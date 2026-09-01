"""Verifies the SP4-audio Task 2 AudioBuffer readback noise and the Task 3
AnalyserNode readback noise: with audio:seed configured, samples read back
via AudioBuffer.getChannelData / AnalyserNode.get{Float,Byte}FrequencyData
carry deterministic, seed-derived noise -- a reread of the same rendered
buffer reproduces exactly, a different seed diverges, and the frequency-domain
Float/Byte readbacks stay mutually coherent (both read the same perturbed
magnitude buffer, not independently-noised destinations).

Driven with Playwright's sync API over content_shell's CDP via
lib_shell.session -- the same shape as verify_sp3a.py / verify_sp1b.py: a
fault in a session becomes a FAIL line, never a traceback that discards
results already collected.

  A1 OfflineAudioContext seed-stability: render a fixed graph
     (OscillatorNode -> DynamicsCompressor -> destination, the canonical
     audiocontext-fingerprinting probe) in an OfflineAudioContext, await
     startRendering(), and sum a fixed slice of getChannelData(0) (samples
     4500-4999). With audio:seed=777, two SEPARATE content_shell processes
     give a BYTE-IDENTICAL sum (reread/seed-stability -- the noise must be a
     pure function of the seed + buffer content, not of anything
     process-random); a third process with audio:seed=888 gives a DIFFERENT
     sum (the seed actually perturbs the samples). OfflineAudioContext
     renders in software, so this needs no GPU and runs headless.

  A2 AnalyserNode frequency-domain seed-stability: render a steady sine tone
     (OscillatorNode -> AnalyserNode -> destination) in an OfflineAudioContext,
     using suspend()/resume() to pause the render mid-stream (at 0.5s, well
     past the FFT window's transient) and read getFloatFrequencyData there --
     this gives AnalyserNode a live, sample-accurate render without a
     real-time audio sink, so it still runs headless. With audio:seed=777,
     two SEPARATE content_shell processes give a BYTE-IDENTICAL float array
     (same reread/seed-stability property as A1); a third process with
     audio:seed=888 gives a DIFFERENT array.

  A3 Float/Byte frequency-domain coherence: from the SAME suspended frame (one
     session, one settle point, both getFloatFrequencyData and
     getByteFrequencyData read back to back before resuming), recompute the
     stock byte-scaling of each noised float dB value --
     round(255*(floatDb - minDecibels)/(maxDecibels - minDecibels)), clamped
     to [0, 255] -- and assert it matches the actual byte array within +/-1
     (the C++ side truncates rather than rounds, so a 1-count slop absorbs
     that without weakening the coherence claim). Matching proves both
     readbacks are reading the SAME perturbed magnitude buffer, not two
     independently-noised destinations that happen to look similar.

  A2b AnalyserNode frequency-domain no-drift at smoothingTimeConstant=1.0:
     magnitude_buffer_ is an EMA (k*prev + (1-k)*new). At the spec-legal
     upper bound k=1.0 the fresh FFT term drops out entirely, so a real
     device's reported spectrum freezes at whatever it was when k became
     1.0 -- it does not keep changing frame over frame. This is the
     regression test for the bug Task 3 originally shipped: perturbing
     magnitude_buffer_ IN PLACE means each frame's DoFFTAnalysis reads back
     the already-noised value through the k*prev term and perturbs it AGAIN,
     so at k=1.0 (where the EMA itself no longer changes the buffer) the
     only thing still moving it is the perturbation step re-applied every
     frame -- an unbounded multiplicative random walk across frames. The
     fix perturbs a scratch copy at each readback instead, so
     magnitude_buffer_ is never mutated and, once frozen by k=1.0, produces
     byte-identical readbacks forever.

     Renders a steady sine (OscillatorNode -> AnalyserNode -> destination)
     with the DEFAULT smoothingTimeConstant for one seed read (so
     magnitude_buffer_ becomes a genuine nonzero value -- the walk needs a
     nonzero start, since a relative perturbation of exactly 0 is a fixed
     point), then sets smoothingTimeConstant = 1.0 and reads
     getFloatFrequencyData at three further suspend points spread across
     several render quanta (0.2s, 0.3s, 0.4s). The three post-switch reads
     must be pairwise byte-identical (flat, matching a real device); any
     pairwise difference is the drift tell.

  TD-A2 Time-domain seed-stability: at a single suspend point (OfflineAudio-
     Context, same shape as A2/A3 but reading getFloatTimeDomainData /
     getByteTimeDomainData instead), two getFloatTimeDomainData() reads back
     to back are byte-identical (input_buffer_ is frozen at a suspend point,
     so re-deriving the same perturbation from the same frozen window is a
     pure-function reread); across separate content_shell processes,
     audio:seed=777 reproduces and audio:seed=888 diverges -- the same
     seed-stability property as A1/A2, extended to the time domain that
     Task 3 left smoke-tested only.

  TD-A3 Time-domain Float/Byte coherence: from the SAME suspend point used
     by TD-A2, recompute the stock byte-scaling of each noised float sample
     -- round(128*(floatSample+1)), clamped to [0, 255] -- and assert it
     matches the actual byte array within +/-1 (same truncate-vs-round slop
     rationale as A3). Matching proves both time-domain readbacks derive
     from the same frozen input_buffer_ window, not two independently-noised
     destinations that happen to look similar.
"""

