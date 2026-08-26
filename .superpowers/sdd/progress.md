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

