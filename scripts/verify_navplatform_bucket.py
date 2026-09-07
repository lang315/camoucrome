"""Verifies the navigator-platform-matches-os registry invariant.

An EXPLICIT navigator.platform that disagrees with the OS claimed in ua:osInfo
is reported at browser-process startup (ValidateAtStartup), and refuses startup
under CAMOU_CONFIG_STRICT. Like verify_sp5a.py this reads the browser's stderr
for the LOG(ERROR) line and discriminates a strict-mode exit 13 from a hang; one
row (NB-MOTIVATION) reads navigator.platform off the page to show the leak is
real and unchanged (report-not-repair -- the explicit value wins).

Structured like verify_sp5a.py: any fault in one session becomes FAIL lines,
never a traceback that discards results already collected.
"""

import json
import sys

import lib_shell

WIN_UA = "Windows NT 10.0; Win64; x64"
CROS_UA = "X11; CrOS x86_64 14541.0.0"
LINUX_UA = "X11; Linux x86_64"

# A Windows UA beside an explicit macOS navigator.platform -- the incoherence.
MISMATCH = {"ua:osInfo": WIN_UA, "navigator.platform": "MacIntel"}
# Both members of the "Linux x86_64" bucket accept that platform.
BUCKET_CROS = {"ua:osInfo": CROS_UA, "navigator.platform": "Linux x86_64"}
BUCKET_LINUX = {"ua:osInfo": LINUX_UA, "navigator.platform": "Linux x86_64"}
COHERENT = {"ua:osInfo": WIN_UA, "navigator.platform": "Win32"}
# navigator.platform set but no OS claimed: nothing to disagree with.
EXPLICIT_NO_UA = {"navigator.platform": "FreeBSD amd64"}

# The violation LOG(ERROR), matched as a substring. Same format as every
# registry Violation (coherence_validator.cc's ValidateAtStartup loop): keep in
# sync with it.
MISMATCH_LINE = (
    "camoucfg: invariant 'navigator-platform-matches-os' violated. "
    "'navigator.platform' is 'MacIntel', which disagrees with 'ua:osInfo'. "
    "It should be 'Win32'.")
REFUSAL = ("camoucfg: configuration is incoherent and CAMOU_CONFIG_STRICT is "
           "set; refusing to start.")

results = {}
notes = []


def failed(keys, label, exc):
    for key in keys:
        results[key] = False
    notes.append(f"{label}: {type(exc).__name__}: {exc}")


def read_stderr():
    """Guarded read of this session's browser stderr (verify_sp5a.py's helper).
    launch() opens the log 'wb', truncating, so each read is its own session."""
    try:
        with open(lib_shell.STDERR_LOG, "rb") as handle:
            return handle.read().decode("utf-8", "replace"), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc


def stderr_after(config):
    _, err = lib_shell.session(json.dumps(config), ["1"])
    if err is not None:
        return None, err
    return read_stderr()


def expect_line(name, config, present, absent=()):
    stderr, err = stderr_after(config)
    if err is not None:
        failed([name], f"{name} session", err)
        return
    results[name] = all(s in stderr for s in present) and all(
        s not in stderr for s in absent)
    if not results[name]:
        notes.append(f"{name}: stderr={stderr!r}")


def expect_strict_exit_13(name, config):
    _, err = lib_shell.session(json.dumps(config), ["1"], strict=True)
    if err is None:
        results[name] = False
        notes.append(f"{name}: browser started under CAMOU_CONFIG_STRICT=1 "
                     "with an incoherent navigator.platform; expected exit 13")
        return
    if "exited during startup" not in str(err):
        results[name] = False
        notes.append(f"{name}: not an exit-during-startup failure: "
                     f"{type(err).__name__}: {err}")
        return
    code_text = str(err).rsplit("code ", 1)[-1]
    try:
        code = int(code_text)
    except ValueError:
        code = None
    if code != 13:
        results[name] = False
        notes.append(f"{name}: exited, but with the wrong code: {err}")
        return
    stderr, read_err = read_stderr()
    if read_err is not None:
        failed([name], f"{name} stderr read", read_err)
        return
    results[name] = REFUSAL in stderr
    if not results[name]:
        notes.append(f"{name}: exited 13 but stderr lacked the refusal: "
                     f"{stderr!r}")


# --- NB-MOTIVATION: the leak is real and unchanged (page-side) ---
# navigator.platform reads "MacIntel" under a Windows UA both before and after:
# the explicit value wins over the derive, and this invariant reports rather
# than repairs it. "MacIntel" != any Windows value is the differ-guarantee.
NB_MOT = ("NB-MOTIVATION explicit navigator.platform wins under a mismatched UA "
          "(unchanged by this slice)")
vals, err = lib_shell.session(json.dumps(MISMATCH), ["navigator.platform"])
if err is not None:
    failed([NB_MOT], "motivation session", err)
else:
    results[NB_MOT] = vals[0] == "MacIntel"
    notes.append(f"NB-MOTIVATION: navigator.platform -> {vals[0]!r}")

# --- The rows this slice flips RED -> GREEN ---
expect_line("NB-MISMATCH-LOG mismatched navigator.platform logs, names Win32",
            MISMATCH, present=[MISMATCH_LINE])
expect_strict_exit_13(
    "NB-MISMATCH-STRICT mismatched navigator.platform under strict exits 13",
    MISMATCH)

# --- The bucket: both Linux and ChromeOS accept "Linux x86_64" ---
expect_line("NB-BUCKET-CROS ChromeOS UA accepts Linux x86_64 (bucket)",
            BUCKET_CROS, present=[], absent=["navigator-platform-matches-os"])
expect_line("NB-BUCKET-LINUX Linux UA accepts Linux x86_64 (bucket)",
            BUCKET_LINUX, present=[], absent=["navigator-platform-matches-os"])

# --- Invariant cases: coherent and no-OS-claimed are silent ---
expect_line("NB-COHERENT Windows UA with Win32 logs no line",
            COHERENT, present=[], absent=["navigator-platform-matches-os"])
expect_line("NB-EXPLICIT-NO-UA navigator.platform without any UA logs no line",
            EXPLICIT_NO_UA, present=[], absent=["navigator-platform-matches-os"])

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)
