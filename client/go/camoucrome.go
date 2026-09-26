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
// viewport, screen, device scale factor, geolocation, color scheme, touch or
// mobile emulation: each
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

// osInfoMarkers mirrors derive.cc kForms: (ua:osInfo marker, UA-CH
// platform) in its match order -- Android and CrOS before Linux, whose marker
// their osInfo also contains.
var osInfoMarkers = [][2]string{{"Android", "Android"}, {"CrOS", "Chrome OS"},
	{"Windows NT", "Windows"}, {"Macintosh", "macOS"}, {"Linux", "Linux"}}

// asObject parses a config or preset (a JSON string or any marshalable value)
// as a JSON object; nil and a typed nil are the empty object.
func asObject(v any) (map[string]any, error) {
	m := map[string]any{}
	if v == nil {
		return m, nil
	}
	s, err := asJSON(v)
	if err != nil {
		return nil, err
	}
	if s == "null" {
		return m, nil
	}
	if err := json.Unmarshal([]byte(s), &m); err != nil {
		return nil, fmt.Errorf("config and preset must be JSON objects: %w", err)
	}
	return m, nil
}

// effectiveKeys are the keys the browser ends up with for what the launcher
// reads: the preset's os and locale expanded as preset_loader.cc does, under
// the explicit config (explicit wins). A shape the browser would ignore is an
// error rather than a silently dropped value.
func effectiveKeys(config, preset any) (map[string]any, error) {
	p, err := asObject(preset)
	if err != nil {
		return nil, err
	}
	c, err := asObject(config)
	if err != nil {
		return nil, err
	}
	out := map[string]any{}
	setOS := func(name string) bool {
		for _, f := range osInfoMarkers {
			if f[1] == name {
				out["ua:osInfo"], out["ua:platform"] = f[0], name
				return true
			}
		}
		return false
	}
	setLocale := func(loc string) {
		langs := []any{loc}
		if primary, _, _ := strings.Cut(loc, "-"); primary != loc {
			langs = append(langs, primary)
		}
		out["locale:tag"], out["navigator.language"], out["navigator.languages"] = loc, loc, langs
	}
	if name, ok := p["os"].(string); ok {
		setOS(name)
	}
	if loc, ok := p["locale"].(string); ok {
		setLocale(loc)
	}
	// preset_loader.cc OverridePresetGroups: an explicit member of the
	// preset's OS pair or locale triple re-derives the whole group from it.
	if _, fromPreset := out["ua:osInfo"]; fromPreset {
		fam := ""
		if info, ok := c["ua:osInfo"].(string); ok {
			for _, f := range osInfoMarkers {
				if strings.Contains(info, f[0]) {
					fam = f[1]
					break
				}
			}
		}
		if plat, ok := c["ua:platform"].(string); ok && fam == "" {
			fam = plat
		}
		setOS(fam) // an unrecognised name leaves the preset's pair
	}
	if _, fromPreset := out["locale:tag"]; fromPreset {
		head := ""
		if l, ok := c["navigator.languages"].([]any); ok && len(l) > 0 {
			head, _ = l[0].(string)
		}
		for _, k := range []string{"navigator.language", "locale:tag"} {
			if v, ok := c[k].(string); ok && head == "" {
				head = v
			}
		}
		if head != "" {
			setLocale(head)
		}
	}
	for k, v := range c {
		out[k] = v
	}
	if l, ok := out["navigator.languages"]; ok {
		list, ok := l.([]any)
		for _, s := range list {
			if _, isStr := s.(string); !isStr {
				ok = false
			}
		}
		if !ok {
			return nil, fmt.Errorf("navigator.languages must be a list of strings, got %v", l)
		}
	}
	return out, nil
}

