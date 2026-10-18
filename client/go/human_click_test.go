package camoucrome

import (
	"encoding/json"
	"math"
	"os"
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
	return nil
}

type fakeMouse struct{ log *[]string }

func (m fakeMouse) Move(x, y float64, _ ...playwright.MouseMoveOptions) error {
	*m.log = append(*m.log, "move")
	return nil
}
func (m fakeMouse) Wheel(dx, dy float64) error { *m.log = append(*m.log, "wheel"); return nil }

var testGeo = geometry{X: 100, Y: 900, W: 120, H: 40, N: 1, BL: 1, BT: 1, VW: 1280, VH: 720, Scroller: "document"}

func run(geos []*geometry, opts playwright.LocatorClickOptions, st *clickProfile) (*fakeTarget, []string) {
	var log []string
	f := &fakeTarget{geos: geos, log: &log}
	_ = act(f, fakeMouse{&log}, nil, opts, st, func() float64 { return 0.4 }, func(time.Duration) {})
	return f, log
}

func TestActPassThroughAndFallbacks(t *testing.T) {
	if f, log := run([]*geometry{&testGeo}, playwright.LocatorClickOptions{Position: &playwright.Position{X: 1, Y: 2}}, nil); len(log) != 1 || f.opts[0].Position.X != 1 {
		t.Fatalf("pass-through: %v", log)
	}
	if _, log := run([]*geometry{nil}, playwright.LocatorClickOptions{}, nil); len(log) != 1 {
		t.Fatalf("nil geometry: %v", log)
	}
	nested := testGeo
	nested.Scroller = "nested"
	if _, log := run([]*geometry{&nested}, playwright.LocatorClickOptions{}, nil); len(log) != 1 {
		t.Fatalf("nested: %v", log)
	}
	_, log := run([]*geometry{&testGeo}, playwright.LocatorClickOptions{}, &clickProfile{scale: 1, windows: true})
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

func TestActWheelsThenScrollNone(t *testing.T) {
	inView := testGeo
	inView.Y = 200
	f, log := run([]*geometry{&testGeo, &testGeo, &inView}, playwright.LocatorClickOptions{}, &clickProfile{scale: 1, windows: true})
	if log[0] != "move" || len(f.opts) != 2 {
		t.Fatalf("log %v opts %d", log, len(f.opts))
	}
	trial, final := f.opts[0], f.opts[1]
	if trial.Trial == nil || !*trial.Trial || final.Scroll == nil || *final.Scroll != *playwright.ScrollModeNone || final.Position == nil || final.Delay != nil {
		t.Fatalf("trial %+v final %+v", trial, final)
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

// Controller ruling 2: the trial timeout is the fixed 2000 ms, never the caller's.
func TestTrialTimeoutIsFixed(t *testing.T) {
	short := 100.0
	inView := testGeo
	inView.Y = 200
	f, _ := run([]*geometry{&inView}, playwright.LocatorClickOptions{Timeout: &short}, nil)
	if len(f.opts) != 2 || f.opts[0].Timeout == nil || *f.opts[0].Timeout != float64(clickTrialTimeoutMs) {
		t.Fatalf("trial timeout: %+v", f.opts)
	}
	if f.opts[1].Timeout == nil || *f.opts[1].Timeout != short {
		t.Fatalf("final timeout must stay the caller's: %+v", f.opts[1])
	}
}
