package main

import (
	"bytes"
	"fmt"
	"sort"
	"strings"
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
	V         string  `json:"v"`   // target value, for input events
	Tgt       string  `json:"tgt"` // target id
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
}

const typedASCII = "Hello, World! "

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
		// Recorded paths are sampled at ~60 Hz (16.7 ms), and a short move has a short path.
		cs = append(cs, row("humanized second click (want >=4 mousemoves, median gap 8-30 ms)",
			click1 >= 0 && md2 > click1 && len(m) >= 4 && med >= 8 && med <= 30,
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

	var gotK, wantK []string
	for _, e := range ev {
		if e.Tgt == "in" && e.Key != "Shift" && (e.Type == "keydown" || e.Type == "keypress" || e.Type == "keyup") {
			gotK = append(gotK, e.Type+":"+e.Key+":"+e.Code)
		}
	}
	for _, c := range typedASCII {
		code := codeOf(c)
		for _, t := range []string{"keydown", "keypress", "keyup"} {
			wantK = append(wantK, t+":"+string(c)+":"+code)
		}
	}
	// A key event for the é would mean it did not take the insertText path.
	cs = append(cs, row("per ASCII char keydown keypress keyup with key and code, none for é (want 42 key events)", strings.Join(gotK, " ") == strings.Join(wantK, " "),
		"got %d key events", len(gotK)))

	val, inputs := "", 0
	for _, e := range ev {
		if e.Type == "input" && e.Tgt == "in" {
			inputs++
			val = e.V
		}
	}
	cs = append(cs, row("#in value after typing equals the text and ends with é (page-side)", val == r.Typed && strings.HasSuffix(val, "é"),
		"value=%q inputs=%d", val, inputs))

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
