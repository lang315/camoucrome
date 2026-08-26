# SP6 — Build system, packaging, and driver API

## 1. Goal

SP6 turns a patched Chromium checkout into something other people can install and
drive. It defines how source modifications are stored and replayed, how the fork stays
current with an upstream that moves every four weeks, how binaries are produced for
each target platform, how they are packaged, how a client configures and launches
them, and how the spoofable-key registry stays consistent between the C++ that reads
keys and the client that writes them. Without SP6 the work in SP0–SP5 exists only as
uncommitted edits inside one developer's WSL2 home directory.

## 2. Depends on

Nominally on all of SP0–SP5, but the dependency is uneven and SP6 should not be
deferred to the end as a single block.

The patch-management and version-pinning parts (§4.1, §4.2) are needed **immediately
after SP0**, because the moment SP0's first commit exists in `~/chromium/src` it is at
risk: `gclient sync` will rewrite that tree, and there is no backup. These parts have
no real dependency on later SPs and should land alongside SP0.

The key registry (§4.6) is needed **before SP1**. SP0 deliberately deferred it, but
SP1 introduces the first configuration keys that a client must generate, and every key
added without a registry is a future drift bug.

Packaging (§4.4) and the driver API (§4.5) genuinely depend on SP1–SP5, because there
is nothing worth distributing until several surfaces are spoofed coherently. Cross-
platform builds (§4.3) depend on nothing technically but consume a large amount of
machine time, so they should be attempted once early — to discover the toolchain
problems while the patch stack is small — and then not again until release.

## 3. Deliverables

SP6 controls no page-visible values, so the conventions' surface table does not apply
literally. The equivalent inventory is of build artifacts and the code that produces
or consumes them.

| Deliverable | Location | Produced by | Consumed by |
|---|---|---|---|
| Upstream pin | `upstream.env` | Human, per rebase | Every script |
| New-file tree | `additions/` | Human | `scripts/apply.sh` |
| Exported diffs | `patches/` | `scripts/export.sh` | `scripts/apply.sh`, review |
| Key registry | `settings/keys.json` | Human, per new key | Codegen + client |
| Generated key constants | `out/gen/components/camoucfg/keys.h` | GN action | All C++ call sites |
| Generated client table | `client/_keys.py` | Same GN action, or a mirror script | Client validation |
| Linux binary archive | `dist/camoucrome-<ver>-linux-x64.tar.xz` | WSL2 build + `scripts/package.py` | Users |
| Windows binary archive | `dist/camoucrome-<ver>-win-x64.zip` | Native Windows build + packager | Users |
| macOS binary archive | `dist/camoucrome-<ver>-mac-<arch>.tar.xz` | Mac build + packager | Users |
| Runtime file manifest | `out/Default/chrome.runtime_deps` | GN `--runtime-deps-list-file` | Packager |

## 4. Design

### 4.1 Patch management: no bespoke patcher

**Recommendation: plain git branches as the source of truth, `git format-patch` for
export, and a small `additions/` copier. Do not port `scripts/patch.py` or
`scripts/developer.py`.**

Camoufox needs a bespoke patcher for a reason that does not apply here. Its pipeline
downloads a Firefox source *tarball*, extracts it, and then `git init`s the result to
get a workspace it can tag and reset. There is no upstream history, no remote, and no
rebase machinery — so `patch.py` (LibreWolf-derived) and the `make edits` UI exist to
simulate what git would have given for free. The `unpatched` / `first-checkpoint` /
`checkpoint` tags are a hand-rolled substitute for branches.

A Chromium checkout is different in kind. `fetch chromium` produces a real git
repository with a real remote, real history (even with `--no-history`, `git fetch
--unshallow` recovers it), and working `rebase`, `cherry-pick`, `bisect`, and
`format-patch`. Reimplementing a patch stack on top of that would discard the one tool
genuinely good at maintaining a patch stack against a moving upstream.

The workflow is therefore:

- A branch `camoucrome/main` in `~/chromium/src` holds every modification as ordinary
  commits. This branch is the source of truth while developing.
