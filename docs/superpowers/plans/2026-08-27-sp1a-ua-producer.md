# SP1a — UA / UA-CH producer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the browser claim another operating system across all three user-agent
channels — the `navigator.userAgent` string, the `navigator.userAgentData` object, and the
`Sec-CH-UA*` request headers — from one patched producer, while the Chromium version it
reports remains the version it was compiled from.

**Architecture:** `components/embedder_support/user_agent_utils.cc` builds the UA string
and the `blink::UserAgentMetadata` struct in the browser process, and Chromium's existing
plumbing carries both to the renderer and the network service. SP1a patches two things in
that one file: the `os_info` argument passed to `BuildUserAgentFromOSAndProduct`, and the
field assignments in `GetUserAgentMetadata()`. Values come from `camoucfg`, which SP0
built; absent keys fall through to the real computed value.

**Tech Stack:** C++17/20 (Chromium style), GN/Siso, `content_shell`, Python 3 +
Playwright over CDP for verification.

## Global Constraints

Copied from `docs/superpowers/specs/00-conventions.md` and the SP1 spec. Every task's
requirements implicitly include this section.

- **No JavaScript injection into page-visible scopes.** Nothing in this plan writes JS
  into a page.
- **Native-looking accessors.** After any change,
  `Object.getOwnPropertyDescriptor(...).get.toString()` must still contain `[native code]`,
  and `Object.keys(window)` / `Object.keys(navigator)` must be byte-identical to the
  captured baseline.
- **Worker parity.** Any surface exposed to both a window and a worker must report
  identical values in both.
- **Coherence over coverage.** A spoofed value contradicting another is worse than not
  spoofing.
- **Fall back to the real value** whenever config is absent, never to a placeholder.
- **Never spoof the browser version.** The Chromium version in the UA string, in
  `userAgentData.brands`, in `fullVersionList`, and in the `Sec-CH-UA` header must equal
  the version this binary was built from, always, regardless of config.
- **Never delete a `probe::Apply*Override` call**, and apply configuration *after* the
  probe so the configured value wins.
- **Bad config must never crash a renderer.** A crash is itself a fingerprint.
- **API shape:** every camoucfg getter takes a scope as its first argument. In the browser
  process that is `camoucfg::GlobalScope()`. Never write a getter call that omits it.
- **Chromium API facts that cost SP0 a build cycle each:** the dictionary type is
  `base::DictValue`, not `base::Value::Dict`; `JSONReader::ReadDict` takes a **required**
  `int options`; `base::NoDestructor` static_asserts against a trivially destructible `T`.
- **`VLOG` expands through `LAZY_STREAM`.** An expression written inside a `VLOG` is never
  evaluated at default verbosity. Never move a load-bearing call into one.
- **Base revision is pinned:** `0e8d4a9268118d323f62ca207b40514df39dcaa9`. Work happens on
  a **named branch**, never detached HEAD — `gclient sync` discards detached commits.
- **Never `git add -A`** in a repository another agent may be writing to. Stage explicit
  paths. This rule was earned in SP0; see `.superpowers/sdd/progress.md`.
- **Git identity is set `--local`** in the Chromium checkout, never `--global` — the same
  WSL distro hosts the user's Camoufox build.

## Environment

Two machines. Do not confuse them.

| | Path | Role |
|---|---|---|
| Mac (this session) | `/Users/lang/GolandProjects/github.com/lang315/camoucrome` | specs, plans, `additions/`, `patches/`, `scripts/`, ledger |
| Build PC (WSL) | `~/chromium/src`, branch `camoucrome/sp0` | the Chromium checkout and `out/Default/content_shell` |

Reach the build machine with:

```bash
CM=~/.ssh/cm-buildpc
/usr/bin/ssh -o ControlMaster=auto -o ControlPath=$CM -o ControlPersist=8h \
  -p 2222 lang315@100.81.40.76 "wsl -d Ubuntu-24.04 -u lang -- bash -s" < script.sh
```

Note `/usr/bin/ssh` — a shell wrapper on this Mac shadows bare `ssh`. Note port **2222**,
not 22.

**A job on the build PC lives only while a `wsl.exe` client is attached.** The WSL2 VM is
torn down seconds after the last client disconnects, so `nohup`, `setsid` and
`Start-Process` cannot work — this is not a usage error. Run long jobs in the foreground of
an ssh session held open by `ControlPersist`, or issue chunked
`timeout -k 15 540 autoninja -C out/Default content_shell` calls until it converges.
A client-side task exiting 255 does not mean the remote job died: check
`pgrep -c "siso|ninja"` first, and never start a second build in the same output directory.

`autoninja` is not on `PATH` in a non-interactive ssh session, because `.bashrc` returns
early when non-interactive. Use `~/depot_tools/autoninja` explicitly.

Incremental rebuild after touching `user_agent_utils.cc` is roughly one to three minutes;
`is_component_build=true` and `symbol_level=0` are already set.

