# SP0 progress ledger

Plan: docs/superpowers/plans/2026-08-26-sp0-config-layer.md
Code lands in ~/chromium/src on the WSL build machine (user `lang`).

Pre-flight review found two defects in the plan itself, both fixed before
Task 1 was dispatched:
- the typed getters read process-global state, so their wrong-type branches
  were untestable. Split into internal getters taking a base::Value::Dict;
  Task 2 now owns them with fixtures, Task 3's public getters forward.
- three steps said "copy the file" with no runnable command. Replaced with
  concrete cat-over-ssh and tar-over-ssh commands.

Second pre-flight pass, run while waiting for the build lock, verified seven
plan assumptions against the real checkout and found one serious defect:

- The gclient checkout is in DETACHED HEAD. Every task commits, and commits
  in detached HEAD belong to no branch -- the next gclient sync discards
  them with nothing in git log to recover from. The plan never created a
  branch. Task 1 now opens with Step 0 creating `camoucrome/sp0`.
- Base revision pinned to 0e8d4a9268118d323f62ca207b40514df39dcaa9 in
  Global Constraints. Task 7 previously derived it as HEAD~5, which breaks
  the moment a review loop adds a fix commit.

Verified and folded into the plan: base/functional/function_ref.h exists;
NavigatorBase inherits ExecutionContextClient at navigator_base.h:47, so
GetExecutionContext() is available; base::Value::Dict::Find takes
std::string_view; components_unittests is declared at components/BUILD.gn:105;
the three BUILD.gn insertion points are lines 206/411/153 respectively.

