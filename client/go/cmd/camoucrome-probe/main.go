// Probe command for scripts/verify_sp6b_driver.py, the Go twin of
// python -m camoucrome.probe: launch through the package with the driver
// directory given, load a URL, print the page's own report (#o text) and
// the browser process argv as JSON. The caller sets DEBUG=pw:protocol and
// PLAYWRIGHT_NODEJS_PATH and reads the protocol log from stderr.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strings"

	"github.com/mxschmitt/playwright-go"

	camoucrome "github.com/lang315/camoucrome/client/go"
)

func fail(what string, err error) {
	fmt.Fprintln(os.Stderr, what, err)
	os.Exit(1)
}

// humanizeOn: the config enables humanize, so the page's button is clicked.
func humanizeOn(config string) bool {
	var c map[string]any
	return json.Unmarshal([]byte(config), &c) == nil && c["humanize:enabled"] == true
}

// scenarioOut is the probe contract of scripts/verify_human_click_clients.py.
// Go has no B, so wrapper_hits is always 0.
type scenarioOut struct {
	Log         any `json:"log"`
	Error       any `json:"error"`
	WrapperHits int `json:"wrapper_hits"`
	Extra       any `json:"extra"`
}

// runScenario performs one row's actions and returns the page's own #o log,
// plus the error messages the page cannot see (A6, stock-missing).
func runScenario(pw *playwright.Playwright, o camoucrome.Options, name, url string) (log, extra any, err error) {
	switch name {
	case "A1", "A2", "A3", "A4", "A5", "A6", "A7", "G1", "stock-missing":
	default:
		return nil, nil, fmt.Errorf("unknown scenario %s", name)
	}
	ctx, err := camoucrome.Launch(pw, o)
	if err != nil {
		return nil, nil, err
	}
	defer ctx.Close()
	var page playwright.Page
	if pages := ctx.Pages(); len(pages) > 0 {
		page = pages[0]
	} else if page, err = ctx.NewPage(); err != nil {
		return nil, nil, err
	}
	if _, err = page.Goto(url, playwright.PageGotoOptions{WaitUntil: playwright.WaitUntilStateLoad}); err != nil {
		return nil, nil, err
	}
	loc := page.Locator("#t")
	half := playwright.LocatorClickOptions{Timeout: playwright.Float(500)}
	errText := func(e error) any {
		if e == nil {
			return nil
		}
		return e.Error()
	}
	switch name {
	case "A1", "A7", "G1":
		n := 5
		if name != "A7" {
			n = 20
		}
		for i := 0; i < n && err == nil; i++ {
			err = camoucrome.HumanClick(loc)
		}
		for i := 0; name == "G1" && i < 3 && err == nil; i++ { // plain Click: the centre
			err = loc.Click()
		}
	case "A2", "A3", "A4", "A5":
		err = camoucrome.HumanClick(loc)
	case "A6":
		if err = camoucrome.HumanClick(page.Locator("#late")); err == nil {
			extra = map[string]any{
				"missing": errText(camoucrome.HumanClick(page.Locator("#nope"), half)),
				"strict":  errText(camoucrome.HumanClick(page.Locator(".dup"), half)),
				"hidden":  errText(camoucrome.HumanClick(page.Locator("#hid"), half)),
			}
		}
	case "stock-missing":
		extra = map[string]any{
			"missing": errText(page.Locator("#nope").Click(half)),
			"strict":  errText(page.Locator(".dup").Click(half)),
			"hidden":  errText(page.Locator("#hid").Click(half)),
		}
	}
	if err != nil {
		return nil, nil, err
	}
	page.WaitForTimeout(500) // the page's 100 ms sync catches the last scroll
	text, err := page.Locator("#o").TextContent()
	if err != nil {
		return nil, nil, err
	}
	err = json.Unmarshal([]byte(text), &log)
	return log, extra, err
}

func main() {
	driverDir := flag.String("driver-dir", "", "playwright-go driver directory (patchright-core or playwright-core)")
	label := flag.String("label", "go", "driver label for the report")
	exe := flag.String("executable", "", "browser binary")
	url := flag.String("url", "", "probe page")
	config := flag.String("config", "", "CAMOU_CONFIG JSON")
	preset := flag.String("preset", "", "CAMOU_PRESET JSON")
	headed := flag.Bool("headed", false, "not headless")
	strict := flag.Bool("strict", false, "CAMOU_CONFIG_STRICT=1")
	// Windows: the sandbox is what strips CAMOU_* from a renderer unless the
	// windows-sandbox-env patch lets it through, and --no-sandbox hides that.
	sandbox := flag.Bool("sandbox", false, "omit --no-sandbox")
	scenario := flag.String("scenario", "", "verify_human_click_clients row: load --url, act, print the page log")
	flag.Parse()
	// A generated identity is ~37 KB (Windows) to ~140 KB (macOS): past
	// Windows' 32767-char command line and Linux's 128 KiB single argument.
	for _, v := range []*string{config, preset} {
		if strings.HasPrefix(*v, "@") {
			raw, err := os.ReadFile((*v)[1:])
			if err != nil {
				fail("read:", err)
			}
			*v = string(raw)
		}
	}

	pw, err := playwright.Run(&playwright.RunOptions{DriverDirectory: *driverDir, SkipInstallBrowsers: true, Verbose: false})
	if err != nil {
		fail("run:", err)
	}
	headless := !*headed
	o := camoucrome.Options{ExecutablePath: *exe, Headless: &headless, Strict: *strict}
	if !*sandbox {
		o.ExtraArgs = []string{"--no-sandbox"}
	}
	if *config != "" {
		o.Config = *config
	}
	if *preset != "" {
		o.Preset = *preset
	}
	if *scenario != "" {
		var out scenarioOut
		if out.Log, out.Extra, err = runScenario(pw, o, *scenario, *url); err != nil {
			out.Error = err.Error()
		}
		json.NewEncoder(os.Stdout).Encode(out)
		pw.Stop()
		return
	}
	ctx, err := camoucrome.Launch(pw, o)
	if err != nil {
		fail("launch:", err)
	}
	var page playwright.Page
	if pages := ctx.Pages(); len(pages) > 0 {
		page = pages[0]
	} else if page, err = ctx.NewPage(); err != nil {
		fail("page:", err)
	}
	// SP2 4.2: a driver's init script must not be observable from the main
	// world. The probe page reports typeof window.__camou_init.
	if err = page.AddInitScript(playwright.Script{Content: playwright.String("window.__camou_init = 1")}); err != nil {
		fail("init script:", err)
	}
	if _, err = page.Goto(*url, playwright.PageGotoOptions{WaitUntil: playwright.WaitUntilStateLoad}); err != nil {
		fail("goto:", err)
	}
	// SP2d: exercise the helper (Go has no B) before reporting.
	if humanizeOn(*config) {
		n, err := page.Locator("#camou-click").Count()
		if err != nil || n == 0 {
			fail("no #camou-click:", fmt.Errorf("count=%d err=%v", n, err))
		}
		if err = camoucrome.HumanClick(page.Locator("#camou-click")); err != nil {
			fail("human click:", err)
		}
	}
	text, err := page.Locator("#o").TextContent()
	if err != nil {
		fail("report:", err)
	}
	argv := browserArgv(*exe)
	ctx.Close()
	pw.Stop()
	var report any
	if err := json.Unmarshal([]byte(text), &report); err != nil {
		fail("report json:", err)
	}
	json.NewEncoder(os.Stdout).Encode(map[string]any{"driver": *label, "report": report, "argv": argv})
}
