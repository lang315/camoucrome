//go:build unix

package rodclient

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"math/rand"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"

	camoucrome "github.com/lang315/camoucrome/client/go"
	"github.com/lang315/camoucrome/client/go/rodclient/internal/browser"
)

// A fake page: logs each request as one JSON line and answers the CDP methods
// the vetted ops use. "#missing" never matches. The state expression reports
// the number of Page.navigate calls seen as the document origin.
const fakePage = `#!/usr/bin/env python3
import json, os, sys, base64, time
r, w = os.fdopen(3, "rb", 0), os.fdopen(4, "wb", 0)
log = open(os.environ["FAKE_LOG"], "a")
buf = b""
navs = 0
polls = 0
boxes = 0
ev = os.environ.get
while True:
    d = r.read(1 << 20)
    if not d:
        sys.exit(0)
    buf += d
    while b"\0" in buf:
        m, buf = buf.split(b"\0", 1)
        q = json.loads(m)
        log.write(json.dumps(q) + "\n"); log.flush()
        me, p = q["method"], q.get("params", {})
        if me == ev("FAKE_HANG"):
            continue
        if me == "DOM.querySelector" and ev("FAKE_QS_ERR"):
            w.write(json.dumps({"id": q["id"], "error": {"code": -32000, "message": ev("FAKE_QS_ERR")}}).encode() + b"\0")
            continue
        err = None
        res = {"targetId": "T", "sessionId": "S", "frameId": "F"}
        if me == "Page.navigate":
            navs += 1
            res = {"frameId": "F", "loaderId": "L"}
        elif me == "Runtime.evaluate":
            if "contextId" in p:
                polls += 1
                n = int(ev("FAKE_FAIL_POLLS", "0"))
                if n < 0 or polls <= n:
                    err = {"code": -32000, "message": ev("FAKE_POLL_ERR", "Cannot find context with specified id")}
                v = "%d|%s|3" % (navs, "loading" if ev("FAKE_NEVER_COMPLETE") else "complete")
            else:
                v = "evalresult"
            res = {"result": {"type": "string", "value": v}}
        elif me == "Page.getFrameTree":
            res = {"frameTree": {"frame": {"id": "F", "loaderId": "L", "url": "", "domainAndRegistry": "", "securityOrigin": "", "mimeType": "", "secureContextType": "Secure", "crossOriginIsolatedContextType": "NotIsolated", "gatedAPIFeatures": []}}}
        elif me == "Page.createIsolatedWorld":
            res = {"executionContextId": 7}
        elif me == "DOM.getDocument":
            res = {"root": {"nodeId": 1, "backendNodeId": 1, "nodeType": 9, "nodeName": "#document", "localName": "", "nodeValue": ""}}
        elif me == "DOM.querySelector":
            res = {"nodeId": 0 if p.get("selector") == "#missing" else 2}
        elif me == "DOM.getBoxModel":
            boxes += 1
            if boxes <= int(ev("FAKE_BOX_FAILS", "0")):
                err = {"code": -32000, "message": "Could not compute box model."}
            c = [10, 20, 111, 20, 111, 61, 10, 61]
            res = {"model": {"content": c, "padding": c, "border": c, "margin": c, "width": 101, "height": 41}}
        elif me == "DOM.resolveNode":
            res = {"object": {"type": "object", "objectId": "O"}}
        elif me == "Runtime.callFunctionOn":
            res = {"result": {"type": "string", "value": "hello"}}
        elif me == "DOM.getAttributes":
            res = {"attributes": ["id", "x", "href", "/y"]}
        elif me == "Page.captureScreenshot":
            res = {"data": base64.b64encode(b"PNG").decode()}
        elif me == "Page.getLayoutMetrics":
            z = {"x": 0, "y": 0, "width": 800, "height": 600}
            vw, vh = [int(x) for x in ev("FAKE_VIEWPORT", "800x600").split("x")]
            res = {"layoutViewport": {"pageX": 0, "pageY": 0, "clientWidth": 800, "clientHeight": 600},
                   "visualViewport": {"offsetX": 0, "offsetY": 0, "pageX": 0, "pageY": 0, "clientWidth": 800, "clientHeight": 600, "scale": 1},
                   "contentSize": z, "cssLayoutViewport": {"pageX": 0, "pageY": 0, "clientWidth": vw, "clientHeight": vh},
                   "cssVisualViewport": {"offsetX": 0, "offsetY": 0, "pageX": 0, "pageY": 0, "clientWidth": 800, "clientHeight": 600, "scale": 1},
                   "cssContentSize": z}
        elif me == "Network.getCookies":
            res = {"cookies": [{"name": "a", "value": "b", "domain": "d", "path": "/", "expires": -1, "size": 2,
                                "httpOnly": True, "secure": False, "session": True, "priority": "Medium",
                                "sameParty": False, "sourceScheme": "Unset", "sourcePort": 80, "sameSite": "Lax"}]}
        out = {"id": q["id"], "error": err} if err else {"id": q["id"], "result": res}
        w.write(json.dumps(out).encode() + b"\0")
        if me == "Browser.close" and not ev("FAKE_NO_EXIT"):
            time.sleep(float(ev("FAKE_EXIT_DELAY", "0")))
            ud = [x.split("=", 1)[1] for x in sys.argv if x.startswith("--user-data-dir=")]
            if ud:
                open(ud[0] + "/exit.txt", "w").write("done")
            sys.exit(0)
`

