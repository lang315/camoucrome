package rodclient

import (
	"context"
	"fmt"
	"math"
	"math/rand"
	"time"
	"unicode"

	"github.com/go-rod/rod"
	"github.com/go-rod/rod/lib/proto"
)

// Timing parameters of human input. They are the maintainers' choice from
// published keystroke and pointing studies (e.g. Dhakal et al., CHI 2018, 136M
// keystrokes; Fitts-law pointing work). They are NOT calibrated on a person.
// Each duration is lognormal (right-skewed, as human timings are) and
// truncated to [min, max] by redrawing, so no value is drawn more often than
// its neighbours; none is a flat uniform.
const (
	dwellMedian = 95 * time.Millisecond  // key hold time of a typical typist: about 90-100 ms in large typing studies
	dwellSigma  = 0.30                   // log-scale spread of the key hold time
	dwellMin    = 40 * time.Millisecond  // shortest plausible key hold
	dwellMax    = 250 * time.Millisecond // a very slow press

	flightMedian = 160 * time.Millisecond // keyDown-to-keyDown of a fast-to-average typist (about 75 wpm)
	flightSigma  = 0.45                   // inter-key intervals are right-skewed with a long tail
	flightMin    = 60 * time.Millisecond  // fastest sustained key pairs
	flightMax    = 600 * time.Millisecond // beyond this it is a pause, modelled separately

	flightAfterPunct  = 1.4  // typists slow down after a space or punctuation (word and clause boundaries)
	flightBeforeShift = 1.25 // reaching for Shift costs time before a capital or symbol

	pauseChance = 0.03                   // rare thinking pause at a word boundary
	pauseMedian = 500 * time.Millisecond // typical hesitation between words
	pauseSigma  = 0.40                   // log-scale spread of the pause
	pauseMin    = 300 * time.Millisecond // shorter than this is not a pause
	pauseMax    = 900 * time.Millisecond // longer pauses are rarer than the model needs

	shiftLeadMedian = 55 * time.Millisecond // the Shift finger lands about 35-90 ms before the letter
	shiftLeadSigma  = 0.30                  // log-scale spread of the Shift lead
	shiftLeadMin    = 35 * time.Millisecond // Shift never lands less than this before the key
	shiftLeadMax    = 90 * time.Millisecond // nor more than this

	shiftReleaseMedian = 30 * time.Millisecond // Shift is let go shortly after the letter
	shiftReleaseSigma  = 0.50                  // release is sloppier than the press
	shiftReleaseMin    = 10 * time.Millisecond // fastest release after the key's keyUp
	shiftReleaseMax    = 60 * time.Millisecond // slowest release after the key's keyUp

	settleMedian = 120 * time.Millisecond // pointer rests briefly on the target before the press
	settleSigma  = 0.40                   // log-scale spread of the settle
	settleMin    = 40 * time.Millisecond  // shortest settle
	settleMax    = 400 * time.Millisecond // longest settle before it reads as hesitation

	clickHoldMedian = 85 * time.Millisecond  // mouse button hold of a normal click: about 80-100 ms
	clickHoldSigma  = 0.30                   // log-scale spread of the hold
	clickHoldMin    = 40 * time.Millisecond  // shortest plausible click
	clickHoldMax    = 200 * time.Millisecond // a slow click

	tremorMedian  = 190 * time.Millisecond // a held hand drifts a pixel or two every 120-300 ms
	tremorSigma   = 0.30                   // log-scale spread of the interval
	tremorMin     = 120 * time.Millisecond // fastest drift
	tremorMax     = 300 * time.Millisecond // slowest drift
	tremorPx      = 2.0                    // drift stays within 2 px of the press point
	tremorSigmaPx = 0.8                    // most drifts are under a pixel

	clickSpread = 1.0 / 6 // Gaussian sigma of the click point, as a fraction of the box side
	clickInner  = 0.35    // the point stays within centre +-35% of the side (the inner 70%)
	clickMinBox = 8.0     // a side under 8 px: its centre
)

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

// flight is the time from one keyDown to the next, for the pair prev, next.
func flight(r *rand.Rand, prev, next rune) time.Duration {
	d := float64(lognormal(r, flightMedian, flightSigma, flightMin, flightMax))
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
