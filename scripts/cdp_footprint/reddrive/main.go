// reddrive is the positive control: the same workload sent the way automation tools leak.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/mafredri/cdp"
	"github.com/mafredri/cdp/devtool"
	"github.com/mafredri/cdp/protocol/dom"
	"github.com/mafredri/cdp/protocol/fetch"
	"github.com/mafredri/cdp/protocol/input"
	"github.com/mafredri/cdp/protocol/page"
	"github.com/mafredri/cdp/protocol/runtime"
	"github.com/mafredri/cdp/rpcc"

	"camoucrome/cdpfootprint/workload"
)

type drv struct {
	cmd  *exec.Cmd
	conn *rpcc.Conn
	c    *cdp.Client
	ctx  context.Context
	mu   sync.Mutex
	m    map[string]int
	root dom.NodeID
}

func (d *drv) count(method string) { d.mu.Lock(); d.m[method]++; d.mu.Unlock() }

func (d *drv) Methods() map[string]int {
	d.mu.Lock()
	defer d.mu.Unlock()
	out := map[string]int{}
	for k, v := range d.m {
		out[k] = v
	}
	return out
}

func (d *drv) Launch(f *workload.Flags) error {
	d.ctx, d.m = context.Background(), map[string]int{}
	args, err := f.Args()
	if err != nil {
		return err
	}
	env, err := f.Env()
	if err != nil {
		return err
	}
	d.cmd = exec.Command(f.Exe, append(args, "--user-data-dir="+f.Profile, "--remote-debugging-port=0")...)
	d.cmd.Env = env
	if err := d.cmd.Start(); err != nil {
		return err
	}
	var port int
	for i := 0; i < 600 && port == 0; i++ { // up to 60 s for DevToolsActivePort
		time.Sleep(100 * time.Millisecond)
		if b, err := os.ReadFile(filepath.Join(f.Profile, "DevToolsActivePort")); err == nil {
			port, _ = strconv.Atoi(strings.SplitN(string(b), "\n", 2)[0])
		}
	}
	if port == 0 {
		return fmt.Errorf("no DevToolsActivePort in %s", f.Profile)
	}
	t, err := devtool.New(fmt.Sprintf("http://127.0.0.1:%d", port)).Get(d.ctx, devtool.Page)
	if err != nil {
		return err
	}
	if d.conn, err = rpcc.DialContext(d.ctx, t.WebSocketDebuggerURL); err != nil {
		return err
	}
	d.c = cdp.NewClient(d.conn)
	for _, s := range []struct {
		name string
		do   func() error
	}{
		{"Runtime.enable", func() error { return d.c.Runtime.Enable(d.ctx) }},
		{"Page.enable", func() error { return d.c.Page.Enable(d.ctx, nil) }},
		{"DOM.enable", func() error { return d.c.DOM.Enable(d.ctx, nil) }},
		// the DOM agent emits per-insertion events only for a bound parent: bind html>body>#t1 like tdp's ElementE
		{"DOM.getDocument", func() error {
			doc, err := d.c.DOM.GetDocument(d.ctx, nil)
			if err != nil {
				return err
			}
			d.root = doc.Root.NodeID
			return nil
		}},
		{"DOM.querySelector", func() error {
			_, err := d.c.DOM.QuerySelector(d.ctx, dom.NewQuerySelectorArgs(d.root, "#t1"))
			return err
		}},
		{"Fetch.enable", func() error {
			pat := "*"
			return d.c.Fetch.Enable(d.ctx, fetch.NewEnableArgs().SetPatterns([]fetch.RequestPattern{{URLPattern: &pat}}))
		}},
	} {
		d.count(s.name)
		if err := s.do(); err != nil {
			return fmt.Errorf("%s: %w", s.name, err)
		}
	}
	rp, err := d.c.Fetch.RequestPaused(d.ctx)
	if err != nil {
		return err
	}
	go func() {
		for {
			ev, err := rp.Recv()
			if err != nil {
				return
			}
			d.count("Fetch.continueRequest")
			d.c.Fetch.ContinueRequest(d.ctx, fetch.NewContinueRequestArgs(ev.RequestID))
		}
	}()
	return nil
}

func (d *drv) Navigate(url string) error {
	ctx, cancel := context.WithTimeout(d.ctx, 60*time.Second)
	defer cancel()
	lf, err := d.c.Page.LoadEventFired(ctx)
	if err != nil {
		return err
	}
	defer lf.Close()
	d.count("Page.navigate")
	if _, err := d.c.Page.Navigate(d.ctx, page.NewNavigateArgs(url)); err != nil {
		return err
	}
	lf.Recv()                                             // a page that never fires load (facebook) is not an error after 60 s
	return d.Eval("() => { window.__footprint_red = 1 }") // the L8 control
}

func (d *drv) evalRaw(js string) (*runtime.EvaluateReply, error) {
	d.count("Runtime.evaluate")
	r, err := d.c.Runtime.Evaluate(d.ctx, runtime.NewEvaluateArgs("("+js+")()\n//# sourceURL=pptr:footprint").SetReturnByValue(true))
	if err == nil && r.ExceptionDetails != nil {
		err = fmt.Errorf("js: %s", r.ExceptionDetails.Text)
	}
	return r, err
}

func (d *drv) Eval(js string) error { _, err := d.evalRaw(js); return err }

func (d *drv) EvalString(js string) (string, error) {
	r, err := d.evalRaw(js)
	if err != nil {
		return "", err
	}
	var s string
	err = json.Unmarshal(r.Result.Value, &s)
	return s, err
}

func (d *drv) WaitSelector(sel string) error {
	for i := 0; i < 150; i++ {
		r, err := d.evalRaw("() => document.querySelector('" + sel + "') !== null")
		if err == nil && string(r.Result.Value) == "true" {
			return nil
		}
		time.Sleep(100 * time.Millisecond)
	}
	return fmt.Errorf("%s never appeared", sel)
}

func (d *drv) Type(sel, text string) error {
	if err := d.Eval("() => document.querySelector('" + sel + "').focus()"); err != nil {
		return err
	}
	d.count("Input.insertText")
	return d.c.Input.InsertText(d.ctx, input.NewInsertTextArgs(text))
}

// Untrusted on purpose: a dispatched mouse click has the real shape and could not fail L7.
func (d *drv) Click(sel string) error {
	return d.Eval("() => document.querySelector('" + sel + "').click()")
}

func (d *drv) Close() {
	if d.cmd == nil || d.cmd.Process == nil {
		return
	}
	if d.c != nil {
		d.c.Browser.Close(d.ctx)
	}
	done := make(chan struct{})
	go func() { d.cmd.Wait(); close(done) }()
	select {
	case <-done:
	case <-time.After(10 * time.Second):
		d.cmd.Process.Kill()
	}
}

func main() {
	os.Exit(workload.Run("red", &drv{}, workload.ParseFlags()))
}
