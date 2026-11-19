package core

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func mustDraw(t *testing.T, seed uint64, h *Host) Identity {
	t.Helper()
	id, err := Draw("windows", &seed, h)
	if err != nil {
		t.Fatal(err)
	}
	return id
}

var goodHost = Host{Cores: 8, WorkArea: [2]int{1920, 1040}, PlatformVersion: "10.0.0", Display: &Display{"srgb", 8, false}}

func TestWindowInvariants(t *testing.T) {
	areas := [][2]int{{1366, 728}, {1920, 1040}, {2560, 1400}, {3840, 2120}}
	checked := map[float64]int{}
	for _, wa := range areas {
		for seed := uint64(1); seed <= 200; seed++ {
			h := Host{Cores: 8, WorkArea: wa}
			id := mustDraw(t, seed, &h)
			r, err := Resolve(id, h, nil)
			if err != nil {
				t.Fatalf("%v seed %d: %v", wa, seed, err)
			}
			checked[r.DPR]++
			ow, oh := int(r.Config["window.outerWidth"].(float64)), int(r.Config["window.outerHeight"].(float64))
			x, y := int(r.Config["window.screenX"].(float64)), int(r.Config["window.screenY"].(float64))
			// the window fits the host work area (physical px = css px * dpr)
			if float64(x+ow)*r.DPR > float64(wa[0]) || float64(y+oh)*r.DPR > float64(wa[1]) {
				t.Errorf("%v seed %d dpr %g: window %dx%d at %d,%d leaves the work area", wa, seed, r.DPR, ow, oh, x, y)
			}
			// 28 of 5000 pool windows are natively smaller than the minimum (gen.py keeps them too): never shrink further
			var own struct{ W, H float64 }
			var m map[string]float64
			json.Unmarshal(id.Entry, &m)
			own.W, own.H = m["window.outerWidth"], m["window.outerHeight"]
			if float64(ow) < min(float64(minWindow[0]), own.W)-2 || float64(oh) < min(float64(minWindow[1]), own.H)-2 {
				t.Errorf("%v seed %d: outer %dx%d under the minimum", wa, seed, ow, oh)
			}
			// the launch size never exceeds the claimed outer, which never exceeds the claimed avail
			if r.Window[0] > ow || r.Window[1] > oh {
				t.Errorf("%v seed %d: --window-size %v above outer %dx%d", wa, seed, r.Window, ow, oh)
			}
			if r.Position != [2]int{x, y} {
				t.Errorf("position %v != screenX/Y %d,%d", r.Position, x, y)
			}
			// snap is idempotent
			l2, o2, err := snapWindow(r.DPR, ow)
			if err != nil || l2 != r.Window[0] || o2 != ow {
				t.Errorf("snap not idempotent: %d -> %d,%d (window %d)", ow, l2, o2, r.Window[0])
			}
			if r.Cores != int(r.Config["navigator.hardwareConcurrency"].(float64)) || r.Cores > 8 {
				t.Errorf("Cores %d, config %v", r.Cores, r.Config["navigator.hardwareConcurrency"])
			}
		}
	}
	if len(checked) < 3 {
		t.Errorf("only DPRs %v were exercised", checked)
	}
}

// A float64 JSON reader (JavaScript, a map[string]any) rounds a uint64 above 2^53, so the seed is a string.
func TestHostSeedSurvivesJSON(t *testing.T) {
	id := mustDraw(t, 1, nil)
	id.HostSeed = 1<<63 + 12345
	b, _ := json.Marshal(id)
	if !strings.Contains(string(b), `"hostSeed":"9223372036854788153"`) {
		t.Errorf("hostSeed is not a string in %.200s", b)
	}
	var generic map[string]any
	json.Unmarshal(b, &generic)
	b2, _ := json.Marshal(generic) // a generic round trip keeps it
	var back Identity
	if err := json.Unmarshal(b2, &back); err != nil || back.HostSeed != id.HostSeed {
		t.Errorf("hostSeed %d after a generic round trip (err %v)", back.HostSeed, err)
	}
}

