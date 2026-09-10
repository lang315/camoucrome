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
	Headless       *bool // nil = headless
	ExtraArgs      []string
}

func asJSON(v any) (string, error) {
	if s, ok := v.(string); ok {
		return s, nil
	}
	b, err := json.Marshal(v)
	return string(b), err
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
		env["CAMOU_CONFIG"] = s
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
	return append(args, o.ExtraArgs...)
}

// Launch starts a persistent context (one profile per identity).
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
