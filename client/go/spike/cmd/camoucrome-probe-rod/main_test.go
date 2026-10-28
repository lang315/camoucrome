package main

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/lang315/camoucrome/client/go/spike/internal/browser"
)

func TestOutputShape(t *testing.T) {
	b, err := marshalOutput("rod", `{"a":1}`, []string{"/x", "--y"})
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
	if got.Driver != "rod" || got.Report["a"] != 1 || len(got.Argv) != 2 {
		t.Fatalf("got %s", b)
	}
	if _, err := marshalOutput("rod", "not json", nil); err == nil {
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

// fakeWS answers every request with one reply carrying the union of the
// fields rod reads, so Connect/Page/WaitLoad/Element/Text run without Chrome.
type fakeWS struct {
	mu      sync.Mutex
	sent    []string
	out     chan []byte
	text    string
	closeCh chan struct{}
	lateAt  time.Time    // #o reads empty before this
	observe func([]byte) // stands in for browser.Conn.Observe
}

func newFake(text string) *fakeWS {
	return &fakeWS{out: make(chan []byte, 64), text: text, closeCh: make(chan struct{})}
}

func (f *fakeWS) Send(b []byte) error {
	var m struct {
		ID     int    `json:"id"`
		Method string `json:"method"`
	}
	if err := json.Unmarshal(b, &m); err != nil {
		return err
	}
	f.mu.Lock()
	f.sent = append(f.sent, m.Method)
	f.mu.Unlock()
	if f.observe != nil {
		f.observe(b)
	}
	txt := f.text
	if time.Now().Before(f.lateAt) {
		txt = ""
	}
	val, _ := json.Marshal(txt)
	f.out <- []byte(`{"id":` + itoa(m.ID) + `,"result":{"targetId":"T","sessionId":"S","frameId":"F","result":{"type":"object","subtype":"node","objectId":"o1","value":` + string(val) + `}}}`)
	return nil
}

func (f *fakeWS) Read() ([]byte, error) {
	select {
	case b := <-f.out:
		return b, nil
	case <-f.closeCh:
		return nil, io.EOF
	}
}

func itoa(i int) string { b, _ := json.Marshal(i); return string(b) }

func TestProbeRunsRodPath(t *testing.T) {
	f := newFake(`{"a":1}`)
	defer close(f.closeCh)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	text, err := probe(ctx, f, "http://127.0.0.1/p", false)
	if err != nil {
		t.Fatal(err)
	}
	if text != `{"a":1}` {
		t.Fatalf("text %q", text)
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	for _, want := range []string{"Target.setDiscoverTargets", "Target.createTarget", "Target.attachToTarget", "Page.navigate", "Runtime.callFunctionOn"} {
		if !contains(f.sent, want) {
			t.Errorf("rod never sent %s; sent %v", want, f.sent)
		}
	}
	if contains(f.sent, "Runtime.enable") {
		t.Errorf("Runtime.enable sent: %v", f.sent)
	}
	t.Logf("rod sent: %v", f.sent)
}

func contains(l []string, s string) bool {
	for _, x := range l {
		if x == s {
			return true
		}
	}
	return false
}

func TestProbeReadError(t *testing.T) {
	f := newFake("")
	close(f.closeCh)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if _, err := probe(ctx, f, "u", false); err == nil {
		t.Fatal("want error from dead transport")
	}
}

var deviceMethods = []string{"Emulation.setDeviceMetricsOverride", "Emulation.setTouchEmulationEnabled", "Network.setUserAgentOverride"}

func TestNoDefaultDeviceFlagBites(t *testing.T) {
	for _, noDev := range []bool{false, true} {
		f := newFake(`{"a":1}`)
		ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		if _, err := probe(ctx, f, "u", noDev); err != nil {
			t.Fatal(err)
		}
		cancel()
		close(f.closeCh)
		f.mu.Lock()
		for _, m := range deviceMethods {
			if got := contains(f.sent, m); got == noDev {
				t.Errorf("noDefaultDevice=%v: %s present=%v", noDev, m, got)
			}
		}
		if contains(f.sent, "Runtime.enable") {
			t.Errorf("noDefaultDevice=%v: Runtime.enable sent", noDev)
		}
		f.mu.Unlock()
	}
}

func TestSendLogWiring(t *testing.T) {
	f := newFake(`{"a":1}`)
	defer close(f.closeCh)
	var log bytes.Buffer
	c := &browser.Conn{}
	logSends(c, &log)
	f.observe = func(b []byte) { c.Observe(b) }
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	if _, err := probe(ctx, f, "u", false); err != nil {
		t.Fatal(err)
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	lines := strings.Split(strings.TrimSpace(log.String()), "\n")
	if len(f.sent) == 0 || len(lines) != len(f.sent) {
		t.Fatalf("logged %d lines, fake saw %d sends", len(lines), len(f.sent))
	}
	for _, l := range lines {
		if !strings.Contains(l, `"method":`) {
			t.Errorf("line without method: %s", l)
		}
	}
}

func TestProbeWaitsForLateReport(t *testing.T) {
	f := newFake(`{"a":1}`)
	defer close(f.closeCh)
	f.lateAt = time.Now().Add(400 * time.Millisecond)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	text, err := probe(ctx, f, "u", false)
	if err != nil || text != `{"a":1}` {
		t.Fatalf("text %q err %v", text, err)
	}
}
