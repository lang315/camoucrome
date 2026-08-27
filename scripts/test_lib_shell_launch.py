"""Freezes the argv launch() builds, for both binaries.

Task 8 gave launch() a `shell` and an `extra_flags` parameter. The plan's own
warning about that change is the reason this file exists: "a default that
quietly changed the flags would break every earlier verification at once."
verify_sp0.py and verify_sp1a.py call session() with the old signature, and
their 11 and 5 PASS results are only comparable to earlier runs if the process
they launch is byte-for-byte the one they launched before.

That is checkable without a browser, a checkout, or a build -- which is the
point, because the binaries live on another machine and the checkout is busy.
The default argv is written out as a literal rather than rebuilt from the
module's constants: a test that derives its expectation from the code under
test passes by construction and would not have caught the change it exists to
catch.

Run: python3 scripts/test_lib_shell_launch.py
"""

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# lib_shell imports playwright at module scope, and playwright is installed on
# the build machine's venv, not here. Only session()/evaluate() use it, and
# neither is exercised below, so a stub is enough -- and keeps this check
# runnable anywhere, which is what makes it get run.
if "playwright.sync_api" not in sys.modules:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        pkg = types.ModuleType("playwright")
        api = types.ModuleType("playwright.sync_api")
        api.sync_playwright = None
        pkg.sync_api = api
        sys.modules["playwright"] = pkg
        sys.modules["playwright.sync_api"] = api

import lib_shell  # noqa: E402


class FakeProc:
    """A process that reports itself dead the moment launch() first checks.

    That drives launch() down its "exited during startup" path, which returns
    in milliseconds instead of polling for a DevToolsActivePort that will never
    appear. The 30-second timeout is a real code path, but waiting it out here
    would buy nothing: the argv was already recorded by __init__.
    """

    def __init__(self, argv, env=None, stdout=None, stderr=None):
        self.argv = argv
        self.env = env
        self.returncode = 3

    def poll(self):
        return self.returncode

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return self.returncode


def capture_launch(**kwargs):
    """Calls launch() with Popen faked; returns (argv, env, error message)."""
    recorded = {}

    def fake_popen(argv, env=None, stdout=None, stderr=None):
        proc = FakeProc(argv, env)
        recorded["proc"] = proc
        return proc

    real_popen = lib_shell.subprocess.Popen
    lib_shell.subprocess.Popen = fake_popen
    try:
        lib_shell.launch(None, **kwargs)
        message = None
    except RuntimeError as exc:
        message = str(exc)
    finally:
        lib_shell.subprocess.Popen = real_popen
    return recorded["proc"].argv, recorded["proc"].env, message


def strip_profile(argv):
    """Drops the one argument that differs between runs by design."""
    return [a for a in argv if not a.startswith("--user-data-dir=")]


failures = []


def check(name, condition, detail=""):
    if condition:
        print(f"PASS  {name}")
    else:
        print(f"FAIL  {name}{': ' + detail if detail else ''}")
        failures.append(name)


# 1. The default argv, frozen. This is the exact command line verify_sp0.py and
#    verify_sp1a.py produced before Task 8 touched this file.
argv, env, message = capture_launch()
check("default argv is unchanged",
      strip_profile(argv) == [
          lib_shell.SHELL,
          "--no-sandbox",
          "--ozone-platform=headless",
          "--remote-debugging-port=0",
          "about:blank",
      ],
      f"got {strip_profile(argv)}")

check("default binary is content_shell",
      argv[0] == lib_shell.SHELL, f"got {argv[0]}")

check("startup failure names content_shell",
      message is not None and message.startswith("content_shell exited"),
      f"got {message!r}")

# 2. chrome mode. The flags differ; everything else must not.
argv, env, message = capture_launch(shell=lib_shell.CHROME,
                                    extra_flags=lib_shell.CHROME_FLAGS)
check("chrome argv is unchanged",
      strip_profile(argv) == [
          lib_shell.CHROME,
          "--no-sandbox",
          "--headless",
          "--no-first-run",
          "--no-default-browser-check",
          "--remote-debugging-port=0",
          "about:blank",
      ],
      f"got {strip_profile(argv)}")

check("chrome mode drops the content_shell headless switch",
      "--ozone-platform=headless" not in argv)

check("startup failure names chrome",
      message is not None and message.startswith("chrome exited"),
      f"got {message!r}")

# 3. The CAMOU_CONFIG scrubbing must survive the refactor for BOTH binaries.
#    It is the hardening most easily lost to a parameter change, and losing it
#    silently makes a leftover CAMOU_CONFIG_1 win over what a run intends.
os.environ["CAMOU_CONFIG_1"] = "leftover"
try:
    _, env, _ = capture_launch(shell=lib_shell.CHROME,
                               extra_flags=lib_shell.CHROME_FLAGS)
    check("CAMOU_CONFIG* is still scrubbed in chrome mode",
          not any(k.startswith("CAMOU_CONFIG") for k in env),
          f"leaked {[k for k in env if k.startswith('CAMOU_CONFIG')]}")
finally:
    del os.environ["CAMOU_CONFIG_1"]

print()
if failures:
    print(f"{len(failures)} FAILED: {', '.join(failures)}")
    sys.exit(1)
print(f"{7 - len(failures)} PASS")