func TestResolveStable(t *testing.T) {
	id := mustDraw(t, 42, &goodHost)
	exit := &Exit{"Europe/Berlin", "DE"}
	a, err := Resolve(id, goodHost, exit)
	if err != nil {
		t.Fatal(err)
	}
	// the identity survives storage
	var back Identity
	b, _ := json.Marshal(id)
	json.Unmarshal(b, &back)
	c, err := Resolve(back, goodHost, exit)
	if err != nil || !reflect.DeepEqual(a, c) {
		t.Errorf("two resolves differ (err %v)", err)
	}
}

func TestDrawDeterministicAndRandom(t *testing.T) {
	a, b := mustDraw(t, 7, nil), mustDraw(t, 7, nil)
	if !reflect.DeepEqual(a, b) {
		t.Error("the same seed drew two identities")
	}
	if reflect.DeepEqual(a, mustDraw(t, 8, nil)) {
		t.Error("two seeds drew one identity")
	}
	x, err1 := Draw("windows", nil, nil)
	y, err2 := Draw("windows", nil, nil)
	if err1 != nil || err2 != nil || x.HostSeed == y.HostSeed {
		t.Errorf("a nil seed is not random: %v %v", err1, err2)
	}
	if _, err := Draw("macos", nil, nil); err == nil || !strings.Contains(err.Error(), "windows") {
		t.Errorf("an OS without a pool: %v", err)
	}
}

func TestDrawSeedsNonZero(t *testing.T) {
	for s := uint64(0); s < 300; s++ {
		id := mustDraw(t, s, nil)
		if id.Seeds["canvas:seed"] == 0 || id.Seeds["mediaDevices:seed"] == 0 || len(id.Seeds) != 2 {
			t.Fatalf("seed %d: %v", s, id.Seeds)
		}
	}
}

func TestExitEdgeCases(t *testing.T) {
	id := mustDraw(t, 5, &goodHost)
	for _, tc := range []struct {
		exit        Exit
		wantTag     string
		wantWarning bool
	}{
		{Exit{"Europe/Berlin", "DE"}, "de-DE", false},
		{Exit{"Europe/Berlin", "de"}, "de-DE", false}, // any case
		{Exit{"Europe/Berlin", ""}, "en-US", true},
		{Exit{"Europe/Berlin", "zz"}, "en-US", true},
		{Exit{"UTC", "US"}, "en-US", false},
	} {
		r, err := Resolve(id, goodHost, &tc.exit)
		if err != nil {
			t.Fatalf("%+v: %v", tc.exit, err)
		}
		if r.Config["locale:tag"] != tc.wantTag || r.Config["navigator.language"] != tc.wantTag ||
			r.Config["timezone:id"] != tc.exit.Timezone || r.Config["webrtc:ipHandlingPolicy"] != "disable_non_proxied_udp" {
			t.Errorf("%+v: %v %v %v", tc.exit, r.Config["locale:tag"], r.Config["timezone:id"], r.Config["webrtc:ipHandlingPolicy"])
		}
		has := false
		for _, w := range r.Warnings {
			has = has || strings.Contains(w, "no locale row")
		}
		if has != tc.wantWarning {
			t.Errorf("%+v: warnings %v", tc.exit, r.Warnings)
		}
	}
	// A zone the fork cannot take is a silent no-op there (it keeps the host's REAL zone, even under strict), so refuse here.
	for _, tz := range []string{"Not/AZone", "UTC+2", "Etc/GMT-3", "Etc/GMT+5", "US/Pacific", "EST5EDT", "", "europe/berlin", "Asia/"} {
		if _, err := Resolve(id, goodHost, &Exit{tz, "DE"}); err == nil {
			t.Errorf("timezone %q was accepted", tz)
		}
	}
	if _, err := Resolve(id, goodHost, &Exit{"Europe/Berlin", "DE"}); err != nil {
		t.Error(err)
	}
}

