# Observer fast-call counting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the tracking observer count calls that take V8's `[NoAllocDirectCall]` fast path (about 100 canvas-2D/WebGL methods and setters), so that canvas and WebGL draw and state counts are exact instead of lower bounds.

**Architecture:** The `observe` slice's bindings-generator hook (`make_camou_observe_record`) is added to the two fast-callback generators in `bind_gen/interface.py`. The fast paths stay registered: with the category off, a fast call costs one category check, the same as a slow call. `Emit` opens its own `HandleScope`, because a fast callback may not have one, and it copies the script name with `WriteUtf8V2` instead of `ToCoreStringWithNullCheck`, so it makes no change to the V8 heap inside a fast call. A hot-loop verify, RED on the current code, proves the new counts.

**Tech Stack:** Chromium 154.0.8037.93 Blink bindings generator (Python), C++ (Blink core), `scripts/verify_observe.py` (Python 3, content_shell with startup tracing), pytest.

**Spec:**
- The design was approved in chat on 2026-10-08 and is restated below.
- The phase-1 spec it extends is `docs/superpowers/specs/2026-10-06-tracking-observer-design.md`, section "What it cannot see": its V8 fast API calls bullet.
- The follow-up it closes is `docs/observer/followups.md`, section "Open", first bullet.

The approved design, restated:
1. In `interface.py`, call `make_camou_observe_record(cg_context)` in the bodies built by `make_no_alloc_direct_call_callback_def` and `make_attribute_set_nadc_callback_def`.
   - Fast paths stay. No call is counted twice: each call takes exactly one path.
2. In `Emit`, add a `v8::HandleScope` and copy the script name with `String::WriteUtf8V2` into a `std::string`. Both run only while the category is on.
3. In `verify_observe.py`, add hot-loop rows for 100 000 × `fillRect` and 100 000 × the `lineWidth` setter. Each needs an exact count. The rows FAIL on the current build and PASS after the fix, and the 15 existing rows still pass.
4. Update the docs: README "what it cannot see", `observe_report.NOT_OBSERVABLE`, `followups.md` (including its stale "Merge preconditions"), and a resolution note in the spec.
5. Fallback, used only if Task 3 shows that the stack walk misbehaves inside a fast call:
   - Fast callbacks then emit an empty `script`.
   - The hot rows expect `script=""`.
   - The README says so.

## Global Constraints

- **No JavaScript injection, and nothing page-visible may change.** The observer only reports (CLAUDE.md, non-negotiable rule 1).
- **Flag off (`camou_observe = false`):** `Record` stays an empty inline, so the generated fast callbacks change by nothing a compiler keeps.
- **Flag on, category off:** each hooked call, slow or fast, costs one category check. The fast paths must remain registered.
- **RED-first:** the new rows must FAIL on the current build before the fix lands, and `--red` mode must report 0/N.
- **Build box:**
  - Use the sshgate server `buildpc` (PowerShell 5), with WSL user `lang`.
  - Send scripts base64-encoded: no newlines and no literal `<` in the PowerShell command.
  - Detach long jobs with `setsid nohup … < /dev/null &`.
- **Box sharing:**
  - Every build takes `bash /home/lang/actions-runner/_work/camoucrome/camoucrome/scripts/build_lock.sh acquire <owner>` and releases it when done.
  - The S2c session (`canvas-mask-implementation`) owns `~/chromium-s2c`, `~/s2c-*`, `/tmp/s2c-*` and the ref `camoucrome/s2c`; never touch them.
  - The full build runs in the window agreed with S2c, about 19:00–21:30 VN on 2026-10-08, after S2c messages "s2c lock released".
  - Message S2c before taking the lock and after releasing it.
- **Box branch:** `camoucrome/main` in `~/chromium/src` is `… 8cf90b48f8 crashpad-no-dumps → cfd88ac347 observe`. Amend only the `observe` commit, the HEAD. Never rewrite `8cf90b48f8` or anything below it: S2c's landing rebase depends on it.
- **Landing order:**
  1. Land on the box: amend, then build `out/Default`.
  2. Run the sync gate (`rc=0`).
  3. Open the PR.
  4. Merge, only with the owner's approval.
  5. Never merge while either session is building.
