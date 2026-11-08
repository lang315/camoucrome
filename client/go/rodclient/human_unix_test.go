//go:build unix

package rodclient

import (
	"context"
	"errors"
	"math"
	"math/rand"
	"sort"
	"strings"
	"testing"
	"time"
)

const ms = time.Millisecond

func ns(q req) time.Duration { return time.Duration(q.Params["ns"].(float64)) }

// keyTrace is the keyboard and sleep entries of a drainAll, in order.
func keyTrace(rs []req) []req {
	var out []req
	for _, q := range rs {
		if q.Method == "Input.dispatchKeyEvent" || q.Method == "Input.insertText" || q.Method == "sleep" {
			out = append(out, q)
		}
	}
	return out
}

func isKey(q req, typ, key string) bool {
	return q.Method == "Input.dispatchKeyEvent" && q.Params["type"] == typ && q.Params["key"] == key
}

func inRange(d, lo, hi time.Duration) bool { return d >= lo && d <= hi }

func seeded() *rand.Rand { return rand.New(rand.NewSource(7)) }

func TestDwellDistribution(t *testing.T) {
	r := seeded()
	var xs []float64
	seen := map[time.Duration]bool{}
	for i := 0; i < 5000; i++ {
		d := dwell(r)
		if !inRange(d, 40*ms, 250*ms) {
			t.Fatalf("dwell %v outside 40-250 ms", d)
		}
		seen[d] = true
		xs = append(xs, float64(d))
	}
	sort.Float64s(xs)
	if med := time.Duration(xs[len(xs)/2]); !inRange(med, 85*ms, 105*ms) {
		t.Errorf("median dwell %v, want about 95 ms", med)
	}
	if len(seen) < 4000 {
		t.Errorf("only %d distinct dwells in 5000 draws", len(seen))
	}
}

func TestFlightDistribution(t *testing.T) {
	r := seeded()
	var xs []float64
	seen := map[time.Duration]bool{}
	sum := 0.0
	for i := 0; i < 200; i++ {
		d := flight(r, 'a', 'b')
		if !inRange(d, 60*ms, 600*ms) {
			t.Fatalf("flight %v outside 60-600 ms", d)
		}
		if seen[d] {
			t.Fatalf("flight %v drawn twice in 200 draws", d)
		}
		seen[d] = true
		xs = append(xs, float64(d))
		sum += float64(d)
	}
	sort.Float64s(xs)
	mean, med := sum/200, xs[100]
	if mean <= med {
		t.Errorf("flight not right-skewed: mean %v <= median %v", time.Duration(mean), time.Duration(med))
	}
}

func meanFlight(prev, next rune, n int) float64 {
	r := seeded()
	sum := 0.0
	for i := 0; i < n; i++ {
		sum += float64(flight(r, prev, next))
	}
	return sum / float64(n)
}

func TestFlightLongerAfterPunctAndBeforeShift(t *testing.T) {
	base := meanFlight('a', 'b', 20000)
	if base == 0 {
		t.Fatal("flight is always zero")
	}
	if f := meanFlight('.', 'b', 20000) / base; f < 1.3 || f > 1.5 {
		t.Errorf("after punctuation x%.2f, want about x1.4", f)
	}
	if f := meanFlight('a', 'B', 20000) / base; f < 1.15 || f > 1.35 {
		t.Errorf("before a shifted key x%.2f, want about x1.25", f)
	}
}

func TestFlightThinkingPauseOnlyAtWordBoundary(t *testing.T) {
	// Without a pause a flight after a space is at most 600 ms x 1.4.
	over := func(prev rune) int {
		r := seeded()
		n := 0
		for i := 0; i < 20000; i++ {
			if flight(r, prev, 'b') > 840*ms {
				n++
			}
		}
		return n
	}
	if n := over('a'); n != 0 {
		t.Errorf("%d long flights inside a word", n)
	}
	if n := over(' '); n < 20 || n > 1000 {
		t.Errorf("%d long flights after a space in 20000 draws, want a few percent at most", n)
	}
}

func TestClickPointOffCentreAndInside(t *testing.T) {
	r := seeded()
	var sx, sy float64
	for i := 0; i < 1000; i++ {
		x, y := clickPoint(r, 100, 200, 300, 280) // 200 x 80, centre (200,240)
		if x < 130 || x > 270 || y < 212 || y > 268 {
			t.Fatalf("point (%v,%v) outside the inner 70%%", x, y)
		}
		if x == 200 && y == 240 {
			t.Fatal("point is the exact centre")
		}
		sx += x
		sy += y
	}
	if math.Abs(sx/1000-200) > 6 || math.Abs(sy/1000-240) > 3 {
		t.Errorf("mean point (%v,%v) not around the centre", sx/1000, sy/1000)
	}
}

