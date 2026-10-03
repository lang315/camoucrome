//go:build !windows

package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
)

func browserArgv(executable string) []string {
	entries, _ := os.ReadDir("/proc")
	for _, e := range entries {
		raw, err := os.ReadFile(filepath.Join("/proc", e.Name(), "cmdline"))
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
			return argv
		}
	}
	return nil
}