func TestResolveWithoutExitKeepsTheEntryLocale(t *testing.T) {
	r, err := Resolve(mustDraw(t, 9, nil), goodHost, nil)
	if err != nil {
		t.Fatal(err)
	}
	if r.Config["locale:tag"] == nil || r.Config["timezone:id"] == nil || r.Config["webrtc:ipHandlingPolicy"] != nil {
		t.Errorf("tag %v zone %v webrtc %v", r.Config["locale:tag"], r.Config["timezone:id"], r.Config["webrtc:ipHandlingPolicy"])
	}
}

func TestUnknownHostSkipsStepsWithWarnings(t *testing.T) {
	r, err := Resolve(mustDraw(t, 3, nil), Host{}, nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"cores unknown", "platform version unknown", "work area unknown", "display unknown"} {
		found := false
		for _, w := range r.Warnings {
			found = found || strings.Contains(w, want)
		}
		if !found {
			t.Errorf("no %q warning in %v", want, r.Warnings)
		}
	}
	if r.Window[0] == 0 || r.DPR == 0 {
		t.Errorf("window %v dpr %g", r.Window, r.DPR)
	}
}

func TestSmallScreen(t *testing.T) {
	small := Host{Cores: 4, WorkArea: [2]int{800, 500}}
	id := mustDraw(t, 1, nil)
	var dpr float64
	json.Unmarshal(id.Entry, &struct {
		DPR *float64 `json:"dpr"`
	}{&dpr})
	if _, err := Resolve(mustDraw(t, 1, nil), Host{Cores: 4, WorkArea: [2]int{800, 500}}, nil); dpr > 1 && err == nil {
		t.Error("a 800x500 work area at DPR > 1 resolved")
	}
	// DPR 2 on 800x500: no window of 800x500 css px fits
	r := map[string]any{}
	json.Unmarshal(id.Entry, &r)
	r["dpr"] = 2.0
	b, _ := json.Marshal(r)
	id.Entry = b
	_, err := Resolve(id, small, nil)
	if err == nil || !strings.Contains(err.Error(), "800") || !strings.Contains(err.Error(), "2") {
		t.Errorf("want an error naming the work area and DPR, got %v", err)
	}
	// Draw with that host skips what cannot fit: whatever it returns holds the window
	for s := uint64(0); s < 30; s++ {
		h := Host{WorkArea: [2]int{1000, 700}}
		d, err := Draw("windows", &s, &h)
		if err != nil {
			continue
		}
		if _, err := Resolve(d, h, nil); err != nil {
			t.Errorf("Draw returned an identity that cannot launch on its host: %v", err)
		}
	}
	// a host of 400x300 holds nothing
	if _, err := Draw("windows", nil, &Host{WorkArea: [2]int{400, 300}}); err == nil {
		t.Error("Draw succeeded on a 400x300 work area")
	}
}

func TestGPUClaimIsTheFiveKeysAndNoGeo(t *testing.T) {
	big := goodHost
	big.Cores = 64 // above every iGPU floor: the claim stays
	for s := uint64(0); s < 100; s++ {
		id := mustDraw(t, s, &goodHost) // entries that hold the minimum window here
		r, err := Resolve(id, big, &Exit{"Europe/Berlin", "DE"})
		if err != nil {
			t.Fatal(err)
		}
		for _, k := range []string{"webGl:vendor", "webGl:renderer", "webGl2:vendor", "webGl2:renderer"} {
			if v, ok := r.Config[k].(string); !ok || v == "" {
				t.Fatalf("seed %d: %s = %v", s, k, r.Config[k])
			}
		}
		if r.Config["webGpu:blocked"] != true {
			t.Fatalf("seed %d: webGpu:blocked = %v", s, r.Config["webGpu:blocked"])
		}
		for k := range r.Config {
			if strings.HasPrefix(k, "geolocation:") ||
				(strings.HasPrefix(k, "webGl") && (strings.HasSuffix(k, ":parameters") || strings.HasSuffix(k, ":supportedExtensions") || strings.HasSuffix(k, ":shaderPrecisionFormats"))) {
				t.Fatalf("seed %d sets %s", s, k)
			}
		}
		for _, a := range Argv(r, LaunchOpts{}) {
			if strings.HasPrefix(a, "--proxy") || strings.HasPrefix(a, "--remote-debugging") {
				t.Fatalf("flag %s", a)
			}
		}
	}
}

