//go:build !windows

package camoucrome

import (
	"errors"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
)

func alive(pid int) bool {
	err := syscall.Kill(pid, 0)
	return err == nil || !errors.Is(err, syscall.ESRCH) // EPERM: another user's live process
}

// browserRunning reads <profile>/SingletonLock ("<host>-<pid>"), which a killed browser leaves behind.
func browserRunning(dir string) bool {
	link, err := os.Readlink(filepath.Join(dir, "SingletonLock"))
	if err != nil {
		return false
	}
	pid, err := strconv.Atoi(link[strings.LastIndex(link, "-")+1:])
	return err != nil || alive(pid)
}

func ownedByMe(fi os.FileInfo) bool {
	st, ok := fi.Sys().(*syscall.Stat_t)
	return ok && int(st.Uid) == os.Getuid()
}
