// Package camoucrome launches the Camoucrome browser with a fingerprint.
//
//	pw, _ := playwright.Run(&playwright.RunOptions{DriverDirectory: driverDir, SkipInstallBrowsers: true})
//	ctx, err := camoucrome.Launch(pw, camoucrome.Options{ExecutablePath: exe, Config: cfg, Window: [2]int{1920, 1040}})
//
// Everything anti-detect lives in the browser and in the driver: point
// playwright-go's DriverDirectory at patchright-core (see
// settings/launcher.json "driver.go") and the Node driver never sends
// Runtime.enable. This package only carries the configuration into the
// process. There is deliberately no field for locale, timezone, user agent,
// viewport, screen, device scale factor, geolocation or color scheme: each
// duplicates a CAMOU_CONFIG key, and a second emulation of the same surface
// fights the fork's value.
package camoucrome

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/mxschmitt/playwright-go"
)

// BaseArgs mirrors settings/launcher.json "launch.base_args".
var BaseArgs = []string{"--no-first-run", "--no-default-browser-check"}

// Options for Launch. Config and Preset are JSON objects (or raw JSON
// strings) carried as CAMOU_CONFIG / CAMOU_PRESET; an explicit config key
// wins over the preset inside the browser.
type Options struct {
	ExecutablePath string
	Config         any
	Preset         any
	Strict         bool
	UserDataDir    string // one profile per identity; a temp dir when empty
	Window         [2]int // --window-size, so inner/outer widths cohere with screen.*
	DPR            float64
	Headless       *bool    // nil = headless
	Extensions     []string // unpacked extension dirs (--load-extension)
	SPKIList       []string // base64 SHA-256 SPKI hashes whose cert errors are ignored (a MITM CA)
	ExtraArgs      []string
	FontsDir       string // the bundled font dir; default "fonts" beside the executable when present
}

// FontconfigFiles mirrors settings/launcher.json launch.fontconfig.files:
// the generated fontconfig of the claimed OS, relative to the fonts dir's parent.
var FontconfigFiles = map[string]string{
	"Windows": "settings/fontconfig/windows.conf",
	"macOS":   "settings/fontconfig/macos.conf",
}

func claimedOS(o Options) string {
	for _, v := range []any{o.Config, o.Preset} {
		if v == nil {
			continue
		}
		s, err := asJSON(v)
		if err != nil {
			continue
		}
		var m map[string]any
		if json.Unmarshal([]byte(s), &m) != nil {
			continue
		}
		for _, k := range []string{"ua:platform", "os"} {
			if p, ok := m[k].(string); ok && p != "" {
				return p
			}
		}
	}
	return ""
}

// FontconfigFor is the FONTCONFIG_FILE for the claimed OS (contract
// launch.fontconfig): the conf beside the bundled fonts dir, which lives
// beside the executable in an archive. Linux claim or no fonts dir: "".
func FontconfigFor(o Options) string {
	file, ok := FontconfigFiles[claimedOS(o)]
	if !ok {
		return ""
	}
	dir := o.FontsDir
	if dir == "" && o.ExecutablePath != "" {
		cand := filepath.Join(filepath.Dir(o.ExecutablePath), "fonts")
		if st, err := os.Stat(cand); err == nil && st.IsDir() {
			dir = cand
		}
	}
	if dir == "" {
		return ""
	}
	abs, err := filepath.Abs(filepath.Join(dir, "..", file))
	if err != nil {
		return ""
	}
	return abs
}

// AcceptLangOf is the --accept-lang value the config implies:
// navigator.languages joined, else locale:tag, else "". Measured
// 2026-09-10: without the flag a French config still sends
// Accept-Language: en-US,en;q=0.9; with it Chrome sends fr-FR,fr;q=0.9.
func AcceptLangOf(config any) string {
	if config == nil {
		return ""
	}
	var m map[string]any
	switch c := config.(type) {
	case string:
		if json.Unmarshal([]byte(c), &m) != nil {
			return ""
		}
	default:
		b, err := json.Marshal(c)
		if err != nil || json.Unmarshal(b, &m) != nil {
			return ""
		}
	}
	if langs, ok := m["navigator.languages"].([]any); ok && len(langs) > 0 {
		parts := make([]string, 0, len(langs))
		for _, l := range langs {
			if s, ok := l.(string); ok {
				parts = append(parts, s)
			}
		}
		return strings.Join(parts, ",")
	}
	if tag, ok := m["locale:tag"].(string); ok {
		return tag
	}
	return ""
}

func asJSON(v any) (string, error) {
	if s, ok := v.(string); ok {
		return s, nil
	}
	b, err := json.Marshal(v)
	return string(b), err
}

