"""Verifies audio-ii Slice 3: ScriptProcessorNode.onaudioprocess input masking.

sp4-audio noises AudioBuffer.getChannelData with a ONE-SHOT did_camou_noise_
guard. ScriptProcessorNode reuses ONE external_input_buffer_ AudioBuffer across
every onaudioprocess callback, so the one-shot fires on callback 1 only --
callbacks 2+ hand JS the RAW rendered samples (measured: verify's own S1 is RED
against the pre-fix binary, cb2 stock==777). The fix adds
AudioBuffer::CamouNoiseNow() (unconditional perturb + set guard) and calls it
every callback, after the backing->external copy, from DispatchEvent
(CHECK(IsMainThread()), so heap alloc is fine there).

  S1 (RED discriminator): with audio:seed=777, callbacks 2 AND 3 differ from
     stock (config None). cb1 is NOT a discriminator -- CamouNoiseNow reproduces
     the exact field the one-shot already produced (same content, same
     "audio-buffer-c" domain), so cb1 is byte-identical pre/post fix. cb2/cb3
     are the leak the fix closes.
  S2 (determinism): audio:seed=777 across two SEPARATE content_shell processes
     gives byte-identical cb1/cb2/cb3 (content-keyed noise, pure function of
     seed+content); audio:seed=888 diverges at cb2 (seed actually perturbs).
  S3 (gating): config {} (no audio:seed) gives cb1/cb2/cb3 byte-identical to a
     bare config-None run -- the mask is gated on config, absent => raw.
  S4 (zero-preservation): audio:seed=777 with NO source connected to the node
     (silent input) -- every sample of every callback is exactly 0.0
     (additive-zero preservation on the new call site; silence must not become
     a "this browser tampers with audio" tell).

Driven over content_shell CDP via lib_shell.session, same shape as
verify_sp4_audio.py. ScriptProcessorNode DOES fire in OfflineAudioContext here
(measured). AudioWorklet does NOT (audioWorklet.addModule never resolves
headless -- worklet thread never starts), so the worklet-input residual is
documented, not shipped -- see the measurement doc.
"""
import json
import os
import sys

import lib_shell

SEED777 = json.dumps({"audio:seed": 777})
SEED888 = json.dumps({"audio:seed": 888})
EMPTY = json.dumps({})

# OfflineAudioContext, OscillatorNode -> ScriptProcessorNode(4096) ->
# destination. Captures the first 4 onaudioprocess callbacks' input channel
# (first 64 samples each). 2s @ 44100 / 4096 ~= 21 callbacks, so 1..3 exist.
def render_js(silent):
    connect = "" if silent else "osc.connect(sp);"
    return (r"""() => new Promise((resolve, reject) => {
      try {
        const ctx = new OfflineAudioContext(1, 44100 * 2, 44100);
        const osc = ctx.createOscillator();
        osc.type = 'sine'; osc.frequency.value = 1000;
        const sp = ctx.createScriptProcessor(4096, 1, 1);
        const cbs = [];
        sp.onaudioprocess = (e) => {
          if (cbs.length < 4)
            cbs.push(Array.from(e.inputBuffer.getChannelData(0).slice(0, 64)));
        };
        %s
        sp.connect(ctx.destination);
        osc.start(0);
        ctx.startRendering().then(() => setTimeout(() => resolve(cbs), 60))
                            .catch(e => reject(String(e)));
      } catch (e) { reject(String(e)); }
    })""" % connect)

def render(config, silent=False):
    vals, err = lib_shell.session(config, [render_js(silent)])
    if err is not None or vals is None:
        return None, err
    return vals[0], None

results = {}
notes = []

# Runs shared across criteria.
stock, e_stock = render(None)
s777a, e777a = render(SEED777)
s777b, e777b = render(SEED777)
s888, e888 = render(SEED888)
empty, e_empty = render(EMPTY)
silent777, e_silent = render(SEED777, silent=True)

S1 = "S1 ScriptProcessor callbacks 2+ masked: cb2 AND cb3 differ from stock under audio:seed"
if stock is None or s777a is None:
    results[S1] = False
    notes.append(f"S1: render error stock={e_stock} 777a={e777a}")
elif len(stock) < 3 or len(s777a) < 3:
    results[S1] = False
    notes.append(f"S1: too few callbacks stock={len(stock)} 777a={len(s777a)}")
else:
    cb2_masked = stock[1] != s777a[1]
    cb3_masked = stock[2] != s777a[2]
    results[S1] = cb2_masked and cb3_masked
    notes.append(f"S1 cb2 stock!=777:{cb2_masked} cb3 stock!=777:{cb3_masked}; "
                 f"cb1 stock!=777:{stock[0] != s777a[0]} (not a discriminator); "
                 f"callbacks={len(stock)}")

S2 = "S2 determinism: audio:seed=777 reproduces across processes, audio:seed=888 diverges"
if s777a is None or s777b is None or s888 is None:
    results[S2] = False
    notes.append(f"S2: render error 777a={e777a} 777b={e777b} 888={e888}")
elif min(len(s777a), len(s777b), len(s888)) < 3:
    results[S2] = False
    notes.append("S2: too few callbacks")
else:
    stable = s777a[0] == s777b[0] and s777a[1] == s777b[1] and s777a[2] == s777b[2]
    differs = s777a[1] != s888[1]
    results[S2] = stable and differs
    notes.append(f"S2 777 cross-process stable(cb1,2,3):{stable}; "
                 f"777 vs 888 cb2 differs:{differs}")

S3 = "S3 gating: config {} (no audio:seed) is byte-identical to bare config-None"
if empty is None or stock is None:
    results[S3] = False
    notes.append(f"S3: render error empty={e_empty} stock={e_stock}")
elif min(len(empty), len(stock)) < 3:
    results[S3] = False
    notes.append("S3: too few callbacks")
else:
    same = all(empty[i] == stock[i] for i in range(3))
    results[S3] = same
    notes.append(f"S3 empty==None (cb1,2,3): {same}")

S4 = "S4 zero-preservation: silent input stays exactly 0.0 in every callback under seed"
if silent777 is None:
    results[S4] = False
    notes.append(f"S4: render error {e_silent}")
elif len(silent777) < 3:
    results[S4] = False
    notes.append(f"S4: too few callbacks ({len(silent777)})")
else:
    all_zero = all(all(v == 0.0 for v in cb) for cb in silent777[:3])
    results[S4] = all_zero
    nonzero = sum(1 for cb in silent777[:3] for v in cb if v != 0.0)
    notes.append(f"S4 silent all-zero(cb1,2,3): {all_zero} ({nonzero} nonzero samples)")

EXPECTED = 4
for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
if len(results) != EXPECTED:
    notes.append(f"expected {EXPECTED} criteria, found {len(results)}")
for note in notes:
    print(f"      {note}")
if results and len(results) == EXPECTED and all(results.values()):
    print("ALL_PASS")
    sys.exit(0)
print("FAIL")
sys.exit(1)