func TestClickPointTinyBoxUsesCentre(t *testing.T) {
	r := seeded()
	if x, y := clickPoint(r, 10, 10, 17, 17); x != 13.5 || y != 13.5 {
		t.Errorf("7x7 box gave (%v,%v), want its centre", x, y)
	}
}

func TestTypeEveryKeyHasDwell(t *testing.T) {
	r := newRig(t)
	if err := r.p.Type(context.Background(), "#i", "abc"); err != nil {
		t.Fatal(err)
	}
	tr := keyTrace(r.drainAll())
	downs := 0
	for i, q := range tr {
		if q.Method == "Input.dispatchKeyEvent" && q.Params["type"] == "keyDown" {
			downs++
			if i+2 >= len(tr) || tr[i+1].Method != "sleep" || !inRange(ns(tr[i+1]), 40*ms, 250*ms) ||
				tr[i+2].Params["type"] != "keyUp" || tr[i+2].Params["key"] != q.Params["key"] {
				t.Errorf("key %v: keyDown is not followed by a 40-250 ms sleep and its keyUp", q.Params["key"])
			}
		}
	}
	if downs != 3 {
		t.Errorf("%d keyDowns, want 3", downs)
	}
}

func TestTypeFlightBetweenKeys(t *testing.T) {
	r := newRig(t)
	if err := r.p.Type(context.Background(), "#i", "abc"); err != nil {
		t.Fatal(err)
	}
	tr := keyTrace(r.drainAll())
	// keyDown a, sleep, keyUp a, sleep(flight - dwell), keyDown b ...
	var gaps []time.Duration
	for i := 0; i+1 < len(tr); i++ {
		if tr[i].Params["type"] == "keyUp" && tr[i+1].Method == "sleep" {
			gaps = append(gaps, ns(tr[i+1]))
		}
	}
	if len(gaps) != 2 {
		t.Fatalf("%d gaps after keyUp, want 2 (none after the last key)", len(gaps))
	}
	if gaps[0] == gaps[1] {
		t.Errorf("both gaps are %v", gaps[0])
	}
}

func TestTypeShiftBracket(t *testing.T) {
	r := newRig(t)
	if err := r.p.Type(context.Background(), "#i", "Hello, World!"); err != nil {
		t.Fatal(err)
	}
	tr := keyTrace(r.drainAll())
	shifted := map[string]bool{"H": true, "W": true, "!": true}
	var downs, ups int
	held := false
	for i, q := range tr {
		if q.Method != "Input.dispatchKeyEvent" {
			continue
		}
		key, _ := q.Params["key"].(string)
		switch {
		case isKey(q, "keyDown", "Shift"):
			downs++
			if held {
				t.Errorf("Shift pressed twice without a release (event %d)", i)
			}
			held = true
			if q.Params["code"] != "ShiftLeft" || q.Params["windowsVirtualKeyCode"] != float64(16) || q.Params["location"] != float64(1) {
				t.Errorf("Shift keyDown fields %v", q.Params)
			}
			if i+2 >= len(tr) || tr[i+1].Method != "sleep" || !inRange(ns(tr[i+1]), 35*ms, 90*ms) ||
				tr[i+2].Params["type"] != "keyDown" || tr[i+2].Params["modifiers"] != float64(8) {
				t.Errorf("Shift keyDown not followed by a 35-90 ms lead and the shifted key")
			}
		case isKey(q, "keyUp", "Shift"):
			ups++
			if !held {
				t.Errorf("Shift released while not held (event %d)", i)
			}
			held = false
			if i < 2 || tr[i-1].Method != "sleep" || !inRange(ns(tr[i-1]), 10*ms, 60*ms) || tr[i-2].Params["type"] != "keyUp" {
				t.Errorf("Shift keyUp not 10-60 ms after a key's keyUp")
			}
		case q.Params["type"] == "keyDown":
			if shifted[key] != held {
				t.Errorf("key %q keyDown with Shift held = %v, want %v", key, held, shifted[key])
			}
			if shifted[key] && q.Params["modifiers"] != float64(8) {
				t.Errorf("shifted key %q lacks the modifier bit", key)
			}
		}
	}
	if downs != 3 || ups != 3 || held {
		t.Errorf("Shift downs/ups = %d/%d held=%v, want 3/3 released", downs, ups, held)
	}
}

func TestTypeConsecutiveShiftedKeysShareOnePress(t *testing.T) {
	r := newRig(t)
	if err := r.p.Type(context.Background(), "#i", "ABc"); err != nil {
		t.Fatal(err)
	}
	var seq []string
	for _, q := range keyTrace(r.drainAll()) {
		switch {
		case q.Method == "sleep":
		case q.Params["type"] == "keyDown":
			seq = append(seq, "v"+q.Params["key"].(string))
		default:
			seq = append(seq, "^"+q.Params["key"].(string))
		}
	}
	if got, want := strings.Join(seq, " "), "vShift vA ^A vB ^B ^Shift vc ^c"; got != want {
		t.Errorf("got  %s\nwant %s", got, want)
	}
}

