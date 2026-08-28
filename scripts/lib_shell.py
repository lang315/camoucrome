"""Shared browser driving helpers.

Extracted verbatim from verify_sp0.py so that later verifications inherit the
hardening rather than re-deriving it. Every non-obvious detail in launch() and
session() exists because of a failure that was observed, not defensively; the
docstrings say which.

Drives content_shell by default and `chrome` when asked. Task 8 needs the
second because content_shell cannot exercise SP1a's central claim: it builds
its own UserAgentMetadata instead of calling the patched producer, and wires
no ClientHintsControllerDelegate, so two of the three channels do not exist
there. The parameters are threaded through rather than forked into a second
copy of launch(), because the five hardening fixes above are exactly what a
copy would drift away from.
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
CHROME = os.path.expanduser("~/chromium/src/out/Default/chrome")
# Per PROCESS, not a fixed path, and that distinction was earned. This was
# "/tmp/camoucrome_verify_stderr.log" for every run, opened "wb" -- truncating
# -- on every launch. Two verifications running at once therefore shared one
# file, and three of verify_sp5a.py's four assertions read it after their
# session, so one run truncating under another silently removed the evidence
# the other was about to read.
#
# Observed on 2026-08-27: verify_sp5a.py reported 3 PASS once while a second
# verification ran concurrently, then 4 PASS on five immediate re-runs. The
# implementer recorded it as an unreproduced transient rather than re-running
# until green, which is the only reason it was still there to explain.
#
# That is exactly the failure launch()'s own docstring warns about: an
# intermittently green verification is worse than a slow one, because it
# teaches people to re-run until it passes, and then it measures nothing.
# Readers go through lib_shell.STDERR_LOG, so each process gets its own file
# and the read pattern is unchanged.
STDERR_LOG = f"/tmp/camoucrome_verify_stderr.{os.getpid()}.log"

# content_shell has no --headless switch; --ozone-platform=headless is the
# equivalent. This is the default so that every call written before Task 8
# keeps its exact argv.
SHELL_FLAGS = ["--ozone-platform=headless"]

# `chrome` wants the real switch. Bare, with no value: IsHeadlessMode() at
# chrome/browser/headless/headless_mode_util.cc:21 is
# HasSwitch(switches::kHeadless) and nothing in the tree reads the switch's
# VALUE -- the only kHeadless value read anywhere is prefs::kHeadlessMode, an
# unrelated integer pref. So --headless=new would behave identically and would
# imply a distinction this revision does not make.
#
# The other two are not cosmetic. A first-run dialog or a default-browser
# prompt on startup means the page under test is not the page that loads, and
# that failure arrives as a Playwright timeout, which looks like flake.
CHROME_FLAGS = ["--headless", "--no-first-run", "--no-default-browser-check"]

# The exact hint list the baseline was captured with. getHighEntropyValues
# returns these plus the three low-entropy values, so a baseline captured with
# this list holds ten keys. Any verification comparing against that baseline
# must request the SAME list -- a shorter request returns fewer keys and an
# equality check against the baseline can then only fail.
HIGH_ENTROPY = """
() => navigator.userAgentData.getHighEntropyValues(
    ["architecture","bitness","platformVersion","model","fullVersionList",
     "wow64","formFactors"])
