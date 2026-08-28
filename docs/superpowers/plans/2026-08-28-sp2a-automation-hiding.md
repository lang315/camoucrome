# SP2a — Unconditional automation-signal suppression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two automation signals that are *decided, unconditional, and fatal on
their own* — `navigator.webdriver` and the `HeadlessChrome` product token — so that the
identity work in SP1/SP3/SP4 stops being worth nothing.

**Architecture:** Two C++ edits, each one hunk, at the single site that produces each
signal. `Navigator::webdriver()` returns `false` before either of its two sources is
consulted. `GetUserAgentInternal()` stops inserting the `Headless` prefix. Neither takes a
config key: a Camoucrome that can be configured to announce itself as automated has failed
at its one job. One new verification script drives both binaries over CDP.

**Tech Stack:** C++20 (Chromium style), GN/Siso, `content_shell` **and** `chrome`,
Python 3 + Playwright over CDP, `components_unittests` for the in-process gate.

---

## Why this is SP2a and not SP2

SP2's spec carries six open decisions, and four of them (D1, D2, D3, D6) say in their own
text that they cannot be settled without a measurement nobody has run. D1 is explicit:

> No recommendation yet, deliberately … Committing to a V8 inspector patch before knowing
> whether a free driver-side fix closes the same vectors would be the single most expensive
> mistake available in this sub-project. **Sequence the measurement first.**

A plan cannot contain tasks for an outcome that is unknown without containing placeholders,
which the plan format forbids. So SP2 splits the way SP1, SP5 and SP6 already did:

- **SP2a (this plan)** — everything the spec has already decided, whose fix is one site and
  whose verification runs today.
