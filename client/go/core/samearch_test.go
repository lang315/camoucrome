package core

import (
	"encoding/json"
	"reflect"
	"testing"
)

// Same-architecture mode (owner 2026-11-19): a new draw claims a GPU only from the host's Dawn architecture. Every host here is
// a fake renderer string; no test reads the machine's GPU or CPU.
const (
	d3d     = "Direct3D11 vs_5_0 ps_5_0, D3D11)"
	rtx3060 = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) " + d3d
	rtx3070 = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 (0x00002484) " + d3d
	rtx4090 = "ANGLE (NVIDIA, NVIDIA GeForce RTX 4090 (0x00002684) " + d3d
	rx6800  = "ANGLE (AMD, AMD Radeon RX 6800 (0x000073BF) " + d3d
	gen8    = "ANGLE (Intel, Intel(R) HD Graphics 5500 (0x00001616) " + d3d
	notIn   = "ANGLE (Intel, Intel(R) UHD Graphics (0x0000FFFF) " + d3d
	swift   = "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)"
)

func TestGPUArchitecture(t *testing.T) {
	for r, want := range map[string]string{
		g630: "intel/gen-9", "ANGLE (Intel, Intel(R) UHD Graphics (0x00009B41) " + d3d: "intel/gen-9",
		"ANGLE (Intel, Intel(R) UHD Graphics (0x00009BC5) " + d3d: "intel/gen-9", xe: "intel/gen-12lp",
		rtx3060: "nvidia/ampere", rtx3070: "nvidia/ampere", rtx4090: "nvidia/lovelace", rx6800: "amd/rdna-2",
		"ANGLE (AMD, AMD Radeon RX 6900 (0x0000163F) " + d3d: "amd/rdna-2", // the exact-id set
		"": "", notIn: "", swift: "", "llvmpipe (LLVM 15)": "",
	} {
		if got := gpuArchitecture(r); got != want {
			t.Errorf("%q: %q, want %q", r, got, want)
		}
	}
}

func claimsOn(t *testing.T, host string, seeds int) (claims []string, none int) {
	t.Helper()
	for s := 1; s <= seeds; s++ {
		h := goodHost
		h.Cores, h.Renderer = 64, host // many cores: the host iGPU floor never rejects a fallback here
		r := claimOf(t, mustDraw(t, uint64(s), &h))
		if r == "" {
			none++
			continue
		}
		claims = append(claims, r)
	}
	return
}

func TestDrawClaimsOnlyTheHostArchitectureOrNone(t *testing.T) {
	for _, host := range []string{g630, rtx3060, rx6800} {
		claims, none := claimsOn(t, host, 300)
		if len(claims) == 0 {
			t.Fatalf("%q: no claim in 300 seeds", host)
		}
		for _, c := range claims {
			if gpuArchitecture(c) != gpuArchitecture(host) {
				t.Fatalf("host %q drew a claim %q", host, c)
			}
		}
		t.Logf("host %s: %d claims, %d none in 300 seeds", gpuArchitecture(host), len(claims), none)
	}
}

func TestNoEntryOfTheHostArchitectureMeansNoClaim(t *testing.T) {
	claims, none := claimsOn(t, gen8, 20) // the pool has no Gen 8 entry
	if len(claims) != 0 || none != 20 {
		t.Fatalf("%d claims, %d none: want 0 and 20", len(claims), none)
	}
	h := goodHost
	h.Renderer = gen8
	id := mustDraw(t, 3, &h)
	var e map[string]any
	json.Unmarshal(id.Entry, &e)
	for _, k := range gpuClaimKeys {
		if _, ok := e[k]; ok {
			t.Errorf("%s stayed in a no-claim entry", k)
		}
	}
}

// An unknown host (no renderer, a software renderer, a non-D3D11 string, an id missing from the table) draws as before.
func TestUnknownHostDrawsAsBefore(t *testing.T) {
	for s := uint64(1); s <= 40; s++ {
		base := mustDraw(t, s, &goodHost)
		for _, unknown := range []string{swift, notIn, "llvmpipe (LLVM 15)"} {
			h := goodHost
			h.Renderer = unknown
			if got := mustDraw(t, s, &h); !reflect.DeepEqual(got, base) {
				t.Fatalf("seed %d, host %q: the draw changed", s, unknown)
			}
		}
	}
}

func TestDrawWarning(t *testing.T) {
	claim := mustDraw(t, 1, &Host{Renderer: g630})
	none := mustDraw(t, 1, &Host{Renderer: gen8}) // no Gen 8 entry: no claim
	if claimOf(t, claim) == "" || claimOf(t, none) != "" {
		t.Fatal("fixtures: want a claim and a no-claim identity")
	}
	for _, c := range []struct {
		host string
		id   Identity
		want bool
	}{{"", claim, false}, {g630, claim, false}, {rtx3060, claim, false}, {swift, claim, true}, {notIn, claim, true},
		{gen8, none, true}, {"", none, false}} {
		if got := DrawWarning(&Host{Renderer: c.host}, c.id) != ""; got != c.want {
			t.Errorf("host %q, claim %q: warning %v, want %v", c.host, claimOf(t, c.id), got, c.want)
		}
	}
	if DrawWarning(nil, claim) != "" {
		t.Error("a nil host warns")
	}
}

// A no-claim fallback must not show a real iGPU beside a thread count below that iGPU's floor (t6 review of #217): host Radeon
// Graphics 0x15E7, 16 cores, AMD CPU, floor 8.
func TestNoClaimFallbackKeepsTheHostIGPUFloor(t *testing.T) {
	host := Host{Cores: 16, CPUVendor: amdCPU, Renderer: "ANGLE (AMD, AMD Radeon(TM) Graphics (0x000015E7) " + d3d}
	if err := loadTables(); err != nil {
		t.Fatal(err)
	}
	floor := igpuFloor(host.Renderer)
	if floor == 0 {
		t.Fatal("fixture: the host has no iGPU floor")
	}
	var none int
	for s := uint64(1); s <= 300; s++ {
		id := mustDraw(t, s, &host)
		if claimOf(t, id) != "" {
			continue
		}
		none++
		var e map[string]any
		json.Unmarshal(id.Entry, &e)
		if n := snapCores(int(e["navigator.hardwareConcurrency"].(float64)), host.Cores); n < floor {
			t.Fatalf("seed %d: no claim with %d threads, below the host iGPU floor %d", s, n, floor)
		}
	}
	t.Logf("%d of 300 no-claim identities, all at or above floor %d", none, floor)
}

// The pool's share by architecture and how often a host of each architecture draws a claim (reported in the PR; run with -v).
// A host takes the first pool renderer of its architecture. The budget is maxDraws, so a rare architecture can draw none.
func TestDrawRateByArchitecture(t *testing.T) {
	p, err := pool()
	if err != nil {
		t.Fatal(err)
	}
	share, sample := map[string]int{}, map[string]string{}
	for _, raw := range p.Entries {
		var e map[string]any
		json.Unmarshal(raw, &e)
		r, _ := e["webGl:renderer"].(string)
		a := gpuArchitecture(r)
		if a == "" {
			t.Fatalf("pool renderer %q has no Dawn architecture", r)
		}
		share[a]++
		if sample[a] == "" {
			sample[a] = r
		}
	}
	for a, n := range share {
		claims, none := claimsOn(t, sample[a], 300)
		t.Logf("%-18s %5.1f%% of the pool; host of it draws a claim in %d of 300 seeds (%d none)", a, 100*float64(n)/float64(len(p.Entries)), len(claims), none)
	}
}