"""

# content_shell emits none of these high-entropy hints, because
# ShellBrowserContext::GetClientHintsControllerDelegate() returns nullptr
# outside test harnesses; advertising Accept-CH does not change that. It does
# still send the low-entropy triple on subresource requests. Advertising them
# anyway keeps this script identical to the one Task 8 runs against `chrome`,
# where the high-entropy hints do arrive.
ACCEPT_CH = ["Sec-CH-UA-Arch", "Sec-CH-UA-Bitness", "Sec-CH-UA-Platform-Version",
             "Sec-CH-UA-Model", "Sec-CH-UA-Full-Version-List", "Sec-CH-UA-WoW64"]


def launch(config, shell=None, extra_flags=None, strict=False, debug_port=None):
    """Starts the browser and returns it once its DevTools port answers.

    Four details here exist because of failures that were actually observed,
    not defensively.

    A fixed `debug_port`, when given, replaces the ephemeral
    --remote-debugging-port=0 and is used directly instead of being read
    back from DevToolsActivePort. This exists for criteria that need the
    AutomationControlled runtime feature to stay OFF: runtime_features.cc
    reads the literal 0 as ChromeDriver's own launch pattern and
    force-enables that feature regardless of any blink-features flag, so a
    session that needs the feature off cannot use the default port. Callers
    should get the port from a just-closed ephemeral socket, not a literal --
    a hardcoded number lets a run attach to a previous instance still
    shutting down, which looks identical to the browser under test
    misbehaving. When `debug_port` is None, this path is untouched -- every
    other verification script depends on it.

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
    Popen itself raises FileNotFoundError naming the path if the binary does
    not exist, the process exiting during startup reports its exit code, and
    a process that lives but never opens a port reports the timeout. Three
    different causes should not arrive as one message. The messages name the
    binary for the same reason -- once two of them can be driven, "exited
    during startup" without a name does not say which one exited.

    Polling the endpoint rather than sleeping a fixed interval. A five-second
    sleep flaked one run in four, and an intermittently failing verification
    is worse than a slow one: it teaches people to re-run until green, and
    then it measures nothing.
    """
    binary = shell if shell is not None else SHELL
    name = os.path.basename(binary)
    flags = SHELL_FLAGS if extra_flags is None else list(extra_flags)

    env = {k: v for k, v in os.environ.items()
           if not k.startswith("CAMOU_CONFIG")}
    if config is not None:
        env["CAMOU_CONFIG"] = config
    if strict:
        env["CAMOU_CONFIG_STRICT"] = "1"

    profile = tempfile.mkdtemp(prefix="camoucrome-verify-")
    # stderr goes to a file, not a pipe. Criterion 6 reads it after the
    # process is gone, and a pipe would deadlock the child if Chromium's
    # startup noise filled the buffer. Each launch truncates it, so a read
    # only ever sees its own run.
    stderr_file = open(STDERR_LOG, "wb")
    # CDP is served on --remote-debugging-port by both binaries; only the
    # headless switch differs, which is what SHELL_FLAGS/CHROME_FLAGS carry.
    port_arg = f"--remote-debugging-port={debug_port if debug_port else 0}"
    proc = subprocess.Popen(
        [binary, "--no-sandbox", *flags,
         f"--user-data-dir={profile}", port_arg,
         "about:blank"],
        env=env, stdout=subprocess.DEVNULL, stderr=stderr_file)
    proc.profile_dir = profile

    port_file = pathlib.Path(profile) / "DevToolsActivePort"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            shutdown(proc)
            raise RuntimeError(
                f"{name} exited during startup, code {proc.returncode}")
        if debug_port is not None:
            # The port is already known -- no DevToolsActivePort read-back.
            try:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{debug_port}/json/version",
                    timeout=1).read()
                proc.cdp_port = debug_port
                return proc
            except Exception:
                pass
        elif port_file.exists():
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
    raise RuntimeError(f"{name} opened no DevTools endpoint within 30s")


def shutdown(proc):
    """Stops the browser and waits for it, so the next launch starts clean."""
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=15)
    shutil.rmtree(getattr(proc, "profile_dir", ""), ignore_errors=True)


def evaluate(proc, expressions, navigate_to=None, cdp=None):
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(
            f"http://127.0.0.1:{proc.cdp_port}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        if navigate_to is not None:
            # wait_until="load" so the subresource request the header
            # assertions read has certainly been issued.
            page.goto(navigate_to, wait_until="load")
        # Sent after navigation and before evaluation: these set inspector
        # agent state that the very next expression reads, and ordering them
        # here removes any question of a navigation clearing it.
        if cdp:
            cdp_session = context.new_cdp_session(page)
            for method, params in cdp:
                cdp_session.send(method, params)
        return [page.evaluate(e) for e in expressions]


def session(config, expressions, navigate_to=None, shell=None, extra_flags=None,
            strict=False, cdp=None, debug_port=None):
    """Runs one browser session; returns (values, error).

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
        proc = launch(config, shell=shell, extra_flags=extra_flags, strict=strict,
                      debug_port=debug_port)
        return evaluate(proc, expressions, navigate_to, cdp=cdp), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    finally:
        if proc is not None:
            shutdown(proc)
