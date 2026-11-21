"""Verifies a ua: half-config refuses startup under CAMOU_CONFIG_STRICT.

A ua:osInfo without ua:platform (or the mirror) spoofs one channel and leaks the
real OS on the other. It was LOG(WARNING)-only; now it feeds the strict refusal
(sp1-navigator-identity-design.md:419-423). Non-strict behavior is unchanged.

Strict consistency (owner backlog 2026-11-21): CAMOU_CONFIG_STRICT=0 (or empty) is NOT strict, here as in
coherence_validator.cc and mask_config_internal.cc (the browser's own read used has_value(), so "0" still refused
a ua: half-config with exit 13); and a configuration that is not a JSON object under strict exits 13 from
BrowserMainLoop::EarlyInitialization instead of aborting with a CHECK (0x80000003) after a log line that said the
keys were ignored.

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
MALFORMED_REFUSAL = ("camoucfg: the configuration is malformed and CAMOU_CONFIG_STRICT is "
                     "set; refusing to start.")
IGNORED_LINE = "its keys are ignored and report real values"  # the non-strict wording

results = {}
notes = []


def failed(keys, label, exc):
    for key in keys:
        results[key] = False
    notes.append(f"{label}: {type(exc).__name__}: {exc}")


read_stderr = lib_shell.read_stderr  # one copy, in lib_shell


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


# chrome is a different startup path from content_shell: it reads the configuration earlier (the pref store, from
# CreateFeatureList, before BrowserMainLoop::EarlyInitialization), and with no --accept-lang flag. A row that must hold
# there runs on it, with the flags a raw or fhtool launch has (none beyond headless).
CHROME_ARGS = {"shell": lib_shell.CHROME, "extra_flags": lib_shell.CHROME_FLAGS + ["--enable-logging=stderr"]}


def expect_strict_exit_13(name, config, refusal=REFUSAL, raw=None, preset=None, forbid=None, browser=None):
    """`raw` replaces the JSON-encoded config (a malformed one); `refusal` must be in stderr, `forbid` must not be."""
    _, err = lib_shell.session(raw if raw is not None else json.dumps(config), ["1"], strict=True, preset=preset,
                               **(browser or {}))
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
    results[name] = refusal in stderr and not (forbid and forbid in stderr)
    if not results[name]:
        notes.append(f"{name}: exited 13 but stderr lacked the refusal "
                     f"(or held the forbidden text): {stderr!r}")


def expect_starts(name, config, strict, raw=None, must_log=None, browser=None):
    """The browser starts (err is None); `strict` is the CAMOU_CONFIG_STRICT value (a string) or False."""
    _, err = lib_shell.session(raw if raw is not None else json.dumps(config), ["1"], strict=strict, **(browser or {}))
    if err is not None:
        results[name] = False
        notes.append(f"{name}: expected a start, got {type(err).__name__}: {err}")
        return
    results[name] = True
    if must_log is not None:
        stderr, read_err = read_stderr()
        results[name] = read_err is None and must_log in stderr
        if not results[name]:
            notes.append(f"{name}: started, but stderr lacked {must_log!r}: {stderr!r}")


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

# (a) CAMOU_CONFIG_STRICT=0 is not strict. RED before the fix: the browser's own read was has_value(), so a
# half-config refused with exit 13 under "0". The same config under strict=1 still refuses (rows above).
expect_starts("UH-STRICT-ZERO ua:platform without ua:osInfo, CAMOU_CONFIG_STRICT=0, starts (not strict)",
              PLATFORM_ONLY, "0")
expect_starts("UH-STRICT-EMPTY ua:osInfo without ua:platform, CAMOU_CONFIG_STRICT='', starts (not strict)",
              OSINFO_ONLY, "")

# (b) A configuration that is not a JSON object under strict: exit 13 from EarlyInitialization, one strict-aware
# log, not the CHECK's 0x80000003 after "its keys are ignored". RED before the fix (the browser aborts).
expect_strict_exit_13("UH-BADJSON-STRICT '{' under strict exits 13 with a strict-aware refusal",
                      None, raw="{", refusal=MALFORMED_REFUSAL, forbid=IGNORED_LINE)
expect_strict_exit_13("UH-NOTOBJECT-STRICT '[]' under strict exits 13", None, raw="[]", refusal=MALFORMED_REFUSAL)
expect_strict_exit_13("UH-BADPRESET-STRICT a malformed preset under strict exits 13", FULL,
                      preset="{", refusal=MALFORMED_REFUSAL, forbid="preset is not a JSON object; ignored")
# The same on chrome (review of #242: the check was in EarlyInitialization, which chrome reaches after it has already
# CHECK-aborted in the pref store; content_shell never did). RED on a build with the check only there.
expect_strict_exit_13("UH-CHROME-BADJSON-STRICT chrome: '{' under strict, no --accept-lang, exits 13",
                      None, raw="{", refusal=MALFORMED_REFUSAL, forbid=IGNORED_LINE, browser=CHROME_ARGS)
expect_strict_exit_13("UH-CHROME-BADPRESET-STRICT chrome: a malformed preset under strict exits 13", FULL,
                      preset="{", refusal=MALFORMED_REFUSAL, browser=CHROME_ARGS)
expect_starts("UH-CHROME-STRICT-ZERO chrome: ua:platform without ua:osInfo, CAMOU_CONFIG_STRICT=0, starts",
              PLATFORM_ONLY, "0", browser=CHROME_ARGS)
expect_starts("UH-CHROME-BADJSON-STRICT-ZERO chrome: '{' under CAMOU_CONFIG_STRICT=0 starts", None, "0", raw="{",
              browser=CHROME_ARGS)
# non-strict is unchanged: a malformed configuration is ignored with the old wording, and the browser starts.
expect_starts("UH-BADJSON-LAX '{' without strict starts and says its keys are ignored", None, False,
              raw="{", must_log=IGNORED_LINE)
expect_starts("UH-BADJSON-STRICT-ZERO '{' under CAMOU_CONFIG_STRICT=0 starts (not strict)", None, "0", raw="{")

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)
