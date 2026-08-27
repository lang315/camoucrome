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
    # Guarded like every other fault path here. This was the one exception,
    # and an unreadable log would have exited by traceback before the print
    # loop, discarding the assertions already collected -- the exact collapse
    # this file's structure exists to prevent.
    #
    # Reading the log is sound because lib_shell.launch() opens it "wb", which
    # truncates: each session sees only its own stderr. Verified empirically
    # as well as by reading -- a warning written by one session is gone after
    # the next. Without that, stale text from an earlier run could satisfy the
    # substring check and turn this assertion into a false pass.
    try:
        with open(lib_shell.STDERR_LOG, "rb") as handle:
            stderr = handle.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        failed(["1 navigator.userAgent is refused, not half-honoured"],
               f"stderr read from {lib_shell.STDERR_LOG}", exc)
    else:
        results["1 navigator.userAgent is refused, not half-honoured"] = (
            "1.2.3.4" not in refused[0]
            and (baseline is not None and refused[0] == baseline["user_agent"])
            and "ua:osInfo" in stderr)

# --- Criteria 7 and 8: nothing changed when nothing was asked for ---
#
# Both spoofed and unconfigured runs are checked against a baseline captured
# from the binary BEFORE this patch existed. Comparing the two runs against
# each other would not catch a substitution that fires unconditionally,
# because both runs execute the same modified code.

# Imported, not redefined. An earlier draft of this step declared its own
# HIGH_ENTROPY asking for five hints while capture_ua_baseline.py asked for
# seven. getHighEntropyValues returns the requested hints plus the three
# low-entropy ones, so the baseline holds ten keys and a five-hint request
# returns eight -- and the assertion below compares them with ==, so it could
# only ever fail. A guaranteed false red, from two copies of one list drifting.
#
# So the list lives in lib_shell, where the capture and every verification
# read the same object and cannot disagree. Move both constants there in this
# step and update capture_ua_baseline.py to import them; do not leave a second
# copy behind.
from lib_shell import ACCEPT_CH, HIGH_ENTROPY

C78 = ["7 no property was added to navigator or window",
       "8 unconfigured userAgentData matches the baseline",
       "8 unconfigured high-entropy values match the baseline",
       "8 unconfigured request headers match the baseline"]

# Guarded like every other external interaction here. The bind is to port 0
# so the kernel picks it and a clash is near impossible -- but "near
# impossible" is not the standard this file holds itself to. Its whole point
# is that no single fault discards results already collected, and start() was
# the one call outside a guard. capture_ua_baseline.py leaves it bare on
# purpose: that script exits 1 on any failure by design. This one must not.
try:
    base_url, headers_for, stop = echo_server.start(ACCEPT_CH)
except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
    failed(C78, "echo_server.start", exc)
    base_url = headers_for = stop = None

try:
    values, err = (None, RuntimeError("listener never started")) \
        if base_url is None else lib_shell.session(
        None,
        ["navigator.userAgentData.platform",
         "navigator.userAgentData.mobile",
         "JSON.stringify(navigator.userAgentData.brands)",
         HIGH_ENTROPY,
         "Object.keys(navigator).sort().join(',')",
         "Object.keys(window).sort().join(',')",
         "Object.getOwnPropertyNames(Navigator.prototype).sort().join(',')"],
        navigate_to=base_url)
    wire = headers_for("/probe.js") if err is None and headers_for else None
finally:
    if stop is not None:
        stop()

if err is not None and base_url is not None:
    failed(C78, "no-config session", err)
elif baseline_err is not None:
    failed(C78, f"baseline load from {BASELINE}", baseline_err)
else:
    (platform, mobile, brands_json, entropy,
     nav_keys, win_keys, proto_props) = values
    results["7 no property was added to navigator or window"] = (
        nav_keys.split(",") == baseline["navigator_keys"]
        and win_keys.split(",") == baseline["window_keys"]
        and proto_props.split(",") == baseline["navigator_prototype_props"])
    results["8 unconfigured userAgentData matches the baseline"] = (
        platform == baseline["platform"]
        and mobile == baseline["mobile"]
        and json.loads(brands_json) == baseline["brands"])
    results["8 unconfigured high-entropy values match the baseline"] = (
        entropy == baseline["high_entropy"])
    if wire is None:
        failed(["8 unconfigured request headers match the baseline"],
               "wire headers",
               RuntimeError("the subresource request was never observed"))
    else:
        observed = {k.lower(): v for k, v in wire.items()
                    if k.lower().startswith("sec-ch-ua")
                    or k.lower() == "user-agent"}
        results["8 unconfigured request headers match the baseline"] = (
            observed == baseline["request_headers"])

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)