type req struct {
	Method string
	Params map[string]any
}

type rig struct {
	t    *testing.T
	b    *Browser
	p    *Page
	log  string
	seen int // log lines already consumed
}

func newRig(t *testing.T) *rig {
	t.Helper()
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not on PATH")
	}
	oldRand := newRand
	t.Cleanup(func() { newRand = oldRand })
	newRand = func() *rand.Rand { return rand.New(rand.NewSource(1)) }
	dir := t.TempDir()
	exe := filepath.Join(dir, "fake-browser")
	if err := os.WriteFile(exe, []byte(fakePage), 0o755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("FAKE_LOG", filepath.Join(dir, "req.jsonl"))
	b, err := Launch(context.Background(), camoucrome.Options{ExecutablePath: exe})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { b.Close() })
	p, err := b.NewPage(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	r := &rig{t: t, b: b, p: p, log: filepath.Join(dir, "req.jsonl")}
	r.drain()
	return r
}

// drain returns the requests logged since the last drain.
func (r *rig) drain() []req {
	raw, _ := os.ReadFile(r.log)
	lines := strings.Split(strings.TrimSpace(string(raw)), "\n")
	var out []req
	for i := r.seen; i < len(lines); i++ {
		var q req
		if lines[i] == "" || json.Unmarshal([]byte(lines[i]), &q) != nil {
			continue
		}
		out = append(out, q)
	}
	r.seen = len(lines)
	return out
}

func methodSet(rs []req) []string {
	m := map[string]bool{}
	for _, q := range rs {
		m[q.Method] = true
	}
	var out []string
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// forbidden lists what no Page op may send. Page.enable is in it because only
// Browser.NewPage sends one (TestNewPageExactMethods); the ops start after that
// point, so it must not appear among their requests. DOM.enable is likewise
// never sent (DOM.getDocument activates the DOM agent implicitly, silently).
func forbidden(m string) bool {
	return m == "Runtime.enable" || m == "Network.enable" || m == "Network.setUserAgentOverride" ||
		strings.HasPrefix(m, "Emulation.") || m == "DOM.enable" || m == "Page.enable"
}

// launchRaw is newRig's launch with options and without draining.
func launchRaw(t *testing.T, opts ...Option) {
	t.Helper()
	dir := t.TempDir()
	exe := filepath.Join(dir, "fake-browser")
	if err := os.WriteFile(exe, []byte(fakePage), 0o755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("FAKE_LOG", filepath.Join(dir, "req.jsonl"))
	b, err := Launch(context.Background(), camoucrome.Options{ExecutablePath: exe}, opts...)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { b.Close() })
}

func TestSendObserverSeesConnectTraffic(t *testing.T) {
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not on PATH")
	}
	var with []string
	launchRaw(t, WithSendObserver(func(m []byte) {
		var q struct{ Method string }
		json.Unmarshal(m, &q)
		with = append(with, q.Method)
	}))
	if !contains(with, "Target.setDiscoverTargets") {
		t.Errorf("WithSendObserver missed connect-time traffic: %v", with)
	}
	// OnSend after Launch returns cannot see it: this is why the option exists.
	var after []string
	dir := t.TempDir()
	exe := filepath.Join(dir, "fake-browser")
	os.WriteFile(exe, []byte(fakePage), 0o755)
	t.Setenv("FAKE_LOG", filepath.Join(dir, "req.jsonl"))
	b, err := Launch(context.Background(), camoucrome.Options{ExecutablePath: exe})
	if err != nil {
		t.Fatal(err)
	}
	defer b.Close()
	b.OnSend(func(m []byte) { after = append(after, string(m)) })
	if _, err := b.NewPage(context.Background()); err != nil {
		t.Fatal(err)
	}
	for _, m := range after {
		if strings.Contains(m, "Target.setDiscoverTargets") {
			t.Errorf("OnSend saw connect-time message: %s", m)
		}
	}
}

