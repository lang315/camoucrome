// client/go/human_click.go -- SP2d client side (spec §4). Go has no
// launch-wide flag (B): playwright-go returns interfaces that cannot be
// patched. The dwell, hold and path are the browser's (humanize:enabled).
package camoucrome

import (
	"errors"
	"math"
	"math/rand/v2"
	"reflect"
	"strings"
	"sync"
	"time"

	"github.com/mxschmitt/playwright-go"
)

type clickProfile struct {
	scale   float64
	windows bool
}

var (
	clickState sync.Map // raw playwright.BrowserContext -> *clickProfile
	lastPoint  sync.Map // playwright.Page -> [2]float64
)

// clickStateKey is the clickState key for ctx, if it can be one: sync.Map
// hashes its key, and an interface whose dynamic type is not comparable
// (a value-typed test double) would panic. The driver's context is a pointer.
func clickStateKey(ctx playwright.BrowserContext) (any, bool) {
	if ctx == nil || !reflect.TypeOf(ctx).Comparable() {
		return nil, false
	}
	return ctx, true
}

// clickSeed is humanize:seed when it is a real uint32 (0 included); any other
// shape, bool and string alike, is absent. A JSON number arrives as float64.
func clickSeed(eff map[string]any) *uint32 {
	f, ok := eff["humanize:seed"].(float64)
	if !ok || !(f >= 0) || f > math.MaxUint32 || f != math.Trunc(f) {
		return nil
	}
	s := uint32(f)
	return &s
}

type clickTarget interface {
	geometry(timeout *float64) *geometry
	Click(playwright.LocatorClickOptions) error
}

type mouser interface {
	Move(x, y float64, options ...playwright.MouseMoveOptions) error
	Wheel(dx, dy float64) error
}

type locatorTarget struct{ l playwright.Locator }

// geometry reads the element's box and the layout viewport with no page JS.
// playwright-go v0.6201.1 never sends isolatedContext and accepts only driver
// 1.62.1, so locator.evaluate would run in the main world -- forbidden by
// spec §4 step 2 (amended 2026-10-18). BoundingBox and CDP
// Page.getLayoutMetrics are driver-side, invisible to page scripts.
//
// shortcut: only rect[0] of the box is available, so what geometryJS measured
// is lost -- border width (bl/bt are 0), multi-rect inline elements (n is 1),
// transform detection (t is false) and nested-scroller detection (scroller is
// "document"; a wrongly-scrolled target is caught only by the no-progress
// stop).
func (t locatorTarget) geometry(timeout *float64) *geometry {
	box, err := t.l.BoundingBox(playwright.LocatorBoundingBoxOptions{Timeout: timeout})
	if err != nil || box == nil {
		return nil // any failure means: fall back to the stock click
	}
	page, err := t.l.Page()
	if err != nil || page == nil {
		return nil
	}
	s, err := page.Context().NewCDPSession(page)
	if err != nil {
		return nil
	}
	raw, err := s.Send("Page.getLayoutMetrics", nil)
	_ = s.Detach() // always, also on the error path
	if err != nil {
		return nil
	}
	vw, vh, ok := viewportFromLayoutMetrics(raw)
	if !ok {
		return nil
	}
	return geometryFromBox(box, vw, vh)
}

// geometryFromBox converts a bounding box and layout viewport into the
// geometry the path math reads. Pure, so the conversion is testable offline.
func geometryFromBox(box *playwright.Rect, vw, vh float64) *geometry {
	if box == nil || !(vw > 0) || !(vh > 0) {
		return nil
	}
	return &geometry{
		X: box.X, Y: box.Y, W: box.Width, H: box.Height, N: 1,
		VW: vw, VH: vh, Scroller: "document",
	}
}

// viewportFromLayoutMetrics pulls cssLayoutViewport's clientWidth and
// clientHeight out of the decoded Page.getLayoutMetrics reply. A missing
// viewport, a non-numeric number or a non-positive size reports ok=false.
func viewportFromLayoutMetrics(v any) (vw, vh float64, ok bool) {
	m, ok := v.(map[string]any)
	if !ok {
		return 0, 0, false
	}
	lv, ok := m["cssLayoutViewport"].(map[string]any)
	if !ok {
		return 0, 0, false
	}
	vw, okW := lv["clientWidth"].(float64)
	vh, okH := lv["clientHeight"].(float64)
	if !okW || !okH || !(vw > 0) || !(vh > 0) {
		return 0, 0, false
	}
	return vw, vh, true
}

func (t locatorTarget) Click(o playwright.LocatorClickOptions) error { return t.l.Click(o) }

// maybeDelivered reports whether the driver's call log shows the press was
// dispatched: 'performing click action' after the last 'retrying click action'
// means a retry would double-click.
func maybeDelivered(err error) bool {
	text := err.Error()
	performed := strings.LastIndex(text, "performing click action")
	if performed < 0 {
		return false
	}
	retried := strings.LastIndex(text, "retrying click action")
	return retried < 0 || performed > retried
}

