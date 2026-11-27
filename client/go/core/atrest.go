package core

// The sweep half of client/go/atrest.go for the driverless path (this module
// does not import camoucrome): Env names its crash dir for this process and
// sweeps a killed client's leftovers first. Keep the two in step.

import (
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"time"
)

const staleAfter = time.Hour // since the dir last changed

// camoucrome-<pid>-<rand> (a temp profile) and camoucrome-crash-<pid>-<rand>, <pid> the launching client's.
// The scripts' own camoucrome-<word>- dirs and the pid-less names of older clients never match.
var ownedName = regexp.MustCompile(`^camoucrome-(?:crash-)?([0-9]+)-[^/\\]+$`)

// sweep removes the temp profiles and crash dirs a killed client left. Only
// this client family's names; never keep (the caller's profile). Liveness:
// the client's pid is in the name, so one kill(0) / OpenProcess per
// candidate, no file to open, and a pid that names any live process keeps
// the dir; a profile is kept too while its SingletonLock / lockfile says a
// browser outlived the client. Failures are ignored.
func sweep(keep string) {
	root := os.TempDir()
	if keep != "" {
		if a, err := filepath.Abs(keep); err == nil {
			keep = a
		}
	}
	ents, err := os.ReadDir(root)
	if err != nil {
		return
	}
	for _, e := range ents {
		m := ownedName.FindStringSubmatch(e.Name())
		d := filepath.Join(root, e.Name())
		if m == nil || d == keep {
			continue
		}
		fi, err := os.Lstat(d)
		if err != nil || !fi.IsDir() || time.Since(fi.ModTime()) < staleAfter || !ownedByMe(fi) {
			continue
		}
		if pid, err := strconv.Atoi(m[1]); err != nil || alive(pid) || browserRunning(d) {
			continue
		}
		os.RemoveAll(d) // one pass: a locked dir must not stall the launch
	}
}
