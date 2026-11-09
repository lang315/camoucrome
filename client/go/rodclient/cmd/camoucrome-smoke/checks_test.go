package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// good builds a log a healthy humanized run would produce.
func good() Run { return goodWith(12, 17) }

// goodWith: moves mousemoves before the second click, gap ms apart.
func goodWith(moves int, gap float64) Run {
	var ev []Event
	t := 0.0
	add := func(typ, tgt string, f func(*Event)) {
		t += 10
		if typ == "mousemove" && len(ev) > 5 {
			t += gap - 10
		}
		e := Event{Type: typ, IsTrusted: true, T: t, Tgt: tgt}
		if f != nil {
			f(&e)
		}
		ev = append(ev, e)
	}
	click := func(moves int) {
		for i := 0; i < moves; i++ {
			add("mousemove", "btn", nil)
		}
		add("pointerdown", "btn", func(e *Event) { e.Buttons = 1 })
		add("mousedown", "btn", func(e *Event) { e.Buttons, e.X, e.Y = 1, 265.5, 172.25 })
		t += 80 // the hold
		add("pointerup", "btn", nil)
		add("mouseup", "btn", nil)
		add("click", "btn", nil)
	}
	click(1)
	click(moves)
	val := ""
	for _, c := range typedASCII {
		val += string(c)
		sh := shiftedKey(string(c))
		if sh {
			t += 20 // Shift pressed 60 ms ahead of the key
			add("keydown", "in", func(e *Event) { e.Key, e.Code, e.Loc, e.Shift = "Shift", "ShiftLeft", 1, true })
			t += 50
		}
		for _, ty := range []string{"keydown", "keypress", "keyup"} {
			ty := ty
			add(ty, "in", func(e *Event) { e.Key, e.Code, e.Shift = string(c), codeOf(c), sh })
			if ty == "keypress" {
				t += 80 // the dwell
			}
		}
		if sh {
			t += 20
			add("keyup", "in", func(e *Event) { e.Key, e.Code, e.Loc = "Shift", "ShiftLeft", 1 })
		}
		add("input", "in", func(e *Event) { e.V = val })
	}
	add("input", "in", func(e *Event) { e.V = val + "é" })
	key := func(typ, tgt, k, v string) {
		t += 40
		add(typ, tgt, func(e *Event) { e.Key, e.Code, e.V = k, "Key"+strings.ToUpper(k), v })
	}
	// #in2: "ab" with b going down before a is up.
	key("keydown", "in2", "a", "")
	key("keydown", "in2", "b", "")
	key("keyup", "in2", "a", "")
	key("keyup", "in2", "b", "")
	key("input", "in2", "", "ab")
	// #in3: a slip (x), Backspace, then the right key.
	for _, k := range [][3]string{{"x", "x", ""}, {"Backspace", "", ""}, {"a", "a", "a"}} {
		key("keydown", "in3", k[0], k[2])
		key("keyup", "in3", k[0], k[2])
		key("input", "in3", "", k[2])
	}
	add("mousedown", "pad", func(e *Event) { e.Buttons = 1 })
	for i := 0; i < 3; i++ {
		t += 200
		add("mousemove", "pad", func(e *Event) { e.Buttons = 1 })
	}
	t += 200
	add("mouseup", "pad", nil)
	add("click", "pad", nil)
	return Run{Hold: 800 * time.Millisecond, Events: ev, Sends: map[string]int{"Page.navigate": 3, "DOM.getDocument": 20}, Typed: typedASCII + "é", RolloverText: "ab", TyposText: "a",
		PNG: append([]byte("\x89PNG\r\n\x1a\n"), make([]byte, 600)...), Cookies: map[string]string{"smoke": "1"}, Humanize: true}
}

func red(t *testing.T, r Run, want string) {
	t.Helper()
	for _, c := range Evaluate(r) {
		if !c.OK && strings.Contains(c.Name, want) {
			return
		}
	}
	t.Errorf("no RED row containing %q: %+v", want, Evaluate(r))
}

func TestGoodRunIsGreen(t *testing.T) {
	cs := Evaluate(good())
	if len(cs) != 18 || Failed(cs) {
		t.Fatalf("rows=%d %+v", len(cs), cs)
	}
}

func TestHumanizeRowOnlyWhenAsked(t *testing.T) {
	r := good()
	r.Humanize = false
	if len(Evaluate(r)) != 17 {
		t.Fatal("humanize row present without the flag")
	}
}

