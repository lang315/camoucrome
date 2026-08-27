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

**`set -o pipefail` before any command whose exit code you intend to read through a pipe.**
`cmd 2>&1 | tail -5; echo "exit=$?"` reports **`tail`'s** status, not `cmd`'s, so a failed
build prints `exit=0`. Demonstrated: `false | tail -1; echo $?` → `0`; with `pipefail` → `1`.
Every build command in this plan had this shape until Task 3 caught it. If you write a new
one, guard it or capture `${PIPESTATUS[0]}`.

Incremental rebuild after touching `user_agent_utils.cc` is roughly one to three minutes;
`is_component_build=true` and `symbol_level=0` are already set.

**Scripts are authored on the Mac and run on the build PC**, in `~/camoucrome-verify/`,
which SP0 created. That directory is not a git repository — the Mac repository is the only
copy of record. So every task that changes a script pushes it across before running it, and
every task that *produces* a file there (Task 1's baseline) pulls it back before
committing. State the direction in the task report; a verification run against a stale copy
of its own script is the failure this note exists to prevent.

Two facts about that directory, both verified on 2026-08-27, both of which will waste a
turn if assumed otherwise:

- **The layout is flat.** Scripts sit directly in `~/camoucrome-verify/`, not in a
  `scripts/` subdirectory — `verify_sp0.py`, `capture_baseline.py`, `smoke.py`. Only
  `baselines/` and `venv/` are subdirectories. In the Mac repository the same files live
  under `scripts/`; the paths differ by design and are not a mistake to correct.
  A flat layout is also what makes `import lib_shell` and `import echo_server` work with no
  path manipulation.
- **Use `venv/bin/python`, never `python3`.** The system interpreter has no Playwright
  (`ModuleNotFoundError: No module named 'playwright'`), so `python3 verify_sp0.py` fails
  in a way that reads like a broken script. Every command in this plan that runs a
  verification uses `venv/bin/python` from `~/camoucrome-verify`, and it is `venv/bin/python3.12`
  underneath.

**Do not use `scp`.** The ssh server is Windows PowerShell, so `scp` lands on the *Windows*
filesystem, while `wsl -d Ubuntu-24.04 -- ...` sees WSL's own. They are two different
`/tmp`, and the failure is quiet in the worst way: `cp /tmp/verify-drop/*.py ~/...` prints
`cannot stat`, the shell keeps going, and the verification then runs the **previous**
version of the script and passes. A green run that proves nothing.

Send file contents through the same stdin script instead, and check the hashes:

```bash
{
  for f in verify_sp0.py lib_shell.py; do
    echo "cat > ~/camoucrome-verify/$f <<'CAMOU_EOF_$f'"
    cat "scripts/$f"
    echo "CAMOU_EOF_$f"
  done
  echo 'cd ~/camoucrome-verify && md5sum verify_sp0.py lib_shell.py'
  echo 'venv/bin/python verify_sp0.py; echo "exit=$?"'
} > /tmp/xfer.sh
CM=~/.ssh/cm-buildpc
/usr/bin/ssh -o ControlPath=$CM -p 2222 lang315@100.81.40.76 \
  "wsl -d Ubuntu-24.04 -u lang -- bash -s" < /tmp/xfer.sh
md5 -q scripts/verify_sp0.py scripts/lib_shell.py   # compare
```

Compare the hashes every time. Any task that runs a verification without confirming the
remote copy is the one it just edited is not verifying its own work.

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
| `ua:platform` | string | `Windows` | `Linux` |
| `ua:platformVersion` | string | `15.0.0` | `` (empty) |
| `ua:architecture` | string | `x86` | `x86` |
| `ua:bitness` | string | `64` | `64` |
| `ua:model` | string | `` (empty) | `` (empty) |
| `ua:mobile` | bool | `false` | `false` |
| `ua:wow64` | bool | `false` | `false` |

Plus one key that predates SP1a: `navigator.hardwareConcurrency`, SP0's tracer-bullet
surface, added to the registry on 2026-08-27 as `kNavigatorHardwareConcurrency`. It is not
new configuration — SP0 already reads it — but both of its call sites were written with the
string literal, which is the thing the registry exists to end. Listing it makes the
registry complete. Converting the call sites is incremental: Task 4 converts
`browser_main_loop.cc`, because it is already editing that file;
`navigator_base.cc` keeps its literal for now rather than pulling an unrelated file into
this task.

`formFactors` gets **no key**: `GetFormFactorsClientHint()` derives it from `mobile`, and
conventions forbids an independent override for a derived value — it would create the
opportunity for incoherence rather than remove it.

The brand list, `full_version` and `brand_full_version_list` get no keys either, because
the version is never spoofed.

**Renamed 2026-08-27, during Task 2's review, while zero call sites existed.** These were
`navigator.uaData:*` until a reviewer pointed out that `navigator.uaData` is not a property
path — the real API is `navigator.userAgentData` — so the dot segment promised a JS path
that does not resolve. That is precisely what the conventions naming rule exists to
prevent, and it was my error in the SP1 spec, faithfully transcribed by Task 2.

Lengthening it to `navigator.userAgentData:` was rejected. Most of this struct is not a
property under any spelling: `architecture`, `bitness`, `platformVersion`, `model` and
`wow64` come only from `getHighEntropyValues()`, and `mobile` and `platform` reach the wire
as `Sec-CH-UA-*` headers whether or not script reads them. A dotted prefix would claim a
correspondence that holds for two of seven members.

So `navigator.*` is reserved for keys that mirror a real JS property path exactly — which
SP1b's keys do — and everything describing the UA identity itself lives under `ua:`,
beside `webGl:` and `canvas:`. Conventions warns that renaming a key after SP6a generates
constants from it is a breaking change; doing it now cost nothing because nothing reads
these yet.

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
cd ~/camoucrome-verify && venv/bin/python verify_sp0.py; echo "exit=$?"
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
venv/bin/python capture_ua_baseline.py > baselines/content_shell-sp0-stock-ua.json
echo "exit=$?"
venv/bin/python -c "import json;d=json.load(open('baselines/content_shell-sp0-stock-ua.json'));print(d['user_agent']);print(d['platform']);print(sorted(d['request_headers']))"
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
- Produces: `camoucfg::keys::kUaOsInfo`, `kNavigatorUserAgent`, `kUaPlatform`,
  `kUaPlatformVersion`, `kUaArchitecture`, `kUaBitness`, `kUaModel`,
  `kUaMobile`, `kUaWow64`, and `camoucfg::keys::kAllKeys` (a span over all of them).
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
set -o pipefail  # without this, $? below is tail's, not the build's
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
inline constexpr char kUaPlatform[] = "ua:platform";
inline constexpr char kUaPlatformVersion[] =
    "ua:platformVersion";
inline constexpr char kUaArchitecture[] = "ua:architecture";
inline constexpr char kUaBitness[] = "ua:bitness";
inline constexpr char kUaModel[] = "ua:model";
inline constexpr char kUaMobile[] = "ua:mobile";
inline constexpr char kUaWow64[] = "ua:wow64";

// Every key above. A new constant must be added here too, which is what makes
// the uniqueness test meaningful.
inline constexpr std::array<std::string_view, 9> kAllKeys = {
    kUaOsInfo,          kNavigatorUserAgent,    kUaPlatform,
    kUaPlatformVersion, kUaArchitecture, kUaBitness,
    kUaModel,       kUaMobile,          kUaWow64,
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
./out/Default/components_unittests --gtest_filter='Camoucfg*:MaskConfig*:ParseConfig*:AssembleRawConfig*:Getters*'
```

Expected: **21 tests pass** — SP0's 19 plus the 2 new ones. A drop below 19 means the
BUILD.gn edit dropped a source; fix it before continuing.

The filter is a union of suite names and not `'Camoucfg*'`, which is what this step said
until Task 2 caught it. Only `CamoucfgKeysTest` carries that prefix; SP0's five suites are
named `AssembleRawConfigTest`, `ParseConfigTest`, `ParseConfigDeathTest`, `GettersTest`
and `MaskConfigTest`. `--gtest_filter='Camoucfg*'` therefore selects **2 of 21** and
reports `PASSED`, which is a false green of exactly the kind that makes a regression check
worthless. Verified on the checkout: the prefix filter runs 2, the union runs 21.

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

Two independent gates block this include and **neither fires on a `.cc`-only change**, so
a normal build stays green with a disallowed include in it.

`gn check` runs during `gn gen`, which `autoninja` triggers only when a `BUILD.gn` or
`.gni` changes — a `.cc` edit alone never regenerates the graph. `checkdeps.py` is not run
by the build at any time. Chromium's include paths are src-root-relative, so the compile
itself succeeds no matter what the GN graph permits.

*Corrected 2026-08-27, mid-task.* This section previously said `autoninja` runs `gn check`
and only `checkdeps.py` was missed. Task 3 demonstrated otherwise on this checkout:
after adding both includes, `autoninja -C out/Default content_shell` exited **0**, while
`gn check` invoked directly exited 1 and named them. SP0's `gn check` failure was real but
came with a `BUILD.gn` edit that forced the regeneration; I generalised from that one
observation and was wrong.

Both gates must therefore be run **explicitly**, and this task's value is demonstrating
each one failing and then passing. A green build proves nothing here.

**Files:**
- Modify: `components/embedder_support/DEPS`
- Modify: `components/embedder_support/BUILD.gn`
- Modify: `components/embedder_support/user_agent_utils.cc` (the include only)

**Interfaces:**
- Consumes: `camoucfg::keys` from Task 2.
- Produces: a `user_agent_utils.cc` that can include camoucfg headers. Tasks 4 and 5
  depend on this and add no further build wiring.

- [ ] **Step 1: Add the include, and watch it fail**

In `components/embedder_support/user_agent_utils.cc`. The exact position, checked in the
file on 2026-08-27: `camoucfg` sorts before `embedder_support`, so the two lines go
**immediately after line 24 `#include "build/build_config.h"` and before line 25
`#include "components/embedder_support/pref_names.h"`** — the first entries in the
`components/` group.

```cpp
#include "components/camoucfg/keys.h"
#include "components/camoucfg/mask_config.h"
```

Build:

Do **not** expect the build to fail — it will not, and that is the point.

```bash
cd ~/chromium/src
set -o pipefail  # without this, $? below is tail's, not the build's
~/depot_tools/autoninja -C out/Default content_shell 2>&1 | tail -5
echo "autoninja exit=$?   # expect 0, and that is the finding, not a pass"
~/depot_tools/gn check out/Default "//components/embedder_support:user_agent"
echo "gn check exit=$?    # expect 1"
python3 buildtools/checkdeps/checkdeps.py --root="$(pwd)" components/embedder_support
echo "checkdeps exit=$?   # expect 1"
```

Expected: `autoninja` **0**; `gn check` **1**, naming
`//components/embedder_support:user_agent` and both includes, and suggesting
`deps = [ "//components/camoucfg:camoucfg" ]`; `checkdeps` **1**, reporting
`Illegal include` for both headers.

Record all three verbatim. The `autoninja` zero is as important as the two failures: it is
the evidence that the normal build loop would have let this through.

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
set -o pipefail  # without this, $? below is tail's, not the build's
~/depot_tools/autoninja -C out/Default content_shell 2>&1 | tail -5
echo "build exit=$?"
python3 buildtools/checkdeps/checkdeps.py --root="$(pwd)" components/embedder_support
echo "checkdeps exit=$?"
```

Expected: build succeeds; `checkdeps` prints `SUCCESS` and exits 0. That invocation was
run against this checkout on 2026-08-27 and passed, so a failure here is your DEPS edit,
not a broken command.

Because it passes today, it is also worth running checkdeps **once before Step 3**, after
the include is added but before the DEPS line. It should fail there, naming the
disallowed include. That is the whole reason this is its own task: `autoninja` runs
`gn check` but never runs `checkdeps.py`, so without that failure nothing in the normal
build loop would ever have told you the grant was missing.

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
    "ua:platform": "Windows",
    "ua:platformVersion": "15.0.0",
    "ua:architecture": "x86",
    "ua:bitness": "64",
    "ua:mobile": False,
    "ua:wow64": False,
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
    # Note on what this asserts, since the name reads bigger than the claim.
    # content_shell's UA reports Chrome/999.0.0.0 -- its own fake version, not
    # this checkout's Chromium milestone. REAL_VERSION comes from the baseline,
    # so it is 999.0.0.0 here, and the assertion is version INVARIANCE: whatever
    # the binary reported before the patch, it must still report. That is the
    # invariant SP1a needs, and it holds in either binary. Task 8, against
    # chrome, is where the number is also the true milestone.
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
    # Guarded like every other fault path here. This was the one exception,
    # and an unreadable log would have exited by traceback before the print
    # loop, discarding the assertions already collected -- the exact collapse
    # this file's structure exists to prevent.
    #
    # Reading the log is sound because lib_shell.launch() opens it "wb", which
    # truncates: each session sees only its own stderr. Verified empirically
    # as well as by reading -- a warning written by one session is gone after
    # the next. Without that, stale text from an earlier run could satisfy the
    # substring check and turn this assertion into a false pass.
    try:
        with open(lib_shell.STDERR_LOG, "rb") as handle:
            stderr = handle.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        failed(["1 navigator.userAgent is refused, not half-honoured"],
               f"stderr read from {lib_shell.STDERR_LOG}", exc)
    else:
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
cd ~/camoucrome-verify && venv/bin/python verify_sp1a.py; echo "exit=$?"
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

**One of these two edits is not exercised by `content_shell`, and the report must say so.**
`ShellContentBrowserClient::GetUserAgent()` (`shell_content_browser_client.cc:747`) calls
`BuildUnifiedPlatformUserAgentFromProduct` *directly*, bypassing `GetUserAgentInternal()`
and therefore the reduced-versus-full choice entirely. So `BuildUserAgentFromProduct` never
runs in the binary this task verifies against.

Patch it anyway. Leaving one of two sibling builders unpatched is how a surface ends up
spoofed on one path and honest on the other, which is worse than either — and `chrome`
routes through `GetUserAgentInternal()`, so the unpatched branch would be live there.
Task 8 is where it gets exercised.

State it plainly in the report rather than letting a green Task 4 imply both edits were
tested. This is the same class of claim as the four false greens recorded in
`00-conventions.md`: the run is real, it simply covers less than its name suggests.

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

Checked on 2026-08-27: `content/browser/DEPS:48` already reads `"+components/camoucfg",`
— a **directory-wide** grant, so `keys.h` is already covered and **this step is a no-op**.
Confirm it rather than assuming:

```bash
grep -n "camoucfg" ~/chromium/src/content/browser/DEPS
```

Expected: one line, `"+components/camoucfg",`. If instead you find a per-header grant
naming only `mask_config.h`, add `"+components/camoucfg/keys.h",` beside it.

The per-header rule in conventions applies to `third_party/blink/renderer/DEPS`, which is
written that way and where least privilege is worth the friction. `content/browser/DEPS`
grants by directory like its neighbours, and SP0 followed that file's own style.

- [ ] **Step 7: Build and re-run**

```bash
set -o pipefail  # without this, $? below is tail's, not the build's
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default content_shell 2>&1 | tail -5
cd ~/camoucrome-verify && venv/bin/python verify_sp1a.py; echo "exit=$?"
```

Expected: **5 PASS, exit=0.**

- [ ] **Step 8: Confirm SP0 has not regressed**

```bash
cd ~/camoucrome-verify && venv/bin/python verify_sp0.py; echo "exit=$?"
cd ~/chromium/src && ./out/Default/components_unittests --gtest_filter='Camoucfg*:MaskConfig*:ParseConfig*:AssembleRawConfig*:Getters*'
```

Expected: 11 PASS exit=0, and **21** unit tests passing. Use the union filter, not
`'Camoucfg*'` — see Task 2 Step 6 for why that one silently runs 2 of 21.

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

> **Amended 2026-08-27, mid-execution — read this before Step 1.**
>
> Task 1 discovered, and an independent check confirmed, that **`content_shell` never calls
> the function this task patches.** `ShellContentBrowserClient::GetUserAgentMetadata()`
> (`content/shell/browser/shell_content_browser_client.cc:750`) returns
> `GetShellUserAgentMetadata()` at `:348`, which builds a `blink::UserAgentMetadata` from
> scratch with `platform = "Unknown"` hardcoded. Only `ChromeContentBrowserClient` calls
> `embedder_support::GetUserAgentMetadata()`.
>
> A browser-driven assertion here would therefore report shell-authored values and could
> never pass, no matter how correct the patch is. Two further walls sit behind that one:
> `ShellBrowserContext::GetClientHintsControllerDelegate()` returns `nullptr` outside test
> harnesses, so `content_shell` emits no `Sec-CH-UA*` headers at all.
>
> **This task's verification moves to `components_unittests`,** which calls
> `GetUserAgentMetadata()` directly — the exact function that ships, in seconds, with no
> browser. `components/embedder_support/user_agent_utils_unittest.cc` already does this at
> `:427`, `:601` and `:684`, so the scaffolding exists.
>
> The end-to-end check that all three channels agree — verification items 2, 3 and 4, and
> SP1a's whole thesis — moves to **Task 8**, against a `chrome` build. It is not dropped.
> Do not add browser assertions for `userAgentData` to `verify_sp1a.py` in this task; they
> would fail for a reason that has nothing to do with your work.
>
> Steps 1 and 2 below are superseded by Steps 1a and 2a. Step 3 is unchanged and is still
> the substance of this task.

- [ ] **Step 1a: Write the failing unit tests**

> **Corrected 2026-08-27, before dispatch, after probing the checkout.** An earlier draft
> of this step used `base::test::ScopedEnvironmentVariableOverride` and put four
> differently-configured tests in one binary. Both halves were wrong.
>
> The class is `base::ScopedEnvironmentVariableOverride`, declared in
> `base/scoped_environment_variable_override.h` — there is no `base::test::` one, so the
> draft would not have compiled.
>
> And it would not have worked even spelled correctly. `camoucfg::Config()`
> (`components/camoucfg/mask_config.cc:18`) is a `base::NoDestructor` function-local
> static: the environment is read **once per process, at first access**, and cached for
> the life of the binary. An override applied after that first touch changes nothing.
> `components_unittests` runs every case in one process, and SP0's own
> `MaskConfigTest.AbsentKeysReturnNullopt` (`mask_config_unittest.cc:208`) calls
> `GlobalScope()` and the real getters — so the config can already be latched before any
> test of yours runs. This is the same property that made SP0 decline a value-level test.
>
> **So the configuration is set outside the process, and each case gets its own
> invocation.** No env-override class, no fixture, no ordering assumptions.

Append to `components/embedder_support/user_agent_utils_unittest.cc`, following the file's
existing style:

```cpp
// These four cases each need a different CAMOU_CONFIG, and camoucfg reads the
// environment once per process and caches it (mask_config.cc:18). So each is
// run in its own invocation of components_unittests with the environment set
// by the runner -- see the command in the step below. Running them together in
// one process would silently test whichever config happened to be latched
// first.
//
// Each case asserts something that is false under the wrong configuration, so
// a mis-run fails loudly instead of quietly exercising the fallback path.

TEST(UserAgentUtilsCamoucfgTest, MetadataFallsBackWhenUnconfigured) {
  // Run with no CAMOU_CONFIG. Every field must be the real computed value.
  blink::UserAgentMetadata metadata = GetUserAgentMetadata();
  EXPECT_EQ(metadata.platform, GetPlatformForUAMetadataForTesting());
  EXPECT_EQ(metadata.architecture, GetCpuArchitecture());
  EXPECT_EQ(metadata.bitness, GetCpuBitness());
  EXPECT_EQ(metadata.wow64, IsWoW64());
}

TEST(UserAgentUtilsCamoucfgTest, MetadataTakesConfiguredValues) {
  blink::UserAgentMetadata metadata = GetUserAgentMetadata();
  EXPECT_EQ(metadata.platform, "Windows");
  EXPECT_EQ(metadata.platform_version, "15.0.0");
  EXPECT_EQ(metadata.architecture, "x86");
  EXPECT_EQ(metadata.bitness, "64");
  EXPECT_FALSE(metadata.mobile);
  EXPECT_FALSE(metadata.wow64);
}

// The version is never spoofed, and this is the assertion that says so. It must
// hold even though the config it runs under sets every other field and tries to
// set the version-bearing ones too.
TEST(UserAgentUtilsCamoucfgTest, ConfigurationCannotMoveTheVersion) {
  blink::UserAgentMetadata metadata = GetUserAgentMetadata();
  EXPECT_EQ(metadata.platform, "Windows");  // proves the config did arrive
  EXPECT_EQ(metadata.full_version, version_info::GetVersionNumber());
  for (const blink::UserAgentBrandVersion& brand :
       metadata.brand_full_version_list) {
    if (brand.brand.find("Not") == std::string::npos) {
      EXPECT_EQ(brand.version, version_info::GetVersionNumber());
    }
  }
}

// form_factors is derived from `mobile` and has no key of its own. Configuring
// mobile must carry it, which is what makes the absence of a key correct rather
// than an omission.
TEST(UserAgentUtilsCamoucfgTest, FormFactorsFollowConfiguredMobile) {
  blink::UserAgentMetadata metadata = GetUserAgentMetadata();
  EXPECT_TRUE(metadata.mobile);
  EXPECT_THAT(metadata.form_factors,
              testing::Contains(blink::kMobileFormFactor));
}
```

`GetPlatformForUAMetadata()` lives in the anonymous namespace, so the first test cannot
call it. Add a shim beside the two the file already has — `GetUnifiedPlatformForTesting()`
at `user_agent_utils.h:113` and `.cc:708` are the pattern to copy:

```cpp
// user_agent_utils.h, beside GetUnifiedPlatformForTesting()
std::string GetPlatformForUAMetadataForTesting();

// user_agent_utils.cc, beside GetUnifiedPlatformForTesting() at :708
std::string GetPlatformForUAMetadataForTesting() {
  return GetPlatformForUAMetadata();
}
```

- [ ] **Step 2a: Run them and confirm three fail**

One invocation per configuration. `components_unittests` is already built from Task 2, so
this needs no rebuild yet.

```bash
cd ~/chromium/src
T=./out/Default/components_unittests

env -u CAMOU_CONFIG $T \
  --gtest_filter='UserAgentUtilsCamoucfgTest.MetadataFallsBackWhenUnconfigured'
echo "fallback exit=$?"

CAMOU_CONFIG='{"ua:platform":"Windows","ua:platformVersion":"15.0.0","ua:architecture":"x86","ua:bitness":"64","ua:mobile":false,"ua:wow64":false}' \
  $T --gtest_filter='UserAgentUtilsCamoucfgTest.MetadataTakesConfiguredValues'
echo "configured exit=$?"

CAMOU_CONFIG='{"ua:platform":"Windows","ua:fullVersionList":"99.0.0.0","ua:brands":"Bogus"}' \
  $T --gtest_filter='UserAgentUtilsCamoucfgTest.ConfigurationCannotMoveTheVersion'
echo "version exit=$?"

CAMOU_CONFIG='{"ua:mobile":true}' \
  $T --gtest_filter='UserAgentUtilsCamoucfgTest.FormFactorsFollowConfiguredMobile'
echo "formfactors exit=$?"
```

Expected before Step 3: **`MetadataFallsBackWhenUnconfigured` passes** (nothing has changed
yet, so the real values are still reported) and the other three **fail**, because nothing
reads those keys.

`env -u CAMOU_CONFIG` on the first one is deliberate. A leftover `CAMOU_CONFIG` in the
shell would make the fallback test compare real values against spoofed ones and fail for a
reason that has nothing to do with the code — SP0 hit exactly this class of leftover and
its verification script filters the whole `CAMOU_CONFIG*` family for it.

If `MetadataTakesConfiguredValues` passes here, before Step 3, something else is already
reading those keys — stop and investigate rather than proceeding.

<details>
<summary>Superseded Steps 1 and 2 (browser assertions) — kept for the record</summary>

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
cd ~/camoucrome-verify && venv/bin/python verify_sp1a.py; echo "exit=$?"
```

Expected: criterion 1's 5 assertions still PASS; **the 7 new ones FAIL**, exit=1. In
particular `4 Sec-CH-UA-Platform matches userAgentData.platform` fails while the UA string
already says Windows — that is the incoherence this task exists to close, visible.

</details>

These two steps are kept rather than deleted because the assertions themselves are correct
and Task 8 reuses them almost unchanged against `chrome`. Only the binary was wrong.

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
          camoucfg::GetBool(scope, camoucfg::keys::kUaMobile)) {
    metadata.mobile = *mobile;
  }
  if (std::optional<std::string> platform =
          camoucfg::GetString(scope, camoucfg::keys::kUaPlatform)) {
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
          camoucfg::GetString(scope, camoucfg::keys::kUaArchitecture)) {
    metadata.architecture = *std::move(architecture);
  }
  if (std::optional<std::string> model =
          camoucfg::GetString(scope, camoucfg::keys::kUaModel)) {
    metadata.model = *std::move(model);
  }
  if (std::optional<std::string> bitness =
          camoucfg::GetString(scope, camoucfg::keys::kUaBitness)) {
    metadata.bitness = *std::move(bitness);
  }
  if (std::optional<bool> wow64 =
          camoucfg::GetBool(scope, camoucfg::keys::kUaWow64)) {
    metadata.wow64 = *wow64;
  }
  if (std::optional<std::string> platform_version = camoucfg::GetString(
          scope, camoucfg::keys::kUaPlatformVersion)) {
    metadata.platform_version = *std::move(platform_version);
  }
  return metadata;
}
```

Note the ordering detail: `mobile` and `platform` are overridden **before** the
`only_low_entropy_ch` early return, because that return path must carry them; and
`form_factors` is computed **after** `mobile` was overridden, so it follows the configured
value without needing a key of its own.

- [ ] **Step 4: Build and re-run the unit tests**

Rebuild, then re-run the **same four invocations from Step 2a** — one per configuration,
not `--gtest_filter='UserAgentUtilsCamoucfgTest.*'`, which would run all four against
whichever config was latched first and is meaningless here.

```bash
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default components_unittests
```

Expected: **all four invocations exit 0.** Paste all four exit codes into the report; a
single summary line cannot show that each ran under its own configuration.

- [ ] **Step 5: Confirm nothing upstream regressed**

This task edits a function with an existing upstream test suite, and the `--user-agent`
precedence change in Step 3 alters a branch those tests exercise. Run the whole file, not
just the new tests:

```bash
env -u CAMOU_CONFIG ./out/Default/components_unittests \
  --gtest_filter='UserAgentUtilsTest.*'
