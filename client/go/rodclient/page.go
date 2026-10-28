package rodclient

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/go-rod/rod"
	"github.com/go-rod/rod/lib/proto"
)

// Page offers vetted operations only. rod's page API is unreachable from
// outside this package: no embedding, no exported field, no accessor.
//
// Every op is raw proto calls on the page session, chosen so that none sends
// Runtime.enable, Emulation.*, Network.setUserAgentOverride, Network.enable,
// DOM.enable or Page.enable (page_test.go asserts it for all ops). rod's own
// helpers are avoided where they enable domains or emulate (Page.Screenshot).
// The only Runtime traffic is Runtime.evaluate / Runtime.callFunctionOn, which
// G0 measured as harmless to the stack-timing signal; G0 measured only the
// Goto+Text path, the other ops are not separately measured.
type Page struct {
	p *rod.Page
}

// WaitUntil picks when Goto returns.
type WaitUntil int

const (
	// WaitLoad returns once the new document's readyState is "complete".
	WaitLoad WaitUntil = iota
	// WaitNetworkIdle is WaitLoad plus no new resource entries for 500 ms.
	WaitNetworkIdle
)

// Cookie is the subset of a CDP cookie callers need.
type Cookie struct {
	Name, Value, Domain, Path string
	Expires                   float64 // seconds since epoch; -1 for a session cookie
	HTTPOnly, Secure          bool
	SameSite                  string
}

const (
	defaultTimeout = 30 * time.Second
	pollEvery      = 50 * time.Millisecond
	idleFor        = 500 * time.Millisecond
)

// opCtx bounds an op: a ctx deadline wins, otherwise 30 s.
func opCtx(ctx context.Context) (context.Context, context.CancelFunc) {
	if _, ok := ctx.Deadline(); ok {
		return ctx, func() {}
	}
	return context.WithTimeout(ctx, defaultTimeout)
}

// bind returns the rod page whose calls honour ctx.
func (p *Page) bind(ctx context.Context) *rod.Page { return p.p.Context(ctx) }

// poll runs f every pollEvery until it reports done, errors or ctx ends.
func poll(ctx context.Context, f func() (bool, error)) error {
	for {
		done, err := f()
		if err != nil {
			return err
		}
		if done {
			return nil
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(pollEvery):
		}
	}
}

// state is "origin|readyState|resourceCount": origin changes with every new
// document, so a stale about:blank (already "complete") cannot end Goto early.
const stateJS = `performance.timeOrigin+"|"+document.readyState+"|"+performance.getEntriesByType("resource").length`

func (p *Page) state(rp *rod.Page) (origin, ready string, res string, err error) {
	r, err := proto.RuntimeEvaluate{Expression: stateJS, ReturnByValue: true}.Call(rp)
	if err != nil {
		return
	}
	if r.ExceptionDetails != nil {
		err = errors.New(r.ExceptionDetails.Text)
		return
	}
	f := strings.Split(r.Result.Value.Str(), "|")
	if len(f) != 3 {
		err = fmt.Errorf("unexpected state %q", r.Result.Value.Str())
		return
	}
	return f[0], f[1], f[2], nil
}

// Goto navigates and waits (default 30 s, ctx deadline wins). Page.navigate
// only; no Page.enable, so load is observed by polling document state.
// Limit: a same-document navigation (hash change) keeps the origin and times out.
func (p *Page) Goto(ctx context.Context, url string, w WaitUntil) error {
	ctx, cancel := opCtx(ctx)
	defer cancel()
	rp := p.bind(ctx)
	old, _, _, err := p.state(rp)
	if err != nil {
		return fmt.Errorf("rodclient: goto: %w", err)
	}
	res, err := proto.PageNavigate{URL: url}.Call(rp)
	if err != nil {
		return fmt.Errorf("rodclient: goto: %w", err)
	}
	if res.ErrorText != "" {
		return fmt.Errorf("rodclient: goto: %s", res.ErrorText)
	}
	var lastRes string
	var since time.Time
	err = poll(ctx, func() (bool, error) {
		o, ready, n, err := p.state(rp)
		if err != nil {
			return false, err
		}
		if o == old || ready != "complete" {
			return false, nil
		}
		if w == WaitLoad {
			return true, nil
		}
		if n != lastRes || since.IsZero() {
			lastRes, since = n, time.Now()
		}
		return time.Since(since) >= idleFor, nil
	})
	if err != nil {
		return fmt.Errorf("rodclient: goto %s: %w", url, err)
	}
	return nil
}