func TestPageOps(t *testing.T) {
	ctx := context.Background()
	r := newRig(t)
	var all []req
	check := func(name string, want ...string) []req {
		t.Helper()
		got := r.drain()
		all = append(all, got...)
		if g := strings.Join(methodSet(got), " "); g != strings.Join(want, " ") {
			t.Errorf("%s sent\n got %s\nwant %s", name, g, strings.Join(want, " "))
		}
		return got
	}

	if err := r.p.Goto(ctx, "http://127.0.0.1/", WaitLoad); err != nil {
		t.Fatal(err)
	}
	got := check("Goto", "Page.createIsolatedWorld", "Page.getFrameTree", "Page.navigate", "Runtime.evaluate")
	for _, q := range got {
		if q.Method == "Runtime.evaluate" && q.Params["contextId"] != float64(7) {
			t.Errorf("Goto probe ran in the main world: %v", q.Params)
		}
	}

	if err := r.p.Click(ctx, "#b"); err != nil {
		t.Fatal(err)
	}
	got = check("Click", "DOM.getBoxModel", "DOM.getDocument", "DOM.querySelector", "DOM.scrollIntoViewIfNeeded", "Input.dispatchMouseEvent", "Page.getLayoutMetrics")
	checkMouse(t, got, true)

	if err := r.p.Type(ctx, "#i", "aé"); err != nil {
		t.Fatal(err)
	}
	got = check("Type", "DOM.focus", "DOM.getDocument", "DOM.querySelector", "Input.dispatchKeyEvent", "Input.insertText")

	if err := r.p.WaitForSelector(ctx, "#b", time.Second); err != nil {
		t.Fatal(err)
	}
	check("WaitForSelector", "DOM.getDocument", "DOM.querySelector")

	if s, err := r.p.Text(ctx, "#b"); err != nil || s != "hello" {
		t.Fatalf("Text = %q, %v", s, err)
	}
	check("Text", "DOM.getDocument", "DOM.querySelector", "DOM.resolveNode", "Runtime.callFunctionOn")

	if s, err := r.p.Attribute(ctx, "#b", "href"); err != nil || s != "/y" {
		t.Fatalf("Attribute = %q, %v", s, err)
	}
	check("Attribute", "DOM.getAttributes", "DOM.getDocument", "DOM.querySelector")
	if _, err := r.p.Attribute(ctx, "#b", "nope"); err == nil {
		t.Error("missing attribute gave no error")
	}
	r.drain()

	if png, err := r.p.Screenshot(ctx); err != nil || string(png) != "PNG" {
		t.Fatalf("Screenshot = %q, %v", png, err)
	}
	got = check("Screenshot", "Page.captureScreenshot")
	if _, ok := got[0].Params["clip"]; ok {
		t.Error("screenshot carries a clip")
	}

	if c, err := r.p.Cookies(ctx); err != nil || len(c) != 1 || c[0].Name != "a" || !c[0].HTTPOnly || c[0].SameSite != "Lax" {
		t.Fatalf("Cookies = %+v, %v", c, err)
	}
	check("Cookies", "Network.getCookies")

	if s, err := r.p.Eval(ctx, "1+1"); err != nil || s != "evalresult" {
		t.Fatalf("Eval = %q, %v", s, err)
	}
	got = check("Eval", "Runtime.evaluate")
	if got[0].Params["expression"] != "1+1" {
		t.Errorf("Eval expression %v", got[0].Params)
	}

	if err := r.p.AddInitScript(ctx, "window.__camou_init = 1"); err != nil {
		t.Fatal(err)
	}
	got = check("AddInitScript", "Page.addScriptToEvaluateOnNewDocument")
	if got[0].Params["source"] != "window.__camou_init = 1" {
		t.Errorf("AddInitScript params %v", got[0].Params)
	}

	if err := r.p.Close(ctx); err != nil {
		t.Fatal(err)
	}
	check("Close", "Page.close")

	for _, q := range all {
		if forbidden(q.Method) {
			t.Errorf("forbidden CDP method sent: %s", q.Method)
		}
	}
}