**Scripts are authored on the Mac and run on the build PC**, in `~/camoucrome-verify/`,
which SP0 created. That directory is not a git repository — the Mac repository is the only
copy of record. So every task that changes a script pushes it across before running it, and
every task that *produces* a file there (Task 1's baseline) pulls it back before
committing. State the direction in the task report; a verification run against a stale copy
of its own script is the failure this note exists to prevent.

```bash
CM=~/.ssh/cm-buildpc
# Mac -> build PC
/usr/bin/scp -o ControlPath=$CM -P 2222 scripts/<name>.py \
  lang315@100.81.40.76:/tmp/verify-drop/
# then on the build PC: cp /tmp/verify-drop/*.py ~/camoucrome-verify/scripts/
```

## Branch

All Chromium-side work continues on the existing branch `camoucrome/sp0`, whose head is
`a90c2cdcb3`. It is not renamed: SP0's ten commits and SP1a's commits form one change set
that `scripts/apply.sh` applies together, and renaming mid-stream would invalidate the
recorded base in the ledger for no gain.

## File Structure

**Mac repository:**

| Path | Responsibility | Task |
|---|---|---|
| `scripts/lib_shell.py` | Create — launch/session/evaluate helpers extracted from `verify_sp0.py`, so SP1a's verification does not re-derive five hardening fixes | 1 |
| `scripts/echo_server.py` | Create — a local HTTP listener that records request headers and advertises `Accept-CH` | 1 |
| `baselines/content_shell-sp0-stock-ua.json` | Create — the pre-SP1a UA surface, capturable only before Task 4 | 1 |
| `additions/camoucfg/keys.h` | Create — the key registry as `constexpr` constants | 2 |
| `additions/camoucfg/keys_unittest.cc` | Create — duplicate and well-formedness check | 2 |
| `additions/camoucfg/BUILD.gn` | Modify — add `keys.h` and `keys_unittest.cc` | 2 |
| `scripts/verify_sp1a.py` | Create in Task 4, extended in Tasks 5 and 6 | 4,5,6 |
| `patches/sp1a-ua-producer.patch` | Create — the extracted diff | 7 |
| `scripts/apply.sh` | Modify — apply the second patch | 7 |

**Chromium checkout:**

| Path | Change | Task |
|---|---|---|
| `components/camoucfg/keys.h` | Copied from `additions/` | 2 |
| `components/camoucfg/BUILD.gn` | Copied from `additions/` | 2 |
| `components/embedder_support/DEPS` | Add `"+components/camoucfg",` | 3 |
| `components/embedder_support/BUILD.gn` | Add `"//components/camoucfg",` to `static_library("user_agent")` deps | 3 |
| `components/embedder_support/user_agent_utils.cc` | The producer patch | 4,5 |
| `content/browser/browser_main_loop.cc` | Add the unsupported-key warning beside SP0's forced parse | 4 |

## Config keys introduced

Eight. All are optional; each absent key falls through to the real value.

| Key | Type | Example (claiming Windows 11 x64) | Real value on this Linux build |
|---|---|---|---|
| `ua:osInfo` | string | `Windows NT 10.0; Win64; x64` | `X11; Linux x86_64` |
| `navigator.uaData:platform` | string | `Windows` | `Linux` |
| `navigator.uaData:platformVersion` | string | `15.0.0` | `` (empty) |
| `navigator.uaData:architecture` | string | `x86` | `x86` |
| `navigator.uaData:bitness` | string | `64` | `64` |
| `navigator.uaData:model` | string | `` (empty) | `` (empty) |
| `navigator.uaData:mobile` | bool | `false` | `false` |
| `navigator.uaData:wow64` | bool | `false` | `false` |

`formFactors` gets **no key**: `GetFormFactorsClientHint()` derives it from `mobile`, and
conventions forbids an independent override for a derived value — it would create the
opportunity for incoherence rather than remove it.

The brand list, `full_version` and `brand_full_version_list` get no keys either, because
the version is never spoofed.

The `navigator.uaData:` prefix is colon-namespaced even though `platform` and `mobile` have
real JavaScript counterparts, because the group as a whole names the `UserAgentMetadata`
struct and most of its members — `architecture`, `bitness`, `platformVersion`, `model`,
`wow64` — are reachable only through `getHighEntropyValues()` and are not properties at
all. One namespace for one struct beats splitting the struct across two naming conventions.

---

### Task 1: Verification scaffolding and the pre-patch baseline

**This task must complete before any task edits `user_agent_utils.cc`.** The baseline it
captures is the current build's *unspoofed* UA surface, and once Task 4 lands there is no
way to capture it again short of rebuilding from the pinned revision.

**Files:**
- Create: `scripts/lib_shell.py`
- Create: `scripts/echo_server.py`
- Create: `scripts/capture_ua_baseline.py`
- Create: `baselines/content_shell-sp0-stock-ua.json` (output, committed)

**Interfaces:**
- Consumes: nothing.
- Produces: `lib_shell.launch(config) -> Popen`, `lib_shell.shutdown(proc) -> None`,
  `lib_shell.evaluate(proc, expressions) -> list`,
  `lib_shell.session(config, expressions) -> (values|None, exception|None)`,
  `lib_shell.SHELL` (the binary path), `lib_shell.STDERR_LOG`.
  `echo_server.start(accept_ch: list[str]) -> (base_url, get_last_headers_callable, stop_callable)`.

- [ ] **Step 1: Extract the shell helpers verbatim from `verify_sp0.py`**

Create `scripts/lib_shell.py`. Move `SHELL`, `STDERR_LOG`, `launch`, `shutdown`,
`evaluate` and `session` across **unchanged**, including their docstrings. Those docstrings
record five failures that were actually observed in SP0 — the `CAMOU_CONFIG*` environment
filter, the per-launch profile directory, `--remote-debugging-port=0` with the port read
back from `DevToolsActivePort`, the three distinguishable startup failures, and polling
instead of sleeping. Re-deriving any of them costs a day.

```python
"""Shared content_shell driving helpers.

Extracted verbatim from verify_sp0.py so that later verifications inherit the
hardening rather than re-deriving it. Every non-obvious detail in launch() and
session() exists because of a failure that was observed, not defensively; the
docstrings say which.
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
STDERR_LOG = "/tmp/camoucrome_verify_stderr.log"
```

Then paste `launch`, `shutdown`, `evaluate` and `session` from `scripts/verify_sp0.py`
without edits.

- [ ] **Step 2: Point `verify_sp0.py` at the shared module and prove it still passes**

Replace the moved definitions in `scripts/verify_sp0.py` with:

```python
from lib_shell import SHELL, STDERR_LOG, launch, shutdown, evaluate, session
```

and delete the now-duplicated bodies. Leave everything else in that file alone.

Run on the build PC:

```bash
cd ~/camoucrome-verify && python3 scripts/verify_sp0.py; echo "exit=$?"
```

Expected: the same **11 PASS, exit=0** it produced before. If any line changed, the
extraction was not verbatim — fix the extraction, do not adjust the assertion.

- [ ] **Step 3: Write the header-echo listener**

Create `scripts/echo_server.py`. `Sec-CH-UA-Arch` and `Sec-CH-UA-Bitness` are high-entropy
hints that a server receives only after it has asked for them with `Accept-CH`, and only on
a **subsequent** request — the first request carries the low-entropy hints alone. The
listener must therefore serve a page that triggers a second same-origin request, and the
recorded headers must come from that second one.

```python
"""A local listener that records request headers, for UA-CH verification.

High-entropy client hints are not sent until the origin has advertised
Accept-CH, and then only from the next request onward. So the root document
both advertises the hints and references a same-origin subresource; the
headers worth asserting on are the subresource's, not the document's.
"""

import http.server
import threading


def start(accept_ch):
    records = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            records.append((self.path, dict(self.headers)))
            body = (b"<!doctype html><title>ua</title>"
                    b"<script src='/probe.js'></script>")
            self.send_response(200)
            self.send_header("Accept-CH", ", ".join(accept_ch))
            if self.path == "/probe.js":
                self.send_header("Content-Type", "application/javascript")
                body = b"/* probe */"
            else:
                self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass  # the test's own output is the only output that matters

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def headers_for(path):
        """Returns the LAST recorded headers for path, or None."""
        for recorded_path, headers in reversed(records):
            if recorded_path == path:
                return headers
        return None

    def stop():
        server.shutdown()
        server.server_close()

    return f"http://127.0.0.1:{server.server_port}/", headers_for, stop
```

- [ ] **Step 4: Write the baseline capture script**

Create `scripts/capture_ua_baseline.py`. It calls `session(..., navigate_to=...)`, which
Step 5 adds — this step only writes the file, and Step 6 is the first step that runs it.

```python
"""Captures the unspoofed UA surface of the CURRENT build.

Must run before the producer patch lands. After Task 4 there is no way to
produce this file again without rebuilding from the pinned base revision,
and the no-config regression check in Task 6 is worth nothing without it.
"""

import json
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
}
print(json.dumps(baseline, indent=2, sort_keys=True))
```

- [ ] **Step 5: Teach `session()` to navigate**

`capture_ua_baseline.py` needs the page pointed at the listener before evaluating, which
`session()` cannot do. Add the parameter in `lib_shell.py`, defaulting to the SP0 behaviour
so no existing caller changes:

```python
def evaluate(proc, expressions, navigate_to=None):
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(
            f"http://127.0.0.1:{proc.cdp_port}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        if navigate_to is not None:
            # wait_until="load" so the subresource request the header
            # assertions read has certainly been issued.
            page.goto(navigate_to, wait_until="load")
        return [page.evaluate(e) for e in expressions]


def session(config, expressions, navigate_to=None):
    proc = None
    try:
        proc = launch(config)
        return evaluate(proc, expressions, navigate_to), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    finally:
        if proc is not None:
            shutdown(proc)
```

Re-run `verify_sp0.py` and confirm **11 PASS, exit=0** again.

- [ ] **Step 6: Capture the baseline**

```bash
cd ~/camoucrome-verify
python3 scripts/capture_ua_baseline.py > baselines/content_shell-sp0-stock-ua.json
echo "exit=$?"
python3 -c "import json;d=json.load(open('baselines/content_shell-sp0-stock-ua.json'));print(d['user_agent']);print(d['platform']);print(sorted(d['request_headers']))"
```

Expected: exit=0; a user agent containing `X11; Linux x86_64`; platform `Linux`; and a
header list including `sec-ch-ua`, `sec-ch-ua-mobile`, `sec-ch-ua-platform`,
`sec-ch-ua-arch`, `sec-ch-ua-bitness`.

If `sec-ch-ua-arch` is absent, the second request was not captured — fix `echo_server.py`,
because Task 5's most important assertion depends on it. Do not proceed with a partial
baseline.

Then pull the file back to the Mac, which is the only copy of record:

```bash
CM=~/.ssh/cm-buildpc
/usr/bin/ssh -o ControlPath=$CM -p 2222 lang315@100.81.40.76 \
  "wsl -d Ubuntu-24.04 -u lang -- cat ~/camoucrome-verify/baselines/content_shell-sp0-stock-ua.json" \
  > baselines/content_shell-sp0-stock-ua.json
python3 -c "import json;json.load(open('baselines/content_shell-sp0-stock-ua.json'))" && echo "valid JSON"
```

The JSON re-parse is not ceremony: this transfer goes through a PowerShell 5.1 shell that
has mangled output before, and a baseline that arrives corrupt would fail Task 6 in a way
that looks like a producer bug.

- [ ] **Step 7: Commit**

```bash
cd /Users/lang/GolandProjects/github.com/lang315/camoucrome
git add scripts/lib_shell.py scripts/echo_server.py scripts/capture_ua_baseline.py \
        scripts/verify_sp0.py baselines/content_shell-sp0-stock-ua.json
git commit -m "verify: capture the unspoofed UA surface before patching the producer"
```

---

### Task 2: The key registry

**Files:**
- Create: `additions/camoucfg/keys.h`
- Create: `additions/camoucfg/keys_unittest.cc`
- Modify: `additions/camoucfg/BUILD.gn`

**Interfaces:**
- Consumes: nothing.
- Produces: `camoucfg::keys::kUaOsInfo`, `kNavigatorUserAgent`, `kUaDataPlatform`,
  `kUaDataPlatformVersion`, `kUaDataArchitecture`, `kUaDataBitness`, `kUaDataModel`,
  `kUaDataMobile`, `kUaDataWow64`, and `camoucfg::keys::kAllKeys` (a span over all of them).
  Tasks 4 and 5 use these instead of string literals.

- [ ] **Step 1: Write the failing test**

Create `additions/camoucfg/keys_unittest.cc`:

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/keys.h"

#include <set>
#include <string_view>

#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg::keys {
namespace {

// The failure this guards against is a constant whose NAME is new but whose
// VALUE duplicates another. Two call sites then read the same key while
// appearing to read different ones, which no compiler or reviewer catches and
// which produces a surface that silently follows the wrong knob.
TEST(CamoucfgKeysTest, EveryKeyIsUnique) {
  std::set<std::string_view> seen;
  for (std::string_view key : kAllKeys) {
    EXPECT_TRUE(seen.insert(key).second) << "duplicate key value: " << key;
  }
  EXPECT_EQ(seen.size(), kAllKeys.size());
}

// Conventions: a key uses a dot when it mirrors a JavaScript property path and
// a colon when it names a synthetic namespace. Either way it carries at least
// one separator, and a key that carries neither is a bare word that will
// collide with a future namespace.
TEST(CamoucfgKeysTest, EveryKeyIsNamespaced) {
  for (std::string_view key : kAllKeys) {
    EXPECT_NE(key.find_first_of(".:"), std::string_view::npos)
        << "key is not namespaced: " << key;
    EXPECT_EQ(key.find(' '), std::string_view::npos)
        << "key contains a space: " << key;
    EXPECT_FALSE(key.empty());
  }
}

}  // namespace
}  // namespace camoucfg::keys
```

- [ ] **Step 2: Run it to confirm it fails**

On the build PC:

```bash
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default components_unittests 2>&1 | tail -20
```

Expected: FAIL — `fatal error: 'components/camoucfg/keys.h' file not found`.

- [ ] **Step 3: Write the header**

Create `additions/camoucfg/keys.h`:

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_KEYS_H_
#define COMPONENTS_CAMOUCFG_KEYS_H_

#include <array>
#include <string_view>

// The registry of configuration keys.
//
// Its purpose is that keys stop being string literals at call sites. A key
// mistyped at one of two sites that should agree produces a surface that
// silently follows a knob nobody set, and neither the compiler nor a reviewer
// reading one file can see it.
//
// Conventions commits to generating this from settings/keys.json in SP6a. It
// is hand-written for now because generation buys exactly one thing beyond
// what a header of constants already buys — a single source feeding both these
// constants and the client's validation table — and the client's table does not
// exist yet. The SP6a task that introduces the generator must emit these same
// constant names so that no call site moves.
//
// Naming rule, from 00-conventions.md: a dot when the key mirrors a JavaScript
// property path exactly, a colon when it names a synthetic namespace with no
// direct JS counterpart. A value derived from another gets no key at all.

namespace camoucfg::keys {

// The OS segment of the user-agent string, e.g. "Windows NT 10.0; Win64; x64".
// Colon-namespaced: it names a substring of a JS property, not the property.
//
// It is deliberately not the whole user-agent string. A whole string carries a
// browser version, and Camoucrome never reports a version other than the one
// its binary was compiled from — so accepting one would mean either emitting a
// contradiction or parsing the string to extract the part we want, and SP1
// forbids parsing user agents locally.
inline constexpr char kUaOsInfo[] = "ua:osInfo";

// Not supported. Present in the registry so the startup validator can warn
// that it was ignored and name kUaOsInfo instead. Camoufox uses this key, so a
// config written for Camoufox will contain it; failing loudly beats producing
// an unspoofed user agent in silence.
inline constexpr char kNavigatorUserAgent[] = "navigator.userAgent";

// The blink::UserAgentMetadata fields. One colon namespace for one struct:
// `platform` and `mobile` do have JavaScript counterparts, but `architecture`,
// `bitness`, `platformVersion`, `model` and `wow64` are reachable only through
// getHighEntropyValues() and are not properties at all. Splitting one struct
// across two naming conventions would be worse than a namespace that is a
// little loose.
//
// Absent from this list on purpose: `brands`, `fullVersionList` and
// `formFactors`. The first two carry the version, which is never spoofed. The
// third is derived from `mobile` by GetFormFactorsClientHint(), and conventions
// gives a derived value no key of its own.
inline constexpr char kUaDataPlatform[] = "navigator.uaData:platform";
inline constexpr char kUaDataPlatformVersion[] =
    "navigator.uaData:platformVersion";
inline constexpr char kUaDataArchitecture[] = "navigator.uaData:architecture";
inline constexpr char kUaDataBitness[] = "navigator.uaData:bitness";
inline constexpr char kUaDataModel[] = "navigator.uaData:model";
inline constexpr char kUaDataMobile[] = "navigator.uaData:mobile";
inline constexpr char kUaDataWow64[] = "navigator.uaData:wow64";

// Every key above. A new constant must be added here too, which is what makes
// the uniqueness test meaningful.
inline constexpr std::array<std::string_view, 9> kAllKeys = {
    kUaOsInfo,          kNavigatorUserAgent,    kUaDataPlatform,
    kUaDataPlatformVersion, kUaDataArchitecture, kUaDataBitness,
    kUaDataModel,       kUaDataMobile,          kUaDataWow64,
};

}  // namespace camoucfg::keys

#endif  // COMPONENTS_CAMOUCFG_KEYS_H_
```

