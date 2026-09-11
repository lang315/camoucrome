# Fonts residuals: the metric grid, three clones, five CJK regions, `local()` by unique name

Spec: `specs/2026-09-11-fonts-residuals-design.md`. Plan:
`plans/2026-09-11-fonts-residuals.md`. Everything here was measured on
2026-09-11 against stock Google Chrome 153.0.8010.36 on the build box's
Windows 10 host (build 19045, `scripts/winhost.py`) and the fork's
`out/Default/chrome` on the box with the bundle (`--fonts-dir`).

## 1. Metric grid: presence is not identity, so measure identity

`scripts/capture_font_metrics.py` renders one page on the host
(`--dump-dom`, temp profile): `measureText` of each of 125 characters
(printable ASCII + À…Ý) at **100 px** in 12 claimed families →
`baselines/chrome-8010-stock-font-metrics-windows.json`. At 100 px a
1/100 em difference is a whole pixel, and canvas advances are linear
(unhinted) on both DirectWrite and FreeType, which the control row
confirms. `scripts/verify_font_metrics.py` renders the same page in the
fork under the Windows claim + bundle and compares per family.

| claimed family | fork renders | chars within 0.5 px | max \|diff\| | mean signed | row |
|---|---|---|---|---|---|
| Arial | Liberation Sans | 0.992 | 0.5 px | ≈0 | M1 control PASS |
| Times New Roman | Liberation Serif | 1.000 | 0.4 px | ≈0 | M1 control PASS |
| Courier New | Liberation Mono | 1.000 | 0.0 px | 0 | M1 control PASS |
| Calibri | Carlito | 0.984 | 0.5 px | ≈0 | M2 PASS |
| Cambria | Caladea | **0.360** | **19.4 px** | −1.9 px | M2b numbers only |
| Georgia | **Gelasio** (new) | 0.984 | 0.5 px | ≈0 | M3 PASS |
| Tahoma | **Wine Tahoma** (new) | 0.720 | 1.6 px | — | M4 approximate PASS |
| Segoe UI | Selawik | 0.784 | 1.1 px | +0.002 | M5 approximate PASS |
| Verdana | Selawik (class font) | 0.000 | 36.6 px | −9.5 px | M6 no clone |
| Trebuchet MS | Selawik | 0.024 | 29.4 px | +1.4 px | M6 no clone |
| Consolas | Liberation Mono | 0.000 | 5.0 px (constant) | +5.0 px | M6 no clone |
| Segoe UI Variable | — | — | — | — | absent on Windows 10 (the list agrees) |

Readings:

- **The control row fixes the noise floor at 0.5 px**: three metric-
  compatible-by-design fonts land within half a pixel of the host on
  every character but two. Anything above that is the font, not the
  renderer.
- **Selawik is an approximate clone of Segoe UI, not a presence-only
  one**: every character within 1.1 px at 100 px (1.1 % of em), mean
  signed difference zero. Microsoft's README says "replacement", not
  "metric-compatible"; the number says it is close. Same class for Wine's
  Tahoma (1.6 px). The verify's threshold for these two rows is *every
  character within 2 px* and the row name says "approximate": the
  threshold names what they are, it does not promote them.
- **Caladea's Google Fonts build is not metric-compatible with Cambria
  on this host**: digits differ by 3–19 px (the `1` by 19.4), capitals by
  2–7 px, lower case by up to 5 px; `H`, `I`, `M`, `U` are *wider*. Kept
  (a serif clone with the right lowercase is still the nearest thing
  shipped), reported as a number, not asserted.
- **Verdana, Trebuchet MS, Consolas have no open metric clone**; the
  grid says how far the class font is (Consolas: a constant 5 px, i.e.
  Liberation Mono's 60 vs Consolas's 55 advance). Presence only, as
  before.

## 2. Clones added (manifest `bundle`)

