# fonts-ii — `@font-face { src: local() }` gating (Layer 1 residual)

Date: 2026-09-06. Source: sp4-fonts whole-branch review "Known Layer-1 tell"
(`2026-08-31-sp4-fonts-surfaces.md` §"Known Layer-1 tell", §"Deferred to
fonts-ii"). Scope decision (user, 2026-09-06): **local() family gate only** —
codepoint/system fallback and the PostScript-name path are residuals.

## The leak

sp4-fonts gates the direct probe (`measureText`) at
`FontFallbackList::GetFontData` with the `fonts:list` allowlist. But
`@font-face { src: local(X) }` resolves through a **separate** path —
`LocalFontFaceSource::CreateFontData` calls `FontCache::GetFontData(...,
kLocalUniqueFace)` **directly**, upstream of `FontFallbackList`, so the sp4-fonts
gate is never reached. Result: for a host font present-but-not-on-`fonts:list`,
the direct method reports it **absent** while `local(X)` reports it **present** —
a **cross-method inconsistency no stock browser produces**. A page running both
concludes a font-blocking modification is active: a positive "anti-detect tool"
signature, arguably worse than the raw leak it half-closes.

## Feasibility (measured on the WSL content_shell, current binary)

The sp4-fonts doc warns a Linux-only verify is "structurally blind" to this tell
— but that is about *Windows* font lists on Linux. Using a font the Linux host
actually has makes the mechanism observable here. `fc-list` shows DejaVu Sans /
Lato / Nimbus / Noto present. Probe via `FontFace.status` after `load()`:

| config | `local("DejaVu Sans")` | meaning |
|---|---|---|
| no `fonts:list` | `loaded` | local() resolves the box font |
| `fonts:list=["Lato"]` | **`loaded`** | **the leak — excluded font still resolves (RED baseline)** |
| no `fonts:list`, `local("DejaVuSans")` | `loaded` | PS name resolves too (residual, below) |

`FontFace.status` is a clean binary discriminator (`loaded` vs `error`).
`document.fonts.check()` is **not** usable — per spec it returns `true` for both
loaded and errored, so a check()-based verify goes green for free
(`2026-08-31-sp4-fonts-surfaces.md` §3).

## The gate

Two edits in `third_party/blink/renderer/core/css/local_font_face_source.cc`
(a `patches/` file; `core/css` already deps `//components/camoucfg` and the blink
`DEPS` already grants `mask_config.h` + `blink_scope.h`, so no BUILD.gn/DEPS
hunk). Both apply the same `fonts:list` allowlist the direct path uses, keyed on
`font_name_` (the `local(...)` argument):

1. **`IsLocalFontAvailable`** — return `false` when `!IsFontAllowed(font_name_)`,
   before the `IsPlatformFontUniqueNameMatchAvailable` call. This covers (a) the
   source-availability decision at `css_font_face.cc:259` (an unlisted local
   source is skipped → `FontFace.status` becomes `error`), and (b) the resolved
   path in `CreateFontData`, because `IsValid() == IsLoading() ||
   IsLocalFontAvailable(...)` and the `!IsValid()` early return then fires.
2. **`CreateFontData`** — the same guard again, placed **after** the
   `probe::LocalFontsEnabled` hook (SP0 rule: config applies after the probe) and
   **before** the `IsValid() && IsLoading()` block. This is the one state edit 1
   cannot reach: when the unique-name lookup is still async
   (`IsLoading()==true`), `IsValid()` short-circuits to true **without** calling
   `IsLocalFontAvailable`, so the block below would hand back a visible loading
   fallback for a font we mean to hide.
   **Defensive-by-reasoning, not measured here** (whole-branch review finding):
   a gate-1-only build — edit 2 removed — was rebuilt and re-run, and it still
   passes every verify case (6/6), because on the Linux/fontconfig verify host
   the unique-name lookup is synchronous so `IsLoading()` is never true. Edit 2's
   branch is exercised only where the lookup is async (Android GMSCore, the
   Windows font service); it is kept as correct defense for those platforms but
   is a **residual** on the "measured" axis (see below), not a verified path.

Scope: `camoucfg::ScopeFor(font_selector_->GetExecutionContext())` (a real
context is in hand). `font_selector_` is constructor-injected
(`font_face.cc:990`, non-null, mirroring the `RemoteFontFaceSource` branch beside
it) and is already dereferenced unconditionally by the pre-existing
`probe::LocalFontsEnabled` call in `CreateFontData`, so non-null is an existing
class invariant the new `IsLocalFontAvailable` deref relies on, not a new
assumption. No new key — reuses `fonts:list` and `IsFontAllowed`. `local()`
never carries a generic family, so no generic-rendering concern.

Only functional caller of `IsPlatformFontUniqueNameMatchAvailable` in the
renderer is this class, so the unique-name availability leak is fully covered by
edit 1 — verified by enumeration, not assumed.

## Verify (RED-first, all Linux, `scripts/verify_fonts_ii.py`)

`FontFace.status` after `load()` settles:

- **F-LEAK** (core): `fonts:list=["Lato"]` + `local("DejaVu Sans")` → RED
  `loaded` on the pre-change binary, GREEN `error` after.
- **F-LISTED** (mandatory anti-overblock): `fonts:list=["DejaVu Sans","Lato"]` +
  `local("DejaVu Sans")` → `loaded` both before and after. A gate that kills
  every `local()` is a bigger tell than the leak.
- **F-STOCK** (rule 5): no `fonts:list` → `loaded` (no-op).
- **F-WORKER** / **F-WORKER-LISTED** (parity, both halves): F-LEAK's probe from
  a DedicatedWorker → `error`, and a *listed* family from a worker → `loaded`.
  The gate is in the shared `LocalFontFaceSource` and `IsFontAllowed`/`ScopeFor`
  ignore the context (single global config), so window/worker cannot currently
  diverge; both halves are asserted rather than only the excluded one so the
  claim is measured, not merely reasoned.
- **F-DIRECT** (sp4-fonts regression): `fonts:list=["Lato"]`, `measureText` of
  `"DejaVu Serif", monospace` equals bare `monospace` (DejaVu Serif is not the
  box `sans-serif` default, avoiding that confound).

Residual **measurement** (not pass/fail): F-PSNAME — `fonts:list=["DejaVu Sans"]`
+ `local("DejaVuSans")` → `error` after the fix. That is the over-block: a listed
font probed by its PostScript name is hidden, because a **family** allowlist
cannot match a PS name. Recorded as a number, not reasoned about.

## Residuals (stated, per #44 discipline)

- **PostScript/full-name over-block.** `local("PostScript name")` of a *listed*
  font is over-blocked (F-PSNAME). Closing it needs a name→family resolution the
  family allowlist model does not have (`IsPlatformFontUniqueNameMatchAvailable`
  matches by unique name). The #44 name path; deferred.
  **Closed 2026-09-11** (`2026-09-11-fonts-metrics.md` §4): the captured
  hosts' full/PostScript names ride in `fonts:aliasLocal`, whose keys the
  gate here also allows, landing on a bundled face's full name.
- **Codepoint / system fallback.** `SystemFindFontForChar` / `GlobalFontFallback`
  / `CommonFontFallback` remain ungated — per-OS platform code, host-sensitive, a
  Linux measurement proves nothing (roadmap fonts-ii HIGH-risk item).
- **Async-loading branch unmeasured.** Edit 2's `IsLoading()==true` path (above)
  is defensive-by-reasoning: the sync-lookup verify host never enters it, and a
  gate-1-only build passes 6/6. It needs an async-unique-name-lookup host
  (Android GMSCore, the Windows font service) to exercise — the same
  Windows/macOS harness the roadmap already demands.
- **Cross-platform completeness.** F-LEAK proves the *mechanism* honors the list
  on a font the host actually has. It proves nothing about whether a Windows list
  hides every Windows host font — that needs the Windows/macOS harness the
  roadmap demanded. The #44 boundary is unchanged.