- **Data:** commit only API names, counts and hosts. No traces or netlogs.
- **Times:** tell the owner clock times in Vietnam time (UTC+7).
- **Python:** keep it 3.9-compatible, because the Windows host runs `observe_report.py`.

## File Structure

- **`scripts/verify_observe.py`:** adds a `HOT` page, a `HOT_N` constant, the `hot_rows()` function and a second on-arm session for the hot page. The function builds the two fast-path rows and is pure, so it can be unit-tested.
- **`scripts/test_verify_observe.py`:** a unit test for `hot_rows()`.
- **`patches/observe.patch`:** the exported slice. On the box it changes `bind_gen/interface.py` (2 hook sites) and `core/execution_context/camou_observe.cc` (`Emit`).
- **`scripts/observe_report.py`:** drops the fast-call entry from `NOT_OBSERVABLE`.
- **`docs/observer/README.md`:** "what it cannot see" and the verify description.
- **`docs/observer/followups.md`:** removes the fast-call item and updates "Merge preconditions".
- **`docs/superpowers/specs/2026-10-06-tracking-observer-design.md`:** a dated resolution note under the fast-call bullet. The original text stays.

---

### Task 1: Hot-loop verify rows (Mac)

**Files:**
- Modify: `scripts/verify_observe.py`
- Test: `scripts/test_verify_observe.py`

**Interfaces:**
- Produces:
  - `verify_observe.HOT_N`: `int`, set to 100000.
  - `verify_observe.hot_rows(c, main_origin, top, n, bump) -> list[tuple[bool, str]]`. `c` is the dict that `tally()` returns, keyed `(name, origin, site, script)` with value `count`.
  - The page `/hot.html`.
- Consumes: the existing `tally()`, `run()`, `serve()`, `ON_FILTER` and `observe_report.events_of`.

- [ ] **Step 1: Write the failing unit test.** Append to `scripts/test_verify_observe.py`:

```python
def test_hot_rows_need_exact_counts_for_both_fast_paths():
    main, top = "http://127.0.0.1:9", "http://127.0.0.1"
    hot = main + "/hot.html"
    n = 5
    exact = {("CanvasRenderingContext2D.fillRect", main, top, hot): n,
             ("CanvasRenderingContext2D.lineWidth.set", main, top, hot): n}
    assert [ok for ok, _ in v.hot_rows(exact, main, top, n, 0)] == [True, True]
    # a fast path skipping the hook shows up as a short count
    short = dict(exact)
    short[("CanvasRenderingContext2D.fillRect", main, top, hot)] = n - 2
    assert [ok for ok, _ in v.hot_rows(short, main, top, n, 0)] == [False, True]
    # --red bumps every expectation by one
    assert [ok for ok, _ in v.hot_rows(exact, main, top, n, 1)] == [False, False]
    # events from another script do not count
    other = {("CanvasRenderingContext2D.fillRect", main, top, main + "/x.js"): n,
             ("CanvasRenderingContext2D.lineWidth.set", main, top, hot): n}
    assert [ok for ok, _ in v.hot_rows(other, main, top, n, 0)] == [False, True]
```

- [ ] **Step 2: Run it and confirm that it fails.**

Run: `python3 -m pytest -q scripts/test_verify_observe.py`
Expected: FAIL with `AttributeError: module 'verify_observe' has no attribute 'hot_rows'`.

- [ ] **Step 3: Implement the change in `scripts/verify_observe.py`.**
  1. After the `TIMING = …` block, add:

```python
# [NoAllocDirectCall] fast paths (V8 fast API calls) take over once V8 optimizes
# the loop; with the hook only on the slow callbacks these counts come out short.
HOT_N = 100000
HOT = """<!doctype html><canvas id=c width=8 height=8></canvas><script>
(async () => {
  const ctx = document.getElementById('c').getContext('2d');
  for (let i = 0; i < %(n)d; i++) { ctx.lineWidth = 1 + (i & 1); ctx.fillRect(0, 0, 1, 1); }
  await fetch('/done', {method: 'POST', body: '{}'});
})();
</script>"""
```

  2. In `serve()`, add this entry to the `pages` dict:

