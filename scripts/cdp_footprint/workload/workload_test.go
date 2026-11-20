package workload

import (
	"strings"
	"testing"
)

func TestStringsDiffer(t *testing.T) {
	if ASCII == VI {
		t.Fatal("ASCII == VI")
	}
	hi := false
	for _, r := range VI {
		if r > 0x7F {
			hi = true
		}
	}
	if !hi {
		t.Fatal("VI has no rune > 0x7F")
	}
}

func TestPreludeDeclaresOnly(t *testing.T) {
	if strings.Contains(Prelude, "window") {
		t.Fatal("Prelude mentions window")
	}
	if strings.Contains(strings.Replace(Prelude, "function", "", 1), "=") {
		t.Fatal("Prelude has an assignment")
	}
}
