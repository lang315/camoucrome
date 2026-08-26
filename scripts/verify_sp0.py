"""Verifies the six SP0 acceptance criteria against a built content_shell."""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

SHELL = os.path.expanduser("~/chromium/src/out/Default/content_shell")
STDERR_LOG = "/tmp/camoucrome_verify_stderr.log"


def launch(config):
    """Starts content_shell and returns it once its DevTools port answers.

    Four details here exist because of failures that were actually observed,
    not defensively.

    Every CAMOU_CONFIG* variable is cleared, not just the bare name. The
    transport gives numbered chunks precedence over the unnumbered variable,
    so a leftover CAMOU_CONFIG_1 in the shell -- and this machine is exactly
    where such leftovers are made -- would silently win over what a run
    intends to set. A stale CAMOU_CONFIG_STRICT would likewise turn the
    malformed-config run into an intentional abort.

    A fresh --user-data-dir per launch. Without one, consecutive runs share
    the default profile and the next instance can start while the previous
    still holds the profile lock; that produced TargetClosedError on the
    first evaluate() in two runs out of eight.

    --remote-debugging-port=0, with the chosen port read back from the
    profile's DevToolsActivePort. A fixed port lets a run connect to a
    previous instance that is still shutting down, which looks identical to
    the browser under test misbehaving.

    Polling the endpoint rather than sleeping a fixed interval. A five-second
    sleep flaked one run in four, and an intermittently failing verification
    is worse than a slow one: it teaches people to re-run until green, and
    then it measures nothing.
    """
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("CAMOU_CONFIG")}
    if config is not None:
        env["CAMOU_CONFIG"] = config

    profile = tempfile.mkdtemp(prefix="camoucrome-verify-")
    # stderr goes to a file, not a pipe. Criterion 6 reads it after the
    # process is gone, and a pipe would deadlock the child if Chromium's
    # startup noise filled the buffer. Each launch truncates it, so a read
    # only ever sees its own run.
    stderr_file = open(STDERR_LOG, "wb")
    # content_shell has no --headless switch; --ozone-platform=headless is
    # the equivalent. CDP is served on --remote-debugging-port as in chrome.
    proc = subprocess.Popen(
        [SHELL, "--no-sandbox", "--ozone-platform=headless",
         f"--user-data-dir={profile}", "--remote-debugging-port=0",
         "about:blank"],
        env=env, stdout=subprocess.DEVNULL, stderr=stderr_file)
    proc.profile_dir = profile

    port_file = pathlib.Path(profile) / "DevToolsActivePort"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            shutdown(proc)
            raise RuntimeError(
                f"content_shell exited during startup, code {proc.returncode}")
        if port_file.exists():
            first = port_file.read_text().splitlines()[:1]
            if first and first[0].strip().isdigit():
                port = int(first[0].strip())
                try:
                    urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/json/version",
                        timeout=1).read()
                    proc.cdp_port = port
                    return proc
                except Exception:
                    pass
        time.sleep(0.1)

    shutdown(proc)
    raise RuntimeError("content_shell opened no DevTools endpoint within 30s")


def shutdown(proc):
    """Stops the browser and waits for it, so the next launch starts clean."""
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=15)
    shutil.rmtree(getattr(proc, "profile_dir", ""), ignore_errors=True)


def evaluate(proc, expressions):
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(
            f"http://127.0.0.1:{proc.cdp_port}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        return [page.evaluate(e) for e in expressions]


def session(config, expressions):
    """Runs one content_shell session; returns (values, error).

    An exception is returned rather than raised. Without this the script is
    a linear sequence with one print loop at the end, so a fault anywhere
    discards every result already collected -- and the fault most likely to
    happen is the one criterion 6 exists to detect. A renderer that crashes
    on malformed configuration would take the whole report with it, leaving
    an unattributed traceback that reads exactly like infrastructure flake.

    Three other regressions collapse the same way if unhandled: an accessor
    demoted from a getter to a data property makes DESCRIPTOR_PROBE throw a
    TypeError, a broken worker path leaves WORKER_PROBE's promise unresolved
    until Playwright times out, and a browser that dies during startup never
    reaches a connection at all.
    """
    proc = None
    try:
        proc = launch(config)
        return evaluate(proc, expressions), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    finally:
        if proc is not None:
            shutdown(proc)


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
with open(BASELINE) as f:
    baseline = json.load(f)

# The real processor count comes from the baseline rather than a literal, so
# this runs on a machine with a different core count without silently
# failing for a reason nothing in the script explains.
REAL = baseline["hardware_concurrency"]

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
STOCK_KEYS = [f"3 falls back to the real {REAL}",
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
    results[f"3 falls back to the real {REAL}"] = real_window == REAL
    results["5 worker agrees when unconfigured"] = real_worker == real_window
    results["4 accessor reports [native code] when unconfigured"] = (
        "[native code]" in descriptor)

# Criterion 4: no property was added or removed, measured against the binary
# as it was BEFORE any Camoucrome call site was wired in. Comparing the
# spoofed run against the unconfigured run would not catch a property this
# change adds unconditionally, because both runs execute the same modified
# code. Both runs are checked against the baseline for that reason.
if spoofed_keys is not None and stock_keys is not None:
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
                  f"6 malformed config reports the real {REAL}",
                  "6 malformed config logs an error"]
bad, err = session("{not json", ["navigator.hardwareConcurrency"])
if err is not None:
    failed(MALFORMED_KEYS, "malformed-config session", err)
else:
    results["6 malformed config does not crash the browser"] = True
    with open(STDERR_LOG, "rb") as f:
        stderr = f.read().decode("utf-8", "replace")
    results[f"6 malformed config reports the real {REAL}"] = bad[0] == REAL
    # Substring match against the implementation's own wording. Direction of
    # failure is a false FAIL, never a false PASS, but a later rename of the
    # log tag would need this updated with it.
    results["6 malformed config logs an error"] = "camoucfg" in stderr

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)
