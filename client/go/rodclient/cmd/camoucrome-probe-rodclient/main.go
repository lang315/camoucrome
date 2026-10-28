// Probe command for scripts/verify_sp6b_driver.py, the rodclient twin of
// camoucrome-probe: launch the fork through rodclient, register the init
// script, load a URL, print the page's own report (#o text) and the browser
// argv as JSON. Every CDP message sent goes to stderr, one raw line each.
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

	camoucrome "github.com/lang315/camoucrome/client/go"
	"github.com/lang315/camoucrome/client/go/rodclient"
)

// initScript is what the playwright probes register: C6 expects exactly one
// new global from it.
const initScript = "window.__camou_init = 1"

// reportWait caps the wait for #o; a var so a test can shorten it.
var reportWait = 20 * time.Second

type cfg struct {
	exe, url, config, preset, label string
	headed, strict, sandbox         bool
}

var errProxy = errors.New("proxy flags are not supported by rodclient v1")

func parseFlags(args []string) (*cfg, error) {
	fs := flag.NewFlagSet("camoucrome-probe-rodclient", flag.ContinueOnError)
	c := &cfg{}
	fs.String("driver-dir", "", "ignored (patchright/playwright only)")
	fs.StringVar(&c.label, "label", "go-rodclient", "driver label for the report")
	fs.StringVar(&c.exe, "executable", "", "browser binary")
	fs.StringVar(&c.url, "url", "", "probe page")
	fs.StringVar(&c.config, "config", "", "CAMOU_CONFIG JSON (or @file)")
	fs.StringVar(&c.preset, "preset", "", "CAMOU_PRESET JSON (or @file)")
	fs.BoolVar(&c.headed, "headed", false, "not headless")
	fs.BoolVar(&c.strict, "strict", false, "CAMOU_CONFIG_STRICT=1")
	fs.BoolVar(&c.sandbox, "sandbox", false, "omit --no-sandbox")
	for _, p := range []string{"proxy", "proxy-bypass", "proxy-user", "proxy-pass"} {
		fs.String(p, "", "rejected: not supported by rodclient v1")
	}
	if err := fs.Parse(args); err != nil {
		return nil, err
	}
	var proxy bool
	fs.Visit(func(f *flag.Flag) { proxy = proxy || strings.HasPrefix(f.Name, "proxy") })
	if proxy {
		return nil, errProxy
	}
	// Generated identities exceed argv limits: same @file convention as camoucrome-probe.
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

func (c *cfg) options() camoucrome.Options {
	headless := !c.headed
	o := camoucrome.Options{ExecutablePath: c.exe, Headless: &headless, Strict: c.strict}
	if !c.sandbox {
		o.ExtraArgs = []string{"--no-sandbox"}
	}
	if c.config != "" {
		o.Config = c.config
	}
	if c.preset != "" {
		o.Preset = c.preset
	}
	return o
}

func marshalOutput(label, report string, argv []string) ([]byte, error) {
	var r any
	if err := json.Unmarshal([]byte(report), &r); err != nil {
		return nil, fmt.Errorf("report json: %w", err)
	}
	return json.Marshal(map[string]any{"driver": label, "report": r, "argv": argv})
}

// page is the part of *rodclient.Page the probe uses.
type page interface {
	AddInitScript(ctx context.Context, js string) error
	Goto(ctx context.Context, url string, w rodclient.WaitUntil) error
	Text(ctx context.Context, selector string) (string, error)
}

// report registers the init script, loads url and returns #o's text once the
// page has filled it (it does so after load, as a timing trial).
func report(ctx context.Context, p page, url string) (string, error) {
	if err := p.AddInitScript(ctx, initScript); err != nil {
		return "", err
	}
	if err := p.Goto(ctx, url, rodclient.WaitLoad); err != nil {
		return "", err
	}
	deadline := time.Now().Add(reportWait)
	for {
		t, err := p.Text(ctx, "#o")
		if err != nil || t != "" {
			return t, err
		}
		if time.Now().After(deadline) {
			return "", fmt.Errorf("#o still empty after %s", reportWait)
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
	// The observer is installed before connecting, so connect-time traffic is logged too.
	b, err := rodclient.Launch(ctx, c.options(), rodclient.WithSendObserver(func(m []byte) { fmt.Fprintln(stderr, string(m)) }))
	if err != nil {
		fmt.Fprintln(stderr, "launch:", err)
		return 1
	}
	defer b.Close()
	p, err := b.NewPage(ctx)
	if err != nil {
		fmt.Fprintln(stderr, "page:", err)
		return 1
	}
	text, err := report(ctx, p, c.url)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	out, err := marshalOutput(c.label, text, b.Argv())
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	fmt.Fprintln(stdout, string(out))
	return 0
}

func main() { os.Exit(run(os.Args[1:], os.Stdout, os.Stderr)) }
