//go:build windows

package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"unsafe"
)

// browserArgv on Windows: Win32_Process has each process's command line as
// one string; CommandLineToArgvW splits it the way the process itself did.
// ConvertTo-Json gives a bare object for one match, a list for more.
func browserArgv(executable string) []string {
	query := fmt.Sprintf(`Get-CimInstance Win32_Process -Filter "Name='%s'" | Select-Object ExecutablePath,CommandLine | ConvertTo-Json -Compress`,
		filepath.Base(executable))
	out, err := exec.Command("powershell", "-NoProfile", "-Command", query).Output()
	out = bytes.TrimSpace(out)
	if err != nil || len(out) == 0 {
		return nil
	}
	if out[0] == '{' {
		out = append(append([]byte{'['}, out...), ']')
	}
	var procs []struct{ ExecutablePath, CommandLine string }
	if json.Unmarshal(out, &procs) != nil {
		return nil
	}
	want, _ := filepath.Abs(executable)
	for _, p := range procs {
		// An empty CommandLine (access denied) must not reach
		// CommandLineToArgvW, which would return this process's own argv.
		if p.CommandLine == "" || !strings.EqualFold(p.ExecutablePath, want) {
			continue
		}
		argv, err := split(p.CommandLine)
		if err != nil {
			continue
		}
		child := false
		for _, a := range argv {
			child = child || strings.HasPrefix(a, "--type=")
		}
		if !child {
			return argv
		}
	}
	return nil
}

func split(cmdline string) ([]string, error) {
	wide, err := syscall.UTF16PtrFromString(cmdline)
	if err != nil {
		return nil, err
	}
	var n int32
	ptr, err := syscall.CommandLineToArgv(wide, &n)
	if err != nil {
		return nil, err
	}
	defer syscall.LocalFree(syscall.Handle(unsafe.Pointer(ptr)))
	argv := make([]string, n)
	for i := range argv {
		argv[i] = syscall.UTF16ToString((*ptr[i])[:])
	}
	return argv, nil
}
