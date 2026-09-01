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

  A7 Additive-mode zero-preservation (whole-branch-review fix, RED-first):
     AudioBuffer.getChannelData's readback noise (audio_buffer.cc) is
     additive (relative=false), and PerturbAudioSamples' additive branch
     used to do samples[i] += delta unconditionally -- so the first read of
     an ALL-ZERO (silent) channel, e.g. a freshly constructed
     `new AudioContext().createBuffer(1, N, rate)`, came back with every
     sample in +/-1e-4 instead of exact 0.0. Stock is exact 0.0 for a
     silent buffer, so this is a targeted "does this browser tamper with
     audio buffers?" tell. With audio:seed=777, constructs a fresh
     1-channel/2048-frame buffer and asserts getChannelData(0) is EVERY
     element exactly 0.0. RED against the pre-fix binary (additive noise
     makes them all nonzero); GREEN once PerturbAudioSamples skips
     exact-zero samples in additive mode. A second assertion, in the SAME
     session, writes a ramp (nonzero samples) into a second buffer and
     confirms getChannelData still comes back perturbed (nonzero deltas
     from the ramp) -- so the fix is confirmed to still noise real signal,
     not just to have disabled additive noise outright.

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

  A3b Different-length Float/Byte frequency-domain coherence: same suspend
     point and apparatus as A3, but read at THREE different lengths in one
     session: getFloatFrequencyData at FULL length (frequencyBinCount),
     getFloatFrequencyData again at HALF length (frequencyBinCount/2), and
     getByteFrequencyData at HALF length -- the shape a deliberate probe
     would use, since a real fingerprinter calls both getters with the same
     frequencyBinCount (A3's shape). PerturbAudioSamples folds a content
     hash of the span it's given into its seed, so a getter that only
     hashes its own [0..len) destination window derives a DIFFERENT
     per-index delta field depending on len, even though both getters read
     the same underlying magnitude_buffer_.

     The primary, RED-capable check is float-vs-float: the full-length
     read's [0, frequencyBinCount/2) prefix must be EXACTLY bit-identical
     to the half-length read (same suspend point, same magnitude_buffer_
     content, so a length-independent derivation must agree exactly with
     no rounding involved). This is the actual discriminator -- measured
     directly against the pre-fix binary, all 512 shared bins differ, by
     up to ~0.017 dB.

     A secondary check mirrors A3's byte-vs-scaled-float form (round(255*
     (floatDb-minDecibels)/(maxDecibels-minDecibels)), +/-1 tolerance) over
     the half-length byte read vs the full-length float read, matching the
     probe shape a page would actually use. This form is NOT the
     discriminator: getByteFrequencyData's 8-bit quantization is ~0.27 dB
     per step (255 levels over the 70 dB default range) -- about 16x
     coarser than the ~0.017 dB max divergence the length-dependent bug
     produces, so it is mathematically incapable of separating "coherent"
     from "incoherent" at this epsilon through +/-1 byte tolerance (it
     passes both pre- and post-fix). It is kept only so the criterion still
     exercises the byte API surface a real probe would use; the float-vs-
     float check above is what makes this criterion RED-first.

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

  TD-A3b Time-domain length-independence (whole-branch-review fix,
     RED-first): same class of bug as the A3b frequency-domain fix, but in
     the time domain. GetFloatTimeDomainData perturbed destination.first(len)
     and GetByteTimeDomainData built a noised(len) scratch -- both hashed
     only the caller's [0, len) destination window, so PerturbAudioSamples'
     content-hash fold made every per-index delta depend on the caller's
     requested length, even though both getters read the same frozen
     input_buffer_ window. At a single suspend point, calls
     getFloatTimeDomainData twice on the SAME analyser with two different
     destination lengths -- fftSize (full) and fftSize/2 (half) -- and
     asserts the full read's [0, half) prefix is EXACTLY bit-identical to
     the half read (same frozen window, so a length-independent derivation
     must agree exactly, no rounding involved). RED against the pre-fix
     binary (the length-dependent hash makes the two reads diverge over
     their shared prefix); GREEN once both time-domain getters build their
     scratch over the full fft_size window (mirroring the A3b frequency-domain
     fix) before slicing to len for output.

  A4 AudioContext scalar overrides: with AudioContext:baseLatency=0.01,
     AudioContext:outputLatency=0.05, AudioContext:maxChannelCount=6 all
     configured, a plain `new AudioContext()` reports .baseLatency,
     .outputLatency, and .destination.maxChannelCount exactly equal to the
     configured values (real-value-first, config-override-last per the SP0
     hook; sampleRate is deliberately untouched, out of scope). These
     getters are synchronous and answer immediately after construction, so
     unlike A1-TD-A3 this needs no rendering, suspend point, or seed --one
     content_shell session, one read.

  A5 no new observable surface (Task 5): Object.keys(window) and
     Object.keys() of the four prototypes this task's patch touches --
     AudioContext.prototype, AudioBuffer.prototype, AnalyserNode.prototype,
     AudioDestinationNode.prototype -- match a genuinely STOCK content_shell
     (this task's six files reverted, then rebuilt) exactly: nothing added,
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
     -- the noise is injected inside the C++ implementation, not via a JS
     override of the accessor itself, so this should never move.
     The stock reference is a PERSISTED baseline, captured once from a real
     stock content_shell into baselines/, exactly as verify_sp4_fonts.py's F6
     and verify_sp3a.py's C10 do for their own key-diff checks -- run with
     --capture-baseline against that stock binary first (see the CAPTURE
     NOTE below); every later run reads the frozen file.

  A6 stock fallback (Task 5): with NO CAMOU_CONFIG at all (bare) on the
     SAME already-patched (post Task 2-4) content_shell used everywhere else
     in this file, A1's OfflineAudioContext getChannelData sum, a bare
     getFloatFrequencyData read (A2's own render shape), and the three A4
     scalars all equal the values measured on a genuinely STOCK binary --
     i.e. the noise/override paths are gated on config being present, not
     unconditional, so an unconfigured session is bit-for-bit
     indistinguishable from a real, unpatched device on these surfaces.
     OfflineAudioContext rendering of a fixed synthetic graph is fully
     deterministic (no real-time audio sink, no host-hardware timing), so
     "equals stock" is a real, checkable claim, not a coincidence of a
     free-running clock. Reuses the SAME stock baseline file as A5 (captured
     in the same --capture-baseline pass, since it is the same config=None
     session that already yields A5's key reads).

CAPTURE NOTE (A5/A6's stock baseline): this script's A1-A4/A2b/A3b/TD-A2/
TD-A3 all run against the CURRENT (already-patched) binary under test,
matching every other verify_* script in this repo. A5 and A6 are the two
criteria that additionally need a reading from a binary that does NOT have
this task's six-file patch applied at all, because both "no new surface" and
"no noise absent config" are invisible to any same-binary configured-vs-bare
comparison (build-time property additions and a config-gated noise path both
read identically whether or not the patch itself is present, only whether
CAMOU_CONFIG is set). Recapturing after this task lands requires: `git
checkout HEAD -- <the six sp4-audio files>` in the checkout, rebuild
content_shell, run this script with `--capture-baseline` (writes
~/camoucrome-verify/baselines/content_shell-sp4audio-stock.json; the other
eight criteria are expected to read FAIL during that capture run, since
audio:seed has no effect on a stock binary -- that is the required RED-first
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

SEED_777 = json.dumps({"audio:seed": 777})
SEED_888 = json.dumps({"audio:seed": 888})

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


# A7: a plain real-time AudioContext (matches A4's shape -- no rendering or
# suspend point needed). A fresh `createBuffer` is silent (stock: all-zero)
# before anything writes to it, so getChannelData on it directly exercises
# the additive-mode zero-preservation fix. A second buffer, with a ramp
# written into it first, confirms the fix still perturbs real (non-zero)
# signal -- so this criterion cannot be satisfied by simply disabling
# additive noise outright.
AUDIO_ZERO_PRESERVE = """() => {
  const ctx = new AudioContext();
  const silent = ctx.createBuffer(1, 2048, 44100);
  const silentData = Array.from(silent.getChannelData(0));

  // copyToChannel is a write path (not noised, does not set the
  // did_camou_noise_ guard), so it lets us seed a buffer with real (nonzero)
  // signal BEFORE the first noised read -- getChannelData() below is then
  // genuinely the first read of non-zero content, exercising the same
  // additive-noise path as silentData above but on real signal.
  const ramp = ctx.createBuffer(1, 2048, 44100);
  const rampValues = new Float32Array(ramp.length);
  for (let i = 0; i < rampValues.length; i++) {
    rampValues[i] = (i / rampValues.length) * 2 - 1;  // -1 .. 1, nonzero
  }
  ramp.copyToChannel(rampValues, 0);
  const rampBefore = Array.from(rampValues);
  const rampAfter = Array.from(ramp.getChannelData(0));  // first noised read
  return { silentData, rampBefore, rampAfter };
}
"""


def render_audio_zero_preserve(config):
    """One content_shell session: renders AUDIO_ZERO_PRESERVE, returns
    (data, err). Same fault contract as render_sum."""
    vals, err = lib_shell.session(config, [AUDIO_ZERO_PRESERVE])
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


# Same shape and same suspend point as ANALYSER_READ, but deliberately reads
# at THREE different lengths: getFloatFrequencyData at full length
# (frequencyBinCount), getFloatFrequencyData again at half length
# (frequencyBinCount/2), and getByteFrequencyData at half length. A real
# fingerprinter calls both getters with frequencyBinCount (A3 above already
# covers that); this is the deliberate-probe shape that catches a getter
# whose noise derivation depends on the caller's destination length rather
# than only on the underlying magnitude buffer's content. The two float
# reads (bypassing byte quantization) are the actual discriminator -- see
# the A3b docstring above for why the byte read alone cannot be.
ANALYSER_READ_DIFFLEN = """() => new Promise((resolve, reject) => {
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
      const fullLen = analyser.frequencyBinCount;
      const halfLen = Math.floor(fullLen / 2);
      const floatFull = new Float32Array(fullLen);
      analyser.getFloatFrequencyData(floatFull);
      const floatHalf = new Float32Array(halfLen);
      analyser.getFloatFrequencyData(floatHalf);
      const byteHalf = new Uint8Array(halfLen);
      analyser.getByteFrequencyData(byteHalf);
      resolve({
        floatFull: Array.from(floatFull),
        floatHalf: Array.from(floatHalf),
        byteHalf: Array.from(byteHalf),
        minDecibels: analyser.minDecibels,
        maxDecibels: analyser.maxDecibels,
      });
      ctx.resume().catch(() => {});
    }).catch(reject);

    ctx.startRendering().catch(() => {});
  } catch (e) { reject(e); }
})
"""


def render_analyser_difflen(config):
    """One content_shell session: renders ANALYSER_READ_DIFFLEN, returns
    (data, err). Same fault contract as render_analyser."""
    vals, err = lib_shell.session(config, [ANALYSER_READ_DIFFLEN])
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


# Same shape and suspend point as TD_ANALYSER_READ, but calls
# getFloatTimeDomainData TWICE at two different destination lengths -- full
# (fftSize) and half (fftSize/2) -- the time-domain analog of A3b's
# different-length frequency probe. Both reads are taken at the same suspend
# point (input_buffer_ frozen, no WriteInput between them), so a
# length-independent derivation must agree exactly over the shared prefix.
TD_ANALYSER_READ_DIFFLEN = """() => new Promise((resolve, reject) => {
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
      const fullLen = analyser.fftSize;
      const halfLen = Math.floor(fullLen / 2);
      const floatFull = new Float32Array(fullLen);
      analyser.getFloatTimeDomainData(floatFull);
      const floatHalf = new Float32Array(halfLen);
      analyser.getFloatTimeDomainData(floatHalf);
      resolve({
        floatFull: Array.from(floatFull),
        floatHalf: Array.from(floatHalf),
      });
      ctx.resume().catch(() => {});
    }).catch(reject);

    ctx.startRendering().catch(() => {});
  } catch (e) { reject(e); }
})
"""


def render_td_analyser_difflen(config):
    """One content_shell session: renders TD_ANALYSER_READ_DIFFLEN, returns
    (data, err). Same fault contract as render_td_analyser."""
    vals, err = lib_shell.session(config, [TD_ANALYSER_READ_DIFFLEN])
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
# (this task's six files reverted, per the CAPTURE NOTE), so these readings
# ARE the stock reference; during a normal run this binary is the patched
# one, and these are the "current, bare" readings A5/A6 compare against the
# persisted baseline. render_sum/render_analyser/render_audio_scalars are
# the SAME functions A1/A2/A4 already use above, just called here with
# config=None instead of a seed.
keys_bare, keys_bare_e = render_keys(None)
sum_bare, sum_bare_e = render_sum(None)
analyser_bare, analyser_bare_e = render_analyser(None)
scalars_bare, scalars_bare_e = render_audio_scalars(None)

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

# One content_shell process: a fresh (all-zero) buffer's getChannelData vs. a
# ramp (nonzero-signal) buffer's getChannelData, both with audio:seed=777.
data_a7, err_a7 = render_audio_zero_preserve(SEED_777)

A7 = "A7 additive-mode zero-preservation: silent buffer stays exact 0.0, non-zero signal still perturbed"

if data_a7 is None:
    results[A7] = False
    notes.append(f"A7: {type(err_a7).__name__}: {err_a7}")
else:
    silent_data = data_a7["silentData"]
    ramp_before = data_a7["rampBefore"]
    ramp_after = data_a7["rampAfter"]
    silent_ok = len(silent_data) > 0 and all(v == 0.0 for v in silent_data)
    ramp_changed = len(ramp_before) == len(ramp_after) and any(
        b != a for b, a in zip(ramp_before, ramp_after))
    results[A7] = silent_ok and ramp_changed
    nonzero_silent = [v for v in silent_data if v != 0.0]
    notes.append(f"A7 silent buffer all-zero: {silent_ok} "
                 f"({len(nonzero_silent)}/{len(silent_data)} nonzero); "
                 f"ramp signal perturbed: {ramp_changed}")
    if not silent_ok:
        notes.append(f"A7 first nonzero silent samples: {nonzero_silent[:5]}")

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

# One content_shell process: same suspend point as A2/A3, but reads
# getFloatFrequencyData at frequencyBinCount (full length), then again at
# frequencyBinCount/2 (half length), then getByteFrequencyData at
# frequencyBinCount/2 (half length).
data_a3b, err_a3b = render_analyser_difflen(SEED_777)

A3B = ("A3b different-length Float/Byte freq coherence: half-length reads "
       "agree with the full-length read's shared prefix")

if data_a3b is None:
    results[A3B] = False
    notes.append(f"A3b: {type(err_a3b).__name__}: {err_a3b}")
else:
    float_full = data_a3b["floatFull"]
    float_half = data_a3b["floatHalf"]
    byte_half = data_a3b["byteHalf"]
    min_db = data_a3b["minDecibels"]
    max_db = data_a3b["maxDecibels"]
    half_len = len(float_half)

    # Primary, RED-capable check: the full-length float read's shared
    # prefix must be EXACTLY bit-identical to the half-length float read
    # (same suspend point, same magnitude_buffer_ content -- a
    # length-independent derivation must agree exactly, no rounding
    # involved). getByteFrequencyData's 8-bit quantization (~0.27 dB per
    # step) is ~16x coarser than the ~0.017 dB max divergence the
    # length-dependent bug produces, so a byte-vs-byte or byte-vs-float
    # comparison with any tolerance loose enough to absorb normal
    # truncate-vs-round noise cannot discriminate; only the exact
    # float-vs-float comparison can. See the module docstring for the
    # measured numbers.
    float_prefix_mismatches = [
        (i, f, h) for i, (f, h) in enumerate(zip(float_full, float_half))
        if f != h
    ]
    float_prefix_ok = (
        half_len > 0 and half_len < len(float_full) and not float_prefix_mismatches
    )

    # Secondary check, kept only to exercise the byte API surface a real
    # probe would use (same formula as A3): NOT the discriminator -- see
    # above and the module docstring for why it passes on both binaries.
    scale = 1.0 if max_db == min_db else 255.0 / (max_db - min_db)
    byte_mismatches = []
    for i, (fdb, bval) in enumerate(zip(float_full, byte_half)):
        expected = round((fdb - min_db) * scale)
        expected = max(0, min(255, expected))
        if abs(expected - bval) > 1:
            byte_mismatches.append((i, fdb, bval, expected))
    byte_form_ok = (
        len(byte_half) > 0 and len(byte_half) < len(float_full) and not byte_mismatches
    )

    results[A3B] = float_prefix_ok and byte_form_ok
    notes.append(
        f"A3b float-prefix mismatches={len(float_prefix_mismatches)}/{half_len} "
        f"(discriminator); byte-form mismatches={len(byte_mismatches)}/{half_len} "
        f"(non-discriminating, minDecibels={min_db} maxDecibels={max_db})"
    )
    if float_prefix_mismatches:
        maxdiff = max(abs(f - h) for _, f, h in float_prefix_mismatches)
        notes.append(
            f"A3b float-prefix max |diff|={maxdiff} dB; first mismatches "
            f"(bin, full, half): {float_prefix_mismatches[:5]}"
        )
    if byte_mismatches:
        notes.append(f"A3b byte-form first mismatches (bin, floatDb, byte, "
                     f"expected): {byte_mismatches[:5]}")

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

# TD-A3b: time-domain length-independence. getFloatTimeDomainData at full
# (fftSize) and half (fftSize/2) length must agree EXACTLY over the shared
# [0, half) prefix -- proving the per-index noise is derived from a fixed
# full window (FIX C), not the caller's destination length. RED pre-fix (the
# len-window content hash differed between the two reads); GREEN after the
# full-window scratch. Same shape as the frequency A3b length check.
td_difflen, td_difflen_err = render_td_analyser_difflen(SEED_777)

TD_A3B = "TD-A3b time-domain length-independence: full/half reads agree over the shared prefix"

if td_difflen is None:
    results[TD_A3B] = False
    notes.append(f"TD-A3b: no data ({td_difflen_err})")
else:
    ff = td_difflen["floatFull"]
    fh = td_difflen["floatHalf"]
    n = len(fh)
    prefix_mismatches = [i for i in range(n) if ff[i] != fh[i]]
    results[TD_A3B] = (n > 0 and len(ff) >= n and not prefix_mismatches)
    notes.append(f"TD-A3b checked {n} prefix samples, "
                 f"mismatches={len(prefix_mismatches)}")
    if prefix_mismatches:
        notes.append(f"TD-A3b first mismatches (i, full, half): "
                     f"{[(i, ff[i], fh[i]) for i in prefix_mismatches[:5]]}")

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
# readings, then exit-code-wise this run still scores A1-TD-A3 normally --
# see the CAPTURE NOTE in the module docstring for why this must be run
# against a genuinely stock (patch-reverted) binary, and why the other eight
# criteria are expected to read FAIL during that run.
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

EXPECTED = 12

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
