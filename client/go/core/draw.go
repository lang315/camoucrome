package core

import (
	"crypto/rand"
	"encoding/binary"
	"encoding/json"
	"fmt"
)

const maxDraws = 50 // gen.py MAX_DRAWS

// DrawWarning is the one warning for a drawn Identity beside its Host's GPU: the renderer is given but its Dawn architecture is
// unknown (Draw then claims from the whole pool with WebGPU blocked, as before), or the architecture is known and the pool had no
// entry of it (the identity has no GPU claim and the real GPU shows). "" for no renderer, a claim of the host's architecture,
// or no Host (gen.py generate, _arch_warning).
func DrawWarning(h *Host, id Identity) string {
	if h == nil || h.Renderer == "" {
		return ""
	}
	var e map[string]any
	_ = json.Unmarshal(id.Entry, &e)
	_, claimed := e["webGl:renderer"]
	switch a := gpuArchitecture(h.Renderer); {
	case a == "" && claimed:
		return "the host GPU's architecture is unknown (no ANGLE D3D11 renderer, or an id Dawn's table lacks): the GPU claim is drawn from the whole pool and WebGPU stays blocked"
	case a != "" && !claimed:
		return fmt.Sprintf("no pool entry in %d draws shares the host GPU's vendor and architecture %s: no GPU claim, the host's real GPU shows", maxDraws, a)
	}
	return ""
}

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
	// Same-architecture mode (gen.py generate): a claim needs the host's vendor and Dawn architecture. With none in the budget the
	// first entry that passed every other rule is kept with no GPU claim, so the host's real GPU shows. An unknown host
	// architecture (or no Host) draws as it did.
	var hostArch string
	if h != nil {
		hostArch = gpuArchitecture(h.Renderer)
	}
	var spare map[string]any
	build := func(entry map[string]any) (Identity, error) {
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
		if rend, _ := entry["webGl:renderer"].(string); hostArch != "" && gpuArchitecture(rend) != hostArch {
			// the real iGPU shows once the claim is gone: its thread count must not sit below the host iGPU's floor
			// A floor that is no thread step (14, 18, 24: real SKU counts) is met by raising the cores to it, as Resolve's dropClaim does.
			n, _ := entry["navigator.hardwareConcurrency"].(float64)
			if floor := igpuFloor(h.Renderer); spare == nil && (snapCores(int(n), h.Cores) >= floor || floor <= h.Cores) {
				if snapCores(int(n), h.Cores) < floor {
					entry["navigator.hardwareConcurrency"] = float64(floor)
				}
				spare = entry
			}
			continue
		}
		return build(entry)
	}
	if spare != nil {
		for _, k := range gpuClaimKeys {
			delete(spare, k)
		}
		return build(spare)
	}
	return Identity{}, fmt.Errorf("no pool entry holds a %dx%d window at this work area %v and CPU vendor %q in %d draws", minWindow[0], minWindow[1], h.WorkArea, h.CPUVendor, maxDraws)
}
