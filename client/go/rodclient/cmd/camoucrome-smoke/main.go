// Smoke program: drive the fork through rodclient against a loopback page that
// logs every input event, then judge the page's own log (see checks.go). Prints
// one JSON report and exits 1 if any check is RED.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	camoucrome "github.com/lang315/camoucrome/client/go"
	"github.com/lang315/camoucrome/client/go/rodclient"
)

const pageHTML = `<!doctype html><title>smoke</title>
<style>body{margin:0}#btn{position:absolute;left:200px;top:150px;width:120px;height:40px}
#in{position:absolute;left:200px;top:250px;width:300px}#out{position:absolute;left:200px;top:300px;white-space:pre}</style>
<button id="btn">Click me</button><input id="in"><div id="out"></div>
<script>
document.cookie = "smoke=1; path=/";
window.__ev = [];
let pending = false;
function rec(e) {
  const t = e.target;
  window.__ev.push({type: e.type, isTrusted: e.isTrusted, t: e.timeStamp, button: e.button || 0, buttons: e.buttons || 0,
    key: e.key || "", code: e.code || "", x: e.clientX || 0, y: e.clientY || 0,
    v: t && t.value !== undefined ? t.value : "", tgt: t && t.id ? t.id : ""});
  if (!pending) {
    pending = true;
    setTimeout(() => { pending = false; document.getElementById("out").textContent = JSON.stringify(window.__ev); }, 0);
  }
}
for (const type of ["mousemove", "mousedown", "mouseup", "click", "pointerdown", "pointerup", "keydown", "keypress",
                    "keyup", "input", "wheel", "focus"]) addEventListener(type, rec, true);
</script>`

type cfg struct {
	exe, config, preset      string
	headed, strict, humanize bool
}

func parseFlags(args []string) (*cfg, error) {
	fs := flag.NewFlagSet("camoucrome-smoke", flag.ContinueOnError)
	c := &cfg{}
	fs.StringVar(&c.exe, "executable", "", "browser binary")
	fs.StringVar(&c.config, "config", "", "CAMOU_CONFIG JSON (or @file)")
	fs.StringVar(&c.preset, "preset", "", "CAMOU_PRESET JSON (or @file)")
	fs.BoolVar(&c.headed, "headed", false, "not headless")
	fs.BoolVar(&c.strict, "strict", false, "CAMOU_CONFIG_STRICT=1")
	fs.BoolVar(&c.humanize, "humanize", false, `add {"humanize:enabled": true} to the config and check the humanized path`)
	if err := fs.Parse(args); err != nil {
		return nil, err
	}
	return c, nil
}

func readArg(v string) (string, error) {
	if strings.HasPrefix(v, "@") {
		raw, err := os.ReadFile(v[1:])
		return string(raw), err
	}
	return v, nil
}

func (c *cfg) options() (camoucrome.Options, error) {
	headless := !c.headed
	o := camoucrome.Options{ExecutablePath: c.exe, Headless: &headless, Strict: c.strict, ExtraArgs: []string{"--no-sandbox"}}
	conf, err := readArg(c.config)
	if err != nil {
		return o, err
	}
	if conf != "" || c.humanize {
		m := map[string]any{}
		if conf != "" {
			if err := json.Unmarshal([]byte(conf), &m); err != nil {
				return o, fmt.Errorf("config: %w", err)
			}
		}
		if c.humanize {
			m["humanize:enabled"] = true
		}
		o.Config = m
	}
	pre, err := readArg(c.preset)
	if err != nil {
		return o, err
	}
	if pre != "" {
		o.Preset = pre
	}
	return o, nil
}

func serve() (url string, stop func(), err error) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return "", nil, err
	}
	srv := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		io.WriteString(w, pageHTML)
	})}
	go srv.Serve(ln)
	return "http://" + ln.Addr().String() + "/", func() { srv.Close() }, nil
}

type report struct {
	Checks   []Check        `json:"checks"`
	Events   []Event        `json:"events"`
	CDPSends map[string]int `json:"cdp_sends"`
	Argv     []string       `json:"argv"`
}

// drive runs the scenario and fills r; a step error ends it early.
func drive(ctx context.Context, b *rodclient.Browser, url string, r *Run) error {
	p, err := b.NewPage(ctx)
	if err != nil {
		return fmt.Errorf("page: %w", err)
	}
	if err := p.Goto(ctx, url, rodclient.WaitLoad); err != nil {
		return err
	}
	for i := 0; i < 2; i++ { // the second exercises "a previous move exists"
		if err := p.Click(ctx, "#btn"); err != nil {
			return err
		}
	}
	if err := p.Type(ctx, "#in", r.Typed); err != nil {
		return err
	}
	if s, err := p.Text(ctx, "#btn"); err != nil || s != "Click me" {
		return fmt.Errorf("Text(#btn) = %q, %v", s, err)
	}
	// #out mirrors window.__ev one tick after each event; wait for the last input.
	deadline := time.Now().Add(5 * time.Second)
	for {
		s, err := p.Text(ctx, "#out")
		if err != nil {
			return err
		}
		var evs []Event
		if json.Unmarshal([]byte(s), &evs) == nil && len(evs) > 0 {
			r.Events = evs
			if last := lastInput(evs); last == r.Typed {
				break
			}
		}
		if time.Now().After(deadline) {
			break // the checks report what is missing
		}
		time.Sleep(50 * time.Millisecond)
	}
	if r.PNG, err = p.Screenshot(ctx); err != nil {
		return err
	}
	cs, err := p.Cookies(ctx)
	if err != nil {
		return err
	}
	r.Cookies = map[string]string{}
	for _, c := range cs {
		r.Cookies[c.Name] = c.Value
	}
	return p.Close(ctx)
}

func lastInput(evs []Event) string {
	v := ""
	for _, e := range evs {
		if e.Type == "input" && e.Tgt == "in" {
			v = e.V
		}
	}
	return v
}

func run(args []string, stdout, stderr io.Writer) int {
	c, err := parseFlags(args)
	if err != nil {
		fmt.Fprintln(stderr, "flags:", err)
		return 2
	}
	o, err := c.options()
	if err != nil {
		fmt.Fprintln(stderr, "flags:", err)
		return 2
	}
	url, stop, err := serve()
	if err != nil {
		fmt.Fprintln(stderr, "serve:", err)
		return 1
	}
	defer stop()
	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
	defer cancel()
	var mu sync.Mutex
	sends := map[string]int{}
	b, err := rodclient.Launch(ctx, o, rodclient.WithSendObserver(func(m []byte) {
		var q struct {
			Method string `json:"method"`
		}
		json.Unmarshal(m, &q)
		mu.Lock()
		sends[q.Method]++
		mu.Unlock()
	}))
	if err != nil {
		fmt.Fprintln(stderr, "launch:", err)
		return 1
	}
	defer b.Close()
	rn := &Run{Typed: typedASCII + "é", Humanize: c.humanize}
	derr := drive(ctx, b, url, rn)
	mu.Lock()
	rn.Sends = sends
	rep := report{Events: rn.Events, CDPSends: sends, Argv: b.Argv()}
	mu.Unlock()
	rep.Checks = Evaluate(*rn)
	if derr != nil {
		rep.Checks = append(rep.Checks, Check{"scenario ran to the end (want no error)", false, derr.Error()})
	}
	out, _ := json.MarshalIndent(rep, "", " ")
	fmt.Fprintln(stdout, string(out))
	if Failed(rep.Checks) {
		return 1
	}
	return 0
}

func main() { os.Exit(run(os.Args[1:], os.Stdout, os.Stderr)) }