echo "exit=$?"
```

Expected: **23 tests**, all passing. A failure here is a real regression in stock
behaviour, not a test to update — the `custom_ua` early return must behave exactly as
before whenever no `ua:osInfo` key is set.

**The filter is `UserAgentUtilsTest.*`, not `UserAgentUtils*`.** Task 5 caught this and it
is corrected here. The bare prefix also matches `UserAgentUtilsCamoucfgTest`, which needs
one process per configuration, so running it unconfigured reports three failures that are
the new suite behaving exactly as designed. Verified: `UserAgentUtils*` lists 27 tests,
`UserAgentUtilsTest.*` lists 23, and the four-test difference is the new suite.

That is the mirror image of this project's usual failure — a false **red** rather than a
false green — and it is worth naming as such. It costs less than a false green, because
someone investigates, but the cost is real: an investigation that ends in "the check was
wrong" teaches people to distrust the check, which is how a later true failure gets waved
through.

Also confirm SP1a's Task 4 work is untouched:

```bash
cd ~/camoucrome-verify && venv/bin/python verify_sp1a.py; echo "exit=$?"
```

Expected: **5 PASS, exit=0** — criterion 1 only. This task adds no browser assertions; see
the amendment note at the top of this task.

- [ ] **Step 6: Commit**

```bash
cd ~/chromium/src
git add components/embedder_support/user_agent_utils.cc \
        components/embedder_support/user_agent_utils_unittest.cc
