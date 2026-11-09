package rodclient

import (
	"context"
	"fmt"
	"math"
	"math/rand"
	"sort"
	"strings"
	"time"
	"unicode"

	"github.com/go-rod/rod"
	"github.com/go-rod/rod/lib/proto"
)

// The timing parameters of human input are in human_params.go, generated from
// settings/human_input.json (public keystroke and mouse datasets; each value's
// source is recorded there). Each duration is lognormal (right-skewed, as human
// timings are) and truncated to [min, max] by redrawing, so no value is drawn
// more often than its neighbours; none is a flat uniform.

// sleep is a var so tests can record waits instead of spending them.
var sleep = realSleep

func realSleep(ctx context.Context, d time.Duration) error {
	if d <= 0 {
		return ctx.Err()
	}
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-time.After(d):
		return nil
	}
}

// lognormal draws median*exp(sigma*N(0,1)) inside [lo, hi] by redrawing.
func lognormal(r *rand.Rand, median time.Duration, sigma float64, lo, hi time.Duration) time.Duration {
	for i := 0; i < 32; i++ {
		d := time.Duration(float64(median) * math.Exp(sigma*r.NormFloat64()))
		if d >= lo && d <= hi {
			return d
		}
	}
	return median
}

// dwell is how long a key stays down.
func dwell(r *rand.Rand) time.Duration {
	return lognormal(r, dwellMedian, dwellSigma, dwellMin, dwellMax)
}

// isShifted reports whether typing r on a US layout needs Shift.
func isShifted(r rune) bool {
	k, ok := usKey(r)
	return ok && k.mod == shiftBit
}

// digraphToken names a key in digraphFlight: a lower-cased letter, or "space".
func digraphToken(r rune) string {
	if r == ' ' {
		return "space"
	}
	return string(unicode.ToLower(r))
}

// flight is the time from one keyDown to the next, for the pair prev, next.
func flight(r *rand.Rand, prev, next rune) time.Duration {
	median := flightMedian
	if m, ok := digraphFlight[digraphToken(prev)+digraphToken(next)]; ok {
		median = m
	}
	d := float64(lognormal(r, median, flightSigma, flightMin, flightMax))
	if unicode.IsSpace(prev) || unicode.IsPunct(prev) || unicode.IsSymbol(prev) {
		d *= flightAfterPunct
	}
	if isShifted(next) {
		d *= flightBeforeShift
	}
	out := time.Duration(d)
	if unicode.IsSpace(prev) && !unicode.IsSpace(next) && r.Float64() < pauseChance {
		out += lognormal(r, pauseMedian, pauseSigma, pauseMin, pauseMax)
	}
	return out
}

// axisPoint draws a Gaussian point around the centre of [lo, hi], inside its inner 70%.
func axisPoint(r *rand.Rand, lo, hi float64) float64 {
	c, w := (lo+hi)/2, hi-lo
	if w < clickMinBox {
		return c
	}
	for i := 0; i < 32; i++ {
		if v := c + r.NormFloat64()*w*clickSpread; math.Abs(v-c) <= clickInner*w {
			return v
		}
	}
	return c
}

// clickPoint is where a person presses inside the box (x0,y0)-(x1,y1).
func clickPoint(r *rand.Rand, x0, y0, x1, y1 float64) (float64, float64) {
	return axisPoint(r, x0, x1), axisPoint(r, y0, y1)
}

// mouse sends one Input.dispatchMouseEvent with the Buttons mask a real mouse
// has; presses and releases carry button left and clickCount 1.
func mouse(rp *rod.Page, op string, t proto.InputDispatchMouseEventType, x, y float64, buttons int) error {
	ev := proto.InputDispatchMouseEvent{Type: t, X: x, Y: y, Buttons: &buttons}
	if t != proto.InputDispatchMouseEventTypeMouseMoved {
		ev.Button, ev.ClickCount = proto.InputMouseButtonLeft, 1
	}
	if err := ev.Call(rp); err != nil {
		return fmt.Errorf("rodclient: %s: %w", op, err)
	}
	return nil
}