- **SP2b (later)** — everything gated on measurement: `Runtime.enable` (4.3/D1), trusted
  input (4.4/D3), isolated-world auditing (4.2), humanized cursor paths (4.5, which the
  spec itself already assigns to "a second phase, after the leak work lands"), and
  `window.chrome` (4.7/D7, which additionally needs SP7's branding decision).

The split is not arbitrary along a difficulty line. It falls exactly where the spec stops
saying *what to do* and starts saying *what to find out*.

**These two surfaces belong in the same sub-project rather than one each,** because SP2's
own §5 makes them a coherence pair: a `false` `webdriver` beside a UA string that says
`HeadlessChrome` is a louder signal than either alone. Landing them together means one
session can assert both, which criterion 8 does.

## What reading the tree changed before any code was written

Six facts, each checked against `~/chromium/src` at `8f0635af04`. Facts 1–4 came from
reading the tree before writing the plan. **Facts 5 and 6 came from the Task 1 implementer
stopping at the Step 5 gate rather than adjusting the criteria to match the count** — the
gate found two defects in this plan, one of which (fact 6) broke its central claim. That is
the gate working exactly as intended, and it is recorded here rather than quietly patched
because the plan's own self-review had called those counts load-bearing and still got them
wrong.

**1. `content_shell` never reaches the `Headless` insert, so it cannot verify the fix.**
`ShellContentBrowserClient::GetUserAgent()`
(`content/shell/browser/shell_content_browser_client.cc:732`) builds its product from
scratch — `base::StringPrintf("Chrome/%s.0.0.0", CONTENT_SHELL_MAJOR_VERSION)` — and calls
`BuildUnifiedPlatformUserAgentFromProduct` directly at `:747`. It never calls
`GetUserAgentInternal()`, which is where the insert lives. **`content_shell` has no
`HeadlessChrome` under any switch.** This is the identical sibling-method trap conventions
records for `GetUserAgentMetadata`, on the sibling that conventions said was *safe*. Task 2
therefore runs against `chrome`, and Task 1 — which patches Blink core — keeps the fast
`content_shell` loop.

**2. Suppressing the prefix breaks an existing upstream unit test, and that is the best
news in this plan.** `components/embedder_support/user_agent_utils_unittest.cc:1040`:

```cpp
TEST_F(UserAgentUtilsTest, HeadlessUserAgent) {
  command_line->AppendSwitch(kHeadless);
  // In headless mode product name should have the Headless prefix.
  EXPECT_THAT(GetUserAgent(), testing::HasSubstr("HeadlessChrome/"));
```

Inverted, it becomes an in-process regression gate that runs in seconds and needs no
browser — strictly better than a browser-level check alone. The spec never mentions it.

**3. `user_agent_utils.cc:221` is the only producer of the prefix in the tree.** Verified by
grepping `"Headless"` across `components/`, `chrome/`, `content/` and `headless/`: the only
other non-test hit is `chrome/install_static/user_data_dir.cc:131`, a temp-directory name.
The fix is complete at one site rather than being one of several.

**4. `Emulation.setAutomationOverride` is confirmed, not inferred.** The spec marked the
probe→CDP mapping *(unverified)*. It is real:
`third_party/blink/public/devtools_protocol/domains/Emulation.pdl:603` declares
`experimental command setAutomationOverride`, implemented at
`inspector_emulation_agent.cc:1222`, which sets `automation_override_`, which
`ApplyAutomationOverride` reads at `:1271`. That is the whole chain.

**5. `webdriver` is a window-only surface, and it cannot be checked at runtime.** It is
declared on the `NavigatorAutomationInformation` mixin
(`third_party/blink/renderer/core/frame/navigator_automation_information.idl:8`), which no
worker interface includes; `worker_navigator.idl:32` is `Exposed=Worker`, so
`WorkerNavigator` is not even a constructor in the window context. Conventions rule 3 is
therefore satisfied by **absence**, and the IDL is the whole evidence. A first draft of this
plan asserted `'webdriver' in WorkerNavigator.prototype` from the window and would have
shipped a criterion that fails on every build ever made. Found by the Task 1 implementer at
the Step 5 gate.

**6. The `AutomationControlled` feature is force-enabled by the harness itself, and by
`--headless`.** `content/child/runtime_features.cc:377-379` maps `--enable-automation`,
**`--headless`** and `--remote-debugging-pipe` onto it, and lines 428–435 add
`--remote-debugging-port=0` — the comment there says outright that an ephemeral port "is how
ChromeDriver launches the browser by default". `lib_shell.launch()` hardcodes exactly that,
so source 1 is on in every session the harness starts.

Two things follow, and the second is the more important:

- The first draft's criterion 2 could not prove what it claimed. With the feature already
  forced on, `webdriver` is `true` before any override is issued, so a build that closed only
  the feature path would have passed it. Criteria 2a/2b now run on a fixed non-zero port,
  which the same file leaves the feature *unset* for, so the probe is the only thing that can
  flip the value. Also found at the Step 5 gate, by the count being 4 instead of 2.
- **Stock Chrome run with `--headless` reports `navigator.webdriver === true` with no
  automation client attached at all.** The leak is not merely "a driver can flip it"; the
  switch that makes it headless has already flipped it. That is a stronger justification for
  this sub-project than the spec gives, and it means Task 2's criterion 8 is a proof rather
  than the coherence bookkeeping it was written as.

The spec's line number for the insert (218) is now 220; SP1a's own patch added lines above
it. Use the symbol, not the number.

## Global Constraints

Copied from `docs/superpowers/specs/00-conventions.md` and the SP2 spec. Every task's
requirements implicitly include this section.

- **No JavaScript injection into page-visible scopes.** Both changes are inside existing
  native C++ producers; neither creates a binding, a property, or a global.
- **Native-looking accessors.** `Object.getOwnPropertyDescriptor(Navigator.prototype,
  'webdriver').get.toString()` must still contain `[native code]`. Criterion 3.
- **Worker parity.** Satisfied by absence here, and the IDL is the evidence: `webdriver`
  is on the `NavigatorAutomationInformation` mixin, and `worker_navigator.idl:32` is
  `Exposed=Worker` without it. There is no runtime worker criterion — see Task 1 Step 4.
- **Coherence over coverage.** `webdriver === false` and a `Headless`-free UA must hold in
  the *same* session. Criterion 8.
- **Fall back to the real value when config is absent** — with one argued exception, and
  this sub-project is inside it. Both surfaces are suppressed **unconditionally, with no
  config key**, because per spec §3.1 "a Camoucrome that announces headless has failed at
  its one job, so this is not a preference". Do not add a key. Do not read `camoucfg` in
  either changed function.
- **`--headless` must keep working as a headless switch.** Only its advertisement goes.
  The `HasSwitch(kHeadless)` test *inside `GetUserAgentInternal`* goes with the insert it
  guards — it has no other purpose there — but every other reader of the switch, in every
  other file, is untouched, and the switch continues to put the browser in headless mode.
- **Assert the expected count, or the expected failure.** An exit code of 0 is not evidence
  that anything was examined. Every step below that runs a suite states the number.
- **Where a check exists to catch a regression, make it fail once on purpose** — and
  confirm the mutant compiled, and that the restore actually rebuilt. A `mv`-restore gives
  the file the backup's mtime, ninja prints `no work to do`, and the mutant binary survives
  a green-looking rebuild. `touch` after restoring and require real work.
- **`cmd 2>&1 | tail -5` then `echo exit=$?` reports `tail`'s status.** Use
  `cmd > log 2>&1 && echo OK || echo FAILED`. Over ssh to the build machine only `&&`/`||`
  markers and `grep -c` counts survive; PowerShell eats `$?` and `$(...)` before `wsl` runs.
- **The verification scripts need `~/camoucrome-verify/venv/bin/python3`,** not the
  system `python3` — playwright is installed only in that venv, and a bare `python3` dies
  at `import lib_shell` with `ModuleNotFoundError: No module named 'playwright'`. That is a
  loud failure rather than a silent one, but it costs a round trip every time.
- **The ssh ControlMaster socket dies around ~32KB of base64 payload** with
  `mm_send_fd: sendmsg(1): Message too long`. Transfer one file per ssh call rather than
  batching several. Found in Task 1 sending `lib_shell.py` and `verify_sp2.py` together.
- **A green build does not run `gn check` or `checkdeps`.** Neither gate fires on a
  `.cc`-only change. Neither task here adds a cross-component include, so neither needs
  them — but do not add one without running both explicitly.
- **The repository is the source of truth; the checkout is a deployment.** Anything edited
  in the tree must land in `patches/` and be proven to reconstruct. Task 3.

## Deliberately deferred, with the reason

Recording these here so a reviewer does not read them as omissions.

- **The `Object.getOwnPropertyNames(window)` diff (spec verification item 4).** It requires
  a *stock* binary of the same revision, which is a second full build, and neither change in
  this plan can add a global — both are value substitutions inside existing native
  producers, provable by reading. The check belongs with SP2b's isolated-world work, which
  is the first thing in this sub-project that could actually make it fire. Capturing a
  baseline from an already-patched build now would bake in any leak it was meant to catch.
- **Everything in the SP2b list above.**

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `third_party/blink/renderer/core/frame/navigator.cc` | Modify (`Navigator::webdriver`, ~line 100) | Return `false` before either source is consulted |
| `components/embedder_support/user_agent_utils.cc` | Modify (`GetUserAgentInternal`, ~line 218–222) | Stop inserting the `Headless` prefix |
| `components/embedder_support/user_agent_utils_unittest.cc` | Modify (`HeadlessUserAgent`, ~line 1040) | Invert the upstream assertion into a regression gate |
| `scripts/lib_shell.py` | Modify (`evaluate`, `session`) | Optional CDP commands before evaluation |
| `scripts/verify_sp2.py` | Create | The eight browser-level criteria |
| `patches/sp2a-automation-hiding.patch` | Create | The three tree edits, as a diff |
| `scripts/apply.sh` | Modify (`PATCHES` array) | Apply the new patch after `sp5a` |
| `docs/superpowers/specs/00-conventions.md` | Modify (sub-project map) | Record the SP2a/SP2b split |

---

### Task 1: `navigator.webdriver` returns false through both of its sources

**Files:**
- Modify: `third_party/blink/renderer/core/frame/navigator.cc:100-107` (in the checkout)
- Modify: `scripts/lib_shell.py:185-219` (in the repository)
- Create: `scripts/verify_sp2.py` (in the repository)

**Interfaces:**
- Consumes: `lib_shell.launch/session/shutdown/SHELL/SHELL_FLAGS/CHROME/CHROME_FLAGS` as
  they exist today.
- Produces: `lib_shell.session(..., cdp=[(method, params), ...])`, used by Task 2;
  `scripts/verify_sp2.py` printing `PASS`/`FAIL` lines and exiting non-zero on any FAIL.

**Background the brief cannot carry.** The getter has two independent sources and the
widely-cited `--disable-blink-features=AutomationControlled` switch closes only the first.
Current body, verified in the tree:

```cpp
bool Navigator::webdriver() const {
  if (RuntimeEnabledFeatures::AutomationControlledEnabled())
    return true;

  bool automation_enabled = false;
  probe::ApplyAutomationOverride(GetExecutionContext(), automation_enabled);
  return automation_enabled;
}
```

- [ ] **Step 1: Add optional CDP commands to `lib_shell`**

Two functions in `scripts/lib_shell.py`. Criterion 2 has to issue a CDP command to the
browser under test before reading a value from it, and nothing in the harness can do that
today. Send the commands **after** navigation and immediately before evaluation, so no
question arises about a navigation resetting agent state.

In `evaluate`, add the parameter and the block:

```python
def evaluate(proc, expressions, navigate_to=None, cdp=None):
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(
            f"http://127.0.0.1:{proc.cdp_port}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        if navigate_to is not None:
            # wait_until="load" so the subresource request the header
            # assertions read has certainly been issued.
            page.goto(navigate_to, wait_until="load")
        # Sent after navigation and before evaluation: these set inspector
        # agent state that the very next expression reads, and ordering them
        # here removes any question of a navigation clearing it.
        if cdp:
            cdp_session = context.new_cdp_session(page)
            for method, params in cdp:
                cdp_session.send(method, params)
        return [page.evaluate(e) for e in expressions]
```

In `launch`, add `debug_port=None`. When given it replaces the hardcoded
`--remote-debugging-port=0` and is used directly, skipping the `DevToolsActivePort`
read-back. Criteria 2a and 2b need this: `runtime_features.cc` reads the literal `0` as
ChromeDriver's launch pattern and force-enables the very feature they are trying to hold
off (see Step 4).

```python
def launch(config, shell=None, extra_flags=None, strict=False, debug_port=None):
    ...
    port_arg = f"--remote-debugging-port={debug_port if debug_port else 0}"
```

and, after `Popen`, when `debug_port` is given, poll `http://127.0.0.1:{debug_port}/json/version`
on the same 30-second deadline and the same three distinguishable failures instead of
waiting for the port file. Keep the existing path untouched when `debug_port` is `None` —
every other verification script depends on it.

In `session`, add both parameters to the signature and pass them through:

```python
def session(config, expressions, navigate_to=None, shell=None, extra_flags=None,
            strict=False, cdp=None, debug_port=None):
```

```python
        proc = launch(config, shell=shell, extra_flags=extra_flags, strict=strict,
                      debug_port=debug_port)
        return evaluate(proc, expressions, navigate_to, cdp=cdp), None
```

- [ ] **Step 2: Confirm the existing harness self-test still passes**

Run: `cd scripts && python3 test_lib_shell_launch.py`
Expected: `7 PASS`, exit 0. It freezes the default argv as a literal; a signature change
that altered the launch line would show up here. It needs no browser and no checkout.

- [ ] **Step 3: Commit the harness change**

```bash
git add scripts/lib_shell.py
git commit -m "lib_shell: allow CDP commands before evaluation

SP2a criterion 2 must set Emulation.setAutomationOverride on the browser
under test and then read navigator.webdriver from the same session. Sent
after navigation, immediately before evaluation."
```

- [ ] **Step 4: Write `scripts/verify_sp2.py` with the four window-side criteria**

Model the structure on `scripts/verify_sp1a.py`: collect into a dict, print one line per
criterion, exit non-zero on any FAIL, and let an exception become FAIL lines rather than a
traceback that discards results already gathered.

**The isolation problem this criteria set exists to solve.** `content/child/runtime_features.cc`
force-enables the `AutomationControlled` runtime feature under four separate conditions —
`--enable-automation`, `--headless`, `--remote-debugging-pipe` (lines 377–379), and
`--remote-debugging-port=0`, the ephemeral-port heuristic at lines 428–435 whose own comment
says it exists because "this is how ChromeDriver launches the browser by default". The
harness hardcodes `--remote-debugging-port=0`, so **source 1 is already on in every session
`lib_shell.launch()` starts.**

That is why criterion 2 must use a *fixed non-zero* port. With the ephemeral port, the
feature is on, `webdriver` is already `true` before any override is issued, and a build that
closed only the feature path would pass an override-based criterion for a reason having
nothing to do with the probe. The same file says a specific port "is more likely for
attaching a debugger, so we should leave EnableAutomationControlled unset" — which is
exactly the configuration in which the probe is the only thing that can flip the value.

| # | Criterion | Launch | On stock `content_shell` |
|---|---|---|---|
| 1 | `navigator.webdriver === false` | harness default (port 0) | **true.** Proves source 1 is closed. |
| 2a | `navigator.webdriver === false` | fixed non-zero port, no override | **also false.** The guard that makes 2b's isolation real — without it, 2b cannot claim the probe was what it closed. |
| 2b | still `false` after `Emulation.setAutomationOverride {enabled:true}` | fixed non-zero port | **true.** Proves source 2 is closed — the one the popular switch misses. |
| 3 | descriptor getter `.toString()` contains `[native code]` | harness default | also passes. Guards rule 2. |

Criterion 2a passing on a stock build is not a defect in it; it is what it is for, and the
file must say so. Without 2a the suite reads as three proofs when it holds two, and 2b's
stated claim would be unfalsifiable.

```python
WEBDRIVER = "navigator.webdriver"
DESCRIPTOR = ("Object.getOwnPropertyDescriptor("
              "Navigator.prototype, 'webdriver').get.toString()")
```

Criteria 2a and 2b need `lib_shell.launch()` to accept a port. Add an optional
`debug_port=None` parameter alongside the `cdp` work in Step 1: when given, it replaces
`--remote-debugging-port=0`, and the port is used directly instead of being read back from
`DevToolsActivePort`. Pick the port by binding an ephemeral socket and closing it, rather
than hardcoding a number — a fixed port lets a run connect to a previous instance that is
still shutting down, which looks identical to the browser under test misbehaving:

```python
def free_port():
    """A port the kernel just handed out, so no two runs collide.

    Not the same as --remote-debugging-port=0: that makes CHROMIUM pick, and
    runtime_features.cc reads the literal 0 as ChromeDriver's launch pattern
    and force-enables AutomationControlled. Criteria 2a/2b need the feature
    OFF so the probe is the only thing that can set webdriver.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
```

```python
port = free_port()
values, err = lib_shell.session(None, [WEBDRIVER], debug_port=port)          # 2a
values, err = lib_shell.session(
    None, [WEBDRIVER], debug_port=free_port(),
    cdp=[("Emulation.setAutomationOverride", {"enabled": True})])             # 2b
```

Add an assertion beside them that the isolation actually held, so a future change to the
harness cannot turn 2a/2b vacuous:

```python
# 2a's PASS is only meaningful if the feature really is off in this
# configuration. If runtime_features.cc ever force-enables on a non-zero
# port too, 2a stays green and 2b silently stops isolating the probe.
# The stock-build run recorded in Step 5 is what establishes this; re-check
# it after any Chromium roll.
```

**There is no worker criterion, and that is deliberate.** `webdriver` is declared on the
`NavigatorAutomationInformation` mixin, and `worker_navigator.idl:32` is `Exposed=Worker`
with no such mixin — so `WorkerNavigator` is not a window global and the surface does not
exist in workers at all. An earlier draft of this plan asserted
`'webdriver' in WorkerNavigator.prototype` from the window, which can never pass on any
build: `typeof WorkerNavigator === 'undefined'` there. Spawning a real worker to confirm a
property the IDL never declares would be testing Blink's bindings generator, not this
change. Conventions rule 3 is satisfied by the IDL, and the IDL is the evidence.

- [ ] **Step 5: Run it against the UNPATCHED tree and record which criteria are red**

Run on the build machine:
```bash
cd ~/chromium/src && ~/camoucrome-verify/venv/bin/python3 ~/camoucrome-verify/verify_sp2.py > ~/sp2-before.log 2>&1 \
  && echo ALL_PASS || echo SOME_FAIL
grep -c '^FAIL' ~/sp2-before.log
grep '^FAIL' ~/sp2-before.log
```
Expected: `SOME_FAIL`, and **exactly 2** FAIL lines — criteria **1 and 2b**. Any other count
means a criterion measures something other than what the table above claims; stop and find
out which before writing the fix. In particular a FAIL on 2a means the feature is on despite
the non-zero port, and 2b's isolation claim is void — that is the specific thing this step
exists to catch. This is the plan's own predict-then-name-every-failure check, and it is
cheaper now than after the fix makes everything green.

- [ ] **Step 6: Make the change**

In the checkout, replace the body of `Navigator::webdriver()`:

```cpp
bool Navigator::webdriver() const {
  // Camoucrome: unconditionally false, and deliberately before BOTH sources.
  //
  // Two independent things set this true upstream. RuntimeEnabledFeatures::
  // AutomationControlledEnabled() is what --disable-blink-features=
  // AutomationControlled turns off, which is why that switch is only half a
  // fix. The second is probe::ApplyAutomationOverride, the instrumentation
  // behind CDP's Emulation.setAutomationOverride
  // (Emulation.pdl:603 -> inspector_emulation_agent.cc:1222), which any
  // client that speaks the protocol can issue at any time.
  //
  // Dropping the probe call is a deliberate exception to the project rule
  // "never delete a probe call", and the argument is narrow enough to state.
  // That rule exists because a probe usually drives a legitimate DevTools
  // emulation feature that a fingerprint override should win over but not
  // break -- hardwareConcurrency is the precedent. Here the probe's ONLY
  // consumer is the value being discarded: automation_override_ is read at
  // exactly one place, inspector_emulation_agent.cc:1271, inside
  // ApplyAutomationOverride itself. So nothing else observes it, the agent
  // still records the state and still answers Success, and the sole effect
  // removed is a driver's ability to re-announce itself -- which is the
  // requirement, not a casualty of it.
  return false;
}
```

**Do not touch the include block.** This is a behaviour change inside one function, and
leaving the includes alone keeps the whole change to one contiguous hunk — which is what a
fork that rebases onto upstream wants in the churniest region of the file.

Two specific reasons, beyond diff hygiene. `core/probe/core_probes.h` is still needed by
the Step 8 mutation, which restores the upstream body and will not compile without it; the
plan's own falsifiability check depends on that include surviving. And
`runtime_enabled_features.h` is not in this file's include block at all —
`RuntimeEnabledFeatures::` resolved transitively — so there is nothing to remove for it.

Add one line to the comment block you just wrote, so the retained include is not deleted
by a later tidy-up:

```cpp
  // core_probes.h stays in the include block though nothing below calls
  // probe:: any more. The plan's mutation check restores the upstream body,
  // which does, and an unexplained unused include is exactly what a future
  // cleanup removes.
```

An earlier draft of this step instead said to `grep -c` for `probe::` and
`RuntimeEnabledFeatures::` and drop an include whose count came back 0. **That check could
not fail**: the comment this same step mandates contains the literal `probe::ApplyAutomationOverride`,
so the count is at least 1 by construction and the "drop it" branch is unreachable. It
produced the right answer here by accident. See the conventions entry Task 3 adds.

- [ ] **Step 7: Build and re-run**

```bash
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default content_shell > ~/b1.log 2>&1 \
  && echo BUILD_OK || { echo BUILD_FAILED; grep -E "error:" ~/b1.log | head -5; }
```
Expected: `BUILD_OK`. `navigator.cc` is a Blink core `.cc`, so this is a one-to-three-minute
incremental build, not a header cascade.

```bash
~/camoucrome-verify/venv/bin/python3 ~/camoucrome-verify/verify_sp2.py > ~/sp2-after.log 2>&1 && echo ALL_PASS || echo SOME_FAIL
grep -c '^PASS' ~/sp2-after.log
```
Expected: `ALL_PASS` and `4`.

- [ ] **Step 8: Mutation — make criteria 1 and 2b fail on purpose**

Restore the original body, rebuild, and confirm the two criteria that are supposed to prove
the fix actually go red. Both halves matter, and they cover different sources: a mutation
that only flips criterion 2b would leave the feature path unproven, and one that only flips
criterion 1 would leave the probe path unproven.

```bash
cd ~/chromium/src
cp third_party/blink/renderer/core/frame/navigator.cc /home/lang/nav.bak
python3 - <<'PY'
p = "third_party/blink/renderer/core/frame/navigator.cc"
s = open(p).read()
new = "  return false;\n}"
old = """  if (RuntimeEnabledFeatures::AutomationControlledEnabled())
    return true;

  bool automation_enabled = false;
  probe::ApplyAutomationOverride(GetExecutionContext(), automation_enabled);
  return automation_enabled;
}"""
assert new in s, "patched body not found -- nothing to mutate"
open(p, "w").write(s.replace(new, old, 1))
print("mutant written")
PY
~/depot_tools/autoninja -C out/Default content_shell > ~/mut.log 2>&1 \
  && echo MUTANT_BUILD_OK || { echo MUTANT_BUILD_FAILED; grep -E "error:" ~/mut.log | head -5; }
grep -c "no work to do" ~/mut.log
```
Expected: `MUTANT_BUILD_OK` and `0`. A mutant that did not compile leaves the previous
binary in place and every subsequent result is meaningless; a `no work to do` means the
same thing by a different route.

```bash
~/camoucrome-verify/venv/bin/python3 ~/camoucrome-verify/verify_sp2.py > ~/sp2-mut.log 2>&1 && echo UNEXPECTED_ALL_PASS || echo FAILED_AS_PREDICTED
grep '^FAIL' ~/sp2-mut.log
```
Expected: `FAILED_AS_PREDICTED`, and the FAIL lines are **exactly criteria 1 and 2b** —
the same two that were red in Step 5. Name the cause of any third failure before
continuing. A FAIL on 2a here would mean the mutation changed something other than what it
was meant to.

- [ ] **Step 9: Restore, rebuild, confirm the restore took effect**

```bash
cd ~/chromium/src
cp /home/lang/nav.bak third_party/blink/renderer/core/frame/navigator.cc
touch third_party/blink/renderer/core/frame/navigator.cc
~/depot_tools/autoninja -C out/Default content_shell > ~/res.log 2>&1 \
  && echo RESTORE_BUILD_OK || echo RESTORE_BUILD_FAILED
grep -c "no work to do" ~/res.log
~/camoucrome-verify/venv/bin/python3 ~/camoucrome-verify/verify_sp2.py > /dev/null 2>&1 && echo ALL_PASS || echo SOME_FAIL
```
Expected: `RESTORE_BUILD_OK`, `0`, `ALL_PASS`. The `touch` is not defensive: `cp` from a
backup can give the restored file an mtime ninja reads as not-newer than the object built
from the mutant, and then the restore is a silent no-op with a correct-looking source tree
on disk.

- [ ] **Step 10: Commit**

Commit the verification script in the repository and the source edit in the checkout
separately — they are two repositories.

```bash
git add scripts/verify_sp2.py
git commit -m "sp2a: verify navigator.webdriver is false through both of its sources

Five criteria; two of them (1b and 2) fail on a stock build and are the
ones that prove anything. Criterion 1 is a regression guard and says so.
Criterion 4 asserts webdriver is ABSENT from WorkerNavigator rather than
asserting a value: it lives on the NavigatorAutomationInformation mixin,
which no worker interface includes."
```

---

### Task 2: suppress the `HeadlessChrome` product token, on all three channels

**Files:**
- Modify: `components/embedder_support/user_agent_utils.cc:218-222` (in the checkout)
- Modify: `components/embedder_support/user_agent_utils_unittest.cc:1040-1048` (in the checkout)
- Modify: `scripts/verify_sp2.py` (in the repository)

**Interfaces:**
- Consumes: `lib_shell.CHROME`, `lib_shell.CHROME_FLAGS` (which already carries
  `--headless`), `lib_shell.ACCEPT_CH`, `echo_server.start(accept_ch)` returning
  `(base_url, headers_for, stop)` — the same shape `verify_sp1a_chrome.py` uses.
- Produces: `verify_sp2.py` at eight criteria total (Task 1 contributes 1, 2a, 2b, 3;
  this task adds 5, 6, 7, 8 — the numbers are labels, not indices, and 4 is deliberately
  unused: it was the worker criterion Task 1 removed).

**Background the brief cannot carry.** This runs against `chrome`, not `content_shell`, and
the reason is not preference: `ShellContentBrowserClient::GetUserAgent()` builds its own
product string and never calls `GetUserAgentInternal()`, so `content_shell` has no
`HeadlessChrome` under any switch and a green run there would prove nothing. `chrome` is
already built at `out/Default/chrome`. Its incremental rebuild is much slower than
`content_shell`'s; budget for it rather than being surprised.

The site, verified in the tree:

```cpp
std::string GetUserAgentInternal() {
  std::string product = GetProductAndVersion();
  if (base::CommandLine::ForCurrentProcess()->HasSwitch(kHeadless)) {
    product.insert(0, "Headless");
  }
```

- [ ] **Step 1: Invert the upstream unit test**

`components/embedder_support/user_agent_utils_unittest.cc`, in `HeadlessUserAgent`. This is
the fast gate and it exists already; do not write a new one beside it.

```cpp
  // Camoucrome: inverted. Upstream asserted HasSubstr("HeadlessChrome/") here,
  // because upstream wants headless mode advertised. This fork suppresses the
  // prefix unconditionally (user_agent_utils.cc, GetUserAgentInternal), so the
  // upstream assertion is exactly the regression this test now guards against.
  // The switch itself is untouched and still means headless -- only the
  // advertisement is gone, which is why the AppendSwitch above stays.
  EXPECT_THAT(GetUserAgent(), testing::Not(testing::HasSubstr("Headless")));
```

Assert on `"Headless"`, not `"HeadlessChrome/"`: the narrower string would pass on a build
that emitted `Headless/154.0.0.0` or `HeadlessChromium/`, and the requirement is that the
word does not appear.

- [ ] **Step 2: Run the test and watch it fail**

```bash
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default components_unittests > ~/b2.log 2>&1 \
  && echo BUILD_OK || { echo BUILD_FAILED; grep -E "error:" ~/b2.log | head -5; }
out/Default/components_unittests --gtest_filter='UserAgentUtilsTest.HeadlessUserAgent' \
  > ~/t2.log 2>&1 && echo UNEXPECTED_PASS || echo FAILED_AS_PREDICTED
grep -c '\[  PASSED  \] 1 test\.' ~/t2.log
```
Expected: `BUILD_OK`, `FAILED_AS_PREDICTED`, `0`. A zero-match `--gtest_filter` exits 0
printing `SUCCESS: all tests passed`, so the literal `[  PASSED  ] 1 test.` line is what
distinguishes "ran and passed" from "selected nothing" — which is why it is grepped here
rather than the exit status being trusted.

- [ ] **Step 3: Make the change**

```cpp
std::string GetUserAgentInternal() {
  std::string product = GetProductAndVersion();
  // Camoucrome: upstream inserts "Headless" here under --headless. Removed
  // unconditionally, with no config key -- a fork that can be configured to
  // announce itself as automated has failed at its one job.
  //
  // The HasSwitch(kHeadless) test is deliberately gone rather than kept with
  // its body emptied: nothing else in this function reads it. --headless
  // itself is untouched everywhere else and still means headless; only the
  // advertisement goes.
  //
  // This is also the fix for a live cross-channel incoherence in stock
  // Chrome, which is the more useful half. Channel 1 (this string) says
  // Headless while channels 2 and 3 -- navigator.userAgentData.brands and
  // Sec-CH-UA -- report Chromium with no Headless anywhere. A detector
  // comparing the three separates headless Chrome from real Chrome without
  // either value having to be implausible alone. Hence criteria 6 and 7:
  // suppressing the prefix in one channel would leave the disagreement.
```

**Do not touch the include block**, for the same reason as Task 1 Step 6: this is a
behaviour change inside one function, and `components/embedder_support/switches.h` supplies
other switch names this file uses regardless.

An earlier draft of this step said to run
`grep -c "kHeadless" components/embedder_support/user_agent_utils.cc` and expect `0`. That
expectation was **unreachable** — the comment this same step mandates contains
`HasSwitch(kHeadless)`, so the count is at least 1 by construction, and an implementer
following the step literally would have hard-stopped on a count it could never produce.
Task 1 shipped the same defect in a milder form, where it happened to yield the right
answer. If you want to know whether executable code still references a symbol, exclude
comment lines explicitly; do not grep a file a previous step just wrote prose into.

- [ ] **Step 4: Run the test and watch it pass**

```bash
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default components_unittests > ~/b3.log 2>&1 \
  && echo BUILD_OK || { echo BUILD_FAILED; grep -E "error:" ~/b3.log | head -5; }
out/Default/components_unittests --gtest_filter='UserAgentUtilsTest.HeadlessUserAgent' \
  > ~/t3.log 2>&1 && echo PASSED || echo FAILED
grep -c '\[  PASSED  \] 1 test\.' ~/t3.log
```
Expected: `BUILD_OK`, `PASSED`, `1`.

- [ ] **Step 5: Confirm the whole `UserAgentUtils` family still passes**

```bash
out/Default/components_unittests --gtest_filter='UserAgentUtils*' > ~/t4.log 2>&1 \
  && echo PASSED || echo FAILED
grep -E '\[  PASSED  \]|\[  FAILED  \]' ~/t4.log
```
Expected: `FAILED`, with the failures being `UserAgentUtilsCamoucfgTest` cases only.
**This is the known false red conventions records:** that suite needs one process per
configuration, so running it alongside its siblings reports three failures that are the
SP1a tests working as designed. Confirm the failing names are all `UserAgentUtilsCamoucfgTest.*`
and that every `UserAgentUtilsTest.*` case passed; a failure outside that suite is real.

- [ ] **Step 6: Add criteria 5–8 to `scripts/verify_sp2.py`**

All four run in **one** `chrome` session with the echo server up, for the same reason
`verify_sp1a_chrome.py` gives: criterion 8 compares two channels, and reading them from two
runs compares two browsers.

| # | Criterion | On stock `chrome --headless` |
|---|---|---|
| 5 | `navigator.userAgent` contains no `Headless` | **fails** — `HeadlessChrome/154.0.0.0`. The proof. |
| 6 | no brand in `navigator.userAgentData.brands` contains `Headless` | also passes. Guards the one-channel fix. |
| 7 | the `Sec-CH-UA` request header contains no `Headless` | also passes. Same. |
| 8 | in this same session, `navigator.webdriver === false` **and** criterion 5 holds | **fails on both halves.** `--headless` is itself one of the switches `runtime_features.cc:378` maps onto `AutomationControlled`, so stock Chrome run headless answers `webdriver: true` with nothing attached. The §5 coherence tie, and a proof rather than bookkeeping. |

Criteria 6 and 7 pass on a stock build, and that is exactly why the spec demands them:
"Asserting it only on the UA string would pass on a build that suppressed the prefix in one
channel." Write that sentence into the file next to them, with the note that they are
guards rather than proofs — the same honesty criterion 1 gets.

```python
values, wire, err = run_chrome(
    None, ["navigator.userAgent",
           "JSON.stringify(navigator.userAgentData.brands)",
           "navigator.webdriver"])
```

where `run_chrome` follows `verify_sp1a_chrome.py:216`:

```python
def run_chrome(config, expressions):
    """One `chrome` session with the echo server up; returns (values, headers, err).

    chrome, not content_shell: ShellContentBrowserClient::GetUserAgent builds
    its own product string and never calls GetUserAgentInternal, so the shell
    has no HeadlessChrome under any switch and would pass this vacuously.

    CHROME_FLAGS already carries --headless, which is the whole precondition
    for the prefix; asserting its absence without it would measure nothing.
    """
    try:
        base_url, headers_for, stop = echo_server.start(lib_shell.ACCEPT_CH)
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, None, exc
    try:
        values, err = lib_shell.session(
            config, expressions, navigate_to=base_url,
            shell=lib_shell.CHROME, extra_flags=lib_shell.CHROME_FLAGS)
        if err is not None:
            return None, None, err
        wire = headers_for("/probe.js")
    finally:
        stop()
    if wire is None:
        return None, None, RuntimeError("the subresource request was never observed")
    return values, {k.lower(): v for k, v in wire.items()}, None
```

Add an assertion that `--headless` is actually in the flags used, so a future edit to
`CHROME_FLAGS` cannot silently turn criteria 5–8 into vacuous passes:

```python
# Not defensive. Every criterion below asserts the ABSENCE of a token that
# only appears under --headless, so dropping the switch would turn all four
# green while measuring nothing -- the project's dominant failure mode,
# arriving through a file this script does not own.
#
# `raise`, not `assert`: python3 -O strips assert statements, and a guard that
# vanishes under a flag is that same failure mode wearing a guard's clothes.
# Task 1's SHELL_FLAGS mirror uses this shape; keep the two identical.
if "--headless" not in lib_shell.CHROME_FLAGS:
    raise RuntimeError(
        "CHROME_FLAGS no longer carries --headless; criteria 5-8 would be vacuous")
```

- [ ] **Step 7: Build `chrome` and run the full suite**

```bash
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default chrome content_shell > ~/b4.log 2>&1 \
  && echo BUILD_OK || { echo BUILD_FAILED; grep -E "error:" ~/b4.log | head -5; }
~/camoucrome-verify/venv/bin/python3 ~/camoucrome-verify/verify_sp2.py > ~/sp2-full.log 2>&1 && echo ALL_PASS || echo SOME_FAIL
grep -c '^PASS' ~/sp2-full.log
```
Expected: `BUILD_OK`, `ALL_PASS`, `8`.

- [ ] **Step 8: Mutation — restore the insert and confirm criteria 5 and 8 go red**

```bash
cd ~/chromium/src
cp components/embedder_support/user_agent_utils.cc /home/lang/uau.bak
python3 - <<'PY'
p = "components/embedder_support/user_agent_utils.cc"
s = open(p).read()
anchor = "  std::string product = GetProductAndVersion();\n"
assert anchor in s
mut = anchor + """  if (base::CommandLine::ForCurrentProcess()->HasSwitch(kHeadless)) {
    product.insert(0, "Headless");
  }
"""
open(p, "w").write(s.replace(anchor, mut, 1))
print("mutant written")
PY
~/depot_tools/autoninja -C out/Default chrome > ~/mut2.log 2>&1 \
  && echo MUTANT_BUILD_OK || { echo MUTANT_BUILD_FAILED; grep -E "error:" ~/mut2.log | head -5; }
grep -c "no work to do" ~/mut2.log
~/camoucrome-verify/venv/bin/python3 ~/camoucrome-verify/verify_sp2.py > ~/sp2-mut2.log 2>&1 && echo UNEXPECTED_ALL_PASS || echo FAILED_AS_PREDICTED
grep '^FAIL' ~/sp2-mut2.log
```
Expected: `MUTANT_BUILD_OK`, `0`, `FAILED_AS_PREDICTED`, and the FAIL lines are **exactly
criteria 5 and 8**. Criteria 6 and 7 stay green under this mutant — which is the direct
demonstration that the UA-string-only assertion the spec warns about would have been
insufficient, and worth recording in the task report rather than merely observed.

If the mutant needs `#include "components/embedder_support/switches.h"` restored to
compile, restore it in the mutant only; a mutant that does not build leaves the previous
binary in place and reports a pass.

- [ ] **Step 9: Restore, rebuild, confirm**

```bash
cd ~/chromium/src
cp /home/lang/uau.bak components/embedder_support/user_agent_utils.cc
touch components/embedder_support/user_agent_utils.cc
~/depot_tools/autoninja -C out/Default chrome > ~/res2.log 2>&1 \
  && echo RESTORE_BUILD_OK || echo RESTORE_BUILD_FAILED
grep -c "no work to do" ~/res2.log
~/camoucrome-verify/venv/bin/python3 ~/camoucrome-verify/verify_sp2.py > /dev/null 2>&1 && echo ALL_PASS || echo SOME_FAIL
```
Expected: `RESTORE_BUILD_OK`, `0`, `ALL_PASS`. This is the step whose omission on
2026-08-27 produced an hour of diagnostics against a mutant binary and a retracted bug
report in four config keys.

- [ ] **Step 10: Commit**

```bash
git add scripts/verify_sp2.py
git commit -m "sp2a: assert the product token carries no Headless on all three channels

Criterion 5 is the proof; 6 and 7 pass on a stock build and exist to catch
a fix applied in one channel only, which the mutation in step 8 demonstrates
directly -- restoring the insert reddens 5 and 8 and leaves 6 and 7 green.
Criterion 8 is SP2's section 5 coherence tie: a false webdriver beside a
headless UA is louder than either alone, so both are asserted in one session.

Runs against chrome, not content_shell: ShellContentBrowserClient builds its
own product string and never reaches GetUserAgentInternal."
```

---

### Task 3: extract the patch, wire it into `apply.sh`, prove reconstruction

**Files:**
- Create: `patches/sp2a-automation-hiding.patch`
- Modify: `scripts/apply.sh` (the `PATCHES` array)
- Modify: `docs/superpowers/specs/00-conventions.md` (sub-project map)

**Interfaces:**
- Consumes: the three tree edits from Tasks 1 and 2.
- Produces: a patch that applies cleanly onto a tree with `sp0`, `sp1a` and `sp5a` already
  applied, and reconstructs byte-identically.

**Background the brief cannot carry.** `apply.sh` lists patches explicitly rather than
globbing, and its comment already names this patch as the reason:

> A glob sorts lexicographically, which matches this order today only by luck: `"sp2-*"`
> will sort between `"sp1a-*"` and `"sp5a-*"`, but SP2 is extracted from a tree that
> already has SP5a applied.

So `sp2a-automation-hiding.patch` goes **last** in the array, after `sp5a`. Getting this
backwards produces a patch that fails on a base that does not match, which is the failure
the explicit list exists to prevent.

`user_agent_utils.cc` is edited by both `sp1a-ua-producer.patch` and this one. The sp2a
diff must be generated from a tree with sp1a already applied, which it is.

`check_checkout_sync.sh` covers `additions/` and `settings/` only. SP2a adds no file to
either, so it stays green and is not evidence about this task; run it anyway to confirm
nothing drifted while the tree was being edited.

- [ ] **Step 1: Extract the diff**

On the build machine, from a tree in the post-SP5a state plus the Task 1 and 2 edits:

```bash
cd ~/chromium/src
git diff -- third_party/blink/renderer/core/frame/navigator.cc \
             components/embedder_support/user_agent_utils.cc \
             components/embedder_support/user_agent_utils_unittest.cc \
  > /home/lang/sp2a.patch
grep -c '^diff --git' /home/lang/sp2a.patch
```
Expected: `3`. Anything else means a file is missing or an unrelated one was swept in.

Note the pathspec is passed as separate arguments. In `zsh` an unquoted `$PATHS` variable
is **not** word-split, so `git diff -- $PATHS` sends one giant pathspec and produces an
empty diff that looks structurally valid. If a variable is used, run it under `bash -c`.

- [ ] **Step 2: Bring it to the repository and confirm it is byte-identical**

Transfer by base64 and compare `sha256` on both sides. Never `scp` to the build machine:
it lands on the Windows filesystem while the WSL shell reads its own `/tmp`, the copy
prints `cannot stat`, and the shell continues — which is how an 11-PASS run once proved
nothing about the edit it was testing.

```bash
shasum -a 256 patches/sp2a-automation-hiding.patch
```
Expected: identical to `sha256sum /home/lang/sp2a.patch` on the far side.

- [ ] **Step 3: Add it to `apply.sh`**

```bash
PATCHES=(
  "$ROOT/patches/sp0-config-layer.patch"
  "$ROOT/patches/sp1a-ua-producer.patch"
  "$ROOT/patches/sp5a-coherence-validator.patch"
  "$ROOT/patches/sp2a-automation-hiding.patch"
)
```

The existing comment above the array already explains why the order is semantic rather
than alphabetical and already names SP2 as the case that breaks a glob. Do not restate it;
the array now demonstrates it.

- [ ] **Step 4: Prove reconstruction from the pinned base**

```bash
cd ~/chromium/src
git stash list | head -1
git checkout -- third_party/blink/renderer/core/frame/navigator.cc \
                components/embedder_support/user_agent_utils.cc \
                components/embedder_support/user_agent_utils_unittest.cc
git apply --3way /home/lang/sp2a.patch && echo APPLY_OK || echo APPLY_FAILED
git diff --cached --stat
```
Expected: `APPLY_OK`, and the stat naming exactly the three files. Use
`git diff --cached --stat`, not `git diff --stat`: `--3way` stages its result, so the
unstaged diff reads empty immediately afterwards and looks like the patch did nothing.

If the apply conflicts, `git checkout -- .` will **not** clear the unmerged index;
`git reset --hard` will.

- [ ] **Step 5: Rebuild and re-run everything from the reconstructed tree**

```bash
cd ~/chromium/src
~/depot_tools/autoninja -C out/Default chrome content_shell components_unittests > ~/b5.log 2>&1 \
  && echo BUILD_OK || { echo BUILD_FAILED; grep -E "error:" ~/b5.log | head -5; }
out/Default/components_unittests --gtest_filter='Camoucfg*:ParseConfig*:CoherenceValidator*:Derive*:UserAgentUtilsTest.*' \
  > ~/t5.log 2>&1 && echo UNIT_OK || echo UNIT_FAILED
grep -E '\[  PASSED  \]' ~/t5.log
```
Then the four browser-level suites, each with its expected count:

| Suite | Expected |
|---|---|
| `verify_sp0.py` | 11 PASS, exit 0 |
| `verify_sp1a.py` | 9 PASS, exit 0 |
| `verify_sp5a.py` | 4 PASS, exit 0 |
| `verify_sp1a_chrome.py` | 34 PASS, exit 0 |
| `verify_sp2.py` | 8 PASS, exit 0 |
| `run_coherence_tests.sh` | 6/6 |

Run each as `script > log 2>&1 && echo OK || echo FAILED` and count `^PASS` lines. A count
that is lower than the table and still exits 0 is the thing this table exists to catch.

- [ ] **Step 6: Confirm repo and checkout have not drifted**

```bash
scripts/check_checkout_sync.sh
```
Expected: `PASS all 17 copied files are identical in repo and checkout`. SP2a adds none, so
17 is the number that should still appear; 18 would mean a file was added to `additions/`
that this plan does not call for.

- [ ] **Step 7: Record the SP2a/SP2b split in conventions**

In `docs/superpowers/specs/00-conventions.md`, the sub-project map row for SP2 becomes two
rows, and the settled-order line becomes `SP5a → SP2a → SP2b → SP3 → SP1b → SP4`. Add one
paragraph beside the existing SP1/SP5/SP6 split rationale saying that SP2 split on the line
where its spec stops deciding and starts asking — four of its six open decisions require a
measurement, and a plan for an unknown outcome is a plan of placeholders.

Add to the "dominant failure mode" table the row this plan earned before running anything:

| The check | What it actually measured |
|---|---|
| a `grep -c` for a symbol, run after a step that mandates writing a comment naming that symbol | **the text the step just wrote.** Task 1 Step 6 asked whether `probe::` was still used and decided an include's fate on the count; the mandated comment contains `probe::ApplyAutomationOverride`, so the count was 1 by construction and the "drop it" branch was unreachable. Task 2 Step 3 had the same shape and expected `0`, which its own mandated comment made impossible. The rule read as "is this symbol still used?" and measured "does this string appear in the file?" — the same substitution as the runner that counted its own `report()` calls. **When one step writes prose into a file and a later step greps it, the grep sees what the step just wrote.** |
| verifying the `HeadlessChrome` fix against `content_shell` | nothing. `ShellContentBrowserClient::GetUserAgent()` builds its own product string and never calls `GetUserAgentInternal()`, so the shell has no `HeadlessChrome` under any switch. Conventions already recorded this trap for `GetUserAgentMetadata` and explicitly cleared `GetUserAgent` as the safe sibling — the clearance was about which *function* it calls, and the headless prefix lives one level below that, inside a caller the shell also skips. |

- [ ] **Step 8: Commit**

```bash
git add patches/sp2a-automation-hiding.patch scripts/apply.sh \
        docs/superpowers/specs/00-conventions.md
git commit -m "sp2a: extract the patch, apply it last, record the SP2 split

Applied after sp5a, not in alphabetical position: the diff is generated from
a tree that already has sp5a, which is the case apply.sh's comment already
names as the reason the list is explicit rather than globbed.

Conventions gains the SP2a/SP2b rows and one more entry in the failure-mode
table: content_shell cannot verify the headless prefix at all, on the same
sibling method conventions previously cleared as safe."
```

---

## Self-review

**Spec coverage.** Of SP2's twelve verification items, this plan implements 1, 2 and 3,
plus §3.1's three-channel requirement and §5's first coherence row. Item 8 (worker parity)
is discharged by the IDL rather than by a runtime check, for the reason in fact 5 — the
surface does not exist in workers, so there is nothing to run. Items 4, 5, 6, 7, 9, 10, 11
and 12 are listed under *Deliberately deferred* or belong to SP2b, each with the reason.
Nothing in the spec is silently dropped.

**Placeholders.** None. Every step has its command, its expected output, and — where a step
runs a suite — the expected count.

**Type consistency.** `lib_shell.session(..., cdp=..., debug_port=...)` is defined in
Task 1 Step 1 and consumed in Task 1 Step 4; `run_chrome` in Task 2 Step 6 mirrors `verify_sp1a_chrome.py:216`
including its three-value return. `echo_server.start` returns `(base_url, headers_for, stop)`
as the existing callers use it.

**One thing worth a reviewer's attention.** Task 1 Step 6 deletes a `probe::` call, which
conventions forbids in general terms. The exception is argued in the comment the step writes
and rests on one checkable fact — `automation_override_` is read at exactly one place,
`inspector_emulation_agent.cc:1271`. If that grep ever returns a second reader, the argument
fails and the change needs revisiting. A reviewer should re-run it rather than take the
comment's word for it.
