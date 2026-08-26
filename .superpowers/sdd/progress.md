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

