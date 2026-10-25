package camoucrome

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
)

// Generated is what `python -m camoucrome.gen` prints: the config and the
// launcher options that go with it. The generator lives in Python (one
// implementation, tested once); Go execs it.
type Generated struct {
	Config map[string]any `json:"config"`
	Launch struct {
		Window [2]int  `json:"window"`
		DPR    float64 `json:"dpr"`
	} `json:"launch"`
	Warnings []string `json:"warnings"`
}

// ParseGenerated decodes the generator's output and folds it into Options
// (Config, Window, DPR); every other field is left for the caller.
func ParseGenerated(raw []byte) (Options, error) {
	var g Generated
	if err := json.Unmarshal(raw, &g); err != nil {
		return Options{}, fmt.Errorf("generator output: %w", err)
	}
	if len(g.Config) == 0 {
		return Options{}, fmt.Errorf("generator output has no config")
	}
	return Options{Config: g.Config, Window: g.Launch.Window, DPR: g.Launch.DPR}, nil
}

// generatedWarnings is the "warnings" list of the generator's output (the host GPU or fonts it could not match).
func generatedWarnings(raw []byte) []string {
	var g Generated
	_ = json.Unmarshal(raw, &g)
	return g.Warnings
}

// GenArgs is what `python -m camoucrome.gen` takes. Seed < 0 means unseeded. ExitIP (with GeoIPDB, a DB-IP Lite or
// GeoLite2-layout .mmdb) makes the zone and locale follow where the proxy's exit address is, unless set here.
type GenArgs struct {
	OS, Timezone, Locale, GPU string
	Seed                      int
	ExitIP, GeoIPDB           string
	// HostRenderer is the host's WebGL renderer (an Intel Gen9 host draws a Gen9 identity per seed); HostFonts limits a
	// Windows claim's fonts to the families this host has.
	HostRenderer string
	HostFonts    bool
}

// genArgs is the generator's argument list; the order is the old Generate's, the new flags last.
func genArgs(g GenArgs) []string {
	args := []string{"-m", "camoucrome.gen"}
	if g.Timezone != "" {
		args = append(args, "--timezone", g.Timezone)
	}
	if g.GPU != "" {
		args = append(args, "--gpu", g.GPU)
	}
	if g.OS != "" {
		args = append(args, "--os", g.OS)
	}
	if g.Locale != "" {
		args = append(args, "--locale", g.Locale)
	}
	if g.Seed >= 0 {
		args = append(args, "--seed", fmt.Sprint(g.Seed))
	}
	if g.ExitIP != "" {
		args = append(args, "--exit-ip="+g.ExitIP)
	}
	if g.GeoIPDB != "" {
		args = append(args, "--geoip-db="+g.GeoIPDB)
	}
	if g.HostRenderer != "" {
		args = append(args, "--host-renderer="+g.HostRenderer)
	}
	if g.HostFonts {
		args = append(args, "--host-fonts")
	}
	return args
}

// Generate runs `python -m camoucrome.gen` (the Python client must be
// installed in that interpreter) with the given OS ("windows", "macos",
// "linux" or "" for any), an optional IANA timezone ("" = the generator's
// locale->zone table), an optional locale and an optional settings/webgl
// profile id. seed < 0 means unseeded.
func Generate(python, osName, timezone, locale, gpu string, seed int) (Options, error) {
	return GenerateWith(python, GenArgs{OS: osName, Timezone: timezone, Locale: locale, GPU: gpu, Seed: seed})
}

// GenerateWith is Generate with the exit-IP flags. The generator's warnings (an exit IP it could not place) go to
// this process's stderr as they are printed.
func GenerateWith(python string, g GenArgs) (Options, error) {
	cmd := exec.Command(python, genArgs(g)...)
	var stderr bytes.Buffer
	cmd.Stderr = io.MultiWriter(&stderr, os.Stderr)
	out, err := cmd.Output()
	if err != nil {
		return Options{}, fmt.Errorf("camoucrome.gen: %w: %s", err, stderr.String())
	}
	for _, w := range generatedWarnings(out) {
		fmt.Fprintln(os.Stderr, "camoucrome.gen: warning: "+w)
	}
	return ParseGenerated(out)
}