```python
                     "/hot.html": (HOT % {"n": HOT_N}, "text/html"),
```

  3. After `tally()`, add:

```python
def hot_rows(c, main_origin, top, n, bump):
    """Exact counts for one fast-path method and one fast-path setter on /hot.html."""
    hot = f"{main_origin}/hot.html"
    rows = []
    for name in ("CanvasRenderingContext2D.fillRect", "CanvasRenderingContext2D.lineWidth.set"):
        got = c.get((name, main_origin, top, hot), 0)
        rows.append((got == n + bump, f"{name} x{n} (fast path) script={hot}: {got} (want {n + bump})"))
    return rows
```

  4. In `main()`, insert this just before the off-arm block (the line starting `# off arm:`):

```python
    # fast paths: a separate session, so 2 x HOT_N events do not crowd the probe's trace
    hot_events, hot_res, _ = run("hot.html", ON_FILTER)
    if hot_events is None:
        rows.append((False, f"hot arm: {hot_res}"))
    else:
        hc = tally(observe_report.events_of(hot_events))
        hot_port = next((o.rsplit(":", 1)[1] for (_, o, _, _) in hc
                         if o and o.startswith("http://127.0.0.1:")), None)
        rows += hot_rows(hc, f"http://127.0.0.1:{hot_port}", top, HOT_N, bump)
```

  5. In the module docstring, change the `on` line to: `on     category enabled: every row below must match exactly (probe page, then the hot page for V8 fast API calls)`.

  Note: each `run()` starts its own server on a new port, which is why the hot origin is read from the hot session.

- [ ] **Step 4: Run the tests and confirm that they pass.**

Run: `python3 -m pytest -q scripts/test_verify_observe.py scripts/test_observe_report.py`
Expected: all pass. `test_verify_observe.py` has 2 tests.

- [ ] **Step 5: Commit.**

```bash
git add scripts/verify_observe.py scripts/test_verify_observe.py
git commit -m "test(observer): hot-loop rows for V8 fast API calls"
```

---

### Task 2: RED proof on the current build (box, no build)

**Files:** none. This task produces evidence only, written to the SDD workspace report.

**Interfaces:**
- Consumes: Task 1's `verify_observe.py` from this branch (pushed), and the current box build `~/chromium/src/out/Default`. That build has `camou_observe = true` and no fast-path hook.
- Produces: the RED numbers. These are the 17 rows, of which 15 PASS and the 2 hot rows FAIL with `0 < got < 100000`, plus the `--red` result.

- [ ] **Step 1: Push the branch.**

```bash
git push -u origin worktree-observer-fastcall
```

- [ ] **Step 2: Take a short lock slot.** The run lasts a few minutes, but S2c's cost runs are timing-sensitive, so take the build lock:
  1. Run `build_lock.sh status`.
  2. If it is free, run `acquire observe-fastcall-red`.
  3. If it is held, wait for the next "s2c lock released" message.
  4. Message S2c: "observe-fastcall-red: verify only, ~5 min, no build".

- [ ] **Step 3: Run the verify on the box.** Send this as a base64 script:

```bash
set -u
R=/home/lang/actions-runner/_work/camoucrome/camoucrome
git -C "$R" fetch -q origin worktree-observer-fastcall || exit 4
D=/tmp/observe-fastcall-red; rm -rf "$D"; mkdir -p "$D"
git -C "$R" archive FETCH_HEAD scripts | tar -x -C "$D"
cd "$D/scripts" || exit 5
export CAMOU_OUT=$HOME/chromium/src/out/Default
grep -c '^camou_observe = true' "$CAMOU_OUT/args.gn"
for mode in green --red; do
  arg=""; [ "$mode" = "--red" ] && arg="--red"
  echo "=== verify_observe.py $mode"
  ~/camoucrome-verify/venv/bin/python3 verify_observe.py $arg 2>&1 | tail -20
  echo "rc=${PIPESTATUS[0]}"
done
bash $R/scripts/build_lock.sh release observe-fastcall-red
```

Expected:
- **Green mode:** `15/17 PASS`, `rc=1`. The two failures are the hot rows, each with `0 < got < 100000`.
- **`--red` mode:** `0/17 PASS`, `rc=1`.