git commit -m "embedder_support: let configuration supply the UA client hints"
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

> **Amended 2026-08-27.** Task 5's browser assertions were superseded, so `HIGH_ENTROPY`
> and `ACCEPT_CH` are no longer defined earlier in the file — this task defines them itself
> (they appear in the code below).
>
> Be clear about what each assertion here proves in `content_shell`, so nobody later reads
> more into a green run than it earned:
>
> - `7 no property was added` and the `window`/`navigator` key diffs — **fully load-bearing.**
>   They are the rule-2 guarantee and they work in `content_shell`.
> - `8 unconfigured userAgentData matches the baseline` — a real regression check, but it
>   exercises `GetShellUserAgentMetadata()`, which Task 5 does not patch. It proves this
>   change did not disturb the shell's own producer. It says nothing about ours. Keep it;
>   Task 8 is where the equivalent assertion becomes load-bearing.
> - `8 unconfigured request headers match the baseline` — **corrected 2026-08-27**, after
>   Task 1's capture contradicted the sentence that stood here. `content_shell` is not
>   header-silent: it sends the low-entropy triple `sec-ch-ua`, `sec-ch-ua-mobile` and
>   `sec-ch-ua-platform` on **subresource** requests with no `Accept-CH` needed, and sends
>   nothing at all on **navigation** requests. Only the high-entropy hints are truly absent.
>   Those three values come from `GetShellUserAgentMetadata`, so the assertion is a
>   regression check on the shell's producer, not evidence about ours. It would catch this
>   patch changing or adding headers. Report it as exactly that.
> - `1 unconfigured UA is byte-identical to the baseline` (from Task 4) is the one no-config
>   assertion that genuinely covers this task's producer, because the UA string path does
>   run through `embedder_support` in `content_shell`.

