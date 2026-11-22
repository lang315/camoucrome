package camoucrome

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func seedsFileName(t *testing.T) string {
	raw, err := os.ReadFile("../../settings/launcher.json")
	if err != nil {
		t.Fatal(err)
	}
	var c struct {
		Seeds struct {
			File string `json:"profile_file"`
		} `json:"per_instance_seeds"`
	}
	if err := json.Unmarshal(raw, &c); err != nil {
		t.Fatal(err)
	}
	if c.Seeds.File == "" {
		t.Fatal("launcher.json names no per_instance_seeds.profile_file")
	}
	return c.Seeds.File
}

func TestProfileSeedsAreDrawnOnceAndReadBack(t *testing.T) {
	profile := filepath.Join(t.TempDir(), "profile") // the first launch makes it
	first, err := ProfileSeeds(profile, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(first) != len(SeedKeys) {
		t.Fatalf("seeds %v", first)
	}
	raw, err := os.ReadFile(filepath.Join(profile, seedsFileName(t)))
	if err != nil {
		t.Fatal(err)
	}
	var stored map[string]uint32
	if err := json.Unmarshal(raw, &stored); err != nil {
		t.Fatal(err)
	}
	for _, k := range SeedKeys {
		if stored[k] == 0 || stored[k] != first[k] {
			t.Fatalf("%s: stored %d, returned %v", k, stored[k], first[k])
		}
	}
	again, err := ProfileSeeds(profile, nil)
	if err != nil || !reflect.DeepEqual(again, first) {
		t.Fatalf("second read %v (%v) != %v", again, err, first)
	}
}

// The file the Python and Node clients write must read the same here.
func TestProfileSeedsReadAnotherClientsFileAndDrawOnlyTheMissingKeys(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, seedsFileName(t))
	if err := os.WriteFile(path, []byte(`{"canvas:seed": 5}`), 0o644); err != nil {
		t.Fatal(err)
	}
	seeds, err := ProfileSeeds(dir, nil)
	if err != nil {
		t.Fatal(err)
	}
	if seeds["canvas:seed"] != uint32(5) || seeds["mediaDevices:seed"] == nil || len(seeds) != 2 {
		t.Fatalf("seeds %v", seeds)
	}
	var stored map[string]uint32
	raw, _ := os.ReadFile(path)
	if err := json.Unmarshal(raw, &stored); err != nil || len(stored) != 2 ||
		stored["canvas:seed"] != 5 || stored["mediaDevices:seed"] != seeds["mediaDevices:seed"] {
		t.Fatalf("stored %s (%v)", raw, err)
	}
}

// An old file lacking mediaDevices:seed is rewritten with it drawn; the old
// audio:seed stays in the file but never reaches the caller.
func TestProfileSeedsRewriteOfAnOldFileKeepsAudioSeedInPlace(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, seedsFileName(t))
	if err := os.WriteFile(path, []byte(`{"canvas:seed":11,"audio:seed":22}`), 0o644); err != nil {
		t.Fatal(err)
	}
	seeds, err := ProfileSeeds(dir, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, has := seeds["audio:seed"]; has || len(seeds) != 2 || seeds["canvas:seed"] != uint32(11) {
		t.Fatalf("seeds %v", seeds)
	}
	var stored map[string]uint32
	raw, _ := os.ReadFile(path)
	if err := json.Unmarshal(raw, &stored); err != nil || len(stored) != 3 ||
		stored["audio:seed"] != 22 || stored["canvas:seed"] != 11 || stored["mediaDevices:seed"] != seeds["mediaDevices:seed"] {
		t.Fatalf("stored %s (%v)", raw, err)
	}
}

func TestSeedKeysHaveNoAudioSeed(t *testing.T) {
	if !reflect.DeepEqual(SeedKeys, []string{"canvas:seed", "mediaDevices:seed"}) {
		t.Fatalf("SeedKeys %v", SeedKeys)
	}
}

// A kept profile from before audio:seed was removed still holds it.
func TestProfileSeedsOldFileWithAudioSeedLoadsUnchanged(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, seedsFileName(t))
	raw := `{"canvas:seed":11,"audio:seed":22,"mediaDevices:seed":33}`
	if err := os.WriteFile(path, []byte(raw), 0o644); err != nil {
		t.Fatal(err)
	}
	seeds, err := ProfileSeeds(dir, nil)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(seeds, map[string]any{"canvas:seed": uint32(11), "mediaDevices:seed": uint32(33)}) {
		t.Fatalf("seeds %v", seeds)
	}
	if got, _ := os.ReadFile(path); string(got) != raw {
		t.Fatalf("file rewritten to %s", got)
	}
}

// A redraw would silently give the profile a different canvas and
// device-ID fingerprint than every earlier session showed.
func TestProfileSeedsRefuseADamagedFileRatherThanRedraw(t *testing.T) {
	for _, damaged := range []string{`{"canvas:seed"`, `[1, 2]`, `{"mediaDevices:seed": 0}`,
		`{"mediaDevices:seed": 4294967296}`, `{"mediaDevices:seed": "7"}`, `{"mediaDevices:seed": true}`, `{"mediaDevices:seed": 1.5}`, `null`} {
		dir := t.TempDir()
		path := filepath.Join(dir, seedsFileName(t))
		if err := os.WriteFile(path, []byte(damaged), 0o644); err != nil {
			t.Fatal(err)
		}
		_, err := ProfileSeeds(dir, nil)
		if err == nil || !strings.Contains(err.Error(), "camoucrome-seeds.json") {
			t.Fatalf("%s: err %v", damaged, err)
		}
		if raw, _ := os.ReadFile(path); string(raw) != damaged {
			t.Fatalf("%s: file changed to %s", damaged, raw)
		}
	}
}

func TestPollingHzRule(t *testing.T) {
	// the table the Python and Node clients assert too: one rule in three languages
	want := []uint32{125, 1000, 125, 1000, 125, 1000, 1000, 125, 1000, 125}
	for i, w := range want {
		if got := PollingHz(uint32(i + 1)); got != w {
			t.Errorf("PollingHz(%d) = %d, want %d", i+1, got, w)
		}
	}
	n := 0
	for s := uint32(1); s <= 20000; s++ {
		if PollingHz(s) == 1000 {
			n++
		}
	}
	if n < 5400 || n > 6600 {
		t.Errorf("%d of 20000 seeds give 1000 Hz, want about 30%%", n)
	}
}
