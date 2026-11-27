package core

import (
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"syscall"
)

func alive(pid int) bool {
	h, err := syscall.OpenProcess(0x1000, false, uint32(pid)) // PROCESS_QUERY_LIMITED_INFORMATION
	if err != nil {
		return err != syscall.Errno(87) // ERROR_INVALID_PARAMETER: no such process; anything else keeps
	}
	defer syscall.CloseHandle(h)
	var code uint32
	return syscall.GetExitCodeProcess(h, &code) != nil || code == 259 // STILL_ACTIVE
}

// browserRunning: Chrome holds <profile>/lockfile open without delete sharing while it runs, so the remove fails then.
func browserRunning(dir string) bool {
	err := os.Remove(filepath.Join(dir, "lockfile"))
	return err != nil && !errors.Is(err, fs.ErrNotExist)
}

func ownedByMe(os.FileInfo) bool { return true } // %TEMP% is per user
