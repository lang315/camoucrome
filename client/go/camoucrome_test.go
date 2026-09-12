package camoucrome

import (
	"encoding/json"
	"fmt"
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
		AcceptLangArg     string   `json:"accept_lang_arg"`
		ExtensionArgs     []string `json:"extension_args"`
		SPKIArg           string   `json:"spki_arg"`
		Fontconfig        struct {
			Env   string            `json:"env"`
			Files map[string]string `json:"files"`
		} `json:"fontconfig"`
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

func TestPerInstanceSeedsMatchTheContract(t *testing.T) {
	raw, _ := os.ReadFile("../../settings/launcher.json")
	var c struct {
		Seeds struct {
			Keys []string `json:"keys"`
		} `json:"per_instance_seeds"`
	}
	if err := json.Unmarshal(raw, &c); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(SeedKeys, c.Seeds.Keys) {
		t.Fatalf("seed keys %v != %v", SeedKeys, c.Seeds.Keys)
	}
	n := 0
	zeroThenCount := func(b []byte) (int, error) { // first draw is zero and must be redrawn
		n++
		if n == 1 {
			return copy(b, []byte{0, 0, 0, 0}), nil
		}
		return copy(b, []byte{byte(n), 1, 2, 3}), nil
	}
	cfg, err := PerInstanceConfig(zeroThenCount)
	if err != nil {
		t.Fatal(err)
	}
	if len(cfg) != len(SeedKeys) || n != len(SeedKeys)+1 {
		t.Fatalf("cfg %v draws %d", cfg, n)
	}
	for k, v := range cfg {
		if v.(uint32) == 0 {
			t.Fatalf("%s is zero", k)
		}
	}
}

func TestParseGenerated(t *testing.T) {
	o, err := ParseGenerated([]byte(`{"config":{"screen.width":1536,"ua:platform":"Windows","canvas:seed":7},"launch":{"window":[1536,824],"dpr":1.25}}`))
	if err != nil {
		t.Fatal(err)
	}
	if o.Window != [2]int{1536, 824} || o.DPR != 1.25 || o.Config.(map[string]any)["ua:platform"] != "Windows" {
		t.Fatalf("parsed %+v", o)
	}
	if _, err := ParseGenerated([]byte(`{"launch":{}}`)); err == nil {
		t.Fatal("empty config must be an error")
	}
	// The parsed options launch with the generator's geometry flags.
	if got := BuildArgs(o); !reflect.DeepEqual(got[len(got)-2:], []string{"--window-size=1536,824", "--force-device-scale-factor=1.25"}) {
		t.Fatalf("args %v", got)
	}
}

func TestAcceptLangExtensionsAndSPKIMatchTheContract(t *testing.T) {
	c := load(t)
	if got := AcceptLangOf(map[string]any{"navigator.languages": []string{"fr-FR", "fr"}}); got != "fr-FR,fr" {
		t.Fatalf("accept-lang %q", got)
	}
	if got := AcceptLangOf(`{"locale:tag":"de-DE"}`); got != "de-DE" {
		t.Fatalf("accept-lang %q", got)
	}
	if got := AcceptLangOf(map[string]any{"screen.width": 1}); got != "" {
		t.Fatalf("accept-lang %q", got)
	}
	headed := false
	args := BuildArgs(Options{Headless: &headed, Config: `{"navigator.languages":["fr-FR","fr"]}`,
		Extensions: []string{"/e1", "/e2"}, SPKIList: []string{"AAA=", "BBB="}})
	want := []string{
		strings.Replace(c.Launch.AcceptLangArg, "{languages}", "fr-FR,fr", 1),
		strings.Replace(c.Launch.ExtensionArgs[0], "{paths}", "/e1,/e2", 1),
		strings.Replace(c.Launch.ExtensionArgs[1], "{paths}", "/e1,/e2", 1),
		strings.Replace(c.Launch.SPKIArg, "{hashes}", "AAA=,BBB=", 1),
	}
	if got := args[len(c.Launch.BaseArgs)+1:]; !reflect.DeepEqual(got, want) {
		t.Fatalf("args %v != %v", got, want)
	}
}

func TestFontconfigFollowsTheClaimedOS(t *testing.T) {
	c := load(t)
	if !reflect.DeepEqual(c.Launch.Fontconfig.Files, FontconfigFiles) || c.Launch.Fontconfig.Env != "FONTCONFIG_FILE" {
		t.Fatalf("contract files %v != %v", c.Launch.Fontconfig.Files, FontconfigFiles)
	}
	root := t.TempDir()
	fonts := root + "/fonts"
	os.MkdirAll(fonts, 0o755)
	os.MkdirAll(root+"/settings/fontconfig", 0o755)
	os.WriteFile(root+"/settings/fontconfig/windows.conf", []byte("<fontconfig/>"), 0o644)
	want := root + "/settings/fontconfig/windows.conf"
	if got := FontconfigFor(Options{Config: map[string]any{"ua:platform": "Windows"}, FontsDir: fonts}); got != want {
		t.Fatalf("windows: %q != %q", got, want)
	}
	if got := FontconfigFor(Options{Config: map[string]any{"ua:platform": "Linux"}, FontsDir: fonts}); got != "" {
		t.Fatalf("linux claim must set nothing, got %q", got)
	}
	if got := FontconfigFor(Options{Preset: map[string]any{"os": "macOS"}, FontsDir: fonts}); !strings.HasSuffix(got, "settings/fontconfig/macos.conf") {
		t.Fatalf("preset os: %q", got)
	}
	os.WriteFile(root+"/chrome", nil, 0o755)
	if got := FontconfigFor(Options{Config: map[string]any{"ua:platform": "Windows"}, ExecutablePath: root + "/chrome"}); got != want {
		t.Fatalf("fonts beside the executable: %q != %q", got, want)
	}
	env, _ := BuildEnv(Options{Config: map[string]any{"ua:platform": "Windows"}, FontsDir: fonts}, nil)
	if env["FONTCONFIG_FILE"] != want {
		t.Fatalf("env: %q", env["FONTCONFIG_FILE"])
	}
	env, _ = BuildEnv(Options{Config: map[string]any{"ua:platform": "Windows"}}, nil)
	if _, ok := env["FONTCONFIG_FILE"]; ok {
		t.Fatal("no fonts dir must set nothing")
	}
}

func TestALargeConfigIsChunkedIntoNumberedEnvStrings(t *testing.T) {
	big := map[string][]string{"fonts:local": make([]string, 700)}
	for i := range big["fonts:local"] {
		big["fonts:local"][i] = strings.Repeat("x", 100)
	}
	env, err := BuildEnv(Options{Config: big}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := env["CAMOU_CONFIG"]; ok {
		t.Fatal("CAMOU_CONFIG set for a large config")
	}
	joined := ""
	for n := 1; ; n++ {
		c, ok := env[fmt.Sprintf("CAMOU_CONFIG_%d", n)]
		if !ok {
			break
		}
		if len([]rune(c)) > configChunkRunes {
			t.Fatalf("chunk %d has %d runes", n, len([]rune(c)))
		}
		joined += c
	}
	var back map[string][]string
	if err := json.Unmarshal([]byte(joined), &back); err != nil || len(back["fonts:local"]) != 700 {
		t.Fatalf("chunks do not reassemble: %v", err)
	}
}
