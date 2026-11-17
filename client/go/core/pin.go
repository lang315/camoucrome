package core

import (
	"errors"
	"fmt"
	"math/rand/v2"
	"os"
	"slices"
	"sync"
)

// pinMu is held across read mask, set, start and restore. Every Chrome spawn
// in the process must go through Pinned, pinned or not: a spawn inside
// another's pin window would inherit the wrong mask.
var pinMu sync.Mutex

// The OS calls, replaced by tests. affinityGet returns (nil, nil) where the
// platform has no affinity API.
var (
	affinityGet func() ([]int, error)
	affinitySet func(cpus []int) error
)

// Pinned runs start with this process pinned to cores random CPUs of its
// allowed set when cores is below them, and restores the mask after (also when
// start fails). Chrome and its children inherit the mask: Windows
// CreateProcess inherits the process mask, Linux threads (every tid of this
// process is set) pass theirs to the child. With cores >= allowed, or no
// affinity API (macOS), it just calls start. A pin that cannot be set or
// restored is an error naming the pid and count.
func Pinned(cores int, start func() error) error {
	pinMu.Lock()
	defer pinMu.Unlock()
	allowed, err := affinityGet()
	if err != nil {
		return fmt.Errorf("cannot read the CPU mask of pid %d: %w", os.Getpid(), err)
	}
	if allowed == nil || cores < 1 || cores >= len(allowed) {
		return start()
	}
	pick := slices.Clone(allowed)
	rand.Shuffle(len(pick), func(i, j int) { pick[i], pick[j] = pick[j], pick[i] })
	pick = pick[:cores]
	slices.Sort(pick)
	restore := func() error {
		if err := affinitySet(allowed); err != nil {
			return fmt.Errorf("cannot restore pid %d to its %d CPUs: %w", os.Getpid(), len(allowed), err)
		}
		return nil
	}
	if err := affinitySet(pick); err != nil {
		// a half-applied set: undo it, and say so when that fails too
		return errors.Join(fmt.Errorf("cannot pin pid %d to %d CPUs: %w", os.Getpid(), cores, err), restore())
	}
	return errors.Join(start(), restore())
}

// cpusOfMask is the CPUs of a Windows process mask. A mask of 0 means the
// process has threads in more than one processor group (the API reports 0):
// pinning it would silently do nothing, so it is an error.
// shortcut: one processor group, so at most 64 CPUs; upgrade for a bigger host.
func cpusOfMask(proc uint64) ([]int, error) {
	if proc == 0 {
		return nil, errors.New("the process mask is 0: it spans more than one processor group, which Pinned cannot pin")
	}
	var cpus []int
	for i := 0; i < 64; i++ {
		if proc>>i&1 == 1 {
			cpus = append(cpus, i)
		}
	}
	return cpus, nil
}
