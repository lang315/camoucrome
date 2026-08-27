"""Captures the unspoofed UA surface of the CURRENT build.

Must run before the producer patch lands. After Task 4 there is no way to
produce this file again without rebuilding from the pinned base revision,
and the no-config regression check in Task 6 is worth nothing without it.
"""

import json
import os
import subprocess
import sys

import echo_server
import lib_shell

HIGH_ENTROPY = """
() => navigator.userAgentData.getHighEntropyValues(
    ["architecture","bitness","platformVersion","model","fullVersionList",
     "wow64","formFactors"])
"""

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

ACCEPT_CH = ["Sec-CH-UA-Arch", "Sec-CH-UA-Bitness", "Sec-CH-UA-Platform-Version",
             "Sec-CH-UA-Model", "Sec-CH-UA-Full-Version-List", "Sec-CH-UA-WoW64"]

base_url, headers_for, stop = echo_server.start(ACCEPT_CH)
try:
    values, err = lib_shell.session(None, EXPRESSIONS, navigate_to=base_url)
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

# The absent sec-ch-ua-* headers and platform "Unknown" below are content_shell's
# true unspoofed state, not a partial capture: content_shell never wires a
# ClientHintsControllerDelegate (so Accept-CH can't be persisted) and hardcodes
# "Unknown" in GetShellUserAgentMetadata(). Recorded explicitly so no later task
# misreads these values as what real Chrome would report.
commit = subprocess.run(
    ["git", "-C", os.path.expanduser("~/chromium/src"), "rev-parse", "--short", "HEAD"],
    capture_output=True, text=True, check=True).stdout.strip()

baseline = {
    "user_agent": user_agent,
    "brands": json.loads(brands),
    "platform": platform,
    "mobile": mobile,
    "high_entropy": high_entropy,
    "navigator_prototype_props": proto_props.split(","),
    "navigator_keys": navigator_keys.split(","),
    "window_keys": window_keys.split(","),
    "request_headers": {k.lower(): v for k, v in subresource.items()
                        if k.lower().startswith("sec-ch-ua")
                        or k.lower() == "user-agent"},
    "provenance": {
        "binary": "content_shell",
        "captured_at_commit": commit,
        "metadata_producer": "content/shell/browser/shell_content_browser_client.cc:348 GetShellUserAgentMetadata",
        "ua_string_producer": "components/embedder_support/user_agent_utils.cc BuildUnifiedPlatformUserAgentFromProduct",
        "known_absent": [
            "all sec-ch-ua-* request headers: ShellBrowserContext::GetClientHintsControllerDelegate() returns nullptr outside test harnesses",
            "userAgentData.platform is the literal \"Unknown\", hardcoded in GetShellUserAgentMetadata",
        ],
    },
}
print(json.dumps(baseline, indent=2, sort_keys=True))
