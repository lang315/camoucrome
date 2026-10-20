package camoucrome

import (
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"os"
	"reflect"
	"strconv"
	"testing"
	"time"

	"github.com/mxschmitt/playwright-go"
)

func stream(xs []float64) func() float64 {
	i := 0
	return func() float64 { v := xs[i]; i++; return v }
}

func near(a, b, tol float64) bool { return math.Abs(a-b) <= tol*math.Max(1, math.Abs(b)) }

func TestVectors(t *testing.T) {
	raw, err := os.ReadFile("../../settings/human_click_vectors.json")
	if err != nil {
		t.Fatal(err)
	}
	var v struct {
		Splitmix64   [][2]string `json:"splitmix64"`
		ProfileScale []struct {
			Seed  *uint32 `json:"seed"`
			Salt  string  `json:"salt"`
			Scale float64 `json:"scale"`
		} `json:"profile_scale"`
		SampleKnots []struct {
			Knots [21]float64 `json:"knots"`
			U     float64     `json:"u"`
			Value float64     `json:"value"`
		} `json:"sample_knots"`
		ClickPosition []struct {
			Geo      geometry    `json:"geo"`
			Last     *[2]float64 `json:"last"`
			Model    offsetModel `json:"model"`
			Scale    float64     `json:"scale"`
			Rand     []float64   `json:"rand"`
			Position *[2]float64 `json:"position"`
		} `json:"click_position"`
		NextBurst []struct {
			Geo     geometry    `json:"geo"`
			Landing float64     `json:"landing"`
			Burst   [21]float64 `json:"burst"`
			Pause   [21]float64 `json:"pause"`
			Rand    []float64   `json:"rand"`
			Out     *[2]float64 `json:"out"`
		} `json:"next_burst"`
	}
	if err := json.Unmarshal(raw, &v); err != nil {
		t.Fatal(err)
	}
	for _, c := range v.Splitmix64 {
		x, _ := strconv.ParseUint(c[0], 16, 64)
		y, _ := strconv.ParseUint(c[1], 16, 64)
		if got := splitmix64(x); got != y {
			t.Errorf("splitmix64(%x) = %x, want %x", x, got, y)
		}
	}
	for _, c := range v.ProfileScale {
		if got := profileScale(c.Seed, c.Salt); !near(got, c.Scale, 1e-12) {
			t.Errorf("profileScale(%v,%s) = %v, want %v", c.Seed, c.Salt, got, c.Scale)
		}
	}
	for _, c := range v.SampleKnots {
		if got := sampleKnots(c.Knots, c.U); !near(got, c.Value, 1e-12) {
			t.Errorf("sampleKnots(u=%v) = %v, want %v", c.U, got, c.Value)
		}
	}
	for i, c := range v.ClickPosition {
		got := clickPosition(c.Geo, c.Last, c.Model, c.Scale, stream(c.Rand))
		if (got == nil) != (c.Position == nil) || (got != nil && (!near(got.X, c.Position[0], 1e-9) || !near(got.Y, c.Position[1], 1e-9))) {
			t.Errorf("clickPosition case %d = %v, want %v", i, got, c.Position)
		}
	}
	for i, c := range v.NextBurst {
		n, pause, ok := nextBurst(c.Geo, c.Landing, c.Burst, c.Pause, stream(c.Rand), clickMaxNotches)
		if ok != (c.Out != nil) || (ok && (float64(n) != c.Out[0] || !near(pause, c.Out[1], 1e-9))) {
			t.Errorf("nextBurst case %d = %d,%v,%v want %v", i, n, pause, ok, c.Out)
		}
	}
}

type fakeTarget struct {
	geos []*geometry
	log  *[]string
	opts []playwright.LocatorClickOptions
	errs []error
}

func (f *fakeTarget) geometry(timeout *float64) *geometry {
	g := f.geos[0]
	if len(f.geos) > 1 {
		f.geos = f.geos[1:]
	}
	return g
}

func (f *fakeTarget) Click(o playwright.LocatorClickOptions) error {
	*f.log = append(*f.log, "click")
	f.opts = append(f.opts, o)
	if len(f.errs) > 0 {
		err := f.errs[0]
		f.errs = f.errs[1:]
		return err
	}
	return nil
}