// WaitNetworkIdle still ends (the fake's resource count is constant).
func TestGotoNetworkIdle(t *testing.T) {
	r := newRig(t)
	start := time.Now()
	if err := r.p.Goto(context.Background(), "http://127.0.0.1/", WaitNetworkIdle); err != nil {
		t.Fatal(err)
	}
	if time.Since(start) < idleFor {
		t.Errorf("returned after %v, before the idle window", time.Since(start))
	}
}

func TestMissingSelectorTimesOut(t *testing.T) {
	r := newRig(t)
	ops := map[string]func(ctx context.Context) error{
		"WaitForSelector": func(ctx context.Context) error { return r.p.WaitForSelector(ctx, "#missing", 150*time.Millisecond) },
		"Click":           func(ctx context.Context) error { return r.p.Click(ctx, "#missing") },
		"Type":            func(ctx context.Context) error { return r.p.Type(ctx, "#missing", "x") },
		"Text":            func(ctx context.Context) error { _, err := r.p.Text(ctx, "#missing"); return err },
		"Attribute":       func(ctx context.Context) error { _, err := r.p.Attribute(ctx, "#missing", "id"); return err },
	}
	for name, f := range ops {
		t.Run(name, func(t *testing.T) {
			ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
			defer cancel()
			start := time.Now()
			err := f(ctx)
			if err == nil || time.Since(start) > 2*time.Second {
				t.Fatalf("err = %v after %v", err, time.Since(start))
			}
		})
	}
}

func TestCtxCancelAborts(t *testing.T) {
	r := newRig(t)
	ctx, cancel := context.WithCancel(context.Background())
	go func() { time.Sleep(100 * time.Millisecond); cancel() }()
	start := time.Now()
	err := r.p.Click(ctx, "#missing")
	if err == nil || time.Since(start) > 2*time.Second {
		t.Fatalf("err = %v after %v", err, time.Since(start))
	}
}

// checkMouse asserts the events of one Click: an optional start move (first
// click), then moved/pressed/released at the box centre with the Buttons mask.
func checkMouse(t *testing.T, got []req, first bool) {
	t.Helper()
	var evs []map[string]any
	for _, q := range got {
		if q.Method == "Input.dispatchMouseEvent" {
			evs = append(evs, q.Params)
		}
	}
	want := []string{"mouseMoved", "mousePressed", "mouseReleased"}
	if first {
		want = append([]string{"mouseMoved"}, want...)
	}
	var types []string
	for _, e := range evs {
		types = append(types, e["type"].(string))
	}
	if strings.Join(types, " ") != strings.Join(want, " ") {
		t.Fatalf("mouse events %v, want %v", types, want)
	}
	if first {
		x, y := evs[0]["x"].(float64), evs[0]["y"].(float64)
		if x < 50 || x > 300 || y < 50 || y > 200 {
			t.Errorf("start move (%v,%v) outside [50,300]x[50,200]", x, y)
		}
		evs = evs[1:]
	}
	buttons := []float64{0, 1, 0}
	for i, e := range evs {
		if math.Abs(e["x"].(float64)-60.5) > 1 || math.Abs(e["y"].(float64)-40.5) > 1 {
			t.Errorf("%v at (%v,%v), box centre is (60.5,40.5)", e["type"], e["x"], e["y"])
		}
		if b, ok := e["buttons"].(float64); !ok || b != buttons[i] {
			t.Errorf("%v buttons = %v, want %v", e["type"], e["buttons"], buttons[i])
		}
		if i > 0 && (e["button"] != "left" || e["clickCount"] != float64(1)) {
			t.Errorf("%v button/clickCount = %v/%v", e["type"], e["button"], e["clickCount"])
		}
	}
}

