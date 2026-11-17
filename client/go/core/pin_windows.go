//go:build windows

package core

import (
	"fmt"
	"syscall"
	"unsafe"
)

var (
	kernel32        = syscall.NewLazyDLL("kernel32.dll")
	procGetAffinity = kernel32.NewProc("GetProcessAffinityMask")
	procSetAffinity = kernel32.NewProc("SetProcessAffinityMask")
)

func init() {
	affinityGet = func() ([]int, error) {
		h, _ := syscall.GetCurrentProcess()
		var proc, sys uintptr
		if r, _, e := procGetAffinity.Call(uintptr(h), uintptr(unsafe.Pointer(&proc)), uintptr(unsafe.Pointer(&sys))); r == 0 {
			return nil, e
		}
		return cpusOfMask(uint64(proc))
	}
	affinitySet = func(cpus []int) error {
		var m uint64
		for _, c := range cpus {
			if c < 0 || c > 63 {
				return fmt.Errorf("cpu %d out of range", c)
			}
			m |= 1 << c
		}
		h, _ := syscall.GetCurrentProcess()
		if r, _, e := procSetAffinity.Call(uintptr(h), uintptr(m)); r == 0 {
			return e
		}
		return nil
	}
}