type fakeMouse struct{ log *[]string }

func (m fakeMouse) Move(x, y float64, _ ...playwright.MouseMoveOptions) error {
	*m.log = append(*m.log, "move")
	return nil
}
func (m fakeMouse) Wheel(dx, dy float64) error { *m.log = append(*m.log, "wheel"); return nil }

var testGeo = geometry{X: 100, Y: 900, W: 120, H: 40, N: 1, BL: 1, BT: 1, VW: 1280, VH: 720, Scroller: "document"}

func run(geos []*geometry, opts playwright.LocatorClickOptions, st *clickProfile, errs ...error) (*fakeTarget, []string, error) {
	var log []string
	f := &fakeTarget{geos: geos, log: &log, errs: errs}
	err := act(f, fakeMouse{&log}, nil, opts, st, func() float64 { return 0.4 }, func(time.Duration) {})
	return f, log, err
}

func TestActPassThroughAndFallbacks(t *testing.T) {
	if f, log, _ := run([]*geometry{&testGeo}, playwright.LocatorClickOptions{Position: &playwright.Position{X: 1, Y: 2}}, nil); len(log) != 1 || f.opts[0].Position.X != 1 {
		t.Fatalf("pass-through: %v", log)
	}
	if _, log, _ := run([]*geometry{nil}, playwright.LocatorClickOptions{}, nil); len(log) != 1 {
		t.Fatalf("nil geometry: %v", log)
	}
	nested := testGeo
	nested.Scroller = "nested"
	if _, log, _ := run([]*geometry{&nested}, playwright.LocatorClickOptions{}, nil); len(log) != 1 {
		t.Fatalf("nested: %v", log)
	}
	_, log, _ := run([]*geometry{&testGeo}, playwright.LocatorClickOptions{}, &clickProfile{scale: 1, windows: true})
	wheels := 0
	for _, e := range log {
		if e == "wheel" {
			wheels++
		}
	}
	if wheels != 2 || log[len(log)-1] != "click" {
		t.Fatalf("no progress: %v", log)
	}
}

type scrollingTarget struct{ geo *geometry }

func (f *scrollingTarget) geometry(*float64) *geometry { g := *f.geo; return &g }
func (f *scrollingTarget) Click(playwright.LocatorClickOptions) error { return nil }

type scrollingMouse struct {
	geo  *geometry
	tops *[]float64
}

func (m scrollingMouse) Move(float64, float64, ...playwright.MouseMoveOptions) error { return nil }
func (m scrollingMouse) Wheel(dx, dy float64) error {
	m.geo.Y -= dy
	*m.tops = append(*m.tops, m.geo.Y)
	return nil
}

// The final top must sit at the landing depth, not near the bottom of the
// viewport, where the target first becomes fully visible.
func TestActWheelsPastFirstVisibilityToTheLandingDepth(t *testing.T) {
	geo := testGeo
	geo.Y, geo.H = 3000, 40
	var tops []float64
	err := act(&scrollingTarget{geo: &geo}, scrollingMouse{geo: &geo, tops: &tops}, nil,
		playwright.LocatorClickOptions{}, &clickProfile{scale: 1, windows: true},
		func() float64 { return 0 }, func(time.Duration) {})
	if err != nil {
		t.Fatal(err)
	}
	first := -1
	for i, y := range tops {
		if y >= 0 && y+geo.H <= geo.VH {
			first = i
			break
		}
	}
	if first < 0 || first >= len(tops)-1 {
		t.Fatalf("stopped at the first fully visible position: %v", tops)
	}
	if math.Abs(geo.Y-0.2*geo.VH) >= 100 {
		t.Fatalf("final top %v, want within 100 of %v", geo.Y, 0.2*geo.VH)
	}
}

// pinLanding replaces the shipped landing knots (which top out at 0.2891, so
// a high r cannot clamp L) with the 0.95 the clamped-goal defect needs.
func pinLanding(t *testing.T) {
	t.Helper()
	old := clickLanding
	for i := range clickLanding {
		clickLanding[i] = 0.95
	}
	t.Cleanup(func() { clickLanding = old })
}

type pageEndTarget struct {
	geo  *geometry
	opts []playwright.LocatorClickOptions
}

