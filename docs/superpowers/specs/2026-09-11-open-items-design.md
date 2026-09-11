# Open items after A5 — fonts posture, WebGL profile DB, locale→zone table, chrome-binary to-dos

Design for the five items the 2026-09-11 recap left to the user, decided
here so they can be built without a question round: fonts licensing (C),
the archive re-cut, the B1 to-do list on the `chrome` binary, the WebGL
profile database, and GeoIP / locale→timezone. Each section states the
decision, what is built, how it is verified (RED first), and what stays
open by name.

Sources read for this: roadmap A3 #2 / A5 #3 / B1 / C, `sp4-fonts-surfaces`,
`fonts-ii-local-surfaces`, `sp6b-generator`, `sp6b-packaging` §3,
`2026-09-11-d-gaps`, SP2 §4.7 + D4 + D7, SP7 D1 and the phone-home doc's
"still open", `verify_sp1a_chrome.py`'s pinned baseline, and two facts
measured while writing this: the box's **Windows host has stock Google
Chrome 153.0.8010.36** (the pinned tag) with an Intel UHD Graphics 630, and
a **headed Chrome 151 on the Mac** exposes `ANGLE (Apple, ANGLE Metal
Renderer: Apple M1 Pro, Unspecified Version)` (headless gives no context).

## 1. Fonts: decision C, answered

**Decision: no proprietary font file is redistributed.** Segoe UI, Tahoma,
Calibri, San Francisco, Helvetica Neue and the rest of the Windows/macOS UI
sets are licensed to the OS, not to us; Camoufox ships them, that is its
exposure, not ours. What we ship instead is a **metric-compatible open
bundle plus a fontconfig alias layer**, per claimed OS, on the Linux host:

| claimed family | resolves to (bundled) | licence | metric relation |
|---|---|---|---|
| Segoe UI, system-ui (Windows) | Selawik | SIL OFL 1.1 (Microsoft) | designed by Microsoft as a Segoe UI replacement; metric agreement unmeasured |
| Arial, Helvetica | Liberation Sans | SIL OFL 1.1 | metric-compatible |
| Times New Roman | Liberation Serif | SIL OFL 1.1 | metric-compatible |
| Courier New | Liberation Mono | SIL OFL 1.1 | metric-compatible |
| Calibri | Carlito | SIL OFL 1.1 | metric-compatible |
| Cambria | Caladea | SIL OFL 1.1 | metric-compatible |
| Georgia, Verdana, Tahoma, Trebuchet MS | Noto Serif / Noto Sans (no open clone) | SIL OFL 1.1 | **not** metric-compatible: resolves, widths differ from Windows |
| system-ui, -apple-system, Helvetica Neue (macOS) | Inter | SIL OFL 1.1 | not metric-compatible: resolves, widths differ |
| Yu Gothic, Meiryo, Microsoft YaHei, SimSun, Malgun Gothic, PingFang SC, Hiragino Sans (CJK) | Noto Sans CJK SC (one regional OTF, ~16 MB) | SIL OFL 1.1 | glyph coverage, not metrics: without it a Windows claim renders CJK as tofu, which canvas text probes see |
| Segoe UI Emoji, Apple Color Emoji | Noto Color Emoji (~10 MB) | SIL OFL 1.1 | same: tofu is a tell |
| every other captured family | by script class (sans → Selawik/Inter, serif → Liberation Serif, mono → Liberation Mono, CJK → Noto CJK, symbol → Noto Sans Symbols) | — | presence only |

**The family lists are captured, not authored.** The box's Windows host
is a real Windows 10 install: `Get-ChildItem C:\Windows\Fonts` plus
`[System.Drawing.Text.InstalledFontCollection]::new().Families` (PowerShell
over `ssh buildpc`) gives `families.Windows` with provenance; on the Mac
`system_profiler SPFontsDataType -json` gives `families.macOS`. Every
captured family gets a **strong** alias to a bundled fallback by its script
class (a name→class table in `settings/fonts.json`, default sans), so the
whole captured list resolves and `fonts:list` can be the whole list.

