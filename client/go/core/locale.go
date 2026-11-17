package core

import (
	"fmt"
	"regexp"
	"strings"
	"time"
)

// zoneAreas are the IANA areas a zone name may start with. Etc/* (Etc/GMT-3
// is a fixed offset the fork and a page would show differently), the legacy
// names (US/Pacific, EST5EDT, GB) and a bare offset (UTC+2) are refused:
// the fork keeps the REAL host zone when it cannot take the id, even under
// CAMOU_CONFIG_STRICT=1, so a zone that gets that far is a silent no-op.
var zoneAreas = map[string]bool{"Africa": true, "America": true, "Antarctica": true, "Arctic": true, "Asia": true,
	"Atlantic": true, "Australia": true, "Europe": true, "Indian": true, "Pacific": true}

var zoneForm = regexp.MustCompile(`^[A-Z][A-Za-z_]+/[A-Za-z0-9_+-]+(/[A-Za-z0-9_+-]+)?$`)

// validZone accepts "UTC" and an Area/Location name that Go's embedded tzdata knows.
func validZone(name string) error {
	if name == "UTC" {
		return nil
	}
	area, _, _ := strings.Cut(name, "/")
	if !zoneForm.MatchString(name) || !zoneAreas[area] {
		return fmt.Errorf("timezone %q is not a canonical IANA Area/Location name (Etc/*, legacy names and offsets are refused)", name)
	}
	if _, err := time.LoadLocation(name); err != nil {
		return fmt.Errorf("timezone %q is not in the IANA database: %w", name, err)
	}
	return nil
}

// localeFor is the locale of a country (ISO 3166-1 alpha-2, any case): the
// country table, else en-US and a warning.
func localeFor(country string) (tag string, warning string) {
	if t, ok := tables.country[strings.ToUpper(country)]; ok {
		return t, ""
	}
	return "en-US", fmt.Sprintf("country %q has no locale row: en-US", country)
}

// languagesFor is gen.py from_pool's list for a locale: [tag] or [tag, primary].
func languagesFor(tag string) []any {
	if primary, _, found := strings.Cut(tag, "-"); found {
		return []any{tag, primary}
	}
	return []any{tag}
}

// voiceList is gen.py voices_keys("Windows", tag): the locale's language-pack
// row, else the same language's first row (file order), else en-US, then the
// remote voices.
func voiceList(tag string) ([]any, error) {
	t := &tables
	row, ok := t.voices[tag]
	if !ok {
		lang, _, _ := strings.Cut(tag, "-")
		for _, k := range t.voiceTags {
			if l, _, _ := strings.Cut(k, "-"); l == lang {
				row, ok = t.voices[k], true
				break
			}
		}
	}
	if !ok {
		row = t.voices["en-US"]
	}
	var list []any
	if err := jsonUnmarshal(row, &list); err != nil {
		return nil, err
	}
	return append(list, t.remote...), nil
}

// displayFlags is gen.py display_flags; the warning is "" when there is none.
func displayFlags(d *Display) (flags []string, warning string) {
	if d == nil {
		return nil, "display unknown: gamut, bit depth and HDR keep the host's values"
	}
	if d.Gamut != "srgb" {
		flags = []string{"--force-color-profile=srgb"}
	}
	var left []string
	if d.ColorBits != 8 {
		left = append(left, "10-bit")
	}
	if d.HDR {
		left = append(left, "hdr")
	}
	if len(left) > 0 {
		warning = fmt.Sprintf("host display is %s: no lever hides it, every profile shows it", strings.Join(left, ", "))
	}
	return flags, warning
}

func validDisplay(d *Display) bool {
	return d != nil && (d.Gamut == "srgb" || d.Gamut == "p3" || d.Gamut == "rec2020") && (d.ColorBits == 8 || d.ColorBits == 10)
}
