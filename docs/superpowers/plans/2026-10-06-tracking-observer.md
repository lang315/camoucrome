# Tracking Observer (phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An opt-in, build-gated logger that records every call of an allow-listed fingerprint Web IDL member (name, origin, top-level site) through Chromium tracing, plus netlog and cookie names, summarised per site by a report script; then a manual facebook.com / instagram.com / threads recon with it.

**Architecture:** One new patch slice `observe` (last in `patches/series`): a GN arg `camou_observe` exported through Blink's `bindings_buildflags`, a disabled-by-default trace category `camou.observe`, a core helper `camou_observe::Record()`, and an allow-list in the bindings generator that emits a `Record` call in the same six callback kinds that already carry `BLINK_BINDINGS_TRACE_EVENT`. Chromium's startup tracing writes the events to JSON; `--log-net-log` writes requests; `scripts/observe_report.py` joins them with cookie names from the profile.

**Tech Stack:** Chromium 154 (`f89f3a4363`, tag 154.0.8037.93), Blink bind_gen (Python), Perfetto track events, Python 3 stdlib + pytest for the scripts.

**Spec:** `docs/superpowers/specs/2026-10-06-tracking-observer-design.md`. Out-of-scope items: `docs/observer/followups.md`. Phase 1b (dashboard) gets its own plan after this one lands.

## Global Constraints

- No JavaScript injection into page-visible scopes; nothing page-visible changes (rule 1, 2). The observer only adds trace events.
- `camou_observe` defaults to `false`; it is **never** added to `settings/build-args.gn` (which `release-args.gn` copies verbatim); `package.py` refuses `camou_observe = true`.
- Trace category exactly `disabled-by-default-camou.observe` (`TRACE_DISABLED_BY_DEFAULT("camou.observe")`).
- Event name exactly the bindings logging id: `Interface.member.get` / `.set` for attributes, `Interface.operation` for operations, `Interface.constructor` for constructors (`_make_bindings_logging_id`, `interface.py`).
- Event args exactly `origin` (security origin serialization) and `site` (window: `GetStorageKey().GetTopLevelSite().Serialize()`; worker: `""`).
- Startup flags exactly: `--trace-startup=disabled-by-default-camou.observe --trace-startup-format=json --trace-startup-file=<f> --trace-startup-duration=0 --trace-startup-record-mode=record-as-much-as-possible --log-net-log=<f>`.
- Cookie reads select only `host_key, name, expires_utc, is_httponly`; never `value` or `encrypted_value`.
- Committed recon data: API names + counts, hosts + query-stripped paths, cookie names. Never cookie values, account ids, payloads, raw traces or netlogs.
- **Parallel workdir (decided 2026-10-06).** This slice is built in a second gclient workdir, `W=~/chromium-observe/src`, on branch `camoucrome/observe`, so it runs alongside the canvas session that owns `~/chromium/src` / `camoucrome/main`. The two workdirs **share refs** (gclient-new-workdir symlinks `.git/refs`): never check out `camoucrome/main` in `W`, never commit to it from here. Verifies aim at this build with `CAMOU_OUT=$HOME/chromium-observe/src/out/Default`.
- Change-set loop: edit and build in `W` on `camoucrome/observe`, commit with subject == patch stem (`observe`), then `scripts/export.sh $W camoucrome/observe`; never hand-edit `patches/`.
- **Builds take turns.** 25 GB RAM does not hold two Chromium builds. Every build in `W` takes `scripts/build_lock.sh acquire observe` first and releases it after; a full build runs only when the canvas session is idle (overnight), agreed with that session by message.
- **Windows is sequential.** `D:\camou-win` is one uncommitted tree shared with the canvas session; Tasks 6-7 start only after that session has released it.
- Build box access: `mcp__sshgate__exec` server `buildpc`, PowerShell outer shell, bash scripts base64-encoded (`wsl -d Ubuntu-24.04 -u lang -- bash -c "echo <b64> | base64 -d | bash"`), no newline and no `<` in the command. Ref-moving git runs in the foreground.
- A GREEN verification counts only after the same check was seen RED.
- The plan branch is pushed to `origin` so the box can fetch it (memory `box-evidence-for-a-branch`); every push is approved by the owner first.
- The box's `out/Default` and the Windows host are shared with other sessions: check for a running ninja or an in-progress rebase before every build or ref-moving git command, and stop rather than interrupt it.

## File Structure

| Path | Responsibility |
|---|---|
| `scripts/observe_report.py` (new) | Parse trace JSON, netlog JSON, Cookies sqlite; print the per-site markdown report. Pure stdlib. Also imported by the verify. |
| `scripts/test_observe_report.py` (new) | pytest on hand-made fixtures. |
| `scripts/verify_observe.py` (new) | Box verification: probe pages, exact counts, RED mode, off arm, timing numbers. |
| `scripts/package.py` (modify) | Refuse `camou_observe = true`. |
| `scripts/test_package.py` (modify) | Test for that refusal. |
| `.github/workflows/build-verify.yml` (modify) | Run the new pytest file and `verify_observe.py`; copy `observe_report.py` to `$VERIFY`. |
| `patches/observe.patch` + `patches/series` (generated by export) | The Chromium-side slice below. |
| `third_party/blink/renderer/platform/BUILD.gn` (box tree) | `camou_observe` arg + `CAMOU_OBSERVE` buildflag. |
| `base/trace_event/builtin_categories.h` (box tree) | Register the category. |
| `third_party/blink/renderer/core/execution_context/camou_observe.{h,cc}` (box tree, new) | `Record()` / `Emit()`. |
| `third_party/blink/renderer/core/execution_context/build.gni` (box tree) | List the two new sources. |
| `third_party/blink/renderer/bindings/scripts/bind_gen/interface.py` (box tree) | Allow-list + `make_camou_observe_record()` + six call sites. |
| `docs/observer/README.md` (new) | Operator guide. |
| `docs/superpowers/measurements/2026-10-<dd>-fb-ig-observe.md` (new) | Recon results. |

---

### Task 0: A second workdir on the build box

The canvas session owns `~/chromium/src` and `camoucrome/main`, and on 2026-10-06 that branch carried its unmerged S2b commits on top of the merged change set. This slice therefore branches from the **merged** change set, not from the branch tip: `camoucrome/main-pre-s2b` (`55d16f0740`, subject `crashpad-no-dumps`), which Step 2 proves equal to `origin/main`'s `patches/`.

**Files:** none.

