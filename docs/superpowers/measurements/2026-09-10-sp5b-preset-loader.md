# SP5b preset loader (A3 #3) — 2026-09-10

Spec: `specs/2026-08-26-sp5-coherence-engine-design.md` §4.5. Roadmap A3 #3.

## 1. Shape

A preset is the minimum identifying set of a captured device
(`settings/presets/chromium-<milestone>.json`). It reaches the browser as
`CAMOU_PRESET` (or `CAMOU_PRESET_1..N`, the same chunked transport as
`CAMOU_CONFIG`), never as a file path: `ParsedConfig()` runs in every process
and the renderer cannot open files behind its sandbox, while the environment
is inherited exactly as `CAMOU_CONFIG` already relies on. A client reads the
file and passes it; the browser never opens one.

`ExpandPreset(preset, fork_milestone)` in `additions/camoucfg/preset_loader.cc`
is a pure `DictValue → DictValue`; its field → key table is at the top of the
file. `ParsedConfig()` parses the preset with the same rules as the config
(malformed refuses under `CAMOU_CONFIG_STRICT`, otherwise logs and contributes
nothing), expands it, then merges the explicit config over it, so an explicit
key wins and `ValidateAtStartup` validates the merged result with no extra
code. The merge is `base::DictValue::Merge`, recursive for dict-valued keys:
an explicit `webGl:parameters` overrides the preset's table one pname at a
time and the preset's other pnames survive. A malformed preset logs its own
line (`preset is not a JSON object; ignored, explicit configuration still
applies`), not `ParseConfig`'s "all spoofing is disabled", which would be
false with a `CAMOU_CONFIG` beside it. A field outside the table logs a
warning naming it, so a typo or a `CAMOU_CONFIG`-shaped object passed as a
preset is not a silent no-op.

| preset field | keys emitted |
|---|---|
| `os` (UA-CH platform name) | `ua:osInfo`, `ua:platform` (canonical forms from derive.h) |
| `platformVersion` | `ua:platformVersion` |
| `gpu.vendor`, `gpu.renderer`, `gpu.parameters` | both contexts' vendor/renderer, and the same parameter table on both |
| `screen.{width,height,availWidth,availHeight}` | the four `screen.*` keys |
| `fonts` | `fonts:list` |
| `locale` | `locale:tag`, `navigator.language`, `navigator.languages = [tag, primary]` |
| `timezone` | `timezone:id` |

Not emitted, on purpose: `navigator.platform` (derived from the claimed OS
at read time), `screen.colorDepth` / `window.*` / `dpr` (per instance; DPR has
no key), every seed (per instance), `sampleRate` (no key, SP4), and every
version-bearing field (UA string, brands, `fullVersionList`, `Sec-CH-UA`),
which the fork's own milestone produces. Locale expands to all three keys and
the GPU to both contexts plus the table, so the twelve registry entries hold
by construction for a well-formed preset.

**Milestone policy.** The spec weighed refuse / rewrite / warn and recommended
rewrite. Because no version-bearing field is ever taken from a preset, there
is nothing to rewrite: a mismatch (or a missing `milestone`) logs one
WARNING saying the hardware and locale claims stay valid, and the browser
starts. That is the spec's "rewrite" with an empty rewrite set. The fork's
milestone comes from `version_info::GetMajorVersionNumberAsInt()`, a new
cross-component dep of `//components/camoucfg` (`gn check` + `checkdeps`
below).

## 2. The shipped preset is a smoke preset

`scripts/capture_preset.py` records the fork's own unconfigured identity
over CDP (`chrome` binary, since content_shell reports UA-CH platform
"Unknown"; loopback page, since `userAgentData` needs a secure context).
`settings/presets/chromium-153.json` is that capture on the build box:
Linux, headless 800×600, SwiftShader Vulkan, en-US, UTC. Its provenance
block says so. It exists to exercise the loader end to end and is not a
distributable identity; no GPU profile was invented for it, because an
invented parameter table is the incoherence A3 #2 exists to prevent.
Fonts are omitted (no enumeration without a permission prompt).

## 3. Checks

