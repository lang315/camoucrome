"""Verifies a ua: half-config refuses startup under CAMOU_CONFIG_STRICT.

A ua:osInfo without ua:platform (or the mirror) spoofs one channel and leaks the
real OS on the other. It was LOG(WARNING)-only; now it feeds the strict refusal
(sp1-navigator-identity-design.md:419-423). Non-strict behavior is unchanged.

Like verify_sp5a.py: reads the browser's stderr for the WARNING/refusal lines and
discriminates a strict-mode exit 13 from a hang. Any fault in one session becomes
a FAIL line, never a traceback that discards results already collected.
"""

import json
import sys

import lib_shell

OSINFO_ONLY = {"ua:osInfo": "Windows NT 10.0; Win64; x64"}
PLATFORM_ONLY = {"ua:platform": "Windows"}
FULL = {"ua:osInfo": "Windows NT 10.0; Win64; x64", "ua:platform": "Windows"}
# A lone wrong-typed metadata key, and nothing else. ua:mobile is a bool key
# given a string, so the type-aware UaMetadataKeyHasValue returns false ->
# any_metadata_configured is false -> branch 1 does NOT fire -> nothing is
# spoofed -> starts under strict. This is a real type-blindness discriminator:
# reverting UaMetadataKeyHasValue to a type-blind HasKey() would make
# any_metadata_configured true, fire branch 1, and refuse under strict -> RED.
# (The previous config set ua:osInfo+ua:platform validly, so neither branch
# depended on ua:mobile's type at all -- a false control.)
TYPE_BLIND = {"ua:mobile": "yes"}

# ua:osInfo set, ua:platform absent -> branch 2.
OSINFO_WARN = ("camoucfg: 'ua:osInfo' is set but 'ua:platform' is not, so "
               "navigator.userAgentData.platform and Sec-CH-UA-Platform still "
               "report this machine's real")
# ua:platform set, ua:osInfo absent -> branch 1.
PLATFORM_WARN = ("camoucfg: 'ua:platform' is set but 'ua:osInfo' is not set to a "
                 "value this build can read")
REFUSAL = ("camoucfg: configuration is incoherent and CAMOU_CONFIG_STRICT is "
           "set; refusing to start.")

results = {}
notes = []


def failed(keys, label, exc):
    for key in keys:
        results[key] = False
    notes.append(f"{label}: {type(exc).__name__}: {exc}")


def read_stderr():
    try:
        with open(lib_shell.STDERR_LOG, "rb") as handle:
            return handle.read().decode("utf-8", "replace"), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc


def expect_starts_with_warning(name, config, warning):
    """Non-strict: browser starts (err is None) and the warning is logged."""
    _, err = lib_shell.session(json.dumps(config), ["1"])
    if err is not None:
        failed([name], f"{name} session", err)
        return
    stderr, read_err = read_stderr()
    if read_err is not None:
        failed([name], f"{name} stderr read", read_err)
        return
    results[name] = warning in stderr
    if not results[name]:
        notes.append(f"{name}: warning absent; stderr={stderr!r}")


def expect_starts_silent(name, config):
    """Strict, but coherent: browser starts and does NOT refuse."""
    _, err = lib_shell.session(json.dumps(config), ["1"], strict=True)
    if err is None:
        results[name] = True
        return
    results[name] = False
    notes.append(f"{name}: expected start under strict, got "
                 f"{type(err).__name__}: {err}")


def expect_strict_exit_13(name, config):
    _, err = lib_shell.session(json.dumps(config), ["1"], strict=True)
    if err is None:
        results[name] = False
        notes.append(f"{name}: browser started under CAMOU_CONFIG_STRICT=1 with "
                     "a ua: half-config; expected exit 13")
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


# The two rows this slice flips RED -> GREEN.
expect_strict_exit_13(
    "UH-OSINFO-STRICT ua:osInfo without ua:platform, strict, exits 13",
    OSINFO_ONLY)
expect_strict_exit_13(
    "UH-PLATFORM-STRICT ua:platform without ua:osInfo, strict, exits 13",
    PLATFORM_ONLY)

# Regression: non-strict is unchanged -- still warns, still starts.
expect_starts_with_warning(
    "UH-OSINFO-WARN ua:osInfo alone, non-strict, warns and starts",
    OSINFO_ONLY, OSINFO_WARN)
expect_starts_with_warning(
    "UH-PLATFORM-WARN ua:platform alone, non-strict, warns and starts",
    PLATFORM_ONLY, PLATFORM_WARN)

# A coherent full pair, and the type-blindness guard, both start under strict.
expect_starts_silent(
    "UH-FULL-COHERENT ua:osInfo + ua:platform, strict, starts", FULL)
expect_starts_silent(
    "UH-TYPE-BLIND-GUARD lone wrong-typed ua:mobile is not a half-config "
    "(type-aware presence, not HasKey), strict, starts", TYPE_BLIND)

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)