func TestTypeOffLayoutRuneHasNoShiftOrDwell(t *testing.T) {
	r := newRig(t)
	if err := r.p.Type(context.Background(), "#i", "é"); err != nil {
		t.Fatal(err)
	}
	for _, q := range keyTrace(r.drainAll()) {
		if q.Method == "Input.dispatchKeyEvent" {
			t.Errorf("key event %v for a rune off the layout", q.Params)
		}
	}
}

func TestClickWaitsBeforeAndDuringPress(t *testing.T) {
	r := newRig(t)
	if err := r.p.Click(context.Background(), "#b"); err != nil {
		t.Fatal(err)
	}
	// start move, move, settle, pressed, hold, released
	var seq []string
	var sl []time.Duration
	for _, q := range r.drainAll() {
		switch q.Method {
		case "Input.dispatchMouseEvent":
			seq = append(seq, q.Params["type"].(string))
		case "sleep":
			seq = append(seq, "sleep")
			sl = append(sl, ns(q))
		}
	}
	if got, want := strings.Join(seq, " "), "mouseMoved mouseMoved sleep mousePressed sleep mouseReleased"; got != want {
		t.Fatalf("got  %s\nwant %s", got, want)
	}
	if !inRange(sl[0], 40*ms, 400*ms) {
		t.Errorf("settle %v outside 40-400 ms", sl[0])
	}
	if !inRange(sl[1], 40*ms, 200*ms) {
		t.Errorf("hold %v outside 40-200 ms", sl[1])
	}
}

func TestHold(t *testing.T) {
	r := newRig(t)
	const d = 1500 * ms
	if err := r.p.Hold(context.Background(), "#b", d); err != nil {
		t.Fatal(err)
	}
	var press, release *req
	var held time.Duration
	var tremor []req
	var gaps []time.Duration
	for _, q := range r.drainAll() {
		q := q
		switch {
		case q.Method == "Input.dispatchMouseEvent" && q.Params["type"] == "mousePressed":
			press = &q
		case q.Method == "Input.dispatchMouseEvent" && q.Params["type"] == "mouseReleased":
			release = &q
		case press != nil && release == nil && q.Method == "sleep":
			held += ns(q)
			gaps = append(gaps, ns(q))
		case press != nil && release == nil && q.Method == "Input.dispatchMouseEvent":
			tremor = append(tremor, q)
		}
	}
	if press == nil || release == nil {
		t.Fatal("no press/release")
	}
	if held != d {
		t.Errorf("held for %v, want exactly %v", held, d)
	}
	if len(tremor) < 1 {
		t.Fatal("no tremor mouseMoved while held")
	}
	px, py := press.Params["x"].(float64), press.Params["y"].(float64)
	for _, m := range tremor {
		if m.Params["type"] != "mouseMoved" || m.Params["buttons"] != float64(1) {
			t.Errorf("tremor event %v, want mouseMoved with buttons 1", m.Params)
		}
		if math.Abs(m.Params["x"].(float64)-px) > 2 || math.Abs(m.Params["y"].(float64)-py) > 2 {
			t.Errorf("tremor (%v,%v) more than 2 px from the press point (%v,%v)", m.Params["x"], m.Params["y"], px, py)
		}
	}
	for i, g := range gaps[:len(gaps)-1] { // the last wait may be cut short to end at d
		if !inRange(g, 120*ms, 300*ms) {
			t.Errorf("tremor gap %d = %v outside 120-300 ms", i, g)
		}
	}
	if release.Params["x"] != press.Params["x"] || release.Params["y"] != press.Params["y"] {
		t.Errorf("released at a different point than pressed")
	}
}

func TestHoldReleasesTheButtonOnError(t *testing.T) {
	r := newRig(t)
	rec := sleep
	n := 0
	sleep = func(ctx context.Context, d time.Duration) error {
		if n++; n == 3 { // settle, then the second tremor wait fails
			return errors.New("boom")
		}
		return rec(ctx, d)
	}
	if err := r.p.Hold(context.Background(), "#b", time.Hour); err == nil {
		t.Fatal("no error")
	}
	var last string
	for _, q := range r.drain() {
		if q.Method == "Input.dispatchMouseEvent" {
			last = q.Params["type"].(string)
		}
	}
	if last != "mouseReleased" {
		t.Errorf("last mouse event %q, want mouseReleased", last)
	}
}
