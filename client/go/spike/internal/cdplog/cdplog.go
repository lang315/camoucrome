// Package cdplog records every CDP message a client sends, so a probe can
// assert that Runtime.enable (and friends) never left the process.
package cdplog

import (
	"encoding/json"
	"io"
	"sync"
)

type Logger struct {
	mu     sync.Mutex
	w      io.Writer
	counts map[string]int
}

func NewLogger(w io.Writer) *Logger { return &Logger{w: w, counts: map[string]int{}} }

// Log writes msg + "\n" and counts its "method". Compact JSON has no raw newline.
func (l *Logger) Log(msg []byte) {
	var m struct {
		Method string `json:"method"`
	}
	_ = json.Unmarshal(msg, &m)
	l.mu.Lock()
	defer l.mu.Unlock()
	l.counts[m.Method]++
	_, _ = l.w.Write(append(append([]byte{}, msg...), '\n'))
}

func (l *Logger) Count(method string) int {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.counts[method]
}
