# Shared conventions for all Camoucrome specs

Every SP spec in this directory assumes the decisions below. Do not re-litigate them
inside an individual spec; reference this file instead.

## Project

Camoucrome is an anti-detect fork of Chromium. It is the Chromium counterpart to
Camoufox (`lang315/camoufox`, a Firefox fork). The defining constraint, carried over
from Camoufox, is that **spoofing is implemented in C++ at the Blink/browser level,
never by injecting JavaScript into the page**. A page must not be able to observe
that any value was substituted.

Camoufox is the reference design, not a codebase to copy. Firefox and Chromium share
no code. What ports is the *architecture*: a C++ config layer that patched call sites
consult.

## Decided architecture

**Config component.** `//components/camoucfg/` — one GN target usable from the
browser, renderer, and GPU processes. Blink reaches it through **per-header** entries
in `third_party/blink/renderer/DEPS`, one line per header a Blink file actually
includes — `"+components/camoucfg/mask_config.h",` and
`"+components/camoucfg/blink_scope.h",` — not a directory-wide
`"+components/camoucfg",` grant.

Per-header is what that file already does for other components, and it keeps the grant
to least privilege: a later SP that includes a third camoucfg header has to add a line
and, in doing so, has to think about whether Blink should see it. `gn check` is enabled
for blink core, so a missing entry is a hard build failure rather than a warning.

*Corrected 2026-08-27 — the sentence above is true only under a precondition it does not
state, and the gap is dangerous enough to spell out.*

**Neither dependency gate fires on a `.cc`-only change.** `gn check` runs during
`gn gen`, and `autoninja` regenerates the build graph only when a `BUILD.gn` or `.gni`
file changes. `checkdeps.py` is never run by the build at all. So adding a disallowed
`#include` to a `.cc` file and building produces a clean, green build from both gates —
Chromium's include paths are src-root-relative, so the compile succeeds regardless of what
the GN graph permits.

Demonstrated on this checkout during SP1a Task 3: two disallowed includes added to
`components/embedder_support/user_agent_utils.cc`, then
`autoninja -C out/Default content_shell` exited **0**. Run explicitly,
`gn check out/Default "//components/embedder_support:user_agent"` exited **1** and named
both includes, and `checkdeps.py` also failed. The gates work; the build simply does not
consult them.

The obvious objection — that the build exited 0 because it did nothing — was ruled out.
That build ran four real steps (CXX, AR, SOLINK, LINK), and the `.o` is fourteen seconds
newer than the `.cc`.

The stronger half was then measured rather than argued. The object compiled under the
unwired state is **never recompiled afterwards**:

```
2026-08-27 07:41:25  components/embedder_support/user_agent_utils.cc
2026-08-27 07:41:39  out/Default/obj/.../user_agent/user_agent_utils.o
```

The `.o` still carried that timestamp long after the `BUILD.gn` and `DEPS` entries were
added and the tree rebuilt. Adding the dependency changed the link, not the compile
command, so ninja saw no reason to redo it. The artifact produced while the include was
disallowed is the one sitting in the binary.

So the window in which a bad include is visible at all is exactly one `gn gen`, and only if
something independently forces one. Miss it and nothing downstream ever looks again.

This does not contradict SP0, it explains it. SP0's `gn check` failure was real because its
include arrived alongside a `BUILD.gn` edit, which forced the regeneration. The rule above
was generalised from that single observation and the generalisation was wrong.

**So run both gates explicitly whenever a change adds a cross-component include**, and do
not treat a green build as evidence:

```bash
~/depot_tools/gn check out/Default "//the/target:name"
python3 buildtools/checkdeps/checkdeps.py --root="$(pwd)" path/to/dir
```

## The dominant failure mode of this project

Not a check that fails. **A check that reports success while measuring almost nothing.**

Nine were found on 2026-08-27 alone, during SP1a Tasks 1–8. Seven reported success while
measuring almost nothing, the eighth reported failure while measuring the wrong thing, and
the ninth could not have been measured by anything.