- [ ] **Step 4: Add both files to the GN target**

In `additions/camoucfg/BUILD.gn`, add `"keys.h",` to the `sources` of
`static_library("camoucfg")` — keeping the list alphabetical, so it goes before
`"mask_config.cc"` and after `"blink_scope.h"`:

```gn
static_library("camoucfg") {
  sources = [
    "blink_scope.h",
    "keys.h",
    "mask_config.cc",
    "mask_config.h",
    "mask_config_internal.cc",
    "mask_config_internal.h",
  ]

  deps = [ "//base" ]
}
```

and add `"keys_unittest.cc",` to `source_set("unit_tests")`:

```gn
source_set("unit_tests") {
  testonly = true
  sources = [
    "keys_unittest.cc",
    "mask_config_unittest.cc",
  ]

  deps = [
    ":camoucfg",
    "//base",
    "//base/test:test_support",
    "//testing/gtest",
  ]
}
```

- [ ] **Step 5: Copy into the checkout, build and run**

```bash
# From the Mac:
CM=~/.ssh/cm-buildpc
/usr/bin/scp -o ControlPath=$CM -P 2222 \
  additions/camoucfg/keys.h additions/camoucfg/keys_unittest.cc \
  additions/camoucfg/BUILD.gn \
  lang315@100.81.40.76:/tmp/camoucfg-drop/
```