- [ ] **Step 1: Move the shared probes into `lib_shell`, then write the assertions**

First, in `scripts/lib_shell.py`, add the two constants that the capture and every
verification must agree on, and make `capture_ua_baseline.py` import them rather than
keeping its own copy:

```python
# The exact hint list the baseline was captured with. getHighEntropyValues
# returns these plus the three low-entropy values, so a baseline captured with
# this list holds ten keys. Any verification comparing against that baseline
# must request the SAME list -- a shorter request returns fewer keys and an
# equality check against the baseline can then only fail.
HIGH_ENTROPY = """
() => navigator.userAgentData.getHighEntropyValues(
    ["architecture","bitness","platformVersion","model","fullVersionList",
     "wow64","formFactors"])
"""

# content_shell emits none of these high-entropy hints, because
# ShellBrowserContext::GetClientHintsControllerDelegate() returns nullptr
# outside test harnesses; advertising Accept-CH does not change that. It does
# still send the low-entropy triple on subresource requests. Advertising them
# anyway keeps this script identical to the one Task 8 runs against `chrome`,
# where the high-entropy hints do arrive.
ACCEPT_CH = ["Sec-CH-UA-Arch", "Sec-CH-UA-Bitness", "Sec-CH-UA-Platform-Version",
             "Sec-CH-UA-Model", "Sec-CH-UA-Full-Version-List", "Sec-CH-UA-WoW64"]
```

