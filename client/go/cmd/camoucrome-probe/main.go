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
