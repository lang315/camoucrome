package core

import (
	"encoding/json"
	"strings"
	"testing"
)

func claimOf(t *testing.T, id Identity) string {
	t.Helper()
	var e map[string]any
	if err := json.Unmarshal(id.Entry, &e); err != nil {
		t.Fatal(err)
	}
	r, _ := e["webGl:renderer"].(string)
	return r
}

func TestIGPUVendor(t *testing.T) {
	cases := map[string]string{
		"ANGLE (Intel, Intel(R) Iris(R) Xe Graphics (0x000046A6) Direct3D11 vs_5_0 ps_5_0, D3D11)":   intelCPU,
		"ANGLE (Intel, Intel(R) UHD Graphics 620 (0x00003EA0) Direct3D11 vs_5_0 ps_5_0, D3D11)":      intelCPU,
		"ANGLE (AMD, AMD Radeon(TM) Graphics (0x000015BF) Direct3D11 vs_5_0 ps_5_0, D3D11)":          amdCPU,
		"ANGLE (AMD, AMD Radeon RX Vega 11 Graphics (0x000015DD) Direct3D11 vs_5_0 ps_5_0, D3D11)":   amdCPU,
		"ANGLE (Intel, Intel(R) Arc(TM) A770 Graphics (0x000056A0) Direct3D11 vs_5_0 ps_5_0, D3D11)": "",
		"ANGLE (AMD, AMD Radeon RX 6800 (0x000073BF) Direct3D11 vs_5_0 ps_5_0, D3D11)":               "",
		"ANGLE (AMD, AMD Radeon Pro W6800 (0x000073A2) Direct3D11 vs_5_0 ps_5_0, D3D11)":             "",
		"ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002503) Direct3D11 vs_5_0 ps_5_0, D3D11)":       "",
		"": "",
	}
	for r, want := range cases {
		if got := igpuVendor(r); got != want {
			t.Errorf("%q: %q, want %q", r, got, want)
		}
	}
}

func TestCPUVendorOf(t *testing.T) {
	for in, want := range map[string]string{
		"vendor_id\t: GenuineIntel\nmodel name : x": intelCPU,
		"vendor_id\t: AuthenticAMD":                 amdCPU,
		"Intel64 Family 6 Model 140, GenuineIntel":  intelCPU,
		"AMD64 Family 25 Model 33, AuthenticAMD":    amdCPU,
		"Apple M1":                                  "", "": "",
	} {
		if got := cpuVendorOf(in); got != want {
			t.Errorf("%q: %q, want %q", in, got, want)
		}
	}
}

// The shares of the embedded pool that mismatch each host; gen.py's gpu_class gives the same counts (test_igpu_cpu_vendor.py).
func TestPoolMismatchShares(t *testing.T) {
	p, err := pool()
	if err != nil {
		t.Fatal(err)
	}
	var amd, intel int
	for _, raw := range p.Entries {
		var e map[string]any
		if err := json.Unmarshal(raw, &e); err != nil {
			t.Fatal(err)
		}
		switch igpuVendor(e["webGl:renderer"].(string)) {
		case amdCPU:
			amd++
		case intelCPU:
			intel++
		}
	}
	if amd != 634 || intel != 2276 {
		t.Fatalf("AMD iGPU claims %d (want 634), Intel iGPU claims %d (want 2276) of %d", amd, intel, len(p.Entries))
	}
}

func TestDrawSkipsAMismatchedIGPU(t *testing.T) {
	for _, host := range []string{intelCPU, amdCPU} {
		h := goodHost
		h.CPUVendor = host
		n := 0
		for s := uint64(0); s < 300; s++ {
			id := mustDraw(t, s, &h)
			if v := igpuVendor(claimOf(t, id)); v != "" && v != host {
				t.Fatalf("seed %d on %s drew a claim for %s", s, host, v)
			}
			if igpuVendor(claimOf(t, id)) == host {
				n++
			}
		}
		if n < 20 {
			t.Fatalf("%s: only %d same-vendor iGPU claims in 300 draws", host, n)
		}
	}
}

// A stored identity drops the GPU claim on a mismatched host, keeps it on a same-vendor host and with the field unset.
func TestResolveDropsAMismatchedClaim(t *testing.T) {
	var dropped, kept int
	for s := uint64(0); s < 300; s++ {
		id := mustDraw(t, s, &goodHost)
		want := igpuVendor(claimOf(t, id))
		if want == "" {
			continue
		}
		other := amdCPU
		if want == amdCPU {
			other = intelCPU
		}
		for host, keep := range map[string]bool{want: true, "": true, other: false} {
			h := goodHost
			h.Cores = 64
			h.CPUVendor = host
			r, err := Resolve(id, h, nil)
			if err != nil {
				t.Fatal(err)
			}
			for _, k := range gpuClaimKeys {
				if _, ok := r.Config[k]; ok != keep {
					t.Fatalf("seed %d host %q: %s present = %v, want %v", s, host, k, ok, keep)
				}
			}
			if !keep {
				found := false
				for _, w := range r.Warnings {
					found = found || strings.Contains(w, "CPU vendor")
				}
				if !found {
					t.Fatalf("seed %d: no warning for the drop", s)
				}
				dropped++
			} else {
				kept++
			}
		}
	}
	if dropped < 20 || kept < 40 {
		t.Fatalf("dropped %d kept %d", dropped, kept)
	}
}