func TestSecondClickHasNoStartMove(t *testing.T) {
	r := newRig(t)
	ctx := context.Background()
	for i, first := range []bool{true, false} {
		if err := r.p.Click(ctx, "#b"); err != nil {
			t.Fatal(err)
		}
		t.Logf("click %d", i)
		checkMouse(t, r.drain(), first)
	}
}

func TestClickRetriesBoxModel(t *testing.T) {
	t.Setenv("FAKE_BOX_FAILS", "3")
	r := newRig(t)
	if err := r.p.Click(context.Background(), "#b"); err != nil {
		t.Fatal(err)
	}
	t.Setenv("FAKE_BOX_FAILS", "1000")
	r2 := newRig(t)
	ctx, cancel := context.WithTimeout(context.Background(), 300*time.Millisecond)
	defer cancel()
	err := r2.p.Click(ctx, "#b")
	if err == nil || !strings.Contains(err.Error(), "box model") {
		t.Fatalf("err = %v", err)
	}
}

func TestTypeKeys(t *testing.T) {
	setDelay(t, 0)
	r := newRig(t)
	if err := r.p.Type(context.Background(), "#i", "aB1é"); err != nil {
		t.Fatal(err)
	}
	var seq []string
	for _, q := range r.drain() {
		switch q.Method {
		case "Input.dispatchKeyEvent":
			seq = append(seq, fmt.Sprintf("%v:%v:%v:%v:%v:%v", q.Params["type"], q.Params["key"], q.Params["code"], q.Params["text"], q.Params["windowsVirtualKeyCode"], q.Params["modifiers"]))
		case "Input.insertText":
			seq = append(seq, "insert:"+q.Params["text"].(string))
		case "DOM.focus":
			seq = append(seq, "focus")
		}
	}
	want := []string{"focus",
		"keyDown:a:KeyA:a:65:<nil>", "keyUp:a:KeyA:<nil>:65:<nil>",
		"keyDown:B:KeyB:B:66:8", "keyUp:B:KeyB:<nil>:66:8",
		"keyDown:1:Digit1:1:49:<nil>", "keyUp:1:Digit1:<nil>:49:<nil>",
		"insert:é"}
	if !reflect.DeepEqual(seq, want) {
		t.Fatalf("got\n%s\nwant\n%s", strings.Join(seq, "\n"), strings.Join(want, "\n"))
	}
}

func TestTypeCtxCancelMidText(t *testing.T) {
	setDelay(t, 50*time.Millisecond)
	r := newRig(t)
	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()
	if err := r.p.Type(ctx, "#i", strings.Repeat("a", 100)); err == nil {
		t.Fatal("no error")
	}
	if n := len(r.drain()); n > 40 {
		t.Errorf("%d requests: text kept going after cancel", n)
	}
}

func TestGotoSurvivesPollErrors(t *testing.T) {
	t.Setenv("FAKE_FAIL_POLLS", "4")
	r := newRig(t)
	if err := r.p.Goto(context.Background(), "http://127.0.0.1/", WaitLoad); err != nil {
		t.Fatal(err)
	}
	if n := countMethod(r.drain(), "Page.createIsolatedWorld"); n < 2 {
		t.Errorf("world created %d times, want it recreated after failures", n)
	}
}

