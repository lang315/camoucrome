package core

import (
	"encoding/json"
	"reflect"
	"strings"
	"testing"
)

const (
	g630 = "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E92) Direct3D11 vs_5_0 ps_5_0, D3D11)"
	xe   = "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics (0x00009A49) Direct3D11 vs_5_0 ps_5_0, D3D11)"
)

// withClaim is the identity for seed 990001 with the given GPU claim and webGpu:blocked, as the pool builds it.
func withClaim(t *testing.T, claim string, blocked bool) Identity {
	t.Helper()
	id := mustDraw(t, 990001, &goodHost)
	var e map[string]any
	if err := json.Unmarshal(id.Entry, &e); err != nil {
		t.Fatal(err)
	}
	for _, k := range gpuClaimKeys {
		delete(e, k)
	}
	if claim != "" {
		e["webGl:vendor"], e["webGl2:vendor"] = "Google Inc. (X)", "Google Inc. (X)"
		e["webGl:renderer"], e["webGl2:renderer"] = claim, claim
		e["webGpu:blocked"] = blocked
	}
	id.Entry, _ = json.Marshal(e)
	return id
}

func resolveOn(t *testing.T, id Identity, renderer string) Resolved {
	t.Helper()
	h := goodHost
	h.Cores, h.Renderer = 64, renderer // the host CPU vendor stays unknown: the vendor rule is not under test
	r, err := Resolve(id, h, nil)
	if err != nil {
		t.Fatal(err)
	}
	return r
}

// testdata/golden/webgpu.json is gen.gpu_keys's webGpu:blocked for each (claim, host) pair (scripts/gen_go_core_golden.py).
func TestWebGpuBlockedMatchesPython(t *testing.T) {
	var rows []struct {
		Claim   string
		Host    *string
		Blocked bool
	}
	golden(t, "webgpu.json", &rows)
	if len(rows) < 15 {
		t.Fatalf("%d rows: the golden stopped covering the cases", len(rows))
	}
	var open int
	for _, r := range rows {
		host := ""
		if r.Host != nil {
			host = *r.Host
		}
		got := resolveOn(t, withClaim(t, r.Claim, true), host).Config["webGpu:blocked"]
		if got != r.Blocked {
			t.Errorf("claim %q on host %q: blocked %v, want %v", r.Claim, host, got, r.Blocked)
		}
		if !r.Blocked {
			open++
		}
	}
	if open != 6 {
		t.Fatalf("%d unblocked rows, want 6: the golden lost a same-family case", open)
	}
}

// An unknown host keeps every claim blocked, and an unknown host's identity is the one a stored identity resolved to before.
func TestUnknownHostStaysBlocked(t *testing.T) {
	for _, claim := range []string{g630, xe, ""} {
		id := withClaim(t, claim, true)
		r := resolveOn(t, id, "")
		if claim != "" && r.Config["webGpu:blocked"] != true {
			t.Errorf("%q on an unknown host is not blocked", claim)
		}
		// the same entry and host without the new field: byte-equal
		h := goodHost
		h.Cores = 64
		old, err := Resolve(id, h, nil)
		if err != nil || !reflect.DeepEqual(old, r) {
			t.Errorf("%q: an unknown renderer changed the resolution (%v)", claim, err)
		}
	}
}

// A Gen9 claim resolves differently only in webGpu:blocked, and only on a Gen9 host.
func TestGen9HostOnlyFlipsBlocked(t *testing.T) {
	id := withClaim(t, g630, true)
	unknown, gen9 := resolveOn(t, id, ""), resolveOn(t, id, strings.Replace(g630, "3E92", "3EA0", 1))
	if gen9.Config["webGpu:blocked"] != false || unknown.Config["webGpu:blocked"] != true {
		t.Fatal("blocked did not flip on a Gen9 host")
	}
	gen9.Config["webGpu:blocked"] = true
	if !reflect.DeepEqual(unknown, gen9) {
		t.Fatal("a Gen9 host changed more than webGpu:blocked")
	}
}

func TestParseRenderer(t *testing.T) {
	for in, ok := range map[string]bool{g630: true, "": false, "   ": false, "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)": false,
		"llvmpipe (LLVM 15)": false, "Microsoft Basic Render Driver": false, "Software Renderer": false} {
		got, err := ParseRenderer(in)
		if (err == nil) != ok || (ok && got != in) || (!ok && got != "") {
			t.Errorf("%q: %q, %v", in, got, err)
		}
	}
}

// Of the pool entries, the share whose webGpu:blocked turns false on a Gen9 host (reported in the PR). The host is Intel with
// 64 cores, so neither the cores floor nor the CPU vendor drops a claim.
func TestPoolShareUnblockedOnGen9Host(t *testing.T) {
	p, err := pool()
	if err != nil {
		t.Fatal(err)
	}
	const host = "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E92) Direct3D11 vs_5_0 ps_5_0, D3D11)"
	var claims, open, gen9Claims int
	for i, raw := range p.Entries {
		var e map[string]any
		json.Unmarshal(raw, &e)
		r, _ := e["webGl:renderer"].(string)
		if r == "" {
			continue
		}
		claims++
		if gen9DeviceID(r) {
			gen9Claims++
		}
		id := Identity{Version: poolFormat, OS: "windows", Entry: raw, Seeds: map[string]uint32{"canvas:seed": 1, "mediaDevices:seed": 2}, HostSeed: uint64(i + 1)}
		res, err := Resolve(id, Host{Cores: 64, CPUVendor: intelCPU, Renderer: host}, nil)
		if err != nil {
			t.Fatal(err)
		}
		if b, ok := res.Config["webGpu:blocked"]; ok && b == false {
			open++
		}
	}
	t.Logf("pool: %d entries, %d with a GPU claim, %d Gen9 claims, %d unblocked on a Gen9 host = %.1f%% of entries", len(p.Entries), claims, gen9Claims, open, 100*float64(open)/float64(len(p.Entries)))
	if open == 0 || open > gen9Claims {
		t.Fatalf("%d unblocked of %d Gen9 claims", open, gen9Claims)
	}
}
