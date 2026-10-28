//go:build !windows

package browser

import (
	"bytes"
	"context"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"
)

// A fake browser: echoes each NUL-terminated message from fd 3 on fd 4 with
// a prefix; "quit" makes it write to stderr and exit; ignores other args.
const fake = `#!/usr/bin/env python3
import os, sys
if "--remote-debugging-pipe" not in sys.argv:
    sys.stderr.write("no pipe flag\n"); sys.exit(2)
r, w = os.fdopen(3, "rb", 0), os.fdopen(4, "wb", 0)
buf = b""
while True:
    d = r.read(1 << 20)
    if not d:
        sys.exit(0)
    buf += d
    while b"\0" in buf:
        m, buf = buf.split(b"\0", 1)
        if m == b"quit":
            sys.stderr.write("fake: bye-tail\n"); sys.stderr.flush(); sys.exit(3)
        w.write(b"echo:" + m + b"\0")
`

func start(t *testing.T, ctx context.Context) *Proc {
	t.Helper()
	exe := filepath.Join(t.TempDir(), "fake-browser")
	if err := os.WriteFile(exe, []byte(fake), 0o755); err != nil {
		t.Fatal(err)
	}
	p, err := Start(ctx, Options{Executable: exe})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(p.Stop)
	return p
}

func profile(p *Proc) string {
	for _, a := range p.Argv {
		if d, ok := strings.CutPrefix(a, "--user-data-dir="); ok {
			return d
		}
	}
	return ""
}

func gone(pid int) bool {
	for i := 0; i < 100; i++ {
		if syscall.Kill(pid, 0) != nil {
			return true
		}
		time.Sleep(20 * time.Millisecond)
	}
	return false
}

func TestStartRoundtrip(t *testing.T) {
	p := start(t, context.Background())
	if err := p.Conn.Send([]byte(`{"id":1}`)); err != nil {
		t.Fatal(err)
	}
	got, err := p.Conn.Read()
	if err != nil || string(got) != `echo:{"id":1}` {
		t.Fatalf("%q %v", got, err)
	}
}

func TestStartEOFCarriesStderrTail(t *testing.T) {
	p := start(t, context.Background())
	_ = p.Conn.Send([]byte("quit"))
	_, err := p.Conn.Read()
	if !errors.Is(err, io.EOF) || !strings.Contains(err.Error(), "fake: bye-tail") {
		t.Fatalf("err = %v", err)
	}
	if !strings.Contains(p.StderrTail(), "bye-tail") {
		t.Fatal("StderrTail empty")
	}
}

func TestStopIdempotentAndCleans(t *testing.T) {
	p := start(t, context.Background())
	dir := profile(p)
	p.Stop()
	if _, err := os.Stat(dir); !os.IsNotExist(err) || !gone(p.Pid) {
		t.Fatalf("profile stat %v, gone=%v", err, gone(p.Pid))
	}
	if err := os.Mkdir(dir, 0o755); err != nil { // a second Stop must not touch it
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)
	p.Stop()
	if _, err := os.Stat(dir); err != nil {
		t.Fatal("second Stop ran cleanup again")
	}
}

func TestCtxCancelCleans(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	p := start(t, ctx)
	dir := profile(p)
	cancel()
	for i := 0; i < 100; i++ {
		if _, err := os.Stat(dir); os.IsNotExist(err) {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	if _, err := os.Stat(dir); !os.IsNotExist(err) || !gone(p.Pid) {
		t.Fatalf("profile stat %v, gone=%v", err, gone(p.Pid))
	}
}

func TestLargeMessage(t *testing.T) {
	p := start(t, context.Background())
	big := bytes.Repeat([]byte("x"), 20<<20)
	errc := make(chan error, 1)
	go func() { errc <- p.Conn.Send(big) }()
	got, err := p.Conn.Read()
	if err != nil || len(got) != len(big)+5 {
		t.Fatalf("len %d err %v", len(got), err)
	}
	if err := <-errc; err != nil {
		t.Fatal(err)
	}
}

func TestConcurrentSendOrder(t *testing.T) {
	p := start(t, context.Background())
	var seen []string
	p.Conn.Observe = func(m []byte) { seen = append(seen, string(m)) }
	var wg sync.WaitGroup
	for g := 0; g < 8; g++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := 0; i < 50; i++ {
				_ = p.Conn.Send([]byte(`{"g":` + string(rune('0'+g)) + `,"i":` + string(rune('0'+i%10)) + `}`))
			}
		}()
	}
	wg.Wait()
	for i := 0; i < 400; i++ {
		got, err := p.Conn.Read()
		if err != nil {
			t.Fatal(err)
		}
		if want := "echo:" + seen[i]; string(got) != want {
			t.Fatalf("msg %d: wire %q observed %q", i, got, want)
		}
	}
}
