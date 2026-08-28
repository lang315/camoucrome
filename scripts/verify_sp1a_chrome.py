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

# The pinned upstream revision this baseline must be a capture of (README.md).
# Not the checkout's current HEAD: a HEAD-tracking guard is refused the
# moment ANY patch lands, including ones that never touch the UA surface, and
# its only escape hatch is recapturing from whatever is currently built --
# which is what commit 9f1040e did, and which makes the baseline compare the
# fork against a recording of itself instead of against stock. Fork-side UA
# deltas (SP2a's Headless-prefix removal, for one) are reconciled in code at
# the comparison sites below, not by moving this constant.
STOCK_BASE_COMMIT = "0e8d4a9268"

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

# WIN alone is not enough, and the reason is worth stating because it took a
# mutation to see. This build runs on 64-bit x86 Linux, so the unpatched
# browser ALREADY reports architecture "x86", bitness "64", mobile false and
# wow64 false. WIN asks for exactly those four. Every assertion about them
# therefore passes whether or not the config reached the field.
#
# Measured, not reasoned: disabling those four substitutions in
# GetUserAgentMetadata() and rebuilding chrome left this file printing
# 17 PASS, exit 0. Four of the seven metadata keys were unverified and one
# (ua:model) was executed by nothing at all.
#
# So each key must be exercised at least once with a value the unpatched build
# does NOT report. These two profiles do that, and EveryMetadataKeyIsExercised
# below fails if a future key is added without one.
#
# Both are real configurations rather than scrambles. An anti-detect browser
# should not have test profiles that describe machines nobody owns, because a
# profile is also an example, and examples get copied.

# A 32-bit process on 64-bit Windows: that is precisely what WoW64 means.
# Differs from the host in bitness and wow64.
WOW64 = {
    "ua:osInfo": "Windows NT 10.0; Win64; x64",
    "ua:platform": "Windows",
    "ua:platformVersion": "15.0.0",
    "ua:architecture": "x86",
    "ua:bitness": "32",
    "ua:mobile": False,
    "ua:wow64": True,
}

# A Pixel. Android reports empty architecture and bitness, a populated model,
# and mobile true -- differing from the host in five of the seven.
ANDROID = {
    "ua:osInfo": "Linux; Android 10; K",
    "ua:platform": "Android",
    "ua:platformVersion": "13",
    "ua:architecture": "",
    "ua:bitness": "",
    "ua:model": "Pixel 7",
    "ua:mobile": True,
    "ua:wow64": False,
}

# config key -> (getHighEntropyValues field, request header, is it a boolean)
METADATA_KEYS = [
    ("ua:platform", "platform", "sec-ch-ua-platform", False),
    ("ua:platformVersion", "platformVersion", "sec-ch-ua-platform-version", False),
    ("ua:architecture", "architecture", "sec-ch-ua-arch", False),
    ("ua:bitness", "bitness", "sec-ch-ua-bitness", False),
    ("ua:model", "model", "sec-ch-ua-model", False),
    ("ua:mobile", "mobile", "sec-ch-ua-mobile", True),
    ("ua:wow64", "wow64", "sec-ch-ua-wow64", True),
]

results = {}
notes = []


def failed(keys, label, exc):
    for key in keys:
        results[key] = False
    notes.append(f"{label}: {type(exc).__name__}: {exc}")


