"""Verifies the SP2a acceptance criteria: navigator.webdriver, and the
HeadlessChrome product token.

Nine criteria across two automation signals: navigator.webdriver (1-3) and
the HeadlessChrome product token (5-9; 4 is deliberately unused, see below).
1 and 2b are the ones that prove anything for the first signal:
navigator.webdriver has two independent sources, and the widely-cited
--disable-blink-features=AutomationControlled switch closes only one of
them. On a stock build both come back `true` (FAIL).

The isolation problem this criteria set exists to solve:
content/child/runtime_features.cc force-enables the AutomationControlled
runtime feature under several conditions, including
--remote-debugging-port=0 -- read as ChromeDriver's own launch pattern -- and,
independently, --headless (runtime_features.cc:378). The first is exactly
what lib_shell.launch() hardcodes by default, so source 1
(RuntimeEnabledFeatures::AutomationControlledEnabled()) is already ON in
every session the harness starts unless a fixed, non-zero debug_port is
supplied instead. Criterion 1 uses the harness default deliberately, to
prove the fix wins even when Chromium's own launch-pattern heuristic has
already forced the feature on. Criteria 2a/2b use a fixed port so source 1
stays off and probe::ApplyAutomationOverride (behind CDP's
Emulation.setAutomationOverride) is the only thing that can flip the value --
without 2a as a guard, 2b's isolation claim would be unfalsifiable.

2a/2b's isolation has a second precondition, unguarded until now:
content_shell must not be launched with --headless either, or that switch
alone would force source 1 on regardless of debug_port. lib_shell.SHELL_FLAGS
carries --ozone-platform=headless -- content_shell's actual headless switch --
and not --headless, which is what keeps 2a/2b isolating the probe path. The
assertion below holds that fact down so it cannot drift silently.

There is no worker criterion, and that is deliberate. `webdriver` is
declared on the NavigatorAutomationInformation mixin, and
worker_navigator.idl is Exposed=Worker with no such mixin -- so
WorkerNavigator is not a window global and the surface does not exist in
workers at all (`typeof WorkerNavigator === 'undefined'` from window, on
any build). Spawning a real worker to confirm a property the IDL never
declares would be testing Blink's bindings generator, not this change.

Criteria 5-9 test the second signal, the HeadlessChrome product token
(GetUserAgentInternal(), in user_agent_utils.cc), across four channels: the
UA string, navigator.userAgentData.brands, the Sec-CH-UA request header, and
the User-Agent request header. Four, not all -- Sec-CH-UA-Full-Version-List
and getHighEntropyValues().fullVersionList are readable too and are not
asserted here; they come from the brand list, so 6 already pins their source.

5 is the proof. 9 shares 5's producer and so cannot diverge from it for THIS
defect -- it pins the transport rather than the value, because the UA reaches
navigator.userAgent and the wire header by different paths, and a later SP
rewriting the header in the network service would show up here and nowhere
else. 6 and 7 pass on a stock build already and are
PINS, not proofs: channel 1 is the only one the defect ever spanned, so
nothing in this task's mutation (Step 8) can redden them -- it edits
GetUserAgentInternal() alone, and neither channel is produced there;
GetUserAgentMetadata() is. They hold the line against a future Chromium roll
adding a headless brand, or a fork change routing the brand list through the
product string. 8 ties the token to navigator.webdriver in the same session:
--headless is itself one of the switches that forces AutomationControlled on
(see criteria 1-3's own paragraph above), so a stock headless build fails
both halves at once.

Structured like verify_sp1a.py, and for the same reason: a fault in any one
session must become a FAIL line rather than a traceback that discards every
result already collected. session() already returns faults as (None, exc)
instead of raising, so each block below only needs to check `err`.
"""

import json
import socket
import sys

import echo_server
import lib_shell

WEBDRIVER = "navigator.webdriver"
DESCRIPTOR = ("Object.getOwnPropertyDescriptor("
              "Navigator.prototype, 'webdriver').get.toString()")

results = {}
notes = []

