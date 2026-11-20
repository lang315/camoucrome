package core

import (
	"encoding/json"
	"fmt"
	"regexp"
	"strconv"
	"strings"
)

var platformVersionRe = regexp.MustCompile(`^\d+\.\d+\.\d+$`)

// majorOf is the major of an N.N.N platformVersion (0 when it does not parse).
func majorOf(pv string) int {
	n, _ := strconv.Atoi(strings.SplitN(pv, ".", 2)[0])
	return n
}

// angleIGPURe is gen.py ANGLE_D3D11_RE for the two vendors that have iGPU floors.
var angleIGPURe = regexp.MustCompile(`^ANGLE \((Intel|AMD), .+ \(0x([0-9A-Fa-f]{8})\) Direct3D11 vs_5_0 ps_5_0, D3D11\)$`)

// gpuClaimKeys is gen.py GPU_CLAIM_KEYS.
var gpuClaimKeys = []string{"webGl:vendor", "webGl:renderer", "webGl2:vendor", "webGl2:renderer", "webGpu:blocked"}

const (
	intelCPU = "GenuineIntel"
	amdCPU   = "AuthenticAMD"
)

// igpuVendor is gen.py igpu_vendor: the CPUID vendor a claimed iGPU implies (AMD APUs ship only with AMD CPUs, Intel iGPUs
// only with Intel CPUs). "" for a dGPU, a renderer that is not ANGLE D3D11, and any id gen.gpu_class does not call an iGPU:
// data/igpu-ids.json holds exactly those ids (scripts/gen_go_core_data.py), so the two cannot differ on a name.
func igpuVendor(renderer string) string {
	m := angleIGPURe.FindStringSubmatch(renderer)
	if m == nil || loadTables() != nil {
		return ""
	}
	if !tables.igpuIDs[m[1]+":0x"+strings.ToUpper(m[2])] {
		return ""
	}
	if m[1] == "AMD" {
		return amdCPU
	}
	return intelCPU
}

// vendorFits is gen.py vendor_fits: false only when the claim implies a vendor and the host is known to have the other.
func vendorFits(renderer, host string) bool {
	want := igpuVendor(renderer)
	return want == "" || (host != intelCPU && host != amdCPU) || want == host
}

// angleD3D11Re is gen.py ANGLE_D3D11_RE.
var angleD3D11Re = regexp.MustCompile(`^ANGLE \((NVIDIA|AMD|Intel), (.+) \(0x([0-9A-Fa-f]{8})\) Direct3D11 vs_5_0 ps_5_0, D3D11\)$`)

// gpuArchitecture is gen.py gpu_architecture as "vendor/architecture" (Dawn's names, lower case: "intel/gen-9"), or "" for no
// renderer, a software or non-D3D11 string, or a device id the table (data/gpu-architectures.json) does not hold.
func gpuArchitecture(renderer string) string {
	m := angleD3D11Re.FindStringSubmatch(renderer)
	if m == nil || loadTables() != nil {
		return ""
	}
	vendor := strings.ToLower(m[1])
	dev, err := strconv.ParseUint(m[3], 16, 32)
	if err != nil {
		return ""
	}
	for _, s := range tables.arch[vendor] {
		if a, ok := s.ids[dev&s.mask]; ok {
			return vendor + "/" + a
		}
	}
	return ""
}

// webGpuOpen is the rule gen.py gpu_keys uses to leave webGpu:blocked false: the claim and the host share vendor and Dawn
// architecture (adapter.info reports only those), or the claim is the host's own renderer string. An unknown host ("") is never open.
func webGpuOpen(claim, host string) bool {
	if host == "" {
		return false
	}
	a := gpuArchitecture(claim)
	return claim == host || (a != "" && a == gpuArchitecture(host))
}

// igpuFloor is gen.py igpu_thread_floor: the fewest threads the claimed iGPU's CPU family ships with, 0 for none.
func igpuFloor(renderer string) int {
	m := angleIGPURe.FindStringSubmatch(renderer)
	if m == nil {
		return 0
	}
	return tables.floors[m[1]+":0x"+strings.ToUpper(m[2])]
}

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
	// A host snap below the claimed iGPU's floor drops the GPU claim (gen.py from_pool): the real GPU then matches the real CPU.
	if r, _ := cfg["webGl:renderer"].(string); r != "" {
		if floor := igpuFloor(r); floor > 0 && num("navigator.hardwareConcurrency") < floor {
			for _, k := range gpuClaimKeys {
				delete(cfg, k)
			}
			warn = append(warn, fmt.Sprintf("host cores snap to %d, below the %d threads of the claimed GPU's CPU family: the GPU claim is dropped and the host's real GPU is kept", num("navigator.hardwareConcurrency"), floor))
		}
		// An iGPU claim beside the other vendor's CPU: Skia's reciprocal estimates show the host's CPU vendor in a CPU-rastered readback.
		if _, kept := cfg["webGl:renderer"]; kept && !vendorFits(r, h.CPUVendor) {
			for _, k := range gpuClaimKeys {
				delete(cfg, k)
			}
			warn = append(warn, "the claimed iGPU ships only with the other CPU vendor than this host's: the GPU claim is dropped and the host's real GPU is kept")
		}
	}

	// A kept GPU claim stays blocked for WebGPU unless the host's renderer is the same family (gen.py gpu_keys). Only ever
	// true to false: a stored identity on a host with no renderer resolves as before.
	if r, kept := cfg["webGl:renderer"].(string); kept && cfg["webGpu:blocked"] == true && webGpuOpen(r, h.Renderer) {
		cfg["webGpu:blocked"] = false
	}

	// 2. platform version (Windows claim).
	switch {
	case h.PlatformVersion == "":
		warn = append(warn, "host platform version unknown: the entry's value stays")
	case platformVersionRe.MatchString(h.PlatformVersion):
		cfg["ua:platformVersion"] = h.PlatformVersion
		// A Windows 11 version lists the Windows 11 families (gen.py from_pool): fonts date Windows (CreepJS).
		w := tables.fonts.Families.Windows.Win11
		// An absent list (every host font visible) stays absent: six names alone would hide the rest.
		if list, ok := cfg["fonts:list"].([]any); ok && majorOf(h.PlatformVersion) >= w.MinPlatformMajor {
			listed := map[string]bool{}
			for _, f := range list {
				listed[f.(string)] = true
			}
			for _, f := range w.Families {
				if !listed[f] {
					list = append(list, f)
				}
			}
			cfg["fonts:list"] = list
		}
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

	// 4b. the locale's supplemental font pack is listed: a Windows with that display language has it (gen.py with_locale_pack).
	if list, ok := cfg["fonts:list"].([]any); ok {
		cfg["fonts:list"] = withLocalePack(&tables.fonts, list, tag)
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
