# CLAUDE.md

Guidance for Claude Code (and any agent) working in this repository.

## What this is

Camoucrome is an anti-detect fork of **Chromium** — the Chromium counterpart to
[Camoufox](https://github.com/lang315/camoufox) (a Firefox fork). This repo is
**not the Chromium source**. It is a change set — whole new files in `additions/`
plus diffs in `patches/` — that `scripts/apply.sh` lays onto a pristine Chromium
checkout to produce a fingerprint-spoofing browser.

The change set is generated against Chromium revision **`a727b57805`** (an early
subset was first cut against `0e8d4a9268`, then rebased). Rebasing onto a newer
revision is SP6a's job.

## The defining constraint (never violate)

**All fingerprint spoofing is implemented in C++ at the Blink/browser level,
never by injecting JavaScript into the page.** A page must not be able to observe
that a value was substituted:

- Accessors keep reporting `[native code]` (`...get.toString()` unchanged).
- `Object.keys(window)` is byte-identical to a stock build.
- A surface exposed to both a window and a worker reports identical values in
  both (worker parity — see conventions rule 3).

If a surface can only be reached from JS, say so and treat it as an open problem;
do not quietly inject. This is inherited from Camoufox and is the whole reason
the project exists.

## Read first

- **[`docs/superpowers/specs/00-conventions.md`](docs/superpowers/specs/00-conventions.md)**
  — the authoritative architecture decisions every spec assumes. Non-negotiable
  rules, the config API shape, the build environment, and (most importantly) the
  catalogue of ways a check can report success while measuring nothing. Read it
  before writing or verifying anything.
- **[`docs/superpowers/plans/2026-09-02-followon-roadmap.md`](docs/superpowers/plans/2026-09-02-followon-roadmap.md)**
  — the ordered/scoped list of remaining slices (the `-ii` residual closers and
  the two high-risk deep-surgery items).

## Repository layout

| Path | Contents |
|---|---|
| `additions/` | whole new files, **copied** into the Chromium tree verbatim (esp. `additions/camoucfg/` — the C++ config layer) |
| `patches/` | diffs against files that **already exist** in Chromium |
| `settings/` | `invariants.json` (cross-surface invariant registry, SP5) and `build-args.gn` (canonical GN args, incl. the proprietary-codec pair) |
| `scripts/` | `apply.sh` (the applier) and `verify_*.py` (per-slice browser verifications) |
| `docs/superpowers/{specs,plans,measurements}/` | design specs, implementation plans, and per-slice surface measurements |
| `baselines/` | regenerable, build-host-local stock reference captures (git-ignored; not committed) |

New files go in `additions/`, edits to existing files go in `patches/`. This
split (from Camoufox, held across ~64 patches) keeps rebase conflicts confined to
the small diffs.

## The config layer (`//components/camoucfg`)

One GN target reachable from the browser, renderer, and GPU processes. Blink
reaches it through **per-header** `+components/camoucfg/<header>.h` grants in
`third_party/blink/renderer/DEPS` (least privilege; a new header needs a new
line).

- **Getters** — `GetString/GetUint32/GetInt32/GetDouble/GetBool(scope, key)` →
  `std::optional<...>`. Every getter takes a `ConfigScope` first arg. Get it with
  `camoucfg::ScopeFor(execution_context)` (or `ScopeFor(nullptr)` off the main
  thread); today every scope resolves to the same process-global config, parsed
  once into a `base::NoDestructor<base::DictValue>` (immutable after parse, so
  worker/render-thread reads are safe). **Never write a getter that omits the
  scope.**
- **Keys** live in `additions/camoucfg/keys.h` as `constexpr char[]` constants.
  Adding a key is a **triple edit that must stay consistent**: (1) the `k…`
  constant, (2) the `kAllKeys` array plus its `std::array<…, N>` size, (3) the
  `declared` set in `keys_unittest.cc`. A dropped entry fails the unit tests.
- **Naming** — a **dot** mirrors a JS property path exactly
  (`navigator.userAgent`, `window.outerHeight`); a **colon** names a synthetic
  namespace (`canvas:seed`, `webGl:renderer`). A value derived from another gets
  **no key** (an independent override only creates incoherence).
- **The SP0 hook pattern** — read the real value first; apply the config override
  only when the key is present; no-op when absent (conventions rule 5). Fall back
  to the real value, never a hardcoded placeholder. Apply configuration **last,
  after any `probe::Apply*Override` hook**, so the configured value wins without
  breaking DevTools emulation (never delete a probe call).

## Build & verify

Chromium builds on the user's Windows PC inside **WSL2 (Ubuntu 24.04)** as
non-root user `lang` at `~/chromium/src`, out dir `out/Default`
(`is_component_build=true`, `symbol_level=0`), so an incremental rebuild after one
Blink file is 1–3 min. The verification target is **`content_shell`** (small,
still exposes the DevTools protocol), not `chrome`.

- Apply the change set: `scripts/apply.sh <chromium-src>` (copies `additions/`,
  then `git apply --3way` each patch in the explicit, semantic order in the
  script — not alphabetical).
- Browser verifications are `scripts/verify_*.py`, run under
  `~/camoucrome-verify/venv/bin/python3` (bare `python3` lacks `playwright`).
  They drive `content_shell` over CDP via `lib_shell.session(config, [js...])`.
- Unit tests: the `components_unittests` target (`--gtest_filter='Camoucfg*'`
  covers only a subset — filter deliberately, see below).

**`content_shell` is not a complete browser, and the gap is load-bearing.**
Anything under `//chrome` is absent (`window.chrome` has no installer linked).
Worse, it sometimes **reimplements** a surface rather than omitting it —
`GetUserAgentMetadata()` is rebuilt in shell code with `platform="Unknown"` and
never calls the patched `embedder_support` producer, so a patch there is
invisible in `content_shell`. Before planning a verification, confirm the binary
under test actually **calls the function being patched** (grep the patched
symbol's callers, not the feature name).

## The dominant failure mode: a check that measures nothing

This is the project's most expensive class of bug — read 00-conventions.md's
table of them. The discipline:

- **RED-first.** Before trusting a verification, make it **fail on purpose** and
  confirm it says so. A GREEN run carries almost no information until you know
  what it measured. Assert the **expected count** or the **expected failure**, not
  just exit 0.
- **A precise comment beside an imprecise guard is a defect report.** The cheapest
  detector found here is reading a fix's own comment against the fix.
- **Read the brief against the tree before running anything** — the cheapest place
  this project finds defects.
- Confirm the build reports **NON-ZERO steps**; a stale `.o` gives a silent
  0-step no-op with stale results.

## Working with patches (traps that cost real time)

- **Revising a patch must re-extract EVERY path the original touched** — including
  its `BUILD.gn` dep line. Dropping a `//components/camoucfg` dep from a re-cut
  patch passes every green signal (the checkout already had the dep) and only
  fails on a fresh `apply.sh` + `gn check`.
- **To extract just your new edits when the file already belongs to an earlier
  patch:** snapshot the pre-edit worktree with `BASE=$(git stash create)` (no
  branch change), edit, then `git diff $BASE -- <files>` — this excludes the
  earlier patch's hunks. Gate the result: the earlier patch's added lines must not
  reappear in yours.
- **Round-trip every patch before trusting it:** revert the whole touched
  directory to pristine (`git checkout HEAD -- <dir>/`), `git apply --3way` the
  full patch sequence, then `gn check` the target ("Header dependency check OK"),
  rebuild, and re-run the verify. A single-file re-extraction can silently drop a
  cross-file dep.
- Two git behaviours mislead: `git apply --3way` **stages** its result, so
  `git diff --stat` reads empty afterwards — use `--cached`. And
  `git checkout -- <file>` reverts to the **staged** version if staged — use
  `git checkout HEAD -- <file>` for pristine.
- **Neither `gn check` nor `checkdeps.py` runs on a `.cc`-only build.** Run both
  explicitly whenever a change adds a cross-component include; a green build is not
  evidence.

## Non-negotiable rules (from 00-conventions.md §"Non-negotiable rules")

1. No JavaScript injection into page-visible scopes.
2. Native-looking accessors; `Object.keys(window)` unchanged vs stock.
3. Worker parity for any surface exposed to both.
4. **Coherence over coverage** — a spoofed value that contradicts another spoofed
   value is worse than not spoofing at all. SP5's invariant registry
   (`settings/invariants.json`) exists to catch these; extend it when a slice adds
   a numeric-range or cross-surface key.
5. Fall back to the real value when config is absent (with the behavioral-spoof
   refinement and the fail-closed exception noted in the conventions).

Bad config must never crash a renderer — a crash is itself a fingerprint.
