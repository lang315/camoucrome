package core

import (
	"errors"
	"slices"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// fakeMask swaps the OS calls for a recorder over 4 allowed CPUs.
func fakeMask(t *testing.T, allowed []int) (sets *[][]int) {
	t.Helper()
	og, os := affinityGet, affinitySet
	t.Cleanup(func() { affinityGet, affinitySet = og, os })
	var rec [][]int
	affinityGet = func() ([]int, error) { return allowed, nil }
	affinitySet = func(c []int) error { rec = append(rec, slices.Clone(c)); return nil }
	return &rec
}

func TestPinnedNoop(t *testing.T) {
	sets := fakeMask(t, []int{0, 1, 2, 3})
	for _, cores := range []int{4, 8, 0} {
		calls := 0
		if err := Pinned(cores, func() error { calls++; return nil }); err != nil || calls != 1 {
			t.Fatalf("cores %d: calls %d err %v", cores, calls, err)
		}
	}
	if len(*sets) != 0 {
		t.Errorf("a mask was set: %v", *sets)
	}
	affinityGet = func() ([]int, error) { return nil, nil } // no affinity API (macOS)
	if err := Pinned(1, func() error { return nil }); err != nil || len(*sets) != 0 {
		t.Errorf("no-API host: %v %v", err, *sets)
	}
}

func TestPinnedSetsAndRestores(t *testing.T) {
	sets := fakeMask(t, []int{0, 1, 2, 3})
	boom := errors.New("start failed")
	err := Pinned(2, func() error {
		if len(*sets) != 1 || len((*sets)[0]) != 2 {
			t.Errorf("during start: %v", *sets)
		}
		return boom
	})
	if !errors.Is(err, boom) {
		t.Fatalf("start's error lost: %v", err)
	}
	if len(*sets) != 2 || !slices.Equal((*sets)[1], []int{0, 1, 2, 3}) {
		t.Errorf("not restored after a failed start: %v", *sets)
	}
	for _, c := range (*sets)[0] {
		if c < 0 || c > 3 {
			t.Errorf("picked CPU %d outside the allowed set", c)
		}
	}
}

func TestPinnedRestoreFailureIsAnError(t *testing.T) {
	fakeMask(t, []int{0, 1, 2, 3})
	n := 0
	affinitySet = func([]int) error {
		if n++; n == 2 {
			return errors.New("denied")
		}
		return nil
	}
	if err := Pinned(1, func() error { return nil }); err == nil {
		t.Error("a mask that was not restored went unreported")
	}
}

func TestPinnedSerialises(t *testing.T) {
	fakeMask(t, []int{0, 1, 2, 3})
	var in, maxIn atomic.Int32
	var wg sync.WaitGroup
	for i := 0; i < 2; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			Pinned(2, func() error {
				n := in.Add(1)
				for {
					m := maxIn.Load()
					if n <= m || maxIn.CompareAndSwap(m, n) {
						break
					}
				}
				time.Sleep(30 * time.Millisecond)
				in.Add(-1)
				return nil
			})
		}()
	}
	wg.Wait()
	if maxIn.Load() != 1 {
		t.Errorf("%d Pinned calls overlapped", maxIn.Load())
	}
}

func TestPlatformVersion(t *testing.T) {
	for _, c := range []struct {
		dword uint32
		want  string
	}{{0x000F0000, "15.0.0"}, {0x00130001, "19.1.0"}, {0x000D0000, "13.0.0"}, {0x00070000, "7.0.0"}} {
		if got := contractVersion(c.dword); got != c.want {
			t.Errorf("%#x: %s, want %s", c.dword, got, c.want)
		}
	}
	for build, want := range map[int]string{10240: "1.0.0", 10586: "2.0.0", 14393: "3.0.0", 15063: "4.0.0", 16299: "5.0.0", 17134: "6.0.0"} {
		if got, ok := preRS5Contract(build); !ok || got != want {
			t.Errorf("build %d: %s %v, want %s", build, got, ok, want)
		}
	}
	if _, ok := preRS5Contract(17135); ok {
		t.Error("RS5 uses the registry")
	}
	if got := platformVersion(22631, 0, false); got != "19.0.0" {
		t.Errorf("no contract: %s", got)
	}
	if got := platformVersion(22631, 0x000F0000, true); got != "15.0.0" {
		t.Errorf("contract: %s", got)
	}
}

func TestProbeHostCores(t *testing.T) {
	fakeMask(t, []int{0, 1, 2})
	if h, _ := ProbeHost(); h.Cores != 3 {
		t.Errorf("Cores %d, want 3", h.Cores)
	}
}