| The check | What it actually measured |
|---|---|
| `scp` a script across, then run the verification | the *previous* script — `scp` had landed on the Windows filesystem while the WSL shell read its own `/tmp`, the `cp` printed `cannot stat`, and the shell continued. 11 PASS, proving nothing about the edit. |
| `--gtest_filter='Camoucfg*'` as a regression gate | 2 tests of 21, and printed `PASSED`. Only `CamoucfgKeysTest` carries that prefix; SP0's five suites do not. |
| `autoninja` after adding a disallowed `#include` | nothing — neither gate runs on a `.cc`-only change, as above. |
| `cmd 2>&1 \| tail -5` then `echo "exit=$?"` | `tail`'s exit status. A failed build prints `exit=0`. This was every build command in the SP1a plan. |
| `$?` or `$(...)` sent to the build machine over ssh | **PowerShell's**, not bash's. The login shell on that box is PowerShell 5.1, and it expands both before `wsl` ever runs: `$?` is a PowerShell *boolean*, so `echo EXIT_IS_$?` prints `EXIT_IS_True` after a failing command, and `$(git branch --show-current)` runs on the Windows side in `C:\`, printing `fatal: not a git repository` and an empty value. Hit four times on 2026-08-27, each time producing a confident-looking status line that reported nothing. **Only `&&`/`||` markers and `grep -c` counts survive the trip.** |
| a mutation test whose mutant did not compile | nothing. The build failed, the **previous** binary stayed in place, the test ran against it and printed `OK`. Found while mutation-testing a gate change: reverting it left a helper unused, `-Wunused-function` failed the build, and the "mutation survived" result was meaningless. |
| `bash -lc '...; echo EXIT=$?'` | not the inner command's status. Nesting a command string inside `-lc` loses it the same way a pipe does. Found by Task 6 in its own tooling, during the mutant run. |
| a regression filter that also matched the new suite | a false **red**: `--gtest_filter='UserAgentUtils*'` swept in `UserAgentUtilsCamoucfgTest`, which needs one process per configuration, so it reported three failures that were the new tests working as designed. |
| an equality check against a baseline captured with a different probe | nothing it could ever pass. `capture_ua_baseline.py` requested seven high-entropy hints and a draft of the verification requested five; `getHighEntropyValues` returns the requested hints plus three low-entropy ones, so ten keys were compared against eight. Caught by reading the baseline, not by running. |
| a runner's own count guard | **the number of times a function is called in the file it lives in.** `run_coherence_tests.sh` computed `TOTAL=$((PASS_COUNT+FAIL_COUNT))` and errored unless it was 6; both counters were incremented only inside `report()`, called exactly six times as literals, so `TOTAL` was unconditionally 6. It compared the count of `report` calls against the `6` two lines below. Meanwhile each `--gtest_filter` was a *separate* literal from the name passed to `report`, output was `>/dev/null`, and a zero-match filter **exits 0 printing `SUCCESS: all tests passed`** — measured. So a mistyped filter printed `PASS`. The script's own comment said it existed to stop "a runner that silently ran fewer than six cases and still exited 0". |
| a hardcoded `provenance` block on a captured artifact | **nothing at all, by construction — no code reads it.** `capture_ua_baseline.py` asserted `"binary": "content_shell"` and a `known_absent` list claiming no `sec-ch-ua-*` header arrives. Task 8 reuses that script against `chrome`, which sends them, so the block would have described the file as the opposite of its own contents. Nothing would have failed; the file would simply have been cited. Found on 2026-08-27 by reading Task 8's steps against the script, before its build finished. |
| N synthetic input events forwarded synchronously in one C++ call | **~2 of them, clustered, with near-identical timestamps.** SP2b Task 3: humanizing a mouse move by `ForwardMouseEvent`-ing 24 interior points back-to-back delivered only ~2 to the page — the input router coalesces queued mousemoves the renderer has not consumed, and with zero wall-clock time between sends even the survivors carry indistinguishable `timeStamp`s. A manufactured `WebInputEvent::TimeStamp()` per point does nothing; what a page reads is real delivery time. A page-visible multi-event sequence requires delayed tasks spaced by real wall-clock delay, with the CDP command deferred to the path's end. Applies to any future multi-event input synthesis. |
| | a mutation, cited as evidence for criteria its mutant could not reach | **which function was edited, not which criteria are sound.** SP2a Task 2 restored the `Headless` insert in `GetUserAgentInternal()`, criteria 5, 8 and 9 reddened, 6 and 7 stayed green — and that was written up as proof the three-channel requirement earns its place. Backwards: `brands` and `Sec-CH-UA` come from `GetUserAgentMetadata()`, so the mutant could not redden 6 and 7 whatever their quality, and criterion 5 *is* the UA-string-only assertion the write-up claimed would have been insufficient. Criterion 8 conjoins a UA-string term with a `navigator.webdriver` term the same mutant never touches, so it reddened only through the half it shares with criterion 5 — **a conjunction reddened by a mutant that reaches only one conjunct proves only that conjunct.** **A mutation falsifies only the criteria whose producer it edits.** Green under a mutant that cannot reach you is not a result. |
| absence-asserting criteria that treat a missing surface as a PASS | **nothing, silently, in exactly the criteria that never move.** `"Headless" not in wire.get("sec-ch-ua", "")` passes when the header is absent; `not any("Headless" in b for b in brands)` passes on an empty list. Both were written as the three-channel guarantee and both would have survived a roll that stopped sending the header. The inverse idiom is safe by accident: an *equality* comparison against a non-empty expected value fails when the surface disappears, which is why the same `.get(h, "")` shape is correct three files over and wrong here. **Assert presence before asserting absence.** |
| a `grep -c` for a symbol, run after a step that mandates writing a comment naming that symbol | **the text the step just wrote.** SP2a Task 1 Step 6 asked whether `probe::` was still used and decided an include's fate on the count; the mandated comment contains `probe::ApplyAutomationOverride`, so the count was 1 by construction and the "drop it" branch was unreachable. Task 2 Step 3 had the same shape and expected `0`, which its own mandated comment made impossible. The rule read as "is this symbol still used?" and measured "does this string appear in the file?" — the same substitution as the runner that counted its own `report()` calls. **When one step writes prose into a file and a later step greps it, the grep sees what the step just wrote.** |
| verifying the `HeadlessChrome` fix against `content_shell` | nothing. `ShellContentBrowserClient::GetUserAgent()` builds its own product string and never calls `GetUserAgentInternal()`, so the shell has no `HeadlessChrome` under any switch. This table already recorded the trap for `GetUserAgentMetadata` and explicitly cleared `GetUserAgent` as the safe sibling — the clearance was about which *function* it calls, and the headless prefix lives one level below that, inside a caller the shell also skips. |
| a `git commit -m` body containing backticks | **whatever text zsh leaves after running the backticked span as a command substitution first.** A commit message stating a rule "raises X, not asserts Y" lost both backtick-quoted words silently — no error, no non-zero exit, a committed message reading "is now , not ." Same family as the `$?`/`$(...)` row above: the login shell interprets the string before the intended program ever sees it. **Write commit prose with `git commit -F <file>` whenever it contains backticks**, not `-m`. |

**A ninth, and the worst kind: a claim no check could ever reach.** Provenance blocks,
comments and plan prose are read by people and by nothing else, so they never fail — they
are cited. The fix that landed is the shape to copy: **derive the claim from what was
observed, and refuse rather than default when the input is unrecognised.** `known_absent`
is now computed from the headers that actually arrived, and an unknown binary is rejected
with a message saying to go read the source, because a default there would be an assertion
about code nobody read. The same day, a comment justifying `--headless=new` as avoiding "a
deprecated alias" turned out to describe no property of this tree; `IsHeadlessMode()` never
reads the switch's value. Both were confident, both were unfalsifiable by any test, and one
grep settled each.

Most were written by the same person who then had to find them. **Not one was caught by
anything failing.** Every one was caught by someone reading output and noticing it was
*smaller than it should have been*, or reading a document against the tree and noticing the
two disagreed — two tests where twenty-one were expected, a build that finished too fast, a
green run on a tree that should not compile, a comparison whose two sides could never have
matched.

Three of the eight were found by reading a task brief against the actual code **before
running anything**. That has been the cheapest place this project finds defects, by a wide
margin: no build, no browser, no waiting.

So: **assert the expected count, or the expected failure.** An exit code of 0 is not
evidence that anything was examined, and "it ran green" carries almost no information here
until you know what it measured.

**The cheapest detector found so far: read the fix's own comment against the fix.**

SP5a's whole-branch review took three rounds, and every round found the same shape — a fix
correct in substance with one hole left where the mechanism was more specific than the
guard around it. All four of those residual holes were found the same way, and not by
running anything:

| The comment said | The code guarded |
|---|---|
| "always repairs `keys[1]` to …" | only `keys[0]` |
| "a duplicate entry masking a missing one" | counts, which duplicates leave equal |
| "a runner that silently ran fewer than six cases and still exited 0" | the number of `report` calls in its own file |
| "an absent key is already covered by the fall-back rule" | a rule the same change had just disproved |

The comment was accurate every time. It described the whole mechanism, the code implemented
part of it, and the gap between them was visible at reading speed — no build, no browser, no
mutation. **A precise comment beside an imprecise guard is a defect report someone already
wrote for you.** That makes writing the mechanism out in full doubly worth it: it is how the
next reader finds what you missed.

Three habits follow, each earned by one of the eight:

- Where a check exists to catch a regression, **make it fail once on purpose** and confirm
  it says so — and **confirm the mutant compiled**, because a mutation that does not build
  leaves the old binary in place and reports a pass.
- **A restored file can be OLDER than the mutant object it replaces, and then the rebuild
  is a no-op.** `mv`-ing a `.bak` back gives the restored source the BACKUP's mtime, which
  ninja can read as not-newer than the `.o` built from the mutant. It prints
  `no work to do`, the mutant binary stays, and every subsequent run measures it — with a
  correct-looking source tree on disk to reassure you. Found on 2026-08-27 by an agent
  mutation-testing its own fix, on the first restore it attempted. **`touch` the file after
  restoring, and require the rebuild to report real work rather than `no work to do`.**
  This is the sharper form of the rule below: there, the restore never rebuilt; here it
  rebuilt and still changed nothing.

- **`git clean -fd` in the Chromium checkout is a footgun, and `apply.sh` hands you the
  reason to reach for it.** `scripts/apply.sh` copies `additions/` into the tree as
  UNTRACKED files, and untracked files block a branch switch — so the obvious remedy is
  `git clean -fd`. Run at the checkout root that deletes the 247 gclient-managed
  directories `.gclient_entries` lists, including `third_party/llvm-build`, which is the
  toolchain. Recovery is a full `gclient sync`. **Always scope it to a path**
  (`git clean -fd components/camoucfg/`), and confirm the toolchain is still there before
  trusting the next build. Verified on 2026-08-27 after SP5a's reconstruction: 248 entries,
  `third_party/llvm-build` and `buildtools/linux64` present.

- **Restoring the source is not restoring the binary.** A mutation script must rebuild
  *after* it restores, and re-run the baseline to prove the restore took effect. On
  2026-08-27 a script ended `cp uau.bak … ; echo "restored"` with no rebuild, so
  `out/Default/chrome` stayed the mutant. The next hour of diagnostics — five failing
  assertions, a per-key probe, a no-CDP run — all measured that mutant, and were written up
  as a product bug in four config keys. There was no bug. The mutant was doing exactly what
  it was built to do.

  The tell was available twice and read past twice. An in-process gtest showed the same
  four substitutions working, which got filed as an in-process-versus-browser contradiction
  rather than as a reason to suspect the *binary*. Then instrumenting the producer forced a
  rebuild and printed the correct values — credited to the instrumentation, when the
  rebuild was the variable. **When a fresh build disagrees with an earlier run, suspect the
  earlier binary before inventing a mechanism that explains both.**
- **Predict what should fail, then name the cause of every failure you observe.** A count
  that matches the prediction is weak evidence; an unexplained extra failure means the
  check reaches something nobody has accounted for.
- **Read the brief against the tree before running it.** Three of the eight were stale
  expected counts, drifted duplicate constants, and an incomplete commit list — all visible
  by reading, none of which would have announced themselves in a green run.

**Config transport.** Environment variables `CAMOU_CONFIG_1`, `CAMOU_CONFIG_2`, …
concatenated in order, falling back to a single `CAMOU_CONFIG`. Chunking exists
because Windows caps a single environment variable near 32KB. This is deliberately
byte-compatible with Camoufox's transport so that Camoufox's Python fingerprint
generator can eventually drive both forks.

**Config format.** A flat JSON object whose keys are dotted or colon-separated
strings (`"navigator.userAgent"`, `"webGl:parameters"`). Parsed once per process into
a **`base::DictValue`** held by a `base::NoDestructor`, via
`base::JSONReader::ReadDict(raw, base::JSON_PARSE_RFC)`. No third-party JSON library
is vendored.

Three API details that cost SP0 a build cycle each, recorded so no later SP repeats
them. `base::Value::Dict` does **not** exist in this Chromium revision — the type is
`base::DictValue`, and `components/` contains 4520 uses of the latter and none of the
former. `JSONReader::Read` and `ReadDict` take a **required** `int options` argument
with no default. And `base::NoDestructor` static_asserts against a trivially
destructible `T`, so it suits the dictionary but not an empty tag type like
`ConfigScope`, which uses a plain function-local static instead.

**API shape.** Every getter takes a `ConfigScope` as its first argument:

```cpp
camoucfg::GetUint32(ScopeFor(execution_context), "navigator.hardwareConcurrency")
```

In SP0 every scope resolves to the same process-global config. The scope parameter
exists so that a later per-context backing store can be introduced by changing
`ScopeFor` alone, without touching a single call site. Never write a getter that
omits the scope.

**Failure behavior.** Missing config is normal and silent — every surface falls back
to its real value. Malformed JSON logs an error once per process; if
`CAMOU_CONFIG_STRICT=1` is set it aborts startup instead. A type mismatch logs a
warning naming the key and returns `nullopt`. Bad config must never crash a renderer:
a crash is itself a fingerprint.

**The browser-process parse is load-bearing, not diagnostic.** The configuration is
parsed lazily on first access, and the first surface to touch it lives in a *renderer*.
That means strict mode, left to itself, would fire its `CHECK` in a renderer — turning
"refuse to start" into a renderer crash, which is precisely what the rule above
forbids. SP0 avoids this by forcing the parse in the browser process during
`BrowserMainLoop::EarlyInitialization`, so a malformed configuration under strict mode
refuses startup before any renderer exists.

That call currently sits next to a `VLOG` and reads like a diagnostic. It is not. Do
not delete it while tidying, and do not fold the `HasKey` call back inside the `VLOG`
— `VLOG` expands through `LAZY_STREAM`, so an expression inside it is never evaluated
at default verbosity and the parse would silently stop happening.

**Open weakness, for SP6a or SP7 to resolve:** making strict mode depend on the side
effect of a line whose stated purpose is logging is fragile. A future sub-project
should give startup validation its own explicit call rather than leaving it as an
operand.

## Non-negotiable rules for every SP

1. **No JavaScript injection into page-visible scopes.** If a surface can only be
   reached from JS, say so explicitly and treat it as an open problem rather than
   quietly injecting.
2. **Native-looking accessors.** After any change,
   `Object.getOwnPropertyDescriptor(...).get.toString()` must still report
   `[native code]`, and `Object.keys(window)` must be unchanged against a stock build.
3. **Worker parity.** Any surface exposed to both a window and a worker must report
   identical values in both. Camoufox needed `cross-process-storage.patch` for exactly
   this class of bug; a worker disagreeing with its window is a tell.

   Today this holds for free: the config arrives by environment variable and child
   processes inherit the environment, so every context in the process parses the same
   bytes. **That guarantee expires the moment a per-context override channel lands.**
   Whichever SP introduces that channel owns re-establishing worker parity explicitly,
   and must say so in its spec.
4. **Coherence over coverage.** A spoofed value that contradicts another spoofed value
   is worse than not spoofing at all. Where a surface must agree with another, name the
   surface and the invariant.
5. **Fall back to the real value** whenever config is absent, never to a hardcoded
   placeholder.

   One scoped exception is allowed, and only where a spec argues it explicitly: a
   surface may fail *closed* — refusing to answer rather than answering honestly — when
   a partially spoofed profile would be more detectable than a blocked one. Camoufox's
   `blockIfNotDefined` mode for WebGL parameters is the precedent: a GL profile with
   some values spoofed and the rest real is a stronger signal than a context that
   declines to report. Do not generalise this to surfaces where a real value is merely
   inconvenient.

## The config layer does not reach every process

`ScopeFor()` resolves a `blink::ExecutionContext`, so it is available anywhere Blink
runs, and `//components/camoucfg` itself is reachable from the browser and GPU
processes. It is **not** available in services that run outside all three — the device
service, which owns geolocation, is the known case. A surface living there needs its
own path to the config and cannot assume the Blink-shaped API. Say so in the spec
rather than discovering it during implementation.

