package camoucrome

// What a launch leaves on disk, and what its error text carries (the #272
// audit's three client-side holes). Mirrors client/python/tests/test_at_rest.py.

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/mxschmitt/playwright-go"
)

const posix = runtime.GOOS != "windows"

func mode(t *testing.T, p string) os.FileMode {
	t.Helper()
	fi, err := os.Stat(p)
	if err != nil {
		t.Fatal(err)
	}
	return fi.Mode().Perm()
}

// useTempRoot points os.TempDir at root: TMPDIR on POSIX, TMP on Windows (TEMP for any reader of it).
func useTempRoot(t *testing.T, root string) {
	for _, k := range []string{"TMPDIR", "TMP", "TEMP"} {
		t.Setenv(k, root)
	}
}

func withUmask022(t *testing.T) {
	if !posix {
		t.Skip("POSIX modes")
	}
	old := setUmask(0o022)
	t.Cleanup(func() { setUmask(old) })
}

// 1. Profile dir mode.

func TestProfileSeedsCreatesEveryMissingDirOwnerOnly(t *testing.T) {
	withUmask022(t)
	base := t.TempDir()
	udd := filepath.Join(base, "a", "b", "udd")
	if _, err := ProfileSeeds(udd, rand.Read); err != nil {
		t.Fatal(err)
	}
	for _, d := range []string{filepath.Join(base, "a"), filepath.Join(base, "a", "b"), udd} {
		if m := mode(t, d); m != 0o700 {
			t.Errorf("%s: mode %o, want 700", d, m)
		}
	}
}

func TestProfileSeedsLeavesAnExistingDirModeAlone(t *testing.T) {
	withUmask022(t)
	udd := t.TempDir()
	os.Chmod(udd, 0o755)
	if _, err := ProfileSeeds(udd, rand.Read); err != nil {
		t.Fatal(err)
	}
	if m := mode(t, udd); m != 0o755 {
		t.Errorf("mode %o, want 755 kept", m)
	}
}

func TestTempDirsMatchTheContract(t *testing.T) {
	raw, err := os.ReadFile("../../settings/launcher.json")
	if err != nil {
		t.Fatal(err)
	}
	var c struct {
		Launch struct {
			TempDirs struct {
				Prefix     string `json:"prefix"`
				CrashKind  string `json:"crash_kind"`
				StaleAfter int    `json:"stale_after_seconds"`
			} `json:"temp_dirs"`
		} `json:"launch"`
	}
	if err := json.Unmarshal(raw, &c); err != nil {
		t.Fatal(err)
	}
	td := c.Launch.TempDirs
	if td.Prefix != tempPrefix || td.CrashKind != crashKind || time.Duration(td.StaleAfter)*time.Second != staleAfter {
		t.Fatalf("launch.temp_dirs %+v, client %q %q %v", td, tempPrefix, crashKind, staleAfter)
	}
}

func TestLaunchTempDirsAreOwnerOnlyAndCarryTheClientPid(t *testing.T) {
	useTempRoot(t, t.TempDir())
	f := &fakeLauncher{err: errors.New("stop here")}
	var dirs []string
	f.hook = func() {
		dirs = []string{f.dir, f.opts.Env[CrashDumpsEnv]}
		for _, d := range dirs {
			if m := mode(t, d); posix && m != 0o700 {
				t.Errorf("%s: mode %o, want 700", d, m)
			}
		}
	}
	launch(f, Options{ExecutablePath: "/x/chrome"})
	pid := os.Getpid()
	if !strings.HasPrefix(filepath.Base(dirs[0]), fmt.Sprintf("camoucrome-%d-", pid)) ||
		!strings.HasPrefix(filepath.Base(dirs[1]), fmt.Sprintf("camoucrome-crash-%d-", pid)) {
		t.Errorf("temp dirs %v do not carry this pid %d", dirs, pid)
	}
}

// 2. Stale temp dirs of a killed client.

