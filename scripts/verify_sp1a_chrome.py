"""Verifies SP1a's central claim against `chrome`: one producer, three channels.

verify_sp1a.py runs against content_shell, which can only reach criterion 1.
content_shell builds its own UserAgentMetadata instead of calling the patched
producer, and wires no ClientHintsControllerDelegate, so criteria 2, 3 and 4
have no surface to test there. `chrome` calls
embedder_support::GetUserAgentMetadata() and has a real delegate -- confirmed
by the baseline capture, which returned platform 'Linux' and all nine hints.

Criterion 4 is the one that matters and the reason the other two are not
enough. Each of them checks a channel against the CONFIG, so a patch that was
bypassed on one path could still satisfy both if the bypassed path happened to
produce a plausible value. Criterion 4 checks the channels against EACH OTHER,
in a single session, which is the only formulation that fails when one path
skips the producer.

Structured like verify_sp1a.py, for the reasons its docstring gives: any fault
becomes FAIL lines rather than a traceback that discards results already
collected.
"""

import json
import os
import sys

import echo_server
import lib_shell
from lib_shell import ACCEPT_CH, HIGH_ENTROPY

BASELINE = os.path.expanduser(
    "~/camoucrome-verify/baselines/chrome-0e8d4a9268-stock-ua.json")

# Identical to verify_sp1a.py's. Kept in step by hand rather than imported:
# importing it would execute that file, which runs its own browser sessions.
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
    missing = [k for k in ("user_agent", "brands", "platform", "mobile",
                           "high_entropy", "request_headers")
               if k not in data]
    if missing:
        return None, KeyError(f"baseline lacks {', '.join(missing)}")
    return data, None


baseline, baseline_err = load_baseline(BASELINE)


def product_token(ua):
    """The 'Chrome/<version>' token, whatever prefix it carries.

    NOT startswith("Chrome/"), which is what verify_sp1a.py uses and what this
    file used first. Under --headless the token is HeadlessChrome/154.0.0.0 --
    user_agent_utils.cc:218 does product.insert(0, "Headless") -- so a prefix
    match returns None here and the version assertion fails for a reason that
    has nothing to do with the version. An `in` test reads both forms.
    """
    for token in ua.split():
        if "Chrome/" in token:
            return token
    return None


# The UA string carries the OS as a free-form segment while userAgentData
# carries a UA-CH token, so "these agree" cannot be string equality. It is a
# mapping, and it has to be written out.
#
# An earlier form of the criterion-4 check read
#     ua_platform != "Windows" or "Windows NT" in ua
# which is true for every value of ua_platform that is not "Windows" -- so it
# asserted nothing at all outside the one case under test. It was found by
# trying to design a mutation that would break it and discovering none could:
# a config naming Windows in ua:osInfo and Linux in ua:platform leaves
# channels 2 and 3 agreeing with each other, and the old clause exempted the
# UA string. That configuration is incoherent, SP5a's "ua-os-family-agrees"
# entry owns rejecting it, and this file must still notice when it is served.
UA_TOKEN_FOR_PLATFORM = {
    "Windows": "Windows NT",
    "macOS": "Macintosh",
    "Linux": "X11; Linux",
    "Android": "Android",
    "Chrome OS": "CrOS",
    "Chromium OS": "CrOS",
}


def ua_carries_platform(ua, platform):
    """Whether the UA string's OS segment matches the UA-CH platform token.

    An unmapped platform is a FAIL, not a pass. A verification that silently
    waves through the values it does not recognise is the failure this project
    keeps finding, and the fix costs one dict entry.
    """
    token = UA_TOKEN_FOR_PLATFORM.get(platform)
    return token is not None and token in ua


def unquote(value):
    """sec-ch-ua-* values are RFC 8941 strings: "x86" -> x86."""
    return value.strip().strip('"')


def is_true(value):
    """RFC 8941 booleans: ?1 / ?0."""
    return value.strip() == "?1"


