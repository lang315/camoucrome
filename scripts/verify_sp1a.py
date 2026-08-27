"""Verifies the SP1a acceptance criteria against a built content_shell.

Structured like verify_sp0.py, and for the reasons its docstrings give: a
fault in any one session must become FAIL lines rather than a traceback that
discards every result already collected. An intermittently green verification
is worse than a slow one -- it teaches people to re-run until it passes, and
then it measures nothing.
"""

import json
import os
import sys

import echo_server
import lib_shell

BASELINE = os.path.expanduser(
    "~/camoucrome-verify/baselines/content_shell-sp0-stock-ua.json")

# Windows 11 x64, en-US. Carries no version field of any kind: the reported
# Chromium version is always this build's own.
#
# The osInfo value is byte-identical to the literal in GetUnifiedPlatform()'s
# own BUILDFLAG(IS_WIN) arm, which a Linux build compiles out. Taking it from
# Chromium's own source rather than from a captured string means the claim
# matches what a real Chrome on Windows emits by construction.
WIN = {
    "ua:osInfo": "Windows NT 10.0; Win64; x64",
    "ua:platform": "Windows",
    "ua:platformVersion": "15.0.0",
    "ua:architecture": "x86",
    "ua:bitness": "64",
    "ua:mobile": False,
    "ua:wow64": False,
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
    # Every key any assertion reads. Task 6 reads "mobile" and
    # "navigator_prototype_props", so a baseline missing either must become
    # FAIL lines here rather than a KeyError three hundred lines later.
    missing = [k for k in ("user_agent", "brands", "platform", "mobile",
                           "high_entropy", "navigator_prototype_props",
                           "navigator_keys", "window_keys", "request_headers")
               if k not in data]
    if missing:
        return None, KeyError(f"baseline lacks {', '.join(missing)}")
    return data, None


baseline, baseline_err = load_baseline(BASELINE)


def build_version():
    """The Chromium version this binary was compiled from.

    Read from the stock user agent in the baseline rather than from
    chrome/VERSION: the baseline came out of this exact binary, while the
    source tree can have moved.
    """
    if baseline is None:
        return None
    # ".../Chrome/141.0.7390.54 Safari/..." -> "141.0.7390.54"
    for token in baseline["user_agent"].split():
        if token.startswith("Chrome/"):
            return token.split("/", 1)[1]
    return None


REAL_VERSION = build_version()

# --- Criterion 1: the OS token moves, the version does not ---

C1 = ["1 spoofed UA carries the Windows OS token",
      "1 spoofed UA carries no Linux token",
      "1 spoofed UA reports the build's own version",
      "1 unconfigured UA is byte-identical to the baseline",
      "1 navigator.userAgent is refused, not half-honoured"]

spoofed, err = lib_shell.session(json.dumps(WIN), ["navigator.userAgent"])
if err is not None:
    failed(C1[:3], "spoofed session", err)
else:
    ua = spoofed[0]
    results["1 spoofed UA carries the Windows OS token"] = (
        "Windows NT 10.0; Win64; x64" in ua)
    results["1 spoofed UA carries no Linux token"] = (
        "Linux" not in ua and "X11" not in ua)
    # Note on what this asserts, since the name reads bigger than the claim.
    # content_shell's UA reports Chrome/999.0.0.0 -- its own fake version, not
    # this checkout's Chromium milestone. REAL_VERSION comes from the baseline,
    # so it is 999.0.0.0 here, and the assertion is version INVARIANCE: whatever
    # the binary reported before the patch, it must still report. That is the
    # invariant SP1a needs, and it holds in either binary. Task 8, against
    # chrome, is where the number is also the true milestone.
    results["1 spoofed UA reports the build's own version"] = (
        REAL_VERSION is not None and f"Chrome/{REAL_VERSION}" in ua)

stock, err = lib_shell.session(None, ["navigator.userAgent"])
if err is not None:
    failed(["1 unconfigured UA is byte-identical to the baseline"],
           "unconfigured session", err)
elif baseline_err is not None:
    failed(["1 unconfigured UA is byte-identical to the baseline"],
           f"baseline load from {BASELINE}", baseline_err)
else:
    results["1 unconfigured UA is byte-identical to the baseline"] = (
        stock[0] == baseline["user_agent"])

# A whole user-agent string carries a version. Honouring it would mean either
# emitting a version this binary contradicts or parsing the string to extract
# the OS segment, and SP1 forbids both. So it must be ignored -- and it must
# say so, because silently producing an unspoofed UA from a config that
# plainly asked for a spoofed one is the kind of failure people lose a day to.
refused, err = lib_shell.session(
    json.dumps({"navigator.userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64;"
                                       " x64) Chrome/1.2.3.4 Safari/537.36"}),
    ["navigator.userAgent"])
if err is not None:
    failed(["1 navigator.userAgent is refused, not half-honoured"],
           "refusal session", err)
else:
    with open(lib_shell.STDERR_LOG, "rb") as handle:
        stderr = handle.read().decode("utf-8", "replace")
    results["1 navigator.userAgent is refused, not half-honoured"] = (
        "1.2.3.4" not in refused[0]
        and (baseline is not None and refused[0] == baseline["user_agent"])
        and "ua:osInfo" in stderr)

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)
