package core

// The sweep half of client/go/atrest.go for the driverless path (this module
// does not import camoucrome): Env names its crash dir for this process and
// sweeps a killed client's leftovers first. Keep the two in step.

import (
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"strconv"
	"time"
)

// Set by init (launch.go) from settings/launcher.json launch.temp_dirs:
// staleAfter is the time since the dir last changed; ownedName matches
// camoucrome-<pid>-<rand> (a temp profile) and camoucrome-crash-<pid>-<rand>, <pid> the launching client's.
// The scripts' own camoucrome-<word>- dirs and the pid-less names of older clients never match.
var (
	staleAfter time.Duration
	ownedName  *regexp.Regexp
)

// sweep removes the temp profiles and crash dirs a killed client left. Only
// this client family's names; never keep (the caller's profile) or a dir
// that holds it. Liveness:
// the client's pid is in the name, so one kill(0) / OpenProcess per
// candidate, no file to open, and a pid that names any live process keeps
// the dir; a profile is kept too while its SingletonLock / lockfile says a
// browser outlived the client. Failures are ignored.
func sweep(keep string) {
	root := os.TempDir()
	var spared []os.FileInfo
	if keep != "" {
		var ok bool
		if spared, ok = protectedDirs(keep); !ok {
			return // never delete on doubt
		}
	}
	ents, err := os.ReadDir(root)
	if err != nil {
		return
	}
	for _, e := range ents {
		m := ownedName.FindStringSubmatch(e.Name())
		d := filepath.Join(root, e.Name())
		if m == nil {
			continue
		}
		fi, err := os.Lstat(d)
		if err != nil || !fi.IsDir() || time.Since(fi.ModTime()) < staleAfter || !ownedByMe(fi) ||
			slices.ContainsFunc(spared, func(k os.FileInfo) bool { return os.SameFile(k, fi) }) {
			continue
		}
		if pid, err := strconv.Atoi(m[1]); err != nil || alive(pid) || browserRunning(d) {
			continue
		}
		os.RemoveAll(d) // one pass: a locked dir must not stall the launch
	}
}

// protectedDirs returns keep, resolved, and every dir above it, so Sweep
// spares a candidate that is the caller's dir or holds it however either is
// spelled (a symlink, /var vs /private/var, an 8.3 name, case): os.SameFile
// compares identities, not paths. keep may not exist yet; its deepest
// existing ancestor stands in. ok is false on any doubt.
func protectedDirs(keep string) (dirs []os.FileInfo, ok bool) {
	p, err := filepath.Abs(keep)
	if err != nil {
		return nil, false
	}
	for {
		_, err := os.Stat(p)
		if err == nil {
			break
		}
		if !errors.Is(err, fs.ErrNotExist) || filepath.Dir(p) == p {
			return nil, false
		}
		p = filepath.Dir(p)
	}
	if p, err = filepath.EvalSymlinks(p); err != nil {
		return nil, false
	}
	for {
		fi, err := os.Stat(p)
		if err != nil {
			return nil, false
		}
		dirs = append(dirs, fi)
		if filepath.Dir(p) == p {
			return dirs, true
		}
		p = filepath.Dir(p)
	}
}
