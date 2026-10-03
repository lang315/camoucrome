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
import subprocess
import sys
import tempfile
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
# Every check that ran, so the final line counts what happened instead of a
# literal. The count used to be written as `7 - len(failures)`, which stops
# being the number of checks the moment one is added -- a report that states a
# number it did not measure.
results = []


def check(name, condition, detail=""):
    results.append(name)
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

# 3b. The sandbox. `--no-sandbox` was unconditional, and on Windows that is the
#     one argv under which the project's only Windows-specific bug was
#     invisible: CreateFilteredEnvironment() strips every CAMOU_* variable from
#     sandboxed children, so a renderer-consumed key read the real value under
#     the default sandbox and the spoofed one under --no-sandbox
#     (measurements/2026-09-24-review-triage.md:183). A verification that cannot
#     launch sandboxed cannot measure that fix at all.
#
#     The default stays False so every earlier call's argv is byte-identical --
#     the frozen argv above is the guard for that.
argv, _, _ = capture_launch(sandbox=True)
check("sandbox=True drops --no-sandbox and changes nothing else",
      strip_profile(argv) == [
          lib_shell.SHELL,
          "--ozone-platform=headless",
          "--remote-debugging-port=0",
          "about:blank",
      ],
      f"got {strip_profile(argv)}")

argv, _, _ = capture_launch(sandbox=False)
check("sandbox=False is the argv every earlier run used",
      "--no-sandbox" in argv and argv.index("--no-sandbox") == 1,
      f"got {strip_profile(argv)}")

# 4. Where the binaries are. _binaries() is the single place that resolves the
#    two binary paths, so these cases are the whole surface for THOSE two; the
#    rest of the box's layout is layout()'s, checked in section 5. They pass
#    an environment and an os.name explicitly rather than mutating the real
#    ones: the constants are resolved once at import, so a test that set
#    os.environ here would be measuring nothing.
DEFAULT_OUT = os.path.expanduser("~/chromium/src/out/Default")

out, shell, chrome = lib_shell._binaries({}, "posix")
check("no CAMOU_OUT keeps the paths every earlier run used",
      (out, shell, chrome) == (DEFAULT_OUT,
                               f"{DEFAULT_OUT}/content_shell",
                               f"{DEFAULT_OUT}/chrome"),
      f"got {(out, shell, chrome)}")

_, shell, chrome = lib_shell._binaries({"CAMOU_OUT": "/w/out/Release"}, "posix")
check("CAMOU_OUT moves both binaries",
      (shell, chrome) == ("/w/out/Release/content_shell",
                          "/w/out/Release/chrome"),
      f"got {(shell, chrome)}")

# CAMOU_EXE is not new here: eleven client-driven verify scripts already read
# it to aim at an extracted release archive. lib_shell honouring the same
# variable is what lets one setting point both families at one binary -- and it
# names a file, so it must not drag content_shell along with it.
_, shell, chrome = lib_shell._binaries(
    {"CAMOU_OUT": "/w/out/Release", "CAMOU_EXE": "/extracted/chrome"}, "posix")
check("CAMOU_EXE wins for chrome and leaves content_shell alone",
      (shell, chrome) == ("/w/out/Release/content_shell", "/extracted/chrome"),
      f"got {(shell, chrome)}")

# The suffix only. The separator comes from the HOST's os.path.join, so this
# check cannot assert a whole Windows path while running on Linux, and
# pretending otherwise would be a false green.
_, shell, chrome = lib_shell._binaries({"CAMOU_OUT": r"D:\out\Release"}, "nt")
check("nt names chrome.exe and content_shell.exe",
      (shell.endswith("content_shell.exe"), chrome.endswith("chrome.exe"))
      == (True, True),
      f"got {(shell, chrome)}")

