package main

import (
	"strings"
	"testing"
)

var good = expected{TZ: "Europe/Berlin", Lang: "de-DE", Langs: []string{"de-DE", "de"}, Cores: 8}

func obs() observed {
	return observed{TZ: "Europe/Berlin", Lang: "de-DE", Langs: []string{"de-DE", "de"}, Cores: 8}
}

func TestJudgeAcceptsTheExpected(t *testing.T) {
	if bad := judge(good, obs()); len(bad) != 0 {
		t.Errorf("%v", bad)
	}
}

func TestJudgeRows(t *testing.T) {
	for want, mut := range map[string]func(*observed){
		"timeZone":            func(o *observed) { o.TZ = "UTC" },
		"language":            func(o *observed) { o.Langs = []string{"de-DE"} },
		"hardwareConcurrency": func(o *observed) { o.Cores = 16 },
		"server-reflexive":    func(o *observed) { o.Cands = []string{"candidate:1 1 udp 1 abc.local 1 typ srflx"} },
		"raw address":         func(o *observed) { o.Cands = []string{"candidate:1 1 udp 1 192.0.2.7 5000 typ host"} },
		"raw address in":      func(o *observed) { o.Cands = []string{"candidate:1 1 udp 1 2001:db8::1 5000 typ host"} },
		"disable_non_proxied": func(o *observed) { o.Cands = []string{"candidate:1 1 udp 1 abc.local 5000 typ host"} },
	} {
		o := obs()
		mut(&o)
		bad := strings.Join(judge(good, o), "|")
		if !strings.Contains(bad, want) {
			t.Errorf("%s: %q", want, bad)
		}
	}
}