**Decision rules:**
- **A hot row shows exactly 100000 on the current build.** The loop never reached the fast path, so the row measures nothing. STOP and report; do not proceed. The remedy is to warm the loop inside a function called repeatedly, then re-run.
- **A hot row shows 0.** The page or the slow hook is broken. STOP and report.

- [ ] **Step 4: Release the lock.** The script releases it. Message S2c "observe-fastcall-red done", and record the exact numbers in the task report.

---

### Task 3: Hook the fast callbacks, land on the box, build (box, in the window)

**Files (box, `~/chromium/src`):**
- Modify: `third_party/blink/renderer/bindings/scripts/bind_gen/interface.py`, in `make_attribute_set_nadc_callback_def` and `make_no_alloc_direct_call_callback_def`.
- Modify: `third_party/blink/renderer/core/execution_context/camou_observe.cc`, in `Emit`.
- Modify (Mac worktree): `patches/observe.patch`, which is re-exported.

**Interfaces:**
- Consumes:
  - `make_camou_observe_record(cg_context)`, already in `interface.py`. It returns a `TextNode`, or `None` when the member is not allow-listed.
  - The `${isolate}` symbol. Both fast generators already define it as `v8_arg_callback_options.isolate`.
- Produces:
  - Generated fast callbacks that call `camou_observe::Record("<Interface>.<member>[.set]", isolate)`.
  - The amended box commit `observe`.
  - A new `patches/observe.patch`.

- [ ] **Step 1: Wait for the window.**
  1. Wait for S2c's "s2c lock released" message, expected around 19:00 VN.
  2. Run `build_lock.sh acquire observe-fastcall`.
  3. Message S2c: "observe-fastcall: amend observe + full out/Default build, ~2.5 h".

- [ ] **Step 2: Check the preconditions in `~/chromium/src`:**
  - the branch is `camoucrome/main`;
  - HEAD is `cfd88ac347` with subject `observe`;
  - the parent is `8cf90b48f8`;
  - `git status --porcelain` is empty;
  - no ninja is running.

  If any of these is false, STOP.

- [ ] **Step 3: Edit `interface.py`.** In `make_no_alloc_direct_call_callback_def`, directly after the line `bind_callback_local_vars(body, cg_context)`, add:

```python
    camou_record = make_camou_observe_record(cg_context)
    if camou_record:
        body.append(camou_record)
```

In `make_attribute_set_nadc_callback_def`, add the same three lines directly after its `bind_callback_local_vars(body, cg_context)` line.

- [ ] **Step 4: Edit `Emit` in `camou_observe.cc`.**
  1. Make the first statement of the function body:

```cpp
  // A [NoAllocDirectCall] fast callback may have no HandleScope open.
  v8::HandleScope handle_scope(isolate);
```

  2. Replace the `std::string script = ToCoreStringWithNullCheck(...).Utf8();` statement with:

```cpp
  // Copied without ToCoreString, which may externalize the V8 string: Emit
  // also runs inside fast API calls, where the V8 heap must not change.
  std::string script;
  v8::Local<v8::String> v8_script =
      v8::StackTrace::CurrentScriptNameOrSourceURL(isolate);
  if (!v8_script.IsEmpty()) {
    script.resize(v8_script->Utf8LengthV2(isolate));
    v8_script->WriteUtf8V2(isolate, script.data(), script.size());
  }
```

  3. Add `#include "v8/include/v8-primitive.h"`.
  4. Remove `#include ".../platform/bindings/v8_binding.h"` only if nothing else in the file uses it. Check with grep for `ToCoreString` and `V8String`.
  5. Update the comment above `Emit` to say that it runs from slow and fast callbacks.

- [ ] **Step 5: Regenerate the bindings and check the generated code before the full build.**

```bash
cd ~/chromium/src && gn gen out/Default >/dev/null && autoninja -C out/Default gen/third_party/blink/renderer/bindings/modules/v8/v8_canvas_rendering_context_2d.cc
grep -n "camou_observe::Record" out/Default/gen/third_party/blink/renderer/bindings/modules/v8/v8_canvas_rendering_context_2d.cc | grep -E "fillRect|lineWidth"
```

