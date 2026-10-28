// Package browser starts the fork with the launcher contract's argv and env,
// without any driver library: the driver under test gets only a Conn.
package browser

import (
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
	Pid   int
	Argv  []string // the browser's actual argv, what C4 reads
	Conn  *Conn    // pipe transport (nil with UsePort)
	WSURL string   // UsePort only
	Stop  func()
	tail  *tailBuf
	pipeR io.ReadCloser
	pipeW io.WriteCloser
}

// PipeRW is the raw pipe (nil, nil with UsePort), for a driver that frames the
// transport itself (chromedp's PipeConn). Use it instead of Conn, not with it.
func (p *Proc) PipeRW() (io.ReadCloser, io.WriteCloser) { return p.pipeR, p.pipeW }

// StderrTail is the last 4 KiB the browser wrote to stderr.
func (p *Proc) StderrTail() string { return p.tail.String() }

type Options struct {
	Executable, URL, Config, Preset string
	Headed, Strict, Sandbox         bool
	// UsePort swaps the pipe for --remote-debugging-port=0, ONLY for the
	// chromedp RED control (no pipe transport). C4 flags the port flag on that
	// row; fine, RED rows are judged on C1 only.
	UsePort bool
}

var wsRe = regexp.MustCompile(`DevTools listening on (ws://\S+)\n`)

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

// portWatcher is the UsePort stderr sink: it keeps the tail and reports the
// DevTools URL once, only on a complete line (no line-length limit, unlike a bufio.Scanner).
type portWatcher struct {
	tail *tailBuf
	ch   chan string
	once sync.Once
}

func (w *portWatcher) Write(p []byte) (int, error) {
	w.tail.Write(p)
	if m := wsRe.FindStringSubmatch(w.tail.String()); m != nil {
		w.once.Do(func() { w.ch <- m[1] })
	}
	return len(p), nil
}

// Start launches the browser. Stop is mandatory: the browser and a watcher
// goroutine live until Stop (or ctx cancel) runs.
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
	cmd.WaitDelay = 2 * time.Second // a descendant holding stderr must not hang Wait
	setGroup(cmd)
	tail := &tailBuf{}
	watch := &portWatcher{tail: tail, ch: make(chan string, 1)}
	cmd.Stderr = tail
	var files []*os.File // all four pipe ends, closed by stop
	var toChild, fromChild [2]*os.File
	if o.UsePort {
		cmd.Stderr = watch
	} else {
		cr, cw, err1 := os.Pipe()
		pr, pw, err2 := os.Pipe()
		if err1 != nil || err2 != nil {
			os.RemoveAll(dir)
			return nil, errors.Join(err1, err2)
		}
		toChild, fromChild = [2]*os.File{cr, cw}, [2]*os.File{pr, pw}
		files = []*os.File{cr, cw, pr, pw}
		cmd.ExtraFiles = []*os.File{cr, pw} // the browser sees fd 3 (reads) and fd 4 (writes)
	}
	closeFiles := func() {
		for _, f := range files {
			f.Close()
		}
	}
	if err := cmd.Start(); err != nil {
		closeFiles()
		os.RemoveAll(dir)
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
			os.RemoveAll(dir)
		})
	}
	go func() {
		select {
		case <-ctx.Done():
			stop()
		case <-done:
		}
	}()
	full := append([]string{o.Executable}, argv...)
	p := &Proc{Pid: cmd.Process.Pid, tail: tail, Argv: full, Stop: stop}
	if !o.UsePort {
		toChild[0].Close() // the child's ends; ours stay
		fromChild[1].Close()
		p.pipeR, p.pipeW = fromChild[0], toChild[1]
		p.Conn = newConn(fromChild[0], toChild[1])
		p.Conn.onEOF = func(err error) error {
			select { // let the exit and the stderr copy finish so the tail is complete
			case <-waited:
			case <-time.After(2 * time.Second):
			}
			return fmt.Errorf("%w; browser stderr tail:\n%s", err, strings.TrimSpace(tail.String()))
		}
		return p, nil
	}
	select {
	case p.WSURL = <-watch.ch:
		return p, nil
	case <-waited:
		stop()
		return nil, fmt.Errorf("browser exited without a DevTools URL; stderr tail:\n%s", strings.TrimSpace(tail.String()))
	case <-time.After(20 * time.Second):
		stop()
		return nil, errors.New("no DevTools URL within 20s; stderr tail:\n" + strings.TrimSpace(tail.String()))
	}
}
