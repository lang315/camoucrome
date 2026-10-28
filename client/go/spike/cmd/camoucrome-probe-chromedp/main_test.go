package main

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha1"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestOutputShape(t *testing.T) {
	b, err := marshalOutput("chromedp", `{"a":1}`, []string{"/x", "--y"})
	if err != nil {
		t.Fatal(err)
	}
	var got struct {
		Driver string         `json:"driver"`
		Report map[string]int `json:"report"`
		Argv   []string       `json:"argv"`
	}
	if err := json.Unmarshal(b, &got); err != nil {
		t.Fatal(err)
	}
	if got.Driver != "chromedp" || got.Report["a"] != 1 || len(got.Argv) != 2 {
		t.Fatalf("got %s", b)
	}
	if _, err := marshalOutput("chromedp", "not json", nil); err == nil {
		t.Fatal("bad report accepted")
	}
}

func TestProxyFlagsRejected(t *testing.T) {
	for _, f := range []string{"--proxy", "--proxy-bypass", "--proxy-user", "--proxy-pass"} {
		var se bytes.Buffer
		if code := run([]string{f, "x", "--url", "http://127.0.0.1/"}, io.Discard, &se); code != 2 || !strings.Contains(se.String(), "not supported in spike") {
			t.Errorf("%s: code=%d stderr=%q", f, code, se.String())
		}
	}
}

func TestParseFlags(t *testing.T) {
	c, err := parseFlags([]string{"--executable", "/b", "--url", "u", "--headed", "--strict", "--sandbox", "--driver-dir", "d", "--label", "l", "--config", "{}"})
	if err != nil || c.exe != "/b" || c.url != "u" || !c.headed || !c.strict || !c.sandbox || c.config != "{}" {
		t.Fatalf("%+v %v", c, err)
	}
	if _, err := parseFlags([]string{"--config", "@/nonexistent/x"}); err == nil {
		t.Fatal("missing @file accepted")
	}
}

// The prefixes are the ones chromedp v0.21.0 remote/conn.go really logs
// ("-> %s" on Write, "<- %s" on Read); the in-process server test below
// proves them against the real Conn, this test pins the filter itself.
func TestSentOnly(t *testing.T) {
	var got []string
	f := sentOnly(func(b []byte) { got = append(got, string(b)) })
	f("-> %s", []byte("{\"id\":1,\"method\":\"A.b\"}\n"))
	f("<- %s", []byte("{\"id\":1,\"result\":{}}"))
	f("unknown OpCode: %s", "x")
	f("-> %s", []byte(`{"id":2,"method":"C.d"}`))
	if len(got) != 2 || got[0] != `{"id":1,"method":"A.b"}` || got[1] != `{"id":2,"method":"C.d"}` {
		t.Fatalf("got %q", got)
	}
}

// fakeChrome is a minimal websocket CDP server, enough for chromedp's attach,
// Navigate and Text to run without a browser. It records every method received.
type fakeChrome struct {
	mu      sync.Mutex
	methods []string
	text    string
	lateAt  time.Time // #o reads empty before this
	srv     *httptest.Server
}

func newFakeChrome(text string) *fakeChrome {
	f := &fakeChrome{text: text}
	f.srv = httptest.NewServer(http.HandlerFunc(f.serve))
	return f
}

func (f *fakeChrome) wsURL() string {
	return "ws" + strings.TrimPrefix(f.srv.URL, "http") + "/devtools/browser/fake"
}

func (f *fakeChrome) sent() []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]string{}, f.methods...)
}

func writeFrame(c net.Conn, mu *sync.Mutex, payload []byte) {
	hdr := []byte{0x81}
	switch n := len(payload); {
	case n < 126:
		hdr = append(hdr, byte(n))
	case n < 65536:
		hdr = append(hdr, 126, 0, 0)
		binary.BigEndian.PutUint16(hdr[2:], uint16(n))
	default:
		hdr = append(hdr, 127, 0, 0, 0, 0, 0, 0, 0, 0)
		binary.BigEndian.PutUint64(hdr[2:], uint64(n))
	}
	mu.Lock()
	defer mu.Unlock()
	c.Write(append(hdr, payload...))
}

