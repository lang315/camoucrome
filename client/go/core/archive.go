package core

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"
)

// webGpuBlocked is the first key a stamp without config_keys cannot be known to take.
const webGpuBlocked = "webGpu:blocked"

// CheckArchive fails closed on a config the browser would silently ignore (an unknown
// key only logs a warning, even under strict mode). It reads camoucrome-release.json
// beside exe: with config_keys, any config key not listed is an error; a stamp from
// before config_keys refuses webGpu:blocked; no stamp (a dev build) is allowed.
func CheckArchive(exe string, cfg map[string]any) error {
	raw, err := os.ReadFile(filepath.Join(filepath.Dir(exe), "camoucrome-release.json"))
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("core: release stamp: %w", err)
	}
	var stamp struct {
		Version    string    `json:"version"`
		ConfigKeys *[]string `json:"config_keys"`
	}
	if err := json.Unmarshal(raw, &stamp); err != nil {
		return fmt.Errorf("core: release stamp: %w", err)
	}
	if stamp.ConfigKeys == nil {
		if _, ok := cfg[webGpuBlocked]; ok {
			return fmt.Errorf("core: browser %s predates config_keys and does not know %s", stamp.Version, webGpuBlocked)
		}
		return nil
	}
	var unknown []string
	for k := range cfg {
		if !slices.Contains(*stamp.ConfigKeys, k) {
			unknown = append(unknown, k)
		}
	}
	if len(unknown) > 0 {
		slices.Sort(unknown)
		return fmt.Errorf("core: browser %s does not know config keys: %s", stamp.Version, strings.Join(unknown, ", "))
	}
	return nil
}
