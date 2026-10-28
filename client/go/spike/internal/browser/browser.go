// Package browser starts the fork with the launcher contract's argv and env,
// without any driver library: rod and chromedp only get the DevTools URL.
package browser

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"syscall"
	"time"

	camoucrome "github.com/lang315/camoucrome/client/go"
)

type Proc struct {
	Argv  []string
	WSURL string
	Stop  func()
}

type Options struct {
	Executable, URL, Config, Preset string
	Headed, Strict, Sandbox         bool
}

var wsRe = regexp.MustCompile(`DevTools listening on (ws://\S+)`)

// buildArgv is the contract's argv with a debugging port instead of the pipe
// (--remote-debugging-port=0 is the one deviation: the driver libs need a socket).
func buildArgv(o Options, dir string) []string {
	argv := append([]string{}, camoucrome.BaseArgs...)
	if !o.Headed {
		argv = append(argv, "--headless=new")
	}
	argv = append(argv, "--remote-debugging-port=0", "--user-data-dir="+dir)
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

func Start(ctx context.Context, o Options) (*Proc, error) {
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
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true} // shortcut: unix only, spike runs on the Linux box
	stderr, err := cmd.StderrPipe()
	if err != nil {
		os.RemoveAll(dir)
		return nil, err
	}
	if err := cmd.Start(); err != nil {
		os.RemoveAll(dir)
		return nil, err
	}
	stop := func() {
		_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
		_ = cmd.Wait()
		os.RemoveAll(dir)
	}
	type res struct {
		ws   string
		tail string
	}
	ch := make(chan res, 1)
	go func() {
		var tail []string
		sc := bufio.NewScanner(stderr)
		for sc.Scan() {
			line := sc.Text()
			if m := wsRe.FindStringSubmatch(line); m != nil {
				ch <- res{ws: m[1]}
				for sc.Scan() { // keep draining so the browser never blocks on stderr
				}
				return
			}
			if tail = append(tail, line); len(tail) > 20 {
				tail = tail[1:]
			}
		}
		ch <- res{tail: strings.Join(tail, "\n")}
	}()
	select {
	case r := <-ch:
		if r.ws == "" {
			stop()
			return nil, fmt.Errorf("browser exited without a DevTools URL; stderr tail:\n%s", r.tail)
		}
		return &Proc{Argv: append([]string{o.Executable}, argv...), WSURL: r.ws, Stop: stop}, nil
	case <-time.After(20 * time.Second):
		stop()
		return nil, errors.New("no DevTools URL within 20s; stderr tail:\n" + (<-ch).tail)
	}
}
