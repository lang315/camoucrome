// corecheck draws identities with client/go/core, resolves each for four proxy
// exits and starts the fork under CAMOU_CONFIG_STRICT=1 through rodclient, then
// reads back what a page sees: the time zone, the languages, the core count and
// the WebRTC candidates. One PASS/FAIL line per case; exit 1 on any FAIL or when
// the case count is not n*4. A startup abort under strict is a FAIL naming the error.
//
//	go run ./cmd/camoucrome-corecheck -exe ~/l7-dist/chrome -n 10
//
// -red tz and -red rtc make the check fail on purpose (RED-first): a wrong
// expected zone, and a config with webrtc:ipHandlingPolicy removed.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
	"time"

	camoucrome "github.com/lang315/camoucrome/client/go"
	"github.com/lang315/camoucrome/client/go/core"
	"github.com/lang315/camoucrome/client/go/rodclient"
)

// A fixed screen and OS version stand in for what the Windows probe reads: the
// box is Linux, and this check is about the exit-dependent keys.
var host = core.Host{WorkArea: [2]int{1920, 1040}, PlatformVersion: "10.0.0", Display: &core.Display{Gamut: "srgb", ColorBits: 8}}

var exits = []core.Exit{{Timezone: "America/New_York", Country: "US"}, {Timezone: "Asia/Bangkok", Country: "TH"},
	{Timezone: "Europe/Berlin", Country: "DE"}, {Timezone: "Africa/Nairobi", Country: "ZZ"}} // ZZ: unknown country, en-US

const probeJS = `(async () => {
  const pc = new RTCPeerConnection({iceServers: [{urls: 'stun:stun.l.google.com:19302'}]});
  const cands = [];
  pc.onicecandidate = e => { if (e.candidate) cands.push(e.candidate.candidate); };
  const done = new Promise(r => { const t = setTimeout(r, 4000);
    pc.onicegatheringstatechange = () => { if (pc.iceGatheringState === 'complete') { clearTimeout(t); r(); } }; });
  pc.createDataChannel('x');
  await pc.setLocalDescription(await pc.createOffer());
  await done; pc.close();
  return JSON.stringify({tz: Intl.DateTimeFormat().resolvedOptions().timeZone, lang: navigator.language,
    langs: navigator.languages, cores: navigator.hardwareConcurrency, cands});
})()`

type observed struct {
	TZ    string   `json:"tz"`
	Lang  string   `json:"lang"`
	Langs []string `json:"langs"`
	Cores int      `json:"cores"`
	Cands []string `json:"cands"`
}

type expected struct {
	TZ    string
	Lang  string
	Langs []string
	Cores int
}

var (
	rawV4 = regexp.MustCompile(`\b\d{1,3}(\.\d{1,3}){3}\b`)
	rawV6 = regexp.MustCompile(`\s([0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F:]*\s`)
)

// judge lists what a page saw that differs from what was resolved. Candidates:
// no srflx, no raw address, and, because the policy is disable_non_proxied_udp
// and this check sets no proxy, none at all: a candidate means the policy is
// not in force.
func judge(w expected, o observed) []string {
	var bad []string
	if o.TZ != w.TZ {
		bad = append(bad, fmt.Sprintf("timeZone %q, want %q", o.TZ, w.TZ))
	}
	if o.Lang != w.Lang || !slices.Equal(o.Langs, w.Langs) {
		bad = append(bad, fmt.Sprintf("language %q %v, want %q %v", o.Lang, o.Langs, w.Lang, w.Langs))
	}
	if o.Cores != w.Cores {
		bad = append(bad, fmt.Sprintf("hardwareConcurrency %d, want %d", o.Cores, w.Cores))
	}
	for _, c := range o.Cands {
		switch {
		case strings.Contains(c, "typ srflx"):
			bad = append(bad, "server-reflexive ICE candidate: "+c)
		case rawV4.MatchString(c) || rawV6.MatchString(c+" "):
			bad = append(bad, "raw address in an ICE candidate: "+c)
		default:
			bad = append(bad, "an ICE candidate with no proxy (disable_non_proxied_udp is not in force): "+c)
		}
	}
	return bad
}

func runCase(ctx context.Context, exe, fonts string, strict bool, red string, id core.Identity, ex core.Exit) (bad []string, err error) {
	r, err := core.Resolve(id, host, &ex)
	if err != nil {
		return nil, err
	}
	if red == "rtc" {
		delete(r.Config, "webrtc:ipHandlingPolicy")
	}
	h := true
	o := camoucrome.Options{ExecutablePath: exe, Config: r.Config, Strict: strict, Window: r.Window, DPR: r.DPR,
		Position: &r.Position, Headless: &h, FontsDir: fonts, ExtraArgs: append([]string{"--no-sandbox"}, r.Args...)}
	b, err := rodclient.Launch(ctx, o)
	if err != nil {
		return nil, err
	}
	defer b.Close()
	p, err := b.NewPage(ctx)
	if err != nil {
		return nil, err
	}
	if err := p.Goto(ctx, "about:blank", rodclient.WaitLoad); err != nil {
		return nil, err
	}
	out, err := p.Eval(ctx, probeJS)
	if err != nil {
		return nil, err
	}
	var ob observed
	if err := json.Unmarshal([]byte(out), &ob); err != nil {
		return nil, fmt.Errorf("probe result %q: %w", out, err)
	}
	w := expected{TZ: ex.Timezone, Lang: r.Config["navigator.language"].(string), Cores: r.Cores}
	for _, l := range r.Config["navigator.languages"].([]any) {
		w.Langs = append(w.Langs, l.(string))
	}
	if red == "tz" {
		w.TZ = "Pacific/Auckland"
	}
	return judge(w, ob), nil
}

func main() {
	exe := flag.String("exe", "", "browser binary")
	n := flag.Int("n", 10, "identities (each runs against 4 exits)")
	strict := flag.Bool("strict", true, "CAMOU_CONFIG_STRICT=1")
	red := flag.String("red", "", "tz or rtc: fail on purpose")
	flag.Parse()
	if *exe == "" {
		fmt.Fprintln(os.Stderr, "need -exe")
		os.Exit(2)
	}
	fonts := filepath.Join(filepath.Dir(*exe), "fonts")
	h, _ := core.ProbeHost()
	host.Cores = h.Cores
	total, pass := 0, 0
	for i := 1; i <= *n; i++ {
		seed := uint64(i)
		id, err := core.Draw("windows", &seed, &host)
		if err != nil {
			fmt.Printf("FAIL seed=%d draw: %v\n", i, err)
			total += len(exits)
			continue
		}
		for _, ex := range exits {
			ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
			bad, err := runCase(ctx, *exe, fonts, *strict, *red, id, ex)
			cancel()
			total++
			if err != nil {
				bad = append(bad, "error: "+err.Error())
			}
			if len(bad) == 0 {
				pass++
				fmt.Printf("PASS seed=%d exit=%s/%s\n", i, ex.Country, ex.Timezone)
			} else {
				fmt.Printf("FAIL seed=%d exit=%s/%s: %s\n", i, ex.Country, ex.Timezone, strings.Join(bad, "; "))
			}
		}
	}
	fmt.Printf("%d/%d PASS\n", pass, total)
	if pass != total || total != *n*len(exits) {
		os.Exit(1)
	}
}