def load_baseline(path):
    """Loads the baseline and refuses it if it is not a stock capture.

    A baseline's whole value is that it predates every fork patch. capture_
    ua_baseline.py records provenance.captured_at_commit -- the checkout's
    git HEAD at capture time -- so this only has to compare that recorded
    value against STOCK_BASE_COMMIT, the pinned revision it must equal.
    Nothing here reads the checkout's CURRENT commit: a baseline captured
    from an already-patched checkout is wrong regardless of what the
    checkout has since moved to or away from, and checking against a moving
    target is what let commit 9f1040e recapture the baseline from a patched
    build and have the guard call it fresh. Refusing here, the same way an
    unrecognised binary is refused at capture time, gives that failure one
    named cause instead of four confusing FAILs that read like a regression
    this file did not cause.
    """
    try:
        with open(path) as handle:
            data = json.load(handle)
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    missing = [k for k in ("user_agent", "brands", "platform", "mobile",
                           "high_entropy", "request_headers", "provenance")
               if k not in data]
    if missing:
        return None, KeyError(f"baseline lacks {', '.join(missing)}")
    captured_commit = data["provenance"].get("captured_at_commit")
    if not captured_commit:
        return None, KeyError(
            "baseline's provenance lacks captured_at_commit")
    if captured_commit != STOCK_BASE_COMMIT:
        return None, RuntimeError(
            f"baseline is not a stock capture: provenance.captured_at_commit "
            f"is {captured_commit!r}, expected {STOCK_BASE_COMMIT!r} -- the "
            f"pinned upstream revision this project builds from (README.md), "
            f"captured before any Camoucrome patch landed. This file must "
            f"stay that stock capture; a fork-side UA delta (SP2a's "
            f"Headless-prefix removal, for one) belongs in code at the "
            f"comparison site -- see product_token()'s caller and the "
            f"criterion-8 block below -- not in this file. If {path} was "
            f"genuinely overwritten, restore it from git history rather than "
            f"recapturing: git show <last-good-commit>:baselines/"
            f"chrome-{STOCK_BASE_COMMIT}-stock-ua.json. Only recapture if "
            f"you have rebuilt `chrome` from the unpatched "
            f"{STOCK_BASE_COMMIT} checkout, with the venv interpreter (bare "
            f"python3 has no playwright): "
            f"~/camoucrome-verify/venv/bin/python3 capture_ua_baseline.py "
            f"--shell {lib_shell.CHROME} > "
            f"baselines/chrome-{STOCK_BASE_COMMIT}-stock-ua.json in the "
            f"camoucrome repo (git-tracked), then redeploy that file to "
            f"{path} -- writing only to {path} updates this checkout's copy "
            f"and leaves the repo one stale.")
    return data, None


baseline, baseline_err = load_baseline(BASELINE)


def product_token(ua):
    """The 'Chrome/<version>' token, whatever prefix it carries.

    NOT startswith("Chrome/"), which is what verify_sp1a.py uses and what
    this file used first. That distinction used to matter here: under
    --headless the token was HeadlessChrome/154.0.0.0, upstream inserting the
    prefix in GetUserAgentInternal(). SP2a (user_agent_utils.cc, that same
    function) removed the insert unconditionally, so every token this file
    observes today is plain "Chrome/<version>" and a prefix match would
    already work. The `in` form is kept anyway -- it costs nothing, and it is
    what still reads correctly if some prefix, upstream's or a future fork
    addition, ever gets inserted again.
    """
    for token in ua.split():
        if "Chrome/" in token:
            return token
    return None


def sp2a_expected_ua(raw):
    """What SP2a's own build reports, given the pre-SP2a stock UA string.

    BASELINE must stay a stock, pre-SP2a capture (load_baseline() refuses it
    otherwise), so it still carries the "Headless" prefix that SP2a
    (user_agent_utils.cc, GetUserAgentInternal) removes unconditionally.
    Every comparison against the baseline needs that same removal applied
    here, or it compares a live SP2a build's output against a token no build
    produces anymore -- not a regression, just the one delta this task
    intends.
    """
    return raw.replace("HeadlessChrome/", "Chrome/")


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


# The CPU tokens a UA string carries for each (architecture, bitness) pair, as
# real Chrome emits them. Windows-on-ARM is the case that makes this subtle:
# Chrome there reports "Win64; x64" in the STRING while reporting
# architecture "arm" in the hints, deliberately, because the string's tokens
# are a compatibility fiction that the hints exist to replace. So the mapping
# below is not "arch appears in the string" -- it is "this pair is a
# combination real Chrome actually produces".
#
# Empty architecture and bitness are what Android and iOS report; there the UA
# string carries no CPU token to agree with, so anything is consistent.
CPU_CONSISTENT = {
    ("x86", "64"): ["Win64; x64", "x86_64", "Intel Mac OS X", "WOW64"],
    ("x86", "32"): ["WOW64", "Win64; x64", "i686", "i586"],
    ("arm", "64"): ["Win64; x64", "aarch64", "Mac OS X", "Android"],
    ("arm", "32"): ["Win64; x64", "armv7", "armv8", "Android"],
}


