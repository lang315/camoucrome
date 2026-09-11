# Fonts residuals and the open list after the open-items slice — design

Date: 2026-09-11. Source: the residual list at the end of the open-items
slice (`measurements/2026-09-11-fonts-bundle.md` §4, `2026-09-11-webgl-
profiles.md` §4, `2026-09-11-chrome-binary-items.md` §6). The user handed
the list back as the next slice. Each item below is either built, measured
and recorded as a number, or closed with the fact that blocks it.

## 0. Decisions that shape everything

- **Presence is not identity.** The bundle makes claimed families *resolve*;
  a page that measures a glyph's advance width still reads the clone's
  metrics. The only honest closure is a **metric grid**: the same characters
  measured on the real host (stock Chrome 153 on the box's Windows 10 host,
  `winhost.dump_dom`) and in the fork under the Windows claim. What matches
  is reported as matching; what differs is reported as a number, not
  reasoned about.
- **Only open-licence files.** Additions this slice: Gelasio (OFL, Google
  Fonts, designed metric-compatible with Georgia), Wine's Tahoma (LGPL 2.1+,
  the Wine project's `fonts/tahoma.ttf`, name table family "Tahoma") and
  the five-region Noto Sans CJK OTC (OFL, replaces the SC-only OTF). Each
  one stays only if the metric grid or the glyph test says it earns its
  place; a clone that does not match is dropped, not shipped as "presence".
- **Coherence over coverage (rule 4).** A family list captured on Windows
  10 build 19045 is a Windows 10 list; the generator's UA-CH
  `platformVersion` must say Windows 10. Same for macOS 15.7.4. The claim
  follows the list, because the list cannot follow the claim.
- **Blocked is blocked.** The macOS build needs a Chromium checkout and out
  dir (≥ 120 GiB); the Mac has 47 GiB free. Not started, recorded with
  the number. The macOS WebGL re-capture waits for the Mac's Chrome to reach
  153 (still 151.0.7922.138 today). Hinting/anti-aliasing posture is out of
  scope by reasoning, not by decision: without the real font file, pixel
  identity is unreachable, so the metric grid is the whole honest measure.

## 1. Metric grid (`scripts/capture_font_metrics.py`, `baselines/`, `scripts/verify_font_metrics.py`)

**Capture.** One page, `--dump-dom` on the Windows host (stock Chrome 153,
temp profile, headless), then the same page in the fork through the probe
with the Windows config + bundle. For each family in the grid set and each
of 95 printable ASCII code points plus 30 Latin-1 letters, `measureText`
of the single character at **100 px** (large enough that a 1/100 em
difference is a whole pixel; canvas advances are linear, unhinted, on both
DirectWrite and FreeType). Families: Segoe UI, Arial, Times New Roman,
Courier New, Calibri, Cambria, Consolas, Georgia, Verdana, Tahoma,
Trebuchet MS, Segoe UI Variable (Windows 10 has it after 21H2 — the capture
records whether it resolved). Output
`baselines/chrome-8010-stock-font-metrics-windows.json` {family: {char:
width}} plus `resolved` per family (width test: monospace vs serif
fallback, as `verify_fonts_bundle.py`).

**Compare.** `verify_font_metrics.py` loads the baseline, runs the fork
page (Windows claim + `fonts:list` + `fonts:alias`, `--fonts-dir`), and
per family reports: characters measured, characters within 0.5 px of the
host at 100 px (½ % of em), max absolute difference, and the mean signed
difference. A **control row** fixes the noise floor: Arial (host) vs the
fork's Liberation Sans is metric-compatible by design, so its
within-0.5-px fraction must be ≥ 0.98 or the harness is measuring
rendering, not fonts.

Rows (pass/fail only where the design promises equality):
- M1 control: Arial / Times New Roman / Courier New within 0.5 px ≥ 0.98.
- M2 Carlito/Caladea for Calibri/Cambria ≥ 0.98 (metric-compatible by
  design; a miss is a bundle defect).