func TestGotoReportsLastPollError(t *testing.T) {
	t.Setenv("FAKE_FAIL_POLLS", "-1")
	r := newRig(t)
	ctx, cancel := context.WithTimeout(context.Background(), 400*time.Millisecond)
	defer cancel()
	err := r.p.Goto(ctx, "http://127.0.0.1/", WaitLoad)
	if err == nil || !strings.Contains(err.Error(), "Cannot find context") || !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("err = %v", err)
	}
}

func TestGotoDeadSessionReturnsAtOnce(t *testing.T) {
	t.Setenv("FAKE_FAIL_POLLS", "-1")
	t.Setenv("FAKE_POLL_ERR", "Session with given id not found.")
	r := newRig(t)
	start := time.Now()
	err := r.p.Goto(context.Background(), "http://127.0.0.1/", WaitLoad)
	if err == nil || time.Since(start) > 2*time.Second {
		t.Fatalf("err = %v after %v", err, time.Since(start))
	}
}

func TestGotoTimesOutWhenNeverComplete(t *testing.T) {
	t.Setenv("FAKE_NEVER_COMPLETE", "1")
	r := newRig(t)
	ctx, cancel := context.WithTimeout(context.Background(), 400*time.Millisecond)
	defer cancel()
	if err := r.p.Goto(ctx, "http://127.0.0.1/", WaitLoad); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("err = %v", err)
	}
}

func TestHungOpsTimeOut(t *testing.T) {
	for _, m := range []string{"Page.captureScreenshot", "Page.close", "Page.addScriptToEvaluateOnNewDocument"} {
		t.Run(m, func(t *testing.T) {
			t.Setenv("FAKE_HANG", m)
			r := newRig(t)
			ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
			defer cancel()
			var err error
			switch m {
			case "Page.close":
				err = r.p.Close(ctx)
			case "Page.addScriptToEvaluateOnNewDocument":
				err = r.p.AddInitScript(ctx, "1")
			default:
				_, err = r.p.Screenshot(ctx)
			}
			if err == nil {
				t.Fatal("no error")
			}
		})
	}
}

func countMethod(rs []req, m string) (n int) {
	for _, q := range rs {
		if q.Method == m {
			n++
		}
	}
	return
}

func setDelay(t *testing.T, d time.Duration) {
	old := keyDelay
	t.Cleanup(func() { keyDelay = old })
	keyDelay = func(*rand.Rand) time.Duration { return d }
}

func TestSoftIgnoresDeadlineErrors(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	var last error
	real := errors.New("Cannot find context")
	if err := soft(ctx, real, &last); err != nil || last != real {
		t.Fatalf("err %v last %v", err, last)
	}
	cancel()
	if err := soft(ctx, context.Canceled, &last); err != nil || last != real {
		t.Fatalf("deadline error overwrote last: %v", last)
	}
}

func TestStartPointClampedToViewport(t *testing.T) {
	t.Setenv("FAKE_VIEWPORT", "200x150")
	r := newRig(t)
	if err := r.p.Click(context.Background(), "#b"); err != nil {
		t.Fatal(err)
	}
	for _, q := range r.drain() {
		if q.Method == "Input.dispatchMouseEvent" {
			x, y := q.Params["x"].(float64), q.Params["y"].(float64)
			if x < 0 || x > 100 || y < 0 || y > 75 {
				t.Errorf("start move (%v,%v) outside half of 200x150", x, y)
			}
			return
		}
	}
	t.Fatal("no mouse event")
}

func TestTypeTabAndCRLF(t *testing.T) {
	setDelay(t, 0)
	r := newRig(t)
	if err := r.p.Type(context.Background(), "#i", "\t\r\nx\n"); err != nil {
		t.Fatal(err)
	}
	var seq []string
	for _, q := range r.drain() {
		if q.Method == "Input.dispatchKeyEvent" {
			seq = append(seq, fmt.Sprintf("%v:%v:%v:%v", q.Params["type"], q.Params["key"], q.Params["text"], q.Params["windowsVirtualKeyCode"]))
		}
	}
	want := []string{"keyDown:Tab:<nil>:9", "keyUp:Tab:<nil>:9", "keyDown:Enter:\r:13", "keyUp:Enter:<nil>:13",
		"keyDown:x:x:88", "keyUp:x:<nil>:88", "keyDown:Enter:\r:13", "keyUp:Enter:<nil>:13"}
	if !reflect.DeepEqual(seq, want) {
		t.Fatalf("got %v\nwant %v", seq, want)
	}
}

