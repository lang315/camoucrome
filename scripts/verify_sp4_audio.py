"""Verifies the SP4-audio AudioContext scalar overrides and the absence of any
other audio surface change. The readback noise (audio:seed, AudioBuffer and
AnalyserNode) was removed on 2026-11-03 by owner ruling after the M0 probe, so
the old seed rows (A1-A3, A2b, A3b, TD-A2, TD-A3, TD-A3b, A7) are gone and
only A4, A5 and A6 remain.

Driven with Playwright's sync API over content_shell's CDP via
lib_shell.session -- the same shape as verify_sp3a.py / verify_sp1b.py: a
fault in a session becomes a FAIL line, never a traceback that discards
results already collected.

  A4 AudioContext scalar overrides: with AudioContext:baseLatency=0.01,
     AudioContext:outputLatency=0.05, AudioContext:maxChannelCount=6 all
     configured, a plain `new AudioContext()` reports .baseLatency,
     .outputLatency, and .destination.maxChannelCount exactly equal to the
     configured values (real-value-first, config-override-last per the SP0
     hook; sampleRate is deliberately untouched, out of scope). These
     getters are synchronous and answer immediately after construction, so
     this needs no rendering, suspend point, or seed -- one content_shell
     session, one read.

  A5 no new observable surface (Task 5): Object.keys(window) and
     Object.keys() of the four prototypes this task's patch touches --
     AudioContext.prototype, AudioBuffer.prototype, AnalyserNode.prototype,
     AudioDestinationNode.prototype -- match a genuinely STOCK content_shell
     (this task's three files reverted, then rebuilt) exactly: nothing added,
     nothing removed. Unlike navigator's instance keys in verify_sp4_fonts.py's
     F6 (which measure vacuously empty there -- WebIDL members normally live
     on Interface.prototype, not the instance), these four prototypes on this
     content_shell build DO carry their own-enumerable WebIDL members
     (measured empirically: AudioContext.prototype has 11 own keys,
     AudioBuffer.prototype 7, AnalyserNode.prototype 9,
     AudioDestinationNode.prototype 1), so this is a real, non-vacuous check
     on this engine -- not the fonts-style navigator no-op the brief warned
     might recur. Plus a standing native-accessor regression check:
     AudioBuffer.prototype.getChannelData.toString() and AnalyserNode.
     prototype.getFloatFrequencyData.toString() still match /[native code]/
     -- the scalar overrides live in the C++ implementation, not in a JS
     override of any accessor, so this should never move.
     The stock reference is a PERSISTED baseline, captured once from a real
     stock content_shell into baselines/, exactly as verify_sp4_fonts.py's F6
     and verify_sp3a.py's C10 do for their own key-diff checks -- run with
     --capture-baseline against that stock binary first (see the CAPTURE
     NOTE below); every later run reads the frozen file.

  A6 stock fallback (Task 5): with NO CAMOU_CONFIG at all (bare) on the
     SAME already-patched (post Task 2-4) content_shell used everywhere else
     in this file, an OfflineAudioContext getChannelData sum, a bare
     getFloatFrequencyData read, and the three A4
     scalars all equal the values measured on a genuinely STOCK binary --
     i.e. the scalar overrides are gated on config being present, not
     unconditional, so an unconfigured session is bit-for-bit
     indistinguishable from a real, unpatched device on these surfaces.
     OfflineAudioContext rendering of a fixed synthetic graph is fully
     deterministic (no real-time audio sink, no host-hardware timing), so
     "equals stock" is a real, checkable claim, not a coincidence of a
     free-running clock. Reuses the SAME stock baseline file as A5 (captured
     in the same --capture-baseline pass, since it is the same config=None
     session that already yields A5's key reads).

CAPTURE NOTE (A5/A6's stock baseline): this script's A4 runs against the
CURRENT (already-patched) binary under test, matching every other verify_* script in this repo. A5 and A6 are the two
criteria that additionally need a reading from a binary that does NOT have
this task's three-file patch applied at all, because both "no new surface" and
"stock values absent config" are invisible to any same-binary configured-vs-bare
comparison (build-time property additions and a config-gated override both
read identically whether or not the patch itself is present, only whether
CAMOU_CONFIG is set). Recapturing after this task lands requires: `git
checkout HEAD -- <the three sp4-audio files: BUILD.gn, audio_context.cc, audio_destination_node.cc>` in the checkout, rebuild
content_shell, run this script with `--capture-baseline` (writes
~/camoucrome-verify/baselines/content_shell-sp4audio-stock.json; A4 is
expected to read FAIL during that capture run, since the scalar overrides
have no effect on a stock binary -- that is the required RED-first
evidence, not a bug in the capture), then `git apply` the patch back and
rebuild again before running normally. The baseline JSON is NOT committed to
this repo (same as verify_sp3a's canvas baseline and verify_sp4_fonts' key
baseline) -- it is regenerable, build-host state, tracked only in
~/camoucrome-verify/baselines/ on the verify machine.
"""