Then on the build PC, copy `/tmp/camoucfg-drop/*` into `components/camoucfg/` and:

```bash
cd ~/chromium/src
~/depot_tools/autoninja -C out/Default components_unittests
./out/Default/components_unittests --gtest_filter='CamoucfgKeysTest.*'
echo "exit=$?"
```

Expected: **2 tests from 1 test suite ran. [ PASSED ] 2 tests.**, exit=0.

- [ ] **Step 6: Confirm SP0's tests still pass**

```bash
./out/Default/components_unittests --gtest_filter='Camoucfg*'
```

Expected: 21 tests pass — SP0's 19 plus the 2 new ones. A drop below 19 means the BUILD.gn
edit dropped a source; fix it before continuing.

- [ ] **Step 7: Commit — both repositories**

```bash
# Chromium checkout, on branch camoucrome/sp0:
cd ~/chromium/src
git add components/camoucfg/keys.h components/camoucfg/keys_unittest.cc \
        components/camoucfg/BUILD.gn
git commit -m "camoucfg: add the configuration key registry"

# Mac:
cd /Users/lang/GolandProjects/github.com/lang315/camoucrome
git add additions/camoucfg/keys.h additions/camoucfg/keys_unittest.cc \
        additions/camoucfg/BUILD.gn
git commit -m "camoucfg: add the configuration key registry"
```

---

### Task 3: Let `embedder_support` depend on `camoucfg`

Two independent gates block this include, and only one of them fails at build time. SP0
lost a cycle to exactly this: `autoninja` runs `gn check`, which enforces the GN
dependency graph, but it does **not** run `checkdeps.py`, which enforces `DEPS`
`include_rules`. A missing `DEPS` line therefore builds cleanly and fails presubmit later.
Both edits belong to this task, and the task verifies both.

**Files:**
- Modify: `components/embedder_support/DEPS`
- Modify: `components/embedder_support/BUILD.gn`
- Modify: `components/embedder_support/user_agent_utils.cc` (the include only)

**Interfaces:**
- Consumes: `camoucfg::keys` from Task 2.
- Produces: a `user_agent_utils.cc` that can include camoucfg headers. Tasks 4 and 5
  depend on this and add no further build wiring.

- [ ] **Step 1: Add the include, and watch it fail**

In `components/embedder_support/user_agent_utils.cc`, add to the include block (Chromium
sorts `components/` includes alphabetically, so these go after
`#include "components/camoucfg/..."`'s alphabetical neighbours — place them with the other
`components/` includes):

```cpp
#include "components/camoucfg/keys.h"
#include "components/camoucfg/mask_config.h"
```

Build:

```bash
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default content_shell 2>&1 | tail -20
```

Expected: FAIL, with a `gn check` error naming
`//components/embedder_support:user_agent` and reporting that it does not have a
dependency on `//components/camoucfg`.

Record the exact error text in the task report. It is the evidence that the GN gate is
real and that the next step is what closes it.

- [ ] **Step 2: Add the GN dependency**

In `components/embedder_support/BUILD.gn`, in `static_library("user_agent")`, add
`"//components/camoucfg",` to `deps`, alphabetically before
`"//components/policy/core/common"`:

```gn
static_library("user_agent") {
  sources = [
    "user_agent_utils.cc",
    "user_agent_utils.h",
  ]

  deps = [
    ":embedder_support",
    "//build:branding_buildflags",
    "//components/camoucfg",
    "//components/policy/core/common",
    "//components/prefs",
    "//components/version_info",
    "//net",
    "//third_party/blink/public/common:headers",
    "//ui/base",
  ]
}
```

- [ ] **Step 3: Add the `DEPS` grant**

`components/embedder_support/DEPS` is a flat alphabetical `include_rules` list. The new
entry goes after `"+components/background_sync",` and before
`"+components/content_settings/browser",`:

```
include_rules = [
  "+components/background_sync",
  "+components/camoucfg",
  "+components/content_settings/browser",
  ...
]
```

Unlike Blink's `DEPS`, this file grants by directory rather than per-header, matching the
style of every other entry in it. The per-header rule in conventions is specific to
`third_party/blink/renderer/DEPS`, which is written that way.

- [ ] **Step 4: Build and verify both gates**

```bash
cd ~/chromium/src
~/depot_tools/autoninja -C out/Default content_shell 2>&1 | tail -5
echo "build exit=$?"
python3 buildtools/checkdeps/checkdeps.py --root="$(pwd)" components/embedder_support
echo "checkdeps exit=$?"
```

Expected: build succeeds; `checkdeps` prints `SUCCESS` and exits 0.

If `checkdeps.py` is not at that path, find it with
`find . -name checkdeps.py -not -path '*/node_modules/*' | head`. Report the path used.

- [ ] **Step 5: Commit**

```bash
cd ~/chromium/src
git add components/embedder_support/DEPS components/embedder_support/BUILD.gn \
        components/embedder_support/user_agent_utils.cc
git commit -m "embedder_support: depend on camoucfg"
```

---

### Task 4: Substitute the OS segment of the user-agent string

**Files:**
- Modify: `components/embedder_support/user_agent_utils.cc`
- Modify: `content/browser/browser_main_loop.cc`
- Create: `scripts/verify_sp1a.py`

**Interfaces:**
- Consumes: `camoucfg::keys::kUaOsInfo`, `kNavigatorUserAgent` (Task 2); the build wiring
  (Task 3); `lib_shell`, `echo_server`, the baseline (Task 1).
- Produces: `verify_sp1a.py` with criterion 1's assertions, which Tasks 5 and 6 extend.

- [ ] **Step 1: Write the failing assertions**

Create `scripts/verify_sp1a.py`. It follows `verify_sp0.py`'s shape exactly: every session
is wrapped so that one fault becomes FAILs rather than erasing every other result, and the
baseline load is guarded for the same reason.

