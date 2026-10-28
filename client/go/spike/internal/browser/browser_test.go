package browser

import (
	"encoding/json"
	"os"
	"strings"
	"testing"

	camoucrome "github.com/lang315/camoucrome/client/go"
)

func TestArgvHasContractFlags(t *testing.T) {
	raw, err := os.ReadFile("../../../../../settings/launcher.json")
	if err != nil {
		t.Fatal(err)
	}
	var c struct {
		MustNot []string `json:"browser_argv_must_not_contain"`
	}
	if err := json.Unmarshal(raw, &c); err != nil || len(c.MustNot) == 0 {
		t.Fatalf("launcher.json: %v, %d forbidden", err, len(c.MustNot))
	}
	has := func(argv []string, a string) bool {
		for _, x := range argv {
			if x == a {
				return true
			}
		}
		return false
	}
	argv := buildArgv(Options{Executable: "x"}, "/p")
	for _, a := range append(camoucrome.BaseArgs, "--remote-debugging-port=0", "--headless=new", "--user-data-dir=/p") {
		if !has(argv, a) {
			t.Errorf("argv %v lacks %s", argv, a)
		}
	}
	if has(buildArgv(Options{Executable: "x", Headed: true}, "/p"), "--headless=new") {
		t.Error("Headed still has --headless=new")
	}
	// --remote-debugging-port=0 is the spike's one intended deviation: rod and
	// chromedp need a socket, the contract says pipe. C4 will flag it.
	for _, bad := range c.MustNot {
		if bad == "--remote-debugging-port" {
			continue
		}
		for _, a := range argv {
			if strings.HasPrefix(a, bad) {
				t.Errorf("argv has forbidden %s", a)
			}
		}
	}
	if !has(argv, "--no-sandbox") || has(buildArgv(Options{Sandbox: true}, "/p"), "--no-sandbox") {
		t.Error("--no-sandbox must follow !Sandbox")
	}
}

func TestEnvDropsParentCamou(t *testing.T) {
	env, err := buildEnv(Options{Config: `{"navigator.hardwareConcurrency":4}`}, []string{"CAMOU_CONFIG=evil", "CAMOU_CONFIG_1=evil", "PATH=/bin"})
	if err != nil {
		t.Fatal(err)
	}
	joined := strings.Join(env, "\n")
	if strings.Contains(joined, "evil") || !strings.Contains(joined, "CAMOU_CONFIG={") || !strings.Contains(joined, "PATH=/bin") {
		t.Fatalf("env %v", env)
	}
}
