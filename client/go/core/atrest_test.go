package core

// The driverless path's half of the #272 audit fix: Env names its crash dir
// for this process and sweeps a killed client's leftovers (atrest.go).

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

func TestSweepSparesTheCallersDirHoweverItIsSpelled(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("symlinks")
	}
	root := t.TempDir()
	t.Setenv("TMPDIR", root)
	alias := filepath.Join(t.TempDir(), "alias") // another spelling of the temp root (/var vs /private/var)
	if err := os.Symlink(root, alias); err != nil {
		t.Fatal(err)
	}
	c := exec.Command(os.Args[0], "-test.run=^$")
	if err := c.Run(); err != nil {
		t.Fatal(err)
	}
	dead := c.Process.Pid
	old := time.Now().Add(-2 * time.Hour)
	for _, k := range []struct{ name, below string }{{"caller", ""}, {"outer", "profile"}, {"unborn", "not/yet"}, {"loop", ""}} {
		d := filepath.Join(root, fmt.Sprintf("camoucrome-%d-%s", dead, k.name))
		os.Mkdir(d, 0o700)
		keep := filepath.Join(alias, filepath.Base(d), k.below)
		switch k.name {
		case "outer": // the caller's dir inside a candidate
			os.Mkdir(filepath.Join(d, "profile"), 0o700)
		case "loop": // ELOOP: neither found nor missing, so nothing is swept
			os.Symlink("loop", filepath.Join(root, "loop"))
			keep = filepath.Join(root, "loop", "profile")
		}
		os.Chtimes(d, old, old)
		sweep(keep) // "unborn": not created yet, the sweep runs first
		if _, err := os.Stat(d); err != nil {
			t.Errorf("%s swept", k.name)
		}
	}
}

func TestEnvNamesTheCrashDirForThisProcessAndSweepsADeadClients(t *testing.T) {
	root := t.TempDir()
	for _, k := range []string{"TMPDIR", "TMP", "TEMP"} { // os.TempDir: TMPDIR on POSIX, TMP on Windows
		t.Setenv(k, root)
	}
	c := exec.Command(os.Args[0], "-test.run=^$")
	if err := c.Run(); err != nil { // reaped: the pid names no process
		t.Fatal(err)
	}
	dead, me := c.Process.Pid, os.Getpid()
	mk := func(name string, age time.Duration) string {
		d := filepath.Join(root, name)
		os.Mkdir(d, 0o700)
		tm := time.Now().Add(-age)
		os.Chtimes(d, tm, tm)
		return d
	}
	gone := []string{mk(fmt.Sprintf("camoucrome-%d-1234", dead), 2*time.Hour), mk(fmt.Sprintf("camoucrome-crash-%d-1234", dead), 2*time.Hour)}
	kept := []string{mk(fmt.Sprintf("camoucrome-%d-live", me), 2*time.Hour), mk(fmt.Sprintf("camoucrome-%d-young", dead), time.Minute),
		mk("camoucrome-verify-1234", 2*time.Hour), mk(fmt.Sprintf("camoucrome-%d-caller", dead), 2*time.Hour)}
	env, cleanup, err := envFor(Resolved{Config: map[string]any{}}, LaunchOpts{UserDataDir: kept[3]}, nil, "Linux")
	if err != nil {
		t.Fatal(err)
	}
	defer cleanup()
	for _, kv := range env {
		if v, ok := strings.CutPrefix(kv, "BREAKPAD_DUMP_LOCATION="); ok && !strings.HasPrefix(filepath.Base(v), fmt.Sprintf("camoucrome-crash-%d-", me)) {
			t.Errorf("crash dir %s does not carry this pid", v)
		}
	}
	for _, d := range gone {
		if _, err := os.Stat(d); err == nil {
			t.Errorf("%s left behind", filepath.Base(d))
		}
	}
	for _, d := range kept {
		if _, err := os.Stat(d); err != nil {
			t.Errorf("%s swept", filepath.Base(d))
		}
	}
}