Files live in `fonts/` (git-ignored), fetched by `scripts/fetch_fonts.py`
from pinned release URLs with sha256s recorded in `settings/fonts.json`,
which also carries the alias table, the script-class table, the captured
family lists and each font's licence file name. Bundle size ≈ 35 MB
compressed (CJK + emoji are most of it); the archive grows from 149 MiB
to roughly 185 MiB, accepted: tofu in a canvas probe is a louder tell than
an archive size. `package.py` copies `fonts/` and the two fontconfig
files into the archive when the directory exists (`--no-fonts` to skip;
the stamp records `fonts: true|false`).

**Two fontconfig files**, `settings/fontconfig/windows.conf` and
`settings/fontconfig/macos.conf`, generated from `settings/fonts.json` by
`scripts/gen_fontconfig.py` (`--check` like `gen_keys.py`): `<dir
prefix="relative">../fonts</dir>` and nothing else (no system dirs, so
DejaVu/Ubuntu/Cantarell never resolve by name; fontconfig 2.15 on Ubuntu
24.04 supports the relative prefix, so the archive extracts anywhere), a
`<cachedir prefix="xdg">camoucrome-fontconfig</cachedir>` so launches do
not rescan, `<alias binding="strong">` for every claimed family — **strong
is load-bearing**: Skia's fontconfig manager (`SkFontMgr_fontconfig::
matchFamilyStyle`) accepts a match only when the pattern's family equals
the request under strong binding, and fontconfig's default weak fallback
is exactly what Chrome reports as "font not found" — and the generic
defaults (`sans-serif` → Selawik or Inter, `serif` → Liberation Serif,
`monospace` → Liberation Mono). Cutting the system directories is what
closes the `system-ui` and CSS2-keyword rows in the d-gaps doc: Chrome
resolves both through the fontconfig default sans.

**Launcher duty**: both launchers set `FONTCONFIG_FILE` to the conf of the
claimed OS family (`ua:platform` / preset `os`) when a `fonts` dir is found
beside the executable, or when `fonts_dir=` is passed. Contract field
`launch.fontconfig` in `settings/launcher.json`: `{ "env":
"FONTCONFIG_FILE", "files": { "Windows": "fontconfig/windows.conf",
"macOS": "fontconfig/macos.conf" } }`. No env for a Linux claim.

**Generator**: `gen.py` emits `fonts:list` = the claimed OS's canonical
list from `settings/fonts.json` (`families.Windows`, `families.macOS`),
every name of which resolves under that conf. Linux claim: no list (host
fonts are the truth). The allowlist is a filter; the conf is what makes
the listed names resolvable — both are needed.

**Verify** `scripts/verify_fonts_bundle.py` on `chrome` through the probe,
width test only (`document.fonts.check` is useless, measured):

- F1 RED: no `FONTCONFIG_FILE`, no config: `Segoe UI` width == monospace
  fallback width (unresolvable), `DejaVu Sans` resolves.
- F2 Windows conf + Windows `fonts:list`: every listed family resolves
  (width with monospace fallback ≠ bare monospace); `DejaVu Sans`,
  `Ubuntu`, `Cantarell` do not; `system-ui` width == `Selawik` width ==
  `Segoe UI` width; `font: caption` renders at that same width.
- F3 macOS conf + macOS list: every listed family resolves; `system-ui`
  width == `Inter` width == `-apple-system` width.
- F4 generator: `gen.py --os Windows` output's `fonts:list` ⊆ resolvable
  set under the Windows conf (page-measured, not table-asserted).
- F5 archive: after extraction, `fonts/` + the two confs present and F2
  passes with `CAMOU_EXE=<extracted>/chrome`.

**Open, named**: glyph-level metrics of Selawik vs Segoe UI are
unmeasured (a per-glyph width baseline captured on the Windows host would
tell; the width test above measures presence, not identity);
Georgia/Verdana/Tahoma have no open metric clone; CJK coverage is one
regional font (Simplified Chinese glyph forms for Japanese/Korean text); hinting/AA posture (FreeType vs DirectWrite
rasterisation) is a separate measurement; Windows/macOS hosts get no
alias layer (DirectWrite/CoreText, not fontconfig); F-PSNAME residual
(PostScript-name probes) unchanged.

## 2. Archive re-cut

Mechanical: the `out/Release` relink with `d-pointer-touch` and the
invariant is done (104 steps); `pkg_job.sh` stamps `changeset_commit
58b59ab`, `branch_tip bc91762ccd`, then the DevTools check and the
six-driver sweep run on the extracted tree. Re-cut once more at the end
of this slice so the archive carries `fonts/`. Packaging doc §3 gets a
"second cut" line; the roadmap's A5 #1 names the commit.

## 3. WebGL profile database (A3 #2) — unblocked by two real GPUs

**Shape**: `settings/webgl/<id>.json`, one file per (OS, GPU) capture:

```json
{ "id": "windows-intel-uhd-630-d3d11", "os": "Windows",
  "vendor": "Google Inc. (Intel)",
  "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E92) Direct3D11 vs_5_0 ps_5_0, D3D11)",
  "webgl":  { "parameters": {"3379": 16384, "3386": [16384, 16384], "34076": 16384},
              "supportedExtensions": ["ANGLE_instanced_arrays", "EXT_color_buffer_half_float"],
              "shaderPrecisionFormats": {"VERTEX_SHADER/HIGH_FLOAT": [127, 127, 23]},
              "contextAttributes": {"alpha": true, "antialias": true, "powerPreference": "default"} },
  "webgl2": { "parameters": {}, "supportedExtensions": [], "shaderPrecisionFormats": {}, "contextAttributes": {} },
  "provenance": { "binary": "Google Chrome 153.0.8010.36 (stock, Windows 10 host of the build box)",
                  "captured": "2026-09-11", "how": "scripts/capture_webgl_profile.py", "headless": true, "angle": "d3d11" } }
