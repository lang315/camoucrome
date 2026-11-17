//go:build !windows

package core

func probeWorkArea() ([2]int, []string) {
	return [2]int{}, []string{"work area: only read on Windows; the window step is skipped"}
}

func probePlatformVersion() (string, []string) {
	return "", []string{"platform version: only read on Windows; the entry's value stays"}
}
