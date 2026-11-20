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
			Supplemental map[string]struct {
				Families []string `json:"families"`
				Locales  []string `json:"locales"`
			} `json:"supplemental"`
		} `json:"Windows"`
	} `json:"families"`
	AliasMap     struct{ Windows map[string]string } `json:"alias_map"`
	ExtraAllowed struct{ Windows []string }          `json:"extra_allowed"`
	UniqueMap    struct{ Windows map[string]string } `json:"unique_map"`
}

// fontKeys is scripts/gen_go_core_data.py rebuild_fonts (itself gen.py
// fonts_keys with chosen = base + the groups, no host families) for the Windows claim. A group name may be an optional
// group or a supplemental pack; a name the data lacks adds nothing.
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
	// supplemental (FoD) packs follow extra_allowed in the order given (gen.py fonts_keys: pack name order); listed only
	for _, g := range groups {
		allowed = append(allowed, fam.Supplemental[g].Families...)
	}
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

// localePack is the supplemental pack whose locales match tag (equal, or a prefix plus "-", case-insensitive), in name
// order, else "" (gen.py locale_pack).
func localePack(f *fontsData, tag string) string {
	t := strings.ToLower(tag)
	names := make([]string, 0, len(f.Families.Windows.Supplemental))
	for n := range f.Families.Windows.Supplemental {
		names = append(names, n)
	}
	sort.Strings(names)
	for _, n := range names {
		for _, p := range f.Families.Windows.Supplemental[n].Locales {
			if p = strings.ToLower(p); t == p || strings.HasPrefix(t, p+"-") {
				return n
			}
		}
	}
	return ""
}

// withLocalePack is list with tag's pack listed; the packs stay in name order after the rest and before the win11
// families (gen.py with_locale_pack). Unchanged when no pack matches.
func withLocalePack(f *fontsData, list []any, tag string) []any {
	pack := localePack(f, tag)
	if pack == "" {
		return list
	}
	sup := f.Families.Windows.Supplemental
	listed, inPacks, win11 := map[string]bool{}, map[string]bool{}, map[string]bool{}
	for _, v := range list {
		listed[v.(string)] = true
	}
	for _, g := range sup {
		for _, n := range g.Families {
			inPacks[n] = true
		}
	}
	for _, n := range f.Families.Windows.Win11.Families {
		win11[n] = true
	}
	present := []string{}
	for n, g := range sup {
		all := len(g.Families) > 0
		for _, x := range g.Families {
			all = all && listed[x]
		}
		if all || n == pack {
			present = append(present, n)
		}
	}
	sort.Strings(present)
	out := []any{}
	for _, v := range list {
		if s := v.(string); !inPacks[s] && !win11[s] {
			out = append(out, v)
		}
	}
	for _, n := range present {
		for _, x := range sup[n].Families {
			out = append(out, x)
		}
	}
	for _, v := range list {
		if win11[v.(string)] {
			out = append(out, v)
		}
	}
	return out
}
