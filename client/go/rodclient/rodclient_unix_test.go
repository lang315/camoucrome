//go:build unix

package rodclient

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"sync"
	"syscall"
	"testing"

	camoucrome "github.com/lang315/camoucrome/client/go"
)

// A fake browser: answers every request with one reply carrying the union of
// the fields rod reads, and appends each request's method to $FAKE_LOG.
const fake = `#!/usr/bin/env python3
import json, os, sys
r, w = os.fdopen(3, "rb", 0), os.fdopen(4, "wb", 0)
log = open(os.environ["FAKE_LOG"], "a")
buf = b""
while True:
    d = r.read(1 << 20)
    if not d:
        sys.exit(0)
    buf += d
    while b"\0" in buf:
        m, buf = buf.split(b"\0", 1)
        q = json.loads(m)
        log.write(q["method"] + "\n"); log.flush()
        res = {"targetId": "T", "sessionId": "S", "frameId": "F"}
        w.write(json.dumps({"id": q["id"], "result": res}).encode() + b"\0")
        if q["method"] == "Browser.close":
            sys.exit(0)
`

func TestLaunchNewPageClose(t *testing.T) {
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not on PATH")
	}
	dir := t.TempDir()
	exe := filepath.Join(dir, "fake-browser")
	if err := os.WriteFile(exe, []byte(fake), 0o755); err != nil {
		t.Fatal(err)
	}
	logPath := filepath.Join(dir, "methods.log")
	t.Setenv("FAKE_LOG", logPath)

	b, err := Launch(context.Background(), camoucrome.Options{ExecutablePath: exe})
	if err != nil {
		t.Fatal(err)
	}
	var mu sync.Mutex
	var sent []string
	b.OnSend(func(m []byte) { mu.Lock(); sent = append(sent, string(m)); mu.Unlock() })
	pid, owned := b.proc.Pid, append([]string{}, b.owned...)
	if len(owned) != 2 {
		t.Fatalf("owned %v", owned)
	}
	inTemp(t, "crash dir", owned[0], "camoucrome-crash-")
	inTemp(t, "profile dir", owned[1], "camoucrome-")
	if !contains(b.Argv(), "--user-data-dir="+owned[1]) {
		t.Errorf("argv does not name the owned profile %s: %v", owned[1], b.Argv())
	}
	if !strings.Contains(strings.Join(b.Argv(), " "), "--remote-debugging-pipe") {
		t.Fatalf("argv %v", b.Argv())
	}
	if _, err := b.NewPage(context.Background()); err != nil {
		t.Fatal(err)
	}
	mu.Lock()
	if len(sent) == 0 {
		t.Error("OnSend saw nothing")
	}
	mu.Unlock()

	if err := b.Close(); err != nil {
		t.Fatal(err)
	}
	if err := b.Close(); err != nil {
		t.Fatalf("second Close: %v", err)
	}
	if err := syscall.Kill(pid, 0); err != syscall.ESRCH {
		t.Fatalf("process %d still there (%v)", pid, err)
	}
	for _, p := range owned {
		if _, err := os.Stat(p); !os.IsNotExist(err) {
			t.Errorf("left behind: %s", p)
		}
	}

	raw, _ := os.ReadFile(logPath)
	methods := strings.Fields(string(raw))
	for _, want := range []string{"Target.setDiscoverTargets", "Target.createTarget", "Target.attachToTarget"} {
		if !contains(methods, want) {
			t.Errorf("rod never sent %s: %v", want, methods)
		}
	}
	for _, m := range methods {
		if strings.HasPrefix(m, "Emulation.") || m == "Network.setUserAgentOverride" || m == "Runtime.enable" {
			t.Errorf("forbidden CDP method sent: %s (all: %v)", m, methods)
		}
	}
}

func fakeBrowser(t *testing.T) string {
	t.Helper()
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not on PATH")
	}
	dir := t.TempDir()
	exe := filepath.Join(dir, "fake-browser")
	if err := os.WriteFile(exe, []byte(fake), 0o755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("FAKE_LOG", filepath.Join(dir, "methods.log"))
	return exe
}

func TestCloseKeepsCallerProfile(t *testing.T) {
	exe := fakeBrowser(t)
	prof := t.TempDir()
	b, err := Launch(context.Background(), camoucrome.Options{ExecutablePath: exe, UserDataDir: prof})
	if err != nil {
		t.Fatal(err)
	}
	if !contains(b.Argv(), "--user-data-dir="+prof) {
		t.Fatalf("argv lacks caller dir: %v", b.Argv())
	}
	crash := b.owned[0]
	if len(b.owned) != 1 {
		t.Fatalf("owned %v: the caller's profile must not be owned", b.owned)
	}
	b.Close()
	if _, err := os.Stat(prof); err != nil {
		t.Errorf("caller profile removed: %v", err)
	}
	if _, err := os.Stat(crash); !os.IsNotExist(err) {
		t.Errorf("crash dir left behind: %v", err)
	}
}

// The mmdb itself needs python maxminddb; a stand-in interpreter that prints
// the module's JSON is enough to test that Launch forwards CheckGeoIP's messages.
func TestLaunchForwardsGeoIPWarnings(t *testing.T) {
	py := filepath.Join(t.TempDir(), "py")
	os.WriteFile(py, []byte("#!/bin/sh\necho '{\"warning\":\"zone contradicts exit IP\"}'\n"), 0o755)
	_, _, _ = capture(t)
	var got []string
	o := camoucrome.Options{ExecutablePath: "/x/chrome", Config: map[string]any{"timezone:id": "Asia/Tokyo"},
		GeoIP: "/db.mmdb", ExitIP: "192.0.2.5", Python: py, Warn: func(m string) { got = append(got, m) }}
	want := camoucrome.CheckGeoIP(o)
	Launch(context.Background(), o)
	if len(want) != 1 || want[0] != "zone contradicts exit IP" || !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v want %v", got, want)
	}
}
