// Package core draws a device identity, resolves it for this machine and
// proxy exit, and emits the launch env and argv. Standard library only.
package core

import "encoding/json"

// ForkVersion is the Chromium version of the fork release this commit pairs with.
const ForkVersion = "157.0.8103.51"

// Identity is stored by the caller: opaque, JSON round-trips.
type Identity struct {
	Version  int               `json:"version"`         // pool format
	OS       string            `json:"os"`              // "windows"
	Entry    json.RawMessage   `json:"entry"`           // the pool entry, verbatim
	Seeds    map[string]uint32 `json:"seeds"`           // canvas:seed, mediaDevices:seed
	HostSeed uint64            `json:"hostSeed,string"` // seeds every random host step; a string so a float64 JSON reader cannot lose bits
}

// Display is the host display from the one-time browser probe.
type Display struct {
	Gamut     string `json:"gamut"`     // srgb, p3, rec2020
	ColorBits int    `json:"colorBits"` // 8 or 10
	HDR       bool   `json:"hdr"`
}

// Host is this machine; zero values mean unknown (the step is skipped with a warning).
type Host struct {
	Cores           int      // allowed CPUs
	WorkArea        [2]int   // availWidth, availHeight in physical px
	PlatformVersion string   // UA-CH platformVersion, N.N.N
	Display         *Display // from the display probe
}

// Exit is the proxy exit: IANA zone and ISO-3166-1 alpha-2 country.
type Exit struct{ Timezone, Country string }

// Resolved is an Identity applied to a Host and Exit.
type Resolved struct {
	Config   map[string]any
	Window   [2]int
	DPR      float64
	Position [2]int
	Args     []string // launch.args, e.g. --force-color-profile=srgb
	Warnings []string
	Cores    int // resolved navigator.hardwareConcurrency; wrap the spawn in Pinned(Cores, start)
}

// LaunchOpts are the caller's launch inputs. The spawner owns the transport
// and proxy argv, so none of those fields exist here.
type LaunchOpts struct {
	UserDataDir string
	Headless    bool
	FontsDir    string // bundled font dir; a Windows or macOS claim on a Linux host needs it
	Strict      bool   // Env sets CAMOU_CONFIG_STRICT=1: a config the browser cannot take aborts the start
	ExtraArgs   []string
}