import json
import os
import sys

import lib_shell

CONFIG_A4 = json.dumps({
    "AudioContext:outputLatency": 0.05,
    "AudioContext:baseLatency": 0.01,
    "AudioContext:maxChannelCount": 6,
})

# OscillatorNode -> DynamicsCompressor -> destination: the canonical
# OfflineAudioContext fingerprinting graph. 1 channel, 44100 frames @ 44100Hz
# is comfortably long enough that samples 4500-4999 are real rendered signal,
# well past the oscillator's start transient.
RENDER_AND_SUM = """() => new Promise((resolve, reject) => {
  try {
    const ctx = new OfflineAudioContext(1, 44100, 44100);
    const osc = ctx.createOscillator();
    osc.type = 'triangle';
    osc.frequency.value = 10000;
    const compressor = ctx.createDynamicsCompressor();
    compressor.threshold.value = -50;
    compressor.knee.value = 40;
    compressor.ratio.value = 12;
    compressor.attack.value = 0;
    compressor.release.value = 0.25;
    osc.connect(compressor);
    compressor.connect(ctx.destination);
    osc.start(0);
    ctx.startRendering().then((buffer) => {
      const data = buffer.getChannelData(0);
      let sum = 0;
      for (let i = 4500; i < 5000; i++) sum += data[i];
      resolve(sum);
    }).catch(reject);
  } catch (e) { reject(e); }
})
"""


def render_sum(config):
    """One content_shell session: renders RENDER_AND_SUM, returns (sum, err).
    Any fault becomes (None, exc), never a traceback that discards results
    already collected from other sessions."""
    vals, err = lib_shell.session(config, [RENDER_AND_SUM])
    if err is not None or vals is None:
        return None, err
    return vals[0], None


# OscillatorNode -> AnalyserNode -> destination. A steady 1kHz sine, suspended
# once mid-render (0.5s -- ~22 FFT windows past the oscillator's start
# transient) so the read happens against a settled steady-state signal.
# suspend()/resume() gives the AnalyserNode a live render tick without a
# real-time audio sink: OfflineAudioContext still renders in software, so
# this needs no GPU and runs headless, same as the sum probe. Both readbacks are taken
# at the SAME suspend point (same frame, no DoFFTAnalysis re-run between
# them).
ANALYSER_READ = """() => new Promise((resolve, reject) => {
  try {
    const ctx = new OfflineAudioContext(1, 88200, 44100);
    const osc = ctx.createOscillator();
    osc.type = 'sine';
    osc.frequency.value = 1000;
    const analyser = ctx.createAnalyser();
    osc.connect(analyser);
    analyser.connect(ctx.destination);
    osc.start(0);

    ctx.suspend(0.5).then(() => {
      const floatData = new Float32Array(analyser.frequencyBinCount);
      analyser.getFloatFrequencyData(floatData);
      const byteData = new Uint8Array(analyser.frequencyBinCount);
      analyser.getByteFrequencyData(byteData);
      resolve({
        floatData: Array.from(floatData),
        byteData: Array.from(byteData),
        minDecibels: analyser.minDecibels,
        maxDecibels: analyser.maxDecibels,
      });
      ctx.resume().catch(() => {});
    }).catch(reject);

    ctx.startRendering().catch(() => {});
  } catch (e) { reject(e); }
})
"""