func readFrame(r *bufio.Reader) ([]byte, byte, error) {
	var h [2]byte
	if _, err := io.ReadFull(r, h[:]); err != nil {
		return nil, 0, err
	}
	n := uint64(h[1] & 0x7f)
	switch n {
	case 126:
		var b [2]byte
		io.ReadFull(r, b[:])
		n = uint64(binary.BigEndian.Uint16(b[:]))
	case 127:
		var b [8]byte
		io.ReadFull(r, b[:])
		n = binary.BigEndian.Uint64(b[:])
	}
	var mask [4]byte
	if h[1]&0x80 != 0 {
		io.ReadFull(r, mask[:])
	}
	p := make([]byte, n)
	if _, err := io.ReadFull(r, p); err != nil {
		return nil, 0, err
	}
	for i := range p {
		p[i] ^= mask[i%4]
	}
	return p, h[0] & 0x0f, nil
}

func (f *fakeChrome) serve(w http.ResponseWriter, r *http.Request) {
	key := r.Header.Get("Sec-WebSocket-Key")
	sum := sha1.Sum([]byte(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"))
	c, rw, err := w.(http.Hijacker).Hijack()
	if err != nil {
		return
	}
	defer c.Close()
	rw.WriteString("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " +
		base64.StdEncoding.EncodeToString(sum[:]) + "\r\n\r\n")
	rw.Flush()
	var wmu sync.Mutex
	emit := func(m map[string]any) {
		b, _ := json.Marshal(m)
		writeFrame(c, &wmu, b)
	}
	for {
		p, op, err := readFrame(rw.Reader)
		if err != nil || op == 8 {
			return
		}
		var req struct {
			ID        int64  `json:"id"`
			Method    string `json:"method"`
			SessionID string `json:"sessionId"`
		}
		if json.Unmarshal(p, &req) != nil || req.Method == "" {
			continue
		}
		f.mu.Lock()
		f.methods = append(f.methods, req.Method)
		txt := f.text
		if time.Now().Before(f.lateAt) {
			txt = ""
		}
		f.mu.Unlock()
		reply := map[string]any{"id": req.ID}
		if req.SessionID != "" {
			reply["sessionId"] = req.SessionID
		}
		reply["result"] = f.result(req.Method, txt)
		emit(reply)
		ev := func(method string, params map[string]any) {
			m := map[string]any{"method": method, "params": params}
			if req.SessionID != "" {
				m["sessionId"] = req.SessionID
			}
			emit(m)
		}
		switch req.Method {
		case "Target.setDiscoverTargets":
			ev("Target.targetCreated", map[string]any{"targetInfo": map[string]any{"targetId": "T", "type": "page", "title": "", "url": "about:blank", "attached": false, "canAccessOpener": false}})
		case "Page.enable":
			// chromedp learns the root frame from frameNavigated before Navigate runs.
			ev("Page.frameNavigated", map[string]any{"frame": map[string]any{"id": "F", "loaderId": "L", "url": "u", "domainAndRegistry": "", "securityOrigin": "", "mimeType": "text/html", "secureContextType": "Secure", "crossOriginIsolatedContextType": "NotIsolated", "gatedAPIFeatures": []any{}}})
		case "Runtime.enable":
			ev("Runtime.executionContextCreated", map[string]any{"context": map[string]any{"id": 1, "origin": "", "name": "", "uniqueId": "u1", "auxData": map[string]any{"frameId": "F", "isDefault": true}}})
		case "Page.navigate":
			ev("Page.lifecycleEvent", map[string]any{"frameId": "F", "loaderId": "L", "name": "init", "timestamp": 1})
			ev("Page.loadEventFired", map[string]any{"timestamp": 1})
			ev("Page.frameStoppedLoading", map[string]any{"frameId": "F"})
			ev("DOM.documentUpdated", map[string]any{})
		}
	}
}

func (f *fakeChrome) result(method, txt string) map[string]any {
	val, _ := json.Marshal(txt)
	var v any
	json.Unmarshal(val, &v)
	o := map[string]any{"nodeId": 2, "parentId": 1, "backendNodeId": 2, "nodeType": 1, "nodeName": "DIV", "localName": "div", "nodeValue": "", "childNodeCount": 0, "attributes": []any{"id", "o"}}
	root := map[string]any{"nodeId": 1, "backendNodeId": 1, "nodeType": 9, "nodeName": "#document", "localName": "", "nodeValue": "", "childNodeCount": 1, "children": []any{o}}
	switch method {
	case "Target.attachToTarget":
		return map[string]any{"sessionId": "S"}
	case "Target.createTarget":
		return map[string]any{"targetId": "T"}
	case "Target.getTargets":
		return map[string]any{"targetInfos": []any{}}
	case "Page.navigate":
		return map[string]any{"frameId": "F", "loaderId": "L"}
	case "Page.getFrameTree":
		return map[string]any{"frameTree": map[string]any{"frame": map[string]any{"id": "F", "loaderId": "L", "url": "u", "domainAndRegistry": "", "securityOrigin": "", "mimeType": "text/html", "secureContextType": "Secure", "crossOriginIsolatedContextType": "NotIsolated", "gatedAPIFeatures": []any{}}}}
	case "DOM.getDocument":
		return map[string]any{"root": root}
	case "DOM.querySelector":
		return map[string]any{"nodeId": 2}
	case "DOM.resolveNode":
		return map[string]any{"object": map[string]any{"type": "object", "subtype": "node", "objectId": "o1"}}
	case "DOM.describeNode":
		return map[string]any{"node": map[string]any{"nodeId": 2, "backendNodeId": 2, "nodeType": 1, "nodeName": "DIV", "localName": "div", "nodeValue": "", "childNodeCount": 0}}
	case "Runtime.evaluate":
		return map[string]any{"result": map[string]any{"type": "object", "className": "Window", "value": v}}
	case "Runtime.callFunctionOn":
		return map[string]any{"result": map[string]any{"type": "string", "value": v}}
	}
	return map[string]any{}
}

func TestProbeAgainstFakeChrome(t *testing.T) {
	f := newFakeChrome(`{"a":1}`)
	defer f.srv.Close()
	var log bytes.Buffer
	var logMu sync.Mutex
	w := writerFunc(func(b []byte) (int, error) { logMu.Lock(); defer logMu.Unlock(); return log.Write(b) })
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	text, err := probe(ctx, f.wsURL(), "http://127.0.0.1/p", sentOnly(logSink(w)))
	if err != nil {
		t.Fatalf("%v; sent %v", err, f.sent())
	}
	if text != `{"a":1}` {
		t.Fatalf("text %q", text)
	}
	sent := f.sent()
	t.Logf("chromedp sent %d: %v", len(sent), sent)
	if !contains(sent, "Runtime.enable") {
		t.Errorf("RED control never sent Runtime.enable: %v", sent)
	}
	logMu.Lock()
	defer logMu.Unlock()
	lines := strings.Split(strings.TrimSpace(log.String()), "\n")
	// The log is taken at Conn.Write, so it holds every send the server saw
	// (the server may not have read the very last one yet).
	if len(lines) < len(sent) {
		t.Fatalf("logged %d lines, server saw %d sends", len(lines), len(sent))
	}
	n := 0
	for _, l := range lines {
		if !strings.Contains(l, `"method":"`) || strings.Contains(l, `"result"`) {
			t.Errorf("not a sent message: %s", l)
		}
		if strings.Contains(l, `"method":"Runtime.enable"`) {
			n++
		}
	}
	if n == 0 {
		t.Errorf("Runtime.enable absent from log")
	}
}

type writerFunc func([]byte) (int, error)

func (w writerFunc) Write(b []byte) (int, error) { return w(b) }

func logSink(w io.Writer) func([]byte) {
	return func(b []byte) { w.Write(append(append([]byte{}, b...), '\n')) }
}

func contains(l []string, s string) bool {
	for _, x := range l {
		if x == s {
			return true
		}
	}
	return false
}

func TestProbeWaitsForLateReport(t *testing.T) {
	f := newFakeChrome(`{"a":1}`)
	defer f.srv.Close()
	f.lateAt = time.Now().Add(500 * time.Millisecond)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	text, err := probe(ctx, f.wsURL(), "u", func(string, ...any) {})
	if err != nil || text != `{"a":1}` {
		t.Fatalf("text %q err %v", text, err)
	}
}

func TestProbeDialError(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if _, err := probe(ctx, "ws://127.0.0.1:1/devtools/browser/x", "u", func(string, ...any) {}); err == nil {
		t.Fatal("want error from dead endpoint")
	}
}
