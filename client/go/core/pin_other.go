//go:build !linux && !windows

package core

// shortcut: macOS has no CPU affinity API, so a claim below the host's cores is not enforced there; revisit if a macOS host is supported.
func init() {
	affinityGet = func() ([]int, error) { return nil, nil }
	affinitySet = func([]int) error { return nil }
}