def render_analyser(config):
    """One content_shell session: renders ANALYSER_READ, returns (data, err).
    Same fault contract as render_sum: any exception becomes (None, exc)."""
    vals, err = lib_shell.session(config, [ANALYSER_READ])
    if err is not None or vals is None:
        return None, err
    return vals[0], None


# A plain real-time AudioContext (not Offline), read synchronously right
# after construction. baseLatency/outputLatency/maxChannelCount are all
# reported at construction time -- no rendering, suspend point, or seed
# needed. A plain `new AudioContext()` constructs fine headless under
# content_shell's --ozone-platform=headless.
AUDIO_SCALARS = """() => {
  const ctx = new AudioContext();
  return {
    baseLatency: ctx.baseLatency,
    outputLatency: ctx.outputLatency,
    maxChannelCount: ctx.destination.maxChannelCount,
  };
}
"""


def render_audio_scalars(config):
    """One content_shell session: renders AUDIO_SCALARS, returns (data, err).
    Same fault contract as render_analyser."""
    vals, err = lib_shell.session(config, [AUDIO_SCALARS])
    if err is not None or vals is None:
        return None, err
    return vals[0], None


# A5's persisted stock reference -- see the CAPTURE NOTE in the module
# docstring. Not committed to the repo, same as verify_sp3a's canvas baseline
# and verify_sp4_fonts' key baseline: regenerable, build-host-local state.
# Also holds A6's stock values (sum/floatData/scalars), captured in the same
# pass -- see A6's docstring paragraph.
BASELINE = os.path.expanduser(
    "~/camoucrome-verify/baselines/content_shell-sp4audio-stock.json")

# A5 (Task 5): the observable JS surface across window and the four
# Web-Audio prototypes this task's patch touches, plus a standing
# native-accessor check on the two readback getters. Sorted so the baseline
# JSON is diff-friendly.
KEYS_JS = """() => ({
  windowKeys: Object.keys(window).sort(),
  audioContextProtoKeys: Object.keys(AudioContext.prototype).sort(),
  audioBufferProtoKeys: Object.keys(AudioBuffer.prototype).sort(),
  analyserProtoKeys: Object.keys(AnalyserNode.prototype).sort(),
  destinationProtoKeys: Object.keys(AudioDestinationNode.prototype).sort(),
  getChannelDataNative: /\\[native code\\]/.test(
    AudioBuffer.prototype.getChannelData.toString()),
  getFloatFreqNative: /\\[native code\\]/.test(
    AnalyserNode.prototype.getFloatFrequencyData.toString()),
})"""


def render_keys(config):
    """One content_shell session: renders KEYS_JS, returns (data, err). Same
    fault contract as render_analyser."""
    vals, err = lib_shell.session(config, [KEYS_JS])
    if err is not None or vals is None:
        return None, err
    return vals[0], None


results = {}
notes = []

# A5/A6 (Task 5): ONE config=None (bare) session per probe, reused for BOTH
# the --capture-baseline write and the normal current-vs-baseline compare --
# the same pattern verify_sp4_fonts.py's F6 uses its single KEYS_JS session
# for. During a --capture-baseline run this binary is the genuinely stock one
# (this task's three files reverted, per the CAPTURE NOTE), so these readings
# ARE the stock reference; during a normal run this binary is the patched
# one, and these are the "current, bare" readings A5/A6 compare against the
# persisted baseline. render_sum/render_analyser/render_audio_scalars are
# the SAME functions A4 already uses above, just called here with
# config=None instead of a seed.
keys_bare, keys_bare_e = render_keys(None)
sum_bare, sum_bare_e = render_sum(None)
analyser_bare, analyser_bare_e = render_analyser(None)
scalars_bare, scalars_bare_e = render_audio_scalars(None)

# One content_shell session: a plain `new AudioContext()` with all three
# scalar overrides configured, read synchronously right after construction.
data_a4, err_a4 = render_audio_scalars(CONFIG_A4)

A4 = "A4 AudioContext scalar overrides: baseLatency/outputLatency/maxChannelCount honor config"