func deadPid(t *testing.T) int {
	t.Helper()
	c := exec.Command(os.Args[0], "-test.run=^$")
	if err := c.Run(); err != nil { // reaped: the pid names no process
		t.Fatal(err)
	}
	return c.Process.Pid
}

func made(t *testing.T, root, name string, age time.Duration, lockPid int) string {
	t.Helper()
	d := filepath.Join(root, name)
	if err := os.Mkdir(d, 0o700); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(filepath.Join(d, "Preferences"), []byte(`{"intl":{"accept_languages":"xx-YY"}}`), 0o600)
	if lockPid != 0 {
		os.Symlink(fmt.Sprintf("somehost-%d", lockPid), filepath.Join(d, "SingletonLock"))
	}
	tm := time.Now().Add(-age)
	os.Chtimes(d, tm, tm)
	return d
}

func TestLaunchSweepsOnlyADeadClientsOldTempDirs(t *testing.T) {
	root := t.TempDir()
	useTempRoot(t, root)
	dead, me, old := deadPid(t), os.Getpid(), 2*time.Hour
	gone := []string{made(t, root, fmt.Sprintf("camoucrome-%d-1234", dead), old, 0),
		made(t, root, fmt.Sprintf("camoucrome-crash-%d-1234", dead), old, 0)}
	kept := []string{made(t, root, fmt.Sprintf("camoucrome-%d-live", me), old, 0),
		made(t, root, fmt.Sprintf("camoucrome-%d-young", dead), time.Minute, 0),
		made(t, root, "camoucrome-verify-1234", old, 0),
		made(t, root, "camoucrome-1234", old, 0),
		made(t, root, fmt.Sprintf("camoucrome-%d-caller", dead), old, 0)}
	link := filepath.Join(root, fmt.Sprintf("camoucrome-%d-link", dead))
	if posix {
		kept = append(kept, made(t, root, fmt.Sprintf("camoucrome-%d-locked", dead), old, me))
		target := made(t, root, "elsewhere", old, 0)
		os.Symlink(target, link)
		kept = append(kept, target)
	}
	file := filepath.Join(root, fmt.Sprintf("camoucrome-%d-file", dead))
	os.WriteFile(file, []byte("x"), 0o600)
	launch(&fakeLauncher{err: errors.New("stop here")}, Options{UserDataDir: kept[4]})
	for _, d := range gone {
		if _, err := os.Stat(d); err == nil {
			t.Errorf("%s left behind", filepath.Base(d))
		}
	}
	for _, d := range kept {
		if _, err := os.Stat(filepath.Join(d, "Preferences")); err != nil {
			t.Errorf("%s swept", filepath.Base(d))
		}
	}
	if _, err := os.Stat(file); err != nil {
		t.Error("a plain file was swept")
	}
	if fi, err := os.Lstat(link); posix && (err != nil || fi.Mode()&os.ModeSymlink == 0) {
		t.Error("a symlink was swept")
	}
}

func TestSweepSparesTheCallersDirHoweverItIsSpelled(t *testing.T) {
	if !posix {
		t.Skip("symlinks")
	}
	root := t.TempDir()
	useTempRoot(t, root)
	alias := filepath.Join(t.TempDir(), "alias") // another spelling of the temp root (/var vs /private/var)
	if err := os.Symlink(root, alias); err != nil {
		t.Fatal(err)
	}
	dead := deadPid(t)
	for _, c := range []struct{ name, below string }{{"caller", ""}, {"outer", "profile"}, {"unborn", "not/yet"}} {
		d := made(t, root, fmt.Sprintf("camoucrome-%d-%s", dead, c.name), 2*time.Hour, 0)
		if c.name == "outer" { // the caller's dir inside a candidate
			os.Mkdir(filepath.Join(d, "profile"), 0o700)
			tm := time.Now().Add(-2 * time.Hour) // the child's mkdir made it young
			os.Chtimes(d, tm, tm)
		}
		Sweep(filepath.Join(alias, filepath.Base(d), c.below)) // "unborn": not created yet, the sweep runs first
		if _, err := os.Stat(filepath.Join(d, "Preferences")); err != nil {
			t.Errorf("%s swept", c.name)
		}
	}
}