```

`capture_webgl_profile.py` runs the page in a given binary (stock Chrome on
the Windows host via `ssh buildpc` PowerShell, always a temp
`--user-data-dir`, never the host's own profile; headed Chrome on the Mac
via playwright, 300×200 window, closed after the read) and prints the
file. Windows order of attempts, stopping at the first non-SwiftShader
renderer: `--headless=new --use-angle=d3d11` (headless self-adds
`--use-angle=swiftshader-webgl` only when `--use-angle` is absent), then
`--use-gl=angle --use-angle=d3d11`, then headed (a window in the SSH
session is invisible; D3D11 renders offscreen). A SwiftShader string is
not a profile and the script refuses to write one. The
parameter list is every numeric `getParameter` pname in the
WebGLRenderingContext and WebGL2RenderingContext IDL constant tables,
enumerated by name in `capture_webgl_profile.py` (the 13 `PNAMES` of
`capture_preset.py` are a subset), plus `getSupportedExtensions()`,
`getShaderPrecisionFormat` for the 6 shader×precision pairs ×3 types, and
`getContextAttributes()`.

Two profiles captured now: `windows-intel-uhd-630-d3d11` (Chrome 153 =
the pin) and `macos-apple-m1-pro-metal` (Chrome 151; provenance says so —
ANGLE Metal limits are driver-stable across two milestones, the strings
are byte-identical to the 153 format the catalogue documents).

**Generator**: `--gpu <id>` selects a profile; absent, the first profile
whose `os` equals the claimed OS; none for the OS → no `webGl:*` (Linux
today). Emits `webGl:vendor/renderer`, `webGl2:vendor/renderer`,
`webGl:parameters`/`webGl2:parameters` (the numeric table),
`webGl:supportedExtensions`/`webGl2:supportedExtensions`. Not emitted:
`shaderPrecisionFormats` and `contextAttributes` (captured for the record;
their keys exist, the generator adds them when a verify shows the host
differs from the profile — the box's SwiftShader and the Intel D3D11
precision tables are compared in the verify below and the doc says which).

**Verify** `scripts/verify_webgl_profile.py` (chrome, probe):

- W1 RED: no config → renderer is the host's SwiftShader string, and
  `MAX_TEXTURE_SIZE` etc. are the host's.
- W2 Windows profile applied → every emitted parameter reads back equal
  on both contexts, vendor/renderer equal to the profile, the extension
  list equal (set equality) **and `getExtension(name)` non-null for every
  claimed name** (a listed extension the SwiftShader host cannot back is
  the tell set equality misses), startup log has zero `camoucfg:`
  invariant lines (`webgl-renderer-backend-fits-os` accepts D3D11 on a
  Windows claim).
- W3 macOS profile on a macOS claim likewise; W3-RED: the macOS profile on
  a Windows claim is refused under strict (`webgl-renderer-backend-fits-os`).
- W4 precision formats + context attributes: host vs profile diff printed;
  asserted equal for the pairs the profile lists (informational when the
  key is not emitted).

**Open, named**: two profiles is a database of two; market-share sampling
(Camoufox's `webgl_data.db`) needs captures the project does not have;
AMD/NVIDIA D3D11 and Linux Mesa entries are one capture each away.

## 4. Locale → timezone table (GeoIP answered)

**Decision: no GeoIP database.** MaxMind GeoLite needs an account and its
licence terms bind redistribution; a proxy-exit lookup is a client runtime
concern the caller already owns (Camoufox's path). What the generator
lacks is an **offline default**: `settings/locale_zones.json`, a table of
~40 locale tags → plausible IANA zones, first entry the most common
(`en-US` → `America/New_York, America/Chicago, America/Denver,
America/Los_Angeles`; `fr-FR` → `Europe/Paris`; `vi-VN` →
`Asia/Ho_Chi_Minh`; `en-GB`, `de-DE`, `es-ES`, `es-MX`, `pt-BR`, `ja-JP`,
`ko-KR`, `zh-CN`, `zh-TW`, `ru-RU`, `it-IT`, `nl-NL`, `pl-PL`, `tr-TR`,
`id-ID`, `th-TH`, `en-AU`, `en-CA`, `fr-CA`, `en-IN`, `hi-IN`, `ar-SA`,
`ar-EG`, `sv-SE`, `da-DK`, `nb-NO`, `fi-FI`, `cs-CZ`, `hu-HU`, `ro-RO`,
`uk-UA`, `el-GR`, `he-IL`, `ms-MY`, `fil-PH`, `en-NZ`, `en-IE`, `en-ZA`,
`de-AT`, `de-CH`, `fr-BE`, `nl-BE`, `pt-PT`).

`gen.py`: `--timezone` optional. Absent → the table row for the locale
(explicit `--locale`, else the pool's `navigator.language`), one zone
chosen by the seed; locale not in the table → refuse with the message it
gives today (no half-config). Go `Generate()` unchanged (it execs the
CLI). `settings/locale_zones.json` is validated by a test: every zone is a
valid IANA name (`zoneinfo.available_timezones()`), every locale tag parses
as `xx-YY`.

**Verify**: generator test `test_gen.py`: `generate("Windows", None,
"fr-FR", seed)` → `timezone:id == "Europe/Paris"`; `en-US` seed-stable and
in the four; unknown locale raises. Oracle on the box: 10 generated
configs without `--timezone` start under strict with zero `camoucfg:` lines
(`timezone-set-with-locale` satisfied) and
`Intl.DateTimeFormat().resolvedOptions().timeZone` equals the emitted zone.

**Open, named**: `geolocation:*` (a representative lat/long per zone) is
not in the table; per-zone weights (market share) are not; a proxy-exit
lookup stays the caller's.

## 5. The B1 to-do list on the `chrome` binary

Roadmap B1's cell is stale in two places (verified by reading the tree):
`Sec-CH-UA*`/`userAgentData` end-to-end **was** verified (SP1a Task 8,
34/34 on M153, `verify_sp1a_chrome.py`), and SP7's two verifies already
run their chrome rows (7/7, 3/3). The roadmap text is corrected; the
genuinely open items and their treatment:

| item | treatment |
|---|---|
| **window.chrome shape** (SP2 §4.7) | `scripts/capture_chrome_object.py` dumps the recursive property tree of `window.chrome` (own names, descriptors' kinds, function `length`/`name`, `toString()` of each function, `loadTimes()`/`csi()` key sets and ordering checks) — run on **stock Chrome 153.0.8010.36 on the Windows host** (same tag as the pin) and on the fork's `chrome` (box, headless). `scripts/verify_chrome_object.py`: diff empty except the platform-bound values (`loadTimes().npnNegotiatedProtocol` etc. are values, not keys); RED: the fork with a config that spoofs the UA still shows the same tree (no config path touches it) — RED-by-construction is the stock-vs-content_shell diff (content_shell has no `window.chrome`: non-empty diff proves the differ sees). Baseline committed as `baselines/chrome-8010-stock-window-chrome.json` |
| **navigator.plugins / mimeTypes / pdfViewerEnabled** | measured, not keyed: the same capture on stock Windows Chrome 153 (headless and headed) and the fork (headless) — `plugins.length`, each `name`/`filename`/`description`, `mimeTypes` (`type`, `suffixes`), `pdfViewerEnabled`. If the fork equals stock → closed, row in the doc. If headless differs from headed on stock → a headless tell, named for B7 (posture), not keyed here |
| **SP7 on chrome: `X-Client-Data` + variations** | `verify_sp7_phonehome.py` gains P4: navigate to `https://www.google.com/generate_204` (network on the box), capture request headers through CDP `Network.requestWillBeSentExtraInfo` (a verify harness, not a driver), assert no `X-Client-Data` header and no request to `clientservices.googleapis.com` / `update.googleapis.com` during the 20 s window. RED, constructed: `X-Client-Data` is only sent from a profile that holds a variations seed with IDs, so a fresh profile on stock sends nothing too. Stock Chrome 153 on the Windows host is launched **twice on the same temp profile** with `--remote-debugging-port` and the same CDP harness: the first run fetches and stores the seed (that fetch is itself the seed-fetch evidence), the second navigates to `generate_204` and sends the header. Fork: the same two-launch shape sends no header either time |
| **Sec-CH-UA end-to-end** | re-run `verify_sp1a_chrome.py` on the box as regression evidence (34/34 expected); roadmap sentence corrected |
| **headless_shell token** (SP2 D4 residual) | decision: `headless_shell` is neither shipped nor tested — `package.py` targets `//chrome:chrome` only and the contract's executable is `chrome`. One sentence in the SP2 spec's D4 and the roadmap closes it; no code |