- One commit per logical change, with a subject prefix naming its SP
  (`sp1: drive navigator.platform from config`). Commit granularity matters here in a
  way it usually does not, because each commit becomes a separately rebasable unit.
- `scripts/export.sh` runs `git format-patch` from the pinned upstream commit to the
  branch tip, writes the result into `patches/`, and separately copies any file that
  did not exist upstream into `additions/` (detected as files added by the range, so
  the split is derived, not maintained by hand).
- `scripts/apply.sh` does the inverse on a fresh checkout: verify `HEAD` matches
  `upstream.env`, copy `additions/` into the tree, then `git am` the `patches/` series.

Two Chromium-specific wrinkles the scripts must handle. First, `gclient sync` moves
`src` to the pinned revision and will refuse or clobber depending on local state, so
`apply.sh` must run *after* sync and `export.sh` must record which upstream commit the
patches apply to. Second, DEPS-managed directories under `third_party/` are separate
git repositories whose contents `gclient` overwrites; a patch landing inside one will
be silently reverted on the next sync. **All Camoucrome changes must live in `src`
itself.** If a change to a DEPS-managed third-party project ever becomes necessary, it
needs its own vendoring strategy, and that should be treated as a design change rather
than absorbed quietly.

The `additions/`-versus-`patches/` split is retained from Camoufox because it earns
its keep for a different reason here — see §4.2.

### 4.2 Version pinning and rebase survival

`upstream.env` records the pinned upstream as a **commit hash plus the branch it came
from**, not a version string alone. A milestone tag is not sufficiently precise: the
same milestone number spans many `src` commits, and DEPS changes between them.

**Track a release branch, not `main`.** Chromium's `refs/branch-heads/<N>` branches
receive security and stability fixes but almost no refactoring, whereas `main` takes
hundreds of commits a day, many of them into exactly the Blink internals this project
patches. Rebasing a patch stack onto `main` weekly would consume most of the available
engineering time. Pinning to a release branch and moving one milestone at a time —
roughly every four weeks — converts continuous conflict into a scheduled, bounded
task.

**The conflict-minimisation rule is the important part of this section.** Every edit
to a file that already exists in Chromium is a future merge conflict; every file that
only exists in `additions/` is not. So each spoofing change should be structured as:
all logic in a new file under `additions/`, and a patch to the existing file that is
as close to three lines as it can be — an include, and a guarded call site that
consults config and otherwise falls through to the original expression.

SP0's design already follows this shape, which is why it is worth stating as policy
rather than as a preference. Camoufox is the cautionary example: its largest
non-Playwright patch, `anti-font-fingerprinting.patch`, is 55KB spread across
`measureText`, `layout/generic`, `layout/mathml`, `OffscreenCanvas` and `gfx/thebes`.
Every one of those touch points is a conflict on every upstream rebase, forever. A
Chromium equivalent written the same way would be unmaintainable at Chromium's rate of
change.

The health metric to track is therefore **total lines in `patches/` that modify
existing files**, reported by `export.sh`. It should stay small and roughly linear in
the number of spoofed surfaces. A patch to an existing file exceeding about thirty
lines should be treated as a design smell and reviewed for whether the logic can move
into `additions/`.

A rebase drill belongs in the verification set (§6.7) so the cost is measured rather
than assumed.

### 4.3 Cross-platform builds: Camoufox's model does not port

This is the sharpest architectural difference between the two projects and it must not
be glossed over.

Camoufox cross-compiles Windows and macOS binaries from a single Linux host;
`multibuild.py --target linux windows macos --arch x86_64 arm64 i686` is a supported
path. **Chromium cannot do this.** A Windows build requires a Windows host with Visual
Studio 2026 (≥ 18.0.0), the "Desktop development with C++" workload including MFC/ATL
support, and Windows 11 SDK 10.0.28000.2270. The toolchain package that would make a
Linux-hosted Windows build possible is Google-internal; external contributors must
supply their own Visual Studio installation, on Windows. A macOS build likewise
requires macOS with Xcode and the matching macOS SDK.

