package camoucrome

import (
	"errors"
	"os"
	"reflect"
	"strings"
	"testing"

	"github.com/mxschmitt/playwright-go"
)

// fakeLauncher records what Launch hands the driver, the way the Python and
// Node tests do with a fake chromium.
type fakeLauncher struct {
	dir  string
	opts playwright.BrowserTypeLaunchPersistentContextOptions
	err  error
	ctx  playwright.BrowserContext
}

func (f *fakeLauncher) LaunchPersistentContext(dir string, o ...playwright.BrowserTypeLaunchPersistentContextOptions) (playwright.BrowserContext, error) {
	f.dir, f.opts = dir, o[0]
	return f.ctx, f.err
}

func TestFailedLaunchRemovesTheTempProfileAndTheCrashDir(t *testing.T) {
	f := &fakeLauncher{err: errors.New("driver gone")}
	if _, err := launch(f, Options{ExecutablePath: "/x/chrome"}); err == nil {
		t.Fatal("launch error was swallowed")
	}
	crash := f.opts.Env[CrashDumpsEnv]
	for _, d := range []string{f.dir, crash} {
		if d == "" {
			t.Fatalf("no directory handed to the driver: dir %q crash %q", f.dir, crash)
		}
		if _, err := os.Stat(d); !os.IsNotExist(err) {
			t.Errorf("%s still there after the launch failed", d)
		}
	}
}

func TestFailedLaunchKeepsACallersProfile(t *testing.T) {
	mine := t.TempDir()
	f := &fakeLauncher{err: errors.New("driver gone")}
	launch(f, Options{UserDataDir: mine})
	if _, err := os.Stat(mine); err != nil {
		t.Errorf("a profile the caller owns was removed: %v", err)
	}
	if f.dir != mine {
		t.Errorf("driver got %q, want the caller's %q", f.dir, mine)
	}
}

func TestLaunchHandsTheDriverTheConfigInTheEnvAndExtraArgsLast(t *testing.T) {
	f := &fakeLauncher{err: errors.New("stop here")}
	o := Options{Config: `{"timezone:id":"Asia/Tokyo"}`, ExtraArgs: []string{"--first-extra", "--last-extra"}}
	launch(f, o)
	if got := f.opts.Env["CAMOU_CONFIG"]; !strings.Contains(got, "Asia/Tokyo") {
		t.Errorf("CAMOU_CONFIG %q lacks the config", got)
	}
	args := f.opts.Args
	if n := len(args); n < 2 || !reflect.DeepEqual(args[n-2:], o.ExtraArgs) {
		t.Errorf("extra args are not last: %v", args)
	}
	if want := BuildArgs(Options{Config: o.Config, ExtraArgs: o.ExtraArgs, UserDataDir: f.dir}); !reflect.DeepEqual(args, want) {
		t.Errorf("argv order\n got %v\nwant %v", args, want)
	}
	if f.opts.IgnoreAllDefaultArgs == nil || !*f.opts.IgnoreAllDefaultArgs || f.opts.NoViewport == nil || !*f.opts.NoViewport {
		t.Errorf("IgnoreAllDefaultArgs and NoViewport must both be true: %+v", f.opts)
	}
}