def run(config, expressions):
    """One `chrome` session with the echo server up; returns (values, headers).

    Both channels come from the SAME session by construction. Criterion 4
    compares JS values against wire headers, and reading them from two runs
    would compare two browsers -- which is not the claim, and would pass on a
    build where each run independently picked a different path.
    """
    try:
        base_url, headers_for, stop = echo_server.start(ACCEPT_CH)
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, None, exc
    try:
        values, err = lib_shell.session(
            config, expressions, navigate_to=base_url,
            shell=lib_shell.CHROME, extra_flags=lib_shell.CHROME_FLAGS)
        if err is not None:
            return None, None, err
        wire = headers_for("/probe.js")
    finally:
        stop()
    if wire is None:
        return None, None, RuntimeError(
            "the subresource request was never observed")
    return values, {k.lower(): v for k, v in wire.items()}, None


EXPRESSIONS = [
    "navigator.userAgent",
    "navigator.userAgentData.platform",
    "navigator.userAgentData.mobile",
    "JSON.stringify(navigator.userAgentData.brands)",
    HIGH_ENTROPY,
]

# --- Criterion 1, re-confirmed in the binary that actually ships ---

C1 = ["1 spoofed UA carries the Windows OS token",
      "1 spoofed UA carries no Linux token",
      "1 spoofed UA reports the build's own version",
      "1 spoofed UA leaves the product token untouched"]
C2 = ["2 userAgentData.platform follows the config",
      "2 userAgentData high-entropy values follow the config",
      "2 userAgentData.mobile follows the config"]
C3 = ["3 Sec-CH-UA-Platform follows the config",
      "3 Sec-CH-UA-Arch and -Bitness follow the config",
      "3 Sec-CH-UA-Platform-Version follows the config",
      "3 Sec-CH-UA-Mobile and -WoW64 follow the config"]
C4 = ["4 UA string, userAgentData and Sec-CH-UA agree on the platform",
      "4 userAgentData and Sec-CH-UA agree on every high-entropy value",
      "4 the UA request header is the UA string"]

spoofed, wire, err = run(json.dumps(WIN), EXPRESSIONS)
if err is not None:
    failed(C1 + C2 + C3 + C4, "spoofed chrome session", err)
elif baseline_err is not None:
    failed(C1 + C2 + C3 + C4, f"baseline load from {BASELINE}", baseline_err)
