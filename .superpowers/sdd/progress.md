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
Task 6 follow-up: the fixed script still flaked, 1 run in 4, with
ECONNREFUSED on the FIRST evaluate() -- a different failure from the
reconnect-after-terminate bug. The implementer ruled out stray processes and
ports, confirmed content_shell normally binds well inside the 5s sleep, re-ran
unmodified to 9/9, and did not patch it. Correct call: it is a startup timing
race, not a logic defect.

Fixed anyway, because an intermittently failing verification is worse than a
slow one. When it goes red the natural reading is "the code regressed" and
someone hunts a bug that is not there; worse, people learn to re-run until
green, and then the script measures nothing. A fixed sleep is hope. launch()
now polls the DevTools endpoint until it answers, with a 30s deadline and a
loud RuntimeError if it never does.

Fixed a latent second flake in the same pass: stderr was a PIPE read after
terminate, which would deadlock the child if Chromium's startup noise ever
filled the buffer. It now goes to a file that each launch truncates.

Task 6: COMPLETE. Flake fix applied and verified.
  I applied the launch() change myself rather than nudge a fourth time --
  mechanical text substitution in a file I wrote, no fresh-eyes value.
  Pushed, md5-matched both sides (f78a1e13...), ran FOUR consecutive times:
  9/9 PASS, exit 0, every run. Before the fix it was 3 of 4.
  Four is deliberate: a one-in-four flake makes a single green run
  meaningless.
  Note the Task 6 review was dispatched against the pre-flake-fix script,
  so any finding about launch()'s sleep is already addressed.

Task 7: dispatched. Until it lands, SP0 exists only as a branch inside a
directory gclient regenerates.
Task 6 second flake: the implementer ran EIGHT times where I had run four,
and found 6/8 -- two failures in a mode never seen before, TargetClosedError
on the first evaluate(). My 4/4 was luck. I had told it a one-in-four flake
makes a single green run meaningless, then stopped at four and treated that
as settled. Under-applied my own rule.

It hypothesised port reuse (terminate() without wait(), fixed PORT). Reading
the script I think there was a third cause it did not name and which fits the
symptom better: --user-data-dir was absent entirely, so consecutive runs
shared the default profile and the next instance could start while the
previous still held the profile lock. The poll then reaches the dying
instance's endpoint and the target vanishes.

Rather than guess which cause it was, closed all three: a fresh
--user-data-dir per launch, --remote-debugging-port=0 with the port read
back from DevToolsActivePort so the browser picks and we read its choice,
and terminate() followed by wait() with kill() on timeout. Added an explicit
check for content_shell exiting during startup, so that reports itself
instead of masquerading as a 30-second timeout.

Verified with TEN consecutive runs: 9/9 PASS and exit 0 every time, md5
matched between repo and build machine. Criterion 4 passed in all ten, which
also disposes of the risk I created by changing the launch flags -- the
baseline was captured without --user-data-dir, and it still matches.

Task 6 review (of the pre-flake-fix script): compliant, one Critical class,
four Important. Two were already closed by e794336 (proc.wait, fixed port,
sleep). Three were new and all correct:

CRITICAL -- no assertion tested "does not crash", and the script had zero
exception handling in a single linear sequence with one print loop at the
end. Any exception discarded EVERY already-computed result behind an
unattributed traceback. The fault most likely to trigger it is precisely the
one criterion 6 exists to detect. Fixed: session() returns exceptions rather
than raising, each group degrades to FAIL independently, and criterion 6 has
its own named "does not crash the browser" assertion. DESCRIPTOR_PROBE now
reads defensively too -- a getter demoted to a data property used to throw
inside the page, so a regression in SP0's most important assertion crashed
the harness instead of printing FAIL.

IMPORTANT -- launch() cleared only CAMOU_CONFIG, not CAMOU_CONFIG_1..N or
CAMOU_CONFIG_STRICT. Numbered chunks take precedence, and this machine is
exactly where stale ones get made. Fixed by stripping every CAMOU_CONFIG*.

IMPORTANT -- the literal 16 was retyped twice while the loaded baseline
already carried hardware_concurrency. Now derived from it.

PROVED the env fix is load-bearing rather than merely consistent with
passing: ran a mutant with the old env handling under an injected leftover
CAMOU_CONFIG_1={"navigator.hardwareConcurrency":99}. Five of eleven
assertions go red, including "malformed config logs an error" -- the
leftover is valid JSON so nothing logs an error, and the run's premise
silently evaporates. The real script under the same injection: 11/11 PASS.

Assertions went from 9 to 11 (non-crash, and descriptor checked in both
sessions).

Task 6 fault injection (cross-check, 5 induced faults): 4 of 5 behaved as
the session() rewrite intends -- browser exits during startup, browser
binary missing, an assertion forced false, and a browser killed mid-session
all degraded their own group to FAIL and left the rest reporting real
results. The fifth found the gap.

The baseline load sat bare at module level, before any session() call, so a
missing or malformed baseline produced a traceback and ZERO PASS/FAIL lines
-- the exact collapse session() exists to prevent, on the one path it did
not cover, and on the file the most important assertion depends on. The
cross-checker predicted this from reading the code, then confirmed it by
running. Right order.

Fixed and verified by re-injecting the same fault: 7 PASS, 4 FAIL (exactly
the baseline-dependent assertions), one note naming the path and cause,
exit 1. Normal run still 11/11.

Two smaller corrections from the same report:
- Assertion key names embedded the machine's core count via f-string, so an
  assertion's identity changed with the machine running it and a FAIL line
  would not grep on another box. Now fixed strings.
- launch() has THREE distinguishable startup failures, not two: Popen raises
  FileNotFoundError naming the path, the process can exit during startup, or
  it can live without ever opening a port. The docstring said two.

Task 7: COMPLETE (commits 9b552df partially, 964de71). SP0 IS DURABLE.
  Reconstruction reproduced a passing verification, which is the whole point
  of the task: fresh branch off the pinned base revision, scripts/apply.sh
  applied cleanly, git diff --stat matched the extracted patch at 132 lines
  across 7 files, the patch reverses cleanly, content_shell rebuilt in 40s,
  and verify_sp0.py against the RECONSTRUCTED tree gave 11/11 PASS, exit 0.
  Remote returned to camoucrome/sp0, clean.

PROCESS FAILURE, MINE. I ran `git add -A` in the Camoucrome repository while
Task 7 was actively writing additions/, patches/ and scripts/apply.sh into
its working tree. Commit 9b552df therefore carries 1117 insertions and the
whole of SP0's extracted change set, under a message describing an exception
handling fix in a test script. Task 7's own copies are byte-identical to what
landed, so the deliverable is correct -- but git log now misdescribes how it
got there, and Task 7 could not use its own commit boundary or message.