Task 1: COMPLETE (commits 59d65cb..696ca6b, 6/6 tests, re-review clean:
  Review found one Important item -- the doc comment described the wrong
  fallback trigger and no test discriminated it. Fixed. The review's
  proposed expected value ("") was itself wrong; verified against Camoufox
  MaskConfig.hpp that "ignored" is correct.

Pre-flight for Task 2 found four more plan defects, all compile-blocking:
- base::Value::Dict does not exist in this revision. The type is
  base::DictValue, a standalone class at base/values.h:242. components/
  has 4520 uses of the latter and zero of the former. 33 occurrences
  renamed in the plan.
- base::JSONReader::Read takes a required int options parameter with no
  default. Switched to ReadDict(raw, base::JSON_PARSE_RFC), which also
  rejects non-object JSON in the same call.
- EXPECT_DEATH matching "camoucfg" would fail in configurations where
  CHECK message text is stripped. base/test/gtest_util.h branches on
  CHECK_WILL_STREAM(); EXPECT_CHECK_DEATH_WITH handles both.
- The unit_tests target needs //base/test:test_support for that macro.

Task 1 re-review verdicts: spec compliance PASS, code quality APPROVED,
no new findings. The reviewer retracted its own earlier false claim that
the shipped code returns "" for a present-but-empty chunk; hand-traced
both our implementation and Camoufox MaskConfig.hpp on identical input and
confirmed "ignored" is correct in both. Byte-compatibility verified by
trace, not by structural resemblance.

Task 2: dispatched.
Task 2: COMPLETE pending review (commit ed9065a1, 16/16 tests).
  Implementer reported two cosmetic plan inaccuracies, both fixed:
  clang says "use of undeclared identifier" not "no member named ... in
  namespace" (unqualified calls from inside the namespace), and gtest
  isolates the death test so combined runs print two PASSED lines, not one.

Pre-flight for Task 3 found one compile-blocking defect:
- ConfigScope had a private constructor befriending GlobalScope. But
  base::NoDestructor placement-news T inside its own constructor, so it is
  NoDestructor that needs the friendship, not GlobalScope. Fixed to
  `friend class base::NoDestructor<ConfigScope>;` with the header include;
  components/ carries several precedents for exactly this.
Verified clean and needing no change: base::Environment::GetVar takes
cstring_view and std::string converts to it implicitly (cstring_view.h:94-121),
so Task 3's lambda is fine; the two BUILD.gn insertion anchors are unmoved.

Task 2: COMPLETE pending review (commit ed9065a1, 16/16 tests).
  Implementer reported two cosmetic plan inaccuracies, both fixed:
  clang says "use of undeclared identifier" not "no member named ... in
  namespace" (unqualified calls from inside the namespace), and gtest
  isolates the death test so combined runs print two PASSED lines, not one.

Pre-flight for Task 3 found one compile-blocking defect:
- ConfigScope had a private constructor befriending GlobalScope. But
  base::NoDestructor placement-news T inside its own constructor, so it is
  NoDestructor that needs the friendship, not GlobalScope. Fixed, with the
  header include; components/ carries several precedents.
Verified clean and needing no change: base::Environment::GetVar takes
cstring_view and std::string converts to it implicitly (cstring_view.h:94-121),
so Task 3's lambda is fine; the two BUILD.gn insertion anchors are unmoved.

Pre-flight for Task 4 found the most consequential plan defect so far:
- NavigatorBase ALREADY overrides hardwareConcurrency (navigator_base.h:57,
  .cc:72). The plan said to add the declaration and the method, which is a
  duplicate definition and will not compile.
- Worse, the existing body calls probe::ApplyHardwareConcurrencyOverride --
  the instrumentation behind CDP Emulation.setHardwareConcurrencyOverride.
  The obvious way to resolve a duplicate-definition error is to delete the
  old method, which would have silently broken DevTools emulation.
- Task 4 now modifies the existing method and applies configuration AFTER
  the probe, so configuration wins and the unconfigured path is untouched.
- Generalised into 00-conventions.md: assume a probe::Apply*Override hook
  already sits on any surface being spoofed, never delete one, and always
  apply configuration last. Same collision class as SP2's webdriver finding
  and the SP1/SP2 coupling through Emulation.setUserAgentOverride.

Task 2: COMPLETE (commits ed9065a1..2a9768ca, 18/18 tests).
  Review verdicts: spec compliance PASS, code quality APPROVED, zero
  Critical, zero Important. Two Minor findings, both gaps in the brief's
  test coverage rather than implementation defects, closed immediately
  rather than deferred because the test shape propagates to Tasks 3-7.
  No separate re-review round: approval preceded the fix, and the fix was
  test-only (23 insertions, 0 deletions, verified by git show --stat).
  Independently re-ran the suite: 18/18, both new tests named OK.

Task 3: dispatched.
Task 3: DONE_WITH_CONCERNS pending review (commit bd3b12ed, 19/19 tests).
  The implementer found that my own earlier "fix" was wrong.
  base/no_destructor.h static_asserts !is_trivially_destructible_v<T>.
  ConfigScope is an empty class, so NoDestructor rejects it outright and
  the assert's own text prescribes a function-local static instead.
  The ORIGINAL plan's `friend const ConfigScope& GlobalScope();` was
  correct all along; commit 773e362 changed it to befriend NoDestructor,
  reinforcing the wrong half. The real defect was NoDestructor, not the
  friend declaration. Plan now uses a plain function-local static.
  Lesson: verifying a mechanism (placement new, friendship) is not the
  same as verifying the template accepts the type. Read the constraints,
  not just the construction site.
  Note base::NoDestructor<base::DictValue> in Config() is unaffected --
  DictValue holds a map and is not trivially destructible.

Pre-flight for Task 6, run while waiting on the Task 3 review, validated the
whole verification approach and fixed a weak assertion.

Smoke-tested Playwright connect_over_cdp against the built content_shell:
ATTACH OK, hardwareConcurrency 16, descriptor "[native code]", worker 16,
222 window keys. content_shell is not a full Chrome and attachability was
an open assumption underneath criteria 2 through 6.

Captured the pre-spoof baseline from that same binary -- it IS the stock
one, since no call site is wired until Task 4 -- and committed it to
baselines/content_shell-0e8d4a9268-stock.json. Criterion 4 previously said
to compare against "a stock content_shell built from the same revision",
which read literally means building a second binary for hours.

Also fixed a weak assertion: the script compared the spoofed run against
the unconfigured run of the SAME binary. After Task 4 both runs execute the
modified code, so a property added unconditionally would appear in both and
the comparison would pass regardless. It now diffs against the recorded
baseline, and additionally checks Navigator.prototype (36 properties).

Task 3 review: spec PASS, code quality PASS with one Important finding to
adjudicate. The reviewer independently verified the NoDestructor deviation
(magic-statics thread safety, singleton invariant airtight, no dangle) and
verified all seven forwarders target the correct Task 2 function.

Adjudicated: extend the absent-key test to all seven getters. std::optional's
converting constructor lets GetDouble->GetInt32From, GetInt32->GetUint32From
and GetBool->HasKeyIn all compile; the last silently turns an absent key into
an engaged optional(false), so a caller stops falling back to the real value.
Asserting every getter on an absent key catches that one.

DECLINED for SP0, carried to SP1: a value-level test proving the numeric
getters forward to the right function (GetDouble on a 1.5 must not reach
GetInt32From). It needs CAMOU_CONFIG set before the singleton latches on
first touch, so it is order-sensitive within the gtest process or needs a
subprocess. A fragile test is worse than a recorded gap. SP1 is the first
sub-project with real call sites for those getters and should add value-level
coverage when it wires them.

Also from the review, both from my brief rather than the implementer:
unused #include <utility>, and the GlobalScope comment drifting from the
corrected brief. Both folded into the fix.

Task 3: COMPLETE (commits bd3b12ed..c3782700, 19/19 tests).
  Review verdicts: spec compliance PASS, code quality PASS. The reviewer
  independently verified the NoDestructor deviation rather than deferring to
  my acceptance of it, and verified all seven forwarders against Task 2's
  signatures. One Important finding (absent-key test covered 4 of 7 getters,
  and the 3 skipped are where a miswiring compiles) adjudicated and fixed.
  Independently re-verified: 7 camoucfg:: assertions in the test, no
  <utility> include, 19/19, checkout clean.

ACCEPTED DRIFT, not worth a build cycle: mask_config.h's friend comment
keeps the implementer's original wording rather than the plan's regenerated
wording. Same reasoning, both correct. Flagged by the implementer, which
correctly stayed inside the three-item scope it was given.

Task 4: dispatched. This is the tracer bullet -- the first surface actually
driven through the config layer.
Task 4: DONE pending review (commit a7de8516, build succeeded).
  THE TRACER BULLET WORKS. Smoke-tested the built binary myself:
    with CAMOU_CONFIG={"navigator.hardwareConcurrency":8} -> window 8, worker 8
    without config                                        -> window 16, worker 16
    both: descriptor "[native code]", 222 window keys (baseline is 222)
  Fallback returns the machine's real value, not a constant. Worker parity
  comes free from overriding in NavigatorBase, the common base of Navigator
  and WorkerNavigator -- the architectural bet made when the plan moved off
  NavigatorConcurrentHardware paid off exactly there.
  Caveat: the smoke test compares key COUNT, not the key LIST. Task 6 does
  the full diff against baselines/content_shell-0e8d4a9268-stock.json.
  probe::ApplyHardwareConcurrencyOverride confirmed still present.

  Implementer self-caught a sed mistake before building: an unanchored
  pattern briefly added the dep to a second deps list, source_set("unit_tests"),
  in core/BUILD.gn. Caught via git diff, removed pre-build; the committed
  diff has exactly one. Verified independently: grep -c finds 1.

  It also reported that `nohup ... & disown` gets silently killed over the
  wrapper while `setsid <cmd> </dev/null >log 2>&1 & disown -a` survived.
  RECORDED BUT NOT CONFIRMED: the surviving build was 8 steps in 15.5s, and
  a 15-second job would survive almost anything, so duration rather than the
  pattern may explain it. Do not rely on this for a long build.

Task 4 review: spec PASS, code quality APPROVE, zero Critical, zero
Important. Reviewer independently confirmed the probe survives and runs
first, the DEPS grant is exactly the two includes and no more, blink_scope.h
only forward-declares ExecutionContext so camoucfg gains no Blink dependency,
and the self-caught sed mistake never reached the commit.

Two Minor items, both mine:
- dead #include base/system/sys_info.h in committed code -> fix dispatched.
- 00-conventions.md told later SPs to add a directory-wide DEPS grant while
  the code uses per-header entries. Per-header is the better choice and is
  what shipped; conventions corrected. Reviewing that section surfaced a
  second drift: the config-format paragraph still named base::Value::Dict
  and implied NoDestructor is universal. Both corrected, and the three
  API facts that each cost SP0 a build cycle are now recorded there.

Pre-flight for Task 6 found an ordering defect: its verification reads the
baseline from ~/camoucrome/..., but the repository does not reach the build
machine until Task 7. Task 6 Step 1 now pushes the baseline to
~/camoucrome-verify/baselines/ and verifies it arrived intact. Pushed and
confirmed on the machine: 222 window keys, 36 navigator props, hc 16.

Task 4: COMPLETE (commits a7de8516..031d2b04, tracer bullet verified working).
  Review: spec PASS, code quality APPROVE, zero Critical, zero Important.
  Both Minor items closed.
  Independently re-verified after the fix: 19/19 unit tests, sys_info refs 0,
  checkout clean, and the tracer still reports 8 with config / native
  descriptor / 222 window keys.
  The implementer noted that content_shell was NOT relinked when the include
  was removed -- Siso's content hashing found no output change -- which is
  stronger evidence the include was dead than reading the source is.

  setsid finding upgraded from "not confirmed" to "one step past": the fix
  build survived genuinely separate SSH/WSL reconnects rather than one
  held-open session. Still only ~19s of wall time, so untested on a long
  build. Do not rely on it for one.

Task 5: dispatched.
Dry-ran Task 7's extraction mechanism ahead of time, read-only:
  git diff BASE HEAD -- <the six paths> currently yields 67 lines across 4
  files (Task 5 will add content/browser/BUILD.gn and browser_main_loop.cc,
  reaching the six the plan predicts). components/camoucfg/ holds exactly
  the seven files Task 7 expects to copy into additions/. No stashes.
  The plan's estimate of "50 to 80 lines touching exactly six files" holds.

  Worth noting the ratio: seven whole new files against 67 diff lines. That
  is the additions-over-patches policy SP6 promotes from preference to rule,
  since every line in patches/ is a line that can conflict on each Chromium
  rebase. SP0 lands on the good side of it.

Task 5: DONE pending review (commit f9b7b21c, browser process verified).
  Independently confirmed: 2 files, 10 insertions, exactly one camoucfg dep
  in content/browser/BUILD.gn, checkout clean. With a real config the browser
  logs "parsed 1 key(s)" and the reachability line. With CAMOU_CONFIG=1
  (invalid JSON) it logs the error once, "parsed 0 key(s)", still reaches the
  line, and does not crash -- criterion 6 demonstrated early, in the browser
  process.

  Two plan defects found and fixed:
  - The verification command piped into plain grep. timeout kills
    content_shell mid-stream and grep's buffer is lost with the pipe, so it
    reproducibly printed nothing while the output was in fact correct. Now a
    file redirect, which also leaves the full log when lines are missing.

  - THE WSL DETACHMENT MYSTERY IS SOLVED, and it is not process-level.
    The entire WSL2 VM is torn down seconds after the last attached wsl.exe
    client disconnects -- confirmed by `uptime` reading "up 0 min" right
    after a build vanished. Nothing inside can outlive the last client, so
    nohup, setsid+disown and Start-Process all fail by construction, and
    Task 4's "setsid survived" was a 19-second job outliving the teardown
    window by luck. What works is keeping a client attached: a foreground
    job in an ssh session held open by ControlMaster/ControlPersist, or
    chunked `timeout -k 15 540 autoninja` calls. Recorded in project memory.

Task 5 review: spec PASS, code quality PASS, one Important finding for
adjudication and two Minor. The Important one is the sharpest of the run.

VLOG(1) << ... HasKey(...) never evaluates HasKey at default verbosity.
VLOG expands to LAZY_STREAM(stream, VLOG_IS_ON(1)), and LAZY_STREAM is
`!(condition) ? (void)0 : ...(stream)` (base/logging.h:374). So the parse
this task exists to force did not happen on a normal launch at all.

Verified empirically rather than by reading alone: with an invalid config
and NO --vmodule, zero camoucfg lines appear -- including the LOG(ERROR)
for malformed JSON, which is not verbosity-gated. With --vmodule, three.

Adjudicated remedy (a), compute the bool before the VLOG, and the reason is
bigger than the diagnostic. CAMOU_CONFIG_STRICT is specified to refuse
startup on malformed config. With a lazy parse the CHECK fires in whichever
process touches config first -- a renderer -- turning "refuse to start" into
a renderer crash, which conventions rule 5 explicitly forbids because a
crash is itself a fingerprint. Forcing the parse in the browser process at
EarlyInitialization makes strict mode mean what it says.

Minor 1 turned out to be a real defect, not just a flag: content/browser/DEPS
exists with 53 +components rules and no camoucfg grant. autoninja does not
run checkdeps.py, so it builds locally and presubmit would reject it. Note
that file grants per DIRECTORY while blink's DEPS grants per HEADER -- match
each file's own convention rather than carrying one across.

Minor 2: the brief's Files header listed only browser_main_loop.cc. Now
lists DEPS and BUILD.gn too.

Task 5: COMPLETE (commits f9b7b21c..a90c2cdc).
  Review: spec PASS, code quality PASS. One Important finding (VLOG lazy
  evaluation meant the parse never ran at default verbosity) and one Minor
  that turned out to be a real defect (missing content/browser/DEPS grant),
  both fixed.
  Independently verified both properties, which must hold together:
    invalid config + no --vmodule -> ERROR fires from the browser process
      (before the fix this printed nothing: proof the parse is unconditional)
    valid config  + no --vmodule -> zero camoucfg lines (silent normal path)
  HasKey is outside the VLOG (grep 0), DEPS grant present, checkout clean,
  19/19 unit tests still pass.
  Recorded in conventions that this parse is load-bearing rather than
  diagnostic, that folding HasKey back inside the VLOG restores the bug
  exactly, and that strict mode depending on a logging line's side effect is
  an open weakness for SP6a or SP7 to resolve properly.

Task 6: dispatched. Full acceptance verification against all six criteria.
Task 6: DONE_WITH_CONCERNS pending fix. 6/6 criteria pass (19/19 unit tests,
9/9 runtime assertions) -- but criteria 2-6 were only observable through a
sequencing-corrected copy, because the committed script crashes.

The crash is mine. When I patched criterion 4 to add the Navigator.prototype
comparison, I put the evaluate() call in the results-assignment block, which
runs after both proc.terminate() calls. Each evaluate() opens a fresh CDP
connection, so it dies with ECONNREFUSED -- before the print loop, so the
script emits zero PASS/FAIL lines and never reaches criterion 6.

The implementer did the right thing three times over: did not edit the
committed script since it was told to use the brief verbatim, wrote an
uncommitted supplement that only moves the read to while the browser is
alive, and stated plainly that the evidence came from the corrected copy.
It could have quietly fixed it and reported 9/9.

Fixed in the plan by hoisting both probes into the live evaluate() batches,
which is also strictly better: Navigator.prototype is now checked in BOTH
runs against the baseline, not one.

Also fixed: the brief said "eight PASS lines" while the script defines nine.
And recorded a real environment finding -- autoninja is not on PATH in a
non-interactive ssh session, because ~/.bashrc only runs for interactive
shells. Every build script must export it explicitly.

Task 6: DONE pending review (commits 7d34db9..5063195).
  SP0 IS VERIFIED. I ran the committed script myself, independently:
  nine PASS lines, exit 0. Plus 19/19 unit tests for criterion 1.
  Six of six acceptance criteria.

  The full sorted-list comparison -- never actually run until now, since my
  own smoke tests only ever compared counts -- passes. Object.keys(window)
  and Object.getOwnPropertyNames(Navigator.prototype) match the pre-spoof
  baseline element for element, in BOTH the spoofed and unconfigured runs.
  That is the assertion separating a C++ implementation from an injected
  one, and it now has evidence rather than inference.

  The implementer checksum-verified the script on both machines, ran it
  twice back to back, and deleted the supplement so no second script can
  drift from the real one.

Task 7: dispatched. The task that makes all of it durable -- until it runs,
SP0 exists only as a branch inside a directory gclient regenerates.
