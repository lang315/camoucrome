// Probe command for scripts/verify_sp6b_driver.py, the chromedp RED control:
// chromedp at default settings enables Runtime on every target attach
// (chromedp.go, runtime.Enable), so verify's C1 must FAIL for this row.
// The browser is started by browser.Start in its default pipe mode, so argv
// is the contract's (C4 clean) and the transport matches the rod row. chromedp
// gets the raw pipe through a custom Allocator (pipeAllocator) over its public
// PipeConn; its ExecAllocator would launch the browser with its own flags.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/chromedp/chromedp"

	"github.com/lang315/camoucrome/client/go/spike/internal/browser"
	"github.com/lang315/camoucrome/client/go/spike/internal/cdplog"
)

type cfg struct {
	exe, url, config, preset, label string
	headed, strict, sandbox         bool
}

func parseFlags(args []string) (*cfg, error) {
	fs := flag.NewFlagSet("camoucrome-probe-chromedp", flag.ContinueOnError)
	c := &cfg{}
	fs.String("driver-dir", "", "ignored (patchright/playwright only)")
	fs.StringVar(&c.label, "label", "chromedp", "driver label for the report")
	fs.StringVar(&c.exe, "executable", "", "browser binary")
	fs.StringVar(&c.url, "url", "", "probe page")
	fs.StringVar(&c.config, "config", "", "CAMOU_CONFIG JSON (or @file)")
	fs.StringVar(&c.preset, "preset", "", "CAMOU_PRESET JSON (or @file)")
	fs.BoolVar(&c.headed, "headed", false, "not headless")
	fs.BoolVar(&c.strict, "strict", false, "CAMOU_CONFIG_STRICT=1")
	fs.BoolVar(&c.sandbox, "sandbox", false, "omit --no-sandbox")
	for _, p := range []string{"proxy", "proxy-bypass", "proxy-user", "proxy-pass"} {
		fs.String(p, "", "rejected: not supported in spike")
	}
	if err := fs.Parse(args); err != nil {
		return nil, err
	}
	var proxy bool
	fs.Visit(func(f *flag.Flag) { proxy = proxy || strings.HasPrefix(f.Name, "proxy") })
	if proxy {
		return nil, errProxy
	}
	for _, v := range []*string{&c.config, &c.preset} {
		if strings.HasPrefix(*v, "@") {
			raw, err := os.ReadFile((*v)[1:])
			if err != nil {
				return nil, err
			}
			*v = string(raw)
		}
	}
	return c, nil
}

var errProxy = errors.New("proxy flags are not supported in spike (chromedp has no proxy-auth path under test)")

func marshalOutput(label, report string, argv []string) ([]byte, error) {
	var r any
	if err := json.Unmarshal([]byte(report), &r); err != nil {
		return nil, fmt.Errorf("report json: %w", err)
	}
	return json.Marshal(map[string]any{"driver": label, "report": r, "argv": argv})
}

// sentOnly adapts chromedp's protocol logger to a sink that sees sent
// messages only. chromedp (v0.21.0, pipe.go) logs the PipeConn's traffic
// through the debugf that NewBrowserTransport hands it from WithDebugf
// (= WithBrowserOption(WithBrowserDebugf)): "-> %s" in each Write (message
// without the trailing NUL, newline already trimmed) and "<- %s" in each Read.
// All browser- and target-level traffic (flattened sessions) shares that one
// PipeConn, so every send is covered. TrimRight is belt and braces.
func sentOnly(sink func([]byte)) func(string, ...any) {
	return func(format string, args ...any) {
		s := fmt.Sprintf(format, args...)
		if rest, ok := strings.CutPrefix(s, "-> "); ok {
			sink([]byte(strings.TrimRight(rest, "\n")))
		}
	}
}

// pipeAllocator is a chromedp.Allocator over a browser that already runs with
// --remote-debugging-pipe. Like remote.Allocator it attaches (Attaches() true:
// the context opens its own tab) and tears down the Conn after the pages close.
type pipeAllocator struct {
	r  io.ReadCloser
	w  io.WriteCloser
	wg sync.WaitGroup
}

func (a *pipeAllocator) Allocate(ctx context.Context, opts ...chromedp.BrowserOption) (*chromedp.Browser, error) {
	if chromedp.FromContext(ctx) == nil {
		return nil, chromedp.ErrInvalidContext
	}
	wctx, cancel := context.WithCancel(context.Background())
	a.wg.Go(func() {
		<-ctx.Done()
		chromedp.Cancel(ctx) // block until all pages are closed
		cancel()
	})
	return chromedp.NewBrowserTransport(wctx, chromedp.NewPipeConn(a.r, a.w), opts...)
}

func (a *pipeAllocator) Wait()          { a.wg.Wait() }
func (a *pipeAllocator) Attaches() bool { return true }

// probe attaches chromedp to the pipe with default settings and returns #o's text.
// Whatever chromedp sends is the measurement; logf receives its debug output.
func probe(ctx context.Context, r io.ReadCloser, w io.WriteCloser, url string, logf func(string, ...any)) (string, error) {
	allocCtx, cancelA := chromedp.NewAllocatorContext(ctx, &pipeAllocator{r: r, w: w})
	defer cancelA()
	cctx, cancelC := chromedp.NewContext(allocCtx, chromedp.WithDebugf(logf))
	defer cancelC()
	if _, err := chromedp.Run(cctx, chromedp.Navigate(url)); err != nil {
		return "", fmt.Errorf("navigate: %w", err)
	}
	// The page fills #o after load (timing trial); poll until it has text.
	deadline := time.Now().Add(20 * time.Second)
	for {
		t, err := chromedp.Run(cctx, chromedp.Text(chromedp.ID("o")))
		if err != nil || t != "" || time.Now().After(deadline) {
			return t, err
		}
		time.Sleep(100 * time.Millisecond)
	}
}

func run(args []string, stdout, stderr io.Writer) int {
	c, err := parseFlags(args)
	if err != nil {
		fmt.Fprintln(stderr, "flags:", err)
		return 2
	}
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	p, err := browser.Start(ctx, browser.Options{Executable: c.exe, URL: "", Config: c.config, Preset: c.preset,
		Headed: c.headed, Strict: c.strict, Sandbox: c.sandbox})
	if err != nil {
		fmt.Fprintln(stderr, "launch:", err)
		return 1
	}
	defer p.Stop()
	r, w := p.PipeRW()
	text, err := probe(ctx, r, w, c.url, sentOnly(cdplog.NewLogger(stderr).Log))
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	out, err := marshalOutput(c.label, text, p.Argv)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	fmt.Fprintln(stdout, string(out))
	return 0
}

func main() { os.Exit(run(os.Args[1:], os.Stdout, os.Stderr)) }
