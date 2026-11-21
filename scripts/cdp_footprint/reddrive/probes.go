package main

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/mafredri/cdp/protocol/dom"
	"github.com/mafredri/cdp/protocol/fetch"
	"github.com/mafredri/cdp/protocol/input"

	"camoucrome/cdpfootprint/workload"
)

func probeMode(m string) bool { return m == "l9" || m == "headers" }

// Red acts: the eval path automation tools leak through; every event fires synchronously inside the call, so the
// driver's sourceURL frame sits under each listener (a native call would fire scroll and select later).
var redActs = map[string]string{
	"focus": "var e = document.querySelector('#a'); e.focus(); e.dispatchEvent(new FocusEvent('focus'))",
	"type": `var e = document.querySelector('#a'); e.focus(); e.value = 'ab';
		e.dispatchEvent(new KeyboardEvent('keydown', {key: 'a', bubbles: true}));
		e.dispatchEvent(new InputEvent('input', {data: 'a', bubbles: true}))`,
	"blur": `var e = document.querySelector('#a'); e.blur(); e.dispatchEvent(new FocusEvent('blur')); e.dispatchEvent(new Event('change', {bubbles: true}))`,
	"click": `var e = document.querySelector('#btn');
		e.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true})); e.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); e.click()`,
	"select": "document.querySelector('#a').dispatchEvent(new Event('select', {bubbles: true}))",
	"scroll": "document.querySelector('#sc').dispatchEvent(new Event('scroll'))",
}

func (d *drv) Act(name string) (string, error) {
	if !d.native {
		return "Runtime.evaluate", d.Eval("() => { " + redActs[name] + " }")
	}
	switch name {
	case "focus":
		return "DOM.focus", d.domFocus("#a")
	case "type":
		if err := d.domFocus("#a"); err != nil {
			return "", err
		}
		for _, c := range "ab" {
			for _, t := range []string{"keyDown", "keyUp"} {
				a := input.NewDispatchKeyEventArgs(t).SetKey(string(c))
				if t == "keyDown" {
					a.SetText(string(c))
				}
				if err := d.c.Input.DispatchKeyEvent(d.ctx, a); err != nil {
					return "", err
				}
			}
		}
		return "Input.dispatchKeyEvent", nil
	case "blur":
		return "Input.dispatchMouseEvent on #b", d.mouse("#b", 1)
	case "click":
		return "Input.dispatchMouseEvent on #btn", d.mouse("#btn", 1)
	case "select":
		return "Input.dispatchMouseEvent clickCount 3 on #a", d.mouse("#a", 3)
	case "scroll":
		x, y, err := d.center("#sc")
		if err != nil {
			return "", err
		}
		return "Input.dispatchMouseEvent mouseWheel", d.c.Input.DispatchMouseEvent(d.ctx, input.NewDispatchMouseEventArgs("mouseWheel", x, y).SetDeltaX(0).SetDeltaY(40))
	}
	return "", workload.NA("unknown action")
}

func (d *drv) node(sel string) (dom.NodeID, error) {
	doc, err := d.c.DOM.GetDocument(d.ctx, nil)
	if err != nil {
		return 0, err
	}
	q, err := d.c.DOM.QuerySelector(d.ctx, dom.NewQuerySelectorArgs(doc.Root.NodeID, sel))
	return q.NodeID, err
}

func (d *drv) domFocus(sel string) error {
	n, err := d.node(sel)
	if err != nil {
		return err
	}
	return d.c.DOM.Focus(d.ctx, dom.NewFocusArgs().SetNodeID(n))
}

func (d *drv) center(sel string) (float64, float64, error) {
	n, err := d.node(sel)
	if err != nil {
		return 0, 0, err
	}
	b, err := d.c.DOM.GetBoxModel(d.ctx, dom.NewGetBoxModelArgs().SetNodeID(n))
	if err != nil {
		return 0, 0, err
	}
	q := b.Model.Content
	return (q[0] + q[4]) / 2, (q[1] + q[5]) / 2, nil
}

func (d *drv) mouse(sel string, clicks int) error {
	x, y, err := d.center(sel)
	if err != nil {
		return err
	}
	for _, t := range []string{"mouseMoved", "mousePressed", "mouseReleased"} {
		a := input.NewDispatchMouseEventArgs(t, x, y).SetButton(input.MouseButtonLeft).SetClickCount(clicks)
		if err := d.c.Input.DispatchMouseEvent(d.ctx, a); err != nil {
			return err
		}
	}
	return nil
}

func orderedHeaders(raw []byte) ([]fetch.HeaderEntry, error) {
	kv, err := workload.OrderedHeaders(raw)
	var out []fetch.HeaderEntry
	for _, h := range kv {
		out = append(out, fetch.HeaderEntry{Name: h[0], Value: h[1]})
	}
	return out, err
}

// Route: red continues with the headers reversed and lower-cased (the defect the judge must catch); native continues
// with none of them touched, and on override with the original order plus X-Probe.
func (d *drv) Route(cond string) (func(), error) {
	if cond == "plain" {
		return func() {}, nil
	}
	pat := "*"
	if err := d.c.Fetch.Enable(d.ctx, fetch.NewEnableArgs().SetPatterns([]fetch.RequestPattern{{URLPattern: &pat}})); err != nil {
		return nil, err
	}
	ctx, cancel := context.WithCancel(d.ctx)
	rp, err := d.c.Fetch.RequestPaused(ctx)
	if err != nil {
		cancel()
		return nil, err
	}
	go func() {
		for {
			ev, err := rp.Recv()
			if err != nil {
				return
			}
			a := fetch.NewContinueRequestArgs(ev.RequestID)
			hs, herr := orderedHeaders(ev.Request.Headers)
			switch {
			case herr != nil:
			case !d.native:
				var rev []fetch.HeaderEntry
				for i := len(hs) - 1; i >= 0; i-- {
					rev = append(rev, fetch.HeaderEntry{Name: strings.ToLower(hs[i].Name), Value: hs[i].Value})
				}
				if cond == "override" {
					rev = append(rev, fetch.HeaderEntry{Name: "x-probe", Value: "1"})
				}
				a.SetHeaders(rev)
			case cond == "override":
				a.SetHeaders(append(hs, fetch.HeaderEntry{Name: "X-Probe", Value: "1"}))
			}
			d.count("Fetch.continueRequest")
			d.c.Fetch.ContinueRequest(d.ctx, a)
		}
	}()
	return func() { cancel(); d.c.Fetch.Disable(d.ctx) }, nil
}

// nativeWait polls for the selector with DOM.querySelector, so the native arm runs no eval at all.
func (d *drv) nativeWait(sel string) error {
	for i := 0; i < 150; i++ {
		if _, err := d.node(sel); err == nil {
			return nil
		}
		time.Sleep(100 * time.Millisecond)
	}
	return fmt.Errorf("%s never appeared", sel)
}
