package camoucrome

import (
	"errors"
	"fmt"
	"reflect"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/mxschmitt/playwright-go"
)

// pinFakes replaces the OS calls: this Mac has no affinity API, so no real pin is read back here.
type pinFakes struct {
	mask []int
	log  []string // "pid:cpus"
	fail error
}

func (p *pinFakes) install(t *testing.T, allowed []int, pids ...int) {
	p.mask = append([]int(nil), allowed...)
	oldGet, oldSet, oldPIDs := affinityGet, affinitySet, driverPIDs
	t.Cleanup(func() { affinityGet, affinitySet, driverPIDs = oldGet, oldSet, oldPIDs })
	affinityGet = func(pid int) ([]int, error) { return append([]int(nil), p.mask...), nil }
	affinitySet = func(pid int, cpus []int) error {
		if p.fail != nil {
			return p.fail
		}
		c := append([]int(nil), cpus...)
		sort.Ints(c)
		p.log = append(p.log, fmt.Sprintf("%d:%v", pid, c))
		p.mask = c
		return nil
	}
	driverPIDs = func() ([]int, error) { return pids, nil }
}

func pinCfg(n any) Options {
	if n == nil {
		return Options{ExecutablePath: "/x/chrome", Config: map[string]any{}}
	}
	return Options{ExecutablePath: "/x/chrome", Config: map[string]any{"navigator.hardwareConcurrency": n}}
}

var eight = []int{0, 1, 2, 3, 4, 5, 6, 7}

func TestPinsTheDriverToNAllowedCPUsThenRestores(t *testing.T) {
	var p pinFakes
	p.install(t, eight, 4242)
	var during []int
	f := &duringLauncher{onLaunch: func() { during = append([]int(nil), p.mask...) }}
	if _, err := launch(f, pinCfg(4)); err != nil {
		t.Fatal(err)
	}
	if len(during) != 4 {
		t.Fatalf("mask during the launch has %d CPUs, want 4: %v", len(during), during)
	}
	want := []string{fmt.Sprintf("4242:%v", during), fmt.Sprintf("4242:%v", eight)}
	if !reflect.DeepEqual(p.log, want) {
		t.Fatalf("calls %v, want %v", p.log, want)
	}
}

func TestNoPinWhenTheClaimReachesTheAllowedCPUsOrPinningIsOff(t *testing.T) {
	no := false
	for name, o := range map[string]Options{"equal": pinCfg(8.0), "above": pinCfg(12.0), "none": pinCfg(nil)} {
		var p pinFakes
		p.install(t, eight, 4242)
		if _, err := launch(&duringLauncher{}, o); err != nil || len(p.log) != 0 {
			t.Errorf("%s: err %v calls %v", name, err, p.log)
		}
	}
	var p pinFakes
	p.install(t, eight, 4242)
	o := pinCfg(2.0)
	o.PinCPUCores = &no
	if _, err := launch(&duringLauncher{}, o); err != nil || len(p.log) != 0 {
		t.Errorf("disabled: err %v calls %v", err, p.log)
	}
}

func TestMaskRestoredWhenTheLaunchFails(t *testing.T) {
	var p pinFakes
	p.install(t, eight, 4242)
	_, err := launch(&duringLauncher{err: errors.New("no chrome")}, pinCfg(2.0))
	if err == nil || !strings.Contains(err.Error(), "no chrome") {
		t.Fatalf("err %v", err)
	}
	if len(p.log) != 2 || p.log[1] != fmt.Sprintf("4242:%v", eight) {
		t.Fatalf("calls %v", p.log)
	}
}

func TestPinFailureErrorsWithPidAndCauseAndDoesNotLaunch(t *testing.T) {
	var p pinFakes
	p.install(t, eight, 4242)
	p.fail = errors.New("EPERM nope")
	f := &duringLauncher{}
	_, err := launch(f, pinCfg(2.0))
	if err == nil || !strings.Contains(err.Error(), "4242") || !strings.Contains(err.Error(), "EPERM nope") {
		t.Fatalf("err %v", err)
	}
	if f.launched {
		t.Fatal("launched despite the failed pin")
	}
}

func TestNoDriverFoundIsAnError(t *testing.T) {
	var p pinFakes
	p.install(t, eight)
	if _, err := launch(&duringLauncher{}, pinCfg(2.0)); err == nil || !strings.Contains(err.Error(), "driver") {
		t.Fatalf("err %v", err)
	}
}

func TestOverlappingLaunchesAreSerialised(t *testing.T) {
	var p pinFakes
	p.install(t, eight, 4242)
	var mu sync.Mutex
	var order []string
	slow := func(name string) *duringLauncher {
		return &duringLauncher{onLaunch: func() {
			mu.Lock()
			order = append(order, "start "+name)
			mu.Unlock()
			time.Sleep(20 * time.Millisecond)
			mu.Lock()
			order = append(order, "end "+name)
			mu.Unlock()
		}}
	}
	var wg sync.WaitGroup
	for _, n := range []string{"a", "b"} {
		wg.Add(1)
		go func() { defer wg.Done(); launch(slow(n), pinCfg(2.0)) }()
	}
	wg.Wait()
	if order[0][6:] != order[1][4:] || order[2][6:] != order[3][4:] {
		t.Fatalf("launches overlapped: %v", order)
	}
	if !reflect.DeepEqual(p.mask, eight) {
		t.Fatalf("final mask %v", p.mask)
	}
}

// duringLauncher is a persistentLauncher that runs a hook inside the launch call.
type duringLauncher struct {
	onLaunch func()
	err      error
	ctx      playwright.BrowserContext
	launched bool
}

func (d *duringLauncher) LaunchPersistentContext(string, ...playwright.BrowserTypeLaunchPersistentContextOptions) (playwright.BrowserContext, error) {
	d.launched = true
	if d.onLaunch != nil {
		d.onLaunch()
	}
	if d.err != nil {
		return nil, d.err
	}
	if d.ctx != nil {
		return d.ctx, nil
	}
	return noEvents{}, nil
}

// noEvents is a BrowserContext that accepts OnClose and nothing else.
type noEvents struct{ playwright.BrowserContext }

func (noEvents) OnClose(func(playwright.BrowserContext)) {}