func TestBrokenFixturesAreRed(t *testing.T) {
	r := good()
	r.Events = r.Events[1:] // drops the seeding mousemove
	red(t, r, "seeding mousemove")

	r = good()
	for i := range r.Events {
		if r.Events[i].Type == "mousedown" {
			r.Events[i].Buttons = 0
		}
	}
	red(t, r, "mousedown.buttons")

	r = good()
	r.Sends["Runtime.enable"] = 1
	red(t, r, "at most 1 Page.enable")
	r = good()
	r.Sends = map[string]int{"Emulation.setDeviceMetricsOverride": 1, "X": 20}
	red(t, r, "at most 1 Page.enable")
	r = good()
	r.Sends = map[string]int{"X": 2} // silent observer
	red(t, r, "at most 1 Page.enable")

	r = good()
	r.Events[3].IsTrusted = false
	red(t, r, "isTrusted")

	r = good()
	for i := len(r.Events) - 1; i >= 0; i-- { // no final input for é
		if r.Events[i].Type == "input" && r.Events[i].Tgt == "in" {
			r.Events = append(r.Events[:i], r.Events[i+1:]...)
			break
		}
	}
	red(t, r, "#in value")

	r = good()
	r.PNG = []byte("\x89PNG")
	red(t, r, "screenshot")
	r = good()
	r.Cookies = nil
	red(t, r, "cookie")

	r = good()
	for i := range r.Events {
		if r.Events[i].Type == "keypress" {
			r.Events[i].Type = "keyup"
		}
	}
	red(t, r, "per ASCII char")

}

func TestRolloverAndTypoRowsAreRed(t *testing.T) {
	drop := func(r Run, f func(Event) bool) Run {
		var out []Event
		for _, e := range r.Events {
			if !f(e) {
				out = append(out, e)
			}
		}
		r.Events = out
		return r
	}
	// An old client: a's keyup before b's keydown, no Backspace.
	r := good()
	for i := range r.Events {
		if e := r.Events[i]; e.Tgt == "in2" && e.Type == "keyup" && e.Key == "a" {
			r.Events[i-1], r.Events[i] = r.Events[i], r.Events[i-1] // keyup a, then keydown b
		}
	}
	red(t, r, "Type: a keydown comes before")
	red(t, drop(good(), func(e Event) bool { return e.Tgt == "in3" && e.Key == "Backspace" }), "TypeWith{Typos}")
	r = good()
	r.TyposText = "b" // the field ended with something other than the text
	red(t, r, "TypeWith{Typos}")
	r = good()
	for i := range r.Events {
		if r.Events[i].Tgt == "in2" && r.Events[i].Key == "b" {
			r.Events[i].Key = "Backspace"
		}
	}
	red(t, r, "Type without typos sends no Backspace")
	r = good()
	r.Events = append(r.Events, Event{Type: "keydown", Tgt: "in3", Key: "q", Code: "KeyQ"}, Event{Type: "keydown", Tgt: "in3", Key: "w", Code: "KeyW"},
		Event{Type: "keydown", Tgt: "in3", Key: "e", Code: "KeyE"})
	red(t, r, "never 3 keys down")
}

// each mutates a good run the way a client without human input would.
func TestHumanInputRowsAreRed(t *testing.T) {
	mut := func(f func(ev []Event) []Event) Run {
		r := good()
		r.Events = f(append([]Event{}, r.Events...))
		return r
	}
	// no dwell: every keyup 1 ms after its keydown
	r := mut(func(ev []Event) []Event {
		for i, e := range ev {
			if e.Tgt == "in" && e.Type == "keyup" && e.Key != "Shift" {
				ev[i].T = ev[i-2].T + 1
			}
		}
		return ev
	})
	red(t, r, "every key held")
	// no Shift events at all, as the old client
	r = mut(func(ev []Event) []Event {
		var out []Event
		for _, e := range ev {
			if e.Key != "Shift" {
				out = append(out, e)
			}
		}
		return out
	})
	red(t, r, "Shift keydown")
	// Shift keydown without location 1
	r = mut(func(ev []Event) []Event {
		for i, e := range ev {
			if e.Key == "Shift" {
				ev[i].Loc = 0
			}
		}
		return ev
	})
	red(t, r, "Shift keydown")
	// Shift pressed 1 ms before the key
	r = mut(func(ev []Event) []Event {
		for i, e := range ev {
			if e.Key == "Shift" && e.Type == "keydown" {
				ev[i].T = ev[i+1].T - 1
			}
		}
		return ev
	})
	red(t, r, "Shift keydown")
	// shiftKey false on the shifted key
	r = mut(func(ev []Event) []Event {
		for i, e := range ev {
			if e.Type == "keydown" && shiftedKey(e.Key) {
				ev[i].Shift = false
			}
		}
		return ev
	})
	red(t, r, "Shift keydown")
	// press and release back to back
	r = mut(func(ev []Event) []Event {
		for i, e := range ev {
			if e.Type == "mouseup" && e.Tgt == "btn" {
				ev[i].T = ev[i-2].T + 0.5
			}
		}
		return ev
	})
	red(t, r, "mousedown to mouseup")
	// press at the exact centre
	r = mut(func(ev []Event) []Event {
		for i, e := range ev {
			if e.Type == "mousedown" && e.Tgt == "btn" {
				ev[i].X, ev[i].Y = 260, 170
			}
		}
		return ev
	})
	red(t, r, "press point")
	// press outside the button
	r = mut(func(ev []Event) []Event {
		for i, e := range ev {
			if e.Type == "mousedown" && e.Tgt == "btn" {
				ev[i].X = 400
			}
		}
		return ev
	})
	red(t, r, "press point")
	// Hold with no tremor, released early, or never pressed
	r = mut(func(ev []Event) []Event {
		var out []Event
		for _, e := range ev {
			if !(e.Tgt == "pad" && e.Type == "mousemove") {
				out = append(out, e)
			}
		}
		return out
	})
	red(t, r, "Hold:")
	r = good()
	r.Hold = 5 * time.Second
	red(t, r, "Hold:")
	// mouseup jumps away from the last mousemove
	r = mut(func(ev []Event) []Event {
		for i, e := range ev {
			if e.Tgt == "pad" && e.Type == "mouseup" {
				ev[i].X = 3
			}
		}
		return ev
	})
	red(t, r, "Hold:")
	r = mut(func(ev []Event) []Event {
		var out []Event
		for _, e := range ev {
			if e.Tgt != "pad" {
				out = append(out, e)
			}
		}
		return out
	})
	red(t, r, "Hold:")
}