func (f *pageEndTarget) geometry(*float64) *geometry { g := *f.geo; return &g }
func (f *pageEndTarget) Click(o playwright.LocatorClickOptions) error {
	f.opts = append(f.opts, o)
	return nil
}

// L clamps to vh - h, so a notch cannot put a visible target inside a 50 px
// window; it must still arrive, not oscillate to the notch budget.
func TestActClampedLandingArrivesWithinOneNotch(t *testing.T) {
	pinLanding(t)
	geo := testGeo
	geo.Y, geo.H = 1200, 40
	var tops []float64
	target := &pageEndTarget{geo: &geo}
	err := act(target, scrollingMouse{geo: &geo, tops: &tops}, nil,
		playwright.LocatorClickOptions{}, &clickProfile{scale: 1, windows: true},
		func() float64 { return 0.5 }, func(time.Duration) {})
	if err != nil {
		t.Fatal(err)
	}
	goal := math.Min(0.95*geo.VH, geo.VH-geo.H)
	if geo.Y < 0 || geo.Y+geo.H > geo.VH {
		t.Fatalf("not visible: %v", geo.Y)
	}
	if math.Abs(geo.Y-goal) >= 100 {
		t.Fatalf("final top %v, want within 100 of %v", geo.Y, goal)
	}
	notches, prev := 0.0, 1200.0
	for _, y := range tops {
		notches += math.Abs(prev-y) / 100
		prev = y
	}
	if notches >= 10 {
		t.Fatalf("%v notches", notches)
	}
	if len(target.opts) != 1 {
		t.Fatalf("clicks: %d", len(target.opts))
	}
	if o := target.opts[0]; o.Scroll == nil || *o.Scroll != *playwright.ScrollModeNone || o.Position == nil {
		t.Fatalf("not a human click: %+v", o)
	}
}

type pageEndMouse struct{ geo *geometry }

func (m pageEndMouse) Move(float64, float64, ...playwright.MouseMoveOptions) error { return nil }
func (m pageEndMouse) Wheel(dx, dy float64) error {
	m.geo.Y = math.Min(m.geo.Y-dy, 380)
	return nil
}

// The target cannot be brought to L=680; held visible at 380, it is clicked
// where the page end left it, not handed to the stock click.
func TestActVisibleAtThePageEndIsClickedNotFallenBack(t *testing.T) {
	pinLanding(t)
	geo := testGeo
	geo.Y, geo.H = -50, 40
	target := &pageEndTarget{geo: &geo}
	err := act(target, pageEndMouse{geo: &geo}, nil,
		playwright.LocatorClickOptions{}, &clickProfile{scale: 1, windows: true},
		func() float64 { return 0.5 }, func(time.Duration) {})
	if err != nil {
		t.Fatal(err)
	}
	if geo.Y != 380 {
		t.Fatalf("page end left the target at %v", geo.Y)
	}
	if len(target.opts) != 1 {
		t.Fatalf("clicks: %d", len(target.opts))
	}
	if o := target.opts[0]; o.Scroll == nil || *o.Scroll != *playwright.ScrollModeNone || o.Position == nil {
		t.Fatalf("not a human click: %+v", o)
	}
}

func TestActFirstClickIsTheRealOne(t *testing.T) {
	inView := testGeo
	inView.Y = 200
	caller := 5000.0
	f, log, err := run([]*geometry{&inView}, playwright.LocatorClickOptions{Timeout: &caller}, &clickProfile{scale: 1, windows: true})
	if err != nil || !reflect.DeepEqual(log, []string{"click"}) || len(f.opts) != 1 {
		t.Fatalf("err %v log %v opts %d", err, log, len(f.opts))
	}
	first := f.opts[0]
	// the first attempt is the real click at the fixed timeout, never the caller's.
	if first.Trial != nil || first.Scroll == nil || *first.Scroll != *playwright.ScrollModeNone ||
		first.Position == nil || first.Delay != nil ||
		first.Timeout == nil || *first.Timeout != float64(clickTrialTimeoutMs) {
		t.Fatalf("first click %+v", first)
	}
}