func TestSweepRemovesNothingWhenTheCallersDirCannotBeResolved(t *testing.T) {
	if !posix {
		t.Skip("symlinks")
	}
	root := t.TempDir()
	useTempRoot(t, root)
	stale := made(t, root, fmt.Sprintf("camoucrome-%d-1234", deadPid(t)), 2*time.Hour, 0)
	os.Symlink("loop", filepath.Join(root, "loop")) // ELOOP: neither found nor missing
	Sweep(filepath.Join(root, "loop", "profile"))
	if _, err := os.Stat(stale); err != nil {
		t.Error("swept on doubt")
	}
}

// chain is err and every error below it, through both Unwrap forms.
func chain(err error) []error {
	if err == nil {
		return nil
	}
	out := []error{err}
	switch u := err.(type) {
	case interface{ Unwrap() error }:
		out = append(out, chain(u.Unwrap())...)
	case interface{ Unwrap() []error }:
		for _, e := range u.Unwrap() {
			out = append(out, chain(e)...)
		}
	}
	return out
}

func TestRedactedErrorKeepsErrorsIsAndHidesTheRawTextBelowIt(t *testing.T) {
	env, err := buildEnvFor(Options{Config: atConfig, Preset: atPreset}, nil, "Windows") // host pinned: a Windows claim on Linux needs fonts
	if err != nil {
		t.Fatal(err)
	}
	pwErr := &playwright.Error{Message: atStderr}
	for name, e := range map[string]error{
		"deadline": fmt.Errorf("could not launch: %s: %w", atStderr, context.DeadlineExceeded),
		"driver":   fmt.Errorf("could not launch: %w", pwErr),
	} {
		r := redactErr(e, env)
		if name == "deadline" && !errors.Is(r, context.DeadlineExceeded) {
			t.Errorf("%s: errors.Is(context.DeadlineExceeded) lost", name)
		}
		var as *playwright.Error
		if name == "driver" && (!errors.Is(r, pwErr) || !errors.As(r, &as) || as != pwErr) {
			t.Errorf("%s: the driver's error is no longer reachable", name)
		}
		for _, c := range chain(r) {
			if l := leaked(c.Error(), atSecrets); len(l) != 0 {
				t.Errorf("%s: %T in the chain leaks %q", name, c, l)
			}
		}
	}
}

// 3. Browser stderr in the launch error.

var (
	atConfig = map[string]any{"navigator.platform": "Win32", "timezone:id": "Asia/Secretville",
		"navigator.hardwareConcurrency": 8, "ua:fullVersion": "157.0.8103.51", "navigator.languages": []any{"xq-ZZ", "xq"}}
	atPreset = map[string]any{"os": "Windows", "gpu": "ANGLE (Secret GPU 9000)"}
	atStderr = strings.Join([]string{
		"browserType.launchPersistentContext: Target page, context or browser has been closed",
		"Browser logs:",
		"<launching> /x/chrome --accept-lang=xq-ZZ,xq --user-data-dir=/p",
		"[pid=7][err] [7:7:ERROR:coherence_validator.cc(726)] camoucfg: invariant 'inv-1' violated. " +
			"'navigator.platform' is 'Win32', which disagrees with 'ua:osInfo'. It should be 'MacIntel'. Not repaired: x",
		"[pid=7][err] [7:7:ERROR:coherence_validator.cc(707)] camoucfg: invariant 'inv-2' violated. " +
			"'ua:fullVersion' is set but 'x.y' is not. It should be Mozilla/5.0 (Derived 1.2). Not repaired: x",
		"[pid=7][err] [7:7:ERROR:coherence_validator.cc(743)] camoucfg: 'navigator.hardwareConcurrency' is '8', out of range",
		"[pid=7][err] [7:7:WARNING:tz.cc(1)] camoucfg: timezone:id 'Asia/Secretville' invalid; falling back to UTC",
		"[pid=7][err] [7:7:WARNING:gpu.cc(1)] renderer ANGLE (Secret GPU 9000) chosen",
		"[pid=7][err] [7:7:WARNING:ua.cc(1)] camoucfg: 'ua:osInfo' is set but 'ua:platform' is not, so x",
	}, "\n")
	atSecrets = []string{"Win32", "MacIntel", "Mozilla/5.0 (Derived 1.2)", "'8'", "Asia/Secretville", "157.0.8103.51",
		"xq-ZZ", "Secret GPU 9000"}
	atKept = []string{"invariant 'inv-1' violated", "but 'x.y' is not", "camoucfg: 'ua:osInfo' is set but 'ua:platform' is not, so x",
		"'navigator.hardwareConcurrency' is '<redacted>', out of range", "coherence_validator.cc(743)"} // public names stay
)

