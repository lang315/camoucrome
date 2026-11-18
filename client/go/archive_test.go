package camoucrome

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCheckArchiveRoot(t *testing.T) {
	old := `{"version":"157.0.8103.51"}`
	cur := `{"version":"157.0.8103.51","config_keys":["ua:platform","webGpu:blocked"]}`
	cases := []struct {
		name, stamp string
		cfg         map[string]any
		want        string // error substring; "" = ok
	}{
		{"old stamp + webGpu:blocked (RED)", old, map[string]any{"webGpu:blocked": true}, "webGpu:blocked"},
		{"old stamp, other key", old, map[string]any{"ua:platform": "x", "future:key": 1}, ""},
		{"new stamp + known keys", cur, map[string]any{"webGpu:blocked": true, "ua:platform": "x"}, ""},
		{"new stamp + unknown key", cur, map[string]any{"ua:platform": "x", "zz:new": 1, "aa:new": 2}, "aa:new, zz:new"},
		{"no stamp + webGpu:blocked", "", map[string]any{"webGpu:blocked": true, "zz:new": 1}, ""},
		{"no stamp, no key", "", map[string]any{}, ""},
		{"old stamp, no key", old, nil, ""},
	}
	for _, c := range cases {
		dir := t.TempDir()
		if c.stamp != "" {
			if err := os.WriteFile(filepath.Join(dir, "camoucrome-release.json"), []byte(c.stamp), 0o644); err != nil {
				t.Fatal(err)
			}
		}
		err := checkArchive(filepath.Join(dir, "chrome"), c.cfg)
		if c.want == "" && err != nil || c.want != "" && (err == nil || !strings.Contains(err.Error(), c.want)) {
			t.Errorf("%s: err = %v, want %q", c.name, err, c.want)
		}
		// Env refuses the same way once the path is given, and skips the check without it.
		_, eerr := buildEnvFor(Options{Config: c.cfg, ExecutablePath: filepath.Join(dir, "chrome")}, nil, "Linux")
		if (eerr != nil) != (c.want != "") {
			t.Errorf("%s: envFor err = %v", c.name, eerr)
		}
	}
	_, err := buildEnvFor(Options{Config: map[string]any{"webGpu:blocked": true}}, nil, "Linux")
	if err == nil || !strings.Contains(err.Error(), "set Options.ExecutablePath") {
		t.Errorf("empty ExecutablePath + webGpu:blocked must error: %v", err)
	}
	if _, err := buildEnvFor(Options{Config: map[string]any{"ua:platform": "x"}}, nil, "Linux"); err != nil {
		t.Errorf("empty ExecutablePath without new keys stays allowed: %v", err)
	}
}

func TestCheckArchiveFollowsASymlinkedExe(t *testing.T) {
	arch, link := t.TempDir(), t.TempDir()
	if err := os.WriteFile(filepath.Join(arch, "camoucrome-release.json"), []byte(`{"version":"v"}`), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(arch, "chrome"), nil, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(arch, "chrome"), filepath.Join(link, "chrome")); err != nil {
		t.Skip(err)
	}
	if err := checkArchive(filepath.Join(link, "chrome"), map[string]any{"webGpu:blocked": true}); err == nil {
		t.Error("stamp beside the symlink target was not read")
	}
}
