"""SP2b measurement 1: does console serialization invoke page getters here?

This is a MEASUREMENT, not a verification. It has no pass/fail: it records
what this build does, so that SP2's open decision D1 can be made on evidence
instead of on the public literature. The spec is explicit that this comes
first -- "Committing to a V8 inspector patch before knowing whether a free
driver-side fix closes the same vectors would be the single most expensive
mistake available in this sub-project."

The vector, from SP2 section 4.3. When the Runtime domain is enabled, objects
passed to console.* are serialized for the protocol, and serialization touches
property getters that would otherwise never run:

    let seen = false;
    const probe = {};
    Object.defineProperty(probe, 'x', { get() { seen = true; return 1; } });
    console.debug(probe);
    // seen === true implies something is consuming console output

Three things this script establishes, in order of how much they change the
plan:

  1. Whether the leak reproduces at all on this Chromium revision. The
     literature is old and V8's inspector has been rewritten repeatedly. If
     the getter never fires, D1 collapses and no V8 patch is warranted.
  2. Whether it fires under OUR harness. Playwright enables the Runtime
     domain -- that is the entire reason patchright exists -- so this is the
     configuration Camoucrome is actually driven in today.
  3. Whether console.* reaches it at all when nothing is attached, which is
     the control. Without this the other two numbers mean nothing: a getter
     that fires with no inspector present would indicate the probe is
     measuring its own construction rather than serialization.

What it deliberately does NOT establish: whether a driver that never sends
Runtime.enable escapes the leak. That needs a CDP client which does not
enable Runtime, and neither Playwright nor anything in the venv provides one.
If measurement 1 shows the leak is live, that client is the next thing to
build -- and it is worth building, because it is the difference between a
free fix and patching V8's inspector.
"""

import json
import sys

import lib_shell

# Split across two evaluations on purpose. Serialization for the protocol is
# not guaranteed to happen synchronously inside the console.* call, so reading
# the flag in the same expression that sets it could report false for a leak
# that is merely late. The second evaluation happens after a round trip, which
# is a weak-but-real ordering guarantee, and the interval is recorded so a
# future reader knows what "after" meant.
ARM = """
() => {
  window.__probeSeen = false;
  const probe = {};
  Object.defineProperty(probe, 'x', {
    get() { window.__probeSeen = true; return 1; },
    enumerable: true,
  });
  // debug, not log: SP2's spec names console.debug, and the level matters --
  // some consumers filter by level before serializing.
  console.debug(probe);
  return window.__probeSeen;
}
"""

READ = "() => window.__probeSeen"

# The same probe against a second sink, to tell "console serialization" apart
# from "any inspector activity". If dir() fires it and debug() does not, the
# vector is narrower than the literature claims and the fix is narrower too.
ARM_DIR = """
() => {
  window.__dirSeen = false;
  const probe = {};
  Object.defineProperty(probe, 'y', {
    get() { window.__dirSeen = true; return 1; },
    enumerable: true,
  });
  console.dir(probe);
  return window.__dirSeen;
}
"""

READ_DIR = "() => window.__dirSeen"

# POSITIVE CONTROL. Without this the whole measurement is worthless: a probe
# that CANNOT fire reports false whether or not the leak exists, and a false
# recorded into a decision document is worse than no measurement. This uses
# the same defineProperty shape and an operation that is guaranteed to read
# the property -- so if this comes back false, the probe is broken and every
# other number in this file must be discarded rather than interpreted.
CONTROL = """
() => {
  let fired = false;
  const probe = {};
  Object.defineProperty(probe, 'z', {
    get() { fired = true; return 1; },
    enumerable: true,
  });
  JSON.stringify(probe);
  return fired;
}
"""


def measure(label, shell, flags):
    """One session. Returns the four probe readings plus both controls.

    console_seen is the second control and it is what makes a `false` above
    interpretable. The leak's precondition is that something is CONSUMING
    console output over the protocol -- which requires Runtime.enable. If no
    console message reaches the client, then the Runtime domain is either not
    enabled or not delivering, the leak's precondition is absent, and the
    false readings say nothing about whether the vector exists. They would
    only say we failed to set up the conditions to look for it.
    """
    proc = None
    try:
        proc = lib_shell.launch(None, shell=shell, extra_flags=flags)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(
                f"http://127.0.0.1:{proc.cdp_port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            received = []
            page.on("console", lambda msg: received.append(msg.type))
            values = [page.evaluate(e)
                      for e in (ARM, READ, ARM_DIR, READ_DIR, CONTROL)]
            page.wait_for_timeout(250)
            return {
                "label": label,
                "debug_immediate": values[0],
                "debug_after_roundtrip": values[1],
                "dir_immediate": values[2],
                "dir_after_roundtrip": values[3],
                "control_getter_can_fire": values[4],
                "control_console_messages_received": received,
            }
    except Exception as exc:  # noqa: BLE001 - a fault must become a record
        return {"label": label, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)


runs = [
    measure("content_shell, Playwright (Runtime domain enabled)",
            lib_shell.SHELL, lib_shell.SHELL_FLAGS),
    measure("chrome, Playwright (Runtime domain enabled)",
            lib_shell.CHROME, lib_shell.CHROME_FLAGS),
]

print(json.dumps({"measurement": "sp2b-1-console-getter", "runs": runs},
                 indent=2))

# Non-zero only on a harness fault. A measurement has no failing result --
# "the getter fired" and "it did not" are both answers, and exiting non-zero
# on one of them would turn a measurement into an assertion of what the
# answer should have been.
sys.exit(1 if any("error" in r for r in runs) else 0)