// A driver timeout earns one corrective burst and one retry; both attempts
// are real clicks at the fixed timeout.
func TestActOneTimeoutRetriesOnce(t *testing.T) {
	inView := testGeo
	inView.Y = 200
	f, log, err := run([]*geometry{&inView}, playwright.LocatorClickOptions{},
		&clickProfile{scale: 1, windows: true}, fmt.Errorf("%w: Timeout 2000ms exceeded", playwright.ErrTimeout))
	if err != nil {
		t.Fatalf("err %v", err)
	}
	if !reflect.DeepEqual(log, []string{"click", "wheel", "click"}) || len(f.opts) != 2 {
		t.Fatalf("log %v opts %d", log, len(f.opts))
	}
	for i, o := range f.opts {
		if o.Timeout == nil || *o.Timeout != float64(clickTrialTimeoutMs) {
			t.Errorf("attempt %d timeout %v", i, o.Timeout)
		}
	}
}

func TestActTwoTimeoutsFallBack(t *testing.T) {
	inView := testGeo
	inView.Y = 200
	caller := 5000.0
	to := func() error { return fmt.Errorf("%w: Timeout 2000ms exceeded", playwright.ErrTimeout) }
	f, log, err := run([]*geometry{&inView}, playwright.LocatorClickOptions{Timeout: &caller},
		&clickProfile{scale: 1, windows: true}, to(), to())
	if err != nil {
		t.Fatalf("fallback must not report the timeout: %v", err)
	}
	if !reflect.DeepEqual(log, []string{"click", "wheel", "click", "click"}) || len(f.opts) != 3 {
		t.Fatalf("log %v opts %d", log, len(f.opts))
	}
	for i := range 2 {
		if f.opts[i].Trial != nil || f.opts[i].Timeout == nil || *f.opts[i].Timeout != float64(clickTrialTimeoutMs) {
			t.Fatalf("attempt %d %+v", i, f.opts[i])
		}
	}
	stock := f.opts[2]
	if stock.Position != nil || stock.Scroll != nil || stock.Timeout == nil || *stock.Timeout != caller {
		t.Fatalf("stock fallback %+v", stock)
	}
}

func TestActNonTimeoutErrorPropagates(t *testing.T) {
	inView := testGeo
	inView.Y = 200
	boom := errors.New("Target closed")
	f, log, err := run([]*geometry{&inView}, playwright.LocatorClickOptions{}, nil, boom)
	if !errors.Is(err, boom) || len(f.opts) != 1 {
		t.Fatalf("err %v opts %d", err, len(f.opts))
	}
	if !reflect.DeepEqual(log, []string{"click"}) {
		t.Fatalf("log %v", log)
	}
}

// Controller ruling 1: humanize:seed 0 is a real uint32 seed (scale is not 1).
func TestClickSeed(t *testing.T) {
	s := clickSeed(map[string]any{"humanize:seed": float64(0)})
	if s == nil || *s != 0 {
		t.Fatalf("seed 0 = %v, want 0", s)
	}
	if got, want := profileScale(s, "offset"), 0.9170564576888419; !near(got, want, 1e-12) {
		t.Errorf("profileScale(seed 0) = %v, want %v", got, want)
	}
	for _, f := range []float64{-1, 1 << 32, 1.5} {
		s := clickSeed(map[string]any{"humanize:seed": f})
		if s != nil {
			t.Errorf("seed %v accepted as %d", f, *s)
		}
		if got := profileScale(s, "offset"); got != 1 {
			t.Errorf("profileScale(seed %v) = %v, want 1", f, got)
		}
	}
	for _, v := range []any{true, "5", nil} {
		if s := clickSeed(map[string]any{"humanize:seed": v}); s != nil {
			t.Errorf("seed %v accepted as %d", v, *s)
		}
	}
	if s := clickSeed(map[string]any{"humanize:seed": float64(math.MaxUint32)}); s == nil || *s != math.MaxUint32 {
		t.Errorf("seed 2^32-1 rejected: %v", s)
	}
}