# 5. layout(), and why it is a function. A module constant would latch the
#    environment at lib_shell's own import, whenever that happens to be, and
#    decide CLIENT for every script imported later in the same process. That is
#    not hypothetical: it shipped for one commit and `pytest -q scripts/` went
#    from 60 passed to a collection error, because test_verify_host_oracle.py
#    sets CAMOU_CLIENT and then imports the script under test, while this file
#    had already imported lib_shell.
ENV = {"CAMOU_VENV": "/v", "PLAYWRIGHT_NODEJS_PATH": "/n",
       "CAMOU_CLIENT": "/c", "CAMOU_FONTS_DIR": "/f"}
L = lib_shell.layout(ENV)
check("layout honours every override it documents",
      (L.py, L.node, str(L.client), L.fonts_dir) == ("/v/bin/python3", "/n", "/c", "/f"),
      f"got {(L.py, L.node, str(L.client), L.fonts_dir)}")

L = lib_shell.layout({})
check("layout's defaults are the paths those scripts used to compute",
      (L.home, L.py, L.node, str(L.client), L.fonts_dir)
      == (os.path.expanduser("~"),
          os.path.expanduser("~/camoucrome-verify/venv/bin/python3"),
          os.path.expanduser("~/camoucrome-driver/node"),
          os.path.expanduser("~/camoucrome-client"),
          os.path.expanduser("~/camoucrome-client/fonts")),
      f"got {(L.home, L.py, L.node, str(L.client), L.fonts_dir)}")

check("fonts follow CAMOU_CLIENT when CAMOU_FONTS_DIR is unset",
      lib_shell.layout({"CAMOU_CLIENT": "/c"}).fonts_dir == "/c/fonts",
      f"got {lib_shell.layout({'CAMOU_CLIENT': '/c'}).fonts_dir}")

# The regression itself: a later reader of os.environ must win over an earlier
# import of this module.
os.environ["CAMOU_CLIENT"] = "/set/after/import"
try:
    check("layout reads os.environ when called, not when lib_shell was imported",
          str(lib_shell.layout().client) == "/set/after/import",
          f"got {lib_shell.layout().client}")
finally:
    del os.environ["CAMOU_CLIENT"]

# 7. Importable without playwright. Eleven verify scripts drive the browser
#    through the client in a subprocess and keep playwright out of their own
#    process; they can only read lib_shell's paths if importing the module does
#    not drag playwright in. A subprocess with playwright blocked is the only
#    honest way to check that here, because playwright IS installed on this
#    machine -- the stub above never runs, so it proves nothing about it.
BLOCK = f"""
import sys


class Block:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] == "playwright":
            raise ImportError("playwright is not installed here")


sys.meta_path.insert(0, Block())
sys.path.insert(0, {os.path.dirname(os.path.abspath(__file__))!r})
import lib_shell
print(lib_shell.CHROME)
"""
done = subprocess.run([sys.executable, "-c", BLOCK], capture_output=True, text=True)
check("lib_shell imports with no playwright installed",
      (done.returncode, done.stdout.strip())
      == (0, os.path.expanduser("~/chromium/src/out/Default/chrome")),
      f"exit {done.returncode}, out {done.stdout.strip()!r}, "
      f"err {done.stderr.strip().splitlines()[-1:]}")

# 8. The stderr log. This check is only sharp on a host whose temp directory is
#    not /tmp -- a Mac, where gettempdir() is under /var/folders -- because a
#    hardcoded "/tmp" and the stdlib answer coincide on Linux. Run it there
#    before believing it.
check("the stderr log is in the platform temp dir and carries the pid",
      (os.path.dirname(lib_shell.STDERR_LOG) == tempfile.gettempdir(),
       str(os.getpid()) in os.path.basename(lib_shell.STDERR_LOG))
      == (True, True),
      f"got {lib_shell.STDERR_LOG} (tempdir {tempfile.gettempdir()})")

print()
if failures:
    print(f"{len(failures)} FAILED of {len(results)}: {', '.join(failures)}")
    sys.exit(1)
print(f"{len(results)} PASS")
