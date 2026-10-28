package browser

import (
	"bufio"
	"bytes"
	"errors"
	"io"
	"sync"
)

// Conn is --remote-debugging-pipe: NUL-terminated JSON each way. Its method
// set mirrors rod's cdp.WebSocketable (Send/Read), from memory of v0.116.x.
type Conn struct {
	mu      sync.Mutex
	w       io.WriteCloser
	r       *bufio.Reader
	Observe func([]byte) // sees every sent message before it is written
}

func newConn(r io.Reader, w io.WriteCloser) *Conn {
	return &Conn{w: w, r: bufio.NewReaderSize(r, 1<<20)}
}

func (c *Conn) Send(msg []byte) error {
	if bytes.IndexByte(msg, 0) >= 0 {
		return errors.New("browser: message contains NUL")
	}
	if c.Observe != nil {
		c.Observe(msg)
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	_, err := c.w.Write(append(append([]byte{}, msg...), 0))
	return err
}

// Read returns the next message without its NUL. EOF before a NUL is an error.
func (c *Conn) Read() ([]byte, error) {
	b, err := c.r.ReadBytes(0)
	if err != nil {
		if len(b) > 0 && errors.Is(err, io.EOF) {
			return nil, io.ErrUnexpectedEOF
		}
		return nil, err
	}
	return b[:len(b)-1], nil
}

func (c *Conn) Close() error { return c.w.Close() }
