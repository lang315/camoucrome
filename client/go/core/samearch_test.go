package core

import (
	"encoding/json"
	"reflect"
	"strings"
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

// A stored identity is re-resolved on a host that may have another GPU architecture: the claim must go with a warning
// (rule 4), not stay. An unknown host renderer keeps the claim, as before.
func TestResolveDropsAClaimOfAnotherHostArchitecture(t *testing.T) {
	id := withClaim(t, rtx3060, true)
	claimed := func(r Resolved) bool { _, ok := r.Config["webGl:renderer"]; return ok }
	cases := []struct {
		name, host string
		keep       bool
	}{
		{"other architecture, same vendor", rtx4090, false},
		{"same architecture", rtx3070, true},
		{"unknown renderer", "", true},
	}
	for _, c := range cases {
		r := resolveOn(t, id, c.host)
		if claimed(r) != c.keep {
			t.Errorf("%s: claim kept = %v, want %v", c.name, claimed(r), c.keep)
		}
		if !c.keep {
			for _, k := range gpuClaimKeys {
				if _, ok := r.Config[k]; ok {
					t.Errorf("%s: %s survived the drop", c.name, k)
				}
			}
		}
		var n int
		for _, w := range r.Warnings {
			if strings.Contains(w, "architecture") {
				n++
			}
		}
		if want := map[bool]int{true: 0, false: 1}[c.keep]; n != want {
			t.Errorf("%s: %d architecture warnings, want %d: %v", c.name, n, want, r.Warnings)
		}
	}
}

// After the architecture drop the host's real iGPU shows: a stored entry with fewer threads than its floor is raised to the
// smallest thread step the host allows, or kept with a warning when the host cannot reach the floor.
func TestResolveArchDropKeepsTheHostIGPUFloor(t *testing.T) {
	id := withClaim(t, rtx3060, true)
	var e map[string]any
	if err := json.Unmarshal(id.Entry, &e); err != nil {
		t.Fatal(err)
	}
	e["navigator.hardwareConcurrency"] = float64(4)
	id.Entry, _ = json.Marshal(e)
	for _, c := range []struct {
		cores, want int
		warn        string
	}{{16, 8, "raised from 4 to 8"}, {4, 4, "fewer than the 8 threads"}} {
		h := goodHost
		h.Cores, h.Renderer = c.cores, xe // Iris Xe 0x9A49: floor 8
		r, err := Resolve(id, h, nil)
		if err != nil {
			t.Fatal(err)
		}
		if got := r.Config["navigator.hardwareConcurrency"]; got != float64(c.want) {
			t.Errorf("host cores %d: hardwareConcurrency %v, want %d", c.cores, got, c.want)
		}
		var found bool
		for _, w := range r.Warnings {
			found = found || strings.Contains(w, c.warn)
		}
		if !found {
			t.Errorf("host cores %d: no warning containing %q: %v", c.cores, c.warn, r.Warnings)
		}
	}
}

// The floor is raised to itself, not to a thread step: floors 24, 14 and 18 are real SKU counts. The other two drops
// (cores below the claimed iGPU's floor, the CPU vendor) leave the real iGPU the same floor.
func TestResolveDropRaisesToTheFloorItself(t *testing.T) {
	const (
		uhd770 = "ANGLE (Intel, Intel(R) UHD Graphics 770 (0x0000A780) " + d3d // floor 24
		ultra  = "ANGLE (Intel, Intel(R) Graphics (0x00007D45) " + d3d         // floor 14
		ultra5 = "ANGLE (Intel, Intel(R) Graphics (0x00007D55) " + d3d         // floor 18
	)
	resolve := func(claim string, entryCores int, h Host) Resolved {
		id := withClaim(t, claim, true)
		var e map[string]any
		if err := json.Unmarshal(id.Entry, &e); err != nil {
			t.Fatal(err)
		}
		e["navigator.hardwareConcurrency"] = float64(entryCores)
		id.Entry, _ = json.Marshal(e)
		r, err := Resolve(id, h, nil)
		if err != nil {
			t.Fatal(err)
		}
		return r
	}
	for _, c := range []struct {
		host        string
		cores, want int
	}{{uhd770, 32, 24}, {uhd770, 24, 24}, {ultra, 14, 14}, {ultra5, 20, 18}} {
		h := goodHost
		h.Cores, h.Renderer = c.cores, c.host
		// 1. arch drop
		if got := resolve(rtx3060, 8, h).Config["navigator.hardwareConcurrency"]; got != float64(c.want) {
			t.Errorf("arch drop, host %q cores %d: %v, want %d", c.host, c.cores, got, c.want)
		}
		// 2. CPU vendor drop (a synthetic path: an Intel iGPU claim beside an AMD CPU never occurs on a real host): an Intel iGPU claim on an AMD CPU host of the same architecture as the claim
		h.CPUVendor = amdCPU
		if got := resolve(c.host, 8, h).Config["navigator.hardwareConcurrency"]; got != float64(c.want) {
			t.Errorf("vendor drop, host %q cores %d: %v, want %d", c.host, c.cores, got, c.want)
		}
	}
	// 3. cores-floor drop: a claimed iGPU of floor 24 with 8 entry cores, on a host of the same iGPU with 32 cores
	h := goodHost
	h.Cores, h.Renderer = 32, ultra5
	r := resolve(uhd770, 8, h)
	if _, kept := r.Config["webGl:renderer"]; kept || r.Config["navigator.hardwareConcurrency"] != float64(18) {
		t.Errorf("cores-floor drop: claim kept or cores %v, want dropped and 18", r.Config["navigator.hardwareConcurrency"])
	}
}

// A floor that is no thread step (14, 18, 24) must not make Draw fail: the spare entry is valid when the host reaches the floor,
// and its cores are raised to it. 400 seeds, every one must draw, and every spare's cores must meet the floor.
func TestDrawNonStepFloorHostsAlwaysDraw(t *testing.T) {
	for _, c := range []struct {
		host  string
		cores int
	}{
		{"ANGLE (Intel, Intel(R) Graphics (0x00007D45) " + d3d, 14},
		{"ANGLE (Intel, Intel(R) Graphics (0x00007D55) " + d3d, 18},
		{"ANGLE (Intel, Intel(R) UHD Graphics 770 (0x0000A780) " + d3d, 32},
	} {
		h := goodHost
		h.Cores, h.Renderer = c.cores, c.host
		var failed int
		for s := uint64(1); s <= 400; s++ {
			id, err := Draw("windows", &s, &h)
			if err != nil {
				failed++
				continue
			}
			var e map[string]any
			if err := json.Unmarshal(id.Entry, &e); err != nil {
				t.Fatal(err)
			}
			if _, claimed := e["webGl:renderer"]; !claimed {
				if n, _ := e["navigator.hardwareConcurrency"].(float64); snapCores(int(n), c.cores) < igpuFloor(c.host) && int(n) < igpuFloor(c.host) {
					t.Errorf("host %q seed %d: spare with %v cores, below the floor", c.host, s, n)
				}
			}
		}
		if failed != 0 {
			t.Errorf("host %q cores %d: %d/400 draws failed", c.host, c.cores, failed)
		}
	}
}
