package workload

import (
	"os"
	"path/filepath"
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

func TestEnvIsExactlyTheGivenOne(t *testing.T) {
	t.Setenv("CAMOU_CONFIG", "stale")
	p := filepath.Join(t.TempDir(), "env.json")
	if err := os.WriteFile(p, []byte(`{"A":"1"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	env, err := (&Flags{EnvJSON: p}).Env()
	if err != nil || len(env) != 1 || env[0] != "A=1" {
		t.Fatalf("env = %v, err = %v", env, err)
	}
}