Unit (`PresetLoaderTest`, literal): the full table, one assertion per key
and a size check; derived/per-instance keys absent; empty preset → empty;
unknown OS → no OS keys; region-less locale → one-entry list; wrong-typed
field skipped, not coerced. `AssembleRawConfigTest.PrefixSelectsThePresetFamily`
pins the transport.

Coherence runner: `ShippedPresetProducesNoViolations`, one process per
`settings/presets/*.json` with the file in `CAMOU_PRESET` and no
`CAMOU_CONFIG`, asserting the keys came out of the preset, zero
violations, zero wrong-type warnings. Zero preset files fails.

Browser (`scripts/verify_sp5b_preset.py`, content_shell under SwiftShader,
an invented fixture preset that is not shipped): P0 RED every surface
differs from the fixture with nothing set; P1 preset only reproduces
screen, locale, timezone, UA OS and both GL identities; P2 explicit
`screen.width` wins, the rest survives; P3 startup log has no invariant,
wrong-type or milestone line; P4 milestone 120 starts and logs the
mismatch; P5 RED malformed preset not strict starts on real values with the
one error line; P6 malformed under strict exits during startup.

## 4. Result (2026-09-10, box, M153 stack)

| check | result |
|---|---|
| RED: runner on the old binary | `error: binary reports 6 CoherenceValidatorTest case(s), this script's ORDER lists 7` |
| RED: `verify_sp5b_preset.py` on the old content_shell | 2 PASS 5 FAIL — P0 (fixture differs) and P3 (nothing logged) pass, P1/P2/P4/P5/P6 fail, the preset ignored |
| build | 21 steps (`components_unittests`, `content_shell`) |
| `components_unittests`, 20 Camoucfg suites | 116 PASSED (6 `PresetLoaderTest` + `PrefixSelectsThePresetFamily` new) |
| `run_coherence_tests.sh` | 7/7 PASS, 12 mutations, `ShippedPresetProducesNoViolations[chromium-153.json]`, 0 wrong-type warnings |
| `verify_sp5b_preset.py` | 7 PASS 0 FAIL |
| `gn check //components/camoucfg/*` | Header dependency check OK |
| `checkdeps.py components/camoucfg` | FAILED first: `-components` from components/DEPS, and the pre-existing `ui/gfx/geometry` includes had no rule either (checkdeps had never been run on this directory). `additions/camoucfg/DEPS` declares both; SUCCESS |
| sweep, 38 `verify_*.py` (`verify_and_mutate.py` box-only, skipped) | 37 ok; `verify_webrtc_ii_fakeip.py` FAIL is the rejected slice's RED record (expected, ledger 2026-09-09); `verify_sp3b.py` failed V2–V8 with "Target page, context or browser has been closed" |
| `verify_sp3b.py` cause | its `GL_FLAGS` *replaced* lib_shell's default flags, dropping `--ozone-platform=headless`; content_shell then opened the WSLg X display (`DISPLAY=:0`) and the log shows `X connection error received`. `SHELL_FLAGS +` restored: ALL_PASS. Not a loader regression: the launch flags, not the config, decide it |
| review amendments (relink, 15 steps) | preset parsed by its own `ReadDict` with its own log line (P5 now also asserts "all spoofing is disabled" is absent); unrecognised-field warning; recursive-merge note; `settings/presets` in the export recipe; `checkdeps` SUCCESS; suites 116, runner 7/7, `verify_sp5b_preset` 7/7, `verify_sp3b` ALL_PASS, `verify_sp5a` 6/6 |
| branch / repo | `camoucrome/main` `sp5b-preset-loader` 44fa83ef0e (additions-only); export gate empty; `check_checkout_sync` PASS, 39 files |

P3 passing on the old binary is expected and is why it is not a RED row:
it asserts an absence, and the RED for the loader itself is P1.

Not done, noted: `capture_preset.py` cannot produce a distributable preset
from here. The box gives SwiftShader, the Mac gives no WebGL headless, and a
non-headless launch would open a window on the user's machine. Real presets
need a capture on real hardware on the OS they claim (A3 #2).

