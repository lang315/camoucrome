package core

import (
	"os"
	"regexp"
	"testing"
)

func TestParseDisplay(t *testing.T) {
	for raw, want := range map[string]Display{
		`{"gamut":"srgb","colorBits":8,"hdr":false}`:         {"srgb", 8, false},
		`{"gamut":"p3","colorBits":10,"hdr":true}`:           {"p3", 10, true},
		`{"gamut":"rec2020","colorBits":8,"hdr":true,"x":1}`: {"rec2020", 8, true},
	} {
		d, err := ParseDisplay(raw)
		if err != nil || *d != want {
			t.Errorf("%s: %v %v", raw, d, err)
		}
	}
	for _, raw := range []string{`{"gamut":"adobe","colorBits":8,"hdr":false}`, `{"gamut":"srgb","colorBits":12,"hdr":false}`,
		`{"gamut":"srgb","colorBits":8}`, `{"gamut":"srgb","colorBits":8,"hdr":"no"}`, `null`, `[]`, ``} {
		if d, err := ParseDisplay(raw); err == nil {
			t.Errorf("%q accepted as %v", raw, d)
		}
	}
}

func TestDisplayProbeJSMatchesPython(t *testing.T) {
	b, err := os.ReadFile("../../python/camoucrome/probe.py")
	if err != nil {
		t.Skip("not inside the repo")
	}
	m := regexp.MustCompile(`(?s)HOST_DISPLAY_JS = """(.*?)"""`).FindSubmatch(b)
	if m == nil {
		t.Fatal("HOST_DISPLAY_JS not found in probe.py")
	}
	if string(m[1]) != DisplayProbeJS {
		t.Errorf("DisplayProbeJS drifted from probe.py:\n%s\n%s", m[1], DisplayProbeJS)
	}
}
