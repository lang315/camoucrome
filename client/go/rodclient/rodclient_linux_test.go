//go:build linux

package rodclient

import (
	"context"
	"os"
	"strings"
	"testing"

	camoucrome "github.com/lang315/camoucrome/client/go"
	"github.com/lang315/camoucrome/client/go/rodclient/internal/browser"
)

// cpusAllowed is the Cpus_allowed_list of the calling thread: core.Pinned sets every thread of the process.
func cpusAllowed(t *testing.T) string {
	t.Helper()
	b, err := os.ReadFile("/proc/thread-self/status")
	if err != nil {
		t.Fatal(err)
	}
	for _, l := range strings.Split(string(b), "\n") {
		if v, ok := strings.CutPrefix(l, "Cpus_allowed_list:"); ok {
			return strings.TrimSpace(v)
		}
	}
	t.Fatal("no Cpus_allowed_list")
	return ""
}

// A navigator.hardwareConcurrency claim below the CPUs pins the process while startFn runs (so Chrome inherits the mask),
// and the mask is back after; PinCPUCores=false leaves it alone.
func TestLaunchPinsDuringStart(t *testing.T) {
	before := cpusAllowed(t)
	if !strings.ContainsAny(before, ",-") {
		t.Skip("needs at least 2 allowed CPUs")
	}
	var during string
	old := startFn
	t.Cleanup(func() { startFn = old })
	startFn = func(context.Context, string, []string, map[string]string) (*browser.Proc, error) {
		during = cpusAllowed(t)
		return nil, errStub
	}
	o := camoucrome.Options{ExecutablePath: "/x/chrome", Config: map[string]any{"navigator.hardwareConcurrency": 1}}
	if _, err := Launch(context.Background(), o); err == nil {
		t.Fatal("want the stub error")
	}
	if strings.ContainsAny(during, ",-") || during == "" {
		t.Errorf("mask during startFn = %q, want one CPU", during)
	}
	if after := cpusAllowed(t); after != before {
		t.Errorf("mask after = %q, want %q restored", after, before)
	}
	no := false
	o.PinCPUCores = &no
	if _, err := Launch(context.Background(), o); err == nil {
		t.Fatal("want the stub error")
	}
	if during != before {
		t.Errorf("PinCPUCores=false: mask during startFn = %q, want %q", during, before)
	}
}
