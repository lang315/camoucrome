package camoucrome

// CPU pin (C3): a claim of N cores below the host's is enforced by affinity, so timing on the host cannot show more.
// playwright-go starts a driver subprocess, and that subprocess spawns Chrome, so the driver is pinned to N of its
// allowed CPUs right before the launch call and restored right after; Chrome and its children inherit the mask.
// playwright-go keeps the driver's pid private, so the driver is found as the child of this process whose command
// line runs "run-driver". A mutex serialises pin-launch-restore: two overlapping launches would restore each
// other's mask.

import (
	"fmt"
	"math/rand"
	"os"
	"os/exec"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"
)

var pinMu sync.Mutex

// The OS calls, replaced by tests. affinityGet returns (nil, nil) where the platform has no affinity API.
var (
	affinityGet = osAffinityGet
	affinitySet = osAffinitySet
	driverPIDs  = osDriverPIDs
)

func osAffinityGet(pid int) ([]int, error) {
	switch runtime.GOOS {
	case "linux": // the list form has no 64-CPU limit, and needs no taskset
		b, err := os.ReadFile("/proc/" + strconv.Itoa(pid) + "/status")
		if err != nil {
			return nil, err
		}
		for _, line := range strings.Split(string(b), "\n") {
			if l, ok := strings.CutPrefix(line, "Cpus_allowed_list:"); ok {
				return cpusFromList(strings.TrimSpace(l))
			}
		}
		return nil, fmt.Errorf("no Cpus_allowed_list in /proc/%d/status", pid)
	case "windows":
		out, err := exec.Command("powershell", "-NoProfile", "-NonInteractive", "-Command",
			fmt.Sprintf("(Get-Process -Id %d).ProcessorAffinity.ToInt64()", pid)).Output()
		if err != nil {
			return nil, err
		}
		return cpusOf(strings.TrimSpace(string(out)), 10)
	}
	// shortcut: macOS has no CPU affinity API, so a claim below the host's cores is not enforced there; revisit if a macOS host is supported
	return nil, nil
}

// cpusFromList decodes "0-3,8".
func cpusFromList(l string) ([]int, error) {
	var cpus []int
	for _, r := range strings.Split(l, ",") {
		lo, hi, found := strings.Cut(r, "-")
		a, err := strconv.Atoi(lo)
		b := a
		if err == nil && found {
			b, err = strconv.Atoi(hi)
		}
		if err != nil || b < a {
			return nil, fmt.Errorf("unreadable CPU list %q", l)
		}
		for c := a; c <= b; c++ {
			cpus = append(cpus, c)
		}
	}
	return cpus, nil
}

func cpuList(cpus []int) string {
	c := append([]int(nil), cpus...)
	sort.Ints(c)
	parts := make([]string, len(c))
	for i, x := range c {
		parts[i] = strconv.Itoa(x)
	}
	return strings.Join(parts, ",")
}

// cpusOf decodes a Windows mask. shortcut: one processor group, so at most 64 CPUs; upgrade for a bigger host.
func cpusOf(s string, base int) ([]int, error) {
	m, err := strconv.ParseUint(s, base, 64)
	if err != nil {
		return nil, fmt.Errorf("unreadable affinity mask %q: %w", s, err)
	}
	var cpus []int
	for i := 0; i < 64; i++ {
		if m>>i&1 == 1 {
			cpus = append(cpus, i)
		}
	}
	return cpus, nil
}

func osAffinitySet(pid int, cpus []int) error {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "linux": // -a: every thread of the process
		cmd = exec.Command("taskset", "-a", "-c", "-p", cpuList(cpus), strconv.Itoa(pid))
	case "windows":
		var m uint64
		for _, c := range cpus {
			m |= 1 << c
		}
		cmd = exec.Command("powershell", "-NoProfile", "-NonInteractive", "-Command",
			fmt.Sprintf("(Get-Process -Id %d).ProcessorAffinity = %d", pid, m))
	default:
		return nil
	}
	if out, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("%w: %s", err, strings.TrimSpace(string(out)))
	}
	return nil
}