// pressAt presses the left button at (x,y), runs while (the held time), then
// releases where while says the pointer ended up, so mouseup sits at the last
// mouseMoved (a pointer cannot jump without a move). When while fails the button
// is still released, on the page without the op's context (which may be the
// reason it failed), so no button is left down.
func (p *Page) pressAt(rp *rod.Page, op string, x, y float64, while func() (float64, float64, error)) error {
	if err := mouse(rp, op, proto.InputDispatchMouseEventTypeMousePressed, x, y, 1); err != nil {
		return err
	}
	x, y, werr := while()
	if werr != nil {
		rp = p.p
	}
	rerr := mouse(rp, op, proto.InputDispatchMouseEventTypeMouseReleased, x, y, 0)
	if werr != nil {
		return fmt.Errorf("rodclient: %s: %w", op, werr)
	}
	return rerr
}

// approach finds the element, scrolls it into view, makes the first-move seed
// if needed, moves to a human press point and settles there. A box that is not
// laid out yet is retried until the op timeout.
func (p *Page) approach(ctx context.Context, rp *rod.Page, selector, op string) (x, y float64, err error) {
	id, err := p.find(ctx, rp, selector)
	if err != nil {
		return 0, 0, fmt.Errorf("rodclient: %s: %w", op, err)
	}
	var q []float64
	var last error
	err = poll(ctx, pollEvery, func() (bool, error) {
		if err := (proto.DOMScrollIntoViewIfNeeded{NodeID: id}).Call(rp); err != nil {
			return false, soft(ctx, err, &last)
		}
		box, err := proto.DOMGetBoxModel{NodeID: id}.Call(rp)
		if err != nil {
			return false, soft(ctx, err, &last)
		}
		if q = box.Model.Content; len(q) != 8 {
			last = fmt.Errorf("box of %d numbers", len(q))
			return false, nil
		}
		return true, nil
	})
	if err != nil {
		if last != nil {
			err = fmt.Errorf("%w (last error: %v)", err, last)
		}
		return 0, 0, fmt.Errorf("rodclient: %s: %w", op, err)
	}
	if !p.moved {
		x0, y0 := p.startPoint(rp)
		if err := mouse(rp, op, proto.InputDispatchMouseEventTypeMouseMoved, x0, y0, 0); err != nil {
			return 0, 0, err
		}
		p.moved = true
	}
	x, y = clickPoint(p.rng, min(q[0], q[2], q[4], q[6]), min(q[1], q[3], q[5], q[7]),
		max(q[0], q[2], q[4], q[6]), max(q[1], q[3], q[5], q[7]))
	if err := mouse(rp, op, proto.InputDispatchMouseEventTypeMouseMoved, x, y, 0); err != nil {
		return 0, 0, err
	}
	if err := sleep(ctx, lognormal(p.rng, settleMedian, settleSigma, settleMin, settleMax)); err != nil {
		return 0, 0, fmt.Errorf("rodclient: %s: %w", op, err)
	}
	return x, y, nil
}

// Hold approaches the element like Click, presses the left button, keeps it
// down for d, then releases. While held it sends a sparse mouseMoved with
// buttons=1, a pixel or two from the press point (hand tremor). d is bounded by
// the op timeout (ctx deadline, else 30 s); on any error the button is released.
// It is a generic primitive, like mouse.down plus mouse.up.
func (p *Page) Hold(ctx context.Context, selector string, d time.Duration) error {
	ctx, cancel := opCtx(ctx)
	defer cancel()
	rp := p.bind(ctx)
	x, y, err := p.approach(ctx, rp, selector, "hold")
	if err != nil {
		return err
	}
	px, py := x, y // the pointer's current position
	return p.pressAt(rp, "hold", x, y, func() (float64, float64, error) {
		for left := d; left > 0; {
			w := min(left, lognormal(p.rng, tremorMedian, tremorSigma, tremorMin, tremorMax))
			if err := sleep(ctx, w); err != nil {
				return px, py, err
			}
			if left -= w; left > 0 {
				dx := max(-tremorPx, min(tremorPx, p.rng.NormFloat64()*tremorSigmaPx))
				dy := max(-tremorPx, min(tremorPx, p.rng.NormFloat64()*tremorSigmaPx))
				if err := mouse(rp, "hold", proto.InputDispatchMouseEventTypeMouseMoved, x+dx, y+dy, 1); err != nil {
					return px, py, err
				}
				px, py = x+dx, y+dy
			}
		}
		return px, py, nil
	})
}

// Tests set these to force a path; production leaves them calibrated.
var (
	rolloverProb = rolloverChance
	typoProb     = typoRate
)