## 6. Ordering and what each slice leaves behind

1. Archive re-cut (running) → packaging doc §3 line.
1b. **One Windows-host capture round** (stock Chrome 153, PowerShell over
   ssh, temp profiles): the font family list, the WebGL profile, the
   `window.chrome` tree, `navigator.plugins`/`mimeTypes`/`pdfViewerEnabled`
   headless and headed, and the two-launch `X-Client-Data` RED — every
   later slice reads its reference data from this round. The Mac round
   (font list, WebGL profile) in the same task.
2. WebGL profiles → `settings/webgl/*.json`,
   generator `--gpu`, `verify_webgl_profile.py`, doc
   `measurements/2026-09-11-webgl-profiles.md`.
3. Locale→zone table → `settings/locale_zones.json`, `gen.py`, tests,
   generator doc §5.
4. Fonts bundle → `settings/fonts.json`, `fetch_fonts.py`, fontconfig
   files, launcher env (Python + Go + Node), `package.py`, generator
   `fonts:list`, `verify_fonts_bundle.py`, doc
   `measurements/2026-09-11-fonts-bundle.md`; then the final archive
   re-cut with fonts.
5. Chrome-binary items → captures + verifies + docs above, roadmap B1
   corrected, SP2 D4 closed.

Every verify is RED-first on the box; every doc states the count it
measured; roadmap rows move only to what the docs say.