Re-run `capture_ua_baseline.py` is **not** required and must not be done — the committed
baseline is the pre-patch surface and re-capturing it now would record the patched build.
The import only has to produce the same list the capture used, which is why it is copied
verbatim from that file.

Then append to `scripts/verify_sp1a.py`, before the printing loop:

```python
# --- Criteria 7 and 8: nothing changed when nothing was asked for ---
#
# Both spoofed and unconfigured runs are checked against a baseline captured
# from the binary BEFORE this patch existed. Comparing the two runs against
# each other would not catch a substitution that fires unconditionally,
# because both runs execute the same modified code.

# Imported, not redefined. An earlier draft of this step declared its own
# HIGH_ENTROPY asking for five hints while capture_ua_baseline.py asked for
# seven. getHighEntropyValues returns the requested hints plus the three
# low-entropy ones, so the baseline holds ten keys and a five-hint request
# returns eight -- and the assertion below compares them with ==, so it could
# only ever fail. A guaranteed false red, from two copies of one list drifting.
#
# So the list lives in lib_shell, where the capture and every verification
# read the same object and cannot disagree. Move both constants there in this
# step and update capture_ua_baseline.py to import them; do not leave a second
# copy behind.
from lib_shell import ACCEPT_CH, HIGH_ENTROPY

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
cd ~/camoucrome-verify && venv/bin/python verify_sp1a.py; echo "exit=$?"
```

