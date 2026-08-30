"""Verifies the SP3a snapshot-readback hook: with canvas:seed set, the pixels
that leave a canvas through toDataURL() and toBlob() carry deterministic noise,
while an unconfigured build stays byte-identical to stock.

Four criteria, all driven with Playwright's sync API over content_shell's CDP,
the same shape as verify_sp2b.py / verify_sp1a.py -- a fault in any one session
becomes FAIL lines, never a traceback that discards results already collected:

  C1 (determinism, HIGHEST): with canvas:seed set, toDataURL() called twice in
     the same document returns byte-identical strings. A page that re-reads the
     same canvas must see the same pixels, or the noise is itself a tell.
  C2 (spoof visible): with canvas:seed set, toDataURL() differs from the same
     scene rendered by a stock run (no CAMOU_CONFIG).
  C3 (off by default): with NO canvas:seed, toDataURL() is byte-identical to the
     stock run -- proving the readback wrap does not itself alter bytes.
  C4 (toBlob agrees): toBlob() readback is deterministic across two calls and
     differs from stock, exactly as toDataURL does.

The "stock run" is a PERSISTED baseline, not a second live run of the binary
under test. Within a single edited binary a no-seed run compared against itself
is vacuous -- it would pass C3 while measuring nothing. So the stock reference
is captured once, from a STOCK content_shell (before the Blink edit exists),
into baselines/, exactly as verify_sp1a captures its stock UA. Run this script
with --capture-baseline against the stock binary FIRST; that run also prints the
criteria (C2 and C4 will FAIL on stock, since a stock seeded run == stock),
which is the required RED-first evidence. Every later run reads that frozen
baseline.
"""

import hashlib
import json
import os
import sys

from playwright.sync_api import sync_playwright

import lib_shell

CANVAS = json.dumps({"canvas:seed": 987654321})

BASELINE = os.path.expanduser(
    "~/camoucrome-verify/baselines/content_shell-sp3a-stock-canvas.json")

# A fixed, non-trivial scene: a diagonal three-stop gradient, a translucent
# circle, an opaque rectangle, and anti-aliased text. Content varies across the
# frame so the content-hash fold in PerturbRgba has real input, and the text +
# alpha exercise both a variety of pixel values and the alpha channel the noise
# must leave untouched. Drawn identically every run, so any byte difference
# between two runs is the noise, never the scene.
DRAW_AND_READ = """() => new Promise((resolve, reject) => {
  try {
    const c = document.createElement('canvas');
    c.width = 300; c.height = 200;
    const ctx = c.getContext('2d');
    const g = ctx.createLinearGradient(0, 0, 300, 200);
    g.addColorStop(0, '#ff2d00');
    g.addColorStop(0.5, '#00c853');
    g.addColorStop(1, '#1a2fff');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 300, 200);
    ctx.fillStyle = 'rgba(255,255,255,0.6)';
    ctx.beginPath();
    ctx.arc(150, 100, 55, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#123456';
    ctx.fillRect(20, 20, 90, 44);
    ctx.fillStyle = '#000000';
    ctx.font = '22px sans-serif';
    ctx.fillText('Camoucrome-SP3a', 24, 160);
    const d1 = c.toDataURL('image/png');
    const d2 = c.toDataURL('image/png');
    const toB64 = (blob) => new Promise((res, rej) => {
      const fr = new FileReader();
      fr.onload = () => res(fr.result);
      fr.onerror = () => rej(fr.error);
      fr.readAsDataURL(blob);
    });
    const asBlob = () => new Promise((res, rej) => {
      c.toBlob((b) => b ? res(b) : rej(new Error('toBlob null')), 'image/png');
    });
    (async () => {
      const b1 = await toB64(await asBlob());
      const b2 = await toB64(await asBlob());
      resolve({ d1, d2, b1, b2 });
    })().catch(reject);
  } catch (e) { reject(e); }
})
"""


