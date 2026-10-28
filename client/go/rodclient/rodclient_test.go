package rodclient

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	camoucrome "github.com/lang315/camoucrome/client/go"
	"github.com/lang315/camoucrome/client/go/rodclient/internal/browser"
)

var errStub = errors.New("stub: no browser")

// capture swaps startFn for one that records what Launch hands the process
// and fails, so no browser is needed.
func capture(t *testing.T) (exe *string, argv *[]string, env *map[string]string) {
	t.Helper()
	exe, argv, env = new(string), new([]string), new(map[string]string)
	old := startFn
	t.Cleanup(func() { startFn = old })
	startFn = func(_ context.Context, e string, a []string, v map[string]string) (*browser.Proc, error) {
		*exe, *argv, *env = e, a, v
		if d := v[camoucrome.CrashDumpsEnv]; d == "" {
			t.Error("no crash-dump dir in env")
		} else if _, err := os.Stat(d); err != nil {
			t.Errorf("crash dir missing during start: %v", err)
		}
		return nil, errStub
	}
	return
}

func TestLaunchParity(t *testing.T) {
	root := t.TempDir()
	fonts := filepath.Join(root, "fonts")
	os.MkdirAll(fonts, 0o755)
	os.MkdirAll(filepath.Join(root, "settings", "fontconfig"), 0o755)
	os.WriteFile(filepath.Join(root, "settings", "fontconfig", "windows.conf"), []byte("<fontconfig/>"), 0o644)
	headed := false
	cases := map[string]camoucrome.Options{
		"empty":   {ExecutablePath: "/x/chrome"},
		"windows": {ExecutablePath: "/x/chrome", Config: map[string]any{"ua:platform": "Windows"}, FontsDir: fonts},
		"ext+spki": {ExecutablePath: "/x/chrome", Extensions: []string{"/e/one", "/e/two"},
			SPKIList: []string{"AAAA="}, ExtraArgs: []string{"--foo"}},
		"headed": {ExecutablePath: "/x/chrome", Headless: &headed, Window: [2]int{1536, 824}, DPR: 1.25,
			Position: &[2]int{10, 20}},
	}
	for name, o := range cases {
		t.Run(name, func(t *testing.T) {
			exe, argv, env := capture(t)
			if _, err := Launch(context.Background(), o); !errors.Is(err, errStub) {
				t.Fatalf("err = %v", err)
			}
			if *exe != o.ExecutablePath {
				t.Fatalf("exe %q", *exe)
			}
			// The temp profile Launch substitutes is the one value that differs from BuildArgs(o).
			var dir string
			for _, a := range *argv {
				if v, ok := strings.CutPrefix(a, "--user-data-dir="); ok {
					dir = v
				}
			}
			if !strings.HasPrefix(filepath.Base(dir), "camoucrome-") {
				t.Fatalf("no temp profile in argv: %v", *argv)
			}
			o2 := o
			o2.UserDataDir = dir
			if want := camoucrome.BuildArgs(o2); !reflect.DeepEqual(*argv, want) {
				t.Fatalf("argv\n got %v\nwant %v", *argv, want)
			}
			want, err := camoucrome.BuildEnv(o, os.Environ())
			if err != nil {
				t.Fatal(err)
			}
			crash := (*env)[camoucrome.CrashDumpsEnv]
			want[camoucrome.CrashDumpsEnv] = crash
			if !reflect.DeepEqual(*env, want) {
				t.Fatalf("env differs from BuildEnv + crash entry")
			}
			for _, d := range []string{dir, crash} {
				if _, err := os.Stat(d); !os.IsNotExist(err) {
					t.Fatalf("%s left behind after failed start (%v)", d, err)
				}
			}
		})
	}
}

func TestLaunchKeepsCallerProfile(t *testing.T) {
	_, argv, _ := capture(t)
	dir := t.TempDir()
	Launch(context.Background(), camoucrome.Options{ExecutablePath: "/x/chrome", UserDataDir: dir})
	if !reflect.DeepEqual((*argv)[len(*argv)-1:], []string{"--user-data-dir=" + dir}) && !contains(*argv, "--user-data-dir="+dir) {
		t.Fatalf("argv lacks caller dir: %v", *argv)
	}
	if _, err := os.Stat(dir); err != nil {
		t.Fatal("caller profile removed")
	}
}

func contains(l []string, s string) bool {
	for _, x := range l {
		if x == s {
			return true
		}
	}
	return false
}

func TestLaunchRejectsProxy(t *testing.T) {
	exe, _, _ := capture(t)
	_, err := Launch(context.Background(), camoucrome.Options{ExecutablePath: "/x/chrome",
		Proxy: &camoucrome.Proxy{Server: "http://127.0.0.1:1", Username: "u", Password: "p"}})
	if err == nil || !strings.Contains(err.Error(), "proxy not supported by rodclient v1") {
		t.Fatalf("err = %v", err)
	}
	if *exe != "" {
		t.Fatal("process started despite proxy")
	}
}