Expected: **9 PASS, exit=0** — the five criterion-1 assertions from Task 4 plus these four.

*Corrected 2026-08-27.* This said 16, arithmetic written when Task 5 was still expected to
add seven browser assertions to this file. The amendment moved those to Task 8 against
`chrome` and the count downstream was never revisited. If you are looking for the missing
seven, they exist — in Task 8.

A failure here is not a test problem. It means a substitution fires when no key is set,
which violates conventions rule 5 and would make the browser detectable *by default* —
fix the producer, never the assertion.

- [ ] **Step 3: Prove the sweep can fail**

A regression check that has never failed is a check nobody has confirmed is wired up. Force
one fault and confirm the report distinguishes it, then revert.

Temporarily change `OsInfoOverrideOr` to return the configured value or
`"X11; Linux x86_64 CAMOUCROME"`, rebuild, and re-run.

Expected: **3 FAIL, 6 PASS.** The three, and the reason each one trips:

| Assertion | Why the mutation reaches it |
|---|---|
| `1 unconfigured UA is byte-identical to the baseline` | its session sets no key at all, so it takes the fallback |
| `1 navigator.userAgent is refused, not half-honoured` | its session sets `navigator.userAgent` but **no `ua:osInfo`**, so it also takes the fallback, and the assertion checks byte-identity against the baseline |
| `8 unconfigured request headers match the baseline` | the `user-agent` header in the no-config session |

*Corrected 2026-08-27, before this step ran.* The plan predicted two and Task 6 predicted
three. Task 6 was right. I had reasoned about which assertions *mention* the unconfigured
case rather than which ones *exercise the fallback path*, and those are different sets —
the second being the one that matters. Three assertions sensitive to this mutation is more
coverage than was designed, not less.

The spoofed criteria must still PASS: they set `ua:osInfo`, so they take the override path
and never see the mutation.

**A fourth failure is worth pausing on** — it would mean the mutation reaches something
neither prediction accounted for. Name the cause of every failure you observe, and if one
has no explanation, stop and report rather than accepting the number.

Then revert, rebuild, and confirm 9 PASS again. Record every output in the report.

- [ ] **Step 4: Commit**

```bash
cd /Users/lang/GolandProjects/github.com/lang315/camoucrome
git add scripts/verify_sp1a.py scripts/lib_shell.py scripts/capture_ua_baseline.py
git commit -m "verify: diff the whole unconfigured UA surface against the baseline"
```

