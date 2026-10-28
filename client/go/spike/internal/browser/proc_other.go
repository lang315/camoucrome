//go:build windows

package browser

import (
	"errors"
	"os/exec"
)

// shortcut: ExtraFiles fds 3/4 and process groups are unix-only; the spike runs on the Linux box.
func platformErr() error { return errors.New("browser: the spike's pipe transport is unix only") }

func setGroup(*exec.Cmd) {}

func killGroup(int) {}