// SP2d Task 8b: the Go client reads geometry with no page JS. playwright-go
// v0.6201.1 never asks the driver for the isolated world, so instead of
// locator.evaluate the rect comes from BoundingBox and the viewport from CDP
// Page.getLayoutMetrics; both stay driver-side.
func TestGeometryFromBox(t *testing.T) {
	if g := geometryFromBox(nil, 1280, 720); g != nil {
		t.Fatalf("nil box = %+v, want nil", g)
	}
	for _, vp := range [][2]float64{{0, 720}, {1280, 0}, {-1, 720}, {1280, math.NaN()}} {
		if g := geometryFromBox(&playwright.Rect{X: 1, Y: 2, Width: 3, Height: 4}, vp[0], vp[1]); g != nil {
			t.Errorf("viewport %vx%v = %+v, want nil", vp[0], vp[1], g)
		}
	}
	g := geometryFromBox(&playwright.Rect{X: 100, Y: 900, Width: 120, Height: 40}, 1280, 720)
	want := geometry{X: 100, Y: 900, W: 120, H: 40, N: 1, VW: 1280, VH: 720, Scroller: "document"}
	if g == nil || *g != want {
		t.Errorf("normal box = %+v, want %+v", g, want)
	}
}

func TestViewportFromLayoutMetrics(t *testing.T) {
	valid := map[string]any{
		"layoutViewport": map[string]any{"clientWidth": 1265.0, "clientHeight": 705.0},
		"cssLayoutViewport": map[string]any{
			"clientWidth": 1280.0, "clientHeight": 720.0, "pageX": 0.0, "pageY": 0.0,
		},
	}
	if vw, vh, ok := viewportFromLayoutMetrics(valid); !ok || vw != 1280 || vh != 720 {
		t.Errorf("valid metrics = %v,%v,%v, want 1280,720,true", vw, vh, ok)
	}
	for _, c := range []struct {
		name string
		v    any
	}{
		{"nil", nil},
		{"not a map", 1280.0},
		{"missing cssLayoutViewport", map[string]any{"layoutViewport": map[string]any{"clientWidth": 1280.0, "clientHeight": 720.0}}},
		{"cssLayoutViewport not a map", map[string]any{"cssLayoutViewport": 1280.0}},
		{"non-numeric width", map[string]any{"cssLayoutViewport": map[string]any{"clientWidth": "1280", "clientHeight": 720.0}}},
		{"non-numeric height", map[string]any{"cssLayoutViewport": map[string]any{"clientWidth": 1280.0, "clientHeight": true}}},
		{"zero width", map[string]any{"cssLayoutViewport": map[string]any{"clientWidth": 0.0, "clientHeight": 720.0}}},
		{"zero height", map[string]any{"cssLayoutViewport": map[string]any{"clientWidth": 1280.0, "clientHeight": 0.0}}},
	} {
		if vw, vh, ok := viewportFromLayoutMetrics(c.v); ok {
			t.Errorf("%s = %v,%v,true, want ok=false", c.name, vw, vh)
		}
	}
}

// --- round 2: delivery, corrective notch, tall targets ----------------------

func timeoutWithLog(log string) error {
	return fmt.Errorf("%w: %s", playwright.ErrTimeout, "Timeout 2000ms exceeded.\n  "+log)
}

const (
	deliveredLog    = "- <header> intercepts pointer events\n  - retrying click action\n  - performing click action"
	notDeliveredLog = "- <header> intercepts pointer events\n  - retrying click action"
	// An earlier 'performing' line does not describe the attempt that timed out.
	performingBeforeRetryLog = "- performing click action\n  - <header> intercepts pointer events\n  - retrying click action\n  - waiting for element to be visible"
)

func TestActTimeoutAfterDeliveryStartedIsNotRetried(t *testing.T) {
	inView := testGeo
	inView.Y = 200
	f, log, err := run([]*geometry{&inView}, playwright.LocatorClickOptions{}, nil, timeoutWithLog(deliveredLog))
	if !errors.Is(err, playwright.ErrTimeout) || len(f.opts) != 1 {
		t.Fatalf("err %v opts %d", err, len(f.opts))
	}
	if !reflect.DeepEqual(log, []string{"click"}) {
		t.Fatalf("log %v", log)
	}
}

func TestActTimeoutBeforeDeliveryStillRetries(t *testing.T) {
	inView := testGeo
	inView.Y = 200
	f, log, err := run([]*geometry{&inView}, playwright.LocatorClickOptions{}, nil, timeoutWithLog(notDeliveredLog))
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(log, []string{"click", "wheel", "click"}) || len(f.opts) != 2 {
		t.Fatalf("log %v opts %d", log, len(f.opts))
	}
}

