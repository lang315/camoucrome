package core

import (
	"crypto/rand"
	"encoding/binary"
	"encoding/json"
	"fmt"
)

const maxDraws = 50 // gen.py MAX_DRAWS

// Draw picks a device from the embedded pool for a claimed OS. With seed nil
// the draw is random (crypto/rand); a given seed makes every part of the
// Identity deterministic. With a Host that knows its work area, entries whose
// DPR cannot hold the minimum window there are skipped, as gen.generate does.
// The returned Identity holds the full entry (font keys included), so a later
// release's data cannot change it.
func Draw(os string, seed *uint64, h *Host) (Identity, error) {
	if os != "windows" {
		return Identity{}, fmt.Errorf("os %q has no pool: the pool OSes are [windows]", os)
	}
	p, err := pool()
	if err != nil {
		return Identity{}, err
	}
	if err := loadTables(); err != nil {
		return Identity{}, err
	}
	var s uint64
	if seed != nil {
		s = *seed
	} else {
		var b [8]byte
		if _, err := rand.Read(b[:]); err != nil {
			return Identity{}, err
		}
		s = binary.LittleEndian.Uint64(b[:])
	}
	r := newRng(s, 0x9E3779B97F4A7C15)
	for try := 0; try < maxDraws; try++ {
		raw := p.Entries[r.intn(len(p.Entries))]
		entry := map[string]any{}
		if err := json.Unmarshal(raw, &entry); err != nil {
			return Identity{}, err
		}
		dpr, _ := entry["dpr"].(float64)
		if h != nil && h.WorkArea[0] > 0 && h.WorkArea[1] > 0 && !holdsMinWindow(h.WorkArea, dpr) {
			continue
		}
		if r, _ := entry["webGl:renderer"].(string); h != nil && !vendorFits(r, h.CPUVendor) {
			continue // gen.py gpu_ok: a claimed iGPU needs the host's CPU vendor
		}
		var groups []string
		for _, g := range entry["fontGroups"].([]any) {
			groups = append(groups, g.(string))
		}
		delete(entry, "fontGroups")
		for k, v := range fontKeys(&tables.fonts, groups) {
			entry[k] = v
		}
		full, err := json.Marshal(entry)
		if err != nil {
			return Identity{}, err
		}
		nonzero := func() uint32 {
			for {
				if v := uint32(r.s.Uint64()); v != 0 {
					return v
				}
			}
		}
		return Identity{Version: poolFormat, OS: os, Entry: full,
			Seeds:    map[string]uint32{"canvas:seed": nonzero(), "mediaDevices:seed": nonzero()},
			HostSeed: r.s.Uint64()}, nil
	}
	return Identity{}, fmt.Errorf("no pool entry holds a %dx%d window at this work area %v and CPU vendor %q in %d draws", minWindow[0], minWindow[1], h.WorkArea, h.CPUVendor, maxDraws)
}
