package main

import (
	"bytes"
	"fmt"
	"sort"
	"strings"
	"time"
)

// Event is one entry of the page's window.__ev log. The page is the source of
// truth: the checks read this, never the client's own return values.
type Event struct {
	Type      string  `json:"type"`
	IsTrusted bool    `json:"isTrusted"`
	T         float64 `json:"t"`
	Button    int     `json:"button"`
	Buttons   int     `json:"buttons"`
	Key       string  `json:"key"`
	Code      string  `json:"code"`
	X         float64 `json:"x"`
	Y         float64 `json:"y"`
	Loc       int     `json:"loc"`   // KeyboardEvent.location
	Shift     bool    `json:"shift"` // event.shiftKey
	V         string  `json:"v"`     // target value, for input events
	Tgt       string  `json:"tgt"`   // target id
}

// Check is one named row.
type Check struct {
	Name   string `json:"name"`
	OK     bool   `json:"ok"`
	Detail string `json:"detail"`
}

// Run is everything the checks look at.
type Run struct {
	Events   []Event
	Sends    map[string]int // CDP method -> count
	PNG      []byte
	Cookies  map[string]string
	Typed    string // what Type was asked to type
	Humanize bool
	Hold     time.Duration // what Hold was asked to hold #pad for

	RolloverText string // what Type was asked to type into #in2 (typos off)
	TyposText    string // what TypeWith{Typos: true} typed into #in3, all chunks
}

// Texts for the key-rollover and typo rows. rolloverText has ~55 pairs of plain
// letters, so no overlap in a run is a ~1e-5 event at the calibrated rate.
const (
	rolloverText = "the quick brown fox jumps over the lazy dog and runs far away"
	typosChunk   = "The quick brown fox, jumps over the lazy dog. Pack my box 12!"
)

// backspaces counts Backspace keydowns on the element with id tgt.
func backspaces(evs []Event, tgt string) (n int) {
	for _, e := range evs {
		if e.Tgt == tgt && e.Type == "keydown" && e.Key == "Backspace" {
			n++
		}
	}
	return n
}

// overlaps replays the keydown and keyup events of one input: how many
// keydowns came while another non-Shift key was down, the most keys down at
// once, and how many were still down at the end.
func overlaps(evs []Event, tgt string) (over, most, left int) {
	down := map[string]bool{}
	for _, e := range evs {
		if e.Tgt != tgt || e.Key == "Shift" {
			continue
		}
		switch e.Type {
		case "keydown":
			if len(down) > 0 {
				over++
			}
			down[e.Code] = true
			most = max(most, len(down))
		case "keyup":
			delete(down, e.Code)
		}
	}
	return over, most, len(down)
}

const typedASCII = "Hello, World! "

// The human-input rows. Each floor is the smallest value rodclient can draw
// (calibrated_floors.go, from settings/human_input.json) less timestampJitterMs
// for event-timestamp jitter, so a healthy run never fails, and it stays far
// above the ~1 ms back-to-back gap of a client without human input.
const timestampJitterMs = 2.0

const (
	minDwellMs = calibDwellMinMs - timestampJitterMs
	minHoldMs  = calibHoldMinMs - timestampJitterMs
	minLeadMs  = calibLeadMinMs - timestampJitterMs
)

// #btn is at left:200 top:150, 120x40 (border box), so its centre is (260,170).
const (
	btnX0, btnY0, btnX1, btnY1 = 200.0, 150.0, 320.0, 190.0
	btnCX, btnCY               = 260.0, 170.0
)

var clickSeq = []string{"pointerdown", "mousedown", "pointerup", "mouseup", "click"}

func row(name string, ok bool, f string, a ...any) Check {
	return Check{name, ok, fmt.Sprintf(f, a...)}
}

func types(evs []Event, keep func(Event) bool) []string {
	var out []string
	for _, e := range evs {
		if keep(e) {
			out = append(out, e.Type)
		}
	}
	return out
}

func index(evs []Event, typ string, nth int) int {
	for i, e := range evs {
		if e.Type == typ && e.Tgt == "btn" {
			if nth == 0 {
				return i
			}
			nth--
		}
	}
	return -1
}

