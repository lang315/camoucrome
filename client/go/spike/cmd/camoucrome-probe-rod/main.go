// Probe command for scripts/verify_sp6b_driver.py, the go-rod twin of
// camoucrome-probe: start the fork with browser.Start (no driver launcher),
// attach rod over the pipe, load a URL, print the page's own report (#o text)
// and the browser argv as JSON. Every CDP message rod sends goes to stderr,
// one per line, from the Conn's send seam (real wire bytes).
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
	"time"

	"github.com/go-rod/rod"
	"github.com/go-rod/rod/lib/cdp"
	"github.com/go-rod/rod/lib/proto"

	"github.com/lang315/camoucrome/client/go/spike/internal/browser"
	"github.com/lang315/camoucrome/client/go/spike/internal/cdplog"
)

type cfg struct {
	exe, url, config, preset, label string
	headed, strict, sandbox         bool
	noDefaultDevice                 bool
}

func parseFlags(args []string) (*cfg, error) {
	fs := flag.NewFlagSet("camoucrome-probe-rod", flag.ContinueOnError)
	c := &cfg{}
	fs.String("driver-dir", "", "ignored (patchright/playwright only)")
	fs.StringVar(&c.label, "label", "rod", "driver label for the report")
	fs.StringVar(&c.exe, "executable", "", "browser binary")
	fs.StringVar(&c.url, "url", "", "probe page")
	fs.StringVar(&c.config, "config", "", "CAMOU_CONFIG JSON (or @file)")
	fs.StringVar(&c.preset, "preset", "", "CAMOU_PRESET JSON (or @file)")
	fs.BoolVar(&c.headed, "headed", false, "not headless")
	fs.BoolVar(&c.strict, "strict", false, "CAMOU_CONFIG_STRICT=1")
	fs.BoolVar(&c.sandbox, "sandbox", false, "omit --no-sandbox")
	fs.BoolVar(&c.noDefaultDevice, "no-default-device", false, "rod NoDefaultDevice(): drop its implicit device emulation (a variant, not the default measurement)")
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
	// Same @file convention as camoucrome-probe: identities exceed argv limits.
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

var errProxy = errors.New("proxy flags are not supported in spike (rod has no proxy-auth path under test)")

func marshalOutput(label, report string, argv []string) ([]byte, error) {
	var r any
	if err := json.Unmarshal([]byte(report), &r); err != nil {
		return nil, fmt.Errorf("report json: %w", err)
	}
	return json.Marshal(map[string]any{"driver": label, "report": r, "argv": argv})
}

// probe attaches rod to ws and returns #o's text. Nothing here sends CDP
// itself; whatever rod's Connect/Page/WaitLoad/Element/Text send is the measurement.
func probe(ctx context.Context, ws cdp.WebSocketable, url string, noDefaultDevice bool) (string, error) {
	b := rod.New().Client(cdp.New().Start(ws)).Context(ctx)
	if noDefaultDevice {
		b = b.NoDefaultDevice()
	}
	if err := b.Connect(); err != nil {
		return "", fmt.Errorf("connect: %w", err)
	}
	page, err := b.Page(proto.TargetCreateTarget{URL: url})
	if err != nil {
		return "", fmt.Errorf("page: %w", err)
	}
	if err := page.WaitLoad(); err != nil {
		return "", fmt.Errorf("load: %w", err)
	}
	el, err := page.Element("#o")
	if err != nil {
		return "", fmt.Errorf("element: %w", err)
	}
	return el.Text() // Runtime.callFunctionOn on the element object: part of what is measured
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
	p.Conn.Observe = cdplog.NewLogger(stderr).Log
	text, err := probe(ctx, p.Conn, c.url, c.noDefaultDevice)
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
