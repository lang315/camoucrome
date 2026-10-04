#!/usr/bin/env python3
"""The named Windows verify set (roadmap step 1) and its runner.

Each entry is a verify script, the row count it must print (or the ALL_PASS line
for the one script whose verdict is a line), and its RED kind:
  stock  run against the host's stock chrome.exe (CAMOU_EXE), which is the same
         version on the same machine and ignores CAMOU_CONFIG, so the script
         must exit non-zero with at least one FAIL row
  own    stock passes these rows too (worker parity, fallback); the script's own
         control rows are its RED, so red mode skips it and says so
red first, then green; a GREEN counts only after its RED was seen.

Run on the Windows host from the tree's scripts directory, with the layout env
the client verifies need (CAMOU_OUT, CAMOU_CLIENT, CAMOU_VENV, the driver and
probe variables, PLAYWRIGHT_NODEJS_PATH):
  python windows_verify_set.py red      # CAMOU_EXE := the stock chrome.exe
  python windows_verify_set.py green
  python windows_verify_set.py green --only verify_sp2b.py,verify_sp4a.py
Each script's output is kept in <tempdir>/windows-verify-set/<mode>/<script>.log.
"""
import collections
import os
import pathlib
import re
import subprocess
import sys
import tempfile

# known_fail: row-name prefixes that must FAIL in green (a documented gap, not a pass)
Entry = collections.namedtuple("Entry", "script rows red known_fail", defaults=((),))

# Row counts: the script's own EXPECTED where it asserts one, otherwise its row
# count read from the source (spec section 2). The driver's verdict is a line.
SET = [
    Entry("verify_windows_sandbox_env.py", 7, "stock"),
    Entry("verify_windows_client.py", 11, "stock"),
    Entry("verify_sp2b.py", 3, "stock"),
    Entry("verify_sp6b_launcher.py", 5, "stock"),
    Entry("verify_sp6b_driver.py", "ALL_PASS", "stock"),
    Entry("verify_crash_dumps.py", 2, "stock"),
    # Prints a row per config only when it fails (verify_sp6b_generator.py:158);
    # green is its RED row plus "36/36 PASS" and ALL_PASS, which it prints only
    # when all 36 pass and the generated count is N per OS.
    Entry("verify_sp6b_generator.py", "ALL_PASS", "stock"),
    Entry("verify_d_pointer_touch.py", 5, "stock"),
    Entry("verify_sp1b.py", 8, "stock"),
    Entry("verify_sp3b.py", 9, "stock"),
    Entry("verify_sp4a.py", 6, "stock"),
    Entry("verify_metric_jitter.py", 11, "stock"),
    Entry("verify_audio_ii.py", 4, "stock"),
    Entry("verify_ua_halfconfig_reject.py", 6, "stock"),
    Entry("verify_sp5b_domain.py", 4, "stock"),
    Entry("verify_webgl_pairing.py", 9, "stock"),
    Entry("verify_webgl_capability_identity.py", 13, "stock"),
    Entry("verify_navplatform_bucket.py", 7, "stock"),
    Entry("verify_fonts_ii.py", 6, "stock"),
    Entry("verify_windows_fonts.py", 5, "stock"),
    # O2 (the Linux-claim RED) fails on the Windows build because the share/canShare/bluetooth gate is
    # IS_LINUX-only code (measured 2026-10-04: the Linux-claim sub-run differed from the host only in
    # UA/platform leaves) -- filed as a backlog item; delete known_fail when the gate lands.
    Entry("verify_host_oracle.py", 4, "stock", known_fail=("O2",)),
]

ROW = re.compile(r"^(?:(PASS|FAIL)\s+\S|\S+: (PASS|FAIL)\s*$)")
STOCK_APP = r"C:\Program Files\Google\Chrome\Application"


def fail_names(stdout):
    """The text after FAIL (or before `: FAIL`) of every FAIL row."""
    names = []
    for line in stdout.splitlines():
        m = ROW.match(line)
        if m and (m.group(1) or m.group(2)) == "FAIL":
            names.append(line.split(":")[0] if m.group(2) else line.split(None, 1)[1].strip())
    return names


def count_rows(stdout):
    """(PASS rows, FAIL rows). A row is a line that starts with PASS/FAIL and a
    name, or `<id>: PASS|FAIL`. Summaries ("2 PASS 1 FAIL"), notes and the
    driver's indented detail lines are not rows."""
    passed = failed = 0
    for line in stdout.splitlines():
        m = ROW.match(line)
        if m:
            if (m.group(1) or m.group(2)) == "PASS":
                passed += 1
            else:
                failed += 1
    return passed, failed