// A host snap below the claimed iGPU's floor drops the five GPU keys (gen.py from_pool); a host above it keeps them.
func TestHostBelowIGPUFloorDropsTheClaim(t *testing.T) {
	small, big := goodHost, goodHost
	small.Cores, big.Cores = 4, 64
	dropped, kept := 0, 0
	for s := uint64(0); s < 300; s++ {
		id := mustDraw(t, s, &goodHost)
		var e map[string]any
		if err := json.Unmarshal(id.Entry, &e); err != nil {
			t.Fatal(err)
		}
		floor := igpuFloor(e["webGl:renderer"].(string))
		rs, err := Resolve(id, small, nil)
		if err != nil {
			t.Fatal(err)
		}
		rb, err := Resolve(id, big, nil)
		if err != nil {
			t.Fatal(err)
		}
		if _, ok := rb.Config["webGl:renderer"]; !ok {
			t.Fatalf("seed %d: a 64-core host dropped the claim", s)
		}
		_, has := rs.Config["webGl:renderer"]
		if floor > 4 {
			if has || len(rs.Warnings) == 0 {
				t.Fatalf("seed %d: floor %d, 4 cores, claim kept = %v", s, floor, has)
			}
			for _, k := range gpuClaimKeys {
				if _, ok := rs.Config[k]; ok {
					t.Fatalf("seed %d: %s survived the drop", s, k)
				}
			}
			dropped++
		} else {
			if !has {
				t.Fatalf("seed %d: floor %d, 4 cores, claim dropped", s, floor)
			}
			kept++
		}
	}
	if dropped < 20 || kept < 20 {
		t.Fatalf("dropped %d, kept %d: the test did not cover both sides", dropped, kept)
	}
}

// A Gen9 claim (UHD 620, 0x3EA0) has a floor in the embedded table, and a host snap below it drops the claim.
func TestGen9FloorDropsTheClaim(t *testing.T) {
	const uhd620 = "ANGLE (Intel, Intel(R) UHD Graphics 620 (0x00003EA0) Direct3D11 vs_5_0 ps_5_0, D3D11)"
	if f := igpuFloor(uhd620); f < 4 {
		t.Fatalf("UHD 620 floor %d, want >= 4", f)
	}
	small := goodHost
	small.Cores = 2
	dropped := 0
	for s := uint64(0); s < 1000; s++ {
		id := mustDraw(t, s, &goodHost)
		var e map[string]any
		if err := json.Unmarshal(id.Entry, &e); err != nil {
			t.Fatal(err)
		}
		r, _ := e["webGl:renderer"].(string)
		if igpuFloor(r) <= 2 || !strings.Contains(r, "Intel(R) UHD Graphics") && !strings.Contains(r, "Intel(R) HD Graphics") {
			continue
		}
		rs, err := Resolve(id, small, nil)
		if err != nil {
			t.Fatal(err)
		}
		if _, has := rs.Config["webGl:renderer"]; has {
			t.Fatalf("seed %d: %s kept on a 2-core host", s, r)
		}
		dropped++
	}
	if dropped < 5 {
		t.Fatalf("dropped %d: the test covered too few Gen9 claims", dropped)
	}
}

// An identity stored before the GPU claim has an Entry without the keys: it keeps the host's GPU.
func TestResolveEntryWithoutGPUKeys(t *testing.T) {
	id := mustDraw(t, 3, nil)
	var e map[string]json.RawMessage
	if err := json.Unmarshal(id.Entry, &e); err != nil {
		t.Fatal(err)
	}
	for _, k := range []string{"webGl:vendor", "webGl:renderer", "webGl2:vendor", "webGl2:renderer", "webGpu:blocked"} {
		delete(e, k)
	}
	id.Entry, _ = json.Marshal(e)
	r, err := Resolve(id, goodHost, nil)
	if err != nil {
		t.Fatal(err)
	}
	for k := range r.Config {
		if strings.HasPrefix(k, "webGl") {
			t.Fatalf("old entry sets %s", k)
		}
	}
}

