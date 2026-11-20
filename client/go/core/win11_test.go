package core

import (
	"reflect"
	"testing"
)

// The Windows 11 families (specs/2026-11-20-win11-host-fonts-design.md): a host whose platformVersion is Windows 11
// lists them, since the identity then carries that version and fonts date Windows (CreepJS).
var win11Want = []string{"Segoe Fluent Icons", "Segoe UI Variable Display", "Segoe UI Variable Text",
	"Segoe UI Variable Small", "Nirmala Text", "Sans Serif Collection"}

func fontList(t *testing.T, pv string) []string {
	t.Helper()
	h := goodHost
	h.PlatformVersion = pv
	r, err := Resolve(mustDraw(t, 7, &h), h, nil)
	if err != nil {
		t.Fatal(err)
	}
	var out []string
	for _, v := range r.Config["fonts:list"].([]any) {
		out = append(out, v.(string))
	}
	return out
}

func TestWin11HostListsTheWin11Families(t *testing.T) {
	base := fontList(t, "10.0.0")
	for _, pv := range []string{"19.0.0", "13.0.0"} {
		got := fontList(t, pv)
		if want := append(append([]string{}, base...), win11Want...); !reflect.DeepEqual(got, want) {
			t.Errorf("%s: fonts:list is not the Windows 10 list plus %v:\n%v", pv, win11Want, got)
		}
	}
}

func TestWin10OrUnknownHostListsNoneOfThem(t *testing.T) {
	for _, pv := range []string{"10.0.0", "", "bad"} {
		for _, f := range fontList(t, pv) {
			for _, w := range win11Want {
				if f == w {
					t.Errorf("%q host lists %q", pv, f)
				}
			}
		}
	}
}

func TestWin11DataIsEmbedded(t *testing.T) {
	if err := loadTables(); err != nil {
		t.Fatal(err)
	}
	w := tables.fonts.Families.Windows.Win11
	if w.MinPlatformMajor != 13 || !reflect.DeepEqual(w.Families, win11Want) {
		t.Errorf("embedded win11 = %+v", w)
	}
}
