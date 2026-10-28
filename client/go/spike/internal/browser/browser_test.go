package browser

import (
	"bytes"
	"encoding/json"
	"io"
	"os"
	"reflect"
	"slices"
	"sort"
	"strings"
	"testing"
	"testing/iotest"
)

func TestArgvHasContractFlags(t *testing.T) {
	raw, err := os.ReadFile("../../../../../settings/launcher.json")
	if err != nil {
		t.Fatal(err)
	}
	var c struct {
		MustNot  []string `json:"browser_argv_must_not_contain"`
		Expected struct {
			Args []string `json:"args"`
		} `json:"browser_argv_expected"`
	}
	if err := json.Unmarshal(raw, &c); err != nil || len(c.MustNot) == 0 || len(c.Expected.Args) == 0 {
		t.Fatalf("launcher.json: %v", err)
	}
	want := append(append([]string{}, c.Expected.Args...), "--user-data-dir=/p", "--no-sandbox")
	sort.Strings(want)
	argv := buildArgv(Options{Executable: "x"}, "/p")
	got := append([]string{}, argv...)
	sort.Strings(got)
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("argv %v != contract %v", argv, want)
	}
	for _, bad := range c.MustNot {
		for _, a := range argv {
			if strings.HasPrefix(a, bad) {
				t.Errorf("argv has forbidden %s", a)
			}
		}
	}
	if slices.Contains(buildArgv(Options{Headed: true}, "/p"), "--headless=new") {
		t.Error("Headed still has --headless=new")
	}
	if slices.Contains(buildArgv(Options{Sandbox: true}, "/p"), "--no-sandbox") {
		t.Error("Sandbox still has --no-sandbox")
	}
	port := buildArgv(Options{UsePort: true}, "/p")
	if !slices.Contains(port, "--remote-debugging-port=0") || slices.Contains(port, "--remote-debugging-pipe") {
		t.Errorf("UsePort argv %v", port)
	}
}

type nopW struct{ bytes.Buffer }

func (*nopW) Close() error { return nil }

func TestConnFraming(t *testing.T) {
	// NUL split across one-byte reads, two messages in one read
	c := newConn(iotest.OneByteReader(strings.NewReader("{\"a\":1}\x00{\"b\":2}\x00")), &nopW{})
	for _, want := range []string{`{"a":1}`, `{"b":2}`} {
		got, err := c.Read()
		if err != nil || string(got) != want {
			t.Fatalf("got %q %v want %q", got, err, want)
		}
	}
	if _, err := c.Read(); err != io.EOF {
		t.Fatalf("clean EOF: %v", err)
	}
	c = newConn(strings.NewReader("{\"a\":1}\x00{\"b\""), &nopW{})
	if _, err := c.Read(); err != nil {
		t.Fatal(err)
	}
	if _, err := c.Read(); err != io.ErrUnexpectedEOF {
		t.Fatalf("EOF mid-message: %v", err)
	}
}

func TestConnSend(t *testing.T) {
	w := &nopW{}
	c := newConn(strings.NewReader(""), w)
	var seen string
	c.Observe = func(m []byte) { seen = string(m) }
	if err := c.Send([]byte(`{"id":1}`)); err != nil || w.String() != "{\"id\":1}\x00" || seen != `{"id":1}` {
		t.Fatalf("%q %q %v", w.String(), seen, err)
	}
	if c.Send([]byte("a\x00b")) == nil {
		t.Fatal("NUL inside a message must be refused")
	}
}

func TestEnvDropsParentCamou(t *testing.T) {
	env, err := buildEnv(Options{Config: `{"navigator.hardwareConcurrency":4}`}, []string{"CAMOU_CONFIG=evil", "CAMOU_CONFIG_1=evil", "PATH=/bin"})
	if err != nil {
		t.Fatal(err)
	}
	joined := strings.Join(env, "\n")
	if strings.Contains(joined, "evil") || !strings.Contains(joined, "CAMOU_CONFIG={") || !strings.Contains(joined, "PATH=/bin") {
		t.Fatalf("env %v", env)
	}
}