# 2a/2b's isolation depends on SHELL_FLAGS never carrying --headless (see the
# module docstring) -- content/child/runtime_features.cc:378 force-enables
# AutomationControlled on that switch independent of debug_port.
# Deliberately `raise`, not `assert`: python3 -O strips assert statements, and
# a precondition that vanishes under a flag is this project's named failure
# mode wearing a guard's clothes. Task 2's CHROME_FLAGS mirror uses the same
# shape, so there is one idiom rather than two.
#
# It guards the module global, which is one level away from the argv each
# session actually uses -- launch() takes SHELL_FLAGS only when extra_flags is
# None, which is true of 2a and 2b today. A future criterion written as
# extra_flags=SHELL_FLAGS + ["--headless"] would pass this and lose the
# isolation anyway. Recorded rather than closed: a helper wrapping two call
# sites costs more than it protects, and the message below names the
# consequence for whoever adds the third.
if "--headless" in lib_shell.SHELL_FLAGS:
    raise RuntimeError(
        "SHELL_FLAGS now carries --headless, which runtime_features.cc maps onto "
        "AutomationControlled; criteria 2a/2b would stop isolating the probe path")

# Criteria 5-9's precondition, hoisted up here rather than left just above
# run_chrome(): criteria 1/2a/2b/3 each launch and tear down a browser before
# execution would otherwise reach this check, so a RuntimeError there escaped
# module scope and discarded those four results before the print loop ever
# ran -- exactly the traceback-over-FAIL-line failure this file's docstring
# says must not happen. Every criterion in the 5-9 block asserts the ABSENCE
# of a token that only appears under --headless, so dropping the switch would
# turn all five green while measuring nothing -- the project's dominant
# failure mode, arriving through a file this script does not own. ("Every
# criterion below" was right where this comment used to sit and became wrong
# when it moved: hoisting put criteria 1-3 below it too, and they assert
# nothing of the kind.)
#
# `raise`, not `assert`: python3 -O strips assert statements, and a guard
# that vanishes under a flag is that same failure mode wearing a guard's
# clothes. Same shape as the SHELL_FLAGS guard above, so there is one idiom
# rather than two.
#
# CHROME_FLAGS is a list, so "--headless" in lib_shell.CHROME_FLAGS is
# element equality -- it would not recognize "--headless=new", which
# lib_shell.py:57-59 documents as behaviorally identical for this switch.
# Checked with startswith("--headless=") too, so a reader who follows that
# note here is not told CHROME_FLAGS dropped --headless when it did not.
if not any(f == "--headless" or f.startswith("--headless=")
           for f in lib_shell.CHROME_FLAGS):
    raise RuntimeError(
        "CHROME_FLAGS no longer carries --headless; criteria 5-9 would be vacuous")


def failed(keys, label, exc):
    for key in keys:
        results[key] = False
    notes.append(f"{label}: {type(exc).__name__}: {exc}")


