package core

import (
	"encoding/json"
	"fmt"
	"regexp"
)

var platformVersionRe = regexp.MustCompile(`^\d+\.\d+\.\d+$`)

// Resolve applies a Host and an Exit to an Identity. It ports the
// host-dependent tail of gen.py from_pool, and never claims a GPU or a
// geolocation. The random steps (window fit) draw from the identity's
// HostSeed, so the same identity on the same host and exit resolves the same
// way every launch.
func Resolve(id Identity, h Host, exit *Exit) (Resolved, error) {
	if id.Version != poolFormat {
		return Resolved{}, fmt.Errorf("identity has format %d, this code reads %d", id.Version, poolFormat)
	}
	if err := loadTables(); err != nil {
		return Resolved{}, err
	}
	cfg := map[string]any{}
	if err := json.Unmarshal(id.Entry, &cfg); err != nil {
		return Resolved{}, fmt.Errorf("identity entry: %w", err)
	}
	dpr, _ := cfg["dpr"].(float64)
	delete(cfg, "dpr")
	num := func(k string) int { v, _ := cfg[k].(float64); return int(v) }
	var warn []string

	// Seeds.
	for _, k := range []string{"canvas:seed", "mediaDevices:seed"} {
		if id.Seeds[k] == 0 {
			return Resolved{}, fmt.Errorf("identity has no %s", k)
		}
		cfg[k] = float64(id.Seeds[k])
	}

	// 1. cores (gen.py from_pool, host_cores).
	if h.Cores > 0 {
		cfg["navigator.hardwareConcurrency"] = float64(snapCores(num("navigator.hardwareConcurrency"), h.Cores))
	} else {
		warn = append(warn, "host cores unknown: the claim is kept, and may exceed the host's")
	}

	// 2. platform version (Windows claim).
	switch {
	case h.PlatformVersion == "":
		warn = append(warn, "host platform version unknown: the entry's value stays")
	case platformVersionRe.MatchString(h.PlatformVersion):
		cfg["ua:platformVersion"] = h.PlatformVersion
	default:
		warn = append(warn, fmt.Sprintf("host platform version %q is not N.N.N: ignored", h.PlatformVersion))
	}

	// 3. window.
	avail := [2]int{num("screen.availWidth"), num("screen.availHeight")}
	origin := [2]int{num("screen.availLeft"), num("screen.availTop")}
	pos := [2]int{num("window.screenX"), num("window.screenY")}
	outer := [2]int{num("window.outerWidth"), num("window.outerHeight")}
	if h.WorkArea[0] > 0 && h.WorkArea[1] > 0 {
		if !holdsMinWindow(h.WorkArea, dpr) {
			return Resolved{}, fmt.Errorf("work area %v cannot hold the minimum window %v at device pixel ratio %g", h.WorkArea, minWindow, dpr)
		}
		pos, outer = fitWindow(newRng(id.HostSeed, 0xD1B54A32D192ED03), h.WorkArea, dpr, avail, origin, pos, outer)
	} else {
		warn = append(warn, "host work area unknown: the window is not fitted to it")
	}
	lw, ow, err := snapWindow(dpr, outer[0])
	if err != nil {
		return Resolved{}, err
	}
	lh, oh, err := snapWindow(dpr, outer[1])
	if err != nil {
		return Resolved{}, err
	}
	cfg["window.screenX"], cfg["window.screenY"] = float64(pos[0]), float64(pos[1])
	cfg["window.outerWidth"], cfg["window.outerHeight"] = float64(ow), float64(oh)

	// 4. exit, else the entry's own locale and the default zone.
	tag, _ := cfg["locale:tag"].(string)
	if exit != nil {
		if err := validZone(exit.Timezone); err != nil {
			return Resolved{}, err
		}
		var w string
		if tag, w = localeFor(exit.Country); w != "" {
			warn = append(warn, w)
		}
		cfg["timezone:id"] = exit.Timezone
		cfg["locale:tag"], cfg["navigator.language"], cfg["navigator.languages"] = tag, tag, languagesFor(tag)
		cfg["webrtc:ipHandlingPolicy"] = "disable_non_proxied_udp"
	} else {
		zs := tables.zones[tag]
		if len(zs) == 0 {
			return Resolved{}, fmt.Errorf("no default zone for locale %q: pass an Exit", tag)
		}
		cfg["timezone:id"] = zs[0]
	}

	// 5. voices follow the locale.
	voices, err := voiceList(tag)
	if err != nil {
		return Resolved{}, err
	}
	cfg["voices:list"] = voices

	// 6. display.
	var args []string
	if h.Display != nil && !validDisplay(h.Display) {
		warn = append(warn, "host display is malformed: ignored") // gen.py: no flags, no "unknown" note
	} else {
		var dw string
		if args, dw = displayFlags(h.Display); dw != "" {
			warn = append(warn, dw)
		}
	}

	return Resolved{Config: cfg, Window: [2]int{lw, lh}, DPR: dpr, Position: pos, Args: args, Warnings: warn,
		Cores: num("navigator.hardwareConcurrency")}, nil
}