There is therefore no single-host build. The replacement is a per-platform builder
model:

| Target | Host | Notes |
|---|---|---|
| Linux x64 | WSL2 (Ubuntu 24.04) on the Windows PC | Already working; the development target |
| Windows x64 | The same PC, natively | Needs its own checkout, its own depot_tools, VS 2026 |
| macOS arm64 | The Mac | Needs Xcode and ~150GB |
| Linux arm64, Windows arm64 | Not planned | See open decisions |

Three consequences of the hardware follow, and each is a real constraint rather than a
detail.

**The Linux and Windows builds share one physical machine and must be serialised.**
The PC has 8 cores / 16 threads and 32GB of RAM, and `.wslconfig` currently grants WSL2
26GB and all 16 processors. Running a native Windows build concurrently with a WSL2
build would oversubscribe both memory and CPU and make each slower than running them
in sequence. The build scripts should refuse to start one while the other is running
rather than leaving this to discipline.

**Disk must be planned before the Windows checkout is created.** A second full
checkout needs roughly 100GB plus 50GB for Visual Studio, and Chromium's Windows
instructions additionally require NTFS (FAT32 fails because some git packfiles exceed
4GB). After the cleanup performed in this session `C:` has about 69GB free, which is
not enough. The Windows checkout belongs on `D:`, which has roughly 870GB free.

**Total wall-clock for a full three-platform release is on the order of a working
day.** The measured Linux `content_shell` build on this machine ran past 28,000 of
43,555 targets in 1h36m; a full `chrome` target is substantially larger, and Windows
and macOS builds are separate multi-hour runs on their own hosts. Release builds
cannot use `is_component_build=true`, which removes the incremental advantage that
makes development iteration fast.

**On CI: not yet, and the reason is disk rather than money.** GitHub-hosted runners
provide on the order of 14GB of free disk on the standard images — an order of
magnitude short of Chromium's 100GB requirement — so the free tier is not merely slow
but unusable. The realistic options are a self-hosted runner (which is the same PC,
solving nothing) or cloud VMs sized at 16+ vCPU with 200GB+ of attached storage,
costing roughly one to three dollars per full build once storage and egress are
included, plus the standing cost of keeping a ccache or Siso cache warm — because
without a warm cache every CI build is a cold build, and a cold Chromium build is
hours.

The recommendation is to build locally and manually until the project has a release
cadence that justifies the setup. Revisit when releases become regular, or when a
second person needs to reproduce a build. Note that the same conclusion does *not*
apply to fast checks: a lint, a `gn gen`, and the key-registry consistency test
(§6.4, §6.5) all run in seconds without a checkout and are worth putting in CI
immediately.

### 4.4 Packaging

Camoufox has `scripts/package.py` and a Go launcher in `legacy/launcher/`. Chromium
changes both halves of that.

**Use Chromium's own runtime-deps machinery rather than a hand-maintained manifest.**
Firefox has `package-manifest.in`, an explicit list Camoufox patches via `config.patch`.
Chromium has no such file, but it has something better: passing
`--runtime-deps-list-file` to `gn gen` makes GN emit the authoritative, transitively
computed list of every file the target needs at runtime. Packaging becomes reading that
list and copying, which is a short script and — more importantly — cannot silently
miss a newly added dependency the way a hand-maintained manifest does.

**Ship a portable archive, not an installer.** Chromium's `mini_installer` (Windows)
and `chrome/installer/linux` `.deb`/`.rpm` targets exist, but they install a browser
system-wide with an updater, file associations, and a default-browser prompt — none of
which an automation tool wants, and some of which are actively hostile to running many
isolated instances. A tar.xz or zip that unpacks anywhere matches how the tool is used
and matches what Camoufox already ships.

**Drop the launcher binary.** Camoufox's Go launcher exists to marshal configuration
and profile selection before exec. With configuration travelling as environment
variables, the client library sets the environment and execs the binary directly; a
separate launcher would be a second thing to build, sign, and keep in sync for no gain.
If a use case for a standalone launcher appears later it can be added, but it should
not be built speculatively.

