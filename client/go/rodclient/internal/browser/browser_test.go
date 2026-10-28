package browser

import (
	"bytes"
	"io"
	"strings"
	"testing"
	"testing/iotest"
)

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