// configChunkRunes: Linux caps one environment string at 128 KiB; a macOS
// identity (191 voices, 409 faces) is ~140 KB, so a large config goes out as
// CAMOU_CONFIG_1..N in order (the reader concatenates).
const configChunkRunes = 30000

func configEnv(raw string) map[string]string {
	r := []rune(raw)
	if len(r) <= configChunkRunes {
		return map[string]string{"CAMOU_CONFIG": raw}
	}
	out := map[string]string{}
	for n, i := 1, 0; i < len(r); n, i = n+1, i+configChunkRunes {
		j := i + configChunkRunes
		if j > len(r) {
			j = len(r)
		}
		out[fmt.Sprintf("CAMOU_CONFIG_%d", n)] = string(r[i:j])
	}
	return out
}

// BuildEnv is the child environment: every CAMOU_* of the parent dropped
// (a stale CAMOU_CONFIG_1 would otherwise win), then config/preset set.
func BuildEnv(o Options, base []string) (map[string]string, error) {
	env := map[string]string{}
	for _, kv := range base {
		k, v, _ := strings.Cut(kv, "=")
		if !strings.HasPrefix(k, "CAMOU_") {
			env[k] = v
		}
	}
	if o.Config != nil {
		s, err := asJSON(o.Config)
		if err != nil {
			return nil, err
		}
		for k, c := range configEnv(s) {
			env[k] = c
		}
	}
	if o.Preset != nil {
		s, err := asJSON(o.Preset)
		if err != nil {
			return nil, err
		}
		env["CAMOU_PRESET"] = s
	}
	if o.Strict {
		env["CAMOU_CONFIG_STRICT"] = "1"
	}
	if fc := FontconfigFor(o); fc != "" {
		env["FONTCONFIG_FILE"] = fc
	}
	return env, nil
}

// BuildArgs are the flags the C++ deliberately left to the launcher, plus
// the two Playwright defaults that IgnoreAllDefaultArgs also drops (the
// debugging pipe, without which the driver waits forever on
// Browser.getVersion, and the profile dir, without which Chrome runs
// --incognito in a scoped dir; measured 2026-09-10) -- and
// the whole argv besides the debugging pipe and the profile dir: Launch
// ignores Playwright's default args, which carry --disable-features=<18
// features>, --blink-settings=primaryHoverType=..., --hide-scrollbars,
// --mute-audio, --force-color-profile=srgb and more, each moving a
// page-visible surface off the compiled defaults (settings/launcher.json).
func BuildArgs(o Options) []string {
	args := append([]string{}, BaseArgs...)
	if o.Headless == nil || *o.Headless {
		args = append(args, "--headless=new")
	}
	args = append(args, "--remote-debugging-pipe")
	if o.UserDataDir != "" {
		args = append(args, "--user-data-dir="+o.UserDataDir)
	}
	if o.Window != [2]int{} {
		args = append(args, fmt.Sprintf("--window-size=%d,%d", o.Window[0], o.Window[1]))
	}
	if o.DPR != 0 {
		args = append(args, fmt.Sprintf("--force-device-scale-factor=%g", o.DPR))
	}
	if al := AcceptLangOf(o.Config); al != "" {
		args = append(args, "--accept-lang="+al)
	}
	if len(o.Extensions) > 0 {
		paths := strings.Join(o.Extensions, ",")
		args = append(args, "--disable-extensions-except="+paths, "--load-extension="+paths)
	}
	if len(o.SPKIList) > 0 {
		args = append(args, "--ignore-certificate-errors-spki-list="+strings.Join(o.SPKIList, ","))
	}
	return append(args, o.ExtraArgs...)
}

// Launch starts a persistent context (one profile per identity). Never
// AddInitScript anything a page could enumerate: the driver runs a user's
// init script in the MAIN world (measured 2026-09-10); Evaluate runs in an
// isolated world, use that.
func Launch(pw *playwright.Playwright, o Options) (playwright.BrowserContext, error) {
	env, err := BuildEnv(o, os.Environ())
	if err != nil {
		return nil, err
	}
	if o.UserDataDir == "" {
		if o.UserDataDir, err = os.MkdirTemp("", "camoucrome-"); err != nil {
			return nil, err
		}
	}
	dir := o.UserDataDir
	headless := true
	if o.Headless != nil {
		headless = *o.Headless
	}
	return pw.Chromium.LaunchPersistentContext(dir, playwright.BrowserTypeLaunchPersistentContextOptions{
		ExecutablePath:       playwright.String(o.ExecutablePath),
		Headless:             playwright.Bool(headless),
		IgnoreAllDefaultArgs: playwright.Bool(true),
		Env:                  env,
		Args:                 BuildArgs(o),
		// Otherwise a 1280x720 viewport is emulated through
		// Emulation.setDeviceMetricsOverride, fighting screen.* and --window-size.
		NoViewport: playwright.Bool(true),
	})
}