func wheelNotches(m mouser, notches int, windows bool, r func() float64, sleep func(time.Duration)) {
	if windows {
		_ = m.Wheel(0, float64(notches*100)) // SP2c splits it into notches
		return
	}
	step := 100.0
	if notches < 0 {
		step = -100
	}
	for range int(math.Abs(float64(notches))) {
		_ = m.Wheel(0, step)
		sleep(time.Duration((18 + 42*r()) * float64(time.Millisecond)))
	}
}

// act is HumanClick's body; page is the key for the last point (nil in tests).
func act(t clickTarget, m mouser, page playwright.Page, o playwright.LocatorClickOptions, st *clickProfile, r func() float64, sleep func(time.Duration)) error {
	if o.Position != nil || o.Force != nil || o.Trial != nil {
		return t.Click(o)
	}
	g := t.geometry(o.Timeout)
	if g == nil || g.Scroller != "document" || g.X < 0 || g.X+g.W > g.VW {
		return t.Click(o)
	}
	if st == nil {
		st = &clickProfile{scale: 1}
	}
	if !visible(*g) {
		pt := [2]float64{g.VW * (0.1 + 0.8*r()), g.VH * (0.1 + 0.8*r())}
		_ = m.Move(pt[0], pt[1])
		if page != nil {
			lastPoint.Store(page, pt)
		}
		landing := sampleKnots(clickLanding, r())
		sent, stuck, prevSign := 0, 0, 0
		for {
			n, pause, ok := nextBurst(*g, landing, clickBurst, clickPause, r, clickMaxNotches-sent)
			if !ok {
				break
			}
			if sent >= clickMaxNotches || stuck >= clickNoProgressBursts {
				if visible(*g) { // the page end: arrived as far as it can
					break
				}
				return t.Click(o)
			}
			wheelNotches(m, n, st.windows, r, sleep)
			sent += int(math.Abs(float64(n)))
			sleep(time.Duration(pause * float64(time.Millisecond)))
			before := g.Y
			if g = t.geometry(o.Timeout); g == nil {
				return t.Click(o)
			}
			sign := 1
			if n < 0 {
				sign = -1
			}
			if (prevSign != 0 && sign != prevSign) || math.Abs(g.Y-before) < 1 {
				stuck++ // a reversal is a bounce, not progress
			} else {
				stuck = 0
			}
			prevSign = sign
		}
	}
	var last *[2]float64
	if page != nil {
		if v, ok := lastPoint.Load(page); ok {
			p := v.([2]float64)
			last = &p
		}
	}
	pos := clickPosition(*g, last, clickOffset, st.scale, r)
	final := o
	final.Scroll = playwright.ScrollModeNone
	final.Position = pos
	attemptTimeout := float64(clickTrialTimeoutMs) // fixed: the first attempt's timeout, never the caller's
	final.Timeout = &attemptTimeout
	dir := 1
	if g.Y+g.H/2 < g.VH/2 { // away from a cover at the top
		dir = -1
	}
	for attempt := range 2 {
		err := t.Click(final)
		if err == nil {
			if pos != nil && page != nil {
				y := g.Y + g.BT + pos.Y
				if attempt == 1 {
					y -= 100 * float64(dir) // the corrective notch moved the target
				}
				lastPoint.Store(page, [2]float64{g.X + g.BL + pos.X, y})
			}
			return nil
		}
		if !errors.Is(err, playwright.ErrTimeout) {
			// The click may already have been delivered: a second one would double-click.
			return err
		}
		if maybeDelivered(err) {
			// The press was dispatched before the deadline: a retry would double-click.
			return err
		}
		if attempt == 1 {
			return t.Click(o)
		}
		wheelNotches(m, dir, st.windows, r, sleep) // a covered target: one corrective burst
		sleep(200 * time.Millisecond)
	}
	return nil
}

// HumanClick wheels l into view (SP2c notches under a Windows claim) and
// clicks an off-centre point with Scroll: none. The first attempt is the real
// click at a fixed timeout; a driver timeout earns one corrective burst and
// one retry, after which the stock l.Click(opts) takes over. A caller's
// Position, Force or Trial passes straight through.
func HumanClick(l playwright.Locator, opts ...playwright.LocatorClickOptions) error {
	var o playwright.LocatorClickOptions
	if len(opts) > 0 {
		o = opts[0] // a copy: the caller's struct is never changed
	}
	page, err := l.Page()
	if err != nil {
		return l.Click(o) // an errored locator: the stock path carries the error
	}
	var st *clickProfile
	if key, ok := clickStateKey(page.Context()); ok {
		if v, ok := clickState.Load(key); ok {
			st = v.(*clickProfile)
		}
	}
	return act(locatorTarget{l}, page.Mouse(), page, o, st, rand.Float64, time.Sleep)
}
