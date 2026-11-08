package rodclient

import (
	"math"
	"math/rand"
	"sort"
	"strings"
	"testing"
	"time"
)

func plan(seed int64, text string, typos bool) []kev {
	r := rand.New(rand.NewSource(seed))
	return planTyping(r, typeItems(r, []rune(text), typos))
}

// sim replays a plan the way a page would see it.
type simResult struct {
	value        string
	backspaces   int
	maxDown      int  // most non-Shift keys down at once
	shiftOK      bool // every shifted key went down with Shift held, no other did
	allReleased  bool
	downBeforeUp bool
	overlaps     int // keyDowns that came while another key was down
}

func sim(evs []kev) simResult {
	res := simResult{shiftOK: true, downBeforeUp: true}
	var val []rune
	down := map[string]bool{}
	shift := false
	for _, e := range evs {
		switch e.op {
		case opShiftDown:
			shift = true
		case opShiftUp:
			shift = false
		case opInsert:
			val = append(val, e.r)
		case opDown:
			if (e.k.mod == shiftBit) != shift {
				res.shiftOK = false
			}
			if len(down) > 0 {
				res.overlaps++
			}
			down[e.k.code] = true
			res.maxDown = max(res.maxDown, len(down))
			switch {
			case e.k.key == "Backspace":
				res.backspaces++
				if len(val) > 0 {
					val = val[:len(val)-1]
				}
			case e.k.text == "\r":
				val = append(val, '\n')
			case e.k.text != "":
				val = append(val, []rune(e.k.text)...)
			}
		case opUp:
			if !down[e.k.code] {
				res.downBeforeUp = false
			}
			delete(down, e.k.code)
		}
	}
	res.value = string(val)
	res.allReleased = len(down) == 0 && !shift
	return res
}

func TestFlightUsesDigraphMedian(t *testing.T) {
	med := func(prev, next rune) time.Duration {
		r := seeded()
		var xs []float64
		for i := 0; i < 20000; i++ {
			xs = append(xs, float64(flight(r, prev, next)))
		}
		sort.Float64s(xs)
		return time.Duration(xs[len(xs)/2])
	}
	for _, c := range []struct {
		p, n rune
		key  string
	}{{'t', 'h', "th"}, {'e', ' ', "espace"}, {' ', 't', "spacet"}} {
		want := digraphFlight[c.key]
		if c.p == ' ' {
			want = time.Duration(float64(want) * flightAfterPunct) // a space counts as punctuation
		}
		if got := med(c.p, c.n); !inRange(got, want*95/100, want*105/100) {
			t.Errorf("%q->%q median %v, want about %v", c.p, c.n, got, want)
		}
	}
	// A pair outside the table keeps the overall median.
	if got := med('1', '2'); !inRange(got, flightMedian*95/100, flightMedian*105/100) {
		t.Errorf("1->2 median %v, want about %v", got, flightMedian)
	}
	// Case does not matter for the lookup.
	if a, b := med('T', 'h'), med('t', 'h'); math.Abs(float64(a-b)) > float64(b)*0.05 {
		t.Errorf("T->h %v vs t->h %v", a, b)
	}
}

func TestRolloverRateNearCalibrated(t *testing.T) {
	text := strings.Repeat("asdfghjkl", 2000) // all plain letters: every pair is eligible
	r := sim(plan(3, text, false))
	rate := float64(r.overlaps) / float64(len(text)-1)
	if math.Abs(rate-rolloverChance) > 0.03 {
		t.Errorf("overlap rate %.3f, want %.3f +-0.03", rate, rolloverChance)
	}
}

func TestRolloverNeverWithoutEligiblePair(t *testing.T) {
	// A Shift change between two keys, a space-less insertText and Backspace never roll.
	for seed := int64(0); seed < 200; seed++ {
		if r := sim(plan(seed, "aBaBaB", false)); r.overlaps != 0 {
			t.Fatalf("seed %d: overlap across a Shift change", seed)
		}
		if r := sim(plan(seed, "aéaéaé", false)); r.overlaps != 0 {
			t.Fatalf("seed %d: overlap next to insertText", seed)
		}
	}
}