func TestDrawnConfigKeysAreDeclared(t *testing.T) {
	b, err := os.ReadFile("../../../settings/keys.json")
	if err != nil {
		t.Skip("not inside the repo")
	}
	var kf struct{ Keys []struct{ Key string } }
	json.Unmarshal(b, &kf)
	declared := map[string]bool{}
	for _, k := range kf.Keys {
		declared[k.Key] = true
	}
	r, err := Resolve(mustDraw(t, 12, nil), goodHost, &Exit{"Asia/Tokyo", "JP"})
	if err != nil {
		t.Fatal(err)
	}
	for k := range r.Config {
		if !declared[k] {
			t.Errorf("config key %q is not in settings/keys.json", k)
		}
	}
}

// --- cross-release fixtures -------------------------------------------------
//
// testdata/stored/*.json are identities written once, with the host, exit and
// the Resolved they gave. A new release must resolve every one byte for byte
// the same, or an account "changes device". DO NOT REGENERATE OR EDIT THESE
// without the orchestrator's OK: a failure here is the bug, not the fixture.
// (STORED_REGEN=1 writes any missing file, never overwrites one.)

type stored struct {
	Identity Identity
	Host     Host
	Exit     *Exit
	Resolved Resolved
}

func TestStoredFixtures(t *testing.T) {
	cases := []struct {
		name string
		seed uint64
		host Host
		exit *Exit
	}{
		{"id-1080p", 101, Host{8, [2]int{1920, 1040}, "10.0.0", &Display{"srgb", 8, false}, "", ""}, &Exit{"Asia/Jakarta", "ID"}},
		{"us-laptop", 202, Host{4, [2]int{1366, 728}, "13.0.0", nil, "", ""}, &Exit{"America/New_York", "US"}},
		{"de-4k", 303, Host{16, [2]int{3840, 2120}, "15.0.0", &Display{"p3", 10, true}, "", ""}, &Exit{"Europe/Berlin", "DE"}},
		{"ph-noexit", 404, Host{6, [2]int{2560, 1400}, "10.0.0", &Display{"srgb", 8, false}, "", ""}, nil},
		{"unknown-host", 505, Host{}, &Exit{"Asia/Bangkok", "TH"}},
	}
	for _, c := range cases {
		path := filepath.Join("testdata", "stored", c.name+".json")
		if _, err := os.Stat(path); os.IsNotExist(err) && os.Getenv("STORED_REGEN") == "1" {
			id := mustDraw(t, c.seed, &c.host)
			r, err := Resolve(id, c.host, c.exit)
			if err != nil {
				t.Fatal(err)
			}
			b, _ := json.MarshalIndent(stored{id, c.host, c.exit, r}, "", " ")
			os.MkdirAll(filepath.Dir(path), 0o755)
			if err := os.WriteFile(path, append(b, '\n'), 0o644); err != nil {
				t.Fatal(err)
			}
		}
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatalf("%s: %v (STORED_REGEN=1 writes a missing one)", c.name, err)
		}
		var s stored
		if err := json.Unmarshal(raw, &s); err != nil {
			t.Fatal(err)
		}
		got, err := Resolve(s.Identity, s.Host, s.Exit)
		if err != nil {
			t.Fatalf("%s: %v", c.name, err)
		}
		gb, _ := json.Marshal(got)
		wb, _ := json.Marshal(s.Resolved)
		if string(gb) != string(wb) {
			t.Errorf("%s: the stored identity resolves differently now (an account would change device)\n got %.300s\nwant %.300s", c.name, gb, wb)
		}
	}
	if m, _ := filepath.Glob("testdata/stored/*.json"); len(m) != 5 {
		t.Errorf("%d stored fixtures, want 5", len(m))
	}
}