Two platform details that will otherwise be discovered late. On macOS, distributing an
unsigned browser bundle means users hit Gatekeeper; codesigning and notarisation
require an Apple Developer account and are a prerequisite for anyone but the author
running the macOS build. On Windows, an unsigned executable draws SmartScreen warnings,
which matters less for a tool run from scripts but still matters.

### 4.5 Driver API

**Recommendation: ship no client in SP6's first iteration. Use stock Playwright with
`env=`, and revisit once SP5 exists — at which point extend the existing `camoufox`
package's generator into a shared, target-parameterised core rather than forking it.**

The reasoning has two parts.

*Why nothing now.* Because SP0 kept the environment-variable transport byte-compatible
with Camoufox, a caller can already do everything a minimal client would do:
Playwright's `chromium.launch(executable_path=..., env={...})` sets `CAMOU_CONFIG` and
launches the patched binary. Writing a client before SP5 defines what needs generating
would mean designing an interface around configuration values that do not exist yet.

*Why extend rather than fork, later.* The expensive and valuable part of the `camoufox`
package is not the launching — it is the roughly 2,300 lines of `fingerprints.py` and
`utils.py` that generate a *coherent* fingerprint: `fix_navigator_arch`,
`clamp_window_dimensions`, `clamp_window_position`, `fix_screen_no_taskbar`,
`resample_screen_for_dpr1`, and the OS-derived font, voice and WebGL sampling. That
logic is browser-agnostic in structure even though its *values* are Firefox-specific;
a Chrome target needs Chrome user-agent strings, Chrome-plausible WebGL renderer
strings, and Chrome's font expectations, but the same invariants. Duplicating it into a
second package guarantees the two copies diverge, and the divergence would be in
exactly the coherence logic where a discrepancy is most costly.

The concrete shape, when it is built: a shared generator core taking a target-browser
parameter, with two thin front-ends. Whether those front-ends live in one distribution
or two is a packaging question, not an architectural one, and is listed as an open
decision.

**The interaction with SP2 deserves a stronger statement than "be careful".** The
threat model must be that the browser is safe against a *stock, unmodified* Playwright
client. Playwright's normal operation calls `Runtime.enable`, installs bindings, and
uses `Page.addScriptToEvaluateOnNewDocument` — all of which are detectable from the
page unless SP2 closes them at the browser level. If the design instead relied on a
patched client avoiding certain CDP calls, then every user who reaches for plain
Playwright, Puppeteer, or a raw CDP library silently loses the protection, and the leak
surface becomes a property of client discipline rather than of the browser. Building
no client in SP6's first iteration has the useful side effect of forcing this: with
stock Playwright as the only driver, any leak SP2 fails to close shows up immediately
in testing rather than being masked by a cooperative client.

### 4.6 Key registry

One file, `settings/keys.json`, declares every spoofable key with its type and
constraints. It is the single source of truth, and both consumers are **generated from
it** rather than written against it.

- A GN action runs a generator script at build time, emitting
  `components/camoucfg/keys.h` into the generated-files directory: a `constexpr
  std::string_view` per key, plus a type tag.
- The same generator emits the client's validation table.

Generation is what makes drift structurally impossible, and it is worth being precise
about why, because Camoufox demonstrates both failure modes that a
hand-maintained registry permits.

The first is **keys the C++ reads that no schema declares**. In Camoufox,
`cssMedia:colorGamut`, `cssMedia:dynamicRange`, `cssMedia:prefersColorScheme`,
`screen:orientation`, `screen:orientationAngle` and the `mediaCapabilities:*` keys are
read by C++ but appear in neither `settings/properties.json` nor `settings/camoucfg.jvv`.
A generator does not prevent this by itself — a developer can still pass a raw string
literal — so it needs an accompanying rule: **call sites reference generated constants,
never string literals**, enforced by a presubmit that rejects a string literal in the
key position of any `camoucfg::Get*` call. With that rule, an undeclared key fails to
compile, because its constant does not exist.