// rolloverMinGap is the least time from a key's keyDown to the keyDown that
// rolls over it.
const rolloverMinGap = 10 * time.Millisecond

type keyKind int

const (
	kindKey       keyKind = iota // a key on the US layout
	kindInsert                   // a rune off the layout, sent by Input.insertText
	kindBackspace                // a typo correction
)

// item is one thing typed: a rune, or a Backspace. gap, when set, replaces the
// drawn flight from the previous keyDown (typo notice, Backspace flight, retype).
type item struct {
	r    rune
	kind keyKind
	gap  time.Duration
}

type evOp int

const (
	opDown evOp = iota
	opUp
	opShiftDown
	opShiftUp
	opInsert
)

// kev is one input event at a time since the start of the text.
type kev struct {
	at time.Duration
	op evOp
	k  usKeyInfo
	r  rune
}

var backspaceKey = usKeyInfo{"Backspace", "Backspace", "", 8, 0}

func typed(c rune) item {
	if _, ok := usKey(c); ok {
		return item{r: c}
	}
	return item{r: c, kind: kindInsert}
}

// typoable: a typable key a person can slip on. Enter and Tab are left alone
// (a typo there submits or moves focus), and so are runes off the layout.
func typoable(c rune) bool {
	_, ok := usKey(c)
	return ok && c != '\n' && c != '\r' && c != '\t'
}

var usRows = [...]string{"`1234567890-=", "qwertyuiop[]\\", "asdfghjkl;'", "zxcvbnm,./"}

// neighbour is a US-QWERTY key next to c: the same row one column over, or the
// rows above and below one column over either way, in c's Shift state. The
// space bar's neighbours are v, b and n.
func neighbour(r *rand.Rand, c rune) rune {
	if c == ' ' {
		return rune("vbn"[r.Intn(3)])
	}
	base, shifted := c, false
	if k, _ := usKey(c); k.mod == shiftBit {
		shifted = true
		switch {
		case c >= 'A' && c <= 'Z':
			base = c - 'A' + 'a'
		case strings.IndexRune(")!@#$%^&*(", c) >= 0:
			base = rune('0' + strings.IndexRune(")!@#$%^&*(", c))
		default:
			base = []rune(unshiftedPunct)[strings.IndexRune(shiftedPunct, c)]
		}
	}
	var cands []rune
	for i, row := range usRows {
		cs := []rune(row)
		for j, b := range cs {
			if b != base {
				continue
			}
			for di := -1; di <= 1; di++ {
				if i+di < 0 || i+di >= len(usRows) {
					continue
				}
				o := []rune(usRows[i+di])
				for dj := -1; dj <= 1; dj++ {
					if (di == 0 && dj == 0) || j+dj < 0 || j+dj >= len(o) {
						continue
					}
					if di == 0 && dj != -1 && dj != 1 {
						continue
					}
					cands = append(cands, o[j+dj])
				}
			}
		}
	}
	n := cands[r.Intn(len(cands))]
	if !shifted {
		return n
	}
	switch {
	case n >= 'a' && n <= 'z':
		return n - 'a' + 'A'
	case n >= '0' && n <= '9':
		return []rune(")!@#$%^&*(")[n-'0']
	default:
		return []rune(shiftedPunct)[strings.IndexRune(unshiftedPunct, n)]
	}
}

// typoRunLen draws how many characters are typed before a typo is noticed.
func typoRunLen(r *rand.Rand) int {
	u := r.Float64()
	for i, p := range typoRunLenProbs {
		if u -= p; u < 0 {
			return i + 1
		}
	}
	return len(typoRunLenProbs)
}

// typeItems is the text as typed. With typos on, each typoable character slips
// with probability typoProb: a neighbour key goes in, run-1 of the correct
// following characters are typed (as far as they are typoable and in the text),
// then the person notices, presses Backspace once per character typed and
// retypes them correctly. The retyped text has no typos of its own, so the
// field's final value is always the text.
func typeItems(r *rand.Rand, runes []rune, typos bool) []item {
	var items []item
	for i := 0; i < len(runes); {
		c := runes[i]
		if !typos || !typoable(c) || r.Float64() >= typoProb {
			items = append(items, typed(c))
			i++
			continue
		}
		n := 1
		for run := typoRunLen(r); n < run && i+n < len(runes) && typoable(runes[i+n]); n++ {
		}
		items = append(items, item{r: neighbour(r, c)})
		for _, f := range runes[i+1 : i+n] {
			items = append(items, typed(f))
		}
		for j := 0; j < n; j++ {
			g := lognormal(r, backspaceFlightMedian, backspaceFlightSigma, backspaceFlightMin, backspaceFlightMax)
			if j == 0 {
				g = lognormal(r, typoNoticeMedian, typoNoticeSigma, typoNoticeMin, typoNoticeMax)
			}
			items = append(items, item{kind: kindBackspace, gap: g})
		}
		for j, f := range runes[i : i+n] {
			it := typed(f)
			if j == 0 {
				it.gap = lognormal(r, typoRetypeMedian, typoRetypeSigma, typoRetypeMin, typoRetypeMax)
			}
			items = append(items, it)
		}
		i += n
	}
	return items
}

