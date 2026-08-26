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

    Three details here exist because of flakes that were actually observed,
    not defensively:

    A fresh --user-data-dir per launch. Without one, consecutive runs share
    the default profile, and the next instance can start while the previous
    still holds the profile lock. That produced TargetClosedError on the
    first evaluate() in two runs out of eight.

    --remote-debugging-port=0, with the chosen port read back from the
    profile's DevToolsActivePort file. A fixed port lets a run connect to a
    previous instance that is still shutting down, which looks identical to
    the browser under test misbehaving.

    Polling the endpoint rather than sleeping a fixed interval. A five-second
    sleep flaked one run in four, and an intermittently failing verification
    is worse than a slow one: it teaches people to re-run until green, and
    then it measures nothing.
    """
    env = dict(os.environ)
    env.pop("CAMOU_CONFIG", None)
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


WORKER_PROBE = """
() => new Promise(resolve => {
  const src = 'self.postMessage(navigator.hardwareConcurrency)';
  const url = URL.createObjectURL(new Blob([src], {type: 'text/javascript'}));
  const w = new Worker(url);
  w.onmessage = e => resolve(e.data);
})
"""

DESCRIPTOR_PROBE = """
() => Object.getOwnPropertyDescriptor(
    Navigator.prototype, 'hardwareConcurrency').get.toString()
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

results = {}

# Criteria 2 and 5: spoofed value, and worker parity under spoofing.
proc = launch('{"navigator.hardwareConcurrency":8}')
window_value, worker_value, descriptor, spoofed_keys, spoofed_proto = evaluate(
    proc, ["navigator.hardwareConcurrency", WORKER_PROBE, DESCRIPTOR_PROBE,
           KEYS_PROBE, PROTO_PROBE])
shutdown(proc)
results["2 spoofed value is 8"] = window_value == 8
results["5 worker agrees when spoofed"] = worker_value == 8
# Criterion 4, first half: the accessor still looks native.
results["4 accessor reports [native code]"] = "[native code]" in descriptor

# Criteria 3 and 5: real value, and worker parity without configuration.
proc = launch(None)
real_window, real_worker, stock_keys, stock_proto = evaluate(
    proc, ["navigator.hardwareConcurrency", WORKER_PROBE, KEYS_PROBE,
           PROTO_PROBE])
shutdown(proc)
results["3 falls back to the real 16"] = real_window == 16
results["5 worker agrees when unconfigured"] = real_worker == real_window

# Criterion 4, second half: no property was added or removed, measured
# against the binary as it was BEFORE any Camoucrome call site was wired in.
# Comparing the spoofed run against the unconfigured run would not catch a
# property this change adds unconditionally, because both runs execute the
# same modified code. Both runs are checked against the baseline for the
# same reason.
results["4 window keys match the pre-spoof baseline"] = (
    spoofed_keys.split(",") == baseline["window_keys"]
    and stock_keys.split(",") == baseline["window_keys"])
results["4 Navigator prototype unchanged"] = (
    spoofed_proto.split(",") == baseline["navigator_prototype_props"]
    and stock_proto.split(",") == baseline["navigator_prototype_props"])

# Criterion 6: malformed configuration does not crash and reports the truth.
proc = launch("{not json")
malformed_value = evaluate(proc, ["navigator.hardwareConcurrency"])[0]
shutdown(proc)
with open(STDERR_LOG, "rb") as f:
    stderr = f.read().decode("utf-8", "replace")
results["6 malformed config reports the real value"] = malformed_value == 16
results["6 malformed config logs an error"] = "camoucfg" in stderr

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")

sys.exit(0 if all(results.values()) else 1)