func TestActPerformingBeforeTheLastRetryIsNotDelivery(t *testing.T) {
	inView := testGeo
	inView.Y = 200
	f, log, err := run([]*geometry{&inView}, playwright.LocatorClickOptions{}, nil, timeoutWithLog(performingBeforeRetryLog))
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(log, []string{"click", "wheel", "click"}) || len(f.opts) != 2 {
		t.Fatalf("log %v opts %d", log, len(f.opts))
	}
}

type notchMouse struct{ deltas []float64 }

func (m *notchMouse) Move(float64, float64, ...playwright.MouseMoveOptions) error { return nil }
func (m *notchMouse) Wheel(dx, dy float64) error {
	m.deltas = append(m.deltas, dy)
	return nil
}

func TestActCorrectiveNotchMovesAwayFromTheCover(t *testing.T) {
	for _, c := range []struct{ y, delta float64 }{{100, -100}, {600, 100}} {
		geo := testGeo
		geo.Y = c.y
		var log []string
		f := &fakeTarget{geos: []*geometry{&geo}, log: &log, errs: []error{timeoutWithLog(notDeliveredLog)}}
		mouse := &notchMouse{}
		err := act(f, mouse, nil, playwright.LocatorClickOptions{}, nil,
			func() float64 { return 0.5 }, func(time.Duration) {})
		if err != nil {
			t.Fatal(err)
		}
		if !reflect.DeepEqual(mouse.deltas, []float64{c.delta}) {
			t.Fatalf("y=%v deltas %v, want [%v]", c.y, mouse.deltas, c.delta)
		}
	}
}

// fakePage is a playwright.Page key for lastPoint: act only stores it.
type fakePage struct{ playwright.Page }

func TestActSecondAttemptRecordsThePointAfterTheCorrectiveNotch(t *testing.T) {
	for _, c := range []struct{ y, dir float64 }{{100, -1}, {600, 1}} {
		geo := testGeo
		geo.Y = c.y
		page := fakePage{}
		var log []string
		f := &fakeTarget{geos: []*geometry{&geo}, log: &log, errs: []error{timeoutWithLog(notDeliveredLog)}}
		err := act(f, fakeMouse{&log}, page, playwright.LocatorClickOptions{}, nil,
			func() float64 { return 0.5 }, func(time.Duration) {})
		if err != nil {
			t.Fatal(err)
		}
		pos := f.opts[1].Position
		want := [2]float64{geo.X + geo.BL + pos.X, geo.Y + geo.BT + pos.Y - 100*c.dir}
		got, ok := lastPoint.Load(page)
		if !ok {
			t.Fatalf("y=%v no last point stored", c.y)
		}
		if got.([2]float64) != want {
			t.Fatalf("y=%v last point %v, want %v", c.y, got, want)
		}
	}
}

// bounceTarget alternates between two non-visible tops, as a tall target does
// when each direction lands it just out of view.
type bounceTarget struct {
	i    int
	opts []playwright.LocatorClickOptions
}

func (f *bounceTarget) geometry(*float64) *geometry {
	g := testGeo
	g.Y, g.H = []float64{70, -30}[f.i%2], 700
	f.i++
	return &g
}

func (f *bounceTarget) Click(o playwright.LocatorClickOptions) error {
	f.opts = append(f.opts, o)
	return nil
}

func TestActBouncingTallTargetStopsAtTheStuckLimit(t *testing.T) {
	target := &bounceTarget{}
	mouse := &notchMouse{}
	err := act(target, mouse, nil, playwright.LocatorClickOptions{}, &clickProfile{scale: 1, windows: true},
		func() float64 { return 0.5 }, func(time.Duration) {})
	if err != nil {
		t.Fatal(err)
	}
	if n := len(mouse.deltas); n == 0 || n > 4 { // two bursts + the corrective notch
		t.Fatalf("%d wheels", n)
	}
	if o := target.opts[len(target.opts)-1]; o.Scroll != nil || o.Position != nil {
		t.Fatalf("not the stock fallback: %+v", o)
	}
}
