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

// Launch is the go-rod twin of camoucrome.Launch. v1 has no proxy support.
func Launch(ctx context.Context, o camoucrome.Options) (*Browser, error) {
	if o.Proxy != nil {
		return nil, errors.New("rodclient: proxy not supported by rodclient v1")
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
		return nil, err
	}
	crash, err := os.MkdirTemp("", "camoucrome-crash-")
	if err != nil {
		return nil, err
	}
	env[camoucrome.CrashDumpsEnv] = crash
	b := &Browser{owned: []string{crash}}
	if o.UserDataDir == "" {
		// Set before BuildArgs so the argv carries it and Start owns no dir.
		if o.UserDataDir, err = os.MkdirTemp("", "camoucrome-"); err != nil {
			b.removeOwned()
			return nil, err
		}
		b.owned = append(b.owned, o.UserDataDir)
	}
	argv := camoucrome.BuildArgs(o)
	p, err := startFn(ctx, o.ExecutablePath, argv, env)
	if err != nil {
		b.removeOwned()
		return nil, err
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
	b.rod = rod.New().NoDefaultDevice().Client(cdp.New().Start(p.Conn)).Context(ctx)
	if err := b.rod.Connect(); err != nil {
		tail := p.StderrTail()
		b.Close()
		return nil, fmt.Errorf("rodclient: connect: %w (stderr: %s)", err, tail)
	}
	return b, nil
}

// Argv is the browser's real argv, executable first.
func (b *Browser) Argv() []string { return b.proc.Argv }

// OnSend sets the sink for every CDP message sent, in wire order.
func (b *Browser) OnSend(f func([]byte)) {
	b.mu.Lock()
	b.sink = f
	b.mu.Unlock()
}

// NewPage opens about:blank with no emulation.
func (b *Browser) NewPage(ctx context.Context) (*Page, error) {
	p, err := b.rod.Context(ctx).Page(proto.TargetCreateTarget{})
	if err != nil {
		return nil, err
	}
	return &Page{p: p}, nil
}

// Close is idempotent and safe after a browser crash.
func (b *Browser) Close() error {
	b.once.Do(func() {
		if b.rod != nil {
			// Best effort: Browser.close, bounded so a dead browser cannot hang us.
			c, cancel := context.WithTimeout(context.Background(), 3*time.Second)
			_ = b.rod.Context(c).Close()
			cancel()
		}
		if b.proc != nil {
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