import json
import sys

import lib_shell

SEED_777 = json.dumps({"audio:seed": 777})
SEED_888 = json.dumps({"audio:seed": 888})

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
# this needs no GPU and runs headless, same as A1. Both readbacks are taken
# at the SAME suspend point (same frame, no DoFFTAnalysis re-run between
# them) so A3 can check them for coherence.
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


# OscillatorNode -> AnalyserNode -> destination, smoothingTimeConstant driven
# to its spec-legal upper bound (1.0) after one seed read. suspendTimes[0]
# uses the analyser's default smoothingTimeConstant (0.8) purely to seed
# magnitude_buffer_ with a genuine nonzero value -- a relative perturbation
# of exactly 0 is a fixed point (0 * (1+delta) == 0), so the drift this test
# is built to catch cannot show up starting from the zero-initialized
# buffer. Immediately after that seed read, smoothingTimeConstant is set to
# 1.0 (the fresh FFT term's weight (1-k) becomes exactly 0), and three more
# reads are taken at later suspend points spread across many render quanta.
# A real device's reported spectrum is frozen from that point on; only the
# in-place-perturbation bug keeps moving it.
ANALYSER_NO_DRIFT = """() => new Promise((resolve, reject) => {
  try {
    const ctx = new OfflineAudioContext(1, Math.ceil(44100 * 0.6), 44100);
    const osc = ctx.createOscillator();
    osc.type = 'sine';
    osc.frequency.value = 1000;
    const analyser = ctx.createAnalyser();
    osc.connect(analyser);
    analyser.connect(ctx.destination);
    osc.start(0);

    const suspendTimes = [0.1, 0.2, 0.3, 0.4];
    const reads = [];

    function readFloat() {
      const data = new Float32Array(analyser.frequencyBinCount);
      analyser.getFloatFrequencyData(data);
      return Array.from(data);
    }

    function scheduleSuspend(i) {
      if (i >= suspendTimes.length) return;
      ctx.suspend(suspendTimes[i]).then(() => {
        reads.push(readFloat());
        if (i === 0) {
          // Seed read done; switch to the spec-legal upper bound for every
          // subsequent read.
          analyser.smoothingTimeConstant = 1.0;
        }
        scheduleSuspend(i + 1);
        ctx.resume();
      }).catch(reject);
    }

    scheduleSuspend(0);
    ctx.startRendering().then(() => {
      resolve(reads);
    }).catch(reject);
  } catch (e) { reject(e); }
})
"""


def render_no_drift(config):
    """One content_shell session: renders ANALYSER_NO_DRIFT, returns the
    4-element reads array (or (None, err) on any fault)."""
    vals, err = lib_shell.session(config, [ANALYSER_NO_DRIFT])
    if err is not None or vals is None:
        return None, err
    return vals[0], None


# OscillatorNode -> AnalyserNode -> destination, same shape as ANALYSER_READ
# but reading the time-domain getters instead of the frequency-domain ones.
# Two getFloatTimeDomainData() reads back to back at the same suspend point
# (no render advance, no DoFFTAnalysis involved -- time-domain reads never
# call it) give TD-A2's within-call reread-determinism check; getByteTime-
# DomainData is read from the same suspend point for TD-A3's coherence
# check.
TD_ANALYSER_READ = """() => new Promise((resolve, reject) => {
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
      const floatData1 = new Float32Array(analyser.fftSize);
      analyser.getFloatTimeDomainData(floatData1);
      const floatData2 = new Float32Array(analyser.fftSize);
      analyser.getFloatTimeDomainData(floatData2);
      const byteData = new Uint8Array(analyser.fftSize);
      analyser.getByteTimeDomainData(byteData);
      resolve({
        floatData1: Array.from(floatData1),
        floatData2: Array.from(floatData2),
        byteData: Array.from(byteData),
      });
      ctx.resume().catch(() => {});
    }).catch(reject);

    ctx.startRendering().catch(() => {});
  } catch (e) { reject(e); }
})
"""


