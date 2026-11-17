package core

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
)

type parityCase struct {
	Name        string         `json:"name"`
	HostOS      string         `json:"hostOS"`
	FontsDir    string         `json:"fontsDir"`
	Config      map[string]any `json:"config"`
	PadChars    int            `json:"padChars"`
	Window      [2]int         `json:"window"`
	DPR         float64        `json:"dpr"`
	Position    [2]int         `json:"position"`
	Headless    bool           `json:"headless"`
	Strict      bool           `json:"strict"`
	UserDataDir string         `json:"userDataDir"`
	ExtraArgs   []string       `json:"extraArgs"`
	Args        []string       `json:"args"`
	WantErr     bool           `json:"wantErr"`
	Env         []string       `json:"env"`
	Argv        []string       `json:"argv"`
}

// normEnv is the fixture's normalise rule (see parity.json).
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

func TestEnvArgvParity(t *testing.T) {
	raw, err := os.ReadFile("testdata/parity.json")
	if err != nil {
		t.Fatal(err)
	}
	var f struct{ Cases []parityCase }
	if err := json.Unmarshal(raw, &f); err != nil {
		t.Fatal(err)
	}
	if len(f.Cases) != 4 {
		t.Fatalf("fixture has %d cases, want 4", len(f.Cases))
	}
	for _, c := range f.Cases {
		cfg := c.Config
		if c.PadChars > 0 {
			cfg["pad"] = strings.Repeat("x", c.PadChars)
		}
		r := Resolved{Config: cfg, Window: c.Window, DPR: c.DPR, Position: c.Position, Args: c.Args}
		o := LaunchOpts{UserDataDir: c.UserDataDir, Headless: c.Headless, FontsDir: c.FontsDir, Strict: c.Strict, ExtraArgs: c.ExtraArgs}
		env, cleanup, err := envFor(r, o, nil, c.HostOS)
		if (err != nil) != c.WantErr {
			t.Fatalf("%s: err %v, wantErr %v", c.Name, err, c.WantErr)
		}
		if err != nil {
			continue
		}
		cleanup()
		if got := normEnv(env); !slices.Equal(got, c.Env) {
			t.Errorf("%s env:\n got %v\nwant %v", c.Name, got, c.Env)
		}
		if got := Argv(r, o); !slices.Equal(got, c.Argv) {
			t.Errorf("%s argv:\n got %v\nwant %v", c.Name, got, c.Argv)
		}
	}
}

func TestEnvDropsInherited(t *testing.T) {
	r := Resolved{Config: map[string]any{"ua:platform": "Linux"}}
	base := []string{"PATH=/bin", "FONTCONFIG_FILE=/x", "BREAKPAD_DUMP_LOCATION=/y", "CAMOU_CONFIG=old", "CAMOU_CONFIG_7=stale", "CAMOU_PRESET=p"}
	env, cleanup, err := envFor(r, LaunchOpts{}, base, "Linux")
	if err != nil {
		t.Fatal(err)
	}
	defer cleanup()
	for _, kv := range env {
		for _, bad := range []string{"FONTCONFIG_FILE=/x", "BREAKPAD_DUMP_LOCATION=/y", "CAMOU_CONFIG=old", "CAMOU_CONFIG_7", "CAMOU_PRESET"} {
			if strings.HasPrefix(kv, bad) {
				t.Errorf("inherited %q survived", kv)
			}
		}
	}
	if !slices.Contains(env, "PATH=/bin") || !slices.Contains(env, `CAMOU_CONFIG={"ua:platform":"Linux"}`) {
		t.Errorf("env lost PATH or the config: %v", env)
	}
	var crash string
	for _, kv := range env {
		if v, ok := strings.CutPrefix(kv, "BREAKPAD_DUMP_LOCATION="); ok {
			crash = v
		}
	}
	if st, err := os.Stat(crash); err != nil || !st.IsDir() {
		t.Fatalf("no crash dir %q: %v", crash, err)
	}
	cleanup()
	if _, err := os.Stat(crash); !os.IsNotExist(err) {
		t.Errorf("cleanup left %s", crash)
	}
}

func TestEnvStrict(t *testing.T) {
	r := Resolved{Config: map[string]any{"ua:platform": "Linux"}}
	for _, strict := range []bool{false, true} {
		env, cleanup, err := envFor(r, LaunchOpts{Strict: strict}, []string{"CAMOU_CONFIG_STRICT=1"}, "Linux")
		if err != nil {
			t.Fatal(err)
		}
		cleanup()
		if got := slices.Contains(env, "CAMOU_CONFIG_STRICT=1"); got != strict {
			t.Errorf("Strict=%v: CAMOU_CONFIG_STRICT present = %v", strict, got)
		}
	}
}

