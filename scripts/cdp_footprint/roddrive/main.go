// roddrive runs the driver probes through client/go/rodclient (go-rod over the pipe).
package main

import (
	"context"
	"os"
	"time"

	"github.com/lang315/camoucrome/client/go"
	"github.com/lang315/camoucrome/client/go/rodclient"

	"camoucrome/cdpfootprint/workload"
)

type drv struct {
	b   *rodclient.Browser
	p   *rodclient.Page
	ctx context.Context
}

func (d *drv) Launch(f *workload.Flags) error {
	d.ctx = context.Background()
	headed := false
	var err error
	d.b, err = rodclient.Launch(d.ctx, camoucrome.Options{ExecutablePath: f.Exe, UserDataDir: f.Profile, Headless: &headed})
	if err != nil {
		return err
	}
	d.p, err = d.b.NewPage(d.ctx)
	return err
}

func (d *drv) Navigate(url string) error {
	return d.p.Goto(d.ctx, url, rodclient.WaitLoad)
}

func (d *drv) WaitSelector(sel string) error {
	return d.p.WaitForSelector(d.ctx, sel, 30*time.Second)
}
func (d *drv) Eval(js string) error                 { _, err := d.p.Eval(d.ctx, js); return err }
func (d *drv) EvalString(js string) (string, error) { return d.p.Eval(d.ctx, js) }
func (d *drv) Type(sel, text string) error          { return d.p.Type(d.ctx, sel, text) }
func (d *drv) Click(sel string) error               { return d.p.Click(d.ctx, sel) }
func (d *drv) Methods() map[string]int              { return nil }
func (d *drv) Close() {
	if d.b != nil {
		d.b.Close()
	}
}

// Act: rodclient's Page has 13 methods (surface_test.go pins them). What it lacks is n/a, never an eval.
func (d *drv) Act(name string) (string, error) {
	switch name {
	case "focus":
		return "", workload.NA("no focus API (Click and Type focus as a side effect)")
	case "type":
		return "Page.Type", d.Type("#a", "ab")
	case "blur":
		return "Page.Click on #b", d.Click("#b")
	case "click":
		return "Page.Click", d.Click("#btn")
	case "select":
		return "", workload.NA("no text-selection API")
	case "scroll":
		return "", workload.NA("no wheel or scroll API")
	}
	return "", workload.NA("unknown action")
}

func (d *drv) Route(cond string) (func(), error) {
	if cond == "plain" {
		return func() {}, nil
	}
	return nil, workload.NA("no request interception API (13-method Page)")
}

func main() { os.Exit(workload.Run("rod", &drv{}, workload.ParseFlags())) }