func leaked(text string, secrets []string) []string {
	return slices.DeleteFunc(slices.Clone(secrets), func(s string) bool { return !strings.Contains(text, s) })
}

func TestLaunchErrorHasTheConfiguredValuesRedactedLineByLine(t *testing.T) {
	useTempRoot(t, t.TempDir())
	old := hostOS
	hostOS = "Windows" // the claim's own host: launch() must not stop at the Linux fonts-dir check
	t.Cleanup(func() { hostOS = old })
	noPin := false // a fake driver has no pid to pin, and the box has more CPUs than the claim
	o := Options{ExecutablePath: "/x/chrome", Config: atConfig, Preset: atPreset, PinCPUCores: &noPin}
	env, err := buildEnvFor(o, nil, "Windows")
	if err != nil {
		t.Fatal(err)
	}
	pwErr := &playwright.Error{Name: "TargetClosedError", Message: atStderr + "\n" + env["CAMOU_CONFIG"], Stack: "at " + atStderr}
	_, err = launch(&fakeLauncher{err: fmt.Errorf("could not launch: %w", pwErr)}, o)
	secrets := append(slices.Clone(atSecrets), env["CAMOU_CONFIG"])
	for name, text := range map[string]string{"Error()": err.Error(), "Message": pwErr.Message, "Stack": pwErr.Stack} {
		if l := leaked(text, secrets); len(l) != 0 {
			t.Errorf("%s leaks %q", name, l)
		}
	}
	if !errors.Is(err, pwErr) {
		t.Error("the driver's error is no longer in the chain")
	}
	if got, want := strings.Count(err.Error(), "\n"), strings.Count(atStderr, "\n")+1; got != want {
		t.Errorf("%d newlines, want %d (line structure kept)", got, want)
	}
	if l := leaked(err.Error(), atKept); len(l) != len(atKept) {
		t.Errorf("public names lost:\n%s", err)
	}
}

func TestRedactDropsChunkedConfigAndPresetStrings(t *testing.T) {
	env, err := buildEnvFor(Options{Config: map[string]any{"k:big": strings.Repeat("Q", 70000)},
		Preset: map[string]any{"os": "Windows", "pad": strings.Repeat("P", 70000)}}, nil, "Windows")
	if err != nil {
		t.Fatal(err)
	}
	if env["CAMOU_CONFIG_1"] == "" || env["CAMOU_PRESET_2"] == "" {
		t.Fatalf("not chunked: %d keys", len(env))
	}
	out := Redact(env["CAMOU_CONFIG_1"]+"\n"+env["CAMOU_PRESET_2"]+"\nQQQ", env)
	if strings.Contains(out, strings.Repeat("Q", 100)) || strings.Contains(out, strings.Repeat("P", 100)) {
		t.Error("a chunk survived")
	}
}
