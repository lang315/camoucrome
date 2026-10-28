// Package rodclient launches the fork exactly as camoucrome.Launch does (same
// env, same argv) but attaches go-rod over --remote-debugging-pipe. rod's own
// launcher is never used: it would add its own argv and env.
package rodclient

import (
	"context"
	"errors"
	"fmt"
	"os"
	"sync"
	"time"

	"github.com/go-rod/rod"
	"github.com/go-rod/rod/lib/cdp"
	"github.com/go-rod/rod/lib/proto"

	camoucrome "github.com/lang315/camoucrome/client/go"
	"github.com/lang315/camoucrome/client/go/rodclient/internal/browser"
)

// startFn is a var so tests can capture argv and env without a browser.
var startFn = browser.Start

// Browser owns the process, the rod connection and the dirs Launch created.
type Browser struct {
	rod  *rod.Browser
	proc *browser.Proc

	mu    sync.Mutex
	sink  func([]byte)
	owned []string // removed by Close
	once  sync.Once
}

type launchConfig struct{ observer func([]byte) }

// Option tunes Launch.
type Option func(*launchConfig)

// WithSendObserver sees every CDP message sent, from the very first one:
// it is installed before rod connects, so connect-time traffic (such as
// Target.setDiscoverTargets) is included. Browser.OnSend only sees what is sent
// after Launch returns, so audit with this option.
func WithSendObserver(f func([]byte)) Option { return func(c *launchConfig) { c.observer = f } }

// Launch is the go-rod twin of camoucrome.Launch. v1 has no proxy support.
//
// ctx bounds Launch only: the browser outlives it (it is started with
// context.WithoutCancel(ctx)), so the usual WithTimeout + defer cancel pattern
// does not kill it; it lives until Close. A ctx cancelled before Launch
// returns (including during the connect) aborts: nothing is left running or on
// disk and ctx.Err() is returned. Errors carry a "rodclient:" prefix and wrap
// their cause.
func Launch(ctx context.Context, o camoucrome.Options, opts ...Option) (*Browser, error) {
	var lc launchConfig
	for _, f := range opts {
		f(&lc)
	}
	if o.Proxy != nil {
		return nil, errors.New("rodclient: proxy not supported by rodclient v1")
	}
	if err := ctx.Err(); err != nil {
		return nil, fmt.Errorf("rodclient: launch: %w", err)
	}
	if o.GeoIP != "" { // o.warn is unexported, so mirror it here
		for _, m := range camoucrome.CheckGeoIP(o) {
			if o.Warn != nil {
				o.Warn(m)
			} else {
				fmt.Fprintln(os.Stderr, "camoucrome: "+m)
			}
		}
	}
	env, err := camoucrome.BuildEnv(o, os.Environ())
	if err != nil {
		return nil, fmt.Errorf("rodclient: launch: %w", err)
	}
	crash, err := os.MkdirTemp("", "camoucrome-crash-")
	if err != nil {
		return nil, fmt.Errorf("rodclient: launch: %w", err)
	}
	env[camoucrome.CrashDumpsEnv] = crash
	b := &Browser{owned: []string{crash}, sink: lc.observer}
	if o.UserDataDir == "" {
		// Set before BuildArgs so the argv carries it and Start owns no dir.
		if o.UserDataDir, err = os.MkdirTemp("", "camoucrome-"); err != nil {
			b.removeOwned()
			return nil, fmt.Errorf("rodclient: launch: %w", err)
		}
		b.owned = append(b.owned, o.UserDataDir)
	}
	argv := camoucrome.BuildArgs(o)
	p, err := startFn(context.WithoutCancel(ctx), o.ExecutablePath, argv, env)
	if err != nil {
		b.removeOwned()
		return nil, fmt.Errorf("rodclient: launch: %w", err)
	}
	b.proc = p
	p.Conn.Observe = func(m []byte) {
		b.mu.Lock()
		f := b.sink
		b.mu.Unlock()
		if f != nil {
			f(m)
		}
	}
	// NoDefaultDevice: rod's implicit laptop emulation would fight screen.*.
	// rod keeps a background context (its event loop must outlive ctx).
	b.rod = rod.New().NoDefaultDevice().Client(cdp.New().Start(p.Conn))
	errc := make(chan error, 1)
	go func() { errc <- b.rod.Connect() }()
	select {
	case err = <-errc:
	case <-ctx.Done():
		p.Stop() // ends the pipe, so Connect returns
		<-errc
		b.Close()
		return nil, fmt.Errorf("rodclient: launch: %w", ctx.Err())
	}
	if err != nil {
		tail := p.StderrTail()
		b.Close()
		return nil, fmt.Errorf("rodclient: connect: %w (stderr: %s)", err, tail)
	}
	if err := ctx.Err(); err != nil {
		b.Close()
		return nil, fmt.Errorf("rodclient: launch: %w", err)
	}
	return b, nil
}

// Argv is a copy of the browser's real argv, executable first.
func (b *Browser) Argv() []string { return append([]string(nil), b.proc.Argv...) }

// OnSend sets the sink for every CDP message sent, in wire order. It replaces
// the observer set by WithSendObserver. The sink runs under the send lock: it
// must be quick and must not call back into Browser or a Page.
func (b *Browser) OnSend(f func([]byte)) {
	b.mu.Lock()
	b.sink = f
	b.mu.Unlock()
}

// NewPage opens about:blank with no emulation. It sends Target.createTarget,
// Target.attachToTarget and Page.enable (rod's page setup; playwright and
// patchright send Page.enable too). This is the only Page.enable in the
// package; no Page op sends one.
func (b *Browser) NewPage(ctx context.Context) (*Page, error) {
	p, err := b.rod.Context(ctx).Page(proto.TargetCreateTarget{})
	if err != nil {
		return nil, fmt.Errorf("rodclient: new page: %w", err)
	}
	return &Page{p: p, rng: newRand()}, nil
}

// exitWait caps how long Close waits for the browser to exit by itself after
// Browser.close, so it can finish writing a persistent profile. A var for tests.
var exitWait = 5 * time.Second

// Close asks the browser to quit (Browser.close, capped 3 s), waits up to
// exitWait for it to exit, then kills the process group and removes the dirs
// Launch created. Idempotent and safe after a browser crash.
func (b *Browser) Close() error {
	b.once.Do(func() {
		if b.rod != nil {
			// Best effort: Browser.close, bounded so a dead browser cannot hang us.
			c, cancel := context.WithTimeout(context.Background(), 3*time.Second)
			_ = b.rod.Context(c).Close()
			cancel()
		}
		if b.proc != nil {
			select {
			case <-b.proc.Exited():
			case <-time.After(exitWait):
			}
			b.proc.Stop()
		}
		b.removeOwned()
	})
	return nil
}

func (b *Browser) removeOwned() {
	for _, d := range b.owned {
		removeDir(d)
	}
}

// removeDir outlasts Windows' file locks; copy of the unexported removeDir in
// client/go/camoucrome.go.
func removeDir(dir string) {
	deadline := time.Now().Add(10 * time.Second)
	for os.RemoveAll(dir) != nil && time.Now().Before(deadline) {
		time.Sleep(50 * time.Millisecond)
	}
}
