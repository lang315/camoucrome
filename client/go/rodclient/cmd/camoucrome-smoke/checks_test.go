package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
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
		add("mousedown", "btn", func(e *Event) { e.Buttons = 1 })
		add("pointerup", "btn", nil)
		add("mouseup", "btn", nil)
		add("click", "btn", nil)
	}
	click(1)
	click(moves)
	val := ""
	for _, c := range typedASCII {
		val += string(c)
		for _, ty := range []string{"keydown", "keypress", "keyup"} {
			ty := ty
			add(ty, "in", func(e *Event) { e.Key, e.Code = string(c), codeOf(c) })
		}
		add("input", "in", func(e *Event) { e.V = val })
	}
	add("input", "in", func(e *Event) { e.V = val + "é" })
	return Run{Events: ev, Sends: map[string]int{"Page.navigate": 3, "DOM.getDocument": 20}, Typed: typedASCII + "é",
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
	if len(cs) != 10 || Failed(cs) {
		t.Fatalf("rows=%d %+v", len(cs), cs)
	}
}

func TestHumanizeRowOnlyWhenAsked(t *testing.T) {
	r := good()
	r.Humanize = false
	if len(Evaluate(r)) != 9 {
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
	r.Events = r.Events[:len(r.Events)-1] // no final input for é
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