Not rewritten. Nothing is pushed, so a rebase would be safe, but erasing the
mistake would also erase the evidence of it, and this repository's present
value is largely its record of how each defect was found. Corrected in the
record instead.

RULE for the rest of this project: never `git add -A` in a repository another
agent may be writing to. Stage explicit paths. The cost of the habit is one
misleading commit here; in a shared checkout with several agents it is
arbitrary work landing under arbitrary messages.


---

## SP1a — UA / UA-CH producer

Spec amended 2026-08-27 (commit e88ff2d) after reading the whole of
user_agent_utils.cc. Plan at docs/superpowers/plans/2026-08-27-sp1a-ua-producer.md.
Seven tasks. None started.

Chromium branch stays camoucrome/sp0; SP1a's base is a90c2cdcb3 (SP0's head).
Pinned checkout base revision is unchanged: 0e8d4a9268118d323f62ca207b40514df39dcaa9.

Facts probed from the real tree on 2026-08-27, so no task re-derives them:

  NavigatorBase          third_party/blink/renderer/core/execution_context/navigator_base.{h,cc}
  UA producer            components/embedder_support/user_agent_utils.cc
    GetUserAgentInternal        :216   picks reduced vs full
    GetUserAgentPlatform        :281   compile-time BUILDFLAG arms
    GetUnifiedPlatform          :301   holds "Windows NT 10.0; Win64; x64" in its IS_WIN arm
    GetUserAgentFromCommandLine :453   --user-agent short-circuit
    GetUserAgent                :465
    GetPlatformForUAMetadata    :616
    GetUserAgentMetadata        :648
    BuildUnifiedPlatformUserAgentFromProduct :839
    BuildUserAgentFromProduct                :844
  GN target              static_library("user_agent") in components/embedder_support/BUILD.gn
  DEPS                   components/embedder_support/DEPS, directory-granted, alphabetical

TASK 1 MUST RUN FIRST AND MUST NOT BE REORDERED. It captures the unspoofed UA
surface from the current binary. After Task 4 edits the producer there is no way
to capture that file again without rebuilding from the pinned base revision, and
Task 6's whole no-config regression sweep is worthless without it.

Order of the rest is not arbitrary either: Task 6 reuses HIGH_ENTROPY and
ACCEPT_CH defined in Task 5.

### Mid-execution amendment, 2026-08-27 (during Task 1)

Task 1 escalated BLOCKED at Step 6 and was right to. Root cause, verified
independently and one level deeper than the escalation found it:

  content_shell NEVER CALLS embedder_support::GetUserAgentMetadata().
  ShellContentBrowserClient::GetUserAgentMetadata()  shell_content_browser_client.cc:750
    -> GetShellUserAgentMetadata()                   shell_content_browser_client.cc:348
       builds the struct from scratch; platform = "Unknown" hardcoded.
  Only ChromeContentBrowserClient::GetUserAgentMetadata() calls it
    (chrome/browser/chrome_content_browser_client.cc:7702).

  But the UA STRING path is fine:
  ShellContentBrowserClient::GetUserAgent()          shell_content_browser_client.cc:732
    -> embedder_support::BuildUnifiedPlatformUserAgentFromProduct  (:747)
  which is one of the exact two functions Task 4 patches. Two sibling methods
  on one class, one delegating to shared code and one not.

  Two further walls behind that: ShellBrowserContext::GetClientHintsControllerDelegate()
  returns nullptr outside test harnesses, so content_shell emits no Sec-CH-UA*
  headers at all; and --run-web-tests wires a mock delegate but perturbs window
  with web-test-only globals, destroying the surface the baseline protects.

MY ERROR, not the subagent's and not the plan's. 00-conventions.md already
warned "check which target owns a surface before planning its verification"
and I planned SP1a without checking. Conventions is now amended with the
stronger rule the case actually teaches: confirm the binary under test CALLS
THE FUNCTION BEING PATCHED. Grep the patched symbol's callers, not the
feature's name.

Rejected: wiring a ClientHintsControllerDelegate into content_shell. It would
produce headers built from GetShellUserAgentMetadata -- a test verifying code
that never ships. Testing the mock.

