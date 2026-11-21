package main

import (
	"github.com/mafredri/cdp/protocol/fetch"

	"camoucrome/cdpfootprint/workload"
	"tdp"
)

// Act uses tdp's own API for each action; "via" names it. Nothing is emulated with an eval of our own.
func (d *drv) Act(name string) (string, error) {
	do := func(sel, via string, f func(*tdp.Element) error) (string, error) {
		e, err := d.p.ElementE(sel)
		if err != nil {
			return via, err
		}
		return via, f(e)
	}
	switch name {
	case "focus":
		return do("#a", "Element.FocusE", (*tdp.Element).FocusE)
	case "type":
		return "Element.ClickE+TypeE", d.Type("#a", "ab")
	case "blur":
		return do("#a", "Element.BlurE", (*tdp.Element).BlurE)
	case "click":
		return do("#btn", "Element.ClickE", func(e *tdp.Element) error { return e.ClickE() })
	case "select":
		return do("#a", "Element.DoubleClickE", func(e *tdp.Element) error { return e.DoubleClickE() })
	case "scroll":
		return "Page.ScrollAtE", d.p.ScrollAtE(70, 160, 0, 40)
	}
	return "", workload.NA("unknown action")
}

// Route: plain = nothing added (tdp's camoucrome mode already pauses every request and continues it); route = a request
// handler that continues; override = a handler that continues with X-Probe added, headers in Chrome's order.
func (d *drv) Route(cond string) (func(), error) {
	if cond == "plain" {
		return func() {}, nil
	}
	d.p.AddRequestHandler(".*", func(rc *tdp.RequestCtx) {
		a := fetch.NewContinueRequestArgs(rc.RequestId())
		if cond == "override" {
			if hs, err := workload.OrderedHeaders(rc.Request.Headers); err == nil {
				var out []fetch.HeaderEntry
				for _, h := range hs {
					out = append(out, fetch.HeaderEntry{Name: h[0], Value: h[1]})
				}
				a.SetHeaders(append(out, fetch.HeaderEntry{Name: "X-Probe", Value: "1"}))
			}
		}
		rc.ContinueRequest(a)
	})
	return func() { d.p.RemoveRequestHandler(".*") }, nil
}