if data_a4 is None:
    results[A4] = False
    notes.append(f"A4: {type(err_a4).__name__}: {err_a4}")
else:
    base_ok = data_a4["baseLatency"] == 0.01
    output_ok = data_a4["outputLatency"] == 0.05
    max_ok = data_a4["maxChannelCount"] == 6
    results[A4] = base_ok and output_ok and max_ok
    notes.append(f"A4 baseLatency={data_a4['baseLatency']!r} (expect 0.01) "
                 f"outputLatency={data_a4['outputLatency']!r} (expect 0.05) "
                 f"maxChannelCount={data_a4['maxChannelCount']!r} (expect 6)")
    if not results[A4]:
        notes.append(f"A4: base_ok={base_ok} output_ok={output_ok} max_ok={max_ok}")

# --capture-baseline: write A5/A6's stock reference from THIS run's bare
# readings, then exit-code-wise this run still scores A4 normally --
# see the CAPTURE NOTE in the module docstring for why this must be run
# against a genuinely stock (patch-reverted) binary, and why A4 is
# expected to read FAIL during that run.
capture = "--capture-baseline" in sys.argv[1:]
if capture:
    if (keys_bare is not None and sum_bare is not None
            and analyser_bare is not None and scalars_bare is not None):
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        with open(BASELINE, "w") as fh:
            json.dump({
                "windowKeys": keys_bare["windowKeys"],
                "audioContextProtoKeys": keys_bare["audioContextProtoKeys"],
                "audioBufferProtoKeys": keys_bare["audioBufferProtoKeys"],
                "analyserProtoKeys": keys_bare["analyserProtoKeys"],
                "destinationProtoKeys": keys_bare["destinationProtoKeys"],
                "sum": sum_bare,
                "floatData": analyser_bare["floatData"],
                "scalars": scalars_bare,
            }, fh, indent=2)
        notes.append(f"capture: wrote stock baseline to {BASELINE}")
    else:
        notes.append(
            f"capture: one or more bare probes failed (keys={'ok' if keys_bare is not None else keys_bare_e!r} "
            f"sum={'ok' if sum_bare is not None else sum_bare_e!r} "
            f"analyser={'ok' if analyser_bare is not None else analyser_bare_e!r} "
            f"scalars={'ok' if scalars_bare is not None else scalars_bare_e!r}); "
            f"baseline NOT written")

stock_baseline = None
try:
    with open(BASELINE) as fh:
        stock_baseline = json.load(fh)
except Exception as exc:  # noqa: BLE001
    notes.append(f"A5/A6 baseline load from {BASELINE}: {type(exc).__name__}: {exc}")

A5 = "A5 no new observable surface: window + 4 Web-Audio prototype key sets match stock; getChannelData/getFloatFrequencyData stay native"

if capture:
    # This run's own purpose was writing the baseline (see above), not
    # scoring itself against it -- comparing a stock capture to itself as
    # "current" would trivially pass and prove nothing. Same treatment as
    # verify_sp4_fonts.py's F6 on a genuinely stock binary: expected, not a
    # failure of this script.
    results[A5] = False
    notes.append("A5: this run wrote the baseline (--capture-baseline); "
                 "re-run without the flag against the patched binary to score A5")
elif keys_bare is None:
    results[A5] = False
    notes.append(f"A5: keys probe {type(keys_bare_e).__name__}: {keys_bare_e}")
elif stock_baseline is None:
    results[A5] = False
    notes.append("A5: no stock baseline loaded (see baseline load note above)")
