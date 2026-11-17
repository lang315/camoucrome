package core

import (
	"encoding/json"
	"fmt"
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
