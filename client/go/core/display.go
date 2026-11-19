package core

import (
	"encoding/json"
	"fmt"
	"strings"
)

// DisplayProbeJS is client/python/camoucrome/probe.py HOST_DISPLAY_JS, byte
// for byte. The spawner runs it once in a headless page of the fork with no
// config, and the caller stores the ParseDisplay result per machine.
const DisplayProbeJS = `() => ({gamut: matchMedia('(color-gamut: rec2020)').matches ? 'rec2020' : matchMedia('(color-gamut: p3)').matches ? 'p3' : 'srgb', colorBits: matchMedia('(color: 10)').matches ? 10 : 8, hdr: matchMedia('(dynamic-range: high)').matches})`

// ParseDisplay reads the probe's result (a JSON object) and mirrors
// gen.valid_display: gamut in srgb, p3, rec2020; colorBits 8 or 10; hdr a bool.
func ParseDisplay(raw string) (*Display, error) {
	var d struct {
		Gamut     string `json:"gamut"`
		ColorBits int    `json:"colorBits"`
		HDR       *bool  `json:"hdr"`
	}
	if err := json.Unmarshal([]byte(raw), &d); err != nil {
		return nil, fmt.Errorf("display probe result is not the expected object: %w", err)
	}
	switch {
	case d.Gamut != "srgb" && d.Gamut != "p3" && d.Gamut != "rec2020":
		return nil, fmt.Errorf("display gamut %q is not srgb, p3 or rec2020", d.Gamut)
	case d.ColorBits != 8 && d.ColorBits != 10:
		return nil, fmt.Errorf("display colorBits %d is not 8 or 10", d.ColorBits)
	case d.HDR == nil:
		return nil, fmt.Errorf("display hdr is missing")
	}
	return &Display{Gamut: d.Gamut, ColorBits: d.ColorBits, HDR: *d.HDR}, nil
}

// RendererProbeJS is client/python/camoucrome/probe.py HOST_GL_JS, byte for byte. Run it in the same headless page as
// DisplayProbeJS, a config-free headless launch. Never run it under an identity config: the page then reports the
// claim, not the host, and WebGPU is unblocked for a renderer the host does not have (the real adapter leaks).
// Pass the result through ParseRenderer.
const RendererProbeJS = `() => { const g = document.createElement('canvas').getContext('webgl');
  const e = g && g.getExtension('WEBGL_debug_renderer_info');
  return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : null; }`

// softwareMarkers is probe.py SOFTWARE_MARKERS.
var softwareMarkers = []string{"swiftshader", "llvmpipe", "software", "basic render"}

// ParseRenderer mirrors probe.host_renderer on the probe's string: a software renderer or an empty string is no host
// renderer (pinning it into an identity is a bot tell), so it comes back "" with an error and WebGPU stays blocked.
func ParseRenderer(s string) (string, error) {
	low := strings.ToLower(s)
	if strings.TrimSpace(s) == "" {
		return "", fmt.Errorf("renderer probe returned no renderer")
	}
	for _, m := range softwareMarkers {
		if strings.Contains(low, m) {
			return "", fmt.Errorf("renderer %q is a software renderer", s)
		}
	}
	return s, nil
}
