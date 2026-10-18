// client/go/human_click.go -- SP2d client side (spec §4). Go has no
// launch-wide flag (B): playwright-go returns interfaces that cannot be
// patched. The dwell, hold and path are the browser's (humanize:enabled).
package camoucrome

import (
	"encoding/json"
	"math"
	"math/rand/v2"
	"reflect"
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

func (t locatorTarget) geometry(timeout *float64) *geometry {
	opts := playwright.LocatorEvaluateOptions{Timeout: timeout}
	v, err := t.l.Evaluate(geometryJS, nil, opts)
	if err != nil || v == nil {
		return nil // any failure means: fall back to the stock click
	}
	raw, err := json.Marshal(v)
	if err != nil {
		return nil
	}
	var g geometry
	if json.Unmarshal(raw, &g) != nil {
		return nil
	}
	return &g
}

func (t locatorTarget) Click(o playwright.LocatorClickOptions) error { return t.l.Click(o) }

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
		sent, stuck := 0, 0
		for !visible(*g) {
			n, pause, ok := nextBurst(*g, landing, clickBurst, clickPause, r, clickMaxNotches-sent)
			if !ok || sent >= clickMaxNotches || stuck >= clickNoProgressBursts {
				return t.Click(o)
			}
			wheelNotches(m, n, st.windows, r, sleep)
			sent += int(math.Abs(float64(n)))
			sleep(time.Duration(pause * float64(time.Millisecond)))
			before := g.Y
			if g = t.geometry(o.Timeout); g == nil {
				return t.Click(o)
			}
			if math.Abs(g.Y-before) < 1 {
				stuck++
			} else {
				stuck = 0
			}
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
	trial := final
	trial.Trial = playwright.Bool(true)
	tt := float64(clickTrialTimeoutMs) // fixed: never derived from the caller's timeout
	trial.Timeout = &tt
	if t.Click(trial) != nil {
		wheelNotches(m, 1, st.windows, r, sleep) // a covered target: one corrective burst
		sleep(200 * time.Millisecond)
		if t.Click(trial) != nil {
			return t.Click(o)
		}
	}
	if err := t.Click(final); err != nil {
		return err
	}
	if pos != nil && page != nil {
		lastPoint.Store(page, [2]float64{g.X + g.BL + pos.X, g.Y + g.BT + pos.Y})
	}
	return nil
}

// HumanClick wheels l into view (SP2c notches under a Windows claim) and
// clicks an off-centre point with Scroll: none. A caller's Position, Force or
// Trial passes straight through; anything the helper cannot handle falls
// back to l.Click(opts) unchanged.
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