func TestGotoResetsWorld(t *testing.T) {
	r := newRig(t)
	r.p.world = 99 // stale id from an earlier document
	if err := r.p.Goto(context.Background(), "http://127.0.0.1/", WaitLoad); err != nil {
		t.Fatal(err)
	}
	if countMethod(r.drain(), "Page.createIsolatedWorld") == 0 {
		t.Error("stale world reused")
	}
}

// launchRig starts the fake with a caller-owned profile and returns the
// browser, the profile dir and every method sent (including connect time).
func launchRig(t *testing.T, ctx context.Context) (*Browser, string, *[]string) {
	t.Helper()
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 not on PATH")
	}
	dir := t.TempDir()
	exe := filepath.Join(dir, "fake-browser")
	if err := os.WriteFile(exe, []byte(fakePage), 0o755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("FAKE_LOG", filepath.Join(dir, "req.jsonl"))
	prof := filepath.Join(dir, "profile")
	os.Mkdir(prof, 0o755)
	var mu sync.Mutex
	methods := new([]string)
	b, err := Launch(ctx, camoucrome.Options{ExecutablePath: exe, UserDataDir: prof}, WithSendObserver(func(m []byte) {
		var q req
		json.Unmarshal(m, &q)
		mu.Lock()
		*methods = append(*methods, q.Method)
		mu.Unlock()
	}))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { b.Close() })
	return b, prof, methods
}

// Page.enable is sent by NewPage and by nothing else; this pins the claim in
// the README and the Page doc (reinstating "no Page.enable" fails here).
func TestNewPageExactMethods(t *testing.T) {
	b, _, methods := launchRig(t, context.Background())
	if _, err := b.NewPage(context.Background()); err != nil {
		t.Fatal(err)
	}
	want := []string{"Target.setDiscoverTargets", "Target.createTarget", "Target.attachToTarget", "Page.enable"}
	if !reflect.DeepEqual(*methods, want) {
		t.Fatalf("Launch+NewPage sent %v, want %v", *methods, want)
	}
}

func TestCloseLetsBrowserFinishProfile(t *testing.T) {
	t.Setenv("FAKE_EXIT_DELAY", "0.3")
	b, prof, _ := launchRig(t, context.Background())
	b.Close()
	if _, err := os.Stat(filepath.Join(prof, "exit.txt")); err != nil {
		t.Fatalf("browser was killed before it finished writing: %v", err)
	}
}

func TestCloseKillsBrowserThatNeverExits(t *testing.T) {
	old := exitWait
	exitWait = 300 * time.Millisecond
	t.Cleanup(func() { exitWait = old })
	t.Setenv("FAKE_NO_EXIT", "1")
	b, _, _ := launchRig(t, context.Background())
	pid := b.proc.Pid
	start := time.Now()
	b.Close()
	if time.Since(start) > 5*time.Second {
		t.Fatalf("Close took %v", time.Since(start))
	}
	if err := syscall.Kill(pid, 0); err != syscall.ESRCH {
		t.Fatalf("process %d survived Close (%v)", pid, err)
	}
}

func TestLaunchCtxCancelAfterReturnKeepsBrowser(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	b, _, _ := launchRig(t, ctx)
	cancel()
	time.Sleep(300 * time.Millisecond)
	if err := syscall.Kill(b.proc.Pid, 0); err != nil {
		t.Fatalf("browser died with the Launch ctx: %v", err)
	}
	if _, err := b.NewPage(context.Background()); err != nil {
		t.Fatalf("NewPage after ctx cancel: %v", err)
	}
}