All three files, in one commit. Step 1 moved the shared constants into `lib_shell.py` and
made `capture_ua_baseline.py` import them, so committing `verify_sp1a.py` alone leaves a
HEAD where `from lib_shell import ACCEPT_CH, HIGH_ENTROPY` fails on a fresh checkout — and
nothing in the sweep would catch it, because the sweep could not run at all.

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
set -o pipefail
cd ~/chromium/src
BASE=a90c2cdcb3   # SP0's head; SP1a's commits start after it

# Derive the list instead of trusting one written in advance. A file this plan
# forgot to name would be silently dropped from the patch, and the
# reconstruction check in Step 4 would still pass -- verify_sp1a.py does not
# run unit tests, so losing user_agent_utils_unittest.cc costs nothing it can
# see. That is the fifth false green this project would have shipped.
echo "=== everything SP1a changed ==="
git diff --stat $BASE..HEAD

echo "=== what additions/ owns, and must NOT be in the patch ==="
git diff --name-only $BASE..HEAD -- components/camoucfg/

echo "=== what the patch owns: edits to files Chromium already had ==="
git diff --name-only $BASE..HEAD -- . ':!components/camoucfg/'
```

Expected at this point in the plan — check against what the commands print, and reconcile
any difference before extracting rather than after:

| Path | Owner |
|---|---|
| `components/camoucfg/BUILD.gn` | `additions/` |
| `components/camoucfg/keys.h` | `additions/` |
| `components/camoucfg/keys_unittest.cc` | `additions/` |
| `components/embedder_support/DEPS` | patch |
| `components/embedder_support/BUILD.gn` | patch |
| `components/embedder_support/user_agent_utils.cc` | patch |
| `components/embedder_support/user_agent_utils_unittest.cc` | patch — **Task 5's tests** |
| `content/browser/browser_main_loop.cc` | patch |

`content/browser/DEPS` is deliberately absent: its `camoucfg` grant predates SP1a, so
Task 4 changed nothing there.

Then extract exactly what the third command listed:

```bash
git diff $BASE..HEAD -- . ':!components/camoucfg/' > /tmp/sp1a-ua-producer.patch
grep -c '^diff --git' /tmp/sp1a-ua-producer.patch   # assert the file count
wc -l /tmp/sp1a-ua-producer.patch
```

Assert the count the `grep` prints against the table. A patch with fewer files than the
tree changed is the failure this step exists to prevent, and it is invisible downstream.

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
set -o pipefail  # without this, $? below is tail's, not the build's
~/depot_tools/autoninja -C out/Default content_shell 2>&1 | tail -5
cd ~/camoucrome-verify
venv/bin/python verify_sp0.py;  echo "sp0 exit=$?"
venv/bin/python verify_sp1a.py; echo "sp1a exit=$?"

# The browser verifications cannot see a missing unit-test file, so check the
# unit tests too -- by COUNT, not exit code. This is what makes a patch that
# silently dropped user_agent_utils_unittest.cc fail here instead of shipping.
cd ~/chromium/src
~/depot_tools/autoninja -C out/Default components_unittests
./out/Default/components_unittests \
  --gtest_filter='Camoucfg*:MaskConfig*:ParseConfig*:AssembleRawConfig*:Getters*' \
  --gtest_list_tests | grep -c '^  '     # expect 21
./out/Default/components_unittests \
  --gtest_filter='UserAgentUtilsCamoucfgTest.*' --gtest_list_tests | grep -c '^  '
```

Expected: `apply.sh` succeeds with no fuzz; `git diff --stat` matches the file list from
Step 1; both verifications report **11 PASS exit=0** and **16 PASS exit=0**.

Then return to the working branch:

```bash
cd ~/chromium/src && git checkout camoucrome/sp0 && \
  set -o pipefail  # without this, $? below is tail's, not the build's
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

### Task 8: Prove the three channels agree, against `chrome`

*Added 2026-08-27, after Task 1 established that `content_shell` never calls the patched
metadata producer.* This is verification items 2, 3 and 4 — SP1a's central claim, that one
producer feeds three coherent channels. Without this task SP1a lands with its thesis
untested end to end, and the spec is explicit that item 4 is "the item that fails if the
producer patch is bypassed anywhere."

**This task is the long pole: a full `chrome` build is hours.** It runs last, alone, so it
never competes for CPU with the fast `content_shell` rebuild loop that Tasks 3–6 depend on.

**Files:**
- Create: `scripts/verify_sp1a_chrome.py`
- Create: `baselines/chrome-0e8d4a9268-stock-ua.json`

**Interfaces:**
- Consumes: `lib_shell`, `echo_server` (Task 1); the landed producer patch (Tasks 4–5).
- Produces: nothing later depends on it. It is a gate, not a component.

> **Rewritten 2026-08-27, before dispatch.** The original Steps 1–3 used
> `git worktree add` to get an unpatched tree. That cannot work here. A Chromium checkout
> is a gclient checkout: `.gclient_entries` lists **247** directories that are separate
> repositories, not tracked by `src.git` — including `third_party/llvm-build`, which is the
> toolchain, and `buildtools/linux64`. A worktree would contain none of them and the build
> would fail for lack of a compiler before it reached any Camoucrome code.
>
> Switching branches inside the existing tree avoids the problem entirely, and costs less:
> one full `chrome` build instead of a full build plus a second output directory.

- [ ] **Step 1: Build `chrome` at the pinned base revision**

Use a real branch, not a detached HEAD. Nothing here commits, so detached would be safe in
principle — but conventions warns about detached HEAD for a reason and a named branch costs
one command.

```bash
set -o pipefail
cd ~/chromium/src
git branch camoucrome/base-for-baseline 0e8d4a9268118d323f62ca207b40514df39dcaa9
git checkout camoucrome/base-for-baseline
git log --oneline -1     # must be 0e8d4a9268
```

Then build, in the **foreground** of a ControlPersist-held ssh session. This is hours.
If the client drops, check `pgrep -c "siso|ninja"` before assuming the job died, and never
start a second build in the same output directory.

```bash
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default chrome
```

`out/Default` already holds `content_shell` at 8.8 GB; `chrome` adds to it rather than
replacing it. Confirm `df -h ~/chromium` has room before starting — there were 888 GB free
on 2026-08-27, so this is a formality, but a build that dies on a full disk after four
hours is worth one command to avoid.

- [ ] **Step 2: Teach the capture and launch helpers to drive `chrome`**

`lib_shell.SHELL` is a module-level constant and `launch()` reads it at call time, so
assigning to it works. The launch flags differ: `--ozone-platform=headless` is a
`content_shell` idiom, while `chrome` wants `--headless=new` plus `--no-first-run` and
`--no-default-browser-check`.

Add both as parameters rather than forking the file — a second copy of `launch()` is how the
five hardening fixes in the original drift apart from their copy.

```python
# lib_shell.py -- add a parameter, keep the default identical to today's behaviour
def launch(config, shell=None, extra_flags=None):
    binary = shell or SHELL
    flags = extra_flags if extra_flags is not None else ["--ozone-platform=headless"]
    ...
    proc = subprocess.Popen(
        [binary, "--no-sandbox", *flags,
         f"--user-data-dir={profile}", "--remote-debugging-port=0",
         "about:blank"],
        env=env, stdout=subprocess.DEVNULL, stderr=stderr_file)
