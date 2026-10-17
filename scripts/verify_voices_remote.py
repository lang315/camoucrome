"""Verifies S5: Chrome's Google network voices on a Windows identity. The list follows
stock (R1); speak() on a remote voice has stock 154's shape, as measured on the Windows host
in session 1 (docs/superpowers/measurements/2026-10-s5-remote-voices.md section 2): no boundary,
a delayed start, the measured end or cut-off (R2-R6);
a local voice keeps its per-word boundaries (R8, control). EXPECTED rows, not exit 0, decide.

S5_ROOT=<a checkout> reads that checkout's generator and data instead (the R1 RED on main)."""
import json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell
from verify_voices_ii import predicted_jitter  # the voices-ii FNV jitter, one Python copy
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.environ.get("S5_ROOT") or ROOT
sys.path.insert(0, os.path.join(ROOT, "client", "python"))
from camoucrome import gen  # noqa: E402

EXPECTED = 11
START_P10_MS, START_P90_MS = 218, 392     # section 2, Google US English, 43 chars
REMOTE_CPS = 16.05                        # section 2, 200 chars at rate 1
# section 4: stock 154's remote duration at a rate, relative to rate 1 (43 chars, deterministic to 0.2 %);
# above rate 2 a remote voice never starts. Interpolated log-log, as speech_synthesis.cc does.
RATE_CURVE = [(0.1, 3.037), (0.25, 2.512), (0.5, 1.823), (0.75, 1.338), (1.0, 1.0), (1.5, 0.582), (2.0, 0.372)]
CFG = json.dumps(gen.voices_keys("Windows", "en-US"))
BASE = json.load(open(os.path.join(ROOT, "baselines", "chrome-8078-stock-oracle-windows.json"), encoding="utf-8"))["headed"]["voices"]

# Same text and cell shape as scripts/measure_remote_voices.py: cancel/pause are timed from the
# 'start' event, and every timer a cell sets is cleared when it ends.
PROBE = r"""(async () => {
  await new Promise(r => setTimeout(r, 300));
  const v = speechSynthesis.getVoices();
  const TXT = n => 'The quick brown fox jumps over the lazy dog. '.repeat(20).slice(0, n);
  const say = (voice, n, act, rate = 1) => new Promise(res => {
    const ev = [], u = new SpeechSynthesisUtterance(TXT(n)), s = performance.now(), at = () => Math.round(performance.now() - s);
    const timers = [], later = (f, ms) => timers.push(setTimeout(f, ms));
    u.voice = voice; u.lang = voice.lang; u.volume = 0; u.rate = rate;
    for (const k of ['start','end','error','boundary','pause','resume']) u.addEventListener(k, e => ev.push([k, at(), e.error || '']));
    let done = false; const fin = () => { if (!done) { done = true; timers.forEach(clearTimeout); setTimeout(() => res(ev.slice()), 80); } };
    u.addEventListener('end', fin); u.addEventListener('error', fin);
    if (act === 'cancel5s') later(() => speechSynthesis.cancel(), 5000);  // a speak that never starts
    u.addEventListener('start', () => {
      if (act === 'cancel') later(() => speechSynthesis.cancel(), 1000);
      if (act === 'pause') later(() => { speechSynthesis.pause(); ev.push(['pausedflag', at(), String(speechSynthesis.paused)]);
        later(() => { ev.push(['pausedflag', at(), String(speechSynthesis.paused)]); speechSynthesis.resume(); }, 1000); }, 1000);
    }, {once: true});
    speechSynthesis.speak(u);
    later(() => { ev.push(['timeout', at(), '']); speechSynthesis.cancel(); fin(); }, 60000);
  });
  const g = v.find(x => x.name === 'Google US English'), l = v.find(x => x.localService);
  return {list: v.map(x => [x.name, x.lang, x.localService, x.default]),
          g43: g && await say(g, 43), g43r2: g && await say(g, 43, '', 2), g43h: g && await say(g, 43, '', 0.5),
          g43r3: g && await say(g, 43, 'cancel5s', 3),
          rep: g && [await say(g, 43), await say(g, 43), await say(g, 43), await say(g, 43)], g540: g && await say(g, 540), gcancel: g && await say(g, 200, 'cancel'),
          gpause: g && await say(g, 200, 'pause'), l43: l && await say(l, 43)};
})()"""



TXT = lambda n: ("The quick brown fox jumps over the lazy dog. " * 20)[:n]  # the probe's TXT()


def rate_factor(rate):
    rate = min(max(rate, RATE_CURVE[0][0]), RATE_CURVE[-1][0])
    for (r0, f0), (r1, f1) in zip(RATE_CURVE, RATE_CURVE[1:]):
        if rate <= r1:
            w = (math.log(rate) - math.log(r0)) / (math.log(r1) - math.log(r0))
            return math.exp(math.log(f0) + w * (math.log(f1) - math.log(f0)))


def predicted_ms(n, rate=1.0, uri="Google US English"):
    """end - start the remote branch must give: chars / cps x rate_factor(rate) x (1 + jitter), where jitter is
    the voices-ii FNV-1a-64 of (text, voiceURI) UTF-8 mapped to +/-0.15 (mirrors speech_synthesis.cc)."""
    return n / REMOTE_CPS * rate_factor(rate) * (1.0 + predicted_jitter(TXT(n), uri)) * 1000.0


def dur(ev): return (first(ev, "end") or 0) - (first(ev, "start") or 0)
def kinds(ev, k): return [e for e in (ev or []) if e[0] == k]
def first(ev, k): return next((e[1] for e in (ev or []) if e[0] == k), None)


