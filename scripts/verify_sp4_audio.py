"""Verifies the SP4-audio Task 2 AudioBuffer readback noise: with audio:seed
configured, samples read back via AudioBuffer.getChannelData carry
deterministic, seed-derived noise -- a reread of the same rendered buffer
reproduces exactly, and a different seed diverges.

One criterion, driven with Playwright's sync API over content_shell's CDP via
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

EXPECTED = 1

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
