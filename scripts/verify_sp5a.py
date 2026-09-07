"""Verifies the SP5a acceptance criteria against a built content_shell.

Structured like verify_sp1a.py, and for the reasons its docstring gives: a
fault in any one session must become FAIL lines rather than a traceback that
discards every result already collected. An intermittently green verification
is worse than a slow one -- it teaches people to re-run until it passes, and
then it measures nothing.
"""

import json
import os
import sys

import lib_shell

BASELINE = os.path.expanduser(
    "~/camoucrome-verify/baselines/content_shell-sp0-stock-ua.json")

# Coherent: ua:osInfo Windows with ua:platform "Windows" -- the invariant
# ua-os-family-agrees is satisfied, so ValidateAtStartup() has nothing to
# report.
COHERENT = {
    "ua:osInfo": "Windows NT 10.0; Win64; x64",
    "ua:platform": "Windows",
}

# Incoherent: same ua:osInfo, ua:platform disagrees. ua:osInfo is the
# authoritative key (invariants.h's keys[0]) and ua:platform is the repaired
# key (keys[1]) -- the one the invariant's log line names as wrong.
INCOHERENT = {
    "ua:osInfo": "Windows NT 10.0; Win64; x64",
    "ua:platform": "Linux",
}

results = {}
notes = []


def failed(keys, label, exc):
    for key in keys:
        results[key] = False
    notes.append(f"{label}: {type(exc).__name__}: {exc}")


def load_baseline(path):
    try:
        with open(path) as handle:
            data = json.load(handle)
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    if "user_agent" not in data:
        return None, KeyError("baseline lacks user_agent")
    return data, None


def read_stderr():
    """Guarded read of lib_shell.STDERR_LOG.

    launch() opens the log "wb", which truncates -- each session's read sees
    only that session's own stderr (verify_sp1a.py relies on the same fact).
    Guarded like every other external read in this file: an unreadable log
    must become a FAIL line, not a traceback that discards results already
    collected.
    """
    try:
        with open(lib_shell.STDERR_LOG, "rb") as handle:
            return handle.read().decode("utf-8", "replace"), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc


baseline, baseline_err = load_baseline(BASELINE)

# --- Assertion 1: a coherent configuration is untouched ---

C1 = "1 coherent config produces a Windows UA and logs no camoucfg: line at all"

values, err = lib_shell.session(json.dumps(COHERENT), ["navigator.userAgent"])
if err is not None:
    failed([C1], "coherent session", err)
else:
    stderr, read_err = read_stderr()
    if read_err is not None:
        failed([C1], f"stderr read from {lib_shell.STDERR_LOG}", read_err)
    else:
        results[C1] = (
            "Windows NT 10.0; Win64; x64" in values[0]
            and "camoucfg:" not in stderr)

# --- Assertion 2: an incoherent configuration is detected and says so ---

C2 = "2 incoherent config logs ua-os-family-agrees naming ua:platform, and starts"

values, err = lib_shell.session(json.dumps(INCOHERENT), ["navigator.userAgent"])
if err is not None:
    failed([C2], "incoherent session", err)
else:
    stderr, read_err = read_stderr()
    if read_err is not None:
        failed([C2], f"stderr read from {lib_shell.STDERR_LOG}", read_err)
    else:
        # "starts" needs no separate check: err is None here only because
        # session() reached evaluate() successfully, which means launch()
        # returned a proc whose DevTools port answered.
        results[C2] = (
            "camoucfg: invariant 'ua-os-family-agrees' violated. "
            "'ua:platform' is 'Linux', which disagrees with 'ua:osInfo'. "
            "It should be 'Windows'." in stderr)

# --- Assertion 3: strict mode refuses to start ---
#
# A refusal and a hang look identical to a naive check -- both fail to hand
# back a working browser -- and a hang would mean the browser is unusable
# rather than fail-closed. lib_shell.launch() raises a distinct RuntimeError
# for each: "... exited during startup, code N" for the exit, "... opened no
# DevTools endpoint within 30s" for the hang. Only the first counts, and only
# with code 13 (chrome::RESULT_CODE_UNSUPPORTED_PARAM) -- a different
# nonzero code would mean the process died for some other reason.

C3 = "3 incoherent config under CAMOU_CONFIG_STRICT exits 13 before starting"

values, err = lib_shell.session(
    json.dumps(INCOHERENT), ["navigator.userAgent"], strict=True)
if err is None:
    results[C3] = False
    notes.append(
        "3: browser started (DevTools opened) under CAMOU_CONFIG_STRICT=1 "
        "with an incoherent configuration; expected exit 13")