The second is **the same key spelled differently in different layers**. Camoufox's
`camoucfg.jvv` declares the voice field as `voiceURI` while `MaskConfig.hpp` and
`fingerprints.py` both read `voiceUri`, so a configuration that validates against the
published schema is rejected by the code that consumes it — and the failure is silent
in the direction that matters, because `MVoices()` skips incomplete entries and the
host's real voices remain exposed. Generating both spellings from one declaration
eliminates this class entirely.

The registry should also carry each key's **owning SP** and a one-line description. The
first is useful when a rebase breaks a surface and someone needs to know which spec
explains it; the second is the documentation, generated rather than written twice.

Type and constraint vocabulary should be kept deliberately small — string, integer with
optional bounds, double with optional bounds, boolean, string list, and a nested-object
escape hatch for the WebGL parameter tables. Camoufox's `camoucfg.jvv` uses a bespoke
JSON-with-validation dialect (`jsonvv`) with regex constraints and `$group` all-or-
nothing coherence groups. The `$group` idea is genuinely valuable and should be carried
across — it is the mechanism that stops someone setting `screen.width` without
`screen.height` — but it belongs to SP5's coherence work, and SP6 should provide the
registry field to express it rather than the engine that enforces it.

## 5. Coherence constraints

SP6 has no page-visible surfaces, so it has no coherence constraints in the usual
sense. It has three consistency obligations instead, and each is a place where a
mismatch produces a fingerprint indirectly.

**The registry must agree with itself across generated outputs.** If the C++ constants
and the client table are ever produced by different code paths, they can disagree, and
a key the client writes but the C++ never reads is a spoof that silently does nothing.
This is checked in §6.4.

**The patch stack must agree with the pinned upstream.** `patches/` applied to any
commit other than the one in `upstream.env` may apply cleanly and still produce
different behaviour, because the surrounding code changed. `apply.sh` verifies the
pin rather than trusting it.

**Binaries across platforms must be built from the same commit.** A release where the
Windows binary contains an SP1 fix that the Linux binary lacks means the two report
subtly different fingerprints, which is worse than either being consistently wrong. The
packager should stamp the source commit into the archive and the packaged binary, and
the release process should refuse to assemble a release from mismatched stamps.

## 6. Verification

1. **Export is idempotent.** On a tree with no uncommitted changes, run
   `scripts/export.sh` twice. `git status --porcelain` in the Camoucrome repo is empty
   after the second run. Failure means the exporter is non-deterministic — usually
   embedded timestamps or unstable patch ordering — and a non-deterministic exporter
   makes every diff review meaningless.

2. **Apply reproduces the branch exactly.** From a fresh `fetch` synced to the commit
   in `upstream.env`, run `scripts/apply.sh`, then
   `git diff --stat camoucrome/main` against the reference branch. Expected output:
   empty. This is the test that the repository, not one machine's home directory, is
   the source of truth.

3. **Apply refuses a mismatched pin.** Sync to any commit other than the pinned one and
   run `scripts/apply.sh`. Expected: non-zero exit and a message naming both the
   expected and actual commit. Expected *not*: a `git am` conflict cascade.

4. **Generated outputs agree.** A test loads `components/camoucfg/keys.h` and the
   generated client table and asserts the two key sets are identical. Seed the test by
   hand-editing one generated file to add a key, and confirm the test fails — a
   consistency test that has never been seen to fail is not known to work.

5. **An undeclared key does not compile.** Add
   `camoucfg::GetString(scope, "navigator.notARealKey")` to any file and build.
   Expected: a compile error, because no such constant exists. Then add the key to
   `settings/keys.json` and rebuild; expected: success. This is the direct regression
   test for Camoufox's `cssMedia:*` drift.

6. **Registry round-trip catches a spelling change.** Rename a key in
   `settings/keys.json` without touching anything else and build. Expected: compile
   errors at every call site referencing the old constant. This is the direct
   regression test for the `voiceURI` / `voiceUri` mismatch.

