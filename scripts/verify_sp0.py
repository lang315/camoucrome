"""Verifies the six SP0 acceptance criteria against a built content_shell."""

import json
import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

SHELL = os.path.expanduser("~/chromium/src/out/Default/content_shell")
PORT = 9333


def launch(config):
    env = dict(os.environ)
    env.pop("CAMOU_CONFIG", None)
    if config is not None:
        env["CAMOU_CONFIG"] = config
    # content_shell has no --headless switch; --ozone-platform=headless is the
    # equivalent and is verified working against this build. CDP is served on
    # --remote-debugging-port exactly as chrome serves it.
    proc = subprocess.Popen(
        [SHELL, "--no-sandbox", "--ozone-platform=headless",
         f"--remote-debugging-port={PORT}", "about:blank"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    time.sleep(5)
    return proc


def evaluate(expressions):
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
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

results = {}

# Criteria 2 and 5: spoofed value, and worker parity under spoofing.
proc = launch('{"navigator.hardwareConcurrency":8}')
window_value, worker_value, descriptor, keys = evaluate(
    ["navigator.hardwareConcurrency", WORKER_PROBE, DESCRIPTOR_PROBE,
     "Object.keys(window).sort().join(',')"])
proc.terminate()
results["2 spoofed value is 8"] = window_value == 8
results["5 worker agrees when spoofed"] = worker_value == 8
# Criterion 4, first half: the accessor still looks native.
results["4 accessor reports [native code]"] = "[native code]" in descriptor
spoofed_keys = keys

# Criteria 3 and 5: real value, and worker parity without configuration.
proc = launch(None)
real_window, real_worker, stock_keys = evaluate(
    ["navigator.hardwareConcurrency", WORKER_PROBE,
     "Object.keys(window).sort().join(',')"])
proc.terminate()
results["3 falls back to the real 16"] = real_window == 16
results["5 worker agrees when unconfigured"] = real_worker == real_window
# Criterion 4, second half: no property was added or removed, measured
# against the binary as it was BEFORE any Camoucrome call site was wired in.
# Comparing the spoofed run against the unconfigured run would not catch a
# property this change adds unconditionally, because both runs execute the
# same modified code.
BASELINE = os.path.expanduser(
    "~/camoucrome-verify/baselines/content_shell-0e8d4a9268-stock.json")
with open(BASELINE) as f:
    baseline = json.load(f)
results["4 window keys match the pre-spoof baseline"] = (
    spoofed_keys.split(",") == baseline["window_keys"]
    and stock_keys.split(",") == baseline["window_keys"])
results["4 Navigator prototype unchanged"] = (
    sorted(evaluate(["Object.getOwnPropertyNames(Navigator.prototype)"])[0])
    == baseline["navigator_prototype_props"])

# Criterion 6: malformed configuration does not crash and reports the truth.
proc = launch("{not json")
malformed_value = evaluate(["navigator.hardwareConcurrency"])[0]
proc.terminate()
stderr = proc.stderr.read().decode("utf-8", "replace")
results["6 malformed config reports the real value"] = malformed_value == 16
results["6 malformed config logs an error"] = "camoucfg" in stderr

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")

sys.exit(0 if all(results.values()) else 1)