- M3 Gelasio for Georgia ≥ 0.98 (kept only if it passes; §2).
- M4 Wine Tahoma for Tahoma: reported; kept only if ≥ 0.98 (Wine's file is
  Bitstream Vera renamed with Tahoma's widths claimed; the grid decides).
- M5 Selawik for Segoe UI: **reported, no threshold** (Microsoft's README:
  "an open source replacement for Segoe UI", kerning missing). The number
  is the answer to "Selawik-vs-Segoe metrics unmeasured".
- M6 Verdana, Trebuchet MS, Consolas: reported (no clone exists; the
  number says how far the class font is).

## 2. Clones added (`settings/fonts.json`, `scripts/fetch_fonts.py`)

| claimed | file | licence | how it enters |
|---|---|---|---|
| Georgia | Gelasio `Gelasio[wght].ttf` + `Gelasio-Italic[wght].ttf` (google/fonts `ofl/gelasio`, `urls`) | OFL 1.1 | `alias: Georgia → Gelasio`; family name in the file is "Gelasio" |
| Tahoma | Wine `fonts/tahoma.ttf`, `tahomabd.ttf` (gitlab.winehq.org raw, `urls`) | LGPL 2.1+ (`licence_url` the Wine LICENSE) | the file's family name **is "Tahoma"**: no alias, it resolves by its own name, so `bundle.provides` lists "Tahoma" and `gen_fontconfig.py` must not alias a family to itself (already excluded: bundled names are never keys) |
| Yu Gothic … PingFang HK (69 CJK names) | `NotoSansCJK-Regular.ttc` (notofonts/noto-cjk `Sans/OTC`, 19,484,784 B, replaces `NotoSansCJKsc-Regular.otf` 16 MB) | OFL 1.1 | `provides` the five families; `script_class.cjk` splits into `cjk_jp`, `cjk_kr`, `cjk_sc`, `cjk_tc`, `cjk_hk` by name (Yu/Meiryo/MS Gothic/Mincho/Hiragino/Osaka/Klee/Tsukushi/Toppan → JP; Malgun/Gulim/Batang/Dotum/Gungsuh/Apple SD Gothic Neo/AppleGothic/AppleMyungjo/Nanum → KR; JhengHei/MingLiU/PingFang TC/Songti TC/Heiti TC/Hiragino Sans CNS → TC; PingFang HK/MingLiU_HKSCS → HK; the rest → SC); `class_font` gets one target per region |

A clone that fails its M-row is removed from the manifest before the
slice ships (the manifest is the record; the measurement doc keeps the
number).

**Glyph test for the CJK split (`verify_fonts_bundle.py` F9):** U+9AA8 (骨)
and U+76F4 (直) have different regional forms; render each at 64 px in
"Yu Gothic" (JP claim) and "Microsoft YaHei" (SC claim) onto canvases and
compare pixel data: JP ≠ SC for at least one of the two (RED before the
split: identical, both SC). Not a fidelity claim — a proof the region
mapping reaches the page.

## 3. PostScript / full-name aliasing (F-PSNAME)

`local("SegoeUI")` on a real Windows host loads; in the fork it errors
twice over: the family allowlist holds families, not unique names
(fonts-ii's over-block, F-PSNAME), and even allowed, no host face has that
unique name. The fix uses what exists: **unique names become allowlist
entries and alias keys.**

- **Capture.** `scripts/capture_fonts_list.py` gains `--names`: it reads
  the `name` table (IDs 1, 4, 6, platform 3 / 0x409) of every font file on
  the capture host — Windows via a stdlib parser pushed to the host with
  `winhost.powershell` (no fontTools there), macOS via fontTools over
  `/System/Library/Fonts`, `…/Supplemental`, `/Library/Fonts` and the
  FontServices `Reserved` dir (PingFang lives there) — and writes
  `families.<os>.unique_names`: {full-or-PS name → {family, style}} for
  faces whose family is in the captured list (188 Windows faces, ~768
  macOS faces).
- **Bundle faces.** `fetch_fonts.py` records each bundled file's faces
  (`bundle[i].faces`: family, full, ps, style) after fetching, so
  `gen_fontconfig.py --check` needs no font files.
- **Map.** `gen_fontconfig.py` writes `unique_map.<os>`: every host
  unique name → the target family's face full name of the same style
  (Regular/Bold/Italic/Bold Italic; unknown style → Regular). The
  generator emits `fonts:list` = families + `extra_allowed` + unique
  names, and `fonts:alias` = `alias_map` ∪ `unique_map`.
- **No C++ change expected**: `LocalFontFaceSource` already calls
  `IsFontAllowed(name)` and `FontCache::GetFontData(…, kLocalUniqueFace)`
  reaches the alias hook with the unique name as the family string; the
  hop lands on the target face's full name, which the Linux unique-name
  lookup resolves from the fontconfig dirs. **Measured first, RED first:**
  if the lookup does not see the bundle dir the row stays red and the doc
  says why; no second hook is added on a guess.
- Rows (`verify_fonts_bundle.py`): F10 RED today: `local("SegoeUI")`
  status `error` under the current config. F11: with unique names,
  `local("SegoeUI")` and `local("Segoe UI Bold")` load and the loaded
  face's width equals `"Segoe UI"` / bold `"Segoe UI"`; `local("Selawik")`
  and `local("Selawik-Regular")` error (bundle unique names are not
  allowed). Worker parity for F11 (rule 3; the fonts-ii verify already
  measures local() in a worker, so the page shape exists).

## 4. Emoji presence (`verify_fonts_bundle.py` F8)

Width cannot see an emoji font. Colour can: draw U+1F600 at 32 px on a
canvas and count pixels whose channels differ (a colour emoji has them; a
tofu box, a monochrome fallback and a blank do not). F8: under the Windows
claim + bundle, `"Segoe UI Emoji"` renders ≥ 50 coloured pixels; RED: no
`--fonts-dir` on the box renders 0 (the box has no colour emoji font;
recorded if it turns out to have one — then the RED is a config with
`fonts:list` excluding every emoji family).

## 5. Claim follows the list (`gen.py`, manifest)

`capture_fonts_list.py` records `families.<os>.os_version` (Windows
`Win32_OperatingSystem.Version` = `10.0.19045`; macOS `sw_vers` =
`15.7.4`) and `platform_version`, the UA-CH form Chrome reports for it
(Windows 10 → `"10.0.0"`; macOS → the marketing version `"15.7.4"`).
`gen.from_pool` sets `ua:platformVersion` to the manifest's
`platform_version` **whenever it emits `fonts:list` for that OS**,
overriding the pool's value. Unit test: a Windows identity's
`ua:platformVersion` is `10.0.0`, a macOS identity's is the manifest's;
Linux (no list) keeps the pool's. Trade-off named in the doc: every
Windows identity is a Windows 10 identity until a Windows 11 host is
captured.

## 6. Closed by fact, recorded

- **macOS build**: 47 GiB free on the Mac (`df`), no depot_tools; a
  checkout plus a component build needs ≥ 120 GiB. Not started. Also blocks
  "Windows/macOS hosts get no alias layer" (no host build to measure).
- **WebGL DB**: the Mac's Chrome is 151.0.7922.138; the 153 re-capture of
  the macOS profile waits. No third GPU is reachable (the host's Edge 152
  shares the Intel UHD 630; WSL has SwiftShader only). Two rows remain.
- **Hinting/AA**: out of scope by reasoning (§0).
- **Invariant `fonts-alias-requires-list`**: the validator reports and
  never repairs (its header says so and static-asserts it); strict aborts,
  non-strict logs. Unchanged; named as such wherever the invariant is
  described.
- **Alias is one hop**: design; chains unsupported.
- **Generator regression at N=10**: run once, the count goes in the doc.

## 7. Verification summary

| what | RED | GREEN |
|---|---|---|
| metric grid | control row below 0.98 = harness broken | M1/M2 ≥ 0.98; M3/M4 decide their clones; M5/M6 numbers |
| CJK split | before: JP pixels == SC pixels | after: differ |
| F-PSNAME | `local("SegoeUI")` error today | loads, width == family width; bundle unique names still error; worker parity |
| emoji | 0 coloured pixels with no bundle | ≥ 50 with |
| claim follows list | — | unit test on `ua:platformVersion`; generator verify G-rows still zero `camoucfg:` lines |
| regressions | — | `verify_fonts_bundle.py` all rows, `verify_sp6b_generator.py` N=10, `run_coherence_tests.sh` 7/7 14, `test_fonts.py`, `test_gen.py`, `gen_fontconfig.py --check` |

Artifacts: `settings/fonts.json` (bundle + classes + unique names +
os/platform versions + maps), `settings/fontconfig/*.conf`,
`baselines/chrome-8010-stock-font-metrics-windows.json`,
`scripts/capture_font_metrics.py`, `scripts/verify_font_metrics.py`,
`scripts/capture_fonts_list.py --names`, `scripts/fetch_fonts.py` (faces),
`scripts/gen_fontconfig.py` (unique_map), `client/python/camoucrome/gen.py`,
`client/python/tests/test_gen.py`, `scripts/test_fonts.py`,
`docs/superpowers/measurements/2026-09-11-fonts-metrics.md`, the fonts
bundle doc §4 rewritten as the remaining list, roadmap rows, ledger. A
fifth archive cut only if a C++ change turns out necessary (§3); otherwise
the bundle changes ride in `fonts/` and `settings/`, which the packager
copies from the repo at cut time — the doc says which cut has them.