## Repository layout

```
additions/     whole new files, copied into the Chromium tree verbatim
patches/       diffs against files that already exist in Chromium
settings/      the spoofable-key registry
scripts/       apply / extract / build helpers
docs/superpowers/specs/   these documents
```

This mirrors Camoufox's split, which has held up across ~64 patches: new files are
copied, edits to existing files are diffs. The Chromium checkout is a git repository,
so `git format-patch` produces `patches/` content directly.

## Build environment

Chromium builds on the user's Windows PC inside WSL2 (Ubuntu 24.04), as the non-root
user `lang`, at `~/chromium/src`. depot_tools refuses to run as root. Build config is
`out/Default` with `is_component_build=true` and `symbol_level=0`, so an incremental
rebuild after touching one Blink source file is one to three minutes. The primary
build target for verification is `content_shell`, not `chrome` — it is far smaller and
still exposes the DevTools protocol.

**`/tmp` on the build machine does not survive between ssh invocations.** The WSL2 VM is
torn down when the last client disconnects and `/tmp` is a tmpfs, so a script written to
`/tmp` in one `ssh` call is gone by the next. Write throwaway scripts on the *client* and
pipe them in on stdin; anything that must persist goes under `~`. Found in SP1a Task 7,
which lost a file between two calls it had every reason to expect would still be there.