```python
"""Verifies the SP1a acceptance criteria against a built content_shell.

Structured like verify_sp0.py, and for the reasons its docstrings give: a
fault in any one session must become FAIL lines rather than a traceback that
discards every result already collected. An intermittently green verification
is worse than a slow one -- it teaches people to re-run until it passes, and
then it measures nothing.
"""

import json
import os
import sys

import echo_server
import lib_shell

BASELINE = os.path.expanduser(
    "~/camoucrome-verify/baselines/content_shell-sp0-stock-ua.json")

# Windows 11 x64, en-US. Carries no version field of any kind: the reported
# Chromium version is always this build's own.
#
# The osInfo value is byte-identical to the literal in GetUnifiedPlatform()'s
# own BUILDFLAG(IS_WIN) arm, which a Linux build compiles out. Taking it from
# Chromium's own source rather than from a captured string means the claim
# matches what a real Chrome on Windows emits by construction.
WIN = {
    "ua:osInfo": "Windows NT 10.0; Win64; x64",
    "navigator.uaData:platform": "Windows",
    "navigator.uaData:platformVersion": "15.0.0",
    "navigator.uaData:architecture": "x86",
    "navigator.uaData:bitness": "64",
    "navigator.uaData:mobile": False,
    "navigator.uaData:wow64": False,
}

results = {}
notes = []


def failed(keys, label, exc):
    for key in keys:
        results[key] = False
    notes.append(f"{label}: {type(exc).__name__}: {exc}")


def load_baseline(path):
    try:
        with open(path) as handle:
            data = json.load(handle)
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    # Every key any assertion reads. Task 6 reads "mobile" and
    # "navigator_prototype_props", so a baseline missing either must become
    # FAIL lines here rather than a KeyError three hundred lines later.
    missing = [k for k in ("user_agent", "brands", "platform", "mobile",
                           "high_entropy", "navigator_prototype_props",
                           "navigator_keys", "window_keys", "request_headers")
               if k not in data]
    if missing:
        return None, KeyError(f"baseline lacks {', '.join(missing)}")
    return data, None


baseline, baseline_err = load_baseline(BASELINE)


def build_version():
    """The Chromium version this binary was compiled from.

    Read from the stock user agent in the baseline rather than from
    chrome/VERSION: the baseline came out of this exact binary, while the
    source tree can have moved.
    """
    if baseline is None:
        return None
    # ".../Chrome/141.0.7390.54 Safari/..." -> "141.0.7390.54"
    for token in baseline["user_agent"].split():
        if token.startswith("Chrome/"):
            return token.split("/", 1)[1]
    return None


REAL_VERSION = build_version()

# --- Criterion 1: the OS token moves, the version does not ---

C1 = ["1 spoofed UA carries the Windows OS token",
      "1 spoofed UA carries no Linux token",
      "1 spoofed UA reports the build's own version",
      "1 unconfigured UA is byte-identical to the baseline",
      "1 navigator.userAgent is refused, not half-honoured"]

spoofed, err = lib_shell.session(json.dumps(WIN), ["navigator.userAgent"])
if err is not None:
    failed(C1[:3], "spoofed session", err)
else:
    ua = spoofed[0]
    results["1 spoofed UA carries the Windows OS token"] = (
        "Windows NT 10.0; Win64; x64" in ua)
    results["1 spoofed UA carries no Linux token"] = (
        "Linux" not in ua and "X11" not in ua)
    results["1 spoofed UA reports the build's own version"] = (
        REAL_VERSION is not None and f"Chrome/{REAL_VERSION}" in ua)

stock, err = lib_shell.session(None, ["navigator.userAgent"])
if err is not None:
    failed(["1 unconfigured UA is byte-identical to the baseline"],
           "unconfigured session", err)
elif baseline_err is not None:
    failed(["1 unconfigured UA is byte-identical to the baseline"],
           f"baseline load from {BASELINE}", baseline_err)
else:
    results["1 unconfigured UA is byte-identical to the baseline"] = (
        stock[0] == baseline["user_agent"])

# A whole user-agent string carries a version. Honouring it would mean either
# emitting a version this binary contradicts or parsing the string to extract
# the OS segment, and SP1 forbids both. So it must be ignored -- and it must
# say so, because silently producing an unspoofed UA from a config that
# plainly asked for a spoofed one is the kind of failure people lose a day to.
refused, err = lib_shell.session(
    json.dumps({"navigator.userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64;"
                                       " x64) Chrome/1.2.3.4 Safari/537.36"}),
    ["navigator.userAgent"])
if err is not None:
    failed(["1 navigator.userAgent is refused, not half-honoured"],
           "refusal session", err)
else:
    with open(lib_shell.STDERR_LOG, "rb") as handle:
        stderr = handle.read().decode("utf-8", "replace")
    results["1 navigator.userAgent is refused, not half-honoured"] = (
        "1.2.3.4" not in refused[0]
        and (baseline is not None and refused[0] == baseline["user_agent"])
        and "ua:osInfo" in stderr)

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)
```

- [ ] **Step 2: Run it and confirm every criterion-1 assertion fails**

```bash
cd ~/camoucrome-verify && python3 scripts/verify_sp1a.py; echo "exit=$?"
```

Expected: the two "unconfigured" and version assertions PASS (nothing has changed yet), and
**`1 spoofed UA carries the Windows OS token`, `1 spoofed UA carries no Linux token` and
`1 navigator.userAgent is refused, not half-honoured` FAIL**, exit=1.

If the spoofed assertions pass here, something is already substituting the UA — stop and
investigate rather than proceeding.

- [ ] **Step 3: Add the substitution helper**

In `components/embedder_support/user_agent_utils.cc`, inside the existing anonymous
namespace, immediately after `GetUserAgentPlatform()` ends (around line 305):

```cpp
// Returns the OS segment of the user-agent string that configuration asks this
// build to claim, or `real` when no key is set.
//
// This is the only substitution point for the user-agent string, and where it
// sits is the design. It is BELOW GetUserAgentInternal()'s choice between the
// reduced and the full form, so a build keeps emitting whichever form is
// correct for it. It is BELOW GetUserAgent()'s --user-agent short-circuit, so
// that switch keeps its meaning. And `product` -- the token carrying the
// Chromium version -- is never routed through here, so the version this build
// reports cannot move no matter what configuration says.
//
// Nothing in a Linux binary can compute a Windows OS string: every arm of
// GetUserAgentPlatform(), GetOSVersion() and GetUnifiedPlatform() is selected
// by BUILDFLAG at compile time, so only one is present in the image. The value
// therefore has to arrive whole from configuration, and an absent key falls
// back to the real platform's string, which is what conventions rule 5 wants
// anyway.
std::string OsInfoOverrideOr(std::string real) {
  std::optional<std::string> configured = camoucfg::GetString(
      camoucfg::GlobalScope(), camoucfg::keys::kUaOsInfo);
  return configured.has_value() ? std::move(*configured) : std::move(real);
}
```

- [ ] **Step 4: Route both builders through it**

Both are at file scope in `namespace embedder_support`, around line 839. Change:

```cpp
std::string BuildUnifiedPlatformUserAgentFromProduct(
    const std::string& product) {
  return BuildUserAgentFromOSAndProduct(OsInfoOverrideOr(GetUnifiedPlatform()),
                                        product);
}

std::string BuildUserAgentFromProduct(const std::string& product) {
  std::string os_info;
  base::StringAppendF(&os_info, "%s%s", GetUserAgentPlatform().c_str(),
                      BuildOSCpuInfo(IncludeAndroidBuildNumber::Exclude,
                                     IncludeAndroidModel::Include)
                          .c_str());
  return BuildUserAgentFromOSAndProduct(OsInfoOverrideOr(std::move(os_info)),
                                        product);
}
```

Only the argument changes in each. Do not restructure the surrounding code.

- [ ] **Step 5: Warn about the unsupported key at startup**