def ua_agrees_on_cpu(ua, architecture, bitness):
    """Whether the UA string's CPU tokens can coexist with the hint values.

    An unmapped pair is a FAIL, not a pass -- the same rule as
    UA_TOKEN_FOR_PLATFORM, and for the same reason.
    """
    if architecture == "" and bitness == "":
        return True  # Android/iOS: no CPU token in the string to contradict.
    tokens = CPU_CONSISTENT.get((architecture, bitness))
    return tokens is not None and any(t in ua for t in tokens)


def unquote(value):
    """sec-ch-ua-* values are RFC 8941 strings: "x86" -> x86."""
    return value.strip().strip('"')


def is_true(value):
    """RFC 8941 booleans: ?1 / ?0."""
    return value.strip() == "?1"


def run(config, expressions, extra=None):
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
            shell=lib_shell.CHROME,
            extra_flags=lib_shell.CHROME_FLAGS + (extra or []))
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
    base_token = product_token(sp2a_expected_ua(baseline["user_agent"]))
    results["1 spoofed UA reports the build's own version"] = (
        base_token is not None and base_token in ua)

    # Guards SP1a's boundary in both directions: SP1a substitutes os_info
    # only, so the product token must stay byte-identical to whatever the
    # unspoofed build reports, regardless of what that token is. It fails
    # just as loudly if SP1a ever starts touching the token, which it must
    # not.
    #
    # This carried a live KNOWN GAP until SP2a: the token stayed
    # HeadlessChrome because SP2 (see its surface table) had not yet removed
    # the prefix. SP2a closed that (user_agent_utils.cc, GetUserAgentInternal,
    # commit b04b4e77f4) -- the token every session observes now is
    # "Chrome/<version>" on both the spoofed and unconfigured sessions, and
    # this assertion no longer has a known-failing case to carry.
    #
    # What keeps the comparison meaningful rather than just quiet is
    # sp2a_expected_ua() above, not the baseline file itself: `baseline` is
    # pinned to the pre-SP2a stock capture (load_baseline() refuses anything
    # else), so base_token is SP2a's one intended delta applied to that
    # stock value, not a token an old, un-rebuilt baseline happens to still
    # contain.
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

    # Criterion 4 compared the metadata channel to the wire channel and the
    # platform to the UA string, and stopped there -- so architecture and
    # bitness were never compared to the UA string at all. SP1 §5 names that
    # invariant explicitly, and without it this config passes every other
    # assertion here:
    #
    #   ua:osInfo "Windows NT 10.0; Win64; x64" + ua:architecture "arm"
    #                                           + ua:bitness "32"
    #
    # navigator.userAgent says Win64; x64 while Sec-CH-UA-Arch says arm. Both
    # channels are individually plausible and they contradict each other,
    # which is the exact shape criterion 4 claims to catch.
    results["4 UA string, userAgentData and Sec-CH-UA agree on the CPU"] = (
        ua_agrees_on_cpu(ua, entropy.get("architecture"),
                         entropy.get("bitness")))

# --- Criterion 2b/3b: every metadata key reaches BOTH channels, proven with
#     a value the unpatched build does not report ---

def check_profile(label, cfg):
    """Asserts each configured metadata key reached both channels.

    Returns the set of keys this profile proved DISCRIMINATINGLY -- those whose
    configured value differs from what the unpatched build reports. A key
    confirmed only with the host's own value is not counted, because that
    assertion would hold with the substitution deleted.
    """
    names = [f"2b {label}: {key} reaches userAgentData and the wire"
             for key, _, _, _ in METADATA_KEYS if key in cfg]
    values, wire, err = run(json.dumps(cfg), EXPRESSIONS)
    if err is not None:
        failed(names, f"{label} session", err)
        return set()
    if baseline_err is not None:
        failed(names, f"baseline load from {BASELINE}", baseline_err)
        return set()

    entropy = values[4]
    stock = baseline["high_entropy"]
    discriminating = set()
    for key, field, header, is_bool in METADATA_KEYS:
        if key not in cfg:
            continue
        want = cfg[key]
        got_js = entropy.get(field)
        got_wire = (is_true(wire.get(header, "?0")) if is_bool
                    else unquote(wire.get(header, "")))
        name = f"2b {label}: {key} reaches userAgentData and the wire"
        results[name] = (got_js == want and got_wire == want)
        if not results[name]:
            notes.append(f"{name}: wanted {want!r}, js={got_js!r}, "
                         f"wire={got_wire!r}")
        if want != stock.get(field):
            discriminating.add(key)
    return discriminating