// find polls DOM.getDocument + DOM.querySelector until the selector matches.
// DOM.* queries work without DOM.enable. Node ids are valid until the next
// getDocument, so each op re-resolves.
func (p *Page) find(ctx context.Context, rp *rod.Page, selector string) (proto.DOMNodeID, error) {
	var id proto.DOMNodeID
	err := poll(ctx, func() (bool, error) {
		doc, err := proto.DOMGetDocument{}.Call(rp)
		if err != nil {
			return false, err
		}
		q, err := proto.DOMQuerySelector{NodeID: doc.Root.NodeID, Selector: selector}.Call(rp)
		if err != nil {
			// an invalid selector is permanent, not "not there yet"
			if strings.Contains(err.Error(), "not a valid selector") {
				return false, err
			}
			return false, nil
		}
		id = q.NodeID
		return id != 0, nil
	})
	if err != nil {
		return 0, fmt.Errorf("selector %q: %w", selector, err)
	}
	return id, nil
}

// WaitForSelector errors when selector has not matched within timeout.
func (p *Page) WaitForSelector(ctx context.Context, selector string, timeout time.Duration) error {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	if _, err := p.find(ctx, p.bind(ctx), selector); err != nil {
		return fmt.Errorf("rodclient: wait: %w", err)
	}
	return nil
}

// Click scrolls the element into view, then sends mouseMoved, mousePressed and
// mouseReleased at the centre of its content box through Input.dispatchMouseEvent.
// The fork humanizes dispatchMouseEvent browser-side; there is no client-side path.
func (p *Page) Click(ctx context.Context, selector string) error {
	ctx, cancel := opCtx(ctx)
	defer cancel()
	rp := p.bind(ctx)
	id, err := p.find(ctx, rp, selector)
	if err != nil {
		return fmt.Errorf("rodclient: click: %w", err)
	}
	if err := (proto.DOMScrollIntoViewIfNeeded{NodeID: id}).Call(rp); err != nil {
		return fmt.Errorf("rodclient: click: %w", err)
	}
	box, err := proto.DOMGetBoxModel{NodeID: id}.Call(rp)
	if err != nil {
		return fmt.Errorf("rodclient: click: %w", err)
	}
	q := box.Model.Content
	if len(q) != 8 {
		return fmt.Errorf("rodclient: click: box of %d numbers", len(q))
	}
	x := (q[0] + q[2] + q[4] + q[6]) / 4
	y := (q[1] + q[3] + q[5] + q[7]) / 4
	for _, t := range []proto.InputDispatchMouseEventType{proto.InputDispatchMouseEventTypeMouseMoved,
		proto.InputDispatchMouseEventTypeMousePressed, proto.InputDispatchMouseEventTypeMouseReleased} {
		ev := proto.InputDispatchMouseEvent{Type: t, X: x, Y: y}
		if t != proto.InputDispatchMouseEventTypeMouseMoved {
			ev.Button, ev.ClickCount = proto.InputMouseButtonLeft, 1
		}
		if err := ev.Call(rp); err != nil {
			return fmt.Errorf("rodclient: click: %w", err)
		}
	}
	return nil
}

// Type focuses the element (DOM.focus) and inserts text with Input.insertText.
// insertText fires one input event and no key events: no per-character key
// mapping to get wrong, and no keystroke timing to fake client-side. A page
// that listens for keydown will not see it; that is the known limit of v1.
func (p *Page) Type(ctx context.Context, selector, text string) error {
	ctx, cancel := opCtx(ctx)
	defer cancel()
	rp := p.bind(ctx)
	id, err := p.find(ctx, rp, selector)
	if err != nil {
		return fmt.Errorf("rodclient: type: %w", err)
	}
	if err := (proto.DOMFocus{NodeID: id}).Call(rp); err != nil {
		return fmt.Errorf("rodclient: type: %w", err)
	}
	if err := (proto.InputInsertText{Text: text}).Call(rp); err != nil {
		return fmt.Errorf("rodclient: type: %w", err)
	}
	return nil
}

