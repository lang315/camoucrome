package cdplog

import (
	"bytes"
	"strings"
	"testing"
)

func fill(l *Logger) {
	l.Log([]byte(`{"id":1,"method":"Runtime.callFunctionOn"}`))
	l.Log([]byte(`{"id":2,"method":"Page.navigate"}`))
	l.Log([]byte(`{"id":3,"method":"Runtime.callFunctionOn"}`))
}

func TestLogCountsMethods(t *testing.T) {
	l := NewLogger(&bytes.Buffer{})
	fill(l)
	if l.Count("Runtime.callFunctionOn") != 2 || l.Count("Page.navigate") != 1 || l.Count("Runtime.enable") != 0 {
		t.Fatal("wrong counts")
	}
}

func TestLogIsOneLinePerMessage(t *testing.T) {
	var b bytes.Buffer
	fill(NewLogger(&b))
	if n := strings.Count(b.String(), "\n"); n != 3 {
		t.Fatalf("%d lines", n)
	}
}
