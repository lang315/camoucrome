// tdpdrive runs the footprint workload through tdp's camoucrome mode.
package main

import (
	"context"
	"os"
	"time"

	"camoucrome/cdpfootprint/workload"
	"tdp"
)

type drv struct {
	b *tdp.Browser
	p *tdp.Page
}

func (d *drv) Launch(f *workload.Flags) error {
	args, err := f.Args()
	if err != nil {
		return err
	}
	env, err := f.Env()
	if err != nil {
		return err
	}
	o := tdp.CamoucromeOptions{Bin: f.Exe, Args: append(args, "--user-data-dir="+f.Profile), Env: env}
	if f.MainWorld {
		o.MainWorldPrelude = workload.Prelude
	}
	d.b, d.p, err = tdp.LaunchCamoucromeE(context.Background(), o)
	if err == nil {
		d.p.NavigationHook = nil // tdp's SSRF guard refuses the loopback probe server
	}
	return err
}

func (d *drv) Navigate(url string) error {
	if err := d.p.NavigateE(url); err != nil {
		return err
	}
	return d.p.WaitLoadE()
}

func (d *drv) WaitSelector(sel string) error        { _, err := d.p.ElementE(sel); return err }
func (d *drv) Eval(js string) error                 { _, err := d.p.EvalE(js); return err }
func (d *drv) EvalString(js string) (string, error) { return d.p.EvalStringE(js) }

func (d *drv) Click(sel string) error {
	el, err := d.p.ElementE(sel)
	if err != nil {
		return err
	}
	return el.ClickE()
}

func (d *drv) Type(sel, text string) error {
	el, err := d.p.ElementE(sel)
	if err != nil {
		return err
	}
	if err := el.ClickE(); err != nil {
		return err
	}
	return el.TypeE(text)
}

// tdp's send observer is unexported: nothing to count.
func (d *drv) Methods() map[string]int { return nil }

func (d *drv) Close() {
	if d.b != nil {
		done := make(chan struct{})
		go func() { d.b.Close(); close(done) }()
		select {
		case <-done:
		case <-time.After(35 * time.Second):
		}
	}
}

func main() {
	os.Exit(workload.Run("tdp@6e87aca", &drv{}, workload.ParseFlags()))
}
