package core

import (
	"encoding/json"
	"fmt"
	"os"
	"reflect"
	"slices"
	"strings"
	"testing"
)

func golden(t *testing.T, name string, v any) {
	t.Helper()
	b, err := os.ReadFile("testdata/golden/" + name)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(b, v); err != nil {
		t.Fatal(err)
	}
}

// norm round-trips through JSON so a Go value compares with a decoded fixture.
func norm(t *testing.T, v any) any {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	var out any
	json.Unmarshal(b, &out)
	return out
}

// Fixtures come from scripts/gen_go_core_golden.py, which runs gen.py itself.
func TestGoldenDeterministic(t *testing.T) {
	if err := loadTables(); err != nil {
		t.Fatal(err)
	}
	t.Run("cores", func(t *testing.T) {
		var rows []struct{ Cores, Claim, Want int }
		golden(t, "cores.json", &rows)
		if len(rows) < 400 {
			t.Fatalf("%d rows", len(rows))
		}
		for _, r := range rows {
			if got := snapCores(r.Claim, r.Cores); got != r.Want {
				t.Errorf("claim %d on %d cores: %d, want %d", r.Claim, r.Cores, got, r.Want)
			}
		}
	})
	t.Run("snap window", func(t *testing.T) {
		var rows map[string][][2]int
		golden(t, "snap.json", &rows)
		if len(rows) != 7 {
			t.Fatalf("%d DPRs, want 7", len(rows))
		}
		for dprs, list := range rows {
			var dpr float64
			fmt.Sscanf(dprs, "%g", &dpr)
			for i, want := range list {
				l, o, err := snapWindow(dpr, 600+i)
				if err != nil || l != want[0] || o != want[1] {
					t.Fatalf("dpr %g outer %d: %d,%d %v, want %v", dpr, 600+i, l, o, err, want)
				}
			}
		}
	})
	t.Run("display flags", func(t *testing.T) {
		var rows []struct {
			Display *Display
			Flags   []string
			Warning *string
		}
		golden(t, "display.json", &rows)
		for _, r := range rows {
			flags, warn := displayFlags(r.Display)
			want := ""
			if r.Warning != nil {
				want = *r.Warning
			}
			if !slices.Equal(flags, r.Flags) || warn != want {
				t.Errorf("%+v: got %v %q, want %v %q", r.Display, flags, warn, r.Flags, want)
			}
		}
	})
	t.Run("voices", func(t *testing.T) {
		var rows []struct {
			Tag  string
			List []any
		}
		golden(t, "voices.json", &rows)
		for _, r := range rows {
			got, err := voiceList(r.Tag)
			if err != nil || !reflect.DeepEqual(got, r.List) {
				t.Errorf("voices for %q differ (err %v, %d vs %d rows)", r.Tag, err, len(got), len(r.List))
			}
		}
	})
	t.Run("exit locale", func(t *testing.T) {
		var rows []struct {
			Country, Tag string
			Languages    []any
			Voices       []any
		}
		golden(t, "exit.json", &rows)
		for _, r := range rows {
			tag, w := localeFor(r.Country)
			if tag != r.Tag || w != "" {
				t.Errorf("%s: %q %q, want %q", r.Country, tag, w, r.Tag)
			}
			if !reflect.DeepEqual(languagesFor(tag), r.Languages) {
				t.Errorf("%s: languages %v, want %v", r.Country, languagesFor(tag), r.Languages)
			}
			if v, _ := voiceList(tag); !reflect.DeepEqual(v, r.Voices) {
				t.Errorf("%s: voices differ", r.Country)
			}
		}
	})
	t.Run("from_pool runs", func(t *testing.T) {
		var runs []struct {
			Seed  int
			Entry map[string]any
			Host  struct {
				Cores           int
				PlatformVersion string
				Display         *Display
			}
			Config map[string]any
			Args   []string
			DPR    float64
		}
		golden(t, "from_pool.json", &runs)
		for _, run := range runs {
			entry, _ := json.Marshal(run.Entry)
			id := Identity{Version: 1, OS: "windows", Entry: entry, Seeds: map[string]uint32{"canvas:seed": 1, "mediaDevices:seed": 2}, HostSeed: 1}
			r, err := Resolve(id, Host{Cores: run.Host.Cores, PlatformVersion: run.Host.PlatformVersion, Display: run.Host.Display}, nil)
			if err != nil {
				t.Fatal(err)
			}
			for _, k := range []string{"canvas:seed", "mediaDevices:seed", "timezone:id", "window.screenX", "window.screenY", "window.outerWidth", "window.outerHeight"} {
				delete(r.Config, k) // the window is host-fitted and snapped in Go; the entry's own is the golden's input
				delete(run.Config, k)
			}
			if r.DPR != run.DPR || !slices.Equal(r.Args, run.Args) {
				t.Errorf("seed %d: dpr/args %v %v, want %v %v", run.Seed, r.DPR, r.Args, run.DPR, run.Args)
			}
			got := norm(t, r.Config).(map[string]any)
			for k, want := range run.Config {
				if !reflect.DeepEqual(got[k], want) {
					t.Errorf("seed %d key %s: %.80v, want %.80v", run.Seed, k, got[k], want)
				}
			}
			for k := range got {
				if _, ok := run.Config[k]; !ok && !strings.HasPrefix(k, "webrtc") {
					t.Errorf("seed %d: Go sets %s, Python does not", run.Seed, k)
				}
			}
		}
	})
}