def render_td_analyser(config):
    """One content_shell session: renders TD_ANALYSER_READ, returns
    (data, err). Same fault contract as render_analyser."""
    vals, err = lib_shell.session(config, [TD_ANALYSER_READ])
    if err is not None or vals is None:
        return None, err
    return vals[0], None


results = {}
notes = []

# Three separate content_shell processes: same seed twice (reread-stability
# must not depend on anything process-random), then a different seed.
sum_a, err_a = render_sum(SEED_777)
sum_b, err_b = render_sum(SEED_777)
sum_c, err_c = render_sum(SEED_888)

A1 = "A1 OfflineAudioContext seed-stability: same seed reproduces, different seed diverges"

if err_a is not None or err_b is not None or err_c is not None:
    results[A1] = False
    if err_a is not None:
        notes.append(f"A1: seed=777 (a): {type(err_a).__name__}: {err_a}")
    if err_b is not None:
        notes.append(f"A1: seed=777 (b): {type(err_b).__name__}: {err_b}")
    if err_c is not None:
        notes.append(f"A1: seed=888: {type(err_c).__name__}: {err_c}")
else:
    stable = sum_a == sum_b
    differs = sum_a != sum_c
    results[A1] = stable and differs
    notes.append(f"A1 seed=777 sum(a)={sum_a!r} sum(b)={sum_b!r} seed=888 sum={sum_c!r}")
    if not results[A1]:
        notes.append(f"A1: stable={stable} differs={differs}")

# Three separate content_shell processes, same shape as A1: same seed twice
# (reread-stability must not depend on anything process-random), then a
# different seed. data_a is also reused by A3 below -- it already carries
# both readbacks from the same suspended frame.
data_a, err_a2a = render_analyser(SEED_777)
data_b, err_a2b = render_analyser(SEED_777)
data_c, err_a2c = render_analyser(SEED_888)

A2 = "A2 AnalyserNode freq seed-stability: same seed reproduces, different seed diverges"

if err_a2a is not None or err_a2b is not None or err_a2c is not None:
    results[A2] = False
    if err_a2a is not None:
        notes.append(f"A2: seed=777 (a): {type(err_a2a).__name__}: {err_a2a}")
    if err_a2b is not None:
        notes.append(f"A2: seed=777 (b): {type(err_a2b).__name__}: {err_a2b}")
    if err_a2c is not None:
        notes.append(f"A2: seed=888: {type(err_a2c).__name__}: {err_a2c}")
else:
    float_a = data_a["floatData"]
    float_b = data_b["floatData"]
    float_c = data_c["floatData"]
    stable = float_a == float_b
    differs = float_a != float_c
    results[A2] = stable and differs
    notes.append(f"A2 seed=777 float(a)==float(b): {stable}; "
                 f"seed=777 vs seed=888 differs: {differs}; bins={len(float_a)}")
    if not results[A2]:
        notes.append(f"A2: stable={stable} differs={differs}")

A3 = "A3 Float/Byte freq coherence: byte readback matches stock scaling of noised float readback"

if data_a is None:
    results[A3] = False
    notes.append("A3: no data from seed=777 render (see A2 error above)")
else:
    float_data = data_a["floatData"]
    byte_data = data_a["byteData"]
    min_db = data_a["minDecibels"]
    max_db = data_a["maxDecibels"]
    scale = 1.0 if max_db == min_db else 255.0 / (max_db - min_db)
    mismatches = []
    for i, (fdb, bval) in enumerate(zip(float_data, byte_data)):
        expected = round((fdb - min_db) * scale)
        expected = max(0, min(255, expected))
        if abs(expected - bval) > 1:
            mismatches.append((i, fdb, bval, expected))
    results[A3] = (len(float_data) > 0 and len(float_data) == len(byte_data)
                    and not mismatches)
    notes.append(f"A3 checked {len(float_data)} bins, mismatches={len(mismatches)} "
                 f"(minDecibels={min_db} maxDecibels={max_db})")
    if mismatches:
        notes.append(f"A3 first mismatches (bin, floatDb, byte, expected): "
                     f"{mismatches[:5]}")