// claimedOS is derive.cc ClaimedOs over the effective keys: a recognised
// ua:osInfo, else ua:platform, else "".
func claimedOS(o Options) string {
	m, err := effectiveKeys(o.Config, o.Preset)
	if err != nil {
		return ""
	}
	if info, ok := m["ua:osInfo"].(string); ok {
		for _, f := range osInfoMarkers {
			if strings.Contains(info, f[0]) {
				return f[1]
			}
		}
	}
	p, _ := m["ua:platform"].(string)
	return p
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
// navigator.languages joined, else locale:tag, else "" -- over the effective
// keys, so a preset's locale counts. Measured 2026-09-10: without the flag a
// French config still sends Accept-Language: en-US,en;q=0.9; with it Chrome
// sends fr-FR,fr;q=0.9. A malformed config gives "" (BuildEnv rejects it).
func AcceptLangOf(config, preset any) string {
	m, err := effectiveKeys(config, preset)
	if err != nil {
		return ""
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
// identity (191 voices, 409 faces) is ~140 KB, so a large config (or preset)
// goes out as CAMOU_CONFIG_1..N in order (the reader concatenates).
const configChunkRunes = 30000

func configEnv(raw, name string) map[string]string {
	r := []rune(raw)
	if len(r) <= configChunkRunes {
		return map[string]string{name: raw}
	}
	out := map[string]string{}
	for n, i := 1, 0; i < len(r); n, i = n+1, i+configChunkRunes {
		j := i + configChunkRunes
		if j > len(r) {
			j = len(r)
		}
		out[fmt.Sprintf("%s_%d", name, n)] = string(r[i:j])
	}
	return out
}

// BuildEnv is the child environment: every CAMOU_* of the parent dropped
// (a stale CAMOU_CONFIG_1 would otherwise win) and its FONTCONFIG_FILE (a
// host conf under a Windows claim is a tell), then config/preset set.
func BuildEnv(o Options, base []string) (map[string]string, error) {
	if _, err := effectiveKeys(o.Config, o.Preset); err != nil {
		return nil, err
	}
	env := map[string]string{}
	for _, kv := range base {
		k, v, _ := strings.Cut(kv, "=")
		if !strings.HasPrefix(k, "CAMOU_") && k != "FONTCONFIG_FILE" {
			env[k] = v
		}
	}
	for name, v := range map[string]any{"CAMOU_CONFIG": o.Config, "CAMOU_PRESET": o.Preset} {
		if v == nil {
			continue
		}
		s, err := asJSON(v)
		if err != nil {
			return nil, err
		}
		if s == "null" { // a typed nil map or pointer
			continue
		}
		for k, c := range configEnv(s, name) {
			env[k] = c
		}
	}
	if o.Strict {
		env["CAMOU_CONFIG_STRICT"] = "1"
	}
	if fc := FontconfigFor(o); fc != "" {
		if _, err := os.Stat(fc); err != nil {
			return nil, fmt.Errorf("the fonts dir has no fontconfig for the claimed OS: %w", err)
		}
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
	if al := AcceptLangOf(o.Config, o.Preset); al != "" {
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
// isolated world, use that. A temp profile (no UserDataDir) is removed when
// the context closes or the launch fails.
func Launch(pw *playwright.Playwright, o Options) (playwright.BrowserContext, error) {
	env, err := BuildEnv(o, os.Environ())
	if err != nil {
		return nil, err
	}
	temp := o.UserDataDir == ""
	if temp {
		if o.UserDataDir, err = os.MkdirTemp("", "camoucrome-"); err != nil {
			return nil, err
		}
	}
	dir := o.UserDataDir
	headless := true
	if o.Headless != nil {
		headless = *o.Headless
	}
	ctx, err := pw.Chromium.LaunchPersistentContext(dir, playwright.BrowserTypeLaunchPersistentContextOptions{
		ExecutablePath:       playwright.String(o.ExecutablePath),
		Headless:             playwright.Bool(headless),
		IgnoreAllDefaultArgs: playwright.Bool(true),
		Env:                  env,
		Args:                 BuildArgs(o),
		// Otherwise a 1280x720 viewport is emulated through
		// Emulation.setDeviceMetricsOverride, fighting screen.* and --window-size.
		NoViewport: playwright.Bool(true),
	})
	if temp {
		if err != nil {
			os.RemoveAll(dir)
		} else {
			ctx.OnClose(func(playwright.BrowserContext) { os.RemoveAll(dir) })
		}
	}
	return ctx, err
}