- [ ] **Step 1: Create the workdir** (reads the existing checkout's objects; writes only under `~/chromium-observe`)

```bash
python3 ~/depot_tools/gclient-new-workdir.py ~/chromium ~/chromium-observe 2>&1 | tail -3
cd ~/chromium-observe/src
git checkout -q -b camoucrome/observe camoucrome/main-pre-s2b
git branch --show-current; git log --oneline -1; git status --porcelain | head -3
```

Expected: branch `camoucrome/observe` at `55d16f0740 crashpad-no-dumps`, empty porcelain. Run the `checkout -b` **immediately**: until then `W`'s HEAD names the shared `camoucrome/main`. If `camoucrome/main-pre-s2b` no longer exists, ask the canvas session (or the owner) for the commit that matches `origin/main` and use that.

- [ ] **Step 2: Prove the base equals `origin/main`'s change set**

```bash
R=/home/lang/actions-runner/_work/camoucrome/camoucrome
git -C $R fetch -q origin main
rm -rf /tmp/observe-base0 /tmp/observe-exp0 && mkdir /tmp/observe-base0 /tmp/observe-exp0
git -C $R archive FETCH_HEAD | tar -x -C /tmp/observe-base0
git -C $R archive FETCH_HEAD | tar -x -C /tmp/observe-exp0
bash /tmp/observe-exp0/scripts/export.sh ~/chromium-observe/src camoucrome/observe | tail -1
diff -rq /tmp/observe-base0 /tmp/observe-exp0; echo diff-rc=$?
```

Expected: `diff-rc=0` (the export of the base reproduces `origin/main` byte for byte). If not, STOP and ask the owner.

- [ ] **Step 3: Toolchain hooks and the out dir**

```bash
cd ~/chromium-observe && gclient runhooks 2>&1 | tail -3
mkdir -p src/out/Default
cp ~/chromium/src/out/Default/args.gn src/out/Default/args.gn
printf '\n# Tracking observer audit build (docs/observer/README.md)\ncamou_observe = true\n' >> src/out/Default/args.gn
cat src/out/Default/args.gn
```

Expected: hooks finish without error (they fetch the clang/rust toolchains into the new workdir); `args.gn` = the dev args plus `camou_observe = true`. `gn gen` waits for Task 3 (the arg does not exist until the slice adds it).

- [ ] **Step 4: Owner questions before the long builds**

- How will the owner drive a headed browser on the Windows host for Task 7 (memory `buildpc-client-layout`: no mouse or keyboard attached)? Physically at the PC, RDP, or plugged-in input. If none, Tasks 6-7 need a different vehicle.
- The overnight build window agreed with the canvas session (message it; the reply sets when Task 3 Step 9 runs).

---

### Task 1: The report script

**Files:**
- Create: `scripts/observe_report.py`
- Test: `scripts/test_observe_report.py`

**Interfaces:**
- Produces: `CATEGORY: str`; `load_events(trace_path) -> list[dict]` (only events of `CATEGORY`, each with `name`, `args.origin`, `args.site`); `surface_counts(events) -> dict[str, dict[str, collections.Counter]]` (key = site, or origin when site is empty → origin → Counter of names); `group_of(name) -> str`; `load_requests(netlog_path) -> list[tuple[str, str, str, str]]` (site, host, path, method); `load_cookie_names(db_path) -> list[tuple[str, str, int, int]]` (host_key, name, expires_utc, is_httponly); `render(events, requests, cookies) -> str`; CLI `observe_report.py TRACE NETLOG [--cookies DB]`.

- [ ] **Step 1: Write the failing tests**

```python
"""observe_report.py on hand-made fixtures shaped like the real files."""
import json
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import observe_report as r  # noqa: E402

CAT = "disabled-by-default-camou.observe"


def ev(name, origin, site, cat=CAT, ph="I"):
    return {"name": name, "cat": cat, "ph": ph, "pid": 1, "tid": 1, "ts": 1,
            "args": {"origin": origin, "site": site}}


def write_trace(tmp_path, events, wrap=True):
    p = tmp_path / "trace.json"
    p.write_text(json.dumps({"traceEvents": events} if wrap else events))
    return p


def test_load_events_keeps_only_the_category(tmp_path):
    p = write_trace(tmp_path, [ev("Navigator.userAgent.get", "https://a.com", "https://a.com"),
                               ev("Other", "x", "y", cat="blink")])
    assert [e["name"] for e in r.load_events(p)] == ["Navigator.userAgent.get"]


def test_load_events_accepts_a_bare_array(tmp_path):
    p = write_trace(tmp_path, [ev("Screen.width.get", "https://a.com", "https://a.com")], wrap=False)
    assert len(r.load_events(p)) == 1


def test_counts_are_real_call_counts_split_by_reading_origin():
    events = [ev("Navigator.userAgent.get", "https://www.facebook.com", "https://news.com")] * 3 + [
        ev("Navigator.userAgent.get", "https://news.com", "https://news.com")]
    c = r.surface_counts(events)
    assert c["https://news.com"]["https://www.facebook.com"]["Navigator.userAgent.get"] == 3
    assert c["https://news.com"]["https://news.com"]["Navigator.userAgent.get"] == 1


def test_worker_events_group_by_origin_when_site_is_empty():
    c = r.surface_counts([ev("WorkerNavigator.hardwareConcurrency.get", "https://a.com", "")])
    assert c["https://a.com"]["https://a.com"]["WorkerNavigator.hardwareConcurrency.get"] == 1


def test_group_of_member_entries_win_over_interface_entries():
    assert r.group_of("Navigator.deviceMemory.get") == "navigator"
    assert r.group_of("Window.matchMedia") == "layout-probe"
    assert r.group_of("Document.cookie.get") == "storage"
    assert r.group_of("Frobnicator.x.get") == "other"


def write_netlog(tmp_path, events):
    data = {"constants": {"logEventTypes": {"URL_REQUEST_START_JOB": 7, "OTHER": 8},
                          "logEventPhase": {"PHASE_BEGIN": 1, "PHASE_END": 2, "PHASE_NONE": 0}},
            "events": events}
    p = tmp_path / "net.json"
    p.write_text(json.dumps(data))
    return p


def start_job(url, nik, sfc="SiteForCookies: {site=null; schemefully_same=false}", phase=1, method="GET"):
    return {"type": 7, "phase": phase, "params": {
        "url": url, "method": method, "network_isolation_key": nik,
        "site_for_cookies": sfc, "initiator": "not an origin"}}


def test_requests_strip_queries_and_use_the_top_frame_site(tmp_path):
    p = write_netlog(tmp_path, [
        start_job("https://www.facebook.com/tr?id=123&ev=PageView", "https://news.com https://news.com"),
        start_job("https://x.com/a", "https://news.com https://news.com", phase=2),
        {"type": 8, "phase": 1, "params": {}},
    ])
    assert r.load_requests(p) == [("https://news.com", "www.facebook.com", "/tr", "GET")]


def test_requests_fall_back_to_site_for_cookies(tmp_path):
    p = write_netlog(tmp_path, [start_job(
        "https://a.com/x?q=1", "null", sfc="SiteForCookies: {site=https://a.com; schemefully_same=true}")])
    assert r.load_requests(p)[0][0] == "https://a.com"


def make_cookies(tmp_path):
    db = tmp_path / "Cookies"
    con = sqlite3.connect(db)
    con.execute("create table cookies (host_key text, name text, value text, encrypted_value blob, "
                "expires_utc integer, is_httponly integer)")
    con.execute("insert into cookies values ('.facebook.com', 'datr', 'SECRET', x'00', 13400000000000000, 1)")
    con.commit()
    con.close()
    return db


def test_cookie_names_never_carry_values(tmp_path):
    rows = r.load_cookie_names(make_cookies(tmp_path))
    assert rows == [(".facebook.com", "datr", 13400000000000000, 1)]
    assert "SECRET" not in repr(rows)


def test_render_lists_counts_hosts_cookies_and_blind_spots(tmp_path):
    events = [ev("Navigator.deviceMemory.get", "https://www.facebook.com", "https://www.facebook.com")] * 2
    requests = [("https://www.facebook.com", "www.facebook.com", "/ajax/bz", "POST")]
    cookies = [(".facebook.com", "datr", 1, 1)]
    out = r.render(events, requests, cookies)
    assert "## https://www.facebook.com" in out
    assert "| navigator | Navigator.deviceMemory.get | https://www.facebook.com | 2 |" in out
    assert "| www.facebook.com | POST /ajax/bz | 1 |" in out
    assert "datr" in out and "SECRET" not in out
    assert "## Not observable" in out and "Intl" in out
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest -q scripts/test_observe_report.py`
Expected: FAIL, `ModuleNotFoundError: No module named 'observe_report'`.

- [ ] **Step 3: Write the implementation**

```python
"""Per-site summary of one tracking-observer session.

Usage: observe_report.py TRACE.json NETLOG.json [--cookies COOKIES_DB]

TRACE comes from --trace-startup=disabled-by-default-camou.observe
--trace-startup-format=json; NETLOG from --log-net-log; COOKIES_DB is a copy of
the profile's Cookies sqlite taken after the browser exited. Prints markdown.
Only names, counts, hosts and query-stripped paths are printed: query strings
carry tokens and cookie values identify the account, so neither is read.
docs/observer/README.md is the operator guide.
"""
import argparse
import collections
import json
import re
import sqlite3
import urllib.parse

CATEGORY = "disabled-by-default-camou.observe"

# Mirror of the allow-list in the observe patch (bind_gen/interface.py).
# A "Interface.member" key wins over its interface's key.
GROUPS = {
    **dict.fromkeys(["Navigator", "WorkerNavigator", "NavigatorUAData", "PluginArray",
                     "MimeTypeArray", "NetworkInformation", "BatteryManager", "Permissions",
                     "StorageManager", "Keyboard", "MediaCapabilities"], "navigator"),
    **dict.fromkeys(["Screen", "ScreenOrientation"], "screen"),
    **dict.fromkeys(["HTMLCanvasElement", "OffscreenCanvas", "CanvasRenderingContext2D",
                     "OffscreenCanvasRenderingContext2D"], "canvas"),
    **dict.fromkeys(["WebGLRenderingContext", "WebGL2RenderingContext"], "webgl"),
    **dict.fromkeys(["GPU", "GPUAdapter"], "webgpu"),
    **dict.fromkeys(["BaseAudioContext", "AudioContext", "OfflineAudioContext",
                     "AnalyserNode", "AudioBuffer"], "audio"),
    **dict.fromkeys(["MediaDevices", "SpeechSynthesis"], "media"),
    "RTCPeerConnection": "webrtc",
    "FontFaceSet": "fonts",
    **dict.fromkeys(["Window.matchMedia", "Window.devicePixelRatio", "Window.outerWidth",
                     "Window.outerHeight", "Window.innerWidth", "Window.innerHeight",
                     "Window.screenX", "Window.screenY", "Window.screenLeft", "Window.screenTop",
                     "HTMLElement.offsetWidth", "HTMLElement.offsetHeight",
                     "Element.getBoundingClientRect", "Element.getClientRects"], "layout-probe"),
    "Document.cookie": "storage",
    "Storage": "storage",
}

NOT_OBSERVABLE = [
    "V8 built-ins: Intl.* (resolvedOptions().timeZone, supportedLocalesOf), "
    "Date.prototype.getTimezoneOffset, Math (phase 2 covers Intl; getTimezoneOffset stays blind)",
    "CSS @media rules in stylesheets (only matchMedia is seen)",
    "Font enumeration by layout measurement beyond the listed layout members",
    "TLS/JA3, HTTP/2 framing, anything computed server-side",
    "Values: the report says that a page read a member, not what it got",
]


def load_events(trace_path):
    with open(trace_path) as f:
        data = json.load(f)
    events = data["traceEvents"] if isinstance(data, dict) else data
    return [e for e in events if e.get("cat") == CATEGORY]


def group_of(name):
    parts = name.split(".")
    return GROUPS.get(".".join(parts[:2])) or GROUPS.get(parts[0], "other")


def surface_counts(events):
    counts = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for e in events:
        args = e.get("args", {})
        origin = args.get("origin", "")
        counts[args.get("site") or origin][origin][e["name"]] += 1
    return counts


_SFC_SITE = re.compile(r"site=([^;}]+)")


def _request_site(params):
    top = params.get("network_isolation_key", "").split(" ")[0]
    if top.startswith("http"):
        return top
    m = _SFC_SITE.search(params.get("site_for_cookies", ""))
    return m.group(1) if m and m.group(1).startswith("http") else ""


def load_requests(netlog_path):
    with open(netlog_path) as f:
        data = json.load(f)
    start = data["constants"]["logEventTypes"]["URL_REQUEST_START_JOB"]
    begin = data["constants"]["logEventPhase"]["PHASE_BEGIN"]
    out = []
    for e in data.get("events", []):
        if e.get("type") != start or e.get("phase") != begin:
            continue
        p = e["params"]
        url = urllib.parse.urlsplit(p["url"])
        out.append((_request_site(p), url.hostname or "", url.path or "/", p.get("method", "")))
    return out


def load_cookie_names(db_path):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return con.execute(
            "select host_key, name, expires_utc, is_httponly from cookies order by host_key, name"
        ).fetchall()
    finally:
        con.close()


def render(events, requests, cookies):
    lines = ["# Tracking observer report", ""]
    counts = surface_counts(events)
    by_site = collections.defaultdict(collections.Counter)
    for site, host, path, method in requests:
        by_site[site][(host, f"{method} {path}")] += 1
    for site in sorted(set(counts) | set(by_site)):
        lines += [f"## {site or '(no site)'}", "", "| group | API | reading origin | calls |",
                  "|---|---|---|---|"]
        for origin, names in sorted(counts.get(site, {}).items()):
            for name, n in sorted(names.items(), key=lambda kv: (group_of(kv[0]), kv[0])):
                lines.append(f"| {group_of(name)} | {name} | {origin} | {n} |")
        reqs = by_site.get(site)
        total = sum(reqs.values()) if reqs else 0
        lines += ["", f"Requests: {total}", "", "| host | request | count |", "|---|---|---|"]
        for (host, req), n in sorted((reqs or {}).items()):
            lines.append(f"| {host} | {req} | {n} |")
        lines.append("")
    if cookies:
        lines += ["## Cookies (names only)", "", "| host | name | expires_utc | httponly |",
                  "|---|---|---|---|"]
        lines += [f"| {h} | {n} | {exp} | {ho} |" for h, n, exp, ho in cookies]
        lines.append("")
    lines += ["## Not observable", ""] + [f"- {item}" for item in NOT_OBSERVABLE]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("trace")
    ap.add_argument("netlog")
    ap.add_argument("--cookies")
    a = ap.parse_args()
    cookies = load_cookie_names(a.cookies) if a.cookies else []
    print(render(load_events(a.trace), load_requests(a.netlog), cookies), end="")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest -q scripts/test_observe_report.py`
Expected: `9 passed`.

- [ ] **Step 5: RED check of one assertion**

Temporarily change `return GROUPS.get(".".join(parts[:2])) or ...` to `return GROUPS.get(parts[0], "other")`; run the tests; expected: `test_group_of_member_entries_win_over_interface_entries` FAILs (`Window.matchMedia` → `other`). Revert; rerun: `9 passed`.

- [ ] **Step 6: Commit**

```bash
git add scripts/observe_report.py scripts/test_observe_report.py
git commit -m "feat(observer): per-site report from trace, netlog and cookie names"
```

---

### Task 2: `package.py` refuses an observer build

**Files:**
- Modify: `scripts/package.py` (in `stage()`, right after the component-build refusal)
- Test: `scripts/test_package.py`

- [ ] **Step 1: Write the failing test** (append to `scripts/test_package.py`)

```python
def test_refuses_observer_build(tree, tmp_path):
    src, out, deps = tree
    (out / "args.gn").write_text("is_debug = false\nis_component_build = false\ncamou_observe = true\n")
    with pytest.raises(SystemExit, match="camou_observe"):
        package.stage(src, out, package.runtime_deps(src, out, deps), "linux-x64", tmp_path / "dist", False)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest -q scripts/test_package.py -k observer`
Expected: FAIL, `DID NOT RAISE`.

- [ ] **Step 3: Implement** (insert after the `if component != "false" and not allow_component:` block)

```python
    if args.get("camou_observe") == "true":
        sys.exit("refusing a build with camou_observe = true: the tracking observer is an audit build, "
                 "never a release (docs/observer/README.md)")
```

- [ ] **Step 4: Run the whole file**

Run: `python3 -m pytest -q scripts/test_package.py`
Expected: all pass, one more than before.

- [ ] **Step 5: Commit**

```bash
git add scripts/package.py scripts/test_package.py
git commit -m "feat(package): refuse an out dir built with camou_observe"
```

---

### Task 3: The `observe` slice in the build tree

**Files (all in `~/chromium-observe/src` on the box):**
- Modify: `third_party/blink/renderer/platform/BUILD.gn`
- Modify: `base/trace_event/builtin_categories.h`
- Create: `third_party/blink/renderer/core/execution_context/camou_observe.h`
- Create: `third_party/blink/renderer/core/execution_context/camou_observe.cc`
- Modify: `third_party/blink/renderer/core/execution_context/build.gni`
- Modify: `third_party/blink/renderer/bindings/scripts/bind_gen/interface.py`
- Modify: `out/Default/args.gn` (not part of the patch)

**Interfaces:**
- Produces: `blink::camou_observe::Record(const char* name, ExecutionContext*)`; buildflag `CAMOU_OBSERVE` in `third_party/blink/renderer/platform/bindings/buildflags.h`; macro `CAMOU_OBSERVE_CATEGORY`; trace events as in Global Constraints.

**Transfer.** The new files and the edit script travel through a throwaway branch, not sshgate chunks: on the Mac create branch `tmp/observe-src` from this worktree's HEAD, add the three files below under `transfer/observe/`, push it (`git push -u origin tmp/observe-src`, owner approves the push), and on the box read them with `git -C $R fetch -q origin tmp/observe-src && git -C $R show FETCH_HEAD:transfer/observe/<file>`. Delete the branch at the end of the task (`git push origin --delete tmp/observe-src`). Nothing under `transfer/` ever reaches this plan's branch.

- [ ] **Step 1: `transfer/observe/camou_observe.h`**

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef THIRD_PARTY_BLINK_RENDERER_CORE_EXECUTION_CONTEXT_CAMOU_OBSERVE_H_
#define THIRD_PARTY_BLINK_RENDERER_CORE_EXECUTION_CONTEXT_CAMOU_OBSERVE_H_

#include "third_party/blink/renderer/core/core_export.h"
#include "third_party/blink/renderer/platform/bindings/buildflags.h"
#include "third_party/blink/renderer/platform/instrumentation/tracing/trace_event.h"

// Tracking observer (docs/observer/README.md). Generated bindings call
// Record() at the entry of every allow-listed Web IDL member. It emits one
// trace event only when the build sets camou_observe = true AND a trace has
// enabled this disabled-by-default category; otherwise it is one category
// check (flag on) or nothing at all (flag off). Nothing page-visible changes.
#define CAMOU_OBSERVE_CATEGORY TRACE_DISABLED_BY_DEFAULT("camou.observe")

namespace blink {

class ExecutionContext;

namespace camou_observe {

#if BUILDFLAG(CAMOU_OBSERVE)
CORE_EXPORT void Emit(const char* name, ExecutionContext* context);

inline void Record(const char* name, ExecutionContext* context) {
  bool enabled = false;
  TRACE_EVENT_CATEGORY_GROUP_ENABLED(CAMOU_OBSERVE_CATEGORY, &enabled);
  if (enabled) [[unlikely]] {
    Emit(name, context);
  }
}
#else
inline void Record(const char*, ExecutionContext*) {}
#endif

}  // namespace camou_observe
}  // namespace blink

#endif  // THIRD_PARTY_BLINK_RENDERER_CORE_EXECUTION_CONTEXT_CAMOU_OBSERVE_H_
```

- [ ] **Step 2: `transfer/observe/camou_observe.cc`**

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "third_party/blink/renderer/core/execution_context/camou_observe.h"

#if BUILDFLAG(CAMOU_OBSERVE)

#include <string>

#include "third_party/blink/renderer/core/execution_context/execution_context.h"
#include "third_party/blink/renderer/core/frame/local_dom_window.h"
#include "third_party/blink/renderer/platform/weborigin/security_origin.h"

namespace blink::camou_observe {

// Only reached with the category enabled, so the string work below never runs
// in an ordinary session. `site` is the top-level site for a window; worker
// scopes have no StorageKey accessor at this pin, so it stays empty and the
// report groups worker reads by origin (a dedicated worker's is its creator's).
void Emit(const char* name, ExecutionContext* context) {
  std::string origin;
  std::string site;
  if (context) {
    if (const SecurityOrigin* security_origin = context->GetSecurityOrigin()) {
      origin = security_origin->ToString().Utf8();
    }
    if (auto* window = DynamicTo<LocalDOMWindow>(context)) {
      site = window->GetStorageKey().GetTopLevelSite().Serialize().Utf8();
    }
  }
  TRACE_EVENT_INSTANT(CAMOU_OBSERVE_CATEGORY, perfetto::StaticString(name),
                      "origin", origin, "site", site);
}

}  // namespace blink::camou_observe

#endif  // BUILDFLAG(CAMOU_OBSERVE)
```

- [ ] **Step 3: `transfer/observe/edit_tree.py`** (edits existing files; every anchor must match exactly once or it aborts before writing anything)

```python
"""Applies the observe slice's edits to a Chromium tree. Usage: edit_tree.py SRC"""
import pathlib
import sys

SRC = pathlib.Path(sys.argv[1])

INTERFACES = ["Navigator", "WorkerNavigator", "NavigatorUAData", "PluginArray", "MimeTypeArray",
              "NetworkInformation", "BatteryManager", "Permissions", "StorageManager", "Keyboard",
              "MediaCapabilities", "Screen", "ScreenOrientation", "HTMLCanvasElement",
              "OffscreenCanvas", "CanvasRenderingContext2D", "OffscreenCanvasRenderingContext2D",
              "WebGLRenderingContext", "WebGL2RenderingContext", "GPU", "GPUAdapter",
              "BaseAudioContext", "AudioContext", "OfflineAudioContext", "AnalyserNode",
              "AudioBuffer", "MediaDevices", "SpeechSynthesis", "RTCPeerConnection", "FontFaceSet",
              "Storage"]
MEMBERS = ["Window.matchMedia", "Window.devicePixelRatio", "Window.outerWidth",
           "Window.outerHeight", "Window.innerWidth", "Window.innerHeight", "Window.screenX",
           "Window.screenY", "Window.screenLeft", "Window.screenTop", "HTMLElement.offsetWidth",
           "HTMLElement.offsetHeight", "Element.getBoundingClientRect", "Element.getClientRects",
           "Document.cookie"]


def fmt_list(items):
    return "".join(f'    "{i}",\n' for i in items)


GENERATOR = '''

# Camoucrome tracking observer (docs/observer/README.md): every call of a member
# of these interfaces, or of these "Interface.member"s, emits one trace event in
# the disabled-by-default-camou.observe category. Keep in sync with GROUPS in
# scripts/observe_report.py.
_CAMOU_OBSERVE_INTERFACES = frozenset([
''' + fmt_list(INTERFACES) + '''])
_CAMOU_OBSERVE_MEMBERS = frozenset([
''' + fmt_list(MEMBERS) + '''])


def make_camou_observe_record(cg_context):
    assert isinstance(cg_context, CodeGenContext)

    interface = cg_context.class_like.identifier
    member = "{}.{}".format(interface, cg_context.property_.identifier)
    if not (interface in _CAMOU_OBSERVE_INTERFACES
            or member in _CAMOU_OBSERVE_MEMBERS):
        return None

    node = TextNode("camou_observe::Record(\\"{}\\", ".format(
        _make_bindings_logging_id(cg_context)) +
                    "${current_execution_context});")
    node.accumulate(
        CodeGenAccumulator.require_include_headers([
            "third_party/blink/renderer/core/execution_context/camou_observe.h"
        ]))
    return node
'''

EDITS = [
    ("third_party/blink/renderer/platform/BUILD.gn",
     "  enable_blink_bindings_tracing = extended_tracing_enabled\n",
     "  enable_blink_bindings_tracing = extended_tracing_enabled\n\n"
     "  # Camoucrome tracking observer (docs/observer/README.md). An audit build\n"
     "  # only: scripts/package.py refuses a release with it on.\n"
     "  camou_observe = false\n"),
    ("third_party/blink/renderer/platform/BUILD.gn",
     '    "BLINK_BINDINGS_TRACE_ENABLED=$enable_blink_bindings_tracing",\n',
     '    "BLINK_BINDINGS_TRACE_ENABLED=$enable_blink_bindings_tracing",\n'
     '    "CAMOU_OBSERVE=$camou_observe",\n'),
    ("base/trace_event/builtin_categories.h",
     '    perfetto::Category(TRACE_DISABLED_BY_DEFAULT("blink.invalidation"))\n        .SetTags("slow"),\n',
     '    perfetto::Category(TRACE_DISABLED_BY_DEFAULT("blink.invalidation"))\n        .SetTags("slow"),\n'
     '    perfetto::Category(TRACE_DISABLED_BY_DEFAULT("camou.observe")),\n'),
    ("third_party/blink/renderer/core/execution_context/build.gni",
     '  "execution_context.cc",\n',
     '  "camou_observe.cc",\n  "camou_observe.h",\n  "execution_context.cc",\n'),
    ("third_party/blink/renderer/bindings/scripts/bind_gen/interface.py",
     "def make_bindings_trace_event(cg_context):\n",
     GENERATOR.lstrip("\n") + "\n\ndef make_bindings_trace_event(cg_context):\n"),
]
CALL = "make_bindings_trace_event(cg_context),\n"

texts = {}
for rel, anchor, _ in EDITS:
    texts.setdefault(rel, (SRC / rel).read_text())
    n = texts[rel].count(anchor)
    if n != 1:
        sys.exit(f"{rel}: anchor found {n} times, expected 1: {anchor!r}")
for rel, anchor, new in EDITS:
    texts[rel] = texts[rel].replace(anchor, new)

rel = "third_party/blink/renderer/bindings/scripts/bind_gen/interface.py"
lines = texts[rel].splitlines(keepends=True)
out, calls = [], 0
for line in lines:
    out.append(line)
    if line.strip() == CALL.strip():
        out.append(line.replace("make_bindings_trace_event", "make_camou_observe_record"))
        calls += 1
if calls != 6:
    sys.exit(f"{rel}: {calls} call sites of make_bindings_trace_event, expected 6")
texts[rel] = "".join(out)

for rel, text in texts.items():
    (SRC / rel).write_text(text)
print("edited", len(texts), "files;", calls, "generator call sites")
```

Notes for the implementer:
- The builtin_categories anchor is the entry after `blink.feature_usage` seen on 2026-10-06 (`builtin_categories.h:309-316`); if the re-pin moved it, pick the nearest `blink.*` disabled-by-default entry and keep the two-line shape.
- The `build.gni` anchor assumes sources there are listed relative to the directory (`"execution_context.cc"`). Before running, check: `grep -n 'execution_context.cc' third_party/blink/renderer/core/execution_context/build.gni`. If the line reads differently, change the anchor and the inserted lines to the same form (and keep alphabetical order).

- [ ] **Step 4: Commit the transfer files, push the throwaway branch**

```bash
git switch -c tmp/observe-src
mkdir -p transfer/observe   # then write the three files above
git add transfer/observe && git commit -m "tmp: observe slice sources for the build box"
git push -u origin tmp/observe-src
git switch -   # back to the plan branch; transfer/ is not on it
```

- [ ] **Step 5: Apply on the box**

```bash
R=/home/lang/actions-runner/_work/camoucrome/camoucrome
git -C $R fetch -q origin tmp/observe-src
cd ~/chromium-observe/src
D=third_party/blink/renderer/core/execution_context
git -C $R show FETCH_HEAD:transfer/observe/camou_observe.h > $D/camou_observe.h
git -C $R show FETCH_HEAD:transfer/observe/camou_observe.cc > $D/camou_observe.cc
git -C $R show FETCH_HEAD:transfer/observe/edit_tree.py > /tmp/edit_tree.py
python3 /tmp/edit_tree.py ~/chromium-observe/src
git status --porcelain
```

Expected: `edited 4 files; 6 generator call sites`, and porcelain lists exactly 4 modified + 2 untracked paths.

- [ ] **Step 6: Turn the arg on in the dev out dir and generate**

```bash
cd ~/chromium-observe/src
grep -q '^camou_observe' out/Default/args.gn || printf '\n# Tracking observer audit build (docs/observer/README.md)\ncamou_observe = true\n' >> out/Default/args.gn
gn gen out/Default 2>&1 | tail -2
grep -n CAMOU_OBSERVE out/Default/gen/third_party/blink/renderer/platform/bindings/buildflags.h
```

Expected: `#define BUILDFLAG_INTERNAL_CAMOU_OBSERVE() (1)`.

- [ ] **Step 7: Check the generated code before the long build**

```bash
cd ~/chromium-observe/src
autoninja -C out/Default third_party/blink/renderer/bindings:generate_bindings_all 2>&1 | tail -2
G=out/Default/gen/third_party/blink/renderer/bindings
grep -rho 'camou_observe::Record(' $G | wc -l
grep -rho 'camou_observe::Record("[^"]*"' $G | sed 's/.*Record("//; s/"$//' | sort -u > /tmp/observe_names.txt
wc -l < /tmp/observe_names.txt
grep -xE 'Navigator\.(userAgent|deviceMemory)\.get|WorkerNavigator\.hardwareConcurrency\.get|HTMLCanvasElement\.toDataURL|Window\.matchMedia|Document\.cookie\.get' /tmp/observe_names.txt
grep -c '^Document\.title' /tmp/observe_names.txt
```

Expected: a call total above 0 (expect several hundred); all six names listed (this is where the mixin naming for `deviceMemory` and `hardwareConcurrency` is confirmed — if a name differs, the expected names in Task 4 and the spec change to what the generator prints); `0` files contain `Document.title`. If the target name `generate_bindings_all` does not exist, list candidates with `gn ls out/Default //third_party/blink/renderer/bindings:* | head` and use the generator action.

- [ ] **Step 8: RED for the generator: flag off generates no calls**

```bash
cd ~/chromium-observe/src
sed -i 's/^camou_observe = true/camou_observe = false/' out/Default/args.gn && gn gen out/Default >/dev/null
grep -n CAMOU_OBSERVE out/Default/gen/third_party/blink/renderer/platform/bindings/buildflags.h
sed -i 's/^camou_observe = false/camou_observe = true/' out/Default/args.gn && gn gen out/Default >/dev/null
```

Expected: `(0)` while off. (The calls stay in generated code either way; with the flag off `Record` is the empty inline. The flag-off build is exercised by the release build in Task 6, which must compile.)

- [ ] **Step 9: Build content_shell and chrome**

```bash
cd ~/chromium-observe/src
R=/home/lang/actions-runner/_work/camoucrome/camoucrome
bash $R/scripts/build_lock.sh acquire observe || exit 1
autoninja -C out/Default content_shell chrome 2>&1 | tail -3
bash $R/scripts/build_lock.sh release observe
```

Only in the build window agreed with the canvas session (Task 0 Step 4). Run detached if it exceeds the sshgate window (memory: detach builds, not git), and release the lock when the detached build ends (put the release in the same detached script). Every later build in this plan (Task 4 fallbacks) takes and releases the lock the same way. Expected: a non-zero step count (a regenerated-bindings build is thousands of steps) and `ninja: build stopped` absent.

- [ ] **Step 10: Dependency gates**

```bash
cd ~/chromium-observe/src
gn check out/Default //third_party/blink/renderer/core/* 2>&1 | tail -1
python3 buildtools/checkdeps/checkdeps.py third_party/blink/renderer/core/execution_context 2>&1 | tail -1
```

Expected: `Header dependency check OK` and `SUCCESS`.

- [ ] **Step 11: Commit in the build tree and export**

```bash
cd ~/chromium-observe/src
git add base/trace_event/builtin_categories.h third_party/blink/renderer/platform/BUILD.gn \
  third_party/blink/renderer/core/execution_context/camou_observe.h \
  third_party/blink/renderer/core/execution_context/camou_observe.cc \
  third_party/blink/renderer/core/execution_context/build.gni \
  third_party/blink/renderer/bindings/scripts/bind_gen/interface.py
git commit -q -m observe && git log --oneline -1
```

Then export into two archives of this plan's branch (pushed to origin), so the diff between them is exactly what the export changed:

```bash
R=/home/lang/actions-runner/_work/camoucrome/camoucrome
git -C $R fetch -q origin <plan-branch>
rm -rf /tmp/observe-repo /tmp/observe-base && mkdir /tmp/observe-repo /tmp/observe-base
git -C $R archive FETCH_HEAD | tar -x -C /tmp/observe-repo
git -C $R archive FETCH_HEAD | tar -x -C /tmp/observe-base
bash /tmp/observe-repo/scripts/export.sh ~/chromium-observe/src camoucrome/observe | tail -1
diff -rq /tmp/observe-base /tmp/observe-repo
```

Expected: `exported <N+1> commits ...`, where N is `wc -l < /tmp/observe-base/patches/series` (33 on 2026-10-06), and `diff -rq` reports exactly `Only in /tmp/observe-repo/patches: observe.patch` and `Files .../patches/series ... differ`. Anything else means the export saw another change: STOP. Bring the two files to the Mac (small enough to print): `base64 -w0 /tmp/observe-repo/patches/observe.patch` and `tail -1 /tmp/observe-repo/patches/series`; on the Mac decode into `patches/observe.patch`, append `observe.patch` to `patches/series`, and check the sha256 of the decoded patch against `sha256sum /tmp/observe-repo/patches/observe.patch` on the box. Then on the Mac:

```bash
git status --porcelain additions patches settings
```

Expected: exactly `?? patches/observe.patch` and ` M patches/series`.

- [ ] **Step 12: Round-trip the patch**

A plain `git worktree` of `src` has none of the DEPS repos, so `gn` cannot run in it; the round trip proves instead that the exported change set reconstructs the branch byte for byte (`gn check` already ran on the real tree in Step 10):

```bash
cd ~/chromium-observe/src
git worktree add -q --detach /tmp/pin $(. /tmp/observe-repo/upstream.env; echo $CHROMIUM_REV)
bash /tmp/observe-repo/scripts/apply.sh /tmp/pin 2>&1 | tail -2
git -C /tmp/pin add -A
git -C /tmp/pin diff --cached --stat camoucrome/observe -- . ':(exclude)components/camoucfg' | tail -3
git worktree remove --force /tmp/pin
```

Expected: `apply.sh` applies every patch including `observe.patch`, and the `diff --stat` against `camoucrome/observe` is empty (`components/camoucfg` is excluded because the branch keeps it untracked and `apply.sh` copies it in).

- [ ] **Step 13: Commit on the Mac, delete the throwaway branch**

```bash
git add patches/observe.patch patches/series
git commit -m "feat(observer): observe slice: allow-listed binding trace events with origin and site"
git push origin --delete tmp/observe-src && git branch -D tmp/observe-src
python3 scripts/check_additions_build.py; echo rc=$?
```

Then push the plan branch and, on the box, prove the box commit and `patches/observe.patch` are byte-identical:

```bash
R=/home/lang/actions-runner/_work/camoucrome/camoucrome
git -C $R fetch -q origin <plan-branch> && git -C $R checkout -q FETCH_HEAD
bash $R/scripts/check_checkout_sync.sh local ~/chromium-observe/src camoucrome/observe; echo rc=$?
```

Expected: both `rc=0`. (The third argument is added in Step 14; until this branch merges, the runner clone's copy is this branch's, fetched above.)

- [ ] **Step 14: `check_checkout_sync.sh` takes a branch**

The script hardcodes `camoucrome/main`, which a second workdir cannot use. In `scripts/check_checkout_sync.sh`:
- usage comment: `# Usage: scripts/check_checkout_sync.sh [ssh-target|local] [checkout-path] [branch]`
- after `SRC="${2:-/home/lang/chromium/src}"` add `BRANCH="${3:-camoucrome/main}"`
- in the `BUILDTREE_BEGIN` line replace both `camoucrome/main` with `$BRANCH` (the string is double-quoted, so it expands locally)
- replace the `for c in` line with `remote_script+='for c in $(git rev-list --reverse --first-parent "$PIN..'"$BRANCH"'"); do`
- in the FAIL messages further down, replace `camoucrome/main` with `$BRANCH`.

Check: on the box, `bash scripts/check_checkout_sync.sh local ~/chromium/src` (default branch) gives the same verdict as before the edit, and `... local ~/chromium-observe/src camoucrome/observe` gives `rc=0`. Then RED: append a comment line to `$W/third_party/blink/renderer/core/execution_context/camou_observe.cc`, run again, expect the FAIL naming that file; `git -C $W checkout -- third_party/blink/renderer/core/execution_context/camou_observe.cc`. Commit:

```bash
git add scripts/check_checkout_sync.sh
git commit -m "fix(sync): check_checkout_sync takes the branch, for a second gclient workdir"
```

Do Step 14 before Step 13's sync check (the numbering keeps the sync check beside the export it guards).

---

### Task 4: `verify_observe.py`

**Files:**
- Create: `scripts/verify_observe.py`
- Modify: `.github/workflows/build-verify.yml` (lines 62, 86, and the run list at 93-99)

**Interfaces:**
- Consumes: `observe_report.load_events`, `observe_report.CATEGORY` (Task 1); `lib_shell.SHELL`, `lib_shell.SHELL_FLAGS`; the trace names confirmed in Task 3 Step 7.

- [ ] **Step 1: Write the verification**

```python
"""Tracking observer verification (docs/superpowers/specs/2026-10-06-tracking-observer-design.md).

Launches content_shell on a local probe with startup tracing, no CDP attached,
and asserts EXACT per-name event counts with the right origin and site. Arms:
  on     category enabled: every row below must match exactly
  off    tracing on for other categories: zero camou.observe events
  --red  same as `on` with every expectation off by one: must FAIL
  --timing  prints call timings with the category off and on (numbers, no verdict)
Run under ~/camoucrome-verify/venv/bin/python3 on the build box.
"""
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

import lib_shell
import observe_report

K = 3
CATEGORY = observe_report.CATEGORY

PROBE = """<!doctype html><title>observe probe</title><canvas id=c width=8 height=8></canvas>
<script>
(async () => {
  const K = %(k)d, out = {};
  for (let i = 0; i < K; i++) {
    navigator.userAgent; navigator.deviceMemory; screen.width;
    document.getElementById('c').toDataURL(); matchMedia('(min-width: 1px)');
    document.cookie; document.title;
  }
  const gl = document.createElement('canvas').getContext('webgl');
  if (!gl) out.webgl = 'no context';
  else for (let i = 0; i < K; i++) gl.getParameter(gl.VERSION);
  const w = new Worker('/worker.js');
  await new Promise(r => { w.onmessage = r; });
  const f = document.createElement('iframe');
  f.src = 'http://localhost:%(port)d/frame.html';
  const framed = new Promise(r => { onmessage = e => { if (e.data === 'frame-done') r(); }; });
  document.body.appendChild(f);
  await framed;
  await fetch('/done', {method: 'POST', body: JSON.stringify(out)});
})();
</script>"""
WORKER = "for (let i = 0; i < %(k)d; i++) navigator.hardwareConcurrency; postMessage('w');"
FRAME = ("<!doctype html><script>for (let i = 0; i < %(k)d; i++) navigator.userAgent;"
         "parent.postMessage('frame-done', '*');</script>")
TIMING = """<!doctype html><canvas id=c width=64 height=64></canvas><script>
(async () => {
  const t0 = performance.now(); for (let i = 0; i < 200000; i++) navigator.userAgent;
  const t1 = performance.now(); const c = document.getElementById('c');
  for (let i = 0; i < 300; i++) c.toDataURL();
  const t2 = performance.now();
  await fetch('/done', {method: 'POST', body: JSON.stringify({ua_200k_ms: t1 - t0, todataurl_300_ms: t2 - t1})});
})();
</script>"""


def serve(k):
    done = threading.Event()
    result = {}

    class H(http.server.BaseHTTPRequestHandler):
        def _send(self, body, ctype):
            data = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            port = self.server.server_port
            pages = {"/probe.html": (PROBE % {"k": k, "port": port}, "text/html"),
                     "/timing.html": (TIMING, "text/html"),
                     "/worker.js": (WORKER % {"k": k}, "application/javascript"),
                     "/frame.html": (FRAME % {"k": k}, "text/html")}
            body, ctype = pages.get(self.path, ("", "text/plain"))
            self._send(body, ctype)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            result.update(json.loads(self.rfile.read(n) or b"{}"))
            self._send("", "text/plain")
            done.set()

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, done, result


def run(page, categories, k=K):
    """One browser session; returns (events or None, page result, trace_path)."""
    server, done, result = serve(k)
    port = server.server_port
    tmp = tempfile.mkdtemp(prefix="camoucrome-observe-")
    trace = os.path.join(tmp, "trace.json")
    argv = [lib_shell.SHELL, *lib_shell.SHELL_FLAGS, f"--user-data-dir={tmp}/profile",
            f"--trace-startup={categories}", "--trace-startup-format=json",
            f"--trace-startup-file={trace}", "--trace-startup-duration=0",
            "--trace-startup-record-mode=record-as-much-as-possible",
            f"http://127.0.0.1:{port}/{page}"]
    env = {k_: v for k_, v in os.environ.items() if not k_.startswith("CAMOU_")}
    proc = subprocess.Popen(argv, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not done.wait(60):
            return None, {"error": "probe never reported"}, trace
    finally:
        proc.terminate()  # graceful: the trace file is written on shutdown
        try:
            proc.wait(30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(10)
        server.shutdown()
    if not os.path.exists(trace):
        return None, dict(result, error="no trace file written"), trace
    return observe_report.load_events(trace), result, trace


def tally(events):
    counts = {}
    for e in events:
        a = e.get("args", {})
        key = (e["name"], a.get("origin"), a.get("site"))
        counts[key] = counts.get(key, 0) + 1
    return counts


def main():
    red = "--red" in sys.argv
    if "--timing" in sys.argv:
        for label, cats in (("off", "blink,loading"), ("on", CATEGORY)):
            _, res, _ = run("timing.html", cats)
            print(f"timing {label}: {res}")
        return 0

    rows = []
    events, res, trace = run("probe.html", CATEGORY)
    if events is None:
        print(f"FAIL on-arm: {res}")
        return 1
    if "webgl" in res:
        print(f"FAIL on-arm: probe reported {res}")
        return 1
    c = tally(events)
    port = None
    for (name, origin, site) in c:
        if origin and origin.startswith("http://127.0.0.1:"):
            port = origin.rsplit(":", 1)[1]
            break
    main_origin, frame_origin, top = (f"http://127.0.0.1:{port}", f"http://localhost:{port}",
                                      "http://127.0.0.1")
    bump = 1 if red else 0
    expect = {(n, main_origin, top): K + bump for n in (
        "Navigator.userAgent.get", "Navigator.deviceMemory.get", "Screen.width.get",
        "HTMLCanvasElement.toDataURL", "Window.matchMedia", "Document.cookie.get",
        "WebGLRenderingContext.getParameter")}
    expect[("WorkerNavigator.hardwareConcurrency.get", main_origin, "")] = K + bump
    expect[("Navigator.userAgent.get", frame_origin, top)] = K + bump
    for key, want in expect.items():
        got = c.get(key, 0)
        rows.append((got == want, f"{key[0]} origin={key[1]} site={key[2]!r}: {got} (want {want})"))
    title = sum(n for (name, _, _), n in c.items() if name.startswith("Document.title"))
    rows.append((title == 0 + bump, f"Document.title (not allow-listed): {title} (want {0 + bump})"))

    off_events, off_res, _ = run("probe.html", "blink,loading")
    off_ok = off_events is not None and len(off_events) == 0
    rows.append((off_ok == (not red), f"off arm (tracing on, category not requested): "
                 f"{'no file' if off_events is None else len(off_events)} camou events (want 0)"))

    passed = sum(ok for ok, _ in rows)
    for ok, text in rows:
        print(("PASS " if ok else "FAIL ") + text)
    print(f"{passed}/{len(rows)} PASS{' (RED mode: expected failures)' if red else ''}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
```

Row count: 7 main-frame rows + 1 worker + 1 iframe + 1 `Document.title` + 1 off arm = **11**.

Fallbacks decided in advance:
- **No trace file after SIGTERM** (`FAIL on-arm: ... no trace file written`): content_shell's SIGTERM path did not run a graceful shutdown. Change `run()` to pass `--trace-startup-duration=20` instead of `0`, and after `/done` poll for the trace file (up to 40 s) before terminating. Same events, no dependence on shutdown. Recon on `chrome` keeps duration 0 and closes the window normally.
- **The iframe row reads `site='http://localhost'`**: `GetStorageKey().GetTopLevelSite()` did not carry the top frame's site. The spec promises the parent's site, so the fix goes in `Emit()`, not in the expectation: derive `site` from the frame tree top, `window->GetFrame()->Tree().Top().GetSecurityContext()->GetSecurityOrigin()` (valid for a RemoteFrame), serialized as a scheme + registrable domain the same way `BlinkSchemefulSite` does (`BlinkSchemefulSite(origin).Serialize()`). Rebuild, re-run RED then GREEN.

- [ ] **Step 2: RED run first**

Get the branch onto the box (`git -C $R fetch -q origin <branch>` + `git archive FETCH_HEAD scripts | tar -x -C /tmp/observe-tree`), then:

```bash
cd /tmp/observe-tree/scripts && CAMOU_OUT=$HOME/chromium-observe/src/out/Default ~/camoucrome-verify/venv/bin/python3 verify_observe.py --red; echo rc=$?
```

Expected: **11 `FAIL` rows**, each count row reading `<K> (want <K+1>)`, the `Document.title` row `0 (want 1)`, the off-arm row `0 camou events (want 0)` marked FAIL, then `0/11 PASS (RED mode: expected failures)` and `rc=1`. An early `FAIL on-arm: ...` line is **not** a passed RED: it is broken infrastructure that also exits 1. If any row PASSes in RED mode, that row measures nothing: fix it before going on.

- [ ] **Step 3: GREEN run**

```bash
cd /tmp/observe-tree/scripts && CAMOU_OUT=$HOME/chromium-observe/src/out/Default ~/camoucrome-verify/venv/bin/python3 verify_observe.py; echo rc=$?
```

Expected: `11/11 PASS`, `rc=0`. Run it 3 times; all three must be 11/11 (an intermittent pass is a FAIL).

- [ ] **Step 4: Report on the real files**

Re-run one GREEN session keeping its temp dir (print `trace` from `run()` in a one-off call or copy it before cleanup), add `--log-net-log=<tmp>/net.json` by hand to the same argv, and run:

```bash
~/camoucrome-verify/venv/bin/python3 /tmp/observe-tree/scripts/observe_report.py <tmp>/trace.json <tmp>/net.json | head -40
```

Expected: a `## http://127.0.0.1` section with the K-counts above and a request table listing `127.0.0.1 GET /probe.html`, `/worker.js`, `localhost GET /frame.html`, `POST /done`. This is the check that the fixture shapes in Task 1 match the real JSON; if a field name differs, fix `observe_report.py` and its fixture together.

- [ ] **Step 5: Timing numbers**

```bash
cd /tmp/observe-tree/scripts && CAMOU_OUT=$HOME/chromium-observe/src/out/Default ~/camoucrome-verify/venv/bin/python3 verify_observe.py --timing
```

Record both lines for the README and the measurement doc. No pass/fail.

- [ ] **Step 6: Wire CI**

In `.github/workflows/build-verify.yml`:
- line 62: append `scripts/observe_report.py` to the `cp` list;
- line 86: append `scripts/test_observe_report.py` to the pytest list;
- after `run verify_crash_dumps.py`: add the guarded line below.

CI builds `~/chromium/src/out/Default`, which does not set `camou_observe` until Task 8 Step 3 decides it. So the new line is guarded and says so out loud, never silently:

```bash
          # needs camou_observe = true in out/Default/args.gn (docs/observer/README.md)
          if grep -q '^camou_observe = true' "$HOME/chromium/src/out/Default/args.gn"; then run verify_observe.py; else echo "SKIP verify_observe.py: camou_observe not set in out/Default/args.gn"; fi
```

- [ ] **Step 7: Commit**

```bash
git add scripts/verify_observe.py .github/workflows/build-verify.yml
git commit -m "test(observer): verify_observe exact counts, worker, iframe, off arm; wire into build-verify"
```

---

### Task 5: Regression on the box and the operator guide

**Files:**
- Create: `docs/observer/README.md`

- [ ] **Step 1: Run CI's checks by hand on the branch tree**

Per memory `box-evidence-for-a-branch`, from `/tmp/observe-tree` with `$VERIFY` copies, and with `CAMOU_OUT=$HOME/chromium-observe/src/out/Default` so every verify measures the observer build (flag on, tracing off): the pytest line from `build-verify.yml:86` (now including `test_observe_report.py`) and every `run verify_*.py` line (93-100). Expected: pytest all passed; every verify prints its usual asserted count (compare with the last green `build-verify` run on main: `gh run list --workflow build-verify -L 1` then `gh run view <id> --log | grep -E 'PASS|passed'`). A verify that was green on main and is not green here is a regression from the always-compiled `Record` calls: STOP and investigate.

- [ ] **Step 2: Write `docs/observer/README.md`**

```markdown
# Tracking observer — operator guide

An audit build that records, per site, which fingerprint surfaces a page reads
(Web IDL member, real call count, reading origin, top-level site) and what it
sends back (requests, cookie names). Observe-only. Design:
`docs/superpowers/specs/2026-10-06-tracking-observer-design.md`.

## Build

Add to the out dir's `args.gn` (never to `settings/build-args.gn`):

    camou_observe = true

`scripts/package.py` refuses such an out dir: an observer build is never a
release. With the arg off, the generated calls compile to nothing.

## Run

    chrome --user-data-dir=<fresh profile> \
      --trace-startup=disabled-by-default-camou.observe \
      --trace-startup-format=json --trace-startup-file=<trace.json> \
      --trace-startup-duration=0 \
      --trace-startup-record-mode=record-as-much-as-possible \
      --log-net-log=<net.json>

Browse, then close the browser normally. The trace is written at shutdown; a
killed browser leaves no trace file. Use one fresh profile per site.

## Read

    cp <profile>/Default/Cookies /tmp/cookies.db
    python3 scripts/observe_report.py <trace.json> <net.json> --cookies /tmp/cookies.db

Per top-level site: surface group, API, reading origin, call count; requests
per host (query strings dropped); cookie names (values are never read). The
raw trace opens in https://ui.perfetto.dev.

## What it cannot see (silence is not safety)

- V8 built-ins: `Intl.*`, `Date.prototype.getTimezoneOffset`, `Math`.
- CSS `@media` rules in stylesheets (only `matchMedia` is seen).
- Font enumeration through layout beyond the listed layout members.
- TLS/JA3, HTTP/2 framing, server-side computation.
- Values: a row says a page read `deviceMemory`, not what it got.

## Detectability

The observer is an audit tool, not a stealth mode. With the category off, each
allow-listed call costs one category check. With it on, each call writes a
trace event; measured overhead: <numbers from verify_observe.py --timing>.
Browse a site normally, on a release build, when staying hidden matters.

## Data handling

Traces, netlogs and profiles hold the operator's real browsing. Keep them on
the machine that made them. Commit only names, counts, hosts and
query-stripped paths.
```

Replace `<numbers from verify_observe.py --timing>` with the two lines recorded in Task 4 Step 5 before committing.

- [ ] **Step 3: Commit**

```bash
git add docs/observer/README.md
git commit -m "docs(observer): operator guide"
```

---

### Task 6: Windows observer build

**Files:** none in the repo.

- [ ] **Step 1: Bring the Windows tree to the change set**

The Windows tree (`D:\camou-win\chromium\src`) carries the change set as an uncommitted working tree (memory `windows-native-build`). Apply only `patches/observe.patch` on top with Git Bash: `git apply --3way <patch>`; expected: clean apply, `git diff --cached --stat` lists the 6 files. Copy the two new files' sha256 against the box's (`sha256sum` both sides) to prove byte equality.

- [ ] **Step 2: Out dir**

`D:\camou-win\chromium\src\out\Observe\args.gn` = `settings/release-args.gn` + `target_cpu = "x64"` + `camou_observe = true`. `gn gen out\Observe`, then a detached `autoninja -C out\Observe chrome` via `Invoke-CimMethod Win32_Process Create` (memory: a `Start-Process` build dies with the ssh session). Expected: non-zero steps, `chrome.exe` present.

- [ ] **Step 3: Smoke the Windows build**

Run `chrome.exe` with the flags from the README against `https://example.com` for 10 s, close it, run `observe_report.py` on the result. Expected: a non-empty `## https://example.com` section is NOT required (example.com reads little); required: the trace file exists and parses, and the netlog shows the request to `example.com`. Then load a local copy of the Task 4 probe through a file served from the host and confirm the 7 main-frame names appear with count K.

---

### Task 7: Recon (manual, with the owner)

**Files:**
- Create: `docs/superpowers/measurements/2026-10-<dd>-fb-ig-observe.md`

The owner drives the browser and logs in by hand; tooling never sees credentials. No automated navigation of Meta sites.

- [ ] **Step 1: Arms**

For each of facebook.com, instagram.com, threads.com: a fresh `--user-data-dir`, the README command line, and these arms, each its own browser session (close between arms so each trace is separate):

1. logged-out landing (load the site, wait 30 s, close);
2. fresh login (log in, wait for the feed, close);
3. established session (relaunch on the same profile as arm 2, browse the feed about 2 minutes, close);
4. a public third-party page embedding the Meta Pixel or a social plugin, if one is found (note the URL in the doc).

- [ ] **Step 2: Reports**

For each arm: copy `Cookies` after exit; run `observe_report.py`; keep raw files on the Windows host only (`D:\camou-win\observe\<site>\<arm>\`).

- [ ] **Step 3: Write the measurement doc**

Sections: method (build, flags, launch with no CDP, arms, dates); per site and arm the report's surface table and request summary (hosts, request counts, `/ajax/bz` count **with the arm's total request count beside it**); cookie names per site; comparison with camoufox's `build-tester/observer/recon_fb_live.json` and `REPORT.md` (surfaces seen here and not there, especially un-spoofed ones and worker reads); the not-observable list; what the data does not show (login walls on logged-out Instagram/Threads). Redaction check before committing: `grep -nE '[?&][a-z_]+=|c_user=|xs=|[0-9]{8,}' <doc>` returns nothing that is a token, id or value.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/measurements/2026-10-<dd>-fb-ig-observe.md
git commit -m "docs(observer): facebook / instagram / threads recon"
```

---

### Task 8: Finish

- [ ] **Step 1:** Update `docs/superpowers/plans/2026-10-02-long-term-roadmap.md` with one line under the backlog or follow-on list: tracking observer phase 1 shipped, phase 1b and V8/Intl pending (`docs/observer/followups.md`).
- [ ] **Step 2:** Use superpowers:finishing-a-development-branch. The PR body carries the evidence: Task 1/2 pytest output, Task 3 Step 7/10 output, Task 4 RED (`0/15`) and GREEN (`15/15` ×2) output (15 rows since phase 1c), Task 5 regression counts vs main, Task 6 build step count, and a link to the measurement doc.
- [ ] **Step 3: Land the slice on `camoucrome/main` BEFORE the PR merges** (final review, 2026-10-07: merging first turns CI red at the sync gate, or into its 180-min timeout while every binding regenerates; `docs/observer/followups.md` "Merge preconditions"). When no other session is mid-rebase or building: in `~/chromium/src`, `git cherry-pick camoucrome/observe` onto `camoucrome/main` (append, subject `observe`); rebuild `out/Default` by hand under the build lock (bindings regenerate; confirm a non-zero step count); `check_checkout_sync.sh local ~/chromium/src` must give `rc=0` against the PR branch; then merge. CI's `verify_observe.py` stays a visible SKIP until the owner decides otherwise. Decide with the owner whether `~/chromium/src/out/Default` gets `camou_observe = true` (CI then runs `verify_observe.py`, at the cost of one full bindings rebuild there) or CI skips that verify until then. Then delete `camoucrome/observe` and, if no longer needed, the workdir (`rm -rf ~/chromium-observe`, after checking nothing in it is uncommitted).