**Two git behaviours that mislead during patch work,** both found the same way:
`git apply --3way` stages its result, so `git diff --stat` immediately afterwards reads
empty and looks like the patch did nothing — use `git diff --cached --stat`. And
`git checkout -- .` will not clear an unmerged index left by a conflicted apply;
`git reset --hard` will.

**The ssh `ControlMaster` socket fails around ~32KB of base64 payload,** with
`mm_send_fd: sendmsg(1): Message too long`. Transfer one file per `ssh` call rather
than batching several through one multiplexed session. Found transferring
`lib_shell.py` and `verify_sp2.py` together.

**Bare `python3` on the build machine has no `playwright`.** The verify scripts need
`~/camoucrome-verify/venv/bin/python3`; the system `python3` fails loudly
(`ModuleNotFoundError` at `import lib_shell`) rather than silently, but SP2a's own
plan still wrote the bare interpreter in seven places before this was caught.

**A job on that machine lives only while a `wsl.exe` client is attached.** The WSL2 VM
itself is torn down seconds after the last one disconnects — confirmed by `uptime`
reading `up 0 min` immediately after a build vanished. So `nohup`, `setsid ... &
disown` and Windows-side `Start-Process` do not fail because they were used wrongly;
they cannot work. Run long jobs in the foreground of an ssh session held open from the
client side (`ControlMaster` plus `ControlPersist` carried a four-hour build through a
laptop sleep), or issue chunked `timeout -k 15 540 autoninja ...` calls. A client-side
task exiting 255 does not mean the remote job died; check `pgrep -c "siso|ninja"` first,
and never start a second build in the same output directory.