elif "exited during startup" in str(err):
    # Parse the trailing integer rather than substring-match "code 13" --
    # that substring also matches code 130, 131, ..., 139, 1300, etc.
    code_text = str(err).rsplit("code ", 1)[-1]
    try:
        code = int(code_text)
    except ValueError:
        code = None
    if code != 13:
        results[C3] = False
        notes.append(f"3: exited, but with the wrong code: {err}")
    else:
        stderr, read_err = read_stderr()
        if read_err is not None:
            failed([C3], f"stderr read from {lib_shell.STDERR_LOG}", read_err)
        else:
            results[C3] = (
                "camoucfg: configuration is incoherent and "
                "CAMOU_CONFIG_STRICT is set; refusing to start." in stderr)
            if not results[C3]:
                notes.append(
                    f"3: exited 13 but stderr lacked the refusal message: "
                    f"{stderr!r}")
else:
    # Includes the hang timeout and any other fault. A hang must not pass as
    # a refusal -- it means the browser is unusable, not fail-closed.
    results[C3] = False
    notes.append(
        f"3: not an exit-during-startup failure: {type(err).__name__}: {err}")

# --- Assertion 4: no config is still silent ---

C4 = "4 unconfigured session logs no camoucfg line and UA matches the baseline"

values, err = lib_shell.session(None, ["navigator.userAgent"])
if err is not None:
    failed([C4], "unconfigured session", err)
elif baseline_err is not None:
    failed([C4], f"baseline load from {BASELINE}", baseline_err)
else:
    stderr, read_err = read_stderr()
    if read_err is not None:
        failed([C4], f"stderr read from {lib_shell.STDERR_LOG}", read_err)
    else:
        results[C4] = (
            "camoucfg:" not in stderr
            and values[0] == baseline["user_agent"])

# --- Assertion 5: a non-UA relation travels the same browser-process path ---
#
# The registry gained a numeric fits-within relation (screen geometry). C1-C4
# only exercise the UA relation; nothing here would notice if ValidateAtStartup
# -> browser_main_loop's LOG path handled kSameOsFamily but not kFitsWithin.
# availWidth > width is the violation. The full log line is matched, as C2 does
# for UA, because it pins base::NumberToString's formatting of old/new values --
# the one thing the unit test, which checks the repaired KEY not the message,
# cannot see (a stray "2560.000000" would pass every unit case).

GEO_INCOHERENT = {"screen.width": 1920, "screen.availWidth": 2560}

C5 = "5 incoherent geometry logs screen-avail-width-fits naming availWidth, and starts"

values, err = lib_shell.session(
    json.dumps(GEO_INCOHERENT), ["navigator.userAgent"])
if err is not None:
    failed([C5], "geometry session", err)
else:
    stderr, read_err = read_stderr()
    if read_err is not None:
        failed([C5], f"stderr read from {lib_shell.STDERR_LOG}", read_err)
    else:
        results[C5] = (
            "camoucfg: invariant 'screen-avail-width-fits' violated. "
            "'screen.availWidth' is '2560', which disagrees with "
            "'screen.width'. It should be '1920'." in stderr)

# --- Assertion 6: geometry incoherence refuses under strict mode too ---
#
# The refusal is invariant-agnostic (the deferred refusal at the bottom of the
# diagnostic block), so this proves kFitsWithin reaches it, not a second code
# path. Same exit-13 discrimination as C3.

C6 = "6 incoherent geometry under CAMOU_CONFIG_STRICT exits 13 before starting"

values, err = lib_shell.session(
    json.dumps(GEO_INCOHERENT), ["navigator.userAgent"], strict=True)
if err is None:
    results[C6] = False
    notes.append(
        "6: browser started under CAMOU_CONFIG_STRICT=1 with an incoherent "
        "geometry configuration; expected exit 13")
elif "exited during startup" in str(err):
    code_text = str(err).rsplit("code ", 1)[-1]
    try:
        code = int(code_text)
    except ValueError:
        code = None
    if code != 13:
        results[C6] = False
        notes.append(f"6: exited, but with the wrong code: {err}")
    else:
        stderr, read_err = read_stderr()
        if read_err is not None:
            failed([C6], f"stderr read from {lib_shell.STDERR_LOG}", read_err)
        else:
            results[C6] = (
                "camoucfg: configuration is incoherent and "
                "CAMOU_CONFIG_STRICT is set; refusing to start." in stderr)
            if not results[C6]:
                notes.append(
                    f"6: exited 13 but stderr lacked the refusal message: "
                    f"{stderr!r}")
else:
    results[C6] = False
    notes.append(
        f"6: not an exit-during-startup failure: {type(err).__name__}: {err}")

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)
