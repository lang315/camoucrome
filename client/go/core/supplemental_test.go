package core

import (
	"encoding/json"
	"testing"
)

// A pool entry's fontGroups may name a supplemental (Windows Features on Demand) pack: its families follow
// extra_allowed in fonts:list, with no faces and no alias (gen.py fonts_keys, specs/2026-11-20-supplemental-font-groups-design.md).
func TestFontKeysSupplemental(t *testing.T) {
	if err := loadTables(); err != nil {
		t.Fatal(err)
	}
	f := &tables.fonts
	jp := f.Families.Windows.Supplemental["japanese"].Families
	if len(jp) == 0 {
		t.Fatal("no japanese supplemental families in the embedded fonts data")
	}
	plain := fontKeys(f, nil)["fonts:list"].([]any)
	got := fontKeys(f, []string{"japanese"})["fonts:list"].([]any)
	if len(got) != len(plain)+len(jp) {
		t.Fatalf("len %d, want %d", len(got), len(plain)+len(jp))
	}
	for i, v := range plain {
		if got[i] != v {
			t.Fatalf("entry %d = %v, want %v", i, got[i], v)
		}
	}
	for i, n := range jp {
		if got[len(plain)+i] != n {
			t.Fatalf("tail %d = %v, want %v", i, got[len(plain)+i], n)
		}
	}
	keys := fontKeys(f, []string{"japanese"})
	for _, n := range jp {
		if _, ok := keys["fonts:alias"].(map[string]any)[n]; ok {
			t.Errorf("%s has an alias", n)
		}
	}
	if local, ok := keys["fonts:local"].([]any); ok && len(local) != len(fontKeys(f, nil)["fonts:local"].([]any)) {
		t.Errorf("fonts:local changed with a supplemental group")
	}
}

// A group name the data does not hold (an older pool beside newer data, or the reverse) adds nothing and does not panic.
func TestFontKeysUnknownGroup(t *testing.T) {
	if err := loadTables(); err != nil {
		t.Fatal(err)
	}
	plain := fontKeys(&tables.fonts, nil)["fonts:list"].([]any)
	got := fontKeys(&tables.fonts, []string{"no-such-group"})["fonts:list"].([]any)
	if len(got) != len(plain) {
		t.Fatalf("len %d, want %d", len(got), len(plain))
	}
}

// withLocalePack answers as gen.py with_locale_pack on the golden rows (scripts/gen_go_core_golden.py).
func TestWithLocalePackGolden(t *testing.T) {
	if err := loadTables(); err != nil {
		t.Fatal(err)
	}
	var rows []struct {
		Tag  string
		In   []any
		Want []any
	}
	golden(t, "locale_pack.json", &rows)
	if len(rows) < 10 {
		t.Fatalf("%d rows", len(rows))
	}
	for _, r := range rows {
		got := withLocalePack(&tables.fonts, r.In, r.Tag)
		if len(got) != len(r.Want) {
			t.Fatalf("%s: len %d, want %d", r.Tag, len(got), len(r.Want))
		}
		for i := range got {
			if got[i] != r.Want[i] {
				t.Fatalf("%s: entry %d = %v, want %v", r.Tag, i, got[i], r.Want[i])
			}
		}
	}
}

// Every pool entry lists its locale's pack when one matches, and at most one other pack (the owner's choice).
func TestPoolSupplementalInvariant(t *testing.T) {
	if err := loadTables(); err != nil {
		t.Fatal(err)
	}
	p, err := pool()
	if err != nil {
		t.Fatal(err)
	}
	sup := tables.fonts.Families.Windows.Supplemental
	drawn := 0
	for i, raw := range p.Entries {
		var e map[string]any
		if err := json.Unmarshal(raw, &e); err != nil {
			t.Fatal(err)
		}
		tag, _ := e["locale:tag"].(string)
		own := localePack(&tables.fonts, tag)
		others, hasOwn := 0, false
		for _, g := range e["fontGroups"].([]any) {
			name := g.(string)
			if _, ok := sup[name]; !ok {
				continue
			}
			if name == own {
				hasOwn = true
			} else {
				others++
			}
		}
		if own != "" && !hasOwn {
			t.Fatalf("entry %d (%s) lacks its pack %s", i, tag, own)
		}
		if others > 1 {
			t.Fatalf("entry %d (%s) lists %d non-matching packs", i, tag, others)
		}
		drawn += others
	}
	if share := float64(drawn) / float64(len(p.Entries)); share < 0.15 || share > 0.30 {
		t.Fatalf("non-matching pack share %.3f, want about 0.22", share)
	}
}
