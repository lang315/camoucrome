"""Verifies the SP2a acceptance criteria for navigator.webdriver.

Four criteria. 1 and 2b are the ones that prove anything: navigator.webdriver
has two independent sources, and the widely-cited
--disable-blink-features=AutomationControlled switch closes only one of
them. On a stock build both come back `true` (FAIL).

The isolation problem this criteria set exists to solve:
content/child/runtime_features.cc force-enables the AutomationControlled
runtime feature under several conditions, including
--remote-debugging-port=0 -- read as ChromeDriver's own launch pattern. That
switch is exactly what lib_shell.launch() hardcodes by default, so source 1
(RuntimeEnabledFeatures::AutomationControlledEnabled()) is already ON in
every session the harness starts unless a fixed, non-zero debug_port is
supplied instead. Criterion 1 uses the harness default deliberately, to
prove the fix wins even when Chromium's own launch-pattern heuristic has
already forced the feature on. Criteria 2a/2b use a fixed port so source 1
stays off and probe::ApplyAutomationOverride (behind CDP's
Emulation.setAutomationOverride) is the only thing that can flip the value --
without 2a as a guard, 2b's isolation claim would be unfalsifiable.

There is no worker criterion, and that is deliberate. `webdriver` is
declared on the NavigatorAutomationInformation mixin, and
worker_navigator.idl is Exposed=Worker with no such mixin -- so
WorkerNavigator is not a window global and the surface does not exist in
workers at all (`typeof WorkerNavigator === 'undefined'` from window, on
any build). Spawning a real worker to confirm a property the IDL never
declares would be testing Blink's bindings generator, not this change.

Structured like verify_sp1a.py, and for the same reason: a fault in any one
session must become a FAIL line rather than a traceback that discards every
result already collected. session() already returns faults as (None, exc)
instead of raising, so each block below only needs to check `err`.
"""

import socket
import sys

import lib_shell

WEBDRIVER = "navigator.webdriver"
DESCRIPTOR = ("Object.getOwnPropertyDescriptor("
              "Navigator.prototype, 'webdriver').get.toString()")

results = {}
notes = []


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
# 2a's PASS is only meaningful if the feature really is off in this
# configuration. If runtime_features.cc ever force-enables on a non-zero
# port too, 2a stays green and 2b silently stops isolating the probe.
# The stock-build run recorded in Step 5 is what establishes this; re-check
# it after any Chromium roll.

# Also false on a stock build. The guard that makes 2b's isolation claim
# real: a fixed non-zero port leaves AutomationControlledEnabled() unset
# (runtime_features.cc's own comment: such a port "is more likely for
# attaching a debugger, so we should leave EnableAutomationControlled
# unset"). A FAIL here means the feature is on despite the non-zero port,
# and 2b would then be proving nothing about the probe path specifically.
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

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)