Expected: `Record` lines for `fillRect` and for `lineWidth.set` in their fast callbacks, in addition to the slow ones. The fast callback has a `v8::FastApiCallbackOptions&` parameter.

If the generated target name differs, find it with `grep -rl "FillRectOperationCallback" out/Default/gen/third_party/blink/renderer/bindings/modules/v8/ | head`. If the fast setter's name is not `CanvasRenderingContext2D.lineWidth.set`, STOP: the fast and slow names must match.

- [ ] **Step 6: Launch the full build, detached and self-releasing.**

```bash
setsid nohup bash -c 'cd ~/chromium/src && autoninja -C out/Default chrome content_shell components_unittests > /tmp/observe-fastcall-build.log 2>&1; echo EXIT=$? >> /tmp/observe-fastcall-build.log; bash /home/lang/actions-runner/_work/camoucrome/camoucrome/scripts/build_lock.sh release observe-fastcall >> /tmp/observe-fastcall-build.log 2>&1' < /dev/null > /dev/null 2>&1 &
```

Check after 90 s and confirm a NON-ZERO planned step count; thousands are expected, since every binding regenerates. While it runs, check every 30 min and send a one-line status, in VN time, to S2c.

- [ ] **Step 7: After `EXIT=0`, verify on the new build.** Use this branch's `scripts`, fetched and archived as in Task 2, and set `CAMOU_OUT=$HOME/chromium/src/out/Default`. Run three things:
  - `verify_observe.py --red`: expect `0/17`, `rc=1`.
  - `verify_observe.py`, twice: expect `17/17`, `rc=0`, both times.
  - `verify_observe.py --timing`: record the numbers to compare against README's off 88.5 / 29.6 ms and on 512.1 / 30.6 ms. There is no verdict.

  **Fallback rule:**
  - If the green run crashes the renderer (the probe never reports) or shows a wrong `script` on the hot rows, apply design item 5: in fast callbacks, emit an empty `script`.
  - Implement it by giving `Record`/`Emit` a `bool with_script` parameter, which the fast generators pass as `false`.
  - Set `hot_rows` to expect `script=""`.
  - Rebuild; this rebuild is incremental for `camou_observe.cc` and the bindings.
  - Re-run this step.

- [ ] **Step 8: Amend the box commit and export.**

```bash
cd ~/chromium/src
git add third_party/blink/renderer/bindings/scripts/bind_gen/interface.py third_party/blink/renderer/core/execution_context/camou_observe.cc
git commit --amend --no-edit   # subject stays "observe"; parent stays 8cf90b48f8
git log --oneline -2
R=/home/lang/actions-runner/_work/camoucrome/camoucrome
git -C "$R" fetch -q origin worktree-observer-fastcall
D0=/tmp/observe-fastcall-base; D=/tmp/observe-fastcall-export
for d in "$D0" "$D"; do rm -rf "$d"; mkdir -p "$d"; git -C "$R" archive FETCH_HEAD | tar -x -C "$d"; done
bash "$D/scripts/export.sh" ~/chromium/src | tail -5
diff -rq "$D0" "$D"   # expected: only patches/observe.patch differs
base64 -w0 "$D/patches/observe.patch"
```

On the Mac, decode the printed base64 into `patches/observe.patch` in the worktree. Then check that `git diff --stat` touches only `patches/observe.patch`. If export also changed other files, STOP and report.

- [ ] **Step 9: Commit on the Mac and run the sync gate on the box.**

```bash
git add patches/observe.patch
git commit -m "feat(observer): count V8 fast API calls"
git push
```

On the box, re-fetch the branch, archive it into a fresh directory, and run `bash <dir>/scripts/check_checkout_sync.sh local ~/chromium/src`. Expected: `rc=0`. Then message S2c "observe-fastcall done (box camoucrome/main = <new sha>, parent 8cf90b48f8)".

---

### Task 4: Docs and report text (Mac)

**Files:**
- Modify: `scripts/observe_report.py`, the `NOT_OBSERVABLE` list.
- Modify: `docs/observer/README.md`.
- Modify: `docs/observer/followups.md`.
- Modify: `docs/superpowers/specs/2026-10-06-tracking-observer-design.md`, the fast-call bullet near line 180.