**`content_shell` is not a complete browser, and the gap is load-bearing.** Anything
implemented under `//chrome` is absent from it. `window.chrome` is the known case: every
installer lives in `chrome/renderer/` and `content/shell/BUILD.gn` links none of them, so
`content_shell` has no `window.chrome` at all. A surface in that position needs a `chrome`
build to verify, which is a much slower loop. Check which target owns a surface before
planning its verification, and say so in the spec rather than discovering it mid-task.

*Amended 2026-08-27, and the amendment is the point:* the gap is not only about missing
features. **`content_shell` sometimes reimplements a surface rather than omitting it**, and
that shape is far more dangerous, because the surface is present, plausible, and wrong.

The case that cost SP1a a task: `ShellContentBrowserClient::GetUserAgentMetadata()`
(`content/shell/browser/shell_content_browser_client.cc:750`) returns
`GetShellUserAgentMetadata()` at `:348`, which assembles a `blink::UserAgentMetadata` from
scratch — hardcoding `platform = "Unknown"` and a `content_shell` brand. It never calls
`embedder_support::GetUserAgentMetadata()`. Only
`ChromeContentBrowserClient::GetUserAgentMetadata()` does. So a patch to the
`embedder_support` producer is entirely invisible in `content_shell`, and a verification
run against it would report the unpatched shell values while looking like a working test.

The user-agent *string* does not have this problem — `ShellContentBrowserClient::GetUserAgent()`
at `:732` calls `embedder_support::BuildUnifiedPlatformUserAgentFromProduct` directly. Two
sibling methods on the same class, one delegating to shared code and one not. Nothing
announces which is which.

Two further walls sit behind that one, both worth knowing before anyone tries to verify
client hints in `content_shell`: `ShellBrowserContext::GetClientHintsControllerDelegate()`
returns `nullptr` outside test harnesses, so no `Sec-CH-UA*` request header is emitted at
all; and `--run-web-tests` does wire a mock delegate but perturbs `window` with
web-test-only globals, destroying the very surface a baseline exists to protect.

**So the rule is stronger than "check which target owns a surface."** Before planning a
verification, confirm that the binary under test actually *calls the function being
patched*. Grep for the patched symbol's callers, not for the feature's name. Wiring a
delegate into `content_shell` to make headers appear would have produced headers built
from shell-authored metadata — a test verifying code that never ships.

## Spec format

Each spec uses these sections, in order:

1. **Goal** — one paragraph. What this SP makes possible that was not possible before.
2. **Depends on** — which SPs must land first, and why.
3. **Surfaces** — a table of every value this SP controls, its config key, its Chromium
   source location (file path, verified against a real checkout where possible), and the
   process it lives in.