def free_port():
    """A port the kernel just handed out, so no two runs collide.

    Not the same as --remote-debugging-port=0: that makes CHROMIUM pick, and
    runtime_features.cc reads the literal 0 as ChromeDriver's launch pattern
    and force-enables AutomationControlled. Criteria 2a/2b need the feature
    OFF so the probe is the only thing that can set webdriver.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --- Criterion 1: harness-default launch (port 0) ---
# True (FAIL) on a stock build. --remote-debugging-port=0 -- what
# lib_shell.launch() hardcodes when no debug_port is given -- is read by
# runtime_features.cc as ChromeDriver's own launch pattern and forces
# RuntimeEnabledFeatures::AutomationControlledEnabled() on, independent of
# any --enable/--disable-blink-features flag. Proves source 1 is closed even
# under the harness's own default launch configuration.
C1 = "1 harness-default launch (port 0): navigator.webdriver === false"
values, err = lib_shell.session(None, [WEBDRIVER])
if err is not None:
    failed([C1], "criterion 1 session", err)
else:
    results[C1] = values[0] is False

# --- Criteria 2a/2b: fixed non-zero port, isolating the probe path ---
#
# 2a is a stock-build gate, consumed once at Step 5, not a live guard in the
# shipped suite. On the unpatched tree, a fixed non-zero port leaves
# AutomationControlledEnabled() unset (runtime_features.cc's own comment:
# such a port "is more likely for attaching a debugger, so we should leave
# EnableAutomationControlled unset") -- so on a stock build a FAIL here means
# the feature is on despite the non-zero port, and 2b would then be proving
# nothing about the probe path specifically. That is exactly what Step 5's
# stock run confirmed; re-check it after any Chromium roll.
#
# On a patched build 2a cannot fail for that reason: Navigator::webdriver()
# returns false unconditionally, regardless of debug_port, so the paragraph
# above describes a stock-build failure mode this run cannot hit. What 2a is,
# here, is a harness canary: it shares 2b's exact launch configuration minus
# the CDP override, so a debug_port regression that breaks CONNECTIVITY -- the
# fixed port never being polled, or the parameter accepted and ignored --
# surfaces as a 2a FAIL instead of a confusing 2b FAIL.
#
# It does not catch a silent revert to port 0: the browser would connect, the
# feature would be force-on, and on a patched build webdriver is still false,
# so 2a passes green. Catching that needs an assertion on the argv, which
# session() does not expose. Named because the obvious example to reach for
# here is the one case the canary misses.
C2A = "2a fixed port, no override: navigator.webdriver === false"
values, err = lib_shell.session(None, [WEBDRIVER], debug_port=free_port())
if err is not None:
    failed([C2A], "criterion 2a session", err)
else:
    results[C2A] = values[0] is False

# True (FAIL) on a stock build. With source 1 held off by 2a's port choice,
# this is the one configuration in which probe::ApplyAutomationOverride is
# what flips the value -- proves source 2 is closed, the one
# --disable-blink-features=AutomationControlled misses entirely.
#
# 2b's isolation claim -- that context.new_cdp_session(page) targets the same
# page page.evaluate() reads -- is established EMPIRICALLY, by Step 5's stock
# run and the Step 8 mutation, in both of which 2b FAILed. A FAIL is only
# possible if the override reached the evaluated page, so the claim rests on
# an observed failure rather than on reading Playwright's source.
#
# Nothing re-checks it per run. Unlike 2a's port precondition, which the guard
# at the top of this file holds down, the targeting assumption has no in-suite
# check, so it would degrade to a guaranteed PASS with nothing to notice.
# The re-check procedure is therefore RE-RUN THE MUTATION, not re-read the
# code -- after any Chromium roll, and after any Playwright upgrade too, since
# new_cdp_session's session-to-page targeting is Playwright's contract, not
# Chromium's.
C2B = "2b fixed port, Emulation.setAutomationOverride(enabled=true): still false"
values, err = lib_shell.session(
    None, [WEBDRIVER], debug_port=free_port(),
    cdp=[("Emulation.setAutomationOverride", {"enabled": True})])
if err is not None:
    failed([C2B], "criterion 2b session", err)
else:
    results[C2B] = values[0] is False

# --- Criterion 3: the getter is still a real accessor ---
# Also passes on a stock build. Guards rule 2 (the getter stays a native
# accessor, not a plain data property a page could distinguish by shape).
C3 = "3 webdriver descriptor getter is native code"
values, err = lib_shell.session(None, [DESCRIPTOR])
if err is not None:
    failed([C3], "criterion 3 session", err)
else:
    results[C3] = "[native code]" in values[0]

# --- Criteria 5-9: the HeadlessChrome product token, across four channels ---
#
# Criterion 5 is the proof: on a stock `chrome --headless` build,
# navigator.userAgent carries "HeadlessChrome/154.0.0.0"
# (GetUserAgentInternal(), in user_agent_utils.cc).
#
# Criteria 6 and 7 pass on a stock build already. They are PINS on two
# surfaces that are already clean, not proofs that this fix reached them --
# channel 1 is the only one the defect ever spanned, so removing its prefix
# cannot leave channels 2 and 3 out of step. Nothing in this task's mutation
# (Step 8) can falsify them: it edits GetUserAgentInternal() alone, and
# neither channel is produced there -- GetUserAgentMetadata() is. They guard
# against a future Chromium roll adding a headless brand, or a fork change
# routing the brand list through the product string.
#
# Criterion 8 is SP2's section 5 coherence tie: --headless is itself one of
# the switches runtime_features.cc:378 maps onto AutomationControlled, so a
# stock headless build answers navigator.webdriver === true with nothing else
# attached -- a false webdriver beside a headless UA is louder than either
# alone, so both are asserted together in the same session as criterion 5.
#
# Criterion 9 is the channel closest to the defect: the User-Agent request
# header, reached by a different code path than navigator.userAgent, and
# already sitting in `wire` at zero marginal cost (verify_sp1a_chrome.py's own
# criterion 4, "the UA request header is the UA string", makes the same
# header comparison).
#
# All five run in one `chrome` session with the echo server up, for the same
# reason verify_sp1a_chrome.py gives: criterion 8 compares two channels
# (webdriver and the UA string), and reading them from two runs would compare
# two browsers.


def run_chrome(config, expressions):
    """One `chrome` session with the echo server up; returns (values, headers, err).

    chrome, not content_shell: ShellContentBrowserClient::GetUserAgent builds
    its own product string and never calls GetUserAgentInternal, so the shell
    has no HeadlessChrome under any switch and would pass this vacuously.

    CHROME_FLAGS already carries --headless, which is the whole precondition
    for the prefix; asserting its absence without it would measure nothing.
    """
    try:
        base_url, headers_for, stop = echo_server.start(lib_shell.ACCEPT_CH)
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
        return None, None, RuntimeError("the subresource request was never observed")
    return values, {k.lower(): v for k, v in wire.items()}, None


C5 = "5 navigator.userAgent contains no Headless"
C6 = "6 no brand in navigator.userAgentData.brands contains Headless"
C7 = "7 the Sec-CH-UA request header contains no Headless"
C8 = "8 navigator.webdriver === false and criterion 5 holds, same session"
C9 = "9 the User-Agent request header contains no Headless"

values, wire, err = run_chrome(
    None, ["navigator.userAgent",
           "JSON.stringify(navigator.userAgentData.brands)",
           "navigator.webdriver"])
if err is not None:
    failed([C5, C6, C7, C8, C9], "criteria 5-9 session", err)
else:
    ua, brands_json, webdriver = values

    # ua and wire are both in hand here, so C5, C7, C8 and C9 are computed
    # BEFORE the brands parse can fail. Only C6 reads `brands`. Failing all
    # five on a parse error would report "the product token leaked into the
    # UA string" for what is really "the brands channel could not be read" --
    # and an hour was lost in this project once to a misattributed failure.
    results[C5] = "Headless" not in ua

    # "sec-ch-ua" in wire first: wire.get(..., "") would let a missing or
    # renamed header PASS silently. This criterion asserts an ABSENCE, which
    # inverts the safety of the .get default -- an equality comparison fails
    # when the surface disappears, an absence assertion passes.
    results[C7] = ("sec-ch-ua" in wire
                   and "Headless" not in wire["sec-ch-ua"])

    results[C8] = webdriver is False and results[C5]

    results[C9] = ("user-agent" in wire
                   and "Headless" not in wire["user-agent"])

    # TypeError as well as ValueError, and the TypeError is the reachable one.
    # json.loads raises JSONDecodeError (a ValueError) on a malformed string
    # but TypeError on a non-string -- and JSON.stringify(undefined) returns
    # JS undefined, which Playwright hands back as None. So if
    # navigator.userAgentData.brands ever goes missing -- THE regression C6
    # exists to pin -- an uncaught TypeError would take the whole run down
    # with no output at all, instead of printing FAIL 6.
    #
    # The two neighbouring cases already behave: brands === null gives "null",
    # which parses to None and fails C6 on bool(None); userAgentData itself
    # being undefined throws in-page and is caught by session().
    try:
        brands = json.loads(brands_json)
    except (ValueError, TypeError) as exc:
        failed([C6], "criterion 6 brands parse", exc)
    else:
        # bool(brands) first: an empty list satisfies `not any(...)` having
        # examined nothing, so absence alone would PASS this criterion.
        results[C6] = bool(brands) and not any(
            "Headless" in b.get("brand", "") for b in brands)

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)
