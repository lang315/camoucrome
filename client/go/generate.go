package camoucrome

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os/exec"
)

// Generated is what `python -m camoucrome.gen` prints: the config and the
// launcher options that go with it. The generator lives in Python (one
// implementation, tested once); Go execs it.
type Generated struct {
	Config map[string]any `json:"config"`
	Launch struct {
		Window [2]int  `json:"window"`
		DPR    float64 `json:"dpr"`
	} `json:"launch"`
}

// ParseGenerated decodes the generator's output and folds it into Options
// (Config, Window, DPR); every other field is left for the caller.
func ParseGenerated(raw []byte) (Options, error) {
	var g Generated
	if err := json.Unmarshal(raw, &g); err != nil {
		return Options{}, fmt.Errorf("generator output: %w", err)
	}
	if len(g.Config) == 0 {
		return Options{}, fmt.Errorf("generator output has no config")
	}
	return Options{Config: g.Config, Window: g.Launch.Window, DPR: g.Launch.DPR}, nil
}

// Generate runs `python -m camoucrome.gen` (the Python client must be
// installed in that interpreter) with the given OS ("windows", "macos",
// "linux" or "" for any), the required IANA timezone, and an optional
// locale. seed < 0 means unseeded.
func Generate(python, osName, timezone, locale string, seed int) (Options, error) {
	args := []string{"-m", "camoucrome.gen", "--timezone", timezone}
	if osName != "" {
		args = append(args, "--os", osName)
	}
	if locale != "" {
		args = append(args, "--locale", locale)
	}
	if seed >= 0 {
		args = append(args, "--seed", fmt.Sprint(seed))
	}
	cmd := exec.Command(python, args...)
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		return Options{}, fmt.Errorf("camoucrome.gen: %w: %s", err, stderr.String())
	}
	return ParseGenerated(out)
}
