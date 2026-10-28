// Package browser starts the fork with a caller-built argv and env, without
// any driver library: the driver gets only a Conn.
//
// Promoted from client/go/spike (throwaway) into rodclient. Argv and env come
// from camoucrome.BuildArgs / BuildEnv, so this package knows no identity logic.
package browser

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"slices"
	"strings"
	"sync"
	"time"
)

type Proc struct {
	Pid  int
	Argv []string // the browser's actual argv, what C4 reads
	Conn *Conn    // pipe transport
	Stop func()
	tail *tailBuf

	waited chan struct{}
}

// Exited is closed once the process has been reaped.
func (p *Proc) Exited() <-chan struct{} { return p.waited }

// StderrTail is the last 4 KiB the browser wrote to stderr.
func (p *Proc) StderrTail() string { return p.tail.String() }

// tailBuf keeps the last 4 KiB of stderr for error messages.
type tailBuf struct {
	mu sync.Mutex
	b  []byte
}

func (t *tailBuf) Write(p []byte) (int, error) {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.b = append(t.b, p...)
	if len(t.b) > 4096 {
		t.b = t.b[len(t.b)-4096:]
	}
	return len(p), nil
}

func (t *tailBuf) String() string {
	t.mu.Lock()
	defer t.mu.Unlock()
	return string(t.b)
}

// Start launches exe with argv and exactly env (nothing is inherited). The
// caller's argv must carry --remote-debugging-pipe (checked up front). A profile
// dir is owned here only when argv has no single-token --user-data-dir=<path>
// (the two-token form is not detected): Start adds a temp one and removes it on
// stop. A caller-supplied dir is never touched. The crash-dump dir and
// BREAKPAD_DUMP_LOCATION are the caller's job (Launch creates and cleans them).
// Stop is mandatory: the browser and a watcher goroutine live until Stop (or ctx
// cancel) runs.
func Start(ctx context.Context, exe string, argv []string, env map[string]string) (*Proc, error) {
	if err := platformErr(); err != nil {
		return nil, err
	}
	if !slices.Contains(argv, "--remote-debugging-pipe") {
		return nil, errors.New("browser: argv lacks --remote-debugging-pipe")
	}
	argv = append([]string{}, argv...)
	dir := ""
	if !slices.ContainsFunc(argv, func(a string) bool { return strings.HasPrefix(a, "--user-data-dir=") }) {
		var err error
		if dir, err = os.MkdirTemp("", "camoucrome-"); err != nil {
			return nil, err
		}
		argv = append(argv, "--user-data-dir="+dir)
	}
	rmDir := func() {
		if dir != "" {
			os.RemoveAll(dir)
		}
	}
	cmd := exec.CommandContext(ctx, exe, argv...)
	cmd.Env = make([]string, 0, len(env))
	for k, v := range env {
		cmd.Env = append(cmd.Env, k+"="+v)
	}
	cmd.WaitDelay = 2 * time.Second // a descendant holding stderr must not hang Wait
	setGroup(cmd)
	tail := &tailBuf{}
	cmd.Stderr = tail
	cr, cw, err1 := os.Pipe()
	pr, pw, err2 := os.Pipe()
	if err1 != nil || err2 != nil {
		for _, f := range []*os.File{cr, cw, pr, pw} {
			if f != nil {
				f.Close()
			}
		}
		rmDir()
		return nil, errors.Join(err1, err2)
	}
	files := []*os.File{cr, cw, pr, pw} // all four pipe ends, closed by stop
	cmd.ExtraFiles = []*os.File{cr, pw} // the browser sees fd 3 (reads) and fd 4 (writes)
	closeFiles := func() {
		for _, f := range files {
			f.Close()
		}
	}
	if err := cmd.Start(); err != nil {
		closeFiles()
		rmDir()
		return nil, err
	}
	waited := make(chan struct{})
	go func() { _ = cmd.Wait(); close(waited) }()
	done := make(chan struct{})
	var once sync.Once
	stop := func() {
		once.Do(func() {
			close(done)
			killGroup(cmd.Process.Pid)
			<-waited
			closeFiles()
			rmDir()
		})
	}
	go func() {
		select {
		case <-ctx.Done():
			stop()
		case <-done:
		}
	}()
	p := &Proc{Pid: cmd.Process.Pid, tail: tail, Argv: append([]string{exe}, argv...), Stop: stop, waited: waited}
	cr.Close() // the child's ends; ours stay
	pw.Close()
	p.Conn = newConn(pr, cw)
	p.Conn.onEOF = func(err error) error {
		select { // let the exit and the stderr copy finish so the tail is complete
		case <-waited:
		case <-time.After(2 * time.Second):
		}
		return fmt.Errorf("%w; browser stderr tail:\n%s", err, strings.TrimSpace(tail.String()))
	}
	return p, nil
}