`content/browser/browser_main_loop.cc` already forces the browser-process parse in
`BrowserMainLoop::EarlyInitialization`, and conventions records as an open weakness that
this validation rides on a line whose stated purpose is logging. Give it an explicit
statement of its own, next to the existing call:

```cpp
  if (camoucfg::HasKey(camoucfg::GlobalScope(),
                       camoucfg::keys::kNavigatorUserAgent)) {
    LOG(WARNING)
        << "camoucfg: '" << camoucfg::keys::kNavigatorUserAgent
        << "' is not supported and has been ignored. A whole user-agent string "
           "carries a browser version, and Camoucrome always reports the "
           "version its binary was built from. Set '"
        << camoucfg::keys::kUaOsInfo
        << "' to the OS segment instead, for example "
           "\"Windows NT 10.0; Win64; x64\".";
  }
```

Add `#include "components/camoucfg/keys.h"` beside the existing
`#include "components/camoucfg/mask_config.h"`.

Place this **after** the existing forced-parse statement, not inside any `VLOG`. A `VLOG`
expands through `LAZY_STREAM`, so an expression written inside one is not evaluated at
default verbosity — the mistake SP0 already made once here, and the reason the existing
call sits where it does.

The warning belongs in the browser process rather than in `OsInfoOverrideOr`, for two
reasons. The producer is called many times per launch and would repeat itself. And the
browser process is where a configuration problem should surface — before any renderer
exists, which is the same argument that put the forced parse here.

- [ ] **Step 6: Check `content/browser`'s DEPS grant covers the new header**

SP0 added a per-header grant for `mask_config.h`. `keys.h` needs its own line, for the same
reason the grant is per-header: including a new one should require thinking about it.

```bash
grep -n "camoucfg" ~/chromium/src/content/browser/DEPS
```

If only `mask_config.h` is listed, add `"+components/camoucfg/keys.h",` beside it.

- [ ] **Step 7: Build and re-run**

```bash
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default content_shell 2>&1 | tail -5
cd ~/camoucrome-verify && python3 scripts/verify_sp1a.py; echo "exit=$?"
```

Expected: **5 PASS, exit=0.**

- [ ] **Step 8: Confirm SP0 has not regressed**

```bash
cd ~/camoucrome-verify && python3 scripts/verify_sp0.py; echo "exit=$?"
cd ~/chromium/src && ./out/Default/components_unittests --gtest_filter='Camoucfg*'
```

Expected: 11 PASS exit=0, and 21 unit tests passing.

- [ ] **Step 9: Commit**

```bash
cd ~/chromium/src
git add components/embedder_support/user_agent_utils.cc \
        content/browser/browser_main_loop.cc content/browser/DEPS
git commit -m "embedder_support: let configuration supply the user agent's OS segment"

cd /Users/lang/GolandProjects/github.com/lang315/camoucrome
git add scripts/verify_sp1a.py
git commit -m "verify: assert the OS token moves and the version does not"
```

---

### Task 5: Substitute the UA-CH metadata fields

This is what makes `navigator.userAgentData` and the `Sec-CH-UA*` headers agree with the
string Task 4 changed. Until it lands, the build emits a Windows user agent alongside
`Sec-CH-UA-Platform: "Linux"` — an incoherence strictly worse than not spoofing, which is
why Tasks 4 and 5 must not be left half-done.

**Files:**
- Modify: `components/embedder_support/user_agent_utils.cc`
- Modify: `scripts/verify_sp1a.py`

**Interfaces:**
- Consumes: everything from Tasks 2–4.
- Produces: criteria 2, 3 and 4 assertions in `verify_sp1a.py`.

- [ ] **Step 1: Write the failing assertions**

Append to `scripts/verify_sp1a.py`, before the printing loop:

```python
# --- Criteria 2, 3 and 4: the object, the hints, and the wire ---

C234 = ["2 userAgentData.platform is Windows",
        "2 brands version equals the UA string's major version",
        "3 high-entropy architecture and bitness match the claim",
        "3 fullVersionList reports the build's own version",
        "4 Sec-CH-UA-Platform matches userAgentData.platform",
        "4 Sec-CH-UA-Arch and Bitness match the high-entropy values",
        "4 the wire User-Agent equals navigator.userAgent"]

HIGH_ENTROPY = """
() => navigator.userAgentData.getHighEntropyValues(
    ["architecture","bitness","platformVersion","model","fullVersionList"])
"""

ACCEPT_CH = ["Sec-CH-UA-Arch", "Sec-CH-UA-Bitness", "Sec-CH-UA-Platform-Version",
             "Sec-CH-UA-Model", "Sec-CH-UA-Full-Version-List", "Sec-CH-UA-WoW64"]

base_url, headers_for, stop = echo_server.start(ACCEPT_CH)
try:
    values, err = lib_shell.session(
        json.dumps(WIN),
        ["navigator.userAgent",
         "navigator.userAgentData.platform",
         "JSON.stringify(navigator.userAgentData.brands)",
         HIGH_ENTROPY],
        navigate_to=base_url)
    wire = headers_for("/probe.js") if err is None else None
finally:
    stop()

if err is not None:
    failed(C234, "metadata session", err)
elif wire is None:
    failed(C234[4:], "wire headers",
           RuntimeError("the subresource request was never observed"))

if err is None:
    ua, platform, brands_json, entropy = values
    brands = json.loads(brands_json)
    ua_major = None
    for token in ua.split():
        if token.startswith("Chrome/"):
            ua_major = token.split("/", 1)[1].split(".")[0]

    results["2 userAgentData.platform is Windows"] = platform == "Windows"
    # The brand list contains a GREASE entry and "Chromium" alongside the
    # branded name, so this looks for agreement rather than for one entry:
    # every non-GREASE brand must report the UA string's major version.
    results["2 brands version equals the UA string's major version"] = (
        ua_major is not None and bool(brands) and all(
            b["version"] == ua_major for b in brands
            if "Not" not in b["brand"]))
    results["3 high-entropy architecture and bitness match the claim"] = (
        entropy.get("architecture") == "x86"
        and entropy.get("bitness") == "64"
        and entropy.get("platformVersion") == "15.0.0")
    results["3 fullVersionList reports the build's own version"] = (
        REAL_VERSION is not None and bool(entropy.get("fullVersionList"))
        and all(e["version"] == REAL_VERSION
                for e in entropy["fullVersionList"]
                if "Not" not in e["brand"]))

if wire is not None:
    lower = {k.lower(): v for k, v in wire.items()}
    results["4 Sec-CH-UA-Platform matches userAgentData.platform"] = (
        lower.get("sec-ch-ua-platform") == '"Windows"')
    results["4 Sec-CH-UA-Arch and Bitness match the high-entropy values"] = (
        lower.get("sec-ch-ua-arch") == '"x86"'
        and lower.get("sec-ch-ua-bitness") == '"64"')
    results["4 the wire User-Agent equals navigator.userAgent"] = (
        lower.get("user-agent") == values[0])
```

- [ ] **Step 2: Run and confirm the new assertions fail**

```bash
cd ~/camoucrome-verify && python3 scripts/verify_sp1a.py; echo "exit=$?"
```

Expected: criterion 1's 5 assertions still PASS; **the 7 new ones FAIL**, exit=1. In
particular `4 Sec-CH-UA-Platform matches userAgentData.platform` fails while the UA string
already says Windows — that is the incoherence this task exists to close, visible.

- [ ] **Step 3: Substitute the metadata fields**

In `GetUserAgentMetadata()` at around line 648. Each field keeps its real computation and
is then overridden only if a key is set, so an absent key falls back to the truth.

