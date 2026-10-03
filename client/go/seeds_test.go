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
	if err := os.WriteFile(path, []byte(`{"canvas:seed": 5, "audio:seed": 4294967295}`), 0o644); err != nil {
		t.Fatal(err)
	}
	seeds, err := ProfileSeeds(dir, nil)
	if err != nil {
		t.Fatal(err)
	}
	if seeds["canvas:seed"] != uint32(5) || seeds["audio:seed"] != uint32(0xFFFFFFFF) || seeds["mediaDevices:seed"] == nil {
		t.Fatalf("seeds %v", seeds)
	}
	var stored map[string]uint32
	raw, _ := os.ReadFile(path)
	if err := json.Unmarshal(raw, &stored); err != nil || stored["mediaDevices:seed"] != seeds["mediaDevices:seed"] {
		t.Fatalf("stored %s (%v)", raw, err)
	}
}

// A redraw would silently give the profile a different canvas, audio and
// device-ID fingerprint than every earlier session showed.
func TestProfileSeedsRefuseADamagedFileRatherThanRedraw(t *testing.T) {
	for _, damaged := range []string{`{"canvas:seed"`, `[1, 2]`, `{"audio:seed": 0}`,
		`{"audio:seed": 4294967296}`, `{"audio:seed": "7"}`, `{"audio:seed": true}`, `{"audio:seed": 1.5}`} {
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
