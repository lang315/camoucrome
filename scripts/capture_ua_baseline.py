"""Captures the unspoofed UA surface of the CURRENT build.

Must run before the producer patch lands. After Task 4 there is no way to
produce this file again without rebuilding from the pinned base revision,
and the no-config regression check in Task 6 is worth nothing without it.

--shell selects which binary to capture. The provenance block is DERIVED from
that choice and from what was actually observed, never asserted: an earlier
version hardcoded binary="content_shell" and a known_absent list claiming the
sec-ch-ua-* headers were missing. Run against `chrome`, which emits them, that
block would have described the capture as the opposite of what it contained --
a baseline file that misreports its own subject is worse than no baseline,
because every later comparison inherits the error while reading as evidence.
"""

import argparse
import json
import os
import subprocess
import sys

import echo_server
import lib_shell
from lib_shell import ACCEPT_CH, HIGH_ENTROPY

# What each binary is, in the terms a reader of the baseline needs: which
# function produced the values in the file. Unknown binaries are refused
# rather than given a default, because the default would be a false claim
# about source code that was never read.
#
# Verified by reading the checkout at 0e8d4a9268 on 2026-08-27.
PRODUCERS = {
    "content_shell": {
        "flags": None,  # lib_shell.SHELL_FLAGS
        "ua_string_producer":
            "content/shell/browser/shell_content_browser_client.cc:732 "
            "ShellContentBrowserClient::GetUserAgent -> "
            "embedder_support::BuildUnifiedPlatformUserAgentFromProduct, with "
            "product built from CONTENT_SHELL_MAJOR_VERSION (hence Chrome/999)",
        "metadata_producer":
            "content/shell/browser/shell_content_browser_client.cc:348 "
            "GetShellUserAgentMetadata -- content_shell's own, NOT "
            "embedder_support::GetUserAgentMetadata",
    },
    "chrome": {
        "flags": lib_shell.CHROME_FLAGS,
        "ua_string_producer":
            "chrome/browser/chrome_content_browser_client.cc:7696 "
            "ChromeContentBrowserClient::GetUserAgent -> "
            "embedder_support::GetUserAgent",
        "metadata_producer":
            "chrome/browser/chrome_content_browser_client.cc:7700 "
            "ChromeContentBrowserClient::GetUserAgentMetadata -> "
            "embedder_support::GetUserAgentMetadata",
    },
}

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--shell", default=lib_shell.SHELL,
                    help="path to the browser binary (default: content_shell)")
args = parser.parse_args()

binary_name = os.path.basename(args.shell)
if binary_name not in PRODUCERS:
    print(f"capture failed: no provenance is recorded for a binary named "
          f"{binary_name!r}. Add it to PRODUCERS after reading which functions "
          f"it uses; do not let the baseline guess.", file=sys.stderr)
    sys.exit(1)
producer = PRODUCERS[binary_name]

EXPRESSIONS = [
    "navigator.userAgent",
    "JSON.stringify(navigator.userAgentData.brands)",
    "navigator.userAgentData.platform",
    "navigator.userAgentData.mobile",
    HIGH_ENTROPY,
    "Object.getOwnPropertyNames(Navigator.prototype).sort().join(',')",
    "Object.keys(navigator).sort().join(',')",
    "Object.keys(window).sort().join(',')",
]

base_url, headers_for, stop = echo_server.start(ACCEPT_CH)
try:
    values, err = lib_shell.session(None, EXPRESSIONS, navigate_to=base_url,
                                    shell=args.shell,
                                    extra_flags=producer["flags"])
    if err is not None:
        print(f"capture failed: {type(err).__name__}: {err}")
        sys.exit(1)
    subresource = headers_for("/probe.js")
    if subresource is None:
        print("capture failed: the subresource request was never observed")
        sys.exit(1)
finally:
    stop()

(user_agent, brands, platform, mobile, high_entropy,
 proto_props, navigator_keys, window_keys) = values

# Guarded like every other failure path here. check=True would raise a bare
# CalledProcessError, which is the one way this script can still die with a
# traceback instead of a "capture failed" line -- and it would do so AFTER the
# browser work succeeded, discarding a capture that cost a browser launch.
try:
    commit = subprocess.run(
        ["git", "-C", os.path.expanduser("~/chromium/src"),
         "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()
except Exception as exc:  # noqa: BLE001 - provenance must never lose a capture
    print(f"capture failed: could not read the checkout's revision: "
          f"{type(exc).__name__}: {exc}", file=sys.stderr)
    sys.exit(1)

observed_headers = {k.lower(): v for k, v in subresource.items()
                    if k.lower().startswith("sec-ch-ua")
                    or k.lower() == "user-agent"}

# Observed, not asserted. Each entry below is a fact about THIS capture that a
# later reader would otherwise have to infer from an absence -- and an absence
# is exactly what a partial or broken capture also looks like. Saying "this was
# requested and did not arrive" distinguishes the two.
known_absent = []
missing_hints = sorted(h.lower() for h in ACCEPT_CH
                       if h.lower() not in observed_headers)
if missing_hints:
    known_absent.append(
        f"high-entropy request headers advertised via Accept-CH but not sent: "
        f"{', '.join(missing_hints)}")
if platform == "Unknown":
    known_absent.append(
        'userAgentData.platform is the literal "Unknown"')

baseline = {
    "user_agent": user_agent,
    "brands": json.loads(brands),
    "platform": platform,
    "mobile": mobile,
    "high_entropy": high_entropy,
    "navigator_prototype_props": proto_props.split(","),
    "navigator_keys": navigator_keys.split(","),
    "window_keys": window_keys.split(","),
    "request_headers": observed_headers,
    "provenance": {
        "binary": binary_name,
        "captured_at_commit": commit,
        "accept_ch_advertised": [h.lower() for h in ACCEPT_CH],
        "metadata_producer": producer["metadata_producer"],
        "ua_string_producer": producer["ua_string_producer"],
        "known_absent": known_absent,
    },
}
print(json.dumps(baseline, indent=2, sort_keys=True))