type placed struct {
	it       item
	down, up time.Duration
	shifted  bool
}

// planTyping lays the items on a timeline (the shared typing model, spec
// 2026-11-09-human-input-model.md). Each keyDown follows the previous keyDown
// by a flight, never before the previous keyUp, unless the pair rolls over:
// both plain keys under the same Shift state, not the same key (one key cannot
// go down twice), with probability rolloverProb.
// A rolled keyDown comes an overlap before the previous keyUp, at least
// rolloverMinGap after the previous keyDown and never before the keyUp of the
// key before that, so no more than two keys (Shift apart) are ever down. Shift
// goes down a lead before the first shifted key of a run and up a release
// after the last one's keyUp.
func planTyping(r *rand.Rand, items []item) []kev {
	var evs []kev
	var prev, prev2 *placed
	var lastUp time.Duration
	shiftDown := false
	shiftRelease := func(after time.Duration) time.Duration {
		at := after + lognormal(r, shiftReleaseMedian, shiftReleaseSigma, shiftReleaseMin, shiftReleaseMax)
		evs = append(evs, kev{at: at, op: opShiftUp})
		shiftDown = false
		return at
	}
	for _, it := range items {
		var k usKeyInfo
		switch it.kind {
		case kindKey:
			k, _ = usKey(it.r)
		case kindBackspace:
			k = backspaceKey
		}
		shifted := it.kind == kindKey && k.mod == shiftBit
		var floor time.Duration // nothing of this item before this
		if shiftDown && !shifted {
			floor = shiftRelease(prev.up)
		}
		var at time.Duration
		switch {
		case prev == nil:
		case it.gap == 0 && prev.it.kind == kindKey && it.kind == kindKey && prev.shifted == shifted && prev.it.r != it.r && r.Float64() < rolloverProb:
			o := lognormal(r, rolloverOverlapMedian, rolloverOverlapSigma, rolloverOverlapMin, rolloverOverlapMax)
			at = max(prev.up-o, prev.down+rolloverMinGap)
			if prev2 != nil {
				at = max(at, prev2.up+time.Millisecond)
			}
		default:
			gap := it.gap
			if gap == 0 {
				gap = flight(r, prev.it.r, it.r)
			}
			at = max(prev.down+gap, lastUp, floor)
		}
		if shifted && !shiftDown {
			evs = append(evs, kev{at: at, op: opShiftDown})
			shiftDown = true
			at += lognormal(r, shiftLeadMedian, shiftLeadSigma, shiftLeadMin, shiftLeadMax)
		}
		pl := &placed{it: it, down: at, up: at, shifted: shifted}
		if it.kind == kindInsert {
			evs = append(evs, kev{at: at, op: opInsert, r: it.r})
		} else {
			d := dwell(r)
			if it.kind == kindBackspace {
				d = lognormal(r, backspaceDwellMedian, backspaceDwellSigma, backspaceDwellMin, backspaceDwellMax)
			}
			pl.up = at + d
			evs = append(evs, kev{at: at, op: opDown, k: k, r: it.r}, kev{at: pl.up, op: opUp, k: k, r: it.r})
		}
		lastUp = max(lastUp, pl.up)
		prev2, prev = prev, pl
	}
	if shiftDown {
		shiftRelease(prev.up)
	}
	sort.SliceStable(evs, func(i, j int) bool { return evs[i].at < evs[j].at })
	return evs
}

// TypeOptions are the opt-in behaviours of Page.TypeWith.
type TypeOptions struct {
	// Typos makes the typist slip now and then and fix it with Backspace; the
	// final value is still the text.
	Typos bool
}
