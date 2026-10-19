// client/go/human_math.go -- SP2d reference math, a port of
// client/python/camoucrome/human_math.py; settings/human_click_vectors.json pins both.
package camoucrome

import (
	"math"

	"github.com/mxschmitt/playwright-go"
)

var clickSalt = map[string]uint64{"hold": 0x686F6C64, "dwell": 0x6477656C6C, "offset": 0x6F6666736574}

type geometry struct {
	X        float64 `json:"x"`
	Y        float64 `json:"y"`
	W        float64 `json:"w"`
	H        float64 `json:"h"`
	N        int     `json:"n"`
	BL       float64 `json:"bl"`
	BT       float64 `json:"bt"`
	T        bool    `json:"t"`
	VW       float64 `json:"vw"`
	VH       float64 `json:"vh"`
	Scroller string  `json:"scroller"`
}

type axisModel struct {
	A float64 `json:"a"`
	B float64 `json:"b"`
}

type offsetModel struct {
	Along  axisModel `json:"along"`
	Across axisModel `json:"across"`
}

func splitmix64(x uint64) uint64 {
	z := x + 0x9E3779B97F4A7C15
	z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9
	z = (z ^ (z >> 27)) * 0x94D049BB133111EB
	return z ^ (z >> 31)
}

func profileScale(seed *uint32, salt string) float64 {
	if seed == nil {
		return 1
	}
	u := float64(splitmix64(uint64(*seed)^clickSalt[salt])>>11) * 0x1p-53
	return math.Exp(math.Log(1.25) * (2*u - 1))
}

func sampleKnots(k [21]float64, u float64) float64 {
	pos := math.Min(math.Max(u, 0), 1) * 20
	i := int(math.Min(math.Floor(pos), 19))
	return k[i] + (pos-float64(i))*(k[i+1]-k[i])
}

func normalPair(r func() float64) (float64, float64) {
	u1, u2 := r(), r()
	rad := math.Sqrt(-2 * math.Log(1-u1))
	return rad * math.Cos(2*math.Pi*u2), rad * math.Sin(2*math.Pi*u2)
}

func clickPosition(g geometry, last *[2]float64, m offsetModel, scale float64, r func() float64) *playwright.Position {
	if g.W < clickMinSidePx || g.H < clickMinSidePx || g.T || g.N != 1 {
		return nil
	}
	cx, cy := g.X+g.W/2, g.Y+g.H/2
	ax, ay := 1.0, 0.0
	if last != nil {
		dx, dy := cx-last[0], cy-last[1]
		if d := math.Hypot(dx, dy); d >= 1 {
			ax, ay = dx/d, dy/d
		}
	}
	wAlong := math.Abs(ax)*g.W + math.Abs(ay)*g.H
	wAcross := math.Abs(ay)*g.W + math.Abs(ax)*g.H
	sdAlong := (m.Along.A + m.Along.B*wAlong) * scale
	sdAcross := (m.Across.A + m.Across.B*wAcross) * scale
	for range clickMaxRedraws {
		z1, z2 := normalPair(r)
		px := cx + ax*z1*sdAlong - ay*z2*sdAcross
		py := cy + ay*z1*sdAlong + ax*z2*sdAcross
		if math.Abs(px-cx) <= clickInnerFraction*g.W/2 && math.Abs(py-cy) <= clickInnerFraction*g.H/2 {
			return &playwright.Position{X: px - g.X - g.BL, Y: py - g.Y - g.BT}
		}
	}
	return nil
}

func visible(g geometry) bool {
	if g.H > g.VH {
		return g.Y >= 0 && g.Y < g.VH
	}
	return g.Y >= 0 && g.Y+g.H <= g.VH
}

func roundAway(x float64) float64 { return math.Copysign(math.Floor(math.Abs(x)+0.5), x) }

func nextBurst(g geometry, landing float64, burst, pause [21]float64, r func() float64, maxNotches int) (int, float64, bool) {
	goal := math.Min(landing*g.VH, math.Max(0, g.VH-g.H))
	delta := g.Y - goal
	if visible(g) && math.Abs(delta) < 100 {
		return 0, 0, false
	}
	total := int(math.Max(-float64(maxNotches), math.Min(float64(maxNotches), roundAway(delta/100))))
	if total == 0 {
		total = -1
		if delta > 0 {
			total = 1
		}
	}
	size := int(math.Max(1, math.Floor(sampleKnots(burst, r())+0.5)))
	if abs := int(math.Abs(float64(total))); size > abs {
		size = abs
	}
	if total < 0 {
		size = -size
	}
	return size, sampleKnots(pause, r()), true
}