else:
    ua, ua_platform, ua_mobile, brands_json, entropy = spoofed

    results["1 spoofed UA carries the Windows OS token"] = (
        "Windows NT 10.0; Win64; x64" in ua)
    results["1 spoofed UA carries no Linux token"] = (
        "Linux" not in ua and "X11" not in ua)
    base_token = product_token(baseline["user_agent"])
    results["1 spoofed UA reports the build's own version"] = (
        base_token is not None and base_token in ua)

    # Records a KNOWN GAP as a measured fact rather than as prose, and guards
    # it in both directions. SP1a substitutes os_info only; product never
    # passes that substitution point, so the token must be byte-identical to
    # the unspoofed one -- today that means the spoofed Windows UA still says
    # HeadlessChrome. That is SP2's to remove (see its surface table), and
    # until it does, this assertion is what stops the leak from being
    # rediscovered by a detector instead of by us. It fails just as loudly if
    # SP1a ever starts touching the token, which it must not.
    results["1 spoofed UA leaves the product token untouched"] = (
        base_token is not None and product_token(ua) == base_token)

    # --- Criterion 2: navigator.userAgentData ---

    results["2 userAgentData.platform follows the config"] = (
        ua_platform == WIN["ua:platform"])
    results["2 userAgentData.mobile follows the config"] = (
        ua_mobile == WIN["ua:mobile"])
    results["2 userAgentData high-entropy values follow the config"] = (
        entropy.get("architecture") == WIN["ua:architecture"]
        and entropy.get("bitness") == WIN["ua:bitness"]
        and entropy.get("platformVersion") == WIN["ua:platformVersion"]
        and entropy.get("platform") == WIN["ua:platform"]
        and entropy.get("wow64") == WIN["ua:wow64"]
        and entropy.get("mobile") == WIN["ua:mobile"])

    # --- Criterion 3: the Sec-CH-UA-* request headers ---

    results["3 Sec-CH-UA-Platform follows the config"] = (
        unquote(wire.get("sec-ch-ua-platform", "")) == WIN["ua:platform"])
    results["3 Sec-CH-UA-Arch and -Bitness follow the config"] = (
        unquote(wire.get("sec-ch-ua-arch", "")) == WIN["ua:architecture"]
        and unquote(wire.get("sec-ch-ua-bitness", "")) == WIN["ua:bitness"])
    results["3 Sec-CH-UA-Platform-Version follows the config"] = (
        unquote(wire.get("sec-ch-ua-platform-version", ""))
        == WIN["ua:platformVersion"])
    results["3 Sec-CH-UA-Mobile and -WoW64 follow the config"] = (
        "sec-ch-ua-mobile" in wire and "sec-ch-ua-wow64" in wire
        and is_true(wire["sec-ch-ua-mobile"]) == WIN["ua:mobile"]
        and is_true(wire["sec-ch-ua-wow64"]) == WIN["ua:wow64"])

    # --- Criterion 4: the channels against EACH OTHER ---
    #
    # The item the spec calls "the one that fails if the producer patch is
    # bypassed anywhere". Everything above compares a channel to the config;
    # only this compares channels to one another, so only this can catch a
    # path that reached a plausible value without going through the producer.

    results["4 UA string, userAgentData and Sec-CH-UA agree on the platform"] = (
        ua_platform == unquote(wire.get("sec-ch-ua-platform", ""))
        and ua_carries_platform(ua, ua_platform))

    results["4 userAgentData and Sec-CH-UA agree on every high-entropy value"] = (
        entropy.get("architecture") == unquote(wire.get("sec-ch-ua-arch", ""))
        and entropy.get("bitness") == unquote(wire.get("sec-ch-ua-bitness", ""))
        and entropy.get("platformVersion")
        == unquote(wire.get("sec-ch-ua-platform-version", ""))
        and entropy.get("model") == unquote(wire.get("sec-ch-ua-model", ""))
        and entropy.get("wow64") == is_true(wire.get("sec-ch-ua-wow64", "?0"))
        and entropy.get("mobile") == is_true(wire.get("sec-ch-ua-mobile", "?0")))

    # The UA string reaches the wire too, and by a different code path than
    # navigator.userAgent. A patch applied to one and not the other is exactly
    # the bypass criterion 4 exists to find.
    results["4 the UA request header is the UA string"] = (
        wire.get("user-agent") == ua)

# --- Criterion 8: unconfigured chrome is unchanged, on all three channels ---
#
# Against the capture from 0e8d4a9268, taken before the patch existed --
# not against another run of this binary, which would execute the same
# modified code and so could not detect a substitution that fires
# unconditionally.

C8 = ["8 unconfigured UA is byte-identical to the baseline",
      "8 unconfigured userAgentData matches the baseline",
      "8 unconfigured request headers match the baseline"]

stock, stock_wire, err = run(None, EXPRESSIONS)
if err is not None:
    failed(C8, "unconfigured chrome session", err)
elif baseline_err is not None:
    failed(C8, f"baseline load from {BASELINE}", baseline_err)
else:
    ua, ua_platform, ua_mobile, brands_json, entropy = stock
    results["8 unconfigured UA is byte-identical to the baseline"] = (
        ua == baseline["user_agent"])
    results["8 unconfigured userAgentData matches the baseline"] = (
        ua_platform == baseline["platform"]
        and ua_mobile == baseline["mobile"]
        and json.loads(brands_json) == baseline["brands"]
        and entropy == baseline["high_entropy"])
    observed = {k: v for k, v in stock_wire.items()
                if k.startswith("sec-ch-ua") or k == "user-agent"}
    results["8 unconfigured request headers match the baseline"] = (
        observed == baseline["request_headers"])

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)
