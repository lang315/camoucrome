//go:build !windows

package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
)

// browserCandidates is the argv of every browser (not renderer/gpu) process running executable, read from procRoot.
// More than one means a stray earlier run is still alive: the probe reports that instead of trusting which one it read
// (2026-10-29: a stray headless chrome made all three patchright rows of verify_sp6b_driver compare a stock-style argv).
func browserCandidates(procRoot, executable string) [][]string {
	var found [][]string
	entries, _ := os.ReadDir(procRoot)
	for _, e := range entries {
		raw, err := os.ReadFile(filepath.Join(procRoot, e.Name(), "cmdline"))
		if err != nil || len(raw) == 0 {
			continue
		}
		parts := bytes.Split(bytes.TrimSuffix(raw, []byte{0}), []byte{0})
		if len(parts) == 1 { // Chromium rewrites its cmdline into one space-joined string
			parts = bytes.Split(parts[0], []byte{' '})
		}
		if string(parts[0]) != executable {
			continue
		}
		argv := make([]string, len(parts))
		child := false
		for i, p := range parts {
			argv[i] = string(p)
			if strings.HasPrefix(argv[i], "--type=") {
				child = true
			}
		}
		if !child {
			found = append(found, argv)
		}
	}
	return found
}

func browserArgvs(executable string) [][]string { return browserCandidates("/proc", executable) }