def judge(mode, entry, returncode, stdout):
    passed, failed = count_rows(stdout)
    if mode == "red":
        if entry.red == "own":
            return True, "own RED: the script's control rows; not run against stock"
        ok = returncode != 0 and failed > 0
        return ok, f"rc={returncode} {passed} PASS {failed} FAIL (want rc!=0 and a FAIL row)"
    if entry.rows == "ALL_PASS":
        ok = returncode == 0 and "ALL_PASS" in stdout.splitlines()
        return ok, f"rc={returncode} ALL_PASS line {'present' if ok else 'missing'}"
    if entry.known_fail:
        names = fail_names(stdout)
        ok = (all(sum(n.startswith(k) for n in names) == 1 for k in entry.known_fail)
              and len(names) == len(entry.known_fail) and passed == entry.rows - len(entry.known_fail))
        return ok, (f"rc={returncode} {passed} PASS {failed} FAIL (want {entry.rows - len(entry.known_fail)} PASS "
                    f"and exactly the known-failing rows {', '.join(entry.known_fail)} FAIL)")
    ok = returncode == 0 and failed == 0 and passed == entry.rows
    return ok, f"rc={returncode} {passed} PASS {failed} FAIL (want {entry.rows} PASS)"


def stock_version(app_dir):
    versions = [p.name for p in pathlib.Path(app_dir).iterdir()
                if p.is_dir() and re.fullmatch(r"\d+\.\d+\.\d+\.\d+", p.name)]
    if len(versions) != 1:
        sys.exit(f"stock Chrome under {app_dir} has {versions or 'no'} version directories; want exactly one")
    return versions[0]


def pin_tag(client):
    for line in (pathlib.Path(client) / "upstream.env").read_text().splitlines():
        if line.startswith("CHROMIUM_TAG="):
            return line.split("=", 1)[1].strip().strip('"')
    sys.exit("upstream.env has no CHROMIUM_TAG")


def select(only_arg):
    """Select entries by --only arg. None → all of SET; string → comma-separated
    names (whitespace stripped). Raises SystemExit if a name is not in SET or if
    no entries are selected."""
    if only_arg is None:
        return SET
    # Split by comma and strip whitespace around each name
    requested = [name.strip() for name in only_arg.split(",")]
    # Check all requested names exist in SET
    scripts = {e.script for e in SET}
    unknown = [name for name in requested if name not in scripts]
    if unknown:
        sys.exit(f"unknown entries: {', '.join(unknown)}")
    # Select matching entries, preserving SET order
    result = [e for e in SET if e.script in requested]
    if not result:
        sys.exit("no entries selected")
    return result


def main(argv):
    if len(argv) < 2 or argv[1] not in ("red", "green"):
        sys.exit(__doc__)
    mode = argv[1]
    only_arg = argv[argv.index("--only") + 1] if "--only" in argv else None
    here = pathlib.Path(__file__).resolve().parent
    client = os.environ.get("CAMOU_CLIENT", str(here.parent))
    app = os.environ.get("CAMOU_STOCK_APP", STOCK_APP)
    have, want = stock_version(app), pin_tag(client)
    if have != want:
        sys.exit(f"stock Chrome is {have}, the pin is {want}: the control is not the pin's version")
    env = dict(os.environ, CAMOU_SHELL="chrome", CAMOU_STOCK_EXE=os.path.join(app, "chrome.exe"))
    if mode == "red":
        env["CAMOU_EXE"] = os.path.join(app, "chrome.exe")
    logs = pathlib.Path(tempfile.gettempdir()) / "windows-verify-set" / mode
    logs.mkdir(parents=True, exist_ok=True)
    print(f"mode={mode} stock={have} pin={want} exe={env.get('CAMOU_EXE', '(fork via CAMOU_OUT)')}")
    entries = select(only_arg)
    good = 0
    for e in entries:
        if mode == "red" and e.red == "own":
            ok, why = judge(mode, e, 0, "")
        else:
            try:
                p = subprocess.run([sys.executable, str(here / e.script)], cwd=here, env=env,
                                   capture_output=True, text=True, timeout=1800)
                out, err, rc = p.stdout, p.stderr, p.returncode
                ok, why = judge(mode, e, rc, out)
            except subprocess.TimeoutExpired as t:
                out, err = (x.decode("utf-8", "replace") if isinstance(x, bytes) else x or "" for x in (t.stdout, t.stderr))
                ok, why = False, "timeout after 1800 s"
            (logs / f"{e.script}.log").write_text(out + "\n--- stderr ---\n" + err, encoding="utf-8")
        good += ok
        print(f"{'OK  ' if ok else 'BAD '} {e.script}: {why}", flush=True)
    print(f"{good}/{len(entries)} entries OK ({mode})")
    return 0 if good == len(entries) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
