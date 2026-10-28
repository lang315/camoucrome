// Package browser starts the fork with the launcher contract's argv and env,
// without any driver library: the driver under test gets only a Conn.
package browser

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"sync"
	"time"

	camoucrome "github.com/lang315/camoucrome/client/go"
)

type Proc struct {
	Argv  []string // the browser's actual argv, what C4 reads
	Conn  *Conn    // pipe transport (nil with UsePort)
	WSURL string   // UsePort only
	Stop  func()
}

type Options struct {
	Executable, URL, Config, Preset string
	Headed, Strict, Sandbox         bool
	// UsePort swaps the pipe for --remote-debugging-port=0, ONLY for the
	// chromedp RED control (no pipe transport). C4 flags the port flag on that
	// row; fine, RED rows are judged on C1 only.
	UsePort bool
}

var wsRe = regexp.MustCompile(`DevTools listening on (ws://\S+)`)

// buildArgv is the contract's expected argv (+ profile dir, + --no-sandbox).
func buildArgv(o Options, dir string) []string {
	argv := append([]string{}, camoucrome.BaseArgs...)
	if !o.Headed {
		argv = append(argv, "--headless=new")
	}
	if o.UsePort {
		argv = append(argv, "--remote-debugging-port=0")
	} else {
		argv = append(argv, "--remote-debugging-pipe")
	}
	argv = append(argv, "--user-data-dir="+dir)
	if !o.Sandbox {
		argv = append(argv, "--no-sandbox")
	}
	if o.URL != "" {
		argv = append(argv, o.URL)
	}
	return argv
}

func buildEnv(o Options, base []string) ([]string, error) {
	m, err := camoucrome.BuildEnv(camoucrome.Options{Config: nilIfEmpty(o.Config), Preset: nilIfEmpty(o.Preset), Strict: o.Strict}, base)
	if err != nil {
		return nil, err
	}
	env := make([]string, 0, len(m))
	for k, v := range m {
		env = append(env, k+"="+v)
	}
	return env, nil
}

func nilIfEmpty(s string) any {
	if s == "" {
		return nil
	}
	return s
}

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

func Start(ctx context.Context, o Options) (*Proc, error) {
	if err := platformErr(); err != nil {
		return nil, err
	}
	dir, err := os.MkdirTemp("", "camoucrome-spike-")
	if err != nil {
		return nil, err
	}
	env, err := buildEnv(o, os.Environ())
	if err != nil {
		os.RemoveAll(dir)
		return nil, err
	}
	argv := buildArgv(o, dir)
	cmd := exec.CommandContext(ctx, o.Executable, argv...)
	cmd.Env = env
	setGroup(cmd)
	tail := &tailBuf{}
	var toChild, fromChild [2]*os.File // browser reads fd 3, writes fd 4
	var closeAll func()
	if !o.UsePort {
		cr, cw, err1 := os.Pipe()
		pr, pw, err2 := os.Pipe()
		if err1 != nil || err2 != nil {
			os.RemoveAll(dir)
			return nil, errors.Join(err1, err2)
		}
		toChild, fromChild = [2]*os.File{cr, cw}, [2]*os.File{pr, pw}
		cmd.ExtraFiles = []*os.File{cr, pw}
		cmd.Stderr = tail
		closeAll = func() {
			for _, f := range []*os.File{cr, cw, pr, pw} {
				f.Close()
			}
		}
	}
	var stderr io.ReadCloser
	if o.UsePort {
		if stderr, err = cmd.StderrPipe(); err != nil {
			os.RemoveAll(dir)
			return nil, err
		}
	}
	if err := cmd.Start(); err != nil {
		if closeAll != nil {
			closeAll()
		}
		os.RemoveAll(dir)
		return nil, err
	}
	stop := func() {
		killGroup(cmd.Process.Pid)
		_ = cmd.Wait()
		if closeAll != nil {
			closeAll()
		}
		os.RemoveAll(dir)
	}
	full := append([]string{o.Executable}, argv...)
	if !o.UsePort {
		toChild[0].Close() // child's ends; ours stay
		fromChild[1].Close()
		return &Proc{Argv: full, Conn: newConn(fromChild[0], toChild[1]), Stop: stop}, nil
	}

	type res struct{ ws string }
	ch := make(chan res, 1)
	go func() {
		sc := bufio.NewScanner(io.TeeReader(stderr, tail))
		for sc.Scan() {
			if m := wsRe.FindStringSubmatch(sc.Text()); m != nil {
				ch <- res{m[1]}
				for sc.Scan() { // keep draining so the browser never blocks on stderr
				}
				return
			}
		}
		ch <- res{}
	}()
	select {
	case r := <-ch:
		if r.ws == "" {
			stop()
			return nil, fmt.Errorf("browser exited without a DevTools URL; stderr tail:\n%s", strings.TrimSpace(tail.String()))
		}
		return &Proc{Argv: full, WSURL: r.ws, Stop: stop}, nil
	case <-time.After(20 * time.Second):
		stop()
		return nil, errors.New("no DevTools URL within 20s; stderr tail:\n" + strings.TrimSpace(tail.String()))
	}
}