// driverQueryScript lists the children of pid running the driver. This script is itself a child's command line, so
// the pattern is built from two strings (the literal would match the query) and its own $PID is excluded.
func driverQueryScript(pid int) string {
	return fmt.Sprintf("$p = '*run-' + 'driver*'; Get-CimInstance Win32_Process -Filter 'ParentProcessId=%d' | "+
		"Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -like $p } | ForEach-Object { $_.ProcessId }", pid)
}

func osDriverPIDs() ([]int, error) {
	self := os.Getpid()
	switch runtime.GOOS {
	case "linux":
		ents, err := os.ReadDir("/proc")
		if err != nil {
			return nil, err
		}
		var pids []int
		for _, e := range ents {
			pid, err := strconv.Atoi(e.Name())
			if err != nil {
				continue
			}
			stat, err := os.ReadFile("/proc/" + e.Name() + "/stat")
			if err != nil {
				continue
			}
			// "pid (comm) state ppid ...": comm may hold spaces and parentheses, so cut at the last ')'
			rest := strings.Fields(string(stat[strings.LastIndexByte(string(stat), ')')+1:]))
			cmdline, _ := os.ReadFile("/proc/" + e.Name() + "/cmdline")
			if len(rest) > 1 && rest[1] == strconv.Itoa(self) && strings.Contains(string(cmdline), "run-driver") {
				pids = append(pids, pid)
			}
		}
		return pids, nil
	case "windows":
		out, err := exec.Command("powershell", "-NoProfile", "-NonInteractive", "-Command", driverQueryScript(self)).Output()
		if err != nil {
			return nil, err
		}
		var pids []int
		for _, f := range strings.Fields(string(out)) {
			if pid, err := strconv.Atoi(f); err == nil {
				pids = append(pids, pid)
			}
		}
		return pids, nil
	}
	return nil, nil
}

// pinned runs call with the driver pinned to n of its allowed CPUs when n is below them, restoring the mask after
// (also when call fails). A pin that cannot be set or restored is an error naming the pid.
func pinned(n int, call func() error) error {
	pinMu.Lock()
	defer pinMu.Unlock()
	own, err := affinityGet(os.Getpid()) // the driver inherited this mask
	if err != nil {
		return fmt.Errorf("cannot read the CPU mask of pid %d: %w", os.Getpid(), err)
	}
	if own == nil || n >= len(own) {
		return call()
	}
	pids, err := driverPIDs()
	if err != nil || len(pids) == 0 {
		return fmt.Errorf("cannot pin to %d CPUs: no playwright driver subprocess found (err %v); set PinCPUCores to false to launch unpinned", n, err)
	}
	type saved struct {
		pid  int
		mask []int
	}
	var done []saved
	restore := func() error {
		var first error
		for _, s := range done {
			if err := affinitySet(s.pid, s.mask); err != nil && first == nil {
				first = fmt.Errorf("cannot restore pid %d to its %d CPUs: %w", s.pid, len(s.mask), err)
			}
		}
		return first
	}
	for _, pid := range pids {
		allowed, err := affinityGet(pid)
		if err == nil {
			pick := append([]int(nil), allowed...)
			rand.Shuffle(len(pick), func(i, j int) { pick[i], pick[j] = pick[j], pick[i] })
			if n > len(pick) {
				n = len(pick)
			}
			pick = pick[:n]
			sort.Ints(pick)
			done = append(done, saved{pid, allowed}) // restore even a half-applied set
			err = affinitySet(pid, pick)
		}
		if err != nil {
			restore()
			return fmt.Errorf("cannot pin driver pid %d to %d CPUs: %w", pid, n, err)
		}
	}
	cerr := call()
	if rerr := restore(); rerr != nil && cerr == nil {
		return rerr
	}
	return cerr
}