func TestRolloverNeverThreeKeysDown(t *testing.T) {
	old := rolloverProb
	rolloverProb = 1 // every eligible pair rolls: the worst case for the cap
	defer func() { rolloverProb = old }()
	for seed := int64(0); seed < 300; seed++ {
		for _, typos := range []bool{false, true} {
			r := sim(plan(seed, "The Quick brown FOX, jumps over 12 lazy dogs!\n", typos))
			if r.maxDown > rolloverMaxDown {
				t.Fatalf("seed %d typos=%v: %d keys down at once", seed, typos, r.maxDown)
			}
			if !r.allReleased || !r.downBeforeUp || !r.shiftOK {
				t.Fatalf("seed %d typos=%v: %+v", seed, typos, r)
			}
		}
	}
}

func TestRolloverOverlapClamp(t *testing.T) {
	old := rolloverProb
	rolloverProb = 1
	defer func() { rolloverProb = old }()
	for seed := int64(0); seed < 100; seed++ {
		evs := plan(seed, strings.Repeat("abcdefgh", 10), false)
		downAt, upAt := map[int]time.Duration{}, map[int]time.Duration{}
		var order []string
		n := 0
		cur := map[string]int{}
		for _, e := range evs {
			switch e.op {
			case opDown:
				downAt[n], cur[e.k.code] = e.at, n
				order = append(order, e.k.code)
				n++
			case opUp:
				upAt[cur[e.k.code]] = e.at
			}
		}
		for i := 0; i < n; i++ {
			if d := upAt[i] - downAt[i]; d < dwellMin || d > dwellMax {
				t.Fatalf("seed %d key %d: dwell %v", seed, i, d)
			}
			if i > 0 && downAt[i] < downAt[i-1]+10*ms {
				t.Fatalf("seed %d key %d: down %v after previous down %v: under 10 ms", seed, i, downAt[i], downAt[i-1])
			}
			if i > 1 && upAt[i-2] > downAt[i] {
				t.Fatalf("seed %d: key %d up %v after key %d down %v", seed, i-2, upAt[i-2], i, downAt[i])
			}
		}
	}
}

const typoText = "Hello, World! It's 2026: the quick brown fox [jumps] over \"lazy\" dogs; ok?\nÉé x"

func TestTypoFinalValueEqualsInput(t *testing.T) {
	old := typoProb
	typoProb = 0.25 // many typos per text, including at the very end
	defer func() { typoProb = old }()
	total := 0
	for seed := int64(0); seed < 400; seed++ {
		text := string([]rune(typoText)[:len([]rune(typoText))-int(seed%7)])
		r := sim(plan(seed, text, true))
		total += r.backspaces
		if r.value != text {
			t.Fatalf("seed %d: value %q, want %q", seed, r.value, text)
		}
		if r.maxDown > rolloverMaxDown || !r.allReleased || !r.shiftOK {
			t.Fatalf("seed %d: %+v", seed, r)
		}
	}
	if total == 0 {
		t.Fatal("no Backspace in 400 runs with typos on")
	}
}

func TestTypoDefaultRateStillExact(t *testing.T) {
	text := strings.Repeat("The quick brown fox, jumps over 12 lazy dogs! ", 40)
	r := sim(plan(5, text, true))
	if r.value != text {
		t.Fatal("final value differs from text")
	}
	if rate := float64(r.backspaces) / float64(len(text)); rate < 0.01 || rate > 0.2 {
		t.Errorf("backspaces per char %.3f, want a few percent", rate)
	}
}

func TestBackspaceOnlyWithTypos(t *testing.T) {
	for seed := int64(0); seed < 300; seed++ {
		if r := sim(plan(seed, typoText, false)); r.backspaces != 0 {
			t.Fatalf("seed %d: %d Backspace with typos off", seed, r.backspaces)
		}
	}
}

func TestTypoNeverOnEnterTabOrOffLayout(t *testing.T) {
	old := typoProb
	typoProb = 1
	defer func() { typoProb = old }()
	for seed := int64(0); seed < 50; seed++ {
		if r := sim(plan(seed, "\t\néé€\n", true)); r.backspaces != 0 {
			t.Fatalf("seed %d: typo on Enter, Tab or insertText", seed)
		}
	}
}