4. **Design** — how it works. Scale the length to the difficulty.
5. **Coherence constraints** — which other surfaces this one must agree with, and the
   invariant in each case.
6. **Verification** — numbered, each item independently runnable and falsifiable. State
   the command and the expected output, not "it works".
7. **Open decisions** — anything not yet settled, with the options and a recommendation.
   Never invent a decision the user has not made; list it here instead.
8. **Explicitly out of scope** — what a reader might expect here but will find elsewhere.

Write in prose with tables where they genuinely compress. No code blocks longer than
about fifteen lines; describe the change instead of transcribing it.

## Sub-project map

| SP | Scope | Depends on |
|----|-------|-----------|
| SP0 | Config layer + tracer-bullet surface | — |
| SP6a | Patch management and the key registry | SP0 |
| SP5a | Invariant registry, reader, and load-time validator | SP0 |
| SP1a | UA / UA-CH producer: user-agent string, `userAgentData`, `Sec-CH-UA*` | SP0 |
| SP1b | Blink-side navigator scalars, languages, `Accept-Language` | SP1a |
| SP2a | Automation hiding: `navigator.webdriver`, the `HeadlessChrome` product token | SP0 |
| SP2b | Automation hiding: humanized cursor (the rest of SP2 resolved to SP6/SP7 by measurement) | SP0, SP2a |
| SP3 | WebGL and canvas fingerprints | SP0 |
| SP4 | Audio, fonts, screen, media devices, battery, WebRTC | SP1, SP3, SP5a |
| SP5b | Invariant catalogue and fingerprint presets | SP1, SP3, SP4 |
| SP6b | Packaging and driver API | SP1–SP5 |
| SP7 | Phone-home removal and build-level hardening | — |

SP5 and SP6 are each split, because both specs argue in their own dependency sections
that half their content is needed far earlier than the other half. SP6's patch
management is needed immediately after SP0's first commit — a branch in the Chromium
tree is at risk from the next `gclient sync` — and its key registry must exist before
SP1 adds twenty keys as string literals. SP5's registry and validator can land as soon
as SP0 does, and SP5 warns that deferring them is precisely the failure mode Camoufox
exhibits. Deferring either to the end is the mistake this split prevents.

*Amended 2026-08-27:* **SP1 is split too, and its dependencies shrank.** SP1a is the
browser-process producer, SP1b the Blink-side leaves; SP1a carries nearly all the
architectural risk while SP1b repeats the pattern SP0 proved, so verifying the risky half
before building twelve mechanical edits on it is worth one extra boundary.

SP1a depends on **SP0 alone**. The two dependencies the map recorded both dissolved on
inspection rather than being waived. SP6a's key registry reduces to a hand-written header
SP1a writes itself (see "Two registries" above). SP5a's contribution was the claimed-OS
derivation — but SP1 *populates* the inputs that function reads and never consumes its
answer; SP4 and SP7 are the consumers. A prerequisite nothing in the dependent actually
calls is not a prerequisite.

SP5a is still owed before SP4, and SP6a before packaging. Neither now blocks SP1a.

