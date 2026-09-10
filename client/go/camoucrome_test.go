package camoucrome

import (
	"encoding/json"
	"os"
	"reflect"
	"strings"
	"testing"
)

type contract struct {
	Forbidden struct {
		Options []string `json:"options"`
	} `json:"forbidden_context_options"`
	Launch struct {
		BaseArgs          []string `json:"base_args"`
		WindowSizeArg     string   `json:"window_size_arg"`
		DPRArg            string   `json:"dpr_arg"`
		HeadlessArg       string   `json:"headless_arg"`
		IgnoreDefaultArgs bool     `json:"ignore_default_args"`
	} `json:"launch"`
}

func load(t *testing.T) contract {
	raw, err := os.ReadFile("../../settings/launcher.json")
	if err != nil {
		t.Fatal(err)
	}
	var c contract
	if err := json.Unmarshal(raw, &c); err != nil {
		t.Fatal(err)
	}
	return c
}

// Parity with settings/launcher.json: same base args, same templates.
func TestArgsMatchTheContract(t *testing.T) {
	c := load(t)
	headed := false
	pipe := "--remote-debugging-pipe"
	if got := BuildArgs(Options{Headless: &headed}); !reflect.DeepEqual(got, append(append([]string{}, c.Launch.BaseArgs...), pipe)) {
		t.Fatalf("base args %v != %v", got, c.Launch.BaseArgs)
	}
	if got := BuildArgs(Options{}); !reflect.DeepEqual(got, append(append([]string{}, c.Launch.BaseArgs...), c.Launch.HeadlessArg, pipe)) {
		t.Fatalf("headless args %v", got)
	}
	want := append(append([]string{}, c.Launch.BaseArgs...), pipe, "--user-data-dir=/p",
		strings.NewReplacer("{width}", "1920", "{height}", "1040").Replace(c.Launch.WindowSizeArg),
		strings.NewReplacer("{dpr}", "1.25").Replace(c.Launch.DPRArg))
	if got := BuildArgs(Options{Headless: &headed, UserDataDir: "/p", Window: [2]int{1920, 1040}, DPR: 1.25}); !reflect.DeepEqual(got, want) {
		t.Fatalf("args %v != %v", got, want)
	}
	if !c.Launch.IgnoreDefaultArgs {
		t.Fatal("contract must require ignore_default_args; Launch passes IgnoreAllDefaultArgs")
	}
}

// The forbidden options are forbidden by construction: Options has no such
// field. This pins that a future field does not sneak one in.
func TestNoForbiddenOptionField(t *testing.T) {
	c := load(t)
	typ := reflect.TypeOf(Options{})
	for _, name := range c.Forbidden.Options {
		flat := strings.ReplaceAll(strings.ToLower(name), "_", "")
		for i := 0; i < typ.NumField(); i++ {
			if strings.ToLower(typ.Field(i).Name) == flat {
				t.Fatalf("Options.%s duplicates a CAMOU_CONFIG surface", typ.Field(i).Name)
			}
		}
	}
}

func TestEnvDropsStaleCamouVarsAndSetsTheTransport(t *testing.T) {
	env, err := BuildEnv(Options{Config: map[string]int{"screen.width": 1}, Preset: `{"os":"Windows"}`, Strict: true},
		[]string{"CAMOU_CONFIG_1=stale", "PATH=/bin"})
	if err != nil {
		t.Fatal(err)
	}
	want := map[string]string{"PATH": "/bin", "CAMOU_CONFIG": `{"screen.width":1}`,
		"CAMOU_PRESET": `{"os":"Windows"}`, "CAMOU_CONFIG_STRICT": "1"}
	if !reflect.DeepEqual(env, want) {
		t.Fatalf("env %v != %v", env, want)
	}
}
