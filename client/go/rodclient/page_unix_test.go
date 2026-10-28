//go:build unix

package rodclient

import (
	"context"
	"encoding/json"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"testing"
	"time"

	camoucrome "github.com/lang315/camoucrome/client/go"
)

// A fake page: logs each request as one JSON line and answers the CDP methods
// the vetted ops use. "#missing" never matches. The state expression reports
// the number of Page.navigate calls seen as the document origin.
const fakePage = `#!/usr/bin/env python3
import json, os, sys, base64
r, w = os.fdopen(3, "rb", 0), os.fdopen(4, "wb", 0)
log = open(os.environ["FAKE_LOG"], "a")
buf = b""
navs = 0
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
        res = {"targetId": "T", "sessionId": "S", "frameId": "F"}
        if me == "Page.navigate":
            navs += 1
            res = {"frameId": "F", "loaderId": "L"}
        elif me == "Runtime.evaluate":
            e = p.get("expression", "")
            v = "%d|complete|3" % navs if "readyState" in e else "evalresult"
            res = {"result": {"type": "string", "value": v}}
        elif me == "DOM.getDocument":
            res = {"root": {"nodeId": 1, "backendNodeId": 1, "nodeType": 9, "nodeName": "#document", "localName": "", "nodeValue": ""}}
        elif me == "DOM.querySelector":
            res = {"nodeId": 0 if p.get("selector") == "#missing" else 2}
        elif me == "DOM.getBoxModel":
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
            res = {"layoutViewport": {"pageX": 0, "pageY": 0, "clientWidth": 800, "clientHeight": 600},
                   "visualViewport": {"offsetX": 0, "offsetY": 0, "pageX": 0, "pageY": 0, "clientWidth": 800, "clientHeight": 600, "scale": 1},
                   "contentSize": z, "cssLayoutViewport": {"pageX": 0, "pageY": 0, "clientWidth": 800, "clientHeight": 600},
                   "cssVisualViewport": {"offsetX": 0, "offsetY": 0, "pageX": 0, "pageY": 0, "clientWidth": 800, "clientHeight": 600, "scale": 1},
                   "cssContentSize": z}
        elif me == "Network.getCookies":
            res = {"cookies": [{"name": "a", "value": "b", "domain": "d", "path": "/", "expires": -1, "size": 2,
                                "httpOnly": True, "secure": False, "session": True, "priority": "Medium",
                                "sameParty": False, "sourceScheme": "Unset", "sourcePort": 80, "sameSite": "Lax"}]}
        w.write(json.dumps({"id": q["id"], "result": res}).encode() + b"\0")
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

func forbidden(m string) bool {
	return m == "Runtime.enable" || m == "Network.enable" || m == "Network.setUserAgentOverride" ||
		strings.HasPrefix(m, "Emulation.") || m == "DOM.enable" || m == "Page.enable"
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
	check("Goto", "Page.navigate", "Runtime.evaluate")

	if err := r.p.Click(ctx, "#b"); err != nil {
		t.Fatal(err)
	}
	got := check("Click", "DOM.getBoxModel", "DOM.getDocument", "DOM.querySelector", "DOM.scrollIntoViewIfNeeded", "Input.dispatchMouseEvent")
	var types []string
	for _, q := range got {
		if q.Method != "Input.dispatchMouseEvent" {
			continue
		}
		types = append(types, q.Params["type"].(string))
		if math.Abs(q.Params["x"].(float64)-60.5) > 1 || math.Abs(q.Params["y"].(float64)-40.5) > 1 {
			t.Errorf("click at (%v,%v), box centre is (60.5,40.5)", q.Params["x"], q.Params["y"])
		}
	}
	if strings.Join(types, " ") != "mouseMoved mousePressed mouseReleased" {
		t.Errorf("mouse events %v", types)
	}

	if err := r.p.Type(ctx, "#i", "héllo"); err != nil {
		t.Fatal(err)
	}
	got = check("Type", "DOM.focus", "DOM.getDocument", "DOM.querySelector", "Input.insertText")
	for _, q := range got {
		if q.Method == "Input.insertText" && q.Params["text"] != "héllo" {
			t.Errorf("insertText %v", q.Params)
		}
	}

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