def run(config):
    """One content_shell session: draw the scene, return its readbacks.

    Returns (result, err). `result` is {d1, d2, b1, b2}: two toDataURL strings
    and two FileReader data: URLs of toBlob output, in one document.
    """
    proc = None
    try:
        proc = lib_shell.launch(config)
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(
                f"http://127.0.0.1:{proc.cdp_port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("about:blank", wait_until="load")
            result = page.evaluate(DRAW_AND_READ)
        return result, None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


capture = "--capture-baseline" in sys.argv[1:]

results = {}
notes = []

C1 = "1 seeded toDataURL is deterministic across two reads"
C2 = "2 seeded toDataURL differs from the stock baseline"
C3 = "3 unconfigured toDataURL is byte-identical to the stock baseline"
C4 = "4 seeded toBlob is deterministic and differs from the stock baseline"

# Live runs on the binary under test: one unconfigured, one seeded.
stockish, stockish_err = run(None)
seeded, seeded_err = run(CANVAS)

if capture:
    # Capture the frozen stock reference from THIS (stock) binary's no-seed run.
    if stockish is None:
        notes.append(f"capture: no-seed session failed: "
                     f"{type(stockish_err).__name__}: {stockish_err}")
    else:
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        with open(BASELINE, "w") as fh:
            json.dump({"toDataURL": sha(stockish["d1"]),
                       "toBlob": sha(stockish["b1"])}, fh)
        notes.append(f"capture: wrote stock baseline to {BASELINE}")

# Load the frozen stock reference (written by an earlier --capture-baseline run
# against the stock binary). Absent -> C2/C3/C4 FAIL with a clear note, never a
# vacuous pass.
baseline = None
try:
    with open(BASELINE) as fh:
        baseline = json.load(fh)
except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
    notes.append(f"baseline load from {BASELINE}: "
                 f"{type(exc).__name__}: {exc}")

# C1: determinism -- byte-identical toDataURL across two reads in one document.
if seeded is None:
    results[C1] = False
    notes.append(f"C1 seeded session: {type(seeded_err).__name__}: {seeded_err}")
else:
    results[C1] = seeded["d1"] == seeded["d2"]
    if not results[C1]:
        notes.append("C1: the two toDataURL reads differ -- noise is not "
                     "reproducible for the same drawing")

# C2: seeded output differs from the frozen stock baseline.
if seeded is None or baseline is None:
    results[C2] = False
else:
    results[C2] = sha(seeded["d1"]) != baseline["toDataURL"]
    if not results[C2]:
        notes.append("C2: seeded toDataURL equals stock -- no visible spoof")

# C3: unconfigured output is byte-identical to the frozen stock baseline.
if stockish is None or baseline is None:
    results[C3] = False
    if stockish is None and stockish_err is not None:
        notes.append(f"C3 no-seed session: "
                     f"{type(stockish_err).__name__}: {stockish_err}")
else:
    results[C3] = sha(stockish["d1"]) == baseline["toDataURL"]
    if not results[C3]:
        notes.append("C3: unconfigured toDataURL differs from stock -- the "
                     "readback wrap altered bytes when noise is off")

# C4: toBlob deterministic across two reads AND differs from stock.
if seeded is None or baseline is None:
    results[C4] = False
else:
    deterministic = seeded["b1"] == seeded["b2"]
    differs = sha(seeded["b1"]) != baseline["toBlob"]
    results[C4] = deterministic and differs
    if not deterministic:
        notes.append("C4: the two toBlob reads differ -- noise not reproducible")
    elif not differs:
        notes.append("C4: seeded toBlob equals stock -- no visible spoof")

EXPECTED = 4

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")

if len(results) != EXPECTED:
    notes.append(
        f"expected {EXPECTED} criteria in `results`, found {len(results)}: "
        "a criterion was added or removed without updating EXPECTED")

for note in notes:
    print(f"      {note}")

if results and len(results) == EXPECTED and all(results.values()):
    print("ALL_PASS")
    sys.exit(0)
print("FAIL")
sys.exit(1)
