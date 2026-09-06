"""Verifies the SP5b config-domain validator against a built content_shell.

Structured like verify_sp5a.py, and for the same reason: a fault in any one
session must become a FAIL line rather than a traceback that discards every
result already collected.

The behavioral RED for this slice is D-STRICT. Run this file against a
content_shell built BEFORE domain_validator was wired in: an out-of-range
latitude under CAMOU_CONFIG_STRICT is accepted, the browser STARTS, and
D-STRICT is FAIL. That flip -- start against the old binary, refuse against the
new one, same config -- is what proves the check measures something. A build
that merely fails to compile the new symbol is NOT a RED result.
"""

import json
import os
import sys

import lib_shell

# A single out-of-range coordinate. latitude 91 is a JSON integer on purpose:
# GetDoubleFrom widens an int to double, so this also exercises that the getter
# hands 91.0 to the domain check rather than dropping an int-typed value.
OUT_OF_RANGE = {"geolocation:latitude": 91}

# A valid coordinate pair: nothing for the domain check to report.
IN_RANGE = {"geolocation:latitude": 45, "geolocation:longitude": 10}

# A wrong-TYPE latitude: a string, not a number. This slice is range-only by
# design -- a type mismatch stays the getter's warning, never a domain refusal
# -- so even under strict the browser must START (GetDouble returns nullopt,
# the domain check has nothing to look at). This is the guard for that stated
# scope boundary.
WRONG_TYPE = {"geolocation:latitude": "91"}

# The substrings the per-violation log line must carry. Kept loose on the
# stringified value (NumberToString(91.0) is "91", but the assertion should not
# turn on that detail) and exact on the key and the range text a reader needs.
DOMAIN_LINE = ["camoucfg:", "geolocation:latitude", "out of range", "[-90, 90]"]

results = {}
notes = []


def failed(keys, label, exc):
    for key in keys:
        results[key] = False
    notes.append(f"{label}: {type(exc).__name__}: {exc}")


def read_stderr():
    """Guarded read of lib_shell.STDERR_LOG (truncated per session by launch)."""
    try:
        with open(lib_shell.STDERR_LOG, "rb") as handle:
            return handle.read().decode("utf-8", "replace"), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc


# --- D-STRICT: strict mode refuses to start on an out-of-range value ---
#
# Same distinction verify_sp5a.py draws: a refusal and a hang both fail to hand
# back a working browser, but only an exit counts, and only code 13
# (chrome::RESULT_CODE_UNSUPPORTED_PARAM). This is the RED gate.

D_STRICT = "D-STRICT strict + latitude=91 exits 13 and logs the domain line"

values, err = lib_shell.session(
    json.dumps(OUT_OF_RANGE), ["navigator.userAgent"], strict=True)
if err is None:
    results[D_STRICT] = False
    notes.append(
        "D-STRICT: browser started under CAMOU_CONFIG_STRICT=1 with an "
        "out-of-range latitude; expected exit 13 (this is the expected RED "
        "against a pre-domain-validator binary)")
elif "exited during startup" in str(err):
    code_text = str(err).rsplit("code ", 1)[-1]
    try:
        code = int(code_text)
    except ValueError:
        code = None
    if code != 13:
        results[D_STRICT] = False
        notes.append(f"D-STRICT: exited, but with the wrong code: {err}")
    else:
        stderr, read_err = read_stderr()
        if read_err is not None:
            failed([D_STRICT], f"stderr read from {lib_shell.STDERR_LOG}",
                   read_err)
        else:
            results[D_STRICT] = all(s in stderr for s in DOMAIN_LINE)
            if not results[D_STRICT]:
                notes.append(
                    f"D-STRICT: exited 13 but stderr lacked the domain line: "
                    f"{stderr!r}")
else:
    results[D_STRICT] = False
    notes.append(
        f"D-STRICT: not an exit-during-startup failure: "
        f"{type(err).__name__}: {err}")

# --- D-WARN: non-strict starts but says so loudly ---

D_WARN = "D-WARN non-strict + latitude=91 starts and logs the domain line"

values, err = lib_shell.session(json.dumps(OUT_OF_RANGE), ["navigator.userAgent"])
if err is not None:
    failed([D_WARN], "warn session", err)
else:
    # "starts" needs no separate check: err is None only because session()
    # reached evaluate(), which means the DevTools port answered.
    stderr, read_err = read_stderr()
    if read_err is not None:
        failed([D_WARN], f"stderr read from {lib_shell.STDERR_LOG}", read_err)
    else:
        results[D_WARN] = all(s in stderr for s in DOMAIN_LINE)
        if not results[D_WARN]:
            notes.append(f"D-WARN: stderr lacked the domain line: {stderr!r}")

# --- D-CLEAN: a valid coordinate pair is untouched (regression) ---

D_CLEAN = "D-CLEAN valid lat/long logs no camoucfg line and starts"

values, err = lib_shell.session(json.dumps(IN_RANGE), ["navigator.userAgent"])
if err is not None:
    failed([D_CLEAN], "clean session", err)
else:
    stderr, read_err = read_stderr()
    if read_err is not None:
        failed([D_CLEAN], f"stderr read from {lib_shell.STDERR_LOG}", read_err)
    else:
        results[D_CLEAN] = "camoucfg:" not in stderr
        if not results[D_CLEAN]:
            notes.append(f"D-CLEAN: unexpected camoucfg line: {stderr!r}")

# --- D-TYPE: a wrong-typed value is NOT a domain refusal (scope boundary) ---
#
# strict=True is the discriminating part: if the slice ever overreached into
# type-rejection, this config would refuse startup and err would be non-None.
# It must start, must not carry an "out of range" line, and must carry the
# getter's own type warning (proving the value was seen and handled as a type
# question, not silently dropped).

D_TYPE = "D-TYPE strict + string latitude starts, warns type, not 'out of range'"

values, err = lib_shell.session(
    json.dumps(WRONG_TYPE), ["navigator.userAgent"], strict=True)
if err is not None:
    results[D_TYPE] = False
    notes.append(
        f"D-TYPE: browser did not start under strict with a wrong-typed "
        f"latitude; a type mismatch must never refuse startup: {err}")
else:
    stderr, read_err = read_stderr()
    if read_err is not None:
        failed([D_TYPE], f"stderr read from {lib_shell.STDERR_LOG}", read_err)
    else:
        results[D_TYPE] = (
            "is not a number" in stderr and "out of range" not in stderr)
        if not results[D_TYPE]:
            notes.append(f"D-TYPE: unexpected stderr: {stderr!r}")

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)