**Interfaces:**
- Consumes: the Task 2 RED numbers and the Task 3 GREEN, RED and timing numbers, read from the SDD reports.
- Produces: docs that match the landed code.

- [ ] **Step 1: Edit `scripts/observe_report.py`.** Delete the last `NOT_OBSERVABLE` entry, the string starting `"V8 fast API calls: about 100 canvas-2D/WebGL …"`, through `"are not affected, and a zero row is a real zero",`. If Task 3 took the fallback, replace it instead with:

```python
    "Script attribution of V8 fast API calls (canvas-2D/WebGL draw and state methods "
    "once V8 optimizes the call site): counted, with an empty script",
```

- [ ] **Step 2: Edit `docs/observer/README.md`.**
  1. Delete the "V8 fast API calls" bullet, all six lines, from "What it cannot see". Under the fallback, use the same wording as Step 1 instead.
  2. Where the README describes `verify_observe.py`, add: "17 rows, including a hot loop of 100 000 `fillRect` calls and `lineWidth` sets that V8 runs on its fast API path".
  3. Replace the overhead numbers only if Task 3's timing differs from them. Otherwise leave them.

- [ ] **Step 3: Edit `docs/observer/followups.md`.**
  1. Delete the "V8 fast API calls are not counted." bullet under "## Open".
  2. Replace the whole "## Merge preconditions (before the PR merges)" section with:

```markdown
## Landing order for a slice that changes the bindings

CI (`build-verify`) builds `~/chromium/src/out/Default` from box branch
`camoucrome/main` and starts with the sync gate, so a bindings change lands on
the box first: amend or append the commit in `~/chromium/src` (in a window
agreed with any other session using the box), rebuild `out/Default` by hand
under the build lock, get `scripts/check_checkout_sync.sh` `rc=0`, then merge.
Since 2026-10-08 CI's out dir sets `camou_observe = true` and runs
`verify_observe.py`.
```

  3. Under "## After the facebook recon (2026-10-07)", append the line: `- Counts of canvas-2D/WebGL draw and state calls in that recon are lower bounds (V8 fast API calls were not counted before 2026-10-08); re-run arms to get exact counts.`

- [ ] **Step 4: Edit the spec.** Directly below the fast-call bullet, without editing its text, add the indented line: `  Resolved 2026-10-08: the fast callbacks are hooked too (plan docs/superpowers/plans/2026-10-08-observer-fastcall.md); counts are exact.` Under the fallback, append `, with an empty script on fast calls` before the final full stop.

- [ ] **Step 5: Run the tests.**

Run: `python3 -m pytest -q scripts/test_observe_report.py scripts/test_verify_observe.py scripts/test_package.py`
Expected: all pass.

- [ ] **Step 6: Commit.**

```bash
git add scripts/observe_report.py docs/observer/README.md docs/observer/followups.md docs/superpowers/specs/2026-10-06-tracking-observer-design.md
git commit -m "docs(observer): fast API calls are counted"
```

---

### Task 5: PR (Mac)

- [ ] **Step 1: Run the pre-flight checks.**
  - `python3 scripts/check_additions_build.py`
  - `python3 scripts/gen_keys.py --check`
  - `python3 -m pytest -q scripts/test_observe_report.py scripts/test_verify_observe.py scripts/test_package.py scripts/test_gen_keys.py scripts/test_build_lock.py`

  Expected: everything passes.

- [ ] **Step 2: Push and open the PR** against `main`. The PR body must contain:
  - Task 2's RED numbers: 15/17 with the exact short counts, and `--red` 0/17.
  - Task 3's GREEN result (17/17 twice), RED result (0/17) and timing.
  - The build's step count and `EXIT=0`.
  - The sync gate `rc=0`.
  - The new box sha.

  End the body with the attribution line.

- [ ] **Step 3: Merge only after the owner approves**, and only while neither session is building. CI (`build-verify`) on main then builds 0 steps and runs `verify_observe.py` with 17 rows. Confirm that the run is green.

## After this plan (not in scope)

- Rebuild the Windows `out\Observe` tree before the instagram/threads recon (follow-up E), so the recon gets exact canvas counts. This needs a host window after S2c's Windows build.
