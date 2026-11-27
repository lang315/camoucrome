package core

import (
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

//go:embed data/launcher.json
var launcherJSON []byte

// contract is the part of settings/launcher.json (copied by
// scripts/gen_go_core_data.py) that Env and Argv read.
var contract struct {
	Launch struct {
		BaseArgs []string `json:"base_args"`
		Env      struct {
			Config     string `json:"config"`
			ChunkChars int    `json:"config_chunk_chars"`
			Strict     string `json:"strict"`
		} `json:"env"`
		CrashDumps struct {
			Env string `json:"env"`
		} `json:"crash_dumps"`
		Fontconfig struct {
			Env   string            `json:"env"`
			Files map[string]string `json:"files"`
		} `json:"fontconfig"`
		NativeFonts struct {
			Drop []string `json:"drop"`
		} `json:"native_fonts"`
		ConfigDefaults struct {
			Keys map[string]any `json:"keys"`
		} `json:"config_defaults"`
	} `json:"launch"`
}

func init() {
	if err := json.Unmarshal(launcherJSON, &contract); err != nil {
		panic("core: embedded launcher.json: " + err.Error())
	}
}

// osInfoMarkers mirrors derive.cc kForms: (ua:osInfo marker, UA-CH platform)
// in match order; Android and CrOS before Linux, whose marker their osInfo contains.
var osInfoMarkers = [][2]string{{"Android", "Android"}, {"CrOS", "Chrome OS"},
	{"Windows NT", "Windows"}, {"Macintosh", "macOS"}, {"Linux", "Linux"}}

var hostOS = map[string]string{"windows": "Windows", "darwin": "macOS", "linux": "Linux"}[runtime.GOOS]

// claimedOS is derive.cc ClaimedOs: a recognised ua:osInfo, else ua:platform, else "".
func claimedOS(cfg map[string]any) string {
	if info, ok := cfg["ua:osInfo"].(string); ok {
		for _, f := range osInfoMarkers {
			if strings.Contains(info, f[0]) {
				return f[1]
			}
		}
	}
	p, _ := cfg["ua:platform"].(string)
	return p
}

// acceptLang is the --accept-lang value: navigator.languages joined, else locale:tag.
func acceptLang(cfg map[string]any) string {
	if langs, ok := cfg["navigator.languages"].([]any); ok && len(langs) > 0 {
		parts := make([]string, 0, len(langs))
		for _, l := range langs {
			if s, ok := l.(string); ok {
				parts = append(parts, s)
			}
		}
		return strings.Join(parts, ",")
	}
	if ls, ok := cfg["navigator.languages"].([]string); ok && len(ls) > 0 {
		return strings.Join(ls, ",")
	}
	tag, _ := cfg["locale:tag"].(string)
	return tag
}

// Env is the child environment: base without CAMOU_*, FONTCONFIG_FILE and
// BREAKPAD_DUMP_LOCATION, plus the config (chunked past config_chunk_chars)
// after the native-fonts drop, a fresh crash-dump dir and the fontconfig for
// the claimed OS. cleanup removes the dump dir.
func Env(r Resolved, o LaunchOpts, base []string) (env []string, cleanup func(), err error) {
	return envFor(r, o, base, hostOS)
}

func envFor(r Resolved, o LaunchOpts, base []string, host string) ([]string, func(), error) {
	noop := func() {}
	if o.Strict && o.Lax {
		return nil, noop, errors.New("Strict and Lax contradict each other: strict is the default, drop Strict")
	}
	if err := CheckArchive(o.ExecutablePath, r.Config); err != nil {
		return nil, noop, err
	}
	claimed := claimedOS(r.Config)
	// A copy, so the caller's map is never touched: the contract's config_defaults go under it (the caller's value wins).
	cfg := make(map[string]any, len(r.Config)+len(contract.Launch.ConfigDefaults.Keys))
	for k, v := range contract.Launch.ConfigDefaults.Keys {
		cfg[k] = v
	}
	for k, v := range r.Config {
		cfg[k] = v
	}
	if host != "" && claimed == host {
		// Those families are real on this host; an alias to the uninstalled bundle would hide them.
		for _, k := range contract.Launch.NativeFonts.Drop {
			delete(cfg, k)
		}
	}
	raw, err := json.Marshal(cfg)
	if err != nil {
		return nil, noop, err
	}
	var fc string
	if file, ok := contract.Launch.Fontconfig.Files[claimed]; ok {
		if o.FontsDir != "" {
			if fc, err = filepath.Abs(filepath.Join(o.FontsDir, "..", file)); err != nil {
				return nil, noop, err
			}
			if _, err := os.Stat(fc); err != nil {
				return nil, noop, fmt.Errorf("the fonts dir has no fontconfig for the claimed OS: %w", err)
			}
		} else if host == "Linux" {
			return nil, noop, fmt.Errorf("%s claim on a Linux host needs the bundled fonts dir (LaunchOpts.FontsDir), but none was given", claimed)
		}
	}
	sweep(o.UserDataDir) // a killed client's leftovers; never the caller's profile
	// Named for this process so sweep() can tell a live client's dir; 0700.
	crash, err := os.MkdirTemp("", fmt.Sprintf("camoucrome-crash-%d-", os.Getpid()))
	if err != nil {
		return nil, noop, err
	}
	env := make([]string, 0, len(base)+6)
	for _, kv := range base {
		k, _, _ := strings.Cut(kv, "=")
		if !strings.HasPrefix(k, "CAMOU_") && k != contract.Launch.Fontconfig.Env && k != contract.Launch.CrashDumps.Env {
			env = append(env, kv)
		}
	}
	name := contract.Launch.Env.Config
	if rs := []rune(string(raw)); len(rs) <= contract.Launch.Env.ChunkChars {
		env = append(env, name+"="+string(raw))
	} else {
		n := contract.Launch.Env.ChunkChars
		for i, c := 0, 1; i < len(rs); i, c = i+n, c+1 {
			env = append(env, fmt.Sprintf("%s_%d=%s", name, c, string(rs[i:min(i+n, len(rs))])))
		}
	}
	if !o.Lax {
		env = append(env, contract.Launch.Env.Strict+"=1")
	}
	env = append(env, contract.Launch.CrashDumps.Env+"="+crash)
	if fc != "" {
		env = append(env, contract.Launch.Fontconfig.Env+"="+fc)
	}
	return env, func() { os.RemoveAll(crash) }, nil
}

// Argv is the browser argv: base_args, --headless=new, --user-data-dir, the
// window flags, --accept-lang, ExtraArgs, then r.Args last. No transport and
// no proxy flags: the spawner owns those. The position flag goes with a
// non-zero Window, since a zero Position is a valid point.
func Argv(r Resolved, o LaunchOpts) []string {
	args := append([]string{}, contract.Launch.BaseArgs...)
	if o.Headless {
		args = append(args, "--headless=new")
	}
	if o.UserDataDir != "" {
		args = append(args, "--user-data-dir="+o.UserDataDir)
	}
	if r.Window != [2]int{} {
		args = append(args, fmt.Sprintf("--window-size=%d,%d", r.Window[0], r.Window[1]),
			fmt.Sprintf("--window-position=%d,%d", r.Position[0], r.Position[1]))
	}
	if r.DPR != 0 {
		args = append(args, fmt.Sprintf("--force-device-scale-factor=%g", r.DPR))
	}
	if al := acceptLang(r.Config); al != "" {
		args = append(args, "--accept-lang="+al)
	}
	// ExtraArgs, then the generator's launch.args: they go last (launcher.json extra_args_last)
	args = append(args, o.ExtraArgs...)
	return append(args, r.Args...)
}
