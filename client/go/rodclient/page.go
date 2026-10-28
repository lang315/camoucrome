package rodclient

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/rand"
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
// DOM.enable or Page.enable (page_unix_test.go asserts it for all ops). rod's
// own helpers are avoided where they enable domains or emulate.
//
// Goto polls document state from an ISOLATED world, so a page cannot hook the
// probe. It sends Page.getFrameTree, Page.createIsolatedWorld (no universal
// access), Runtime.evaluate{contextId} every 100 ms and Page.navigate; the
// world is recreated whenever a navigation destroys it. This is NOT covered by
// G0 (which measured Goto+Text with a different wait); measure it at Task 5.
// The other Runtime traffic is Runtime.callFunctionOn (Text; G0: harmless to
// stack timing) and main-world Runtime.evaluate (Eval only), also not
// separately measured.
//
// Input: the fork humanizes mouse and wheel events browser-side only.
// Keystroke timing is client-side with a fixed uniform 40-120 ms distribution.
type Page struct {
	p     *rod.Page
	rng   *rand.Rand
	world proto.RuntimeExecutionContextID // isolated world for Goto; 0 = none
	moved bool                            // the first Click has been made
}

// newRand and keyDelay are vars so tests can make input deterministic.
var (
	newRand  = func() *rand.Rand { return rand.New(rand.NewSource(time.Now().UnixNano())) }
	keyDelay = func(r *rand.Rand) time.Duration { return time.Duration(40+r.Intn(81)) * time.Millisecond }
)

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
	gotoEvery      = 100 * time.Millisecond
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
func poll(ctx context.Context, every time.Duration, f func() (bool, error)) error {
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
		case <-time.After(every):
		}
	}
}

// stateJS is "origin|readyState|resourceCount": origin changes with every new
// document, so a stale about:blank (already "complete") cannot end Goto early.
const stateJS = `performance.timeOrigin+"|"+document.readyState+"|"+performance.getEntriesByType("resource").length`

// gone reports an error that means the session or target is dead, as opposed
// to a context destroyed by navigation.
func gone(err error) bool {
	if errors.Is(err, io.EOF) || errors.Is(err, io.ErrUnexpectedEOF) {
		return true
	}
	m := err.Error()
	for _, s := range []string{"Session with given id not found", "No session with given id",
		"No target with given id", "Target closed", "Browser closed"} {
		if strings.Contains(m, s) {
			return true
		}
	}
	return false
}

// soft keeps a retryable error in *last; a dead session is returned.
func soft(err error, last *error) error {
	if gone(err) {
		return err
	}
	*last = err
	return nil
}

// probe reads the document state in the isolated world, (re)creating it when
// there is none; any failure drops the world so the next probe recreates it.
func (p *Page) probe(rp *rod.Page) (origin, ready, res string, err error) {
	defer func() {
		if err != nil {
			p.world = 0
		}
	}()
	if p.world == 0 {
		ft, err := proto.PageGetFrameTree{}.Call(rp)
		if err != nil {
			return "", "", "", err
		}
		w, err := proto.PageCreateIsolatedWorld{FrameID: ft.FrameTree.Frame.ID}.Call(rp)
		if err != nil {
			return "", "", "", err
		}
		p.world = w.ExecutionContextID
	}
	r, err := proto.RuntimeEvaluate{Expression: stateJS, ContextID: p.world, ReturnByValue: true}.Call(rp)
	if err != nil {
		return "", "", "", err
	}
	if r.ExceptionDetails != nil {
		return "", "", "", errors.New(r.ExceptionDetails.Text)
	}
	f := strings.Split(r.Result.Value.Str(), "|")
	if len(f) != 3 {
		return "", "", "", fmt.Errorf("unexpected state %q", r.Result.Value.Str())
	}
	return f[0], f[1], f[2], nil
}

// Goto navigates and waits (default 30 s, ctx deadline wins). Page.navigate
// only; no Page.enable, so load is observed by polling document state (see
// Page). A poll error such as a context destroyed by the navigation means
// "not ready yet"; only a dead session ends the wait early, and at the timeout
// the last poll error is reported. Limit: a same-document navigation (hash
// change) keeps the origin and times out.
func (p *Page) Goto(ctx context.Context, url string, w WaitUntil) error {
	ctx, cancel := opCtx(ctx)
	defer cancel()
	rp := p.bind(ctx)
	var last error
	observe := func() (o, ready, n string, ok bool, fatal error) {
		o, ready, n, err := p.probe(rp)
		if err != nil {
			return "", "", "", false, soft(err, &last)
		}
		last = nil
		return o, ready, n, true, nil
	}
	fail := func(err error) error {
		if last != nil && ctx.Err() != nil {
			return fmt.Errorf("rodclient: goto %s: %w (last poll error: %v)", url, err, last)
		}
		return fmt.Errorf("rodclient: goto %s: %w", url, err)
	}
	var old string
	if err := poll(ctx, gotoEvery, func() (bool, error) {
		o, _, _, ok, fatal := observe()
		if ok {
			old = o
		}
		return ok, fatal
	}); err != nil {
		return fail(err)
	}
	res, err := proto.PageNavigate{URL: url}.Call(rp)
	if err != nil {
		return fail(err)
	}
	if res.ErrorText != "" {
		return fmt.Errorf("rodclient: goto %s: %s", url, res.ErrorText)
	}
	var lastRes string
	var since time.Time
	if err := poll(ctx, gotoEvery, func() (bool, error) {
		o, ready, n, ok, fatal := observe()
		if !ok || o == old || ready != "complete" {
			return false, fatal
		}
		if w == WaitLoad {
			return true, nil
		}
		if n != lastRes || since.IsZero() {
			lastRes, since = n, time.Now()
		}
		return time.Since(since) >= idleFor, nil
	}); err != nil {
		return fail(err)
	}
	return nil
}

