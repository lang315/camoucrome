// Package workload is the one workload both drivers run, and the CLI they share.
package workload

import (
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/url"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"
)

const (
	ASCII        = "camou footprint"
	VI           = "Tiếng Việt có dấu"
	ActWindow    = 15 * time.Second
	L3JS         = "() => [document.querySelector('#t1') !== null, document.getElementsByClassName('x').length]"
	Prelude      = "function __h(){}"
	FacebookWait = 60 * time.Second
)

var RebrowserJS = "() => { document.getElementsByClassName('div'); return document.body.innerText.length }"

// Flags is the CLI both drivers implement.
type Flags struct {
	Exe, ArgsJSON, EnvJSON, Profile, Mode, URL, Out string
	MainWorld, Native                               bool
}

func ParseFlags() *Flags {
	f := &Flags{}
	flag.StringVar(&f.Exe, "exe", "", "browser executable")
	flag.StringVar(&f.ArgsJSON, "args-json", "", "file: JSON list of browser flags")
	flag.StringVar(&f.EnvJSON, "env-json", "", "file: JSON object of extra env")
	flag.StringVar(&f.Profile, "profile", "", "user data dir")
	flag.StringVar(&f.Mode, "mode", "probe", "probe|detector|facebook")
	flag.StringVar(&f.URL, "url", "", "page URL")
	flag.StringVar(&f.Out, "out", "", "result JSON file")
	flag.BoolVar(&f.MainWorld, "main-world", false, "tdpdrive: evaluate in the main world")
	flag.BoolVar(&f.Native, "native", false, "reddrive: the clean arm, raw CDP input with no eval and no Runtime.enable")
	flag.Parse()
	return f
}

// Args reads --args-json (empty if unset).
func (f *Flags) Args() ([]string, error) {
	var a []string
	return a, readJSON(f.ArgsJSON, &a)
}

// Env is the child environment exactly as --env-json gives it (build_env already dropped the CAMOU_* of the parent).
func (f *Flags) Env() ([]string, error) {
	var m map[string]string
	if err := readJSON(f.EnvJSON, &m); err != nil {
		return nil, err
	}
	var env []string
	for k, v := range m {
		env = append(env, k+"="+v)
	}
	return env, nil
}

func readJSON(path string, v any) error {
	if path == "" {
		return nil
	}
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, v)
}

// Driver is what a CDP stack must offer to run the workload.
type Driver interface {
	Launch(f *Flags) error
	Navigate(url string) error // returns after load
	WaitSelector(sel string) error
	Eval(js string) error
	EvalString(js string) (string, error)
	Type(sel, text string) error // focus the element, then type
	Click(sel string) error
	Methods() map[string]int
	Close()
}

// ErrNA marks an action or routing the driver's own API cannot do; the reason follows. Never emulated with an eval.
var ErrNA = errors.New("n/a")

func NA(reason string) error { return fmt.Errorf("%w: %s", ErrNA, reason) }

// Prober is what the driver probes add to Driver: L9 actions and header-routing conditions.
// Act names: focus, type, blur, click, select, scroll (fields #a #b #btn #sc of l9.html).
// Route conditions: plain (no routing), route (continue unchanged), override (continue with the header X-Probe: 1);
// undo ends the condition.
type Prober interface {
	Act(name string) (via string, err error)
	Route(cond string) (undo func(), err error)
}

var Acts = []string{"focus", "type", "blur", "click", "select", "scroll"}
var Conds = []string{"plain", "route", "override"}

type Result struct {
	Acts    map[string]string `json:"acts,omitempty"`
	Driver  string            `json:"driver"`
	Methods map[string]int    `json:"methods"`
	Text    *string           `json:"text"`
	Error   *string           `json:"error"`
}

func (r *Result) write(path string, d Driver) {
	r.Methods = d.Methods()
	if r.Methods == nil {
		r.Methods = map[string]int{}
	}
	b, _ := json.Marshal(r)
	if path != "" {
		os.WriteFile(path, b, 0o644)
	}
}