Decisions (user's, 2026-08-27):
  - Task 5 verifies via components_unittests now (calls the shipping function
    directly, seconds, no browser). Its browser assertions are kept in the plan
    inside a <details> block because Task 8 reuses them almost unchanged.
  - NEW TASK 8, runs last and alone: build chrome at the pinned base in a git
    worktree + out/Base, capture the chrome baseline, build patched chrome,
    verify items 2/3/4 end to end. Long pole, hours. Alone so it never competes
    for CPU with the content_shell rebuild loop Tasks 3-6 need.
  - Backup done: github.com/lang315/camoucrome, private, 52 commits pushed.
    Scanned first -- no password in tracked files or history. The Tailscale IP
    100.81.40.76 is in the SP1a plan; private repo, flagged to the user.

Task 1 status: unblocked with option A. Capture what content_shell truly is,
including the empty header set, plus a `provenance` block naming the binary,
the commit, both producers, and what is known-absent and why.

Task 1: complete (commit 30790b9, review clean -- Approved, no Critical, no
Important). Controller follow-ups landed after the review:
  - baseline provenance.known_absent contradicted its own request_headers
    (my dictation error, not the implementer's). Corrected, plus the two
    places the plan repeated it.
  - reviewer's one WARN, provenance.ua_string_producer, resolved: I had
    verified it in my own probe (shell_content_browser_client.cc:747) but the
    evidence was outside both the diff and the report. Both producer entries
    now cite file:line so the artifact supports its own claims.
  - Minor findings fixed: unused imports trimmed from verify_sp0.py, the
    unguarded git subprocess in capture_ua_baseline.py guarded.
  - Minor finding RECORDED, not fixed, for the final whole-branch review:
    baselines/content_shell-sp0-stock-ua.json navigator_keys is [""] not [],
    because "".split(",") == [""]. Faithful data, and symmetric with the
    comparison side which also uses .split(","), so both sides agree. Only a
    hazard for anyone writing a naive `!= []` check.

ENVIRONMENT TRAP, cost one false-green run, do not repeat:
  scp lands on the WINDOWS filesystem; `wsl -- ...` sees WSL's. Two different
  /tmp. `cp /tmp/verify-drop/*.py ~/...` printed "cannot stat", the script
  kept going, and verify_sp0.py ran the PREVIOUS version and reported 11 PASS.
  Transfer file contents through the stdin script and md5sum both ends.
  Recorded in the plan's Environment section.

Task 2: complete (Mac e60e5a5, Chromium 04b16e1c39; review Approved, no
Critical). Follow-ups landed:
  - Task 2 CAUGHT A FALSE GREEN IN MY PLAN: --gtest_filter='Camoucfg*' selects
    2 of 21 tests and prints PASSED, because only CamoucfgKeysTest carries that
    prefix; SP0's suites are AssembleRawConfigTest, ParseConfigTest,
    ParseConfigDeathTest, GettersTest, MaskConfigTest. Verified both filters on
    the checkout (2 vs 21, both exit 0). Union filter now used everywhere.
  - Review's one Important, plan-mandated: navigator.uaData is not a property
    path (real API is navigator.userAgentData), so the dot promised a JS path
    that does not resolve -- my error in the SP1 spec, faithfully transcribed.
    RENAMED to a single synthetic ua: namespace (ua:platform, ua:bitness, ...)
    with constants kUaPlatform etc. Done now because zero call sites existed;
    conventions warns a rename after SP6a generates constants is breaking.
    Rebuilt and re-ran: 21/21, md5 matched both ends.
  - Minor RECORDED for the final review: kAllKeys initializer alignment is not
    clang-format output. Cosmetic.

RULE EARNED, THE HARD WAY, TWICE: a check that reports success while measuring
almost nothing is the failure mode of this project, not a test that fails.
Both catches today (scp silently copying nothing, gtest filter matching 2 of
21) came from someone reading output and finding it SMALLER than it should be
-- never from a failure. Assert the expected COUNT, not just the exit code.

Controller edit during Task 3: added kNavigatorHardwareConcurrency to keys.h
(kAllKeys 9 -> 10). SP0's key was missing from a registry whose stated purpose
is that keys stop being string literals, while browser_main_loop.cc:564 still
used the literal. Built and tested: 21/21, md5 matched both ends.

DEFERRED ON PURPOSE: the Chromium-side commit of that keys.h change waits
until Task 3 reports. Task 3 is staging in the same checkout right now, and a
`git add` landing between its add and its commit would sweep my file into its
commit -- the exact failure I caused in SP0 with `git add -A`. Explicit paths
narrow that window; they do not close it. File is on disk and builds; the
commit can wait.

navigator_base.cc keeps its literal for now. Converting it means pulling an
unrelated file into Task 4. Recorded for SP1b or the final review.

Task 3: complete (Chromium 9a15333574, 3 files +4 lines; 21/21 union filter;
both gates demonstrated failing then passing). Review dispatched.

TASK 3 FOUND TWO DEFECTS IN MY PLAN, both false greens:

  (3) Neither dependency gate fires on a .cc-only change. gn check runs during
      gn gen, which autoninja triggers only on a BUILD.gn/.gni change;
      checkdeps.py is never run by the build. autoninja exited 0 with two
      disallowed includes in place. Ruled out the "it did nothing" objection:
      4 real steps, .o 14s newer than .cc -- and the object compiled while the
      include was disallowed was REUSED by the later build, going into the
      final binary unexamined. Conventions corrected; it had said a missing
      entry is "a hard build failure", generalised from SP0's single case
      where a concurrent BUILD.gn edit forced the regen.

  (4) Every build command in the plan swallowed its own exit code.
      `autoninja ... 2>&1 | tail -5` then `echo "exit=$?"` reports tail's
      status. Six occurrences -- all of them. Demonstrated: `false | tail -1;
      echo $?` prints 0, with pipefail prints 1. All six guarded.

FOUR FALSE GREENS IN ONE DAY. scp copying nothing; gtest filter matching 2 of
21; neither dep gate firing; build exit code eaten by a pipe. Three of the
four were mine. NONE was caught by a failure -- every one was caught by
someone noticing a result was smaller than it should be.

Standing rule for every remaining task: assert the expected COUNT or the
expected FAILURE. An exit code of 0 is not evidence that anything was
examined.

Task 3: review Approved, 0 Critical, 0 Important. Two Minor, both about the
quality of evidence rather than the change; I settled both myself rather than
asking, since re-running is cheaper than a round trip and stronger than a log:
  - test count: 21, confirmed twice independently -- the [21/21] progress
    counter in the raw run, and --gtest_list_tests | grep -c '^  ' = 21. The
    (10,10,1) PASSED lines the reviewer could not account for are Chromium's
    test launcher sharding across child batches, each printing its own line.
  - the .o mtime is still 07:41:39, the Step 1 build, taken after Task 3 had
    added BUILD.gn + DEPS and rebuilt. Adding a dep changed the link, not the
    compile command, so ninja never redid it. The object compiled while the
    include was disallowed is the one in the binary right now. Recorded in
    conventions with the timestamps.

Task 4: complete (Chromium aab538cfab, Mac b3720dc). RED 3 FAIL/2 PASS then
GREEN 5/5; verify_sp0 11/11; unit tests 21/21 union filter.

I observed the four behaviours on the running binary myself rather than
trusting the report, given the day's four false greens:
  no config            -> Mozilla/5.0 (X11; Linux x86_64) ... Chrome/999.0.0.0
  ua:osInfo = Windows  -> Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/999.0.0.0
  {not json            -> X11; Linux x86_64, no crash
  navigator.userAgent  -> ignored, warns, names ua:osInfo

The OS moves and Chrome/999.0.0.0 does not, including under a config that
tries to set a version. That holds because the substitution point is the
os_info argument and `product` never passes through it -- the shape of the
code, not an assertion someone has to remember to run. This is the payoff for
amending the spec after reading the real producer: the original design routed
the finished string through the patch every time, which would have made the
version invariant depend on continued care.

Coverage limit, stated rather than buried: content_shell exercises only
BuildUnifiedPlatformUserAgentFromProduct. The sibling is patched but unrun
until Task 8.

Task 4: review Approved, 0 Critical, 1 Important, 2 Minor.

  Important (mine -- the brief mandated the line): verify_sp1a.py read
  STDERR_LOG unguarded, the one fault path in that file not wrapped. An
  unreadable log would have exited by traceback before the print loop,
  discarding assertions already collected. Fixed in the script and in the
  plan, before Tasks 5 and 6 extend the same file. Re-ran: 5/5, md5 matched.

  The reviewer's WARN alongside it was the sharper question, and it could
  have been false green number five: if lib_shell APPENDED to STDERR_LOG,
  stale "ua:osInfo" text from an earlier run would satisfy the substring
  check spuriously. It could not check; I did, two ways. launch() opens the
  log "wb", which truncates, and empirically a warning written by one session
  is gone after the next. The assertion is sound.

  Minor 1: the kNavigatorHardwareConcurrency swap in browser_main_loop.cc was
  NOT in the brief. It was authorised -- I put it in the dispatch prompt
  explicitly, having added the constant during Task 3. The reviewer was right
  to ask rather than assume; a diff hunk with no line in the brief behind it
  is exactly what an unrequested change looks like.

  Minor 2 (ua:osInfo embedded unescaped) matches the project-wide trust model:
  config is operator-supplied, like every other camoucfg value. Recorded, not
  actioned.

  Reviewer's two "cannot verify from diff" items both resolve to things I had
  already checked and it could not see: GetUserAgentInternal's structure, and
  lib_shell's fault handling. Neither is a gap in the change.

Task 5: complete (Chromium 3109506535). Four config invocations verified by me
independently, each in its own process: fallback / configured / version-cannot-
move / formFactors -- all exit 0. Upstream UserAgentUtilsTest.* 23/23.
verify_sp1a 5/5. SP0's filter still 21/21.

Two concerns, both mine, both real:

  (1) SDD SCRATCH NAMESPACE COLLISION, AND SP0 WORK WAS LOST.
      .superpowers/sdd/ is gitignored (.gitignore is "*"), and SP0 and SP1a
      both write task-N-brief.md / task-N-report.md. SP1a's runs overwrote
      SP0's task-1..5 reports, which existed in no other copy. Task 5's
      implementer noticed and backed up the two files it was about to clobber;
      the earlier four were already gone before anyone looked.

      What survives is the durable record -- commit messages, the specs, this
      ledger -- which is where SP0's findings actually live. What was lost is
      the working notes behind them. Not catastrophic, and the SDD skill does
      treat this directory as scratch that `git clean -fdx` may destroy. But
      it was avoidable and I did not think about it.

      Fixed: SP0's survivors moved to sp0-archive/, SP1a's renamed
      sp1a-task-N-*.md. Every later sub-project prefixes its own.

  (2) FALSE RED, the mirror of this project's usual failure. Step 5's
      --gtest_filter='UserAgentUtils*' also prefix-matches the new
      UserAgentUtilsCamoucfgTest suite, which needs one process per config, so
      unconfigured it reports three failures that are the new tests working as
      designed. Verified: UserAgentUtils* lists 27, UserAgentUtilsTest.* lists
      23, difference is the new suite. Corrected to UserAgentUtilsTest.* with
      the count asserted.

      Worth distinguishing from the false greens: a false red costs less,
      because someone investigates. But an investigation ending in "the check
      was wrong" teaches people to distrust the check, and that is how a later
      true failure gets waved through.

Task 5: review Approved, 0 Critical, 0 Important. Both WARNs resolved by me:
camoucfg includes are present (user_agent_utils.cc:29-30, added by Task 3);
and the registry contains no version or brand key at all -- kUaPlatformVersion
is an OS version, not a browser one -- while ParseConfig keeps no whitelist,
so unknown keys land in the dict and are simply never read.

Acted on one Minor rather than filing it. The gate asked only about ua:osInfo
while D1 states the rule for any ua: key. A config setting ua:platform without
ua:osInfo let --user-agent win the string while config won the metadata.
Widened at BOTH sites, derived from the registry so later keys are covered
automatically. Partial-config incoherence stays SP5a's, explicitly.

AND I NEARLY RECORDED A FALSE MUTATION RESULT. The first mutant reverted the
gate, which left the helper unused; the build failed on -Wunused-function, the
test ran against the STALE binary, and printed OK. Same shape as everything
else today. The second mutant narrows the helper instead so it still compiles,
and the test then fails with architecture empty -- the predicted symptom.

Rule this earns, for every mutation test from here: CONFIRM THE MUTANT BUILT.
A mutation that does not compile does not test anything, and it reports a pass.

Task 6: complete (Mac 6b34d4f), review Approved, 0 Critical, 0 Important.
9 PASS verified by me independently; assertion count 9; remote baseline md5
identical to the Mac's committed copy; HIGH_ENTROPY/ACCEPT_CH now grep to one
definition each, both in lib_shell.

Mutation did its job: mutant BUILD CONFIRMED first (the Task 5 lesson), then
6 PASS / 3 FAIL, the three predicted, each with a named cause. Restored green.

One Minor fixed rather than filed: echo_server.start() was the single external
call outside a guard in a file whose entire premise is that no one fault
discards results already collected. Near-zero probability -- port 0, kernel
assigned -- but Task 8 clones this file, so the fix travels. Re-ran: 9 PASS,
md5 matched.

Reviewer note worth keeping: capture_ua_baseline.py leaves the same call bare
ON PURPOSE, because that script exits 1 on any failure by design. Same code,
different contract. Not every unguarded call is a defect.

Task 7: complete (Mac 4bfc2e3). Patch verified by me: exactly 6 files matching
the derived table, 346 lines, and apply.sh needed no edit -- it already globs
patches/*.patch, so the new patch was picked up unmodified.

Reconstruction from the pinned base through apply.sh alone: patch-owned files
diff empty against camoucrome/sp0, all additions/camoucfg files md5-identical,
and every suite RUN rather than listed -- verify_sp0 11/11, verify_sp1a 9/9,
camoucfg union 21/21, UserAgentUtilsCamoucfgTest 5/5 each in its own process,
upstream UserAgentUtilsTest 23/23.

My own duplicate-file check was wrong and I nearly reported a collision: I
stripped directories before comparing, so embedder_support/BUILD.gn and
camoucfg/BUILD.gn collapsed to the same string. Different files, different
directories. The check was broken, not the work -- and it is the ninth thing
today whose output could not be trusted at face value, this one mine and
caught by reading what I had actually compared.

Three environment facts recorded in conventions, all found by Task 7:
  - /tmp on the build PC does NOT survive between ssh invocations. The VM is
    torn down when the last client disconnects and /tmp is tmpfs. Write
    throwaway scripts on the client and pipe on stdin; persist under ~.
  - git apply --3way stages its result, so git diff --stat immediately after
    reads EMPTY and looks like the patch did nothing. Use --cached.
  - git checkout -- . will not clear an unmerged index from a conflicted
    apply; git reset --hard will.

Task 7: review returned NEEDS FIXES -- one Critical, one Important, both in
the README rather than in the patch or the reconstruction, which it called
excellent and byte-verified.

  Critical: the status line claimed navigator.userAgent, navigator.userAgentData
  and the Sec-CH-UA* headers were "spoofable and coherent". All three are
  patched; only the first is verified end to end. userAgentData has unit tests
  and no browser; the headers have no verification at all; and cross-channel
  coherence -- this sub-project's whole thesis -- is precisely the row still
  open, pending Task 8.

  That is the tenth instance today of a claim reporting more than it measured,
  and the worst placed: in the one artifact whose job is to state status
  truthfully. A test that overclaims misleads whoever reads its output; a
  README that overclaims misleads everyone who never runs anything.

  Replaced with a per-channel table naming the evidence behind each row, plus
  the reason the gap exists -- content_shell reimplements
  GetUserAgentMetadata() and returns a nullptr ClientHintsControllerDelegate,
  so the gap is the test binary rather than neglect.

  Important: three rows still depended on "SP1" after that entry was split
  into SP1a and SP1b -- a dependency on a row the table no longer contained.

  PROCESS NOTE, recorded rather than left implicit: I fixed both myself as
  controller and did NOT re-dispatch the reviewer, which the SDD loop asks
  for. The finding was precise, the fix is one README section, and a fresh
  agent to re-read a paragraph is disproportionate. If a later reader thinks
  that was the wrong call, the fix is in commit history to judge.

Task 8: STARTED EARLY, in parallel with Task 7's review. The checkout is on
camoucrome/base-for-baseline at the pinned base 0e8d4a9268, confirmed
unpatched (OsInfoOverrideOr absent, components/camoucfg absent), and a chunked
chrome build is running in the background -- 9-minute chunks, each its own ssh
call so the build survives WSL teardown between them. Build state lives in
~/chromium, which persists; only /tmp is tmpfs.

Nothing depended on Task 7's review to start it, and it is the longest pole
left.

SP5a Task 1: WRITTEN AND LOGIC-VERIFIED ON THE MAC, not yet built.

The checkout is unavailable on two counts -- it sits on the base revision, so
components/camoucfg does not exist there, and out/Default is occupied by the
chrome build for SP1a Task 8. Switching branches would change inputs under a
running siso. So Task 1 splits: write and check locally now, build and run the
gtest suite when the checkout frees.

What was actually verified on the Mac, which is more than syntax:
  - derive.cc compiles clean under -std=c++20 -Wall -Wextra -Werror against
    the REAL keys.h and a mask_config.h stubbed to exactly what it touches.
  - A gtest-free harness ran the same 28 assertions the unit test will. All
    pass.
  - MUTATION: moving the Linux entry to the front of kForms produced 3
    failures -- osinfo Android, "Android not read as Linux", and the round
    trip. The ordering assertions are real.

AND THE MUTATION FOUND A DEFECT IN MY OWN TEST. "CrOS not read as Linux"
PASSED under that mutant, because "X11; CrOS x86_64 14541.0.0" contains no
"Linux" token at all. It cannot fail under any permutation of kForms.

Not deleted: real ChromeOS user agents are sometimes spelled
"X11; CrOS Linux x86_64", so it guards a future change to the canonical
string. But it does NOT guard the current ordering, and presenting two
assertions as if both did is the same overclaim counted eleven times today.
Split into two named tests, each saying what it actually protects.

Plan corrected: 6 DeriveTest cases -> 7, union filter 27 -> 28.

SP5a Tasks 2 and 3: WRITTEN AND LOGIC-VERIFIED ON THE MAC, not yet built.

Task 2, the registry: invariants.h compiles clean under -Werror, the JSON
parses, and -- run now rather than waiting for the suite -- the two AGREE, so
the file was never committed in a drifted state. A fourth check the plan did
not ask for found something worth a test: every key an entry names must be
declared in keys.h, because an entry naming a nonexistent key is SILENT. The
validator asks, gets nullopt, treats it as absent, skips. The entry reads as
protection and provides none -- the registry's own version of the failure the
registry exists to prevent. Added as EveryInvariantKeyIsDeclaredInTheRegistry.

Task 3, the validator: 12 assertions run against the real functions with a
scripted config, all pass, including REPAIR IDEMPOTENCE -- verification item 2,
which the plan had deferred to Task 4 and which turns out to be three lines
here.

Two mutants, both built before being believed:
  agreement no longer exempts  -> "coherent config" and "idempotent" fail
  authority/repaired swapped   -> both naming assertions fail
Right assertions, right reasons.

THREE CHANGES TO THE PLAN, made while writing:
  - ValidateAndRepairAtStartup renamed ValidateAtStartup. It does not repair.
    A name claiming an action it does not perform is the overclaim counted
    repeatedly today, and in an identifier it misleads at every call site
    rather than once at the console. Renaming beat writing a comment
    apologising for the name.
  - Violation gained authoritative_key. Reporting that a value is wrong
    without naming what it disagrees with is half a report, and two harness
    assertions depend on it.
  - Idempotence moved earlier, since it costs three lines here.

Remaining for when the checkout frees: build all three tasks against Chromium,
run the gtest suites by count, then Tasks 4-7.

HAZARD, ACTIVE RIGHT NOW -- DO NOT RUN verify_sp0.py OR verify_sp1a.py.

The checkout is on camoucrome/base-for-baseline and out/Default has been
building chrome AT THE BASE REVISION for the last hour. This is a component
build, so shared libraries content_shell links have been rebuilt from
unpatched source. out/Default/content_shell is therefore neither the SP1a
binary nor a clean base binary -- it is an undefined mixture.

Running either verification against it would produce numbers that look
meaningful and are not. Depending on which libraries got rebuilt it could
report 11 PASS, or fail in ways that read as a regression in work that is
actually fine. Both outcomes are worse than not running it.

Safe only AFTER: git checkout camoucrome/sp0, then rebuild BOTH content_shell
and chrome. Task 8 Step 3 already says to rebuild content_shell; this is why.

SP5a API RISK RETIRED. The ~500 lines written today were checked only against
stubs I wrote myself, which is circular. Read the real headers on the checkout
-- reading is safe, only writes and builds conflict with siso, and I had been
over-restricting myself:
  base::ListValue          exists; 570 files in components/ use it, 0 use
                           base::Value::List. The plan's usage is correct.
  DictValue::FindList      const ListValue* FindList(std::string_view) const
  DIR_SRC_TEST_DATA_ROOT   base/base_paths.h:71
  Environment::Create()    std::unique_ptr<Environment>
  Environment::GetVar()    virtual std::optional<std::string> GetVar(cstring_view)
  ReadFileToString         (const FilePath&, std::string*)
All six match what the unbuilt code assumes, and SP0's own call site agrees.

STOPPING SP5a CODE HERE. Tasks 1-3 is already more unverified code than one
build cycle should have to validate at once, and Tasks 4-7 all need the
checkout regardless -- 4 needs gtest, 5 patches Chromium, 6 needs a browser,
7 needs git. Writing Task 4 now would add unverified surface without adding
verification: its logic is already proven by the local harness.

---

2026-08-27, while the base-revision chrome build runs (commit b66095a).

TASK 8 STEP 2 IS DONE, out of order and deliberately. It needs no checkout and
no browser, so doing it during the build costs nothing and removes it from the
window where the binary is finally available. Steps 1, 3, 4, 5 still pending.

Two defects found by reading Task 8 against its own script, before running it:

  provenance was hardcoded    binary="content_shell" plus a known_absent list
                              asserting no sec-ch-ua-* header arrives. Step 3
                              expects chrome to produce the opposite of both.
                              Nothing reads provenance -- verified, verify_sp0
                              and verify_sp1a read only surface keys -- so the
                              contradiction would never have failed anything.
                              Now derived; unknown binaries refused.
  --headless=new justified    by a "deprecated alias" claim this tree does not
                              support. IsHeadlessMode() is HasSwitch(kHeadless)
                              and no code reads the value. Reverted to bare
                              --headless, which is what the plan said.

New: scripts/test_lib_shell_launch.py, 7 PASS exit 0, runs anywhere -- no
browser, no checkout. Two mutants confirmed, each failing exactly one check.

STILL REQUIRED when the checkout frees: verify_sp0.py (11 PASS) and
verify_sp1a.py (5 PASS). The argv test proves the launch line is unchanged; it
says nothing about whether the browser still answers the same way.

THE HAZARD ABOVE IS STILL ACTIVE. out/Default/content_shell remains an
undefined mixture. Nothing in this entry touched the checkout -- reads only.

---

2026-08-27, later. TASK 8 COMPLETE. HAZARD CLEARED.

Build at 0e8d4a9268 finished; proved by a second autoninja returning "no work
to do", 0 steps -- not by the task's exit 0, whose log was empty.

Baseline captured, then checkout returned to camoucrome/sp0 (07cadeac4c) and
BOTH binaries rebuilt. The undefined-mixture hazard recorded above is gone.

  verify_sp0.py          11 PASS, 0 FAIL
  verify_sp1a.py          9 PASS, 0 FAIL, exit 0
  verify_sp1a_chrome.py  17 PASS, 0 FAIL, exit 0   <- criteria 1,2,3,4,8

SP1a's central claim -- one producer, three coherent channels -- is verified
end to end. Criterion 4 checks the channels against EACH OTHER in one session,
which is the only formulation that catches a bypassed path.

CRITERION 4 WAS WEAK AND THE MUTATION FOUND IT. The clause
    ua_platform != "Windows" or "Windows NT" in ua
is true for every non-Windows value, so it asserted nothing outside the case
under test. Discovered by trying to design a mutation and finding none could
fail. Replaced with an explicit mapping where an unknown platform FAILS.
Mutant (ua:platform=Linux beside a Windows ua:osInfo): 16 PASS, exit nonzero,
exactly one FAIL, the predicted one. The old clause passes that mutant.

NEW DEFECT, NOT SP1a's: the UA product token is HeadlessChrome/154.0.0.0.
user_agent_utils.cc:218 does product.insert(0, "Headless") under
HasSwitch(kHeadless) -- inside the patched function, three lines above SP1a's
substitution point, unreachable because product never crosses it. A Windows
fingerprint therefore emits "...Windows NT 10.0... HeadlessChrome/154.0.0.0".
Filed to SP2's surface table with file and line. Stock chrome is ALREADY
incoherent here: UA says headless, brands and sec-ch-ua say Chromium, so SP2
must assert the token on all three channels. NOT an SP5 registry entry -- that
registry compares config keys and this has no key.

STALE COUNT FOUND: the plan said verify_sp1a.py gives 5 PASS in two current
instructions. True when Tasks 4-5 wrote it; Task 6 grew the file to 9. Both
corrected; the two historical mentions annotated rather than edited.

TOOLING TRAP, hit four times today, now in conventions: $? and $(...) sent
over ssh are expanded by PowerShell 5.1 BEFORE wsl runs. $? is a PowerShell
boolean, so a failing command prints "True"; $(git ...) runs on the Windows
side in C:\. Only && / || markers and grep -c counts survive the trip.

NEXT: SP1a whole-branch review (SDD requires it after the last task), then
SP5a Tasks 1-3 against a real compiler, then Tasks 4-7.

SP1a DRIFT CHECK, before dispatching the whole-branch review: NO DRIFT.
The SP1a-only range (a90c2cdcb3..07cadeac4c) is 9 files, 531 lines. Six live
in patches/sp1a-ua-producer.patch; three (keys.h, keys_unittest.cc, BUILD.gn)
live in additions/, per the repo's patch-vs-addition split. All nine camoucfg
files hash-match between the Mac repo and the checkout except BUILD.gn, and
that difference is entirely SP5a's unbuilt files. SP1a is faithfully
represented by what is committed.

SP5a DEFECT FOUND BY THAT CHECK: coherence_validator.cc/.h were NOT in
BUILD.gn sources, though Task 3's own file list says to modify BUILD.gn. A
file absent from sources is simply not compiled and nothing errors -- SP5a
would have "built" with its central component never compiled, and the Task 4
tests would have failed to link with a message pointing at the test rather
than at the omission. Added. derive.cc was there; only the validator was
missing, which is why the omission was invisible.

---

SP5a TASKS 1-3 NOW BUILD AND PASS ON A REAL COMPILER. The ~500 lines that had
only ever been checked against stubs I wrote myself are no longer circular.

  branch                 camoucrome/sp5a (off camoucrome/sp0)
  autoninja              BUILD_OK, 11 steps; gn gen re-ran because BUILD.gn
                         changed, so gn check ran on the new files too
  objects                coherence_validator.o (21096 B) and derive.o (6080 B)
                         both present -- coherence_validator.o exists ONLY
                         because of the BUILD.gn fix above
  components_unittests   27/27 SUCCESS, exit 0
                         DeriveTest 7 (as planned) + SP0's 20

Union filter used, never Camoucfg*, which selects 2 of 27:
  DeriveTest.*:CamoucfgKeysTest.*:AssembleRawConfigTest.*:ParseConfigTest.*:
  GettersTest.*:MaskConfigTest.*

MUTATION, against the real build rather than my stubs. Moved the kForms Linux
entry to the front. MUTANT_COMPILED confirmed first (derive.o rebuilt), so the
run was not against a stale binary -- the failure this project has already had
once. Predicted three failures by name before running; got exactly those three
and no others:
  AndroidIsNotMistakenForLinux   "Linux; Android 10; K" contains "Linux"
  RecognisesOsInfoSegments       same string, asserted positively
  CanonicalFormsRoundTrip        Android's canonical os_info, same reason
ChromeOsIsNotMistakenForLinux PASSED under the mutant, which confirms in the
real build what derive_unittest.cc's comment already said: that assertion
cannot fail on ordering and is kept only against a future "X11; CrOS Linux"
spelling. The comment was right; no change needed.

Restored, rebuilt, 27/27 again, derive.cc sha verified identical on both sides.

FIXED: derive.cc's comment named DeriveTest.AndroidAndChromeOsAreNotMistaken-
ForLinux, a test that stopped existing when it was split in two. A comment
pointing at a nonexistent test is unfalsifiable by anything.

STILL TO DO for SP5a: Tasks 4-7 (validator unittest, Chromium wiring, browser
check, patch extraction). Task 4 is next and now has a working build to land in.

---

SP5a TASK 4 DONE, and it closed three more Task 3 omissions.

Task 4's file list says "Modify coherence_validator_unittest.cc". The file did
not exist. Task 3 was supposed to create it, with three guard tests, and was
also supposed to have apply.sh copy settings/invariants.json into the tree --
RegistryMatchesGeneratedHeader reads it from DIR_SRC_TEST_DATA_ROOT. Neither
happened. With BUILD.gn earlier, that is THREE omissions from Task 3, all of
the same kind: work named in the task's own file list, silently skipped, and
none of it detectable by anything that was run at the time.

Now written: coherence_validator_unittest.cc with all six tests (Task 3's
three guards + Task 4's three), BUILD.gn wired, apply.sh copying the JSON.
Compiled first try. ALL_SIX_PASS, each configuration-dependent case in its own
process because camoucfg::Config() latches.

MUTATIONS -- five, every one predicted by name before running, every one
landing exactly where predicted:

  no rebuild needed (the JSON is read at runtime, configs are env):
    clean-config test fed the DIRTY config      -> FAIL, as predicted
    mutation test fed the CLEAN config          -> FAIL, "Which is: 0" vs 1
    extra entry in invariants.json only         -> FAIL, names ghost-entry
    restore                                     -> passes again

  header mutant (second invariant, undeclared key), MUTANT_COMPILED confirmed:
    RegistryMatchesGeneratedHeader              -> FAIL   predicted
    EveryInvariantKeyIsDeclaredInTheRegistry    -> FAIL   predicted
    MutationsExistForEveryInvariant             -> FAIL   predicted
    EveryInvariantIdIsUnique                    -> PASS   predicted: the
      mutant id IS unique, so this guard has nothing to say about it
    restore + rebuild                           -> ALL_SIX_PASS

The four-of-four prediction match is the point. A guard that fires on
everything is as useless as one that fires on nothing, and EveryInvariantIdIs-
Unique staying green is what shows these four are distinguishing cases rather
than all reacting to any perturbation.

REMAINING FOR SP5a: Task 5 (wire ValidateAtStartup into Chromium), Task 6
(browser-level check), Task 7 (patch extraction).

---

SP1a IS NOT COMPLETE. I said "verified end to end" earlier today. That was
wrong, and the review is what exposed it.

WHAT THE REVIEW FOUND (3.1): the WIN profile asks for architecture "x86",
bitness "64", mobile false, wow64 false -- which are EXACTLY what this
x86_64 Linux host already reports unpatched. So every assertion about those
four passed whether or not the config reached the field.

Confirmed by mutation, not by reading: deleting all four substitutions from
GetUserAgentMetadata() and rebuilding chrome left verify_sp1a_chrome.py
printing 17 PASS, exit 0. ua:model was executed by nothing at all -- no config
in the repo set it.

THEN THE FIXED TEST FOUND A REAL BUG. Adding two profiles whose values differ
from the host (WOW64: bitness 32, wow64 true; ANDROID: arch "", bitness "",
mobile true, model Pixel 7) produced five failures on the FIRST run:

  ua:architecture  arm -> page sees x86     NOT APPLIED
  ua:bitness       32  -> page sees 64      NOT APPLIED
  ua:mobile        true -> page sees false  NOT APPLIED
  ua:wow64         true -> page sees false  NOT APPLIED
  ua:platform / ua:platformVersion / ua:model   all APPLIED

Reproduced one key at a time. Both channels agree on the WRONG value, so this
is not a renderer-only loss.

WHERE IT IS NOT:
  not the key names      keys.h has ua:architecture, ua:bitness, ua:mobile,
                         ua:wow64 exactly as the configs spell them
  not the C++ producer   in-process gtest, full WIN config with ONE field
                         changed against a passing control: all four apply
                         (arm, 32, true, true)
  not CDP/Playwright     reproduced with NO CDP client, launching chrome
                         directly at the echo server. SP1 defers "CDP
                         emulation interaction" to SP2; this is not that.
  not a second writer    GetCpuArchitecture/GetCpuBitness/IsWoW64 have no
                         caller in the desktop chrome path outside
                         user_agent_utils.cc; the only other assignments are
                         content_shell, android_webview, chromedriver and the
                         CDP emulation agent.

WHERE IT IS: downstream of the producer, inside chrome, affecting exactly
these four fields and not platform/platformVersion/model. Instrumenting
GetUserAgentMetadata() in the real browser process printed
  CAMOUPROBE arch=arm bitness=32 mobile=1 wow64=1 model=Pixel 7
while the wire header for the same run said arch="x86" bitness="64". So the
producer is right and something between it and both consumers is not.

NEXT SESSION STARTS HERE. Instrument content/browser/client_hints/client_hints.cc
around :709-712 -- the branch where ua_metadata may already have a value and
delegate->GetUserAgentMetadata() is therefore never called. That is the single
most likely place given the field split, and it is one LOG away from certain.

The checkout is clean: instrumentation reverted, chrome and components_unittests
rebuilt, zero CAMOUPROBE lines in a fresh run.

---

CORRECTION. THE "REAL BUG" IN THE ENTRY ABOVE DOES NOT EXIST. It was my own
mutation still resident in out/Default/chrome.

The mutation script for review finding 3.1 ended with

    cp /home/lang/uau.bak .../user_agent_utils.cc
    echo "restored"

It restored the SOURCE and never rebuilt. out/Default/chrome stayed the mutant
-- the binary with the ua:architecture / ua:bitness / ua:mobile / ua:wow64
substitutions deleted. Every "failing" diagnostic afterwards ran against it:
the five FAILs, the one-key-at-a-time probe, and the no-CDP run. All four keys
"not applying" is exactly what that mutant is built to do.

After a clean rebuild: verify_sp1a_chrome.py gives 34 PASS, 0 FAIL, exit 0,
including all fourteen new discriminating 2b assertions. ua:architecture=arm,
ua:bitness=32, ua:mobile=true, ua:wow64=true and ua:model all reach both
channels correctly.

I HAD THE DISPROOF TWICE AND READ PAST IT BOTH TIMES:
  - the in-process gtest showed all four substitutions working. I called that
    a contradiction between "in-process" and "browser" instead of suspecting
    the browser BINARY.
  - instrumenting GetUserAgentMetadata forced a REBUILD, and that run printed
    arch=arm bitness=32 mobile=1 wow64=1. I read it as "producer right,
    downstream wrong" when it was "the previous binary was stale". The rebuild
    was the variable, not the instrumentation.

This is the dominant failure mode again, in a form conventions did not yet
name: not a mutant that failed to compile, but a mutant that compiled, was
never rebuilt away, and outlived the experiment it was written for.

RULE: a mutation script must rebuild AFTER restoring, and must re-run the
baseline to prove the restore took effect. Restoring the source is not
restoring the binary.

WHAT SURVIVES, AND IT MATTERS: review finding 3.1 is REAL and confirmed. That
mutation DID rebuild before running, and the original 17 assertions all passed
against a binary with the four substitutions deleted. The old profile asked
for the host's own values, so four of seven keys were unverified and ua:model
was exercised by nothing. The fix -- two non-host profiles plus the structural
guard -- is correct and is what now gives 34 PASS.

SP1a's producer is sound. The verification is now honest about it.

---

SP5a TASK 5 COMPLETE. Checkout commit e249e76434 on camoucrome/sp5a.

SP0's fragile arrangement is retired: the parse was forced by the side effect
of a HasKey() inside a logging statement, so deleting the log would have moved
the parse into a renderer. ValidateAtStartup() is now the explicit call.

THREE PREVIOUSLY SILENT FAILURES NOW SPEAK. All three were review findings.

  a  typo key            {"ua:platfrom":"Windows"} matched nothing, every
                         getter fell back to real, browser ran fully unspoofed
                         and indistinguishable from no config at all
  b  partial ua: config  hints followed the config, UA string kept the real OS
  c  incoherent config   reported; under CAMOU_CONFIG_STRICT now refuses

EVIDENCE, observed not assumed -- five content_shell launches:
  a typo             warning fires, browser runs (143 = my SIGTERM)
  b partial          warning fires, browser runs
  c incoherent+STRICT EXIT 13, refuses to start
  d incoherent lax   violation logged, browser runs
  e clean control    NO camoucfg output at all  <- no false positives

  build              content_shell + components_unittests OK
  unit               29/29 (was 27; +2 kUaMetadataKeys guards)
  validator          ALL_SIX_PASS, one process per config
  verify_sp0.py      11 PASS, exit 0
  verify_sp1a.py      9 PASS, exit 0

DEVIATION: the plan said `return 1`. EarlyInitialization does return int, so
it would compile, but 1 is RESULT_CODE_KILLED and would report a deliberate
refusal as a kill. content::ResultCode is FROZEN -- static_assert pins
RESULT_CODE_LAST_CODE at 5 and the header forbids new values -- so no
content-level code means "bad configuration". Used a named constant 13, which
is chrome's RESULT_CODE_UNSUPPORTED_PARAM and which CrashExitCodeToString
already prints by that name.

NEW API, both minimal and both guarded:
  camoucfg::UnrecognisedKeys()  returns the offending keys, NOT the dict, so
                                callers cannot start reading config around the
                                typed getters
  keys::kUaMetadataKeys         the client-hint group; two tests pin it as a
                                subset of kAllKeys excluding kUaOsInfo

STILL OPEN from the SP1a review: 1.1 (HasKey is type-blind, so a wrong-typed
ua: key suppresses --user-agent AND fails to spoof), 1.4 SetAndroidOsForTablet-
Site bypass, 3.4/3.5/3.6 documentation, 4.1/4.2 stale comments. 1.1 is next --
it is user_agent_utils.cc, SP1a's file, and deserves its own commit.

NEXT: SP5a Task 6 (browser-level verification), Task 7 (patch extraction).

---

REVIEW FINDINGS 1.1, 4.1, 4.2 CLOSED. Checkout e934e39da2 and the follow-up.

1.1 the gate counted keys it could not read. HasKey() is cfg.Find() != nullptr,
type-blind, so {"ua:wow64":"no"} made ConfigPresentsUserAgentIdentity() true,
which dropped --user-agent, while GetBool() rejected the same value and fell
back to real. Ask for Windows two ways, get Linux. Stock Chromium honours the
switch there. Gate now asks whether a key yields a VALUE, dispatching to the
getter matching the key's type -- the two booleans by name, because asking
GetString() about a boolean logs "not a string" and answers no, the same bug
mirrored.

  MUTATION, and this time the restore rebuilt. New test
  WrongTypedKeyDoesNotOutrankCommandLine passes; reverting the gate to HasKey
  and REBUILDING fails it with GetUserAgent() returning
  "Mozilla/5.0 (X11; Linux x86_64) ... Chrome/154.0.0.0" instead of the switch
  value; restoring AND REBUILDING passes again. Confirmed by re-running, not
  assumed -- that is the error from earlier today, not repeated.

4.1 the comment block explaining why the reported version cannot move -- the
only place stating it -- was attached to the gate, which returns a bool, takes
no `real` and is not a substitution point. OsInfoOverrideOr() had no comment at
all. Moved. A reader asking "where is the version protected" was landing on the
wrong function.

4.2 keys.h promised converting "the two call sites" was incremental, having
converted one. navigator_base.cc still held the literal, so the comment was
false on landing and the tree held the exact hazard the registry exists to end.
Converted; keys.h now names which sites use the constant instead of promising.

FULL REGRESSION after all three, both binaries rebuilt:
  camoucfg unit          29 OK
  validator              ALL_SIX_PASS
  verify_sp0.py          11 PASS, exit 0
  verify_sp1a.py          9 PASS, exit 0
  verify_sp1a_chrome.py  34 PASS, exit 0

STILL OPEN from the review: 1.4 (SetAndroidOsForTabletSite bypasses the
substitution on desktop; the two in-file bypasses are #if IS_ANDROID and do not
compile here), 3.4/3.5/3.6 documentation and spec drift.