// find polls DOM.getDocument + DOM.querySelector until the selector matches.
// DOM.* queries work without DOM.enable. Node ids are valid until the next
// getDocument, so each op re-resolves.
func (p *Page) find(ctx context.Context, rp *rod.Page, selector string) (proto.DOMNodeID, error) {
	var id proto.DOMNodeID
	err := poll(ctx, pollEvery, func() (bool, error) {
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

// WaitForSelector errors when selector has not matched within timeout
// (timeout <= 0 means the 30 s default).
func (p *Page) WaitForSelector(ctx context.Context, selector string, timeout time.Duration) error {
	if timeout <= 0 {
		timeout = defaultTimeout
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	if _, err := p.find(ctx, p.bind(ctx), selector); err != nil {
		return fmt.Errorf("rodclient: wait: %w", err)
	}
	return nil
}

// Click scrolls the element into view, then sends mouseMoved, mousePressed and
// mouseReleased at the centre of its content box through Input.dispatchMouseEvent
// (Buttons bitmask set as a real mouse does). The fork humanizes
// dispatchMouseEvent browser-side, but its SP2b path needs a previous move on
// the same widget, so the first Click on a Page first moves to a random start
// point. A box that is not laid out yet is retried until the op timeout.
func (p *Page) Click(ctx context.Context, selector string) error {
	ctx, cancel := opCtx(ctx)
	defer cancel()
	rp := p.bind(ctx)
	id, err := p.find(ctx, rp, selector)
	if err != nil {
		return fmt.Errorf("rodclient: click: %w", err)
	}
	var q []float64
	var last error
	err = poll(ctx, pollEvery, func() (bool, error) {
		if err := (proto.DOMScrollIntoViewIfNeeded{NodeID: id}).Call(rp); err != nil {
			return false, soft(err, &last)
		}
		box, err := proto.DOMGetBoxModel{NodeID: id}.Call(rp)
		if err != nil {
			return false, soft(err, &last)
		}
		if q = box.Model.Content; len(q) != 8 {
			last = fmt.Errorf("box of %d numbers", len(q))
			return false, nil
		}
		return true, nil
	})
	if err != nil {
		if last != nil {
			err = fmt.Errorf("%w (last error: %v)", err, last)
		}
		return fmt.Errorf("rodclient: click: %w", err)
	}
	mouse := func(t proto.InputDispatchMouseEventType, x, y float64, buttons int) error {
		ev := proto.InputDispatchMouseEvent{Type: t, X: x, Y: y, Buttons: &buttons}
		if t != proto.InputDispatchMouseEventTypeMouseMoved {
			ev.Button, ev.ClickCount = proto.InputMouseButtonLeft, 1
		}
		if err := ev.Call(rp); err != nil {
			return fmt.Errorf("rodclient: click: %w", err)
		}
		return nil
	}
	if !p.moved {
		if err := mouse(proto.InputDispatchMouseEventTypeMouseMoved, float64(50+p.rng.Intn(251)), float64(50+p.rng.Intn(151)), 0); err != nil {
			return err
		}
		p.moved = true
	}
	x := (q[0] + q[2] + q[4] + q[6]) / 4
	y := (q[1] + q[3] + q[5] + q[7]) / 4
	for _, s := range []struct {
		t       proto.InputDispatchMouseEventType
		buttons int
	}{{proto.InputDispatchMouseEventTypeMouseMoved, 0}, {proto.InputDispatchMouseEventTypeMousePressed, 1},
		{proto.InputDispatchMouseEventTypeMouseReleased, 0}} {
		if err := mouse(s.t, x, y, s.buttons); err != nil {
			return err
		}
	}
	return nil
}

// Type focuses the element (DOM.focus), then sends each rune on a US layout as
// Input.dispatchKeyEvent keyDown{key,code,text,windowsVirtualKeyCode} and
// keyUp, with a uniform 40-120 ms delay between characters. Runes off the
// layout (accents, CJK, emoji) go through Input.insertText. Shift is carried
// as the modifier bit; no separate Shift key events are sent. The fork does
// not humanize keys, so this timing is client-side and fixed.
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
	runes := []rune(text)
	for i, r := range runes {
		if err := ctx.Err(); err != nil {
			return fmt.Errorf("rodclient: type: %w", err)
		}
		if err := p.key(rp, r); err != nil {
			return fmt.Errorf("rodclient: type: %w", err)
		}
		if d := keyDelay(p.rng); d > 0 && i < len(runes)-1 {
			select {
			case <-ctx.Done():
				return fmt.Errorf("rodclient: type: %w", ctx.Err())
			case <-time.After(d):
			}
		}
	}
	return nil
}

func (p *Page) key(rp *rod.Page, r rune) error {
	k, ok := usKey(r)
	if !ok {
		return proto.InputInsertText{Text: string(r)}.Call(rp)
	}
	down := proto.InputDispatchKeyEvent{Type: proto.InputDispatchKeyEventTypeKeyDown, Key: k.key, Code: k.code,
		Text: k.text, WindowsVirtualKeyCode: k.vk, Modifiers: k.mod}
	if err := down.Call(rp); err != nil {
		return err
	}
	return proto.InputDispatchKeyEvent{Type: proto.InputDispatchKeyEventTypeKeyUp, Key: k.key, Code: k.code,
		WindowsVirtualKeyCode: k.vk, Modifiers: k.mod}.Call(rp)
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