```

Thread `shell` and `extra_flags` through `session()` the same way `navigate_to` already is.
Then give `capture_ua_baseline.py` a `--shell` argument that passes them.

**Re-run `verify_sp0.py` and `verify_sp1a.py` after this change** — 11 PASS and 5 PASS, both
exit 0. They call `session()` with the old signature and must be unaffected. A default that
quietly changed the flags would break every earlier verification at once.

- [ ] **Step 3: Capture the `chrome` baseline, then build the patched `chrome`**

```bash
cd ~/camoucrome-verify
venv/bin/python capture_ua_baseline.py \
  --shell ~/chromium/src/out/Default/chrome \
  > baselines/chrome-0e8d4a9268-stock-ua.json
venv/bin/python -c "import json;d=json.load(open('baselines/chrome-0e8d4a9268-stock-ua.json'));print(d['user_agent']);print(d['platform']);print(sorted(d['request_headers']))"
```

Expected, and this is the step that proves the whole task was worth doing: `platform` is
`"Linux"` — **not** `"Unknown"` — and the header list contains `sec-ch-ua-arch` and
`sec-ch-ua-bitness`. Those are exactly what `content_shell` cannot produce, and their
presence confirms `chrome` routes through `embedder_support::GetUserAgentMetadata()` and
has a real `ClientHintsControllerDelegate`.

If they are absent, stop and report. It would mean `chrome` does not deliver client hints
either and the premise of this task is wrong — do not work around it.

Give the file the same `provenance` block shape as the `content_shell` baseline, naming
`chrome`, the base revision, and both producers. Pull it back to the Mac and re-parse it,
as in Task 1 Step 6.

Only then switch back and rebuild:

```bash
cd ~/chromium/src
git checkout camoucrome/sp0
~/depot_tools/autoninja -C out/Default chrome
```

This rebuild is incremental — roughly six source files differ — but `chrome` links far more
than `content_shell`, so expect the link alone to take a while. Rebuild `content_shell` too
before running the earlier verifications again, since switching branches invalidated its
objects as well.

- [ ] **Step 4: Write and run the three-channel verification**

Create `scripts/verify_sp1a_chrome.py`. Its assertions are the ones held in the superseded
Steps 1–2 of Task 5 — they were correct; only the binary was wrong. Take them from there
almost unchanged, with three adjustments:

- point `lib_shell.SHELL` at `~/chromium/src/out/Default/chrome`, and add
  `--headless=new` plus `--no-first-run --no-default-browser-check` to the launch flags;
  `--ozone-platform=headless` is a `content_shell` idiom
- load `baselines/chrome-0e8d4a9268-stock-ua.json`
- keep the criterion-1 assertions too, so this run independently re-confirms the UA string
  in the binary that actually ships

```bash
cd ~/camoucrome-verify && venv/bin/python verify_sp1a_chrome.py; echo "exit=$?"
```

Expected: every assertion PASSes, exit=0 — including `Sec-CH-UA-Platform: "Windows"`,
`Sec-CH-UA-Arch: "x86"`, `Sec-CH-UA-Bitness: "64"`, a `userAgentData.platform` of
`"Windows"`, and a `fullVersionList` still reporting the build's own version.

If the headers disagree with `navigator.userAgentData`, the producer patch is being
bypassed on one path — that is precisely what item 4 exists to detect, and it is a blocking
defect, not a test to relax.

- [ ] **Step 5: Clean up and commit**

```bash
cd ~/chromium/src
git branch -d camoucrome/base-for-baseline   # the revision is pinned in the plan and in provenance
git log --oneline -1                          # confirm you are back on camoucrome/sp0
```

Deleting the throwaway branch loses nothing: the base revision is pinned in this plan, in
the README, and in the baseline's own `provenance` block, so the state is reproducible by
name. Leave `out/Default` alone — rebuilding `chrome` from scratch is the expensive part
and nothing about it needs discarding.

```bash
cd /Users/lang/GolandProjects/github.com/lang315/camoucrome
git add scripts/verify_sp1a_chrome.py scripts/capture_ua_baseline.py \
        baselines/chrome-0e8d4a9268-stock-ua.json
git commit -m "verify: prove all three UA channels agree, against chrome"
```

---

## Verification items deferred out of SP1a

Stated so nobody reads a green SP1a run as SP1 being complete.

Items 2, 3 and 4 are **not** in this table any more: they moved to Task 8, which verifies
them against `chrome`. They are deferred within SP1a, not out of it.

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