```cpp
blink::UserAgentMetadata GetUserAgentMetadata(bool only_low_entropy_ch) {
  blink::UserAgentMetadata metadata;
  const camoucfg::ConfigScope& scope = camoucfg::GlobalScope();

  // Low entropy client hints.
  metadata.brand_version_list =
      GetUserAgentBrandMajorVersionListInternal(std::nullopt);
  metadata.mobile = GetMobileBitForUAMetadata();
  metadata.platform = GetPlatformForUAMetadata();

  // The brand list is deliberately not configurable: it carries the Chromium
  // version, and this build always reports the version it was compiled from.
  if (std::optional<bool> mobile =
          camoucfg::GetBool(scope, camoucfg::keys::kUaDataMobile)) {
    metadata.mobile = *mobile;
  }
  if (std::optional<std::string> platform =
          camoucfg::GetString(scope, camoucfg::keys::kUaDataPlatform)) {
    metadata.platform = *std::move(platform);
  }

  // For users providing a valid user-agent override via the command line:
  // If kUACHOverrideBlank is enabled, set user-agent metadata with the
  // default blank values, otherwise return the default UserAgentMetadata values
  // to populate and send only the low entropy client hints.
  // Notes: Sending low entropy hints with empty values may cause requests being
  // blocked by web application firewall software, etc.
  //
  // Camoucrome: when configuration is present it takes precedence over the
  // command line, per the precedence rule in 00-conventions.md. Letting
  // --user-agent through here would blank the hints while the string above
  // still claims Windows, which is an incoherence this patch would have
  // created rather than one it inherited.
  std::optional<std::string> custom_ua = GetUserAgentFromCommandLine();
  if (custom_ua.has_value() &&
      !camoucfg::HasKey(scope, camoucfg::keys::kUaOsInfo)) {
    return base::FeatureList::IsEnabled(blink::features::kUACHOverrideBlank)
               ? blink::UserAgentMetadata()
               : metadata;
  }

  if (only_low_entropy_ch) {
    return metadata;
  }

  // High entropy client hints.
  metadata.brand_full_version_list =
      GetUserAgentBrandFullVersionListInternal(std::nullopt);
  metadata.full_version = std::string(version_info::GetVersionNumber());
  metadata.architecture = GetCpuArchitecture();
  metadata.model = BuildModelInfo();
  metadata.form_factors = GetFormFactorsClientHint(metadata, metadata.mobile);
  metadata.bitness = GetCpuBitness();
  metadata.wow64 = IsWoW64();
  metadata.platform_version = GetPlatformVersion();

  // brand_full_version_list and full_version are absent here for the same
  // reason brand_version_list is: they carry the version.
  //
  // form_factors is absent for a different reason -- it is derived from
  // `mobile` just above, so it already follows the configured value, and an
  // independent key would only create the chance for the two to disagree.
  if (std::optional<std::string> architecture =
          camoucfg::GetString(scope, camoucfg::keys::kUaDataArchitecture)) {
    metadata.architecture = *std::move(architecture);
  }
  if (std::optional<std::string> model =
          camoucfg::GetString(scope, camoucfg::keys::kUaDataModel)) {
    metadata.model = *std::move(model);
  }
  if (std::optional<std::string> bitness =
          camoucfg::GetString(scope, camoucfg::keys::kUaDataBitness)) {
    metadata.bitness = *std::move(bitness);
  }
  if (std::optional<bool> wow64 =
          camoucfg::GetBool(scope, camoucfg::keys::kUaDataWow64)) {
    metadata.wow64 = *wow64;
  }
  if (std::optional<std::string> platform_version = camoucfg::GetString(
          scope, camoucfg::keys::kUaDataPlatformVersion)) {
    metadata.platform_version = *std::move(platform_version);
  }
  return metadata;
}
```

Note the ordering detail: `mobile` and `platform` are overridden **before** the
`only_low_entropy_ch` early return, because that return path must carry them; and
`form_factors` is computed **after** `mobile` was overridden, so it follows the configured
value without needing a key of its own.

- [ ] **Step 4: Build and re-run**

```bash
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default content_shell 2>&1 | tail -5
cd ~/camoucrome-verify && python3 scripts/verify_sp1a.py; echo "exit=$?"
```

Expected: **12 PASS, exit=0.**

- [ ] **Step 5: Commit**

```bash
cd ~/chromium/src
git add components/embedder_support/user_agent_utils.cc
git commit -m "embedder_support: let configuration supply the UA client hints"

cd /Users/lang/GolandProjects/github.com/lang315/camoucrome
git add scripts/verify_sp1a.py
git commit -m "verify: assert all three UA channels agree"
```

---

### Task 6: The no-config regression sweep

Criterion 8. Every value in the surfaces table must equal what the pre-patch build
reported when no configuration is set — diffed programmatically, not spot-checked. This is
the assertion that catches a substitution written so that it fires unconditionally, which
is invisible to every other criterion because they all run *with* a config.

**Files:**
- Modify: `scripts/verify_sp1a.py`

**Interfaces:**
- Consumes: the baseline from Task 1; everything from Tasks 4 and 5.
- Produces: criteria 7 and 8 assertions.

- [ ] **Step 1: Write the assertions**

Append to `scripts/verify_sp1a.py`, before the printing loop:

```python
# --- Criteria 7 and 8: nothing changed when nothing was asked for ---
#
# Both spoofed and unconfigured runs are checked against a baseline captured
# from the binary BEFORE this patch existed. Comparing the two runs against
# each other would not catch a substitution that fires unconditionally,
# because both runs execute the same modified code.

C78 = ["7 no property was added to navigator or window",
       "8 unconfigured userAgentData matches the baseline",
       "8 unconfigured high-entropy values match the baseline",
       "8 unconfigured request headers match the baseline"]

base_url, headers_for, stop = echo_server.start(ACCEPT_CH)
try:
    values, err = lib_shell.session(
        None,
        ["navigator.userAgentData.platform",
         "navigator.userAgentData.mobile",
         "JSON.stringify(navigator.userAgentData.brands)",
         HIGH_ENTROPY,
         "Object.keys(navigator).sort().join(',')",
         "Object.keys(window).sort().join(',')",
         "Object.getOwnPropertyNames(Navigator.prototype).sort().join(',')"],
        navigate_to=base_url)
    wire = headers_for("/probe.js") if err is None else None
finally:
    stop()

if err is not None:
    failed(C78, "no-config session", err)
elif baseline_err is not None:
    failed(C78, f"baseline load from {BASELINE}", baseline_err)
else:
    (platform, mobile, brands_json, entropy,
     nav_keys, win_keys, proto_props) = values
    results["7 no property was added to navigator or window"] = (
        nav_keys.split(",") == baseline["navigator_keys"]
        and win_keys.split(",") == baseline["window_keys"]
        and proto_props.split(",") == baseline["navigator_prototype_props"])
    results["8 unconfigured userAgentData matches the baseline"] = (
        platform == baseline["platform"]
        and mobile == baseline["mobile"]
        and json.loads(brands_json) == baseline["brands"])
    results["8 unconfigured high-entropy values match the baseline"] = (
        entropy == baseline["high_entropy"])
    if wire is None:
        failed(["8 unconfigured request headers match the baseline"],
               "wire headers",
               RuntimeError("the subresource request was never observed"))
    else:
        observed = {k.lower(): v for k, v in wire.items()
                    if k.lower().startswith("sec-ch-ua")
                    or k.lower() == "user-agent"}
        results["8 unconfigured request headers match the baseline"] = (
            observed == baseline["request_headers"])
```

- [ ] **Step 2: Run**