func TestNeighbourIsAdjacentWithSameShiftState(t *testing.T) {
	rows := []string{"`1234567890-=", "qwertyuiop[]\\", "asdfghjkl;'", "zxcvbnm,./"}
	pos := map[rune][2]int{}
	for i, row := range rows {
		for j, c := range row {
			pos[c] = [2]int{i, j}
		}
	}
	pos[' '] = [2]int{4, 4}
	base := func(c rune) rune {
		if k, ok := usKey(c); ok && k.mod == shiftBit {
			if c >= 'A' && c <= 'Z' {
				return c - 'A' + 'a'
			}
			if i := strings.IndexRune(")!@#$%^&*(", c); i >= 0 {
				return rune('0' + i)
			}
			return []rune(unshiftedPunct)[strings.IndexRune(shiftedPunct, c)]
		}
		return c
	}
	r := seeded()
	for _, c := range "aqzm5-/;'[ ]AQZM%_?:\"{ }`~\\|=+,<.>0)1!" {
		seen := map[rune]bool{}
		for i := 0; i < 400; i++ {
			n := neighbour(r, c)
			seen[n] = true
			if n == c {
				t.Fatalf("%q: neighbour is the key itself", c)
			}
			k, ok := usKey(n)
			if !ok {
				t.Fatalf("%q: neighbour %q is not typable", c, n)
			}
			if kc, _ := usKey(c); c != ' ' && (k.mod == shiftBit) != (kc.mod == shiftBit) {
				t.Fatalf("%q: neighbour %q has a different Shift state", c, n)
			}
			a, b := pos[base(c)], pos[base(n)]
			if dr, dc := a[0]-b[0], a[1]-b[1]; dr < -1 || dr > 1 || dc < -2 || dc > 2 {
				t.Fatalf("%q: neighbour %q is not adjacent (%v vs %v)", c, n, a, b)
			}
		}
		if len(seen) < 2 {
			t.Errorf("%q: only %d distinct neighbours", c, len(seen))
		}
	}
}

func TestTypoRunLenDistribution(t *testing.T) {
	r := seeded()
	var got [4]float64
	const n = 40000
	for i := 0; i < n; i++ {
		l := typoRunLen(r)
		if l < 1 || l > 3 {
			t.Fatalf("run length %d", l)
		}
		got[l]++
	}
	for i, p := range typoRunLenProbs {
		if f := got[i+1] / n; math.Abs(f-p) > 0.02 {
			t.Errorf("P(run=%d)=%.3f, want %.3f", i+1, f, p)
		}
	}
}

func TestTypoTimings(t *testing.T) {
	old := typoProb
	typoProb = 0.25
	defer func() { typoProb = old }()
	seen := 0
	for seed := int64(0); seed < 100; seed++ {
		evs := plan(seed, typoText, true)
		var prevDown time.Duration
		prevBS := false
		for i, e := range evs {
			if e.op != opDown {
				continue
			}
			if e.k.key == "Backspace" {
				seen++
				if e.k.code != "Backspace" || e.k.vk != 8 {
					t.Fatalf("Backspace fields %+v", e.k)
				}
				gap := e.at - prevDown
				lo := backspaceFlightMin
				if !prevBS {
					lo = typoNoticeMin
				}
				if gap < lo {
					t.Fatalf("seed %d ev %d: Backspace %v after previous keyDown, want >= %v", seed, i, gap, lo)
				}
				for _, u := range evs[i+1:] {
					if u.op == opUp && u.k.key == "Backspace" {
						if d := u.at - e.at; d < backspaceDwellMin || d > backspaceDwellMax {
							t.Fatalf("Backspace dwell %v", d)
						}
						break
					}
				}
			} else if prevBS && e.at-prevDown < typoRetypeMin {
				t.Fatalf("seed %d: retype %v after last Backspace, want >= %v", seed, e.at-prevDown, typoRetypeMin)
			}
			prevDown, prevBS = e.at, e.k.key == "Backspace"
		}
	}
	if seen == 0 {
		t.Fatal("no Backspace seen")
	}
}
