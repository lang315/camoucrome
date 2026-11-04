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

func TestForeignClaimWithoutAFontsDirFailsOnLinuxOnly(t *testing.T) {
	o := Options{Config: map[string]any{"ua:platform": "Windows"}, ExecutablePath: "/nowhere/chrome"}
	if _, err := buildEnvFor(o, nil, "Linux"); err == nil || !strings.Contains(err.Error(), "Windows") {
		t.Fatalf("Linux host, Windows claim, no fonts dir: err %v", err)
	}
	env, err := buildEnvFor(o, nil, "Windows")
	if _, ok := env["FONTCONFIG_FILE"]; err != nil || ok {
		t.Fatalf("Windows host: env %v err %v", env, err)
	}
	for _, c := range []any{map[string]any{"ua:platform": "Linux"}, nil} {
		if _, err := buildEnvFor(Options{Config: c}, nil, "Linux"); err != nil {
			t.Fatalf("Linux or no claim must pass: %v", err)
		}
	}
}

func TestLaunchWindowMustFitTheConfiguredOuterSize(t *testing.T) {
	both := map[string]any{"window.outerWidth": 1920, "window.outerHeight": 1080}
	for _, c := range []struct {
		name   string
		config any
		window [2]int
		ok     bool
	}{
		{"no window", both, [2]int{}, false},
		{"wider", both, [2]int{1921, 1000}, false},
		{"taller", both, [2]int{1900, 1081}, false},
		{"equal", both, [2]int{1920, 1080}, true},
		{"one key", map[string]any{"window.outerWidth": 1920}, [2]int{1920, 5000}, true},
		{"no outer keys", map[string]any{"a": 1}, [2]int{}, true},
	} {
		f := &fakeLauncher{err: errors.New("stop here")}
		_, err := launch(f, Options{Config: c.config, Window: c.window, UserDataDir: t.TempDir()})
		refused := err != nil && strings.Contains(err.Error(), "window.outer")
		if refused == c.ok {
			t.Errorf("%s: err %v, want ok=%v", c.name, err, c.ok)
		}
	}
}
