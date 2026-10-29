//go:build !windows

package main

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

const exe = "/opt/x/chrome"

func fakeProc(t *testing.T, procs map[string][]string) string {
	root := t.TempDir()
	for pid, argv := range procs {
		if err := os.Mkdir(filepath.Join(root, pid), 0o755); err != nil {
			t.Fatal(err)
		}
		raw := []byte{}
		for _, a := range argv {
			raw = append(append(raw, a...), 0)
		}
		if err := os.WriteFile(filepath.Join(root, pid, "cmdline"), raw, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	return root
}

func TestOneBrowserIsOneCandidateChildrenAreIgnored(t *testing.T) {
	root := fakeProc(t, map[string][]string{
		"10": {exe, "--headless=new"},
		"11": {exe, "--type=renderer"},
		"12": {"/usr/bin/python3", "-m", "x"},
	})
	got := browserCandidates(root, exe)
	if !reflect.DeepEqual(got, [][]string{{exe, "--headless=new"}}) {
		t.Fatalf("candidates = %v", got)
	}
}

func TestAStrayMainProcessIsASecondCandidate(t *testing.T) {
	root := fakeProc(t, map[string][]string{
		"10": {exe, "--headless", "--remote-debugging-port=0", "about:blank"},
		"20": {exe, "--headless=new"},
	})
	if got := browserCandidates(root, exe); len(got) != 2 {
		t.Fatalf("want 2 candidates, got %v", got)
	}
}

func TestMissingProcIsNoCandidate(t *testing.T) {
	if got := browserCandidates(filepath.Join(t.TempDir(), "missing"), exe); len(got) != 0 {
		t.Fatalf("candidates = %v", got)
	}
}
