package camoucrome

import (
	"errors"
	"reflect"
	"strings"
	"testing"

	"github.com/mxschmitt/playwright-go"
)

func TestDriverQueryScriptDoesNotMatchItself(t *testing.T) {
	s := driverQueryScript(77)
	if strings.Contains(s, "run-driver") {
		t.Fatal("the literal would match the query's own command line")
	}
	if !strings.Contains(s, "$PID") || !strings.Contains(s, "ParentProcessId=77") {
		t.Fatalf("script %q", s)
	}
}

func TestCPUListsAreNotLimitedTo64(t *testing.T) {
	got, err := cpusFromList("0-1,8,70-71")
	if err != nil || !reflect.DeepEqual(got, []int{0, 1, 8, 70, 71}) {
		t.Fatalf("%v %v", got, err)
	}
	if cpuList([]int{70, 0, 8}) != "0,8,70" {
		t.Fatal(cpuList([]int{70, 0, 8}))
	}
	if _, err := cpusFromList("x"); err == nil {
		t.Fatal("garbage accepted")
	}
}

func TestRestoreFailureAfterAGoodLaunchClosesTheBrowser(t *testing.T) {
	var p pinFakes
	p.install(t, eight, 4242)
	inner := affinitySet
	affinitySet = func(pid int, cpus []int) error {
		if len(p.log) == 1 { // the restore
			return errors.New("restore denied")
		}
		return inner(pid, cpus)
	}
	c := &closeCounter{}
	_, err := launch(&duringLauncher{ctx: c}, pinCfg(2.0))
	if err == nil || !strings.Contains(err.Error(), "restore") {
		t.Fatalf("err %v", err)
	}
	if c.closed != 1 {
		t.Fatalf("closed %d times", c.closed)
	}
}

func TestPartialPinIsRolledBack(t *testing.T) {
	var p pinFakes
	p.install(t, eight, 4242)
	inner := affinitySet
	n := 0
	affinitySet = func(pid int, cpus []int) error {
		n++
		if n == 1 {
			inner(pid, cpus)
			return errors.New("half")
		}
		return inner(pid, cpus)
	}
	if _, err := launch(&duringLauncher{}, pinCfg(2.0)); err == nil {
		t.Fatal("no error")
	}
	if !reflect.DeepEqual(p.mask, eight) {
		t.Fatalf("mask %v", p.mask)
	}
}

type closeCounter struct {
	noEvents
	closed int
}

func (c *closeCounter) Close(...playwright.BrowserContextCloseOptions) error {
	c.closed++
	return nil
}