func TestLaunchAbortsOnCancel(t *testing.T) {
	for name, hang := range map[string]bool{"already": false, "during connect": true} {
		t.Run(name, func(t *testing.T) {
			if _, err := exec.LookPath("python3"); err != nil {
				t.Skip("python3 not on PATH")
			}
			dir := t.TempDir()
			exe := filepath.Join(dir, "fake-browser")
			os.WriteFile(exe, []byte(fakePage), 0o755)
			t.Setenv("FAKE_LOG", filepath.Join(dir, "req.jsonl"))
			var pid int
			var crash, prof string
			old := startFn
			t.Cleanup(func() { startFn = old })
			startFn = func(ctx context.Context, e string, a []string, v map[string]string) (*browser.Proc, error) {
				p, err := old(ctx, e, a, v)
				if p != nil {
					pid = p.Pid
				}
				crash = v[camoucrome.CrashDumpsEnv]
				for _, x := range a {
					if d, ok := strings.CutPrefix(x, "--user-data-dir="); ok {
						prof = d
					}
				}
				return p, err
			}
			ctx, cancel := context.WithCancel(context.Background())
			if hang {
				t.Setenv("FAKE_HANG", "Target.setDiscoverTargets")
				go func() { time.Sleep(300 * time.Millisecond); cancel() }()
			} else {
				cancel()
			}
			oc, ow := closeCap, exitWait
			closeCap, exitWait = 30*time.Second, 30*time.Second // an abort must not touch either
			t.Cleanup(func() { closeCap, exitWait = oc, ow })
			begin := time.Now()
			_, err := Launch(ctx, camoucrome.Options{ExecutablePath: exe})
			if time.Since(begin) > 5*time.Second {
				t.Errorf("abort took %v", time.Since(begin))
			}
			if !errors.Is(err, context.Canceled) || !strings.HasPrefix(err.Error(), "rodclient:") {
				t.Fatalf("err = %v", err)
			}
			if hang {
				if pid == 0 {
					t.Fatal("process never started")
				}
				if err := syscall.Kill(pid, 0); err != syscall.ESRCH {
					t.Errorf("process %d leaked (%v)", pid, err)
				}
				for _, d := range []string{crash, prof} {
					if _, err := os.Stat(d); !os.IsNotExist(err) {
						t.Errorf("left behind: %s", d)
					}
				}
			} else if pid != 0 {
				t.Error("process started despite cancelled ctx")
			}
		})
	}
}

func TestTextResolvesInIsolatedWorld(t *testing.T) {
	r := newRig(t)
	if _, err := r.p.Text(context.Background(), "#b"); err != nil {
		t.Fatal(err)
	}
	var resolved bool
	for _, q := range r.drain() {
		if q.Method == "DOM.resolveNode" {
			resolved = true
			if q.Params["executionContextId"] != float64(7) {
				t.Errorf("resolveNode params %v: not the isolated world", q.Params)
			}
		}
	}
	if !resolved {
		t.Fatal("no DOM.resolveNode")
	}
}

func TestFindDeadSessionReturnsAtOnce(t *testing.T) {
	t.Setenv("FAKE_QS_ERR", "Session with given id not found.")
	r := newRig(t)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	start := time.Now()
	if err := r.p.WaitForSelector(ctx, "#b", 5*time.Second); err == nil || time.Since(start) > 2*time.Second {
		t.Fatalf("err = %v after %v", err, time.Since(start))
	}
}

func TestArgvIsACopy(t *testing.T) {
	b, _, _ := launchRig(t, context.Background())
	a := b.Argv()
	a[0] = "tampered"
	if b.Argv()[0] == "tampered" {
		t.Fatal("Argv exposes internal slice")
	}
}

func TestCloseSkipsExitWaitWhenBrowserCloseFails(t *testing.T) {
	oc, ow := closeCap, exitWait
	closeCap, exitWait = 200*time.Millisecond, 30*time.Second
	t.Cleanup(func() { closeCap, exitWait = oc, ow })
	t.Setenv("FAKE_HANG", "Browser.close")
	b, _, _ := launchRig(t, context.Background())
	pid := b.proc.Pid
	start := time.Now()
	b.Close()
	if time.Since(start) > 3*time.Second {
		t.Fatalf("Close took %v: it waited for an exit that cannot come", time.Since(start))
	}
	if err := syscall.Kill(pid, 0); err != syscall.ESRCH {
		t.Fatalf("process %d survived (%v)", pid, err)
	}
}