func TestHumanizedSecondClick(t *testing.T) {
	for _, c := range []struct {
		moves int
		gap   float64
		green bool
	}{{7, 17.5, true}, {4, 17.5, true}, {3, 17.5, false}, {12, 1, false}, {6, 40, false}, {6, 12.0, false}, {6, 21.5, false}} {
		r := goodWith(c.moves, c.gap)
		ok := true
		for _, ch := range Evaluate(r) {
			if strings.HasPrefix(ch.Name, "humanized") {
				ok = ch.OK
				if !strings.Contains(ch.Detail, "mousemoves=") {
					t.Errorf("detail lacks counts: %q", ch.Detail)
				}
			}
		}
		if ok != c.green {
			t.Errorf("moves=%d gap=%v: ok=%v want %v", c.moves, c.gap, ok, c.green)
		}
	}
}

func TestPageEnableAllowedOnce(t *testing.T) {
	r := good()
	r.Sends["Page.enable"] = 1
	if Failed(Evaluate(r)) {
		t.Fatal("one Page.enable (NewPage) must be GREEN")
	}
	r.Sends["Page.enable"] = 2
	red(t, r, "at most 1 Page.enable")
	r = good()
	r.Sends["Runtime.enable"] = 1
	red(t, r, "at most 1 Page.enable")
}

func TestOptionsHumanizeMerge(t *testing.T) {
	f := filepath.Join(t.TempDir(), "c.json")
	os.WriteFile(f, []byte(`{"a:b":1}`), 0o600)
	c, err := parseFlags([]string{"--executable", "/b", "--config", "@" + f, "--humanize", "--headed", "--strict"})
	if err != nil {
		t.Fatal(err)
	}
	o, err := c.options()
	m, _ := o.Config.(map[string]any)
	if err != nil || m["humanize:enabled"] != true || m["a:b"] != float64(1) || *o.Headless || !o.Strict || o.ExecutablePath != "/b" {
		t.Fatalf("%+v %v", o, err)
	}
	c, _ = parseFlags(nil)
	if o, _ := c.options(); o.Config != nil {
		t.Fatalf("config %v without flags", o.Config)
	}
	c, _ = parseFlags([]string{"--config", "{bad"})
	if _, err := c.options(); err == nil {
		t.Fatal("bad config accepted")
	}
}

func TestRunErrors(t *testing.T) {
	var se bytes.Buffer
	if code := run([]string{"--nope"}, &bytes.Buffer{}, &se); code != 2 {
		t.Fatalf("code %d", code)
	}
	se.Reset()
	if code := run([]string{"--executable", "/nonexistent/b"}, &bytes.Buffer{}, &se); code != 1 || !strings.Contains(se.String(), "launch:") {
		t.Fatalf("code %d %q", code, se.String())
	}
}

// The floors follow the generated minimums, so a healthy draw at the minimum
// passes, and stay far above the ~1 ms gap of a client without human input.
func TestFloorsTrackCalibration(t *testing.T) {
	for name, c := range map[string]struct{ floor, min float64 }{
		"dwell": {minDwellMs, calibDwellMinMs},
		"hold":  {minHoldMs, calibHoldMinMs},
		"lead":  {minLeadMs, calibLeadMinMs},
	} {
		if c.floor > c.min {
			t.Errorf("%s floor %.1f above the generated minimum %.1f: a healthy draw would fail", name, c.floor, c.min)
		}
		if c.floor < 10 {
			t.Errorf("%s floor %.1f too close to the ~1 ms back-to-back gap: RED would go green", name, c.floor)
		}
	}
}