proved = set()
for label, cfg in (("wow64", WOW64), ("android", ANDROID)):
    proved |= check_profile(label, cfg)

# The structural guard. Without it, the defect this section exists to fix
# returns the moment someone adds an eighth key and tests it with whatever the
# host happens to report. Modelled on SP5a's MutationsExistForEveryInvariant:
# the loop is over the key list, so a key with no discriminating profile is a
# failing assertion rather than a silent gap.
unexercised = [key for key, _, _, _ in METADATA_KEYS if key not in proved]
results["2b every metadata key is exercised with a non-host value"] = (
    not unexercised)
if unexercised:
    notes.append(
        "2b every metadata key is exercised with a non-host value: "
        f"{', '.join(unexercised)} were only ever confirmed with the value "
        "this machine already reports, so those assertions would hold with "
        "the substitution deleted. Add a profile that differs.")

# --- Criterion 1b: --user-agent must not outrank a configuration ---
#
# Commit 07cadeac4c exists to change GetUserAgent()'s gate. Nothing tested it:
# the gtest it added calls GetUserAgentMetadata() only, and neither harness
# ever passed --user-agent. Reverting the added conjunct left every check in
# the deliverable passing, so the commit's own subject was unverified for the
# channel it names.
#
# The switch value below is deliberately a plausible REAL Chrome UA claiming
# macOS. If the switch won, the string would be byte-identical to it; if the
# config wins, the OS segment is the configured Windows one and the product
# token is this build's. Those two outcomes cannot be confused.

C1B = ["1b --user-agent loses to a configuration",
       "1b --user-agent still wins when no configuration is present"]

SWITCH_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 "
             "Safari/537.36")

switched, _, err = run(json.dumps(WIN), ["navigator.userAgent"],
                       extra=[f"--user-agent={SWITCH_UA}"])
if err is not None:
    failed([C1B[0]], "--user-agent with config session", err)
else:
    results[C1B[0]] = (
        switched[0] != SWITCH_UA
        and "Windows NT 10.0; Win64; x64" in switched[0]
        and "Macintosh" not in switched[0])

# The other half of the gate, and the half that keeps this a narrowing rather
# than a removal: with no configuration at all, --user-agent must behave
# exactly as stock Chromium does. A patch that made the switch stop working
# would pass the assertion above and break every non-Camoucrome use of it.
unswitched, _, err = run(None, ["navigator.userAgent"],
                         extra=[f"--user-agent={SWITCH_UA}"])
if err is not None:
    failed([C1B[1]], "--user-agent without config session", err)
else:
    results[C1B[1]] = (unswitched[0] == SWITCH_UA)

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

    # SP2a's delta again: the unconfigured session runs headless too
    # (CHROME_FLAGS), so it no longer reports the Headless-prefixed token
    # the stock baseline was captured with. Comparing it against the raw
    # baseline is what broke these two assertions -- and the product-token
    # ones above -- when 9f1040e's guard first caught the baseline going
    # stale; fixed here at the comparison site instead of by recapturing.
    baseline_ua = sp2a_expected_ua(baseline["user_agent"])
    results["8 unconfigured UA is byte-identical to the baseline"] = (
        ua == baseline_ua)
    results["8 unconfigured userAgentData matches the baseline"] = (
        ua_platform == baseline["platform"]
        and ua_mobile == baseline["mobile"]
        and json.loads(brands_json) == baseline["brands"]
        and entropy == baseline["high_entropy"])
    observed = {k: v for k, v in stock_wire.items()
                if k.startswith("sec-ch-ua") or k == "user-agent"}
    baseline_headers = dict(baseline["request_headers"])
    baseline_headers["user-agent"] = baseline_ua
    results["8 unconfigured request headers match the baseline"] = (
        observed == baseline_headers)

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)
