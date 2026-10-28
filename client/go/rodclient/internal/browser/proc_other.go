//go:build windows

package browser

import (
	"errors"
	"os/exec"
)

// shortcut: ExtraFiles fds 3/4 and process groups are unix-only; upgrade if Windows pipes are needed.
func platformErr() error { return errors.New("browser: the pipe transport is unix only") }

func setGroup(*exec.Cmd) {}

func killGroup(int) {}
