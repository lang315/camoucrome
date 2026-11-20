// Package workload is the one workload both drivers run, and the CLI they share.
package workload

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
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
	MainWorld                                       bool
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
	flag.Parse()
	return f
}

// Args reads --args-json (empty if unset).
func (f *Flags) Args() ([]string, error) {
	var a []string
	return a, readJSON(f.ArgsJSON, &a)
}

// Env is the process env with --env-json merged over it.
func (f *Flags) Env() ([]string, error) {
	var m map[string]string
	if err := readJSON(f.EnvJSON, &m); err != nil {
		return nil, err
	}
	env := os.Environ()
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

type Result struct {
	Driver  string         `json:"driver"`
	Methods map[string]int `json:"methods"`
	Text    *string        `json:"text"`
	Error   *string        `json:"error"`
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