def main():
    v, err = lib_shell.session(CFG, [PROBE], navigate_to="about:blank")
    r = v[0] if v else {}
    if err:
        print("session error:", err)
    lst = r.get("list") or []
    remote_base = [[b[0], b[1], False, False] for b in BASE if not b[2]]
    print(f"note: list {len(lst)} voices")
    res = {}
    res["R1 list: local row, then the 19 Google voices byte-exact"] = len(lst) == 22 and lst[3:] == remote_base and all(x[2] for x in lst[:3])
    g43 = r.get("g43")
    print("note: g43", g43 and [e for e in g43 if e[0] != "boundary"], "boundaries", len(kinds(g43, "boundary")))
    res["R2 remote speak: 0 boundary events, then end"] = g43 is not None and not kinds(g43, "boundary") and first(g43, "end") is not None
    s = first(g43, "start")
    res[f"R3 remote start in [{START_P10_MS - 50}, {START_P90_MS + 150}] ms"] = s is not None and START_P10_MS - 50 <= s <= START_P90_MS + 150
    d43, want43 = dur(g43), predicted_ms(43)
    print(f"note: g43 end-start {d43} predicted {want43:.0f}")
    res["R4a remote 43 chars: end-start = 43/16.05 cps x (1+jitter), within 120 ms"] = s is not None and abs(d43 - want43) <= 120
    g43r2 = r.get("g43r2")
    d43r2 = dur(g43r2)
    want43r2 = predicted_ms(43, 2.0)
    g43h = r.get("g43h")
    d43h, want43h = dur(g43h), predicted_ms(43, 0.5)
    print(f"note: rate 2 end-start {d43r2} predicted {want43r2:.0f}; rate 0.5 {d43h} predicted {want43h:.0f}")
    res["R4c remote 43 chars at rates 2 and 0.5: end-start = predicted x the measured rate curve, within 120 ms"] = (
        first(g43r2, "start") is not None and abs(d43r2 - want43r2) <= 120 and not kinds(g43r2, "boundary")
        and first(g43h, "start") is not None and abs(d43h - want43h) <= 120)
    g43r3 = r.get("g43r3")
    print("note: rate 3", g43r3)
    res["R9 remote at rate 3: never starts (no start/boundary/end for 5 s), then cancel -> interrupted"] = (
        g43r3 is not None and first(g43r3, "start") is None and not kinds(g43r3, "boundary") and first(g43r3, "end") is None
        and [e[2] for e in kinds(g43r3, "error")] == ["interrupted"])
    reps = [first(ev, "start") for ev in (r.get("rep") or [])]
    print("note: repeated starts", reps)
    res["R10 the same text spoken 4 times: starts differ (spread > 15 ms), each in the measured band"] = (
        len(reps) == 4 and None not in reps and max(reps) - min(reps) > 15
        and all(START_P10_MS - 50 <= x <= START_P90_MS + 150 for x in reps))
    g540 = r.get("g540")
    print("note: g540", g540 and [e for e in g540 if e[0] != "boundary"])
    d540, want540 = dur(g540), predicted_ms(540)  # section 2: stock never cut a long speak (0/9)
    print(f"note: g540 end-start {d540} predicted {want540:.0f}")
    res["R4b remote 540 chars: plain end at the predicted time (no cut-off), within 150 ms"] = (
        first(g540, "end") is not None and not kinds(g540, "error") and abs(d540 - want540) <= 150)
    gc = r.get("gcancel")
    print("note: gcancel", gc and [e for e in gc if e[0] != "boundary"])
    res["R5 remote cancel: start, then error interrupted, no end"] = (
        first(gc, "start") is not None and [e[2] for e in kinds(gc, "error")] == ["interrupted"] and first(gc, "end") is None)
    gp = r.get("gpause")
    print("note: gpause", gp and [e for e in gp if e[0] != "boundary"])
    # stock 154 (section 2): a Google voice fires no pause/resume events, but its end moves by the paused second
    want200 = predicted_ms(200)
    dp = dur(gp)
    print(f"note: gpause end-start {dp} predicted {want200 + 1000:.0f}")
    flags = [e[2] for e in kinds(gp, "pausedflag")]
    print("note: speechSynthesis.paused after pause() and 1 s later", flags)
    # stock 154 (section 4): speechSynthesis.paused stays false for a Google voice, before and after pause()
    res["R6 remote pause/resume: no pause/resume events, paused reads false, end later by the paused second (within 250 ms)"] = (
        first(gp, "start") is not None and not kinds(gp, "pause") and not kinds(gp, "resume")
        and flags == ["false", "false"] and abs(dp - (want200 + 1000)) <= 250)
    l43 = r.get("l43")
    print("note: l43", l43 and [e for e in l43 if e[0] != "boundary"], "boundaries", len(kinds(l43, "boundary")))
    ls = first(l43, "start")
    res["R8 control: a local voice still fires per-word boundaries at start ~0"] = len(kinds(l43, "boundary")) >= 8 and ls is not None and ls < 100
    for k, ok in res.items():
        print("PASS " if ok else "FAIL ", k)
    n = sum(bool(x) for x in res.values())
    print(f"{n}/{len(res)} {'ALL_PASS' if n == len(res) == EXPECTED else 'FAIL'}")
    sys.exit(0 if n == len(res) == EXPECTED else 1)


if __name__ == "__main__":
    main()