// codeOf is the KeyboardEvent.code of the ASCII characters in typedASCII.
func codeOf(r rune) string {
	switch {
	case r >= 'a' && r <= 'z':
		return "Key" + strings.ToUpper(string(r))
	case r >= 'A' && r <= 'Z':
		return "Key" + string(r)
	}
	return map[rune]string{' ': "Space", ',': "Comma", '!': "Digit1"}[r]
}

// shiftedKey is a typedASCII key that needs Shift on a US layout.
func shiftedKey(k string) bool { return k == "!" || len(k) == 1 && k[0] >= 'A' && k[0] <= 'Z' }

// Evaluate returns the rows; every one has a stated expected count.
func Evaluate(r Run) []Check {
	var cs []Check
	ev := r.Events

	untrusted := 0
	for _, e := range ev {
		if !e.IsTrusted {
			untrusted++
		}
	}
	cs = append(cs, row("events recorded and all isTrusted (want >0 events, 0 untrusted)", len(ev) > 0 && untrusted == 0,
		"events=%d untrusted=%d", len(ev), untrusted))

	got := types(ev, func(e Event) bool {
		if e.Tgt != "btn" {
			return false
		}
		for _, t := range clickSeq {
			if e.Type == t {
				return true
			}
		}
		return false
	})
	want := append(append([]string{}, clickSeq...), clickSeq...)
	cs = append(cs, row("2 clicks on #btn, each pointerdown mousedown pointerup mouseup click", strings.Join(got, " ") == strings.Join(want, " "),
		"got %s", strings.Join(got, " ")))

	md1, md2, click1 := index(ev, "mousedown", 0), index(ev, "mousedown", 1), index(ev, "click", 0)
	moves := func(from, to int) []Event {
		var out []Event
		for i := from + 1; i < to && i < len(ev); i++ {
			if ev[i].Type == "mousemove" {
				out = append(out, ev[i])
			}
		}
		return out
	}
	seed := 0
	if md1 >= 0 {
		seed = len(moves(-1, md1))
	}
	cs = append(cs, row("seeding mousemove before the first mousedown (want >=1)", seed >= 1, "mousemoves=%d", seed))

	if r.Humanize {
		m := moves(click1, md2)
		var gaps []float64
		for i := 1; i < len(m); i++ {
			gaps = append(gaps, m[i].T-m[i-1].T)
		}
		med := 0.0
		if len(gaps) > 0 {
			s := append([]float64{}, gaps...)
			sort.Float64s(s)
			med = s[len(s)/2]
		}
		// Bounds come from the design: the default movement time is within
		// [80, 1200] ms (humanize:minTime/maxTime), recordings are resampled at
		// 60 Hz, so a path has at least floor(80*60/1000) = 4 sampled intervals
		// (interior moves plus the real final event), each delivered separately
		// because the posts are really delayed. The median gap is the 60 Hz
		// period (1000/60 ms, jitter ~1 ms); +-25% is [12.5, 20.8].
		cs = append(cs, row("humanized second click (want >=4 mousemoves, median gap 12.5-20.8 ms)",
			click1 >= 0 && md2 > click1 && len(m) >= 4 && med >= 12.5 && med <= 20.8,
			"mousemoves=%d medianGapMs=%.1f gapsMs=%.1f", len(m), med, gaps))
	}

	bad := 0
	n := 0
	for _, e := range ev {
		if e.Tgt != "btn" {
			continue
		}
		switch e.Type {
		case "mousedown":
			n++
			if e.Buttons != 1 {
				bad++
			}
		case "mouseup":
			n++
			if e.Buttons != 0 {
				bad++
			}
		case "click":
			n++
			if e.Button != 0 {
				bad++
			}
		}
	}
	cs = append(cs, row("mousedown.buttons==1, mouseup.buttons==0, click.button==0 (want 6 events, 0 wrong)", n == 6 && bad == 0,
		"events=%d wrong=%d", n, bad))

	// keydown and keypress come in text order; keyups may trail the next key's
	// keydown (rollover), so they are compared as a set.
	var gotK, wantK, gotUp, wantUp []string
	for _, e := range ev {
		if e.Tgt == "in" && e.Key != "Shift" && (e.Type == "keydown" || e.Type == "keypress" || e.Type == "keyup") {
			if e.Type == "keyup" {
				gotUp = append(gotUp, e.Key+":"+e.Code)
			} else {
				gotK = append(gotK, e.Type+":"+e.Key+":"+e.Code)
			}
		}
	}
	for _, c := range typedASCII {
		code := codeOf(c)
		wantK = append(wantK, "keydown:"+string(c)+":"+code, "keypress:"+string(c)+":"+code)
		wantUp = append(wantUp, string(c)+":"+code)
	}
	sort.Strings(gotUp)
	sort.Strings(wantUp)
	// A key event for the é would mean it did not take the insertText path.
	cs = append(cs, row("per ASCII char keydown and keypress in order, and one keyup each, none for é (want 42 key events)",
		strings.Join(gotK, " ") == strings.Join(wantK, " ") && strings.Join(gotUp, " ") == strings.Join(wantUp, " "),
		"got %d keydown/keypress, %d keyup", len(gotK), len(gotUp)))

	val, inputs := "", 0
	for _, e := range ev {
		if e.Type == "input" && e.Tgt == "in" {
			inputs++
			val = e.V
		}
	}
	cs = append(cs, row("#in value after typing equals the text and ends with é (page-side)", val == r.Typed && strings.HasSuffix(val, "é"),
		"value=%q inputs=%d", val, inputs))

	// Human input: dwell, Shift events, click hold and point, Hold.
	var short []string
	nkeys := 0
	for i, e := range ev {
		if e.Tgt != "in" || e.Type != "keydown" || e.Key == "Shift" {
			continue
		}
		nkeys++
		up := -1
		for j := i + 1; j < len(ev); j++ {
			if ev[j].Type == "keyup" && ev[j].Key == e.Key && ev[j].Tgt == "in" {
				up = j
				break
			}
		}
		if up < 0 || ev[up].T-e.T < minDwellMs {
			short = append(short, e.Key)
		}
	}
	cs = append(cs, row("every key held >= the calibrated floor between keydown and keyup (want 14 keys, 0 short)", nkeys == len(typedASCII) && len(short) == 0,
		"keys=%d short=%q", nkeys, short))

	nshift, badShift := 0, 0
	for i, e := range ev {
		if e.Tgt != "in" || e.Type != "keydown" || !shiftedKey(e.Key) {
			continue
		}
		nshift++
		down, keyUp, up := -1, -1, -1
		for j := i - 1; j >= 0 && down < 0; j-- { // the nearest Shift event before the key
			if ev[j].Key == "Shift" && ev[j].Type == "keydown" {
				down = j
			} else if ev[j].Key == "Shift" {
				break
			}
		}
		for j := i + 1; j < len(ev); j++ {
			if keyUp < 0 && ev[j].Type == "keyup" && ev[j].Key == e.Key {
				keyUp = j
			}
			if ev[j].Type == "keyup" && ev[j].Key == "Shift" {
				up = j
				break
			}
		}
		if down < 0 || ev[down].Loc != 1 || !ev[down].Shift || e.T-ev[down].T < minLeadMs || !e.Shift || keyUp < 0 || up < keyUp {
			badShift++
		}
	}
	cs = append(cs, row("Shift keydown (location 1) >= the calibrated floor before each shifted key, shiftKey true on it, Shift keyup after (want 3 shifted keys, 0 wrong)",
		nshift == 3 && badShift == 0, "shifted=%d wrong=%d", nshift, badShift))

	if r.RolloverText != "" {
		over, most, left := overlaps(ev, "in2")
		cs = append(cs, row("Type: a keydown comes before the previous key's keyup (rollover), never 3 keys down, all released, value exact (want >=1 overlap, max 2)",
			over >= 1 && most <= 2 && left == 0 && lastInputOf(ev, "in2") == r.RolloverText,
			"overlaps=%d maxDown=%d stillDown=%d", over, most, left))
	}
	if r.TyposText != "" {
		_, most, left := overlaps(ev, "in3")
		bs := backspaces(ev, "in3")
		val := lastInputOf(ev, "in3")
		cs = append(cs, row("TypeWith{Typos}: >=1 Backspace keydown, final #in3 value equals the text exactly, never 3 keys down, all released",
			bs >= 1 && val == r.TyposText && most <= 2 && left == 0, "backspaces=%d valueOK=%v maxDown=%d stillDown=%d", bs, val == r.TyposText, most, left))
	}
	cs = append(cs, row("Type without typos sends no Backspace keydown (want 0 on #in and #in2)",
		backspaces(ev, "in")+backspaces(ev, "in2") == 0, "in=%d in2=%d", backspaces(ev, "in"), backspaces(ev, "in2")))

	var holds []float64
	var offs []string
	for i, e := range ev {
		if e.Tgt != "btn" || e.Type != "mousedown" {
			continue
		}
		for j := i + 1; j < len(ev); j++ {
			if ev[j].Type == "mouseup" && ev[j].Tgt == "btn" {
				holds = append(holds, ev[j].T-e.T)
				break
			}
		}
		if e.X < btnX0 || e.X > btnX1 || e.Y < btnY0 || e.Y > btnY1 || e.X == btnCX && e.Y == btnCY {
			offs = append(offs, fmt.Sprintf("(%.1f,%.1f)", e.X, e.Y))
		}
	}
	minHold := 1e9
	for _, h := range holds {
		minHold = min(minHold, h)
	}
	cs = append(cs, row("mousedown to mouseup >= the calibrated floor on both clicks (want 2 clicks, 0 short)", len(holds) == 2 && minHold >= minHoldMs,
		"holdsMs=%.1f", holds))
	cs = append(cs, row("press point inside #btn and not its exact centre (260,170) on both clicks (want 0 bad of 2)", len(holds) == 2 && len(offs) == 0,
		"bad=%v", offs))

	var padDown, padUp float64
	var lastMove, upAt *Event
	haveDown, haveUp, tremor := false, false, 0
	for _, e := range ev {
		if e.Tgt != "pad" {
			continue
		}
		switch {
		case e.Type == "mousedown" && !haveDown:
			padDown, haveDown = e.T, true
		case e.Type == "mousemove" && haveDown && !haveUp && e.Buttons == 1:
			tremor++
			e := e
			lastMove = &e
		case e.Type == "mouseup" && haveDown && !haveUp:
			padUp, haveUp = e.T, true
			e := e
			upAt = &e
		}
	}
	heldMs := padUp - padDown
	cs = append(cs, row("Hold: mousedown, >=1 mousemove with buttons 1, mouseup after >= the asked duration, at the last mousemove's point",
		haveDown && haveUp && tremor >= 1 && heldMs >= float64(r.Hold.Milliseconds()) && lastMove != nil && upAt.X == lastMove.X && upAt.Y == lastMove.Y,
		"down=%v up=%v tremorMoves=%d heldMs=%.1f askedMs=%d lastMove=%v upAt=%v", haveDown, haveUp, tremor, heldMs, r.Hold.Milliseconds(),
		lastMove != nil && upAt != nil && upAt.X == lastMove.X && upAt.Y == lastMove.Y, upAt != nil))

	png := bytes.HasPrefix(r.PNG, []byte("\x89PNG\r\n\x1a\n"))
	cs = append(cs, row("screenshot is a PNG of >=500 bytes", png && len(r.PNG) >= 500, "png=%v bytes=%d", png, len(r.PNG)))

	cs = append(cs, row("cookie set by the page is read back by Cookies (smoke=1)", r.Cookies["smoke"] == "1", "cookies=%v", r.Cookies))

	var forbidden []string
	total := 0
	for m, c := range r.Sends {
		total += c
		// NewPage sends exactly one Page.enable; a second one would come from an op.
		if m == "Runtime.enable" || m == "Network.enable" || m == "DOM.enable" || (m == "Page.enable" && c > 1) ||
			m == "Network.setUserAgentOverride" || strings.HasPrefix(m, "Emulation.") {
			forbidden = append(forbidden, m)
		}
	}
	sort.Strings(forbidden)
	cs = append(cs, row("no Runtime.enable/Emulation.*/Network.enable/DOM.enable, at most 1 Page.enable, observer alive (want 0 forbidden, >=10 sends)",
		len(forbidden) == 0 && total >= 10, "forbidden=%v sends=%d", forbidden, total))
	return cs
}

// Failed reports whether any row is RED.
func Failed(cs []Check) bool {
	for _, c := range cs {
		if !c.OK {
			return true
		}
	}
	return false
}
