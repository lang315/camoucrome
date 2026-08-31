# SP4-fonts (Layer 1) surface measurements

Measured 2026-08-31 against the WSL checkout `~/chromium/src` (HEAD `a727b57805`),
read-only. This is **Layer 1** of the font fingerprint — the enumeration-visible
surfaces — per the user's 2026-08-31 scope decision ("Layer 1 now, log 2+3").
Layers 2 (codepoint/system fallback) and 3 (metric jitter) are deferred and
recorded at the end. Reference implementation: Camoufox `patches/font-hijacker.patch`
+ `font-list-spoofing.patch` (same `fonts` config key, same `IsFontAllowed` model,
with the #44 context-awareness lesson already encoded).

## Scope (Layer 1)

Three sub-surfaces, all renderer-side and fully Linux-verifiable:

1. **Local Font Access API** — disable it.
2. **Family-probe blocking** — an unlisted specific `font-family` must never resolve
   to a real host face (so `measureText` width can't distinguish it from a
   fallback); listed families still render.
3. **`document.fonts.check` / `load`** — must answer consistently with (2).

## 1. Local Font Access — `window.queryLocalFonts()`

`third_party/blink/renderer/modules/font_access/window_font_access.idl:12` exposes
`Promise<sequence<FontData>> queryLocalFonts(...)` on `Window`. Gated by the
`FontAccess` runtime-enabled feature (`platform/runtime_enabled_features.json5:3187`,
`status: {"Android": "", "default": "stable"}` — **enabled** on desktop). It is a
permission-gated full enumeration of every installed font — the single
highest-yield font surface, and one Firefox has no equivalent of.

**Disable it** by setting the feature status to `""` (or `"test"`) — `queryLocalFonts`
then becomes `undefined`. This is the spec's cheaper correct answer.

**Tell note (recorded, not blocking):** real desktop Chrome exposes
`window.queryLocalFonts`; removing it is a mild missing-API divergence
(`typeof window.queryLocalFonts === 'undefined'` on a claimed-desktop profile).
Mitigating facts: the API needs a permission prompt + user gesture, so it cannot
enumerate silently, and enterprise policy legitimately disables it. The alternative
— keep the API and return the configured `fonts` list from `query()` — is more work
for a surface that can't fire silently. Disabling was the chosen scope; the
drive-from-list alternative is the upgrade path if the missing-API tell ever
matters.

## 2. Family-probe blocking — the choke

The classic no-permission JS font probe measures `measureText` width for
`font-family: X, monospace` vs `monospace` alone; if `X` is installed the widths
differ. That resolution runs through one cross-platform choke:

**`FontCache::GetFontPlatformData(font_description, creation_params, alternate_font_name)`**
(`platform/fonts/font_cache.cc:155`) is the single resolver behind all three
named-lookup probe vectors:

| Vector | Entry | Routes to |
|---|---|---|
| metric probe (`measureText`) | `FontCache::GetFontData` (font_cache.cc:176) | `GetFontPlatformData` → null ⇒ CSS falls back |
| availability (`document.fonts.check`) | `FontCache::IsPlatformFamilyMatchAvailable` (:198) | `GetFontPlatformData` (non-null ⇒ "available") |
| `local("PostScript name")` (#44 unique-name analog) | `FontCache::IsPlatformFontUniqueNameMatchAvailable` (:207) | `GetFontPlatformData` (kLocalUniqueFace) |

Gating `GetFontPlatformData` to a `fonts` allowlist closes all three **in one
cross-platform place** (unlike Layer 2's fallback, which is per-OS). `CreateFontPlatformData`
below it is platform-specific (skia/win/mac/android); `GetFontPlatformData` is not.

### The gate-point tradeoff (the real design decision for the plan)

Genericness is known at **`CSSFontSelector::GetFontData`** (`core/css/css_font_selector.cc:239`,
`if (!font_family.FamilyIsGeneric())`) but is **lost** by the time the lookup reaches
`FontCache::GetFontPlatformData`: generics are resolved to a concrete
`settings_family_name` (css_font_selector.cc:248) and arrive as ordinary named
lookups. `GetFontPlatformData` also special-cases `system-ui` → `SystemFontPlatformData`
(font_cache.cc:161).

So a naïve "block any named family ∉ allowlist" at `GetFontPlatformData` would also
block the concrete font a generic (`serif`/`sans-serif`/`monospace`) resolved to,
**breaking text rendering** — worse than a fingerprint. Two options:

- **(A) Gate at `CSSFontSelector::GetFontData`** where `FamilyIsGeneric()` is visible:
  block only `!FamilyIsGeneric()` specific families ∉ allowlist; generics pass
  untouched and render. Safe against rendering breakage. BUT it is per-document
  (core) and misses callers that reach `FontCache` directly — the `local()`
  unique-name path (`IsPlatformFontUniqueNameMatchAvailable`) and worker /
  `OffscreenCanvas` font access. Those need companion gates.
- **(B) Gate at `FontCache::GetFontPlatformData`** (one cross-cutting point, covers
  workers + `local()`) but must NOT block generic-resolved or last-resort lookups —
  requires either the allowlist to include the generic-default names or a
  never-block-last-resort escape, or rendering breaks.

**Recommendation for the plan:** primary gate at `CSSFontSelector::GetFontData` on
non-generic families (safe, no render breakage), plus a companion gate on
`IsPlatformFontUniqueNameMatchAvailable` (the `local()` unique-name vector) and a
verified check of the worker/`OffscreenCanvas` path. A "generics still render"
verify criterion is mandatory to catch breakage. The implementer resolves the exact
minimal set against RED/GREEN, mirroring how `font-hijacker.patch` structures its
`IsFontAllowed` chokes. Camoufox does NOT block generics via the allowlist — it
handles generic/system fonts in separate OS-derivation patches (out of Layer-1 scope
here); Layer 1 must leave generic rendering intact, not derive it.

### Resolution (after reading both selectors)

`CSSFontSelector::GetFontData` (css_font_selector.cc:250-255) and
`OffscreenFontSelector::GetFontData` (offscreen_font_selector.cc:38-55, the
worker/`OffscreenCanvas` selector) have the **identical** tail:

```cpp
if (!font_family.FamilyIsGeneric()) {
  if (auto* face = font_face_cache_->Get(...)) return face->GetFontData(...);  // @font-face
}
AtomicString settings_family_name = FamilyNameFromSettings(request_description, font_family);
if (settings_family_name.empty()) return nullptr;
return FontCache::Get().GetFontData(request_description, settings_family_name);  // host lookup
```

So the metric-probe gate is: in **both** methods, immediately before the
`FontCache::Get().GetFontData(...)` call, `if (!font_family.FamilyIsGeneric() &&
!camoucfg::IsFontAllowed(scope, family_name)) return nullptr;`. This is
generic-safe (genericness still known), leaves `@font-face` web fonts untouched,
and editing both selectors covers **window + worker parity** in one design. This
is the chosen Layer-1 gate — option A extended to the worker selector, not the
lower `GetFontPlatformData`.

**Companion — `check()` availability.** `FontFaceSet::check` already `continue`s
on generic families before calling `font_selector->IsPlatformFamilyMatchAvailable`
(font_face_set.cc:271), so that predicate never receives a generic. Gate
`IsPlatformFamilyMatchAvailable` (shared FontSelector level, covers window +
worker `check()`): `if (!camoucfg::IsFontAllowed(scope, family)) return false;`.

**Deferred to fonts-ii — `local("PostScript name")`.**
`IsPlatformFontUniqueNameMatchAvailable` matches by full/PostScript unique name,
not family, so a family-name allowlist can't gate it cleanly (the #44
full/PostScript-name path). It needs `@font-face { src: local(...) }` to reach, is
a niche vector, and is grouped with the Layer-2 deferral.

### Config helper

`kFonts` key (`"fonts:list"`, array of strings) + a small **new** camoucfg accessor
`bool camoucfg::IsFontAllowed(const ConfigScope&, std::string_view family)` —
returns `true` when no `fonts` key is set (rule 5 — every host font visible) or
the family is in the list (case-insensitive). Unlike screen/navigator (which
needed no new accessor), this one earns its place: it encapsulates the rule-5 +
case-insensitive-membership logic used at the two-to-three gate sites and is
unit-testable in isolation (`IsFontAllowedTest`), matching the project's
test-the-primitive discipline.

## 3. `document.fonts.check` / `load`

`FontFaceSet::check` (`core/css/font_face_set.cc:232`) skips a family when
`f->FamilyIsGeneric() || font_selector->IsPlatformFamilyMatchAvailable(...)`
(font_face_set.cc:270-272), then consults the web-`@font-face` cache. Because it
keys off `IsPlatformFamilyMatchAvailable` — which routes through the gated
`GetFontPlatformData` — **`check()` inherits the gate**: an unlisted family becomes
not-platform-available and is answered from the web-font path only. (Note: for a
purely-local unlisted family with no `@font-face`, Chrome's `check()` returns
`true` regardless — it reports web-font *load* state, not local presence — so
`check()` is a weak probe; the metric measure is the real one. Verify anyway.)

`FontFaceSet::load` (font_face_set.cc:193) resolves the style and loads matching
`@font-face`s. Camoufox's `font-hijacker.patch:103` gates `load()` explicitly too;
whether Chromium's `load()` leaks local presence is a **verify target** — assert
`load()` of an unlisted local family behaves like a fallback, and add an explicit
gate only if the verify shows a leak.

## Worker / OffscreenCanvas parity

`FontCache` is process-shared, so a `GetFontPlatformData`-level gate covers workers
automatically; a `CSSFontSelector`-only gate does not (workers use
`font_face_set_worker.cc` + `OffscreenCanvasRenderingContext2D` measureText, which
reach `FontCache` without the window's `CSSFontSelector`). Whichever gate point is
chosen, a **worker measureText parity** criterion is required (a listed font and an
unlisted font measured in a dedicated worker must match the window's answers) — this
is the SP1b/SP3b worker-parity discipline applied to fonts.

## Config

New key **`fonts:list`** (`kFonts`) — an array of strings (family names), read via the existing
`camoucfg::GetStringList(scope, keys::kFonts)`. Colon-namespaced per the naming rule (Camoufox uses bare `fonts`; the convention requires a colon for a synthetic control). The
allowlist match is **case-insensitive** (Camoufox lowercases both sides —
`GetStringListLower`); camoucfg has no lowercasing list accessor, so the gate
lowercases inline (or a small `camoucfg` helper is added — decide in the plan; a
helper is cleaner and testable). Rule 5: **no `fonts` key ⇒ no gate** (every host
font visible, stock behavior).

## The #44 boundary (state it, per project discipline)

The allowlist is a **filter**: visible set = (host fonts) ∩ (configured list). SP4-fonts
implements the filter only. It does **not** guarantee the list is plausible for the
claimed OS, nor that the listed fonts are actually present to render — that is
SP5b (profile generation + packaging/bundled fonts) and the SP5a load-time
validator. On a Linux CI host presenting as Windows, listed Windows fonts are
absent → return null → invisible (a coherent-list-but-no-fonts tell); closing that
is packaging's job, not this filter's. A Linux-only verify proves the filter
mechanism, **not** cross-OS coherence — the #44 lesson #3.

## Deferred (logged), per the Layer-1 scope decision

- **Layer 2 — codepoint / system fallback (fonts-ii).** `FontCache::FallbackFontForCharacter`
  (font_cache.cc:229) → `PlatformFallbackFontForCharacter` (per-OS: skia/win/mac/android),
  driven by `FontFallbackIterator`. Rendering an arbitrary glyph picks a host
  fallback face → leaks host-font presence via the selected face + its metrics.
  **Ungated, platform-specific**, verifiable only on Linux here → its own slice, with
  the Win/Mac reasoning stated explicitly (the #44 hazard).
- **Layer 3 — metric jitter.** Its own SP per spec §7 (Camoufox: 55KB across
  measureText / layout / OffscreenCanvas / graphics). Perturbs the exact glyph
  advances of *listed* fonts so the font file/version can't be fingerprinted.
  Independent of Layer 1's enumeration filter.
