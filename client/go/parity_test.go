package camoucrome

// Parity with client/go/core: both read core/testdata/parity.json. Reading a
// fixture, not importing core, keeps this module free of a new dependency.
// PARITY_REGEN=1 rewrites the fixture's expected env and argv from THIS
// package (the reference); hand-check the diff.

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"slices"
	"strings"
	"testing"
)

const parityPath = "core/testdata/parity.json"

type parityCase struct {
	Name        string         `json:"name"`
	HostOS      string         `json:"hostOS"`
	FontsDir    string         `json:"fontsDir,omitempty"`
	Config      map[string]any `json:"config"`
	PadChars    int            `json:"padChars,omitempty"`
	Window      [2]int         `json:"window"`
	DPR         float64        `json:"dpr"`
	Position    [2]int         `json:"position"`
	Headless    bool           `json:"headless"`
	Strict      bool           `json:"strict,omitempty"`
	UserDataDir string         `json:"userDataDir"`
	ExtraArgs   []string       `json:"extraArgs"`
	Args        []string       `json:"args"`
	WantErr     bool           `json:"wantErr"`
	Env         []string       `json:"env"`
	Argv        []string       `json:"argv"`
}

type parityFile struct {
	Normalise string       `json:"normalise"`
	Cases     []parityCase `json:"cases"`
}

// normEnv sorts, replaces the crash dir with <tmp> and a value over 100 chars with its length and hash.
func normEnv(env []string) []string {
	out := []string{}
	for _, kv := range env {
		k, v, _ := strings.Cut(kv, "=")
		switch {
		case k == "BREAKPAD_DUMP_LOCATION":
			v = "<tmp>"
		case len([]rune(v)) > 100:
			v = fmt.Sprintf("<len:%d sha256:%x>", len([]rune(v)), sha256.Sum256([]byte(v)))
		}
		out = append(out, k+"="+v)
	}
	slices.Sort(out)
	return out
}

func (c parityCase) config() map[string]any {
	m := map[string]any{}
	for k, v := range c.Config {
		m[k] = v
	}
	if c.PadChars > 0 {
		m["pad"] = strings.Repeat("x", c.PadChars)
	}
	return m
}

func TestClientParity(t *testing.T) {
	raw, err := os.ReadFile(parityPath)
	if err != nil {
		t.Fatal(err)
	}
	var f parityFile
	if err := json.Unmarshal(raw, &f); err != nil {
		t.Fatal(err)
	}
	regen := os.Getenv("PARITY_REGEN") == "1"
	for i, c := range f.Cases {
		o := Options{Config: c.config(), Window: c.Window, DPR: c.DPR, UserDataDir: c.UserDataDir,
			FontsDir: c.FontsDir, Headless: &c.Headless,
			Strict: c.Strict, ExtraArgs: append(append([]string{}, c.ExtraArgs...), c.Args...)}
		if c.Window != [2]int{} { // core emits the position with a window
			o.Position = &c.Position
		}
		envMap, err := buildEnvFor(o, nil, c.HostOS)
		if (err != nil) != c.WantErr {
			t.Fatalf("%s: err %v, wantErr %v", c.Name, err, c.WantErr)
		}
		var env []string
		for k, v := range envMap {
			env = append(env, k+"="+v)
		}
		if err == nil {
			env = append(env, "BREAKPAD_DUMP_LOCATION=x") // Launch adds the crash dir after buildEnvFor
		}
		var argv []string
		for _, a := range BuildArgs(o) {
			if a != "--remote-debugging-pipe" {
				argv = append(argv, a)
			}
		}
		if regen {
			f.Cases[i].Env, f.Cases[i].Argv = normEnv(env), argv
			if err != nil {
				f.Cases[i].Env, f.Cases[i].Argv = nil, nil
			}
			continue
		}
		if err != nil {
			continue
		}
		if got := normEnv(env); !slices.Equal(got, c.Env) {
			t.Errorf("%s env:\n got %v\nwant %v", c.Name, got, c.Env)
		}
		if !slices.Equal(argv, c.Argv) {
			t.Errorf("%s argv:\n got %v\nwant %v", c.Name, argv, c.Argv)
		}
	}
	if regen {
		b, _ := json.MarshalIndent(f, "", " ")
		if err := os.WriteFile(parityPath, append(b, '\n'), 0o644); err != nil {
			t.Fatal(err)
		}
	}
}
