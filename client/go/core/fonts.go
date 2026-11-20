package core

import (
	"sort"
	"strings"
)

type fontsData struct {
	Families struct {
		Windows struct {
			List   []string `json:"list"`
			Base   []string `json:"base"`
			Groups map[string]struct {
				Families []string `json:"families"`
			} `json:"groups"`
			PsNamesAreCSSFamilies bool `json:"ps_names_are_css_families"`
			UniqueNames           map[string]struct {
				Family string `json:"family"`
			} `json:"unique_names"`
			Faces [][]string `json:"faces"`
			Win11 struct {
				MinPlatformMajor int      `json:"min_platform_major"`
				Families         []string `json:"families"`
			} `json:"win11"`
		} `json:"Windows"`
	} `json:"families"`
	AliasMap     struct{ Windows map[string]string } `json:"alias_map"`
	ExtraAllowed struct{ Windows []string }          `json:"extra_allowed"`
	UniqueMap    struct{ Windows map[string]string } `json:"unique_map"`
}

// fontKeys is scripts/gen_go_core_data.py rebuild_fonts (itself gen.py
// fonts_keys with chosen = base + the groups, no host families) for the Windows claim.
func fontKeys(f *fontsData, groups []string) map[string]any {
	fam := &f.Families.Windows
	chosen := map[string]bool{}
	for _, n := range fam.Base {
		chosen[n] = true
	}
	for _, g := range groups {
		for _, n := range fam.Groups[g].Families {
			chosen[n] = true
		}
	}
	families := []string{}
	have := map[string]bool{}
	hidden := map[string]bool{}
	for _, n := range fam.List {
		if chosen[n] {
			families = append(families, n)
			have[n] = true
		} else {
			hidden[n] = true
		}
	}
	alias := map[string]any{}
	for k, v := range f.AliasMap.Windows {
		if !hidden[k] {
			alias[k] = v
		}
	}
	allowed := append(append([]string{}, families...), f.ExtraAllowed.Windows...)
	// shortcut: this branch is dead for Windows (ps_names_are_css_families is false in fonts.json); map order below
	// is unspecified, so if that changes it must iterate the sorted names (the unique_names order of gen.py is the file's)
	if fam.PsNamesAreCSSFamilies {
		names := make([]string, 0, len(fam.UniqueNames))
		for name, v := range fam.UniqueNames {
			names = append(names, name)
			target := v.Family
			if a, ok := alias[v.Family]; ok {
				target = a.(string)
			}
			if target != name {
				alias[name] = target
			}
		}
		sort.Strings(names)
		allowed = append(allowed, names...)
	}
	out := map[string]any{"fonts:list": toAny(allowed), "fonts:alias": alias}
	if len(fam.Faces) > 0 {
		local := []any{}
		for _, face := range fam.Faces {
			if have[face[2]] {
				local = append(local, strings.Join(face, "\t"))
			}
		}
		out["fonts:local"] = local
	}
	aliasLocal := map[string]any{}
	for k, v := range f.UniqueMap.Windows {
		if u, ok := fam.UniqueNames[k]; !ok || !hidden[u.Family] {
			aliasLocal[k] = v
		}
	}
	out["fonts:aliasLocal"] = aliasLocal
	return out
}

func toAny(s []string) []any {
	out := make([]any, len(s))
	for i, v := range s {
		out[i] = v
	}
	return out
}
