//go:build linux

package core

import (
	"os/exec"
	"regexp"
	"slices"
	"testing"
)

func childCPUs(t *testing.T) string {
	t.Helper()
	out, err := exec.Command("cat", "/proc/self/status").Output()
	if err != nil {
		t.Fatal(err)
	}
	return string(regexp.MustCompile(`Cpus_allowed_list:\s*(\S+)`).FindSubmatch(out)[1])
}

func TestPinnedRestores(t *testing.T) {
	before, err := affinityGet()
	if err != nil || len(before) < 2 {
		t.Skipf("needs 2 allowed CPUs: %v %v", before, err)
	}
	orig := childCPUs(t)
	var during string
	if err := Pinned(1, func() error { during = childCPUs(t); return nil }); err != nil {
		t.Fatal(err)
	}
	if regexp.MustCompile(`[-,]`).MatchString(during) {
		t.Errorf("child saw %q, want exactly 1 CPU", during)
	}
	after, _ := affinityGet()
	if !slices.Equal(before, after) || childCPUs(t) != orig {
		t.Errorf("mask not restored: %v -> %v", before, after)
	}
}