// Text is the element's innerText. It resolves the node and calls a function
// on it (Runtime.callFunctionOn), the one Runtime call G0 measured as harmless.
func (p *Page) Text(ctx context.Context, selector string) (string, error) {
	ctx, cancel := opCtx(ctx)
	defer cancel()
	rp := p.bind(ctx)
	id, err := p.find(ctx, rp, selector)
	if err != nil {
		return "", fmt.Errorf("rodclient: text: %w", err)
	}
	obj, err := proto.DOMResolveNode{NodeID: id}.Call(rp)
	if err != nil {
		return "", fmt.Errorf("rodclient: text: %w", err)
	}
	r, err := proto.RuntimeCallFunctionOn{ObjectID: obj.Object.ObjectID,
		FunctionDeclaration: "function(){return this.innerText}", ReturnByValue: true}.Call(rp)
	if err != nil {
		return "", fmt.Errorf("rodclient: text: %w", err)
	}
	if r.ExceptionDetails != nil {
		return "", fmt.Errorf("rodclient: text: %s", r.ExceptionDetails.Text)
	}
	return r.Result.Value.Str(), nil
}

// Attribute reads one attribute through DOM.getAttributes (no JS); a missing
// attribute is an error.
func (p *Page) Attribute(ctx context.Context, selector, name string) (string, error) {
	ctx, cancel := opCtx(ctx)
	defer cancel()
	rp := p.bind(ctx)
	id, err := p.find(ctx, rp, selector)
	if err != nil {
		return "", fmt.Errorf("rodclient: attribute: %w", err)
	}
	r, err := proto.DOMGetAttributes{NodeID: id}.Call(rp)
	if err != nil {
		return "", fmt.Errorf("rodclient: attribute: %w", err)
	}
	for i := 0; i+1 < len(r.Attributes); i += 2 {
		if r.Attributes[i] == name {
			return r.Attributes[i+1], nil
		}
	}
	return "", fmt.Errorf("rodclient: attribute: %q has no attribute %q", selector, name)
}

// Screenshot is a raw Page.captureScreenshot (PNG): no clip, no
// Emulation.setDeviceMetricsOverride. rod's Page.Screenshot is not used.
func (p *Page) Screenshot(ctx context.Context) ([]byte, error) {
	ctx, cancel := opCtx(ctx)
	defer cancel()
	r, err := proto.PageCaptureScreenshot{Format: proto.PageCaptureScreenshotFormatPng}.Call(p.bind(ctx))
	if err != nil {
		return nil, fmt.Errorf("rodclient: screenshot: %w", err)
	}
	return r.Data, nil
}

// Cookies is Network.getCookies for the page URL; it needs no Network.enable.
func (p *Page) Cookies(ctx context.Context) ([]Cookie, error) {
	ctx, cancel := opCtx(ctx)
	defer cancel()
	r, err := proto.NetworkGetCookies{}.Call(p.bind(ctx))
	if err != nil {
		return nil, fmt.Errorf("rodclient: cookies: %w", err)
	}
	out := make([]Cookie, len(r.Cookies))
	for i, c := range r.Cookies {
		out[i] = Cookie{c.Name, c.Value, c.Domain, c.Path, float64(c.Expires), c.HTTPOnly, c.Secure, string(c.SameSite)}
	}
	return out, nil
}

// Eval runs js in the page's main world through Runtime.evaluate (no
// Runtime.enable), awaiting a returned promise. The result is the string
// itself, or JSON for any other value. The page can observe main-world
// evaluation timing; this op is the one place user JS is sent.
func (p *Page) Eval(ctx context.Context, js string) (string, error) {
	ctx, cancel := opCtx(ctx)
	defer cancel()
	r, err := proto.RuntimeEvaluate{Expression: js, ReturnByValue: true, AwaitPromise: true}.Call(p.bind(ctx))
	if err != nil {
		return "", fmt.Errorf("rodclient: eval: %w", err)
	}
	if r.ExceptionDetails != nil {
		return "", fmt.Errorf("rodclient: eval: %s", r.ExceptionDetails.Text)
	}
	v := r.Result.Value.Val()
	if s, ok := v.(string); ok {
		return s, nil
	}
	if v == nil {
		return "", nil
	}
	b, err := json.Marshal(v)
	return string(b), err
}

// Close closes the page (Page.close).
func (p *Page) Close(ctx context.Context) error {
	ctx, cancel := opCtx(ctx)
	defer cancel()
	if err := (proto.PageClose{}).Call(p.bind(ctx)); err != nil {
		return fmt.Errorf("rodclient: close: %w", err)
	}
	return nil
}
