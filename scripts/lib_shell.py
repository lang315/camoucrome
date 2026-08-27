"""Shared content_shell driving helpers.

Extracted verbatim from verify_sp0.py so that later verifications inherit the
hardening rather than re-deriving it. Every non-obvious detail in launch() and
session() exists because of a failure that was observed, not defensively; the
docstrings say which.
"""

import json
import os
import pathlib
import shutil
import subprocess
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

    Startup can fail in three distinguishable ways, which is deliberate:
    Popen itself raises FileNotFoundError naming the path if SHELL does not
    exist, the process exiting during startup reports its exit code, and a
    process that lives but never opens a port reports the timeout. Three
    different causes should not arrive as one message.

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


def evaluate(proc, expressions, navigate_to=None):
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(
            f"http://127.0.0.1:{proc.cdp_port}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        if navigate_to is not None:
            # wait_until="load" so the subresource request the header
            # assertions read has certainly been issued.
            page.goto(navigate_to, wait_until="load")
        return [page.evaluate(e) for e in expressions]


def session(config, expressions, navigate_to=None):
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
        return evaluate(proc, expressions, navigate_to), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    finally:
        if proc is not None:
            shutdown(proc)
