//go:build !windows

package browser

import (
	"os/exec"
	"syscall"
)

func platformErr() error { return nil }

func setGroup(cmd *exec.Cmd) { cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true} }

func killGroup(pid int) { _ = syscall.Kill(-pid, syscall.SIGKILL) }