func TestEnvChunks(t *testing.T) {
	cfg := map[string]any{"ua:platform": "Linux", "pad": ""}
	base, _ := json.Marshal(cfg)
	cfg["pad"] = strings.Repeat("é", 70001-len([]rune(string(base)))) // multi-byte: chunks count characters
	want, _ := json.Marshal(cfg)
	if n := len([]rune(string(want))); n != 70001 {
		t.Fatalf("setup: %d chars", n)
	}
	env, cleanup, err := envFor(Resolved{Config: cfg}, LaunchOpts{}, nil, "Linux")
	if err != nil {
		t.Fatal(err)
	}
	defer cleanup()
	var got []string
	for _, kv := range env {
		k, v, _ := strings.Cut(kv, "=")
		if k == "CAMOU_CONFIG" {
			t.Fatal("CAMOU_CONFIG set beside chunks")
		}
		if strings.HasPrefix(k, "CAMOU_CONFIG_") {
			got = append(got, v)
		}
	}
	if len(got) != 3 {
		t.Fatalf("%d chunks, want 3", len(got))
	}
	for i, k := range []string{"CAMOU_CONFIG_1", "CAMOU_CONFIG_2", "CAMOU_CONFIG_3"} {
		if !slices.ContainsFunc(env, func(s string) bool { return strings.HasPrefix(s, k+"=") }) {
			t.Errorf("missing %s (%d)", k, i)
		}
	}
	if strings.Join(got, "") != string(want) {
		t.Error("chunks do not concatenate to the config")
	}
}

func TestEnvFontconfigWithFontsDir(t *testing.T) {
	root := t.TempDir()
	os.MkdirAll(filepath.Join(root, "fonts"), 0o755)
	r := Resolved{Config: map[string]any{"ua:platform": "Windows", "ua:osInfo": "Windows NT 10.0; Win64; x64"}}
	if _, _, err := envFor(r, LaunchOpts{FontsDir: filepath.Join(root, "fonts")}, nil, "Linux"); err == nil {
		t.Fatal("a fonts dir without the fontconfig was accepted")
	}
	os.MkdirAll(filepath.Join(root, "settings", "fontconfig"), 0o755)
	conf := filepath.Join(root, "settings", "fontconfig", "windows.conf")
	os.WriteFile(conf, []byte("<fontconfig/>"), 0o644)
	env, cleanup, err := envFor(r, LaunchOpts{FontsDir: filepath.Join(root, "fonts")}, nil, "Linux")
	if err != nil {
		t.Fatal(err)
	}
	defer cleanup()
	if !slices.Contains(env, "FONTCONFIG_FILE="+conf) {
		t.Errorf("no FONTCONFIG_FILE=%s in %v", conf, env)
	}
}

// The embedded copy must be the contract itself (scripts/gen_go_core_data.py regenerates it).
func TestEmbeddedLauncherIsTheContract(t *testing.T) {
	want, err := os.ReadFile("../../../settings/launcher.json")
	if err != nil {
		t.Skip("not inside the repo")
	}
	if !bytes.Equal(want, launcherJSON) {
		t.Error("data/launcher.json differs from settings/launcher.json")
	}
}

func TestArgvOrderAndNoTransport(t *testing.T) {
	r := Resolved{Config: map[string]any{"locale:tag": "de-DE"}, Window: [2]int{1000, 700}, DPR: 1.5, Position: [2]int{3, 4}, Args: []string{"--a"}}
	got := Argv(r, LaunchOpts{Headless: true, UserDataDir: "/u", ExtraArgs: []string{"--z"}})
	want := []string{"--no-first-run", "--no-default-browser-check", "--headless=new", "--user-data-dir=/u",
		"--window-size=1000,700", "--window-position=3,4", "--force-device-scale-factor=1.5", "--accept-lang=de-DE", "--z", "--a"}
	if !slices.Equal(got, want) {
		t.Errorf("got %v", got)
	}
	for _, a := range got {
		if strings.HasPrefix(a, "--remote-debugging") || strings.HasPrefix(a, "--proxy") {
			t.Errorf("spawner-owned flag %s", a)
		}
	}
}
