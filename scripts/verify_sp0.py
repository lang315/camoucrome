"""Verifies the six SP0 acceptance criteria against a built content_shell."""

import json
import os
import sys

from lib_shell import SHELL, STDERR_LOG, launch, shutdown, evaluate, session

WORKER_PROBE = """
() => new Promise(resolve => {
  const src = 'self.postMessage(navigator.hardwareConcurrency)';
  const url = URL.createObjectURL(new Blob([src], {type: 'text/javascript'}));
  const w = new Worker(url);
  w.onmessage = e => resolve(e.data);
})
"""

# Reads the descriptor defensively: a getter demoted to a data property has
# no .get, and calling .toString() on undefined would throw inside the page
# rather than reporting a failure here.
DESCRIPTOR_PROBE = """
() => {
  const d = Object.getOwnPropertyDescriptor(
      Navigator.prototype, 'hardwareConcurrency');
  return d && d.get ? d.get.toString() : `no getter: ${JSON.stringify(d)}`;
}
"""

# Every read must happen while its own content_shell is still alive. Each
# evaluate() opens a fresh CDP connection, so anything asked for after
# shutdown() fails before a single result is printed.
PROTO_PROBE = "Object.getOwnPropertyNames(Navigator.prototype).sort().join(',')"
KEYS_PROBE = "Object.keys(window).sort().join(',')"

BASELINE = os.path.expanduser(
    "~/camoucrome-verify/baselines/content_shell-0e8d4a9268-stock.json")


def load_baseline(path):
    """Loads the recorded pre-spoof surface; returns (data, error).

    Guarded for the same reason session() is. This load used to sit bare at
    module level, so a missing or malformed baseline produced a traceback
    and zero PASS/FAIL lines -- the exact collapse session() exists to
    prevent, on the one path it did not cover, and on the file the most
    important assertion here depends on.
    """
    try:
        with open(path) as handle:
            data = json.load(handle)
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    missing = [k for k in ("window_keys", "navigator_prototype_props",
                           "hardware_concurrency") if k not in data]
    if missing:
        return None, KeyError(f"baseline lacks {', '.join(missing)}")
    return data, None


baseline, baseline_err = load_baseline(BASELINE)
# The real processor count comes from the baseline rather than a literal, so
# this runs on a machine with a different core count without failing for a
# reason nothing in the script explains.
REAL = baseline["hardware_concurrency"] if baseline else None

results = {}
notes = []


def failed(keys, label, exc):
    for key in keys:
        results[key] = False
    notes.append(f"{label}: {type(exc).__name__}: {exc}")


# Criteria 2, 4 and 5: spoofed value, native accessor, worker parity.
SPOOFED_KEYS = ["2 spoofed value is 8",
                "4 accessor reports [native code] when spoofed",
                "5 worker agrees when spoofed"]
spoofed, err = session('{"navigator.hardwareConcurrency":8}',
                       ["navigator.hardwareConcurrency", WORKER_PROBE,
                        DESCRIPTOR_PROBE, KEYS_PROBE, PROTO_PROBE])
if err is not None:
    failed(SPOOFED_KEYS + ["4 window keys match the pre-spoof baseline",
                           "4 Navigator prototype unchanged"],
           "spoofed session", err)
    spoofed_keys = spoofed_proto = None
else:
    window_value, worker_value, descriptor, spoofed_keys, spoofed_proto = spoofed
    results["2 spoofed value is 8"] = window_value == 8
    results["5 worker agrees when spoofed"] = worker_value == 8
    results["4 accessor reports [native code] when spoofed"] = (
        "[native code]" in descriptor)

# Criteria 3, 4 and 5 without configuration.
STOCK_KEYS = ["3 falls back to the real processor count",
              "4 accessor reports [native code] when unconfigured",
              "5 worker agrees when unconfigured"]
stock, err = session(None,
                     ["navigator.hardwareConcurrency", WORKER_PROBE,
                      DESCRIPTOR_PROBE, KEYS_PROBE, PROTO_PROBE])
if err is not None:
    failed(STOCK_KEYS, "unconfigured session", err)
    stock_keys = stock_proto = None
else:
    real_window, real_worker, descriptor, stock_keys, stock_proto = stock
    results["3 falls back to the real processor count"] = (
        REAL is not None and real_window == REAL)
    results["5 worker agrees when unconfigured"] = real_worker == real_window
    results["4 accessor reports [native code] when unconfigured"] = (
        "[native code]" in descriptor)

# Criterion 4: no property was added or removed, measured against the binary
# as it was BEFORE any Camoucrome call site was wired in. Comparing the
# spoofed run against the unconfigured run would not catch a property this
# change adds unconditionally, because both runs execute the same modified
# code. Both runs are checked against the baseline for that reason.
if baseline_err is not None:
    failed(["4 window keys match the pre-spoof baseline",
            "4 Navigator prototype unchanged"],
           f"baseline load from {BASELINE}", baseline_err)
elif spoofed_keys is not None and stock_keys is not None:
    results["4 window keys match the pre-spoof baseline"] = (
        spoofed_keys.split(",") == baseline["window_keys"]
        and stock_keys.split(",") == baseline["window_keys"])
    results["4 Navigator prototype unchanged"] = (
        spoofed_proto.split(",") == baseline["navigator_prototype_props"]
        and stock_proto.split(",") == baseline["navigator_prototype_props"])

# Criterion 6: malformed configuration does not crash and reports the truth.
# The non-crash claim gets its own named assertion. Without one, the failure
# it describes would arrive as an uncaught traceback rather than a FAIL, and
# the spec is explicit that a crash on bad input is itself a fingerprint.
MALFORMED_KEYS = ["6 malformed config does not crash the browser",
                  "6 malformed config reports the real processor count",
                  "6 malformed config logs an error"]
bad, err = session("{not json", ["navigator.hardwareConcurrency"])
if err is not None:
    failed(MALFORMED_KEYS, "malformed-config session", err)
else:
    results["6 malformed config does not crash the browser"] = True
    with open(STDERR_LOG, "rb") as f:
        stderr = f.read().decode("utf-8", "replace")
    results["6 malformed config reports the real processor count"] = (
        REAL is not None and bad[0] == REAL)
    # Substring match against the implementation's own wording. Direction of
    # failure is a false FAIL, never a false PASS, but a later rename of the
    # log tag would need this updated with it.
    results["6 malformed config logs an error"] = "camoucfg" in stderr

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)
