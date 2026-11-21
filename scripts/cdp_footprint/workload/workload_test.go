package workload

import (
	"errors"
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

func TestOrderedHeadersKeepsWireOrderAndCase(t *testing.T) {
	got, err := OrderedHeaders([]byte(`{"Host":"a","x-lower":"2","Accept":"*/*","X-A":"1"}`))
	if err != nil {
		t.Fatal(err)
	}
	want := [][2]string{{"Host", "a"}, {"x-lower", "2"}, {"Accept", "*/*"}, {"X-A", "1"}}
	if len(got) != len(want) {
		t.Fatalf("got %v", got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("got %v want %v", got, want)
		}
	}
}

func TestStatusNeverTurnsNAIntoOK(t *testing.T) {
	if s := status("x", NA("no API")); s != "n/a: no API" {
		t.Fatal(s)
	}
	if s := status("x", errors.New("boom")); s != "error:boom" {
		t.Fatal(s)
	}
	if s := status("API", nil); s != "ok:API" {
		t.Fatal(s)
	}
}