# One content_shell process: 4 suspend-point reads, the first seeding
# magnitude_buffer_ with the default smoothingTimeConstant, the remaining
# three taken after switching to the spec-legal upper bound (1.0).
reads_a2b, err_a2b_ = render_no_drift(SEED_777)

A2B = "A2b AnalyserNode freq no-drift at smoothingTimeConstant=1.0: spectrum stays flat across frames, not drifting"

if err_a2b_ is not None or reads_a2b is None:
    results[A2B] = False
    notes.append(f"A2b: {type(err_a2b_).__name__}: {err_a2b_}")
elif len(reads_a2b) != 4:
    results[A2B] = False
    notes.append(f"A2b: expected 4 reads, got {len(reads_a2b)}")
else:
    r1, r2, r3 = reads_a2b[1], reads_a2b[2], reads_a2b[3]
    eq_12 = r1 == r2
    eq_23 = r2 == r3
    results[A2B] = eq_12 and eq_23
    notes.append(f"A2b post-switch reads equal: r1==r2:{eq_12} r2==r3:{eq_23} "
                 f"bins={len(r1)}")
    if not results[A2B]:
        diffs_12 = sum(1 for x, y in zip(r1, r2) if x != y)
        diffs_23 = sum(1 for x, y in zip(r2, r3) if x != y)
        notes.append(f"A2b differing bins: r1-vs-r2={diffs_12} r2-vs-r3={diffs_23}")

# Three separate content_shell processes, same shape as A2: same seed twice,
# then a different seed. td_data_a is also reused by TD-A3 below.
td_data_a, td_err_a = render_td_analyser(SEED_777)
td_data_b, td_err_b = render_td_analyser(SEED_777)
td_data_c, td_err_c = render_td_analyser(SEED_888)

TD_A2 = "TD-A2 time-domain seed-stability: two reads byte-identical, same seed reproduces, different seed diverges"

if td_err_a is not None or td_err_b is not None or td_err_c is not None:
    results[TD_A2] = False
    if td_err_a is not None:
        notes.append(f"TD-A2: seed=777 (a): {type(td_err_a).__name__}: {td_err_a}")
    if td_err_b is not None:
        notes.append(f"TD-A2: seed=777 (b): {type(td_err_b).__name__}: {td_err_b}")
    if td_err_c is not None:
        notes.append(f"TD-A2: seed=888: {type(td_err_c).__name__}: {td_err_c}")
else:
    within_call_stable = td_data_a["floatData1"] == td_data_a["floatData2"]
    cross_stable = td_data_a["floatData1"] == td_data_b["floatData1"]
    cross_differs = td_data_a["floatData1"] != td_data_c["floatData1"]
    results[TD_A2] = within_call_stable and cross_stable and cross_differs
    notes.append(f"TD-A2 within_call_stable={within_call_stable} "
                 f"seed=777 cross-process stable={cross_stable}; "
                 f"seed=777 vs seed=888 differs={cross_differs}; "
                 f"samples={len(td_data_a['floatData1'])}")
    if not results[TD_A2]:
        notes.append(f"TD-A2: within_call_stable={within_call_stable} "
                     f"cross_stable={cross_stable} cross_differs={cross_differs}")

TD_A3 = "TD-A3 time-domain Float/Byte coherence: byte readback matches stock scaling of noised float readback"

if td_data_a is None:
    results[TD_A3] = False
    notes.append("TD-A3: no data from seed=777 render (see TD-A2 error above)")
else:
    float_data = td_data_a["floatData1"]
    byte_data = td_data_a["byteData"]
    mismatches = []
    for i, (fs, bval) in enumerate(zip(float_data, byte_data)):
        expected = round(128 * (fs + 1))
        expected = max(0, min(255, expected))
        if abs(expected - bval) > 1:
            mismatches.append((i, fs, bval, expected))
    results[TD_A3] = (len(float_data) > 0 and len(float_data) == len(byte_data)
                       and not mismatches)
    notes.append(f"TD-A3 checked {len(float_data)} samples, "
                 f"mismatches={len(mismatches)}")
    if mismatches:
        notes.append(f"TD-A3 first mismatches (i, floatSample, byte, expected): "
                     f"{mismatches[:5]}")

EXPECTED = 6

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
