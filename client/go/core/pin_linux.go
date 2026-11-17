//go:build linux

package core

import (
	"fmt"
	"os"
	"strconv"
	"syscall"
	"unsafe"
)

const maskWords = 16 // 1024 CPUs

// shortcut: one thread-list pass; a thread created mid-pass can miss the mask; loop until stable if Linux spawners matter
func init() {
	affinityGet = func() ([]int, error) {
		var m [maskWords]uint64
		if _, _, e := syscall.RawSyscall(syscall.SYS_SCHED_GETAFFINITY, 0, unsafe.Sizeof(m), uintptr(unsafe.Pointer(&m[0]))); e != 0 {
			return nil, e
		}
		var cpus []int
		for i := 0; i < maskWords*64; i++ {
			if m[i/64]>>(i%64)&1 == 1 {
				cpus = append(cpus, i)
			}
		}
		return cpus, nil
	}
	affinitySet = func(cpus []int) error {
		var m [maskWords]uint64
		for _, c := range cpus {
			if c < 0 || c >= maskWords*64 {
				return fmt.Errorf("cpu %d out of range", c)
			}
			m[c/64] |= 1 << (c % 64)
		}
		ents, err := os.ReadDir("/proc/self/task")
		if err != nil {
			return err
		}
		var first error
		for _, e := range ents {
			tid, err := strconv.Atoi(e.Name())
			if err != nil {
				continue
			}
			if _, _, errno := syscall.RawSyscall(syscall.SYS_SCHED_SETAFFINITY, uintptr(tid), unsafe.Sizeof(m), uintptr(unsafe.Pointer(&m[0]))); errno != 0 && errno != syscall.ESRCH && first == nil {
				first = fmt.Errorf("tid %d: %w", tid, errno) // ESRCH: the thread ended between the listing and the call
			}
		}
		return first
	}
}
