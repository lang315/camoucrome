package camoucrome

import (
	"bytes"
	"crypto/rand"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strconv"
)

// SeedKeys mirrors settings/launcher.json "per_instance_seeds". A preset is a
// device identity; these are per instance and never part of it.
var SeedKeys = []string{"canvas:seed", "audio:seed", "mediaDevices:seed"}

// SeedsFile mirrors settings/launcher.json "per_instance_seeds.profile_file".
const SeedsFile = "camoucrome-seeds.json"

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

// ProfileSeeds returns the seeds a kept profile launches with: drawn once into
// <userDataDir>/camoucrome-seeds.json and read back on every later launch, so
// the profile shows the same canvas, audio and device-ID fingerprint each
// session. Keys missing from the file are drawn (with read, as
// PerInstanceConfig) and added. A damaged file is an error, never a redraw,
// which would change the fingerprint silently. The Python and Node clients
// read and write the same file.
func ProfileSeeds(userDataDir string, read func([]byte) (int, error)) (map[string]any, error) {
	path := filepath.Join(userDataDir, SeedsFile)
	stored := map[string]any{}
	raw, err := os.ReadFile(path)
	if err != nil && !errors.Is(err, fs.ErrNotExist) {
		return nil, err
	}
	if err == nil {
		d := json.NewDecoder(bytes.NewReader(raw))
		d.UseNumber()
		if err := d.Decode(&stored); err != nil {
			return nil, fmt.Errorf("%s must hold a JSON object: %w", path, err)
		}
	}
	seeds := make(map[string]any, len(SeedKeys))
	var missing []string
	for _, k := range SeedKeys {
		v, ok := stored[k]
		if !ok {
			missing = append(missing, k)
			continue
		}
		n, isNum := v.(json.Number)
		u, err := strconv.ParseUint(string(n), 10, 32)
		if !isNum || err != nil || u == 0 {
			return nil, fmt.Errorf("%s: %s must be a non-zero uint32, not %v", path, k, v)
		}
		seeds[k] = uint32(u)
	}
	if len(missing) == 0 {
		return seeds, nil
	}
	drawn, err := PerInstanceConfig(read)
	if err != nil {
		return nil, err
	}
	for _, k := range missing {
		seeds[k], stored[k] = drawn[k], drawn[k]
	}
	out, err := json.Marshal(stored)
	if err != nil {
		return nil, err
	}
	if err := os.MkdirAll(userDataDir, 0o755); err != nil {
		return nil, err
	}
	// Written beside the target and renamed over it, so a crash mid-write never
	// leaves the damaged file the check above would refuse.
	tmp, err := os.CreateTemp(userDataDir, SeedsFile+".")
	if err != nil {
		return nil, err
	}
	_, werr := tmp.Write(out)
	if cerr := tmp.Close(); werr == nil {
		werr = cerr
	}
	if werr == nil {
		werr = os.Rename(tmp.Name(), path)
	}
	if werr != nil {
		os.Remove(tmp.Name())
		return nil, werr
	}
	return seeds, nil
}
