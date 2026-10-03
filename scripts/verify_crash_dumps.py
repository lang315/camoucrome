"""A crash must leave no dump anywhere, for a launch that bypasses the clients.

Backlog item 5 (roadmap 2026-10-02): crashpad writes a minidump on every crash,
and on Windows the dump holds the process's whole environment block, so
CAMOU_CONFIG -- the identity -- lands on disk next to the machine's own
variables (measurements/2026-10-03-windows-substrate.md, "Crashpad on
Windows"). The clients point BREAKPAD_DUMP_LOCATION at a directory they remove
on close; that does nothing for a launch that does not go through them, or a
client killed before close. The lever measured here is in C++
(patches/crashpad-no-dumps.patch): the crashpad handler is told never to write
a report, and still terminates the process with the exception's own code.

So the browser is started directly through lib_shell, with no
BREAKPAD_DUMP_LOCATION, a marker inside the config, and crashed two ways:

  C1  a renderer crash (chrome://crash); the browser must survive it.
  C2  a browser crash (the DevTools `Browser.crash` command; navigating to
      chrome://inducebrowsercrashforrealz does nothing under --headless); the
      process must exit with a crash code, not 0 and not by hanging.

After each, every place a dump could land is searched for files created since
the launch: the profile, the temp directory, the default crash database
(Linux: ~/.config/chromium/Crash Reports, where the RED dump landed, shared by
every profile), and on Windows the default Chromium profile's Crashpad,
%LOCALAPPDATA%\\CrashDumps and both Windows Error
Reporting stores (a crash crashpad does not take goes to WER, which is worse:
outside the profile and possibly uploaded). A row passes only if the crash is
seen to happen AND no new dump file exists AND the marker is in no new file. A
crash that did not happen is NOT MEASURED, never PASS.

RED is the same script against a build without the lever: dumps appear and
hold the marker (Windows: as UTF-16LE).

Env: CAMOU_OUT / CAMOU_EXE as for every lib_shell script.
"""

import os
import pathlib
import sys
import tempfile
import time

import lib_shell

EXPECTED = 2
MARKER = "ZQXJ7731CRASHMARK"
CONFIG = '{"ua:osInfo": "%s"}' % MARKER
DUMP_SUFFIXES = (".dmp", ".mdmp", ".hdmp")
WINDOWS = os.name == "nt"


def roots(profile):
    """Every directory a dump could land in, with whether ANY new file there
    counts. WER writes reports and dumps under several names, so there every
    file counts; a crashpad database rewrites settings.dat on every launch, so
    there only dump files do."""
    found = [(pathlib.Path(profile), False),
             (pathlib.Path(tempfile.gettempdir()), False)]
    if WINDOWS:
        local = pathlib.Path(os.environ["LOCALAPPDATA"])
        data = pathlib.Path(os.environ.get("ProgramData", r"C:\ProgramData"))
        found += [(local / "Chromium" / "User Data" / "Crashpad", False),
                  (local / "CrashDumps", True),
                  (local / "Microsoft" / "Windows" / "WER", True),
                  (data / "Microsoft" / "Windows" / "WER" / "ReportQueue", True),
                  (data / "Microsoft" / "Windows" / "WER" / "ReportArchive", True)]
    else:
        found.append((pathlib.Path.home() / ".config" / "chromium" / "Crash Reports", False))
    return found


def new_dumps(profile, since):
    """(dump files created since `since`, how many of them hold the marker)."""
    dumps = set()
    for root, any_file in roots(profile):
        for top, _, names in os.walk(root):  # silently skips what it cannot list
            for n in names:
                f = pathlib.Path(top) / n
                try:
                    if f.stat().st_mtime < since:
                        continue
                except OSError:
                    continue
                if any_file or f.suffix.lower() in DUMP_SUFFIXES:
                    dumps.add(f)
    dumps = sorted(dumps)
    marked = 0
    for f in dumps:
        try:
            data = f.read_bytes()[:64 << 20]
        except OSError:
            continue
        if MARKER.encode() in data or MARKER.encode("utf-16-le") in data:
            marked += 1
    return dumps, marked


def crashed_exit(code):
    """A crash exit, not a clean one: an NTSTATUS exception code on Windows, a
    signal on POSIX."""
    return code is not None and (code >= 0x80000000 if WINDOWS else code < 0)


def crash(url):
    """One launch, one crash: a renderer crash at `url`, or a browser crash
    when `url` is None. Returns (crash seen, detail, profile, since, proc)."""
    from playwright.sync_api import sync_playwright

    since = time.time() - 1
    proc = lib_shell.launch(CONFIG, shell=lib_shell.CHROME,
                            extra_flags=lib_shell.CHROME_FLAGS, sandbox=WINDOWS)
    crashed = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{proc.cdp_port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.on("crash", lambda _: crashed.append(True))
            if url is None:
                try:
                    browser.new_browser_cdp_session().send("Browser.crash")
                except Exception:  # noqa: BLE001 - the crash is the expected outcome
                    pass
                try:
                    proc.wait(timeout=20)
                except Exception:  # noqa: BLE001
                    pass
            else:
                try:
                    page.goto(url, timeout=10000)
                except Exception:  # noqa: BLE001 - the crash is the expected outcome
                    pass
                deadline = time.monotonic() + 5
                while not crashed and time.monotonic() < deadline:
                    page.wait_for_timeout(100)
    except Exception:  # noqa: BLE001 - a dropped CDP connection is the browser crash
        if url is None:
            try:
                proc.wait(timeout=20)
            except Exception:  # noqa: BLE001
                pass
    if url is None:
        code = proc.poll()
        seen = crashed_exit(code)
        detail = f"exit code {hex(code) if WINDOWS and code is not None else code}"
    else:
        alive = proc.poll() is None
        seen = bool(crashed) and alive
        detail = f"renderer crashed {bool(crashed)}, browser alive {alive}"
    time.sleep(3)  # the handler writes after the crash; count after it has had time
    return seen, detail, proc.profile_dir, since, proc


def main():
    os.environ.pop("BREAKPAD_DUMP_LOCATION", None)  # the scenario is no client
    print(f"binary: {lib_shell.CHROME}")
    rows = [("C1", "renderer crash", "chrome://crash"),
            ("C2", "browser crash", None)]
    passed = failed = 0
    for rid, name, url in rows:
        proc = None
        try:
            seen, detail, profile, since, proc = crash(url)
            dumps, marked = new_dumps(profile, since)
            for f in dumps:
                print(f"    new file: {f} ({f.stat().st_size} bytes)")
            if not seen:
                status = "NOT MEASURED"
            elif dumps or marked:
                status = "FAIL"
            else:
                status = "PASS"
            print(f"{status} {rid} {name}: {detail}; new dumps {len(dumps)}, "
                  f"holding the marker {marked}")
        except Exception as exc:  # noqa: BLE001 - any fault is a FAIL row
            status = "FAIL"
            print(f"FAIL {rid} {name}: {exc!r}")
        finally:
            if proc is not None:
                lib_shell.shutdown(proc)
        passed += status == "PASS"
        failed += status != "PASS"
    print(f"{passed} PASS {failed} FAIL (expected {EXPECTED} PASS)")
    return 0 if passed == EXPECTED and failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