// Run executes the mode and returns the process exit code. --out is written on every exit path.
// Stop = stdin EOF (Windows has no catchable SIGTERM) or SIGINT/SIGTERM: close the browser, write --out, exit.
func Run(name string, d Driver, f *Flags) (code int) {
	r := &Result{Driver: name}
	var once sync.Once
	shutdown := func(errMsg string) {
		once.Do(func() {
			if errMsg != "" && r.Error == nil {
				r.Error = &errMsg
			}
			d.Close()
			r.write(f.Out, d)
		})
	}
	stop := func() {
		msg := ""
		if f.Mode != "probe" { // in probe mode the stop is the normal end
			msg = "interrupted"
		}
		shutdown(msg)
		if msg != "" {
			os.Exit(1)
		}
		os.Exit(0)
	}
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	go func() { <-sig; stop() }()
	go func() { io.Copy(io.Discard, os.Stdin); stop() }()
	defer func() {
		if x := recover(); x != nil {
			shutdown(fmt.Sprint("panic: ", x))
			code = 1
		}
	}()
	if err := run(r, d, f); err != nil {
		s := err.Error()
		fmt.Fprintln(os.Stderr, "error:", err)
		shutdown(s)
		return 1
	}
	shutdown("")
	return 0
}

func run(r *Result, d Driver, f *Flags) error {
	if f.Exe == "" || f.Profile == "" || f.URL == "" {
		return errors.New("--exe, --profile and --url are required")
	}
	if err := d.Launch(f); err != nil {
		return err
	}
	if err := d.Navigate(f.URL); err != nil {
		return err
	}
	switch f.Mode {
	case "l9":
		return runL9(r, d)
	case "headers":
		return runHeaders(r, d, f)
	case "probe":
		t0 := time.Now()
		for _, step := range []func() error{
			func() error { return d.WaitSelector("#ready") },
			func() error { return d.Eval(L3JS) },
			func() error { return d.Type("#t1", ASCII) },
			func() error { return d.Type("#t2", VI) },
			func() error { return d.Click("#go") },
		} {
			if err := step(); err != nil {
				return err
			}
		}
		if el := time.Since(t0); el > ActWindow {
			return fmt.Errorf("acting took %v, over the %v window", el, ActWindow)
		}
		r.write(f.Out, d) // the orchestrator reads this after killing us
		time.Sleep(120 * time.Second)
	case "detector":
		time.Sleep(10 * time.Second)
		if err := d.Eval(RebrowserJS); err != nil {
			return err
		}
		prev, deadline := "\x00", time.Now().Add(120*time.Second)
		for {
			t, err := d.EvalString("() => document.body.innerText")
			if err != nil {
				return err
			}
			if (t != "" && t == prev) || time.Now().After(deadline) {
				r.Text = &t
				break
			}
			prev = t
			time.Sleep(3 * time.Second)
		}
	case "facebook":
		time.Sleep(FacebookWait)
	default:
		return fmt.Errorf("unknown --mode %q", f.Mode)
	}
	return nil
}

func prober(d Driver) (Prober, error) {
	p, ok := d.(Prober)
	if !ok {
		return nil, errors.New("driver is no Prober")
	}
	return p, nil
}

// status of one action or condition: ok:<api used>, n/a:<reason> or error:<text>.
func status(via string, err error) string {
	switch {
	case err == nil:
		return "ok:" + via
	case errors.Is(err, ErrNA):
		return err.Error()
	}
	return "error:" + err.Error()
}

func runL9(r *Result, d Driver) error {
	p, err := prober(d)
	if err != nil {
		return err
	}
	if err := d.WaitSelector("#ready"); err != nil {
		return err
	}
	r.Acts = map[string]string{}
	for _, a := range Acts {
		via, err := p.Act(a)
		r.Acts[a] = status(via, err)
		time.Sleep(400 * time.Millisecond)
	}
	time.Sleep(1500 * time.Millisecond) // the page posts its fires every 400 ms
	return nil
}

func runHeaders(r *Result, d Driver, f *Flags) error {
	p, err := prober(d)
	if err != nil {
		return err
	}
	u, err := url.Parse(f.URL)
	if err != nil {
		return err
	}
	r.Acts = map[string]string{}
	for _, c := range Conds {
		undo, err := p.Route(c)
		r.Acts[c] = status("route", err)
		if err != nil {
			continue
		}
		u.RawQuery = "c=" + c
		err = d.Navigate(u.String())
		time.Sleep(3500 * time.Millisecond) // the page fetches 1.5 s after load
		undo()
		if err != nil {
			return err
		}
	}
	return nil
}

// OrderedHeaders reads a request's header object (as CDP gives it) in the order Chrome wrote it; a Go map would lose it.
func OrderedHeaders(raw []byte) ([][2]string, error) {
	dec := json.NewDecoder(bytes.NewReader(raw))
	if _, err := dec.Token(); err != nil {
		return nil, err
	}
	var out [][2]string
	for dec.More() {
		k, err := dec.Token()
		if err != nil {
			return nil, err
		}
		var v string
		if err := dec.Decode(&v); err != nil {
			return nil, err
		}
		out = append(out, [2]string{k.(string), v})
	}
	return out, nil
}