| file | licence | claimed | kept because |
|---|---|---|---|
| Gelasio `Gelasio[wght].ttf` + Italic (google/fonts `ofl/gelasio`) | OFL 1.1 | Georgia (`alias`) | M3 0.984 within 0.5 px |
| Wine `fonts/tahoma.ttf`, `tahomabd.ttf` (gitlab.winehq.org) | LGPL 2.1+ | Tahoma, **by its own name** (the file's family is "Tahoma"; `gen_fontconfig.alias_target` returns a bundled family carrying the claimed name as itself, so it is never an alias key) | M4 1.6 px max |
| `NotoSansCJK-Regular.ttc` (notofonts/noto-cjk `Sans/OTC`, 19,484,784 B) | OFL 1.1 | 69 CJK names in five regions (`script_class.cjk_jp/kr/sc/tc/hk` = 22/13/21/10/3, one target per region) | F9: 骨/直 in "Yu Gothic" differ pixel-for-pixel from "Microsoft YaHei"; RED equal when Yu Gothic is aliased to the SC face |

The digests of the three new downloads were taken on the box (its own
network path) and pinned before the Mac fetched them: the Mac's fetch
must agree. `fetch_fonts.py` now retries a download **direct, still
verified** when the system HTTPS proxy (a local re-signing VPN app on
the Mac) fails certificate verification — the sha256 pins are the gate,
the transport is not.

## 3. Emoji presence by colour (F8)

Width cannot see an emoji font (no Latin glyphs, fallback identical
either way). Colour can: U+1F600 drawn at 32 px in "Segoe UI Emoji"
under the Windows claim + bundle paints **945** coloured pixels
(channel spread > 32); with no bundle the box paints **0** (the RED).
Presence is now measured, not assumed; fidelity to Segoe UI Emoji's
artwork is not claimed.

## 4. `local()` by PostScript / full name (F-PSNAME)

fonts-ii left `local("SegoeUI")` over-blocked: a family allowlist cannot
match a PostScript name, and no host face has it anyway. Closed with
data, no C++:

- `scripts/fontnames.py`: a stdlib OpenType `name`-table reader (IDs 1,
  2, 4, 6; Windows platform, en-US; TTC aware). `capture_fonts_list.py
  --names` runs it on the Windows host (pushed as text through
  `winhost.powershell`, no fontTools there: 151 files, 188 faces) and on
  the Mac (`/System/Library/Fonts`, `Supplemental`, `/Library/Fonts`, the
  FontServices `Reserved` dir where PingFang lives) and writes
  `families.<os>.unique_names` — 348 Windows, 775 macOS names (Regular
  faces' full names included, since `local("Georgia")` is a full-name
  match; Apple's system fonts carry IDs 1/4/6 on the Mac platform only, so
  the reader falls back to platform 1 — Menlo and Helvetica Neue were
  invisible until it did), each with its family and style — plus
  `os_version` / `platform_version` (§5).
- `fetch_fonts.py` records each bundled file's faces; `gen_fontconfig.py`
  derives `unique_map.<os>`: host name → the target family's face full
  name of the same style (`SegoeUI-Bold` → `Selawik Bold`, `ArialMT` →
  `Liberation Sans`, `Tahoma-Bold` → Wine's `Tahoma Bold`). The generator
  emits the unique names into `fonts:list` and the map into
  `fonts:alias`; the existing hook in `FontCache::GetFontPlatformData`
  takes the hop for the unique-name lookup too.
- Rows (`verify_fonts_bundle.py`): **F10 RED**, family-level keys only:
  `local("SegoeUI")` → `error` (the fonts-ii over-block, reproduced).
  **F11**, generator keys: `local("SegoeUI")`, `local("Segoe UI")` and
  `local("SegoeUI-Bold")` load; the loaded faces measure 416 / 416 / 437 px
  against `"Segoe UI"` at 416; `local("Tahoma-Bold")` loads Wine's bold at
  484; `local("Selawik")` and `local("Selawik-Regular")` stay `error`
  (bundle names are never allowed); a dedicated worker's `local("SegoeUI")`
  status equals the page's (`loaded`). The Linux unique-name lookup does
  see the bundle dir through `FONTCONFIG_FILE`. Variable fonts have one
  face, so a bold request for Georgia lands on `Gelasio Regular`
  (recorded, not hidden).

**Review found the first version sampled the one target where a single
map happens to work**, and it did need C++ after all. Two measurements:

1. `local("Georgia")`, `local("Calibri")`, `local("Symbol")` → `error` on
   the fork while stock Windows loads every installed family by its full
   name. The hop landed on the *family* ("Gelasio"), and the unique-name
   lookup matches full and PostScript names only; Gelasio's Regular face
   is "Gelasio Regular" (Carlito, Caladea, Noto Sans Symbols 2 likewise).
   Selawik and Liberation had passed only because their Regular faces are
   named like their families. CSS wants a family, `local()` wants a face
   name, and one dict keyed by "Georgia" cannot hold both.
2. With the unique names in `fonts:alias` (or merely in `fonts:list`),
   `font-family: "ArialMT"` / `"SegoeUI"` / `"TimesNewRomanPSMT"` resolved
   on the fork; on stock Windows (measured, `--dump-dom`) none of them do.
   The second cause is fontconfig's blank-insensitive family compare:
   "SegoeUI" ≡ "Segoe UI" fires the strong alias, so any unique name that
   passes the CSS allowlist resolves as its family.

Fix, measured: a second map, **`fonts:aliasLocal`** (85th key), read by
the `FontCache` hook only for `kLocalUniqueFace` lookups; `fonts:alias`
stays the family map. The `local()` gate in `LocalFontFaceSource` allows
a name that is in `fonts:list` *or* a key of the local map, so
`fonts:list` holds families only (the generator no longer adds unique
names to it). The manifest's `unique_map` keeps identity entries (Wine's
"Tahoma", "Tahoma Bold") because its keys are what the gate allows; the
one-hop guard makes an identity a no-op. The 15th invariant
`fonts-alias-local-requires-list` is the local twin of the 14th. Rows:
F11 now covers Georgia / Calibri / Symbol (411 / 373 / 524 px, loaded),
**F12** keeps the three PostScript names unresolved as CSS families
(RED twice, both recorded above). fonts-ii's six rows still pass.

**macOS is the other way round, measured.** Stock Chrome 151 on the Mac
(headed, small app window; headless hangs on this Mac) resolves
`font-family: "HelveticaNeue-Bold"` / `"HelveticaNeue"` / `"ArialMT"` /
`"Menlo-Regular"` as CSS families and loads every `local()` name tried;
Blink's `font_matcher_mac.mm` `MatchFontFamily` falls back to
PostScript-name matching by design. So the manifest records
`ps_names_are_css_families` per OS (Windows false, macOS true, each with
its measurement), and for a macOS claim the generator adds the unique
names to `fonts:list` and to `fonts:alias` (mapped to the family target:
`HelveticaNeue-Bold` → `Inter Variable`; a bold PostScript name lands on
the family's Regular through CSS, recorded as a fidelity gap). Rows:
**F13** the three PostScript names resolve under the macOS claim;
**F11-mac** `local()` of five macOS names loads, Inter's own names error,
worker status equals the page's. `verify_fonts_bundle.py` **15/15** on
the box and in archive mode against the sixth cut (no C++ changed for the
macOS side).

## 5. The claim follows the list

A family list is a fact about one OS version. The manifest now records
where each was captured (`Windows 10.0.19045` → UA-CH `platformVersion`
`"10.0.0"`, read from stock Chrome's `getHighEntropyValues` on the host,
not from a table; macOS `15.7.4` → `"15.7.4"` by `sw_vers`, because this
Mac's Chrome 151 hangs headless), and `gen.fonts_keys` emits
`ua:platformVersion` from it whenever it emits `fonts:list`, overriding
the pool's value. Trade-off named: every generated Windows identity is a
Windows 10 identity until a Windows 11 host is captured (Windows 11 adds
Segoe UI Variable and Segoe Fluent Icons, which the Windows 10 list
rightly lacks).

## 6. Verification (box, `out/Default/chrome`, 2026-09-11)

| what | result |
|---|---|
| `verify_font_metrics.py` M1–M5 | 5/5 (table in §1; M2b/M6 as notes) |
| `verify_fonts_bundle.py` F1–F13 with REDs | 15/15 (F2 116/116, F3 180/180, F6 parity, F7 cycle, F8 945 px / RED 0, F9 JP≠SC / RED equal, F10 RED, F11 six names, F11-mac five names, F12, F13) |
| `verify_fonts_ii.py` | 6/6 (the local() gate still refuses an unlisted family) |
| `verify_sp6b_generator.py` N=10 | 36/36: 30 generated configs across 3 OSes with zero `camoucfg:` lines under strict, 5 Z rows, RED |
| `run_coherence_tests.sh` | 7/7, 15 mutations |
| `test_fonts.py` + `test_gen.py` | 26 passed; `gen_fontconfig.py --check` PASS |
| archive | sixth cut (relinked for the local map): packaging doc §3 |

## 7. Closed by fact

- **macOS build**: the Mac has 47 GiB free (`df -h /`), no depot_tools; a
  checkout plus a component out dir needs ≥ 120 GiB. Not started. This
  also blocks "Windows/macOS hosts get no alias layer": there is no host
  build to measure.
- **WebGL profile DB**: the Mac's Chrome is still 151.0.7922.138; the
  macOS profile's 153 re-capture waits for it. No third GPU is reachable
  (the host's Edge 152 shares the Intel UHD 630; WSL has SwiftShader).
- **Hinting / anti-aliasing posture**: out of scope by reasoning. Without
  the real font file, pixel identity is unreachable; the metric grid is
  the whole honest measure.
- **`fonts-alias-requires-list`**: the validator reports and never
  repairs (its header static-asserts it). Strict aborts, non-strict logs
  and the bundle names resolve. The generator never emits that shape.
- **Alias is one hop**: design; chains unsupported.