7. **Rebase drill.** Rebase `camoucrome/main` from the pinned release branch onto the
   next milestone's branch head. Record the number of conflicting files and the number
   of conflicting lines. There is no pass threshold on the first run — the point is to
   establish the baseline before the patch stack grows. On subsequent milestones,
   conflict count growing faster than the number of spoofed surfaces is the signal that
   the `additions/`-over-`patches/` rule (§4.2) is being violated.

8. **Packaged archive runs on a clean machine.** Unpack the archive on a machine that
   has never had a Chromium checkout, launch with
   `CAMOU_CONFIG='{"navigator.hardwareConcurrency":8}'`, and read
   `navigator.hardwareConcurrency` over CDP. Expected: `8`. Launch again with no
   environment variable set. Expected: the machine's real core count. The second half
   matters as much as the first, because it is the test that the fallback path survives
   packaging.

9. **Runtime-deps completeness.** The packaged archive contains every file in
   `chrome.runtime_deps`, verified by comparison rather than by the browser appearing
   to start — a missing locale or ICU data file often produces a browser that starts
   and misbehaves subtly, which in this project means an incoherent fingerprint.

10. **Release stamp coherence.** Given archives for all three platforms, a script
    extracts the embedded source commit from each and asserts they match. Expected on a
    deliberately mismatched set: non-zero exit naming the offending platform.

## 7. Open decisions

**Client packaging: one distribution or two.** Once the shared generator core exists,
`camoufox` and `camoucrome` front-ends could ship as one package with a target
parameter or as two packages depending on a common library. One package is simpler to
keep coherent; two keep release cycles independent and avoid a Firefox-branded package
name being the entry point for a Chromium tool. *Recommendation: two front-end packages
over one shared core library, decided when the core is extracted, not before.* This
does not need answering until after SP5.

**Whether to refactor `camoufox`'s generator in place or extract it.** Extracting the
coherence logic into a shared library means modifying a package that is already
shipping and has users. *Recommendation: extract, but only once Camoucrome has a real
second consumer for it — a refactor with one caller is speculation.*

**ARM targets.** Linux arm64 and Windows arm64 are buildable but need hosts that do not
currently exist in this setup, and macOS arm64 needs the Mac. *Recommendation: macOS
arm64 only, since that host exists; treat Linux and Windows arm64 as out of scope until
someone asks.*

**Code signing.** macOS notarisation requires a paid Apple Developer account; Windows
Authenticode requires a certificate. Both cost money annually and neither is needed for
a tool the author runs from scripts. *Recommendation: defer until there are external
users, and note in the README that unsigned builds will draw OS warnings.*

**Release branch versus milestone tag for the pin.** This spec recommends a release
branch, but a case exists for pinning to `main` at a fixed commit during early
development, when the patch stack is small enough that rebase cost is low and being
close to upstream makes upstream bug reports easier. *Recommendation: `main` at a fixed
commit until SP1 lands, then switch to release branches.*

**Whether `settings/keys.json` should carry validation constraints at all in SP6.**
Types are clearly SP6's concern. Ranges, regexes and `$group` coherence sets arguably
belong to SP5. *Recommendation: SP6 defines the schema fields for constraints so the
file format does not change later, but only implements type checking; SP5 fills in and
enforces the rest.*

## 8. Explicitly out of scope

Fingerprint *generation* — choosing plausible values, sampling real devices, and the
coherence fixups — belongs to SP5. SP6 defines only the transport, the registry, and
the validation of types.

Closing CDP detection vectors belongs to SP2. SP6 states the requirement that the
browser be safe against a stock client, but implements none of it.

The `$group` all-or-nothing coherence enforcement belongs to SP5; SP6 provides only the
registry field in which such groups are declared.

Chromium's own auto-updater, crash reporting, and metrics are not merely out of scope
but should be disabled — they phone home and are themselves a fingerprint. Which
`gn` args and which patches accomplish that is a hardening concern not yet assigned to
an SP, and is flagged here as a gap in the sub-project map rather than claimed by SP6.
