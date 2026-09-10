package camoucrome

import (
	"crypto/rand"
	"encoding/binary"
)

// SeedKeys mirrors settings/launcher.json "per_instance_seeds". A preset is a
// device identity; these are per instance and never part of it.
var SeedKeys = []string{"canvas:seed", "audio:seed", "mediaDevices:seed"}

// PerInstanceConfig draws a fresh non-zero uint32 for every SeedKeys entry.
// Merge explicit keys over it and pass it as Options.Config beside
// Options.Preset. A nil reader uses crypto/rand.
func PerInstanceConfig(read func([]byte) (int, error)) (map[string]any, error) {
	if read == nil {
		read = rand.Read
	}
	cfg := make(map[string]any, len(SeedKeys))
	for _, k := range SeedKeys {
		var b [4]byte
		for {
			if _, err := read(b[:]); err != nil {
				return nil, err
			}
			if v := binary.LittleEndian.Uint32(b[:]); v != 0 {
				cfg[k] = v
				break
			}
		}
	}
	return cfg, nil
}
