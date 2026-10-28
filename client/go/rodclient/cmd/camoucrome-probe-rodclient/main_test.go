package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/lang315/camoucrome/client/go/rodclient"
)

func TestOutputShape(t *testing.T) {
	b, err := marshalOutput("l", `{"a":1}`, []string{"/x", "--y"})
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
	if got.Driver != "l" || got.Report["a"] != 1 || len(got.Argv) != 2 {
		t.Fatalf("got %s", b)
	}
	if _, err := marshalOutput("l", "not json", nil); err == nil {
		t.Fatal("bad report accepted")
	}
}

func TestProxyFlagsRejected(t *testing.T) {
	for _, f := range []string{"--proxy", "--proxy-bypass", "--proxy-user", "--proxy-pass"} {
		var se bytes.Buffer
		if code := run([]string{f, "x", "--url", "http://127.0.0.1/"}, io.Discard, &se); code != 2 || !strings.Contains(se.String(), "not supported") {
			t.Errorf("%s: code=%d stderr=%q", f, code, se.String())
		}
	}
}

func TestParseFlagsAndOptions(t *testing.T) {
	c, err := parseFlags([]string{"--executable", "/b", "--url", "u", "--headed", "--strict", "--driver-dir", "d", "--label", "l", "--config", "{}", "--preset", "{\"p\":1}"})
	if err != nil || c.exe != "/b" || c.url != "u" || c.label != "l" || c.config != "{}" {
		t.Fatalf("%+v %v", c, err)
	}
	o := c.options()
	if o.ExecutablePath != "/b" || !o.Strict || *o.Headless || o.Config != "{}" || o.Preset != "{\"p\":1}" ||
		!reflect.DeepEqual(o.ExtraArgs, []string{"--no-sandbox"}) {
		t.Fatalf("options %+v", o)
	}
	c, _ = parseFlags([]string{"--sandbox"})
	if o := c.options(); !*o.Headless || o.ExtraArgs != nil || o.Config != nil || o.Preset != nil {
		t.Fatalf("options %+v", o)
	}
}

func TestAtFile(t *testing.T) {
	f := filepath.Join(t.TempDir(), "c.json")
	os.WriteFile(f, []byte(`{"k":1}`), 0o600)
	c, err := parseFlags([]string{"--config", "@" + f})
	if err != nil || c.config != `{"k":1}` {
		t.Fatalf("%+v %v", c, err)
	}
	if _, err := parseFlags([]string{"--config", "@/nonexistent/x"}); err == nil {
		t.Fatal("missing @file accepted")
	}
}

func TestLaunchFailureExits1(t *testing.T) {
	var se bytes.Buffer
	if code := run([]string{"--executable", "/nonexistent/browser", "--url", "u"}, io.Discard, &se); code != 1 || !strings.Contains(se.String(), "launch:") {
		t.Fatalf("code=%d stderr=%q", code, se.String())
	}
}

type fakePage struct {
	calls []string
	js    string
	empty int // Text returns "" this many times first
	text  string
	err   error
}

func (f *fakePage) AddInitScript(_ context.Context, js string) error {
	f.calls, f.js = append(f.calls, "init"), js
	return f.err
}

func (f *fakePage) Goto(_ context.Context, u string, w rodclient.WaitUntil) error {
	f.calls = append(f.calls, "goto "+u)
	if w != rodclient.WaitLoad {
		return errors.New("not WaitLoad")
	}
	return nil
}

func (f *fakePage) Text(_ context.Context, sel string) (string, error) {
	f.calls = append(f.calls, "text "+sel)
	if f.empty > 0 {
		f.empty--
		return "", nil
	}
	return f.text, nil
}

func TestReportOrderAndInitScript(t *testing.T) {
	f := &fakePage{text: `{"a":1}`, empty: 2}
	got, err := report(context.Background(), f, "http://x/")
	if err != nil || got != `{"a":1}` {
		t.Fatalf("%q %v", got, err)
	}
	want := []string{"init", "goto http://x/", "text #o", "text #o", "text #o"}
	if !reflect.DeepEqual(f.calls, want) {
		t.Fatalf("calls %v, want %v", f.calls, want)
	}
	if f.js != "window.__camou_init = 1" {
		t.Fatalf("init script %q", f.js)
	}
}

func TestReportErrors(t *testing.T) {
	old := reportWait
	reportWait = 250 * time.Millisecond
	defer func() { reportWait = old }()
	if _, err := report(context.Background(), &fakePage{}, "u"); err == nil || !strings.Contains(err.Error(), "still empty") {
		t.Fatalf("empty #o: %v", err)
	}
	f := &fakePage{err: errors.New("boom")}
	if _, err := report(context.Background(), f, "u"); err == nil || len(f.calls) != 1 {
		t.Fatalf("init failure must stop before goto: %v %v", err, f.calls)
	}
}