else:
    window_ok = keys_bare["windowKeys"] == stock_baseline["windowKeys"]
    ac_ok = keys_bare["audioContextProtoKeys"] == stock_baseline["audioContextProtoKeys"]
    ab_ok = keys_bare["audioBufferProtoKeys"] == stock_baseline["audioBufferProtoKeys"]
    an_ok = keys_bare["analyserProtoKeys"] == stock_baseline["analyserProtoKeys"]
    ad_ok = keys_bare["destinationProtoKeys"] == stock_baseline["destinationProtoKeys"]
    native_ok = bool(keys_bare.get("getChannelDataNative", False)) and bool(
        keys_bare.get("getFloatFreqNative", False))
    results[A5] = window_ok and ac_ok and ab_ok and an_ok and ad_ok and native_ok
    if window_ok:
        win_diff_note = f"window keys unchanged ({len(keys_bare['windowKeys'])} keys)"
    else:
        stock_win = set(stock_baseline["windowKeys"])
        cur_win = set(keys_bare["windowKeys"])
        win_diff_note = (f"window removed={sorted(stock_win - cur_win)!r} "
                          f"added={sorted(cur_win - stock_win)!r}")
    notes.append(
        f"A5 measured: {win_diff_note}; AudioContext.prototype match={ac_ok} "
        f"AudioBuffer.prototype match={ab_ok} AnalyserNode.prototype match={an_ok} "
        f"AudioDestinationNode.prototype match={ad_ok}; "
        f"getChannelData native={keys_bare.get('getChannelDataNative')} "
        f"getFloatFrequencyData native={keys_bare.get('getFloatFreqNative')}")
    if not results[A5]:
        notes.append(
            f"A5: window_ok={window_ok} ac_ok={ac_ok} ab_ok={ab_ok} an_ok={an_ok} "
            f"ad_ok={ad_ok} native_ok={native_ok}")
        if not ac_ok:
            notes.append(f"A5 AudioContext.prototype: stock={stock_baseline['audioContextProtoKeys']!r} "
                         f"current={keys_bare['audioContextProtoKeys']!r}")
        if not ab_ok:
            notes.append(f"A5 AudioBuffer.prototype: stock={stock_baseline['audioBufferProtoKeys']!r} "
                         f"current={keys_bare['audioBufferProtoKeys']!r}")
        if not an_ok:
            notes.append(f"A5 AnalyserNode.prototype: stock={stock_baseline['analyserProtoKeys']!r} "
                         f"current={keys_bare['analyserProtoKeys']!r}")
        if not ad_ok:
            notes.append(f"A5 AudioDestinationNode.prototype: stock={stock_baseline['destinationProtoKeys']!r} "
                         f"current={keys_bare['destinationProtoKeys']!r}")

A6 = "A6 stock fallback (bare, no CAMOU_CONFIG): OfflineAudioContext sum, getFloatFrequencyData, and the three AudioContext scalars all equal stock"

if capture:
    results[A6] = False
    notes.append("A6: this run wrote the baseline (--capture-baseline); "
                 "re-run without the flag against the patched binary to score A6")
elif sum_bare is None or analyser_bare is None or scalars_bare is None:
    results[A6] = False
    notes.append(
        f"A6: bare probes sum={'ok' if sum_bare is not None else sum_bare_e!r} "
        f"analyser={'ok' if analyser_bare is not None else analyser_bare_e!r} "
        f"scalars={'ok' if scalars_bare is not None else scalars_bare_e!r}")
elif stock_baseline is None:
    results[A6] = False
    notes.append("A6: no stock baseline loaded (see baseline load note above)")
else:
    sum_ok = sum_bare == stock_baseline["sum"]
    float_ok = analyser_bare["floatData"] == stock_baseline["floatData"]
    scalars_ok = scalars_bare == stock_baseline["scalars"]
    results[A6] = sum_ok and float_ok and scalars_ok
    notes.append(
        f"A6 measured: sum={sum_bare!r} (stock {stock_baseline['sum']!r}) sum_ok={sum_ok}; "
        f"floatData match={float_ok} ({len(analyser_bare['floatData'])} bins); "
        f"scalars={scalars_bare!r} (stock {stock_baseline['scalars']!r}) scalars_ok={scalars_ok}")
    if not results[A6]:
        notes.append(f"A6: sum_ok={sum_ok} float_ok={float_ok} scalars_ok={scalars_ok}")

EXPECTED = 3

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")

if len(results) != EXPECTED:
    notes.append(f"expected {EXPECTED} criteria, found {len(results)} -- a "
                 "criterion was added/removed without updating EXPECTED")

for note in notes:
    print(f"      {note}")

if results and len(results) == EXPECTED and all(results.values()):
    print("ALL_PASS")
    sys.exit(0)
print("FAIL")
sys.exit(1)
