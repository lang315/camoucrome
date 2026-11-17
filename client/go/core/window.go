package core

import (
	"fmt"
	"math"
)

// minWindow is gen.py MIN_WINDOW: a person's window is never narrower or shorter than this.
var minWindow = [2]int{800, 500}

// threadSteps is gen.py THREAD_STEPS.
var threadSteps = []int{2, 4, 6, 8, 12, 16, 20}

// snapCores is the cores step of gen.py from_pool: a claim above the host's
// snaps to the largest threadSteps value within it (the cores themselves below 2).
func snapCores(claim, cores int) int {
	if cores <= 0 || claim <= cores {
		return claim
	}
	best := cores
	for _, t := range threadSteps {
		if t <= cores {
			best = t
		}
	}
	return best
}

// holdsMinWindow is gen.py holds_min_window.
func holdsMinWindow(area [2]int, dpr float64) bool {
	return float64(area[0])/dpr >= float64(minWindow[0]) && float64(area[1])/dpr >= float64(minWindow[1])
}

// snapWindow is gen.py snap_window along one axis: (launch size, outer the
// browser then reports). The offsets and residues are measured per DPR
// (client/python/camoucrome/gen.py, WINDOW_OFFSET and WINDOW_SAFE).
func snapWindow(dpr float64, outer int) (int, int, error) {
	var off, mod int
	var ok []int
	switch dpr {
	case 1, 2, 2.5, 3:
		off, mod, ok = 0, 1, []int{0}
	case 1.25:
		off, mod, ok = 2, 4, []int{0, 1}
	case 1.5:
		off, mod, ok = 0, 2, []int{0}
	case 1.75:
		off, mod, ok = 2, 4, []int{0, 1, 3}
	default:
		return 0, 0, fmt.Errorf("device pixel ratio %g has no measured window offset", dpr)
	}
	length := outer - off
	for length > 0 {
		in := false
		for _, r := range ok {
			if length%mod == r {
				in = true
			}
		}
		if in {
			return length, length + off, nil
		}
		length--
	}
	return 0, 0, fmt.Errorf("window %d is too small to snap at device pixel ratio %g", outer, dpr)
}

// rng is a PCG stream with its own bounded draw. math/rand/v2 documents the
// PCG output sequence as fixed but not its derived methods (IntN), and a
// stored identity must resolve the same in every release.
type rng struct{ s pcg }

func newRng(seed uint64, stream uint64) *rng { return &rng{newPCG(seed, stream)} }

// intn is uniform enough in [0, n); n > 0.
func (r *rng) intn(n int) int { return int(r.s.Uint64() % uint64(n)) }

// randint is Python's randint(lo, hi), inclusive.
func (r *rng) randint(lo, hi int) int { return lo + r.intn(hi-lo+1) }

// windowPosition is gen.py window_position: how far a person dragged the
// window off the work-area corner, each axis 0..120 px, never so far that the
// window falls under minWindow.
func windowPosition(r *rng, avail, outer [2]int) [2]int {
	var d [2]int
	for i := 0; i < 2; i++ {
		lim := min(120, min(avail[i], outer[i])-minWindow[i])
		d[i] = r.randint(0, max(0, lim))
	}
	return d
}

// fitWindow is gen.py fit_window: pos and outer with the window inside the
// host's work area as well as the claimed one, on each axis.
func fitWindow(r *rng, work [2]int, dpr float64, avail, origin, pos, outer [2]int) ([2]int, [2]int) {
	var capv [2]int
	for i := 0; i < 2; i++ {
		capv[i] = min(avail[i], int(math.Floor(float64(work[i])/dpr)))
		if outer[i] > capv[i] {
			lo := max(minWindow[i], int(math.RoundToEven(0.6*float64(capv[i]))))
			outer[i] = r.randint(min(lo, capv[i]), capv[i])
		}
	}
	var bad []int
	for i := 0; i < 2; i++ {
		if pos[i]+outer[i] > origin[i]+capv[i] {
			bad = append(bad, i)
		}
	}
	if len(bad) > 0 {
		d := windowPosition(r, capv, outer)
		for _, i := range bad {
			pos[i] = origin[i] + d[i]
			outer[i] = min(outer[i], capv[i]-d[i])
		}
	}
	return pos, outer
}