*Amended 2026-08-28:* **SP2 is split too, on a different line than SP1 or SP5/SP6.**
Those splits separated risk from repetition, or an early-needed half from a
late-needed one. SP2 splits where its own spec stops deciding and starts asking:
of the spec's six open decisions (§7, D1–D6), four — D1 (`Runtime.enable`
mitigation), D2 (reimplementing what patchright already covers), D3 (trusted input,
C++ or driver-side) and D6 (the empirical limits, explicitly "none should be closed
without a measurement") — are each written as depending on a measurement the spec
does not yet have, on real Chrome, before there is anything to plan. SP2a is the part
already decided: `navigator.webdriver` and the `HeadlessChrome` product token, both
unconditional fixes with no open question behind them. SP2b is everything still
gated on running an experiment first. A plan for an outcome nobody has measured yet
is a plan of placeholders, so the placeholders are deferred rather than written.

SP2 and SP3 are independent of each other and of SP1. SP7 is GN arguments and build
configuration, so it depends on nothing and can start at any time.

**Order settled 2026-08-27: SP5a (finish) → SP2a → SP2b → SP3 → SP1b → SP4.**

*SP2 complete, 2026-08-30.* SP2a shipped the two binary automation leaks
(`navigator.webdriver`, the `HeadlessChrome` token). SP2b is the humanized
cursor — because measurement collapsed everything else in SP2's spec to
no-C++-here. Four measurements (`docs/superpowers/measurements/`, and
`D1-resolution.md`) resolved the open decisions: D1 (`Runtime.enable`) and the
console-getter leak need no V8 patch — the stack-timing signal is caused by
`Runtime.enable` specifically and closed by a driver that does not enable it,
a **SP6 driver constraint** not a fork patch; D3 (trusted input) is already
`isTrusted` with no `WebMouseEvent` field to patch; isolated worlds (4.2) are
driver-side. `window.chrome` (4.7) is deferred to post-SP7 (branding-gated).
So SP2's large surface reduced to one C++ deliverable, and the expensive V8
inspector patch the spec warned against was measured out rather than written.

SP2 comes before SP3 for a reason worth stating, because it inverts the obvious priority.
As things stand the browser is **identifiable as automated regardless of how good the
identity spoofing is** — a perfect Windows user agent on a browser reporting
`navigator.webdriver: true` is worth nothing. Detectors check automation markers first and
cheaply; one line ends the conversation. Device identity only starts to matter once that
check is survived.

SP5a finishes first only because it is nearly done, and unverified code left in place rots
faster than it would cost to finish. Note also that its *machinery* is worth having early
while its *value* arrives late: with ten keys there is little to enforce, and the registry
becomes useful as SP2, SP3 and SP4 add surfaces — which is exactly why the spec insists it
exist before those, so each lands its invariants rather than being audited afterwards.

## Config key naming

A key uses a **dot** when it mirrors a JavaScript property path exactly
(`navigator.userAgent`, `screen.width`, `window.outerHeight`) and a **colon** when it
names a synthetic namespace with no direct JS counterpart (`webGl:renderer`,
`canvas:seed`, `locale:region`). Camoufox follows this rule in practice without ever
stating it; stating it matters here because SP6a generates C++ constants from the key
registry, which makes a later rename a breaking change.

A value that is *derived* from another gets no key at all. If `screen.orientation` is
always computable from the spoofed dimensions, an independent override key creates the
opportunity for incoherence rather than removing it.

## Ownership decisions

These resolve gaps found while cross-checking the spec set, and override any
contradicting statement left in an individual spec.

**Claimed-OS derivation belongs to SP5a.** The single function answering "what OS are
we claiming" lives in `additions/camoucfg/derive.{h,cc}`, alongside the other derived
values. SP1 populates the inputs it derives from; SP4 and SP7 consume it. No spec
re-derives the OS from a user-agent string locally.

**`window.chrome` belongs to SP2.** Its `runtime`, `loadTimes` and `csi` members are a
page-observable discriminator, and the historically important failure — headless Chrome
lacking the object entirely — is an automation tell rather than a branding one. SP7
owns the build-identity discriminators (Widevine, proprietary codecs); SP2 owns this
one, and the two cross-reference.

**Proprietary codecs and Widevine belong to SP7,** not SP6. SP7 did not exist when SP5
assigned them.

**The fork presents as Chrome, not Chromium.** *(SP7 D1, resolved 2026-08-27.)* The
premise of an anti-detect browser is blending into the common case, and the population
that actually reports Chromium in its brand list is overwhelmingly developers and
automation — the exact group a detector wants to flag. Claiming Chromium is nearer to
self-identifying as automation than to a narrower disguise. SP1a already produces
Chrome-shaped user agents, so this confirms a position rather than choosing one.

Three consequences bind other sub-projects:

- **The build must earn the claim.** Anything Chrome can do that this build cannot is a
  contradiction a page can demonstrate, not merely a value that differs. Codecs are the
  live case; see below.
- **Branding leaks into fingerprint surfaces, so check for it.** Found while probing SP1a:
  `GetPlatformForUAMetadata()` in `user_agent_utils.cc` returns `"Chrome OS"` under
  `BUILDFLAG(GOOGLE_CHROME_BRANDING)` and `"Chromium OS"` otherwise — a branding buildflag
  reaching `navigator.userAgentData.platform` and the `Sec-CH-UA-Platform` header. SP1a's
  `ua:platform` key overrides that particular one, but the pattern is what matters: grep
  for `GOOGLE_CHROME_BRANDING` near any surface before assuming it is branding-neutral.
- **`is_chrome_branded = true` is not the mechanism.** It needs internal Google assets
  this project does not have. The build stays unbranded and matches Chrome's *behaviour*
  through targeted arguments — `ffmpeg_branding = "Chrome"` being the first.

**Proprietary codecs are enabled; Widevine is absent and must not be spoofed.**
*(SP7 D2, resolved 2026-08-27.)* `proprietary_codecs = true` and
`ffmpeg_branding = "Chrome"` follow from D1: with the fork claiming Chrome, a build that
cannot decode H.264 is caught by any page willing to request the media rather than merely
ask about it.

Widevine is the same trap at a higher price — `enable_widevine` is a GN argument but the
CDM is a binary distributed separately, so no flag produces a working one. **SP4 must
leave `requestMediaKeySystemAccess` honest.** Spoofing it while the CDM is absent fails
the moment a page opens a key session, which is the contradiction rule 4 forbids. Recorded
as a known gap to measure, not one to paper over.

Distribution licensing is deliberately *not* settled here. Building and running locally is
a narrow question; distributing binaries carries patent-pool obligations that Google's
Chrome licence does not extend to third-party builds. It blocks nothing before SP6 and is
not a call to make from a technical reading.

**Variations are disabled and no seed is shipped.** *(SP7 D3, resolved 2026-08-27.)* Two
actions, one of which is more urgent than its placement suggests.

`--disable-field-trial-config` fixes a defect that exists **today**: an unbranded build
applies `testing/variations/fieldtrial_testing_config.json` and real Chrome does not, so
the build currently sits at a third position matching neither seeded Chrome nor default
Chrome. That is wrong independently of every other decision here.

Disabling the seed fetch also does something the phone-home framing hides. This project
never spoofs the browser version, precisely because feature availability must match the
version claimed — and a browser whose feature set shifts with a fetched seed makes that
invariant **unverifiable**, since there is no fixed answer to "what does this build
support". Disabling variations is what makes the version-honesty rule checkable at all.

A captured seed baked into the fork is rejected: it would make every instance identical to
every other, trading a "defaults" fingerprint for a cohort marker that exists nowhere but
here. A per-instance seed derived from configuration is the right answer and belongs to
SP5b.

## Out of roadmap: TLS and HTTP/2 fingerprinting

JA3, JA4 and HTTP/2 frame-ordering fingerprints are deliberately **not** an SP, and this
is a decision rather than an oversight. Camoucrome is a real Chromium build using
BoringSSL and Chromium's own network stack, so its TLS and HTTP/2 fingerprints are
already those of Chrome — the same reason this was a strength rather than a gap in
Camoufox. The exposure is not the browser but what sits in front of it: a driver, proxy,
or interception layer that re-terminates TLS will substitute its own fingerprint and
undo this for free. Treat it as a deployment constraint to verify, not a surface to
build. Revisit only if measurement shows the built binary's fingerprint diverging from
stock Chrome of the same milestone.

## Cross-cutting findings

Recorded here because each was discovered while writing one spec but constrains
several. Each is stated in full in its owning spec.

**One producer feeds all three UA channels.** `navigator.userAgentData` and the
`Sec-CH-UA*` request headers both derive from a single `blink::UserAgentMetadata`
struct built by `embedder_support::GetUserAgentMetadata()` in the browser process. SP1
therefore patches two producer functions rather than roughly twenty renderer-side leaf
accessors, and workers inherit the result. This is a place Chromium is *easier* than
Firefox, where Camoufox must patch `Navigator`, `WorkerNavigator`, and `nsHttpHandler`
independently.

**`navigator.webdriver` has two independent sources.** The `AutomationControlled`
runtime feature and a `probe::ApplyAutomationOverride` instrumentation hook both feed
the same getter, so the widely cited `--disable-blink-features=AutomationControlled`
switch closes only one of them. Owned by SP2.

**Assume a `probe::Apply*Override` hook already sits on the surface you are about to
spoof, and check before writing.** This is not confined to `webdriver`. SP0's tracer
surface turned out to have one too: `NavigatorBase::hardwareConcurrency()` already
calls `probe::ApplyHardwareConcurrencyOverride`, the instrumentation behind CDP's
`Emulation.setHardwareConcurrencyOverride`. Chromium exposes a large emulation surface
through DevTools, and much of it lands on exactly the accessors a fingerprint spoof
targets.

Two rules follow. **Never delete a probe call** to resolve a conflict — it silently
breaks DevTools emulation, and removing it is the obvious-looking fix when a
duplicate-definition error appears. And **apply configuration last, after the probe**,
so the configured value wins: the fingerprint is the identity the browser is
presenting, and a driver's emulation override must not be able to contradict it. When
no key is set the lookup is a no-op and the stock behaviour, emulation included,
survives untouched.

The same collision is why SP1 and SP2 are coupled through
`Emulation.setUserAgentOverride`. Expect to find more of these; each one is a
precedence decision, and the answer is the same every time.

**SP1 and SP2 are coupled through CDP.** A pre-existing `platform_override` in
`navigator.cc`, driven by CDP's `Emulation.setUserAgentOverride`, flows through the
same channels SP1 patches. Neutralising it is SP2 work that SP1 depends on.

**Do not spoof the browser version.** SP5's analysis: a claimed version that
contradicts actual feature availability is a contradiction no value substitution
repairs, and feature availability cannot practically be made to match an arbitrary
version. Spoof hardware, locale, and rendering dimensions; let the version be the real
one. This scopes SP1 — it spoofs identity, not version.

**Spoofing an answer the build cannot honour is a contradiction.** Stock Chromium ships
without proprietary codecs, so `canPlayType` for H.264 and AAC answers differently than
real Chrome. SP4 spoofs the API answer; SP7 must make the build actually match via
`proprietary_codecs` and `ffmpeg_branding`. Doing only the first leaves a page able to
ask for the media and watch it fail.

**Two registries, two purposes.** `settings/keys.json` (SP6) is the registry of
spoofable keys and their types, from which both the C++ constants and the client's
validation table are generated. `settings/invariants.json` (SP5) is the registry of
cross-surface invariants, consumed by the browser-process validator, the generator's
self-check, and a generated mutation-test suite. They are different files and neither
subsumes the other.

*Amended 2026-08-27:* the **key registry starts as a hand-written C++ header**,
`additions/camoucfg/keys.h`, and becomes `settings/keys.json` plus a generator in SP6a
when a second consumer exists. The reason the registry has to exist before SP1 is that
keys must stop being string literals scattered across call sites; a header of
`constexpr char[]` constants achieves that completely. Generation buys one further
thing — one source feeding both the C++ constants and the client's validation table —
and that is worth building when the client's table exists to be fed, not before. SP1a
introduces the header; the SP6a task that replaces it must keep the constant names
identical so no call site moves.

**OS-dependent values in Chromium are chosen at compile time, not at run time.** The
whole user-agent producer selects its platform strings through `#if BUILDFLAG(IS_WIN)` /
`IS_MAC` / `IS_LINUX` arms, so a Linux build contains no Windows string to switch to.
There is no code path to redirect: claiming another OS means supplying every value for it
from configuration. Assume this shape wherever a surface reports something
platform-specific, and check for it before designing a patch around a runtime switch that
does not exist. It also fixes what a missing key must do — falling back yields the *real*
platform's value, which is what conventions rule 5 requires anyway.

Discovered in SP1's producer probe; stated in full in
[SP1 §4](2026-08-26-sp1-navigator-identity-design.md).
