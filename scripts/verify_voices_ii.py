"""Verifies voices-ii: word-boundary events, deterministic end-timing jitter,
and the per-speak generation token (stale-timer early-end fix). Extends
sp4-voices' fake speak() completion. Driven over content_shell via lib_shell
(about:blank; SpeechSynthesis is Exposed=Window). See
docs/superpowers/measurements/2026-09-06-voices-ii-surfaces.md.

The end-timing jitter is a pure function of an FNV-1a-64 hash of the utterance
text + voiceURI (UTF-8), replicated below, so V-JITTER-A can assert the exact
predicted jittered end (a strong RED->GREEN: pre-fix the end is the unjittered
linear value).
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell

VOICE_URI = "urn:camou:en"
CPS = 12.5
ONE_VOICE = {"voices:list": [{"name": "Camou EN", "lang": "en-US",
                              "voiceURI": VOICE_URI,
                              "localService": True, "default": True}]}

def cfg(): return json.dumps(ONE_VOICE)

# Mirror of the C++ inline FNV-1a-64 in speech_synthesis.cc: offset basis, prime,
# fold text bytes then voiceURI bytes, unit = (h>>11)/2^53, jitter in +/-0.15.
def predicted_jitter(text, uri=VOICE_URI):
    MASK = (1 << 64) - 1
    h = 0xcbf29ce484222325
    for b in (text.encode("utf-8") + uri.encode("utf-8")):
        # NOTE: fold is text THEN uri as two separate loops in C++, but a single
        # concatenated byte stream is identical (same order, same ops).
        h ^= b
        h = (h * 0x100000001b3) & MASK
    unit = (h >> 11) / float(1 << 53)
    return (unit - 0.5) * 2.0 * 0.15

def predicted_end_ms(text, rate=1.0):
    base = len(text) / (CPS * rate)
    return base * (1.0 + predicted_jitter(text)) * 1000.0

def run(expr):
    v, e = lib_shell.session(cfg(), [expr], navigate_to="about:blank")
    if e: return {"session_err": str(e)}
    return v[0]

BOUNDARY = r"""(async () => {
  speechSynthesis.getVoices(); await new Promise(r=>setTimeout(r,300));
  const voices = speechSynthesis.getVoices();
  if (!voices.length) return {error:'no voice'};
  const u = new SpeechSynthesisUtterance('the quick brown fox jumps');
  u.voice = voices[0]; u.rate = 1.0;
  const seq = [], boundaries = [];
  return await new Promise((res) => {
    u.onstart = () => seq.push('start');
    u.onboundary = (e) => { seq.push('boundary'); boundaries.push({name:e.name, charIndex:e.charIndex, charLength:e.charLength}); };
    u.onend = () => { seq.push('end'); res({seq, boundaries}); };
    u.onerror = (e) => res({error:e.error});
    speechSynthesis.speak(u);
    setTimeout(() => res({seq, boundaries, timeout:true}), 8000);
  });
})()"""

def jitter_probe(text):
    return (r"""(async () => {
      speechSynthesis.getVoices(); await new Promise(r=>setTimeout(r,300));
      const voices = speechSynthesis.getVoices();
      if (!voices.length) return {error:'no voice'};
      const u = new SpeechSynthesisUtterance(%s);
      u.voice = voices[0]; u.rate = 1.0;
      const t0 = performance.now();
      return await new Promise((res) => {
        u.onend = () => res({endMs: performance.now()-t0});
        u.onerror = (e) => res({error:e.error});
        speechSynthesis.speak(u);
        setTimeout(() => res({timeout:true}), 9000);
      });
    })()""" % json.dumps(text))

# V-REUSE2 (GUARD, non-discriminating on this harness): the fake->non-fake
# transition. speak() a camou voice, cancel(), reassign the SAME utterance to a
# non-camou voice (null) and re-speak() it (the real/mojo path); assert no stale
# fake boundary fires after the re-speak. The generation-per-speak-start fix
# closes this on a backend-present target, but content_shell has NO TTS backend,
# so the non-fake re-speak fast-fails and the utterance leaves
# CurrentSpeechUtterance() before the stale tasks evaluate -- the pre-existing
# `u == CurrentSpeechUtterance()` guard already suppresses them here, so this
# check reads 0 both pre- and post-fix (cannot go RED on this box). Kept as a
# regression guard / intent record; the fix itself is verified by construction.
REUSE2 = r"""(async () => {
  speechSynthesis.getVoices(); await new Promise(r=>setTimeout(r,300));
  const voices = speechSynthesis.getVoices();
  if (!voices.length) return {error:'no voice'};
  const u = new SpeechSynthesisUtterance('one two three four five six seven eight');
  u.voice = voices[0]; u.rate = 1.0;
  let counting = false;
  const stale = [];
  u.onboundary = (e) => { if (counting) stale.push(e.charIndex); };
  speechSynthesis.speak(u);
  await new Promise(r=>setTimeout(r,300));
  speechSynthesis.cancel();
  await new Promise(r=>setTimeout(r,50));
  counting = true;          // count only boundaries after the non-fake re-speak
  u.voice = null;           // re-speak the SAME object with a non-camou voice
  speechSynthesis.speak(u);
  await new Promise(r=>setTimeout(r,3000));
  return { staleBoundaryCount: stale.length };
})()"""

# cancel() 1000ms into speak#1, then re-speak the SAME object. A wide cancel gap
# separates the stale early-end (~base-1050 from re-speak) from the fresh
# jittered end (~base from re-speak).
REUSE = r"""(async () => {
  speechSynthesis.getVoices(); await new Promise(r=>setTimeout(r,300));
  const voices = speechSynthesis.getVoices();
  if (!voices.length) return {error:'no voice'};
  const u = new SpeechSynthesisUtterance('aaaaaaaaaaaaaaaaaaaaaaaa'); // 24 -> base ~1920ms
  u.voice = voices[0]; u.rate = 1.0;
  speechSynthesis.speak(u);
  await new Promise(r=>setTimeout(r,1000));
  speechSynthesis.cancel();
  await new Promise(r=>setTimeout(r,50));
  const t1 = performance.now();
  const ends = [];
  return await new Promise((res) => {
    u.onend = () => { ends.push(performance.now()-t1); res({ends}); };
    u.onerror = (e) => res({error:e.error, ends});
    speechSynthesis.speak(u);
    setTimeout(() => res({ends, timeout: ends.length===0}), 5000);
  });
})()"""

def main():
    results, notes = {}, []

    # V-BOUNDARY
    b = run(BOUNDARY)
    exp_ci = [0, 4, 10, 16, 20]; exp_cl = [3, 5, 5, 3, 5]
    if not isinstance(b, dict) or b.get("boundaries") is None:
        results["V-BOUNDARY"] = False; notes.append(f"V-BOUNDARY: {b}")
    else:
        bs = b["boundaries"]; seq = b.get("seq", [])
        ci = [x["charIndex"] for x in bs]; cl = [x["charLength"] for x in bs]
        names_ok = all(x["name"] == "word" for x in bs)
        order_ok = seq[:1] == ["start"] and seq[-1:] == ["end"] and \
                   all(s == "boundary" for s in seq[1:-1])
        incr = all(ci[i] < ci[i+1] for i in range(len(ci)-1))
        results["V-BOUNDARY"] = (len(bs) == 5 and ci == exp_ci and cl == exp_cl
                                 and names_ok and order_ok and incr)
        notes.append(f"V-BOUNDARY count={len(bs)} ci={ci} cl={cl} names_ok={names_ok} "
                     f"order={seq} incr={incr}")

    # V-JITTER-A: endMs matches the PREDICTED jittered end (not the linear one).
    # 'z'*40 has predicted jitter +0.1361 -> jittered end ~3635ms vs linear
    # 3200ms, ~435ms apart, far beyond timer slop.
    TEXT = "z" * 40
    pj = predicted_jitter(TEXT)
    pred = predicted_end_ms(TEXT)
    linear = len(TEXT) / CPS * 1000.0
    ja = run(jitter_probe(TEXT))
    if not isinstance(ja, dict) or ja.get("endMs") is None:
        results["V-JITTER-A"] = False; notes.append(f"V-JITTER-A: {ja}")
    else:
        endMs = ja["endMs"]
        # precondition: chosen text's jitter must be non-trivial so the linear
        # and jittered ends are separated well beyond timer slop.
        substantial = abs(pj) > 0.03
        near_pred = abs(endMs - pred) < 60.0
        far_from_linear = abs(endMs - linear) > 60.0
        results["V-JITTER-A"] = substantial and near_pred and far_from_linear
        notes.append(f"V-JITTER-A jitter={pj:.4f} pred={pred:.0f} linear={linear:.0f} "
                     f"endMs={endMs:.0f} near_pred={near_pred} far_from_linear={far_from_linear} "
                     f"substantial={substantial}")

    # V-JITTER-B: reread determinism (guard, not a discriminator)
    j1 = run(jitter_probe(TEXT)); j2 = run(jitter_probe(TEXT))
    if not (isinstance(j1, dict) and isinstance(j2, dict) and j1.get("endMs") and j2.get("endMs")):
        results["V-JITTER-B"] = False; notes.append(f"V-JITTER-B: {j1} {j2}")
    else:
        d = abs(j1["endMs"] - j2["endMs"])
        results["V-JITTER-B"] = d < 30.0
        notes.append(f"V-JITTER-B |endMs1-endMs2|={d:.1f}ms")

    # V-REUSE: exactly one end, and it is the fresh (late) one, not the stale early
    r = run(REUSE)
    base24 = 24 / CPS * 1000.0  # ~1920ms nominal
    if not isinstance(r, dict) or r.get("ends") is None:
        results["V-REUSE"] = False; notes.append(f"V-REUSE: {r}")
    else:
        ends = r["ends"]
        results["V-REUSE"] = len(ends) == 1 and ends[0] > 1300.0
        notes.append(f"V-REUSE ends={[round(x) for x in ends]} (stale~870 fresh~1632-2208, "
                     f"base={base24:.0f})")

    # V-REUSE2: no stale fake boundary fires after a fake->non-fake re-speak
    r2 = run(REUSE2)
    if not isinstance(r2, dict) or r2.get("staleBoundaryCount") is None:
        results["V-REUSE2"] = False; notes.append(f"V-REUSE2: {r2}")
    else:
        results["V-REUSE2"] = r2["staleBoundaryCount"] == 0
        notes.append(f"V-REUSE2 staleBoundaryCount={r2['staleBoundaryCount']} (0 = fixed)")

    order = ["V-BOUNDARY", "V-JITTER-A", "V-JITTER-B", "V-REUSE", "V-REUSE2"]
    for k in order: print(f"{k}: {'PASS' if results.get(k) else 'FAIL'}")
    for n in notes: print(f"      {n}")
    n = sum(1 for k in order if results.get(k))
    print(f"{n}/{len(order)} " + ("ALL_PASS" if n == len(order) else "FAIL"))
    sys.exit(0 if n == len(order) else 1)

if __name__ == "__main__": main()