```bash
cd ~/camoucrome-verify && python3 scripts/verify_sp1a.py; echo "exit=$?"
```

Expected: **16 PASS, exit=0.**

A failure here is not a test problem. It means a substitution fires when no key is set,
which violates conventions rule 5 and would make the browser detectable *by default* —
fix the producer, never the assertion.

- [ ] **Step 3: Prove the sweep can fail**

A regression check that has never failed is a check nobody has confirmed is wired up. Force
one fault and confirm the report distinguishes it, then revert.

Temporarily change `OsInfoOverrideOr` to return the configured value or
`"X11; Linux x86_64 CAMOUCROME"`, rebuild, and re-run.

Expected: `1 unconfigured UA is byte-identical to the baseline` and
`8 unconfigured request headers match the baseline` FAIL while the spoofed criteria still
PASS. Then revert the change, rebuild, and confirm 16 PASS again.

Record both outputs in the task report.

- [ ] **Step 4: Commit**

```bash
cd /Users/lang/GolandProjects/github.com/lang315/camoucrome
git add scripts/verify_sp1a.py
git commit -m "verify: diff the whole unconfigured UA surface against the baseline"
```

---

### Task 7: Extract the change set and prove it reconstructs

SP0 established this and it caught nothing only because it was done. `~/chromium/src` is
regenerable and the next `gclient sync` may discard it; the patch plus `additions/` is the
durable form.

**Files:**
- Create: `patches/sp1a-ua-producer.patch`
- Modify: `scripts/apply.sh`
- Modify: `README.md`

**Interfaces:**
- Consumes: the four Chromium commits from Tasks 2–5.
- Produces: a change set applicable to a fresh checkout at the pinned base revision.

- [ ] **Step 1: Extract the diff**

`additions/camoucfg/keys.h` and `keys_unittest.cc` are whole new files and belong in
`additions/`, where Task 2 already put them — they must **not** appear in the patch.
Everything else is an edit to a file Chromium already has.

```bash
cd ~/chromium/src
BASE=a90c2cdcb3   # SP0's head; SP1a's commits start after it
git diff $BASE..HEAD -- \
  components/embedder_support/DEPS \
  components/embedder_support/BUILD.gn \
  components/embedder_support/user_agent_utils.cc \
  content/browser/browser_main_loop.cc \
  content/browser/DEPS \
  > /tmp/sp1a-ua-producer.patch
git diff --stat $BASE..HEAD
wc -l /tmp/sp1a-ua-producer.patch
```

`components/camoucfg/BUILD.gn` is also excluded: it is an `additions/` file copied whole,
and Task 2 already updated the copy on the Mac.

Confirm `git diff --stat` lists exactly seven files — the five above plus the two
`components/camoucfg/` files that are handled by `additions/`. Any eighth file is scope
that leaked in; investigate before continuing.

- [ ] **Step 2: Confirm it reverses cleanly**

```bash
cd ~/chromium/src && git apply --check --reverse /tmp/sp1a-ua-producer.patch
echo "exit=$?"
```

Expected: exit=0. A patch that will not reverse cannot be un-applied by `make unpatch`'s
equivalent and is not a usable patch.

- [ ] **Step 3: Copy back and extend `apply.sh`**

Fetch the patch to the Mac as `patches/sp1a-ua-producer.patch`. In `scripts/apply.sh`, add
the second patch after the first, and add `keys.h` / `keys_unittest.cc` to whatever the
script already copies out of `additions/camoucfg/`. Keep the existing structure; do not
rewrite it.

- [ ] **Step 4: Reconstruct from scratch and verify**

The real test. A fresh branch off the **pinned base revision**, both patches applied by
the script alone, rebuilt, and both verifications run.

```bash
cd ~/chromium/src
git checkout -b camoucrome/reconstruct-sp1a 0e8d4a9268118d323f62ca207b40514df39dcaa9
bash /path/to/camoucrome/scripts/apply.sh "$(pwd)"
git diff --stat
~/depot_tools/autoninja -C out/Default content_shell 2>&1 | tail -5
cd ~/camoucrome-verify
python3 scripts/verify_sp0.py;  echo "sp0 exit=$?"
python3 scripts/verify_sp1a.py; echo "sp1a exit=$?"
```

Expected: `apply.sh` succeeds with no fuzz; `git diff --stat` matches the file list from
Step 1; both verifications report **11 PASS exit=0** and **16 PASS exit=0**.

Then return to the working branch:

```bash
cd ~/chromium/src && git checkout camoucrome/sp0 && \
  ~/depot_tools/autoninja -C out/Default content_shell 2>&1 | tail -3
```

- [ ] **Step 5: Update the README status**

Change the status line to record that SP1a landed and what it covers, and update the
sub-project table to show the SP1a/SP1b split and SP1a's reduced dependency (SP0 alone).
Keep the pinned base revision line accurate.

- [ ] **Step 6: Commit**

```bash
cd /Users/lang/GolandProjects/github.com/lang315/camoucrome
git add patches/sp1a-ua-producer.patch scripts/apply.sh README.md
git commit -m "sp1a: extract the producer change set and prove it reconstructs"
```

---

## Verification items deferred out of SP1a

Stated so nobody reads a green SP1a run as SP1 being complete.

| Item | Why deferred |
|---|---|
| 5 — Accept-Language | `navigator.languages` lives in Blink, not the producer. **SP1b.** |
| 6 — worker parity | The producer's values reach workers through `global_scope_creation_params.cc` for free, but SP1's own spec says that is a claim to check, not assume. Checking it needs the SP1b harness that drives dedicated, shared and service workers. **SP1b.** |
| 7 — native accessors on patched properties | SP1a patches no accessor, so Task 6 checks only that no property appeared. The `[native code]` assertion has something to say once SP1b patches accessors. **SP1b.** |
| 9 — Chrome constants | `productSub`, `vendor` and the rest are in `navigator.cc`. **SP1b.** |
| 10 — CDP emulation interaction | D1 resolved: configuration wins, and neutralising `Emulation.setUserAgentOverride` is **SP2**, which owns the CDP surface. SP1a neutralises only the `--user-agent` path, and only inside the function it already edits, because leaving it would have created an incoherence rather than inherited one. |

## Self-review

**Spec coverage.** SP1a claims verification items 1, 2, 3, 4, 7 (partial) and 8; Tasks 4, 5
and 6 assert each. Items 5, 6, 9 and 10 are SP1b or SP2, tabled above. The eight config
keys in the spec's amended surfaces table each have a task.

**Placeholders.** None. Every code step carries the code; every command carries its
expected output.

**Type consistency.** `OsInfoOverrideOr(std::string) -> std::string` is defined in Task 4
Step 3 and called twice in Step 4. `camoucfg::GetString/GetBool/HasKey` match
`additions/camoucfg/mask_config.h` as SP0 shipped it. `lib_shell.session(config,
expressions, navigate_to=None)` is defined in Task 1 Step 5 and used with that signature in
Tasks 4, 5 and 6. `echo_server.start(accept_ch) -> (base_url, headers_for, stop)` is
defined in Task 1 Step 3 and unpacked identically at all three call sites. `HIGH_ENTROPY`
and `ACCEPT_CH` are defined in Task 5 and reused in Task 6, which is why Task 6 must not be
reordered before it.

**Known risk, not resolved here.** Task 5's brand-version assertion treats any brand whose
name contains `Not` as the GREASE entry. That is how the GREASE brand is built today, but
it is a heuristic against a string Chromium deliberately varies. If it misfires, the
symptom is a FAIL on a correct build — the safe direction — and the fix is to compare
against the baseline's brand list instead of pattern-matching.
