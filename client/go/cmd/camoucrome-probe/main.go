// Probe command for scripts/verify_sp6b_driver.py, the Go twin of
// python -m camoucrome.probe: launch through the package with the driver
// directory given, load a URL, print the page's own report (#o text) and
// the browser process argv as JSON. The caller sets DEBUG=pw:protocol and
// PLAYWRIGHT_NODEJS_PATH and reads the protocol log from stderr.
package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/mxschmitt/playwright-go"

	camoucrome "github.com/lang315/camoucrome/client/go"
)

func browserArgv(executable string) []string {
	entries, _ := os.ReadDir("/proc")
	for _, e := range entries {
		raw, err := os.ReadFile(filepath.Join("/proc", e.Name(), "cmdline"))
		if err != nil || len(raw) == 0 {
			continue
		}
		parts := bytes.Split(bytes.TrimSuffix(raw, []byte{0}), []byte{0})
		if len(parts) == 1 { // Chromium rewrites its cmdline into one space-joined string
			parts = bytes.Split(parts[0], []byte{' '})
		}
		if string(parts[0]) != executable {
			continue
		}
		argv := make([]string, len(parts))
		child := false
		for i, p := range parts {
			argv[i] = string(p)
			if strings.HasPrefix(argv[i], "--type=") {
				child = true
			}
		}
		if !child {
			return argv
		}
	}
	return nil
}

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
	flag.Parse()

	pw, err := playwright.Run(&playwright.RunOptions{DriverDirectory: *driverDir, SkipInstallBrowsers: true, Verbose: false})
	if err != nil {
		fail("run:", err)
	}
	headless := !*headed
	o := camoucrome.Options{ExecutablePath: *exe, ExtraArgs: []string{"--no-sandbox"}, Headless: &headless}
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
