# Windows Oracle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the fork-side differences the Windows oracle found (brands, WebShare, WebBluetooth, Font Access presence + content, voices) and turn the oracle into a standing verify.

**Architecture:** Two new keys (`ua:brand`, `fonts:local`), three C++ hunks (brand list, claim-gated runtime features in the renderer client, Font Access response substitution), generator data (brand, voices, faces). Verify = `verify_host_oracle.py` rows O1–O4.

**Tech Stack:** C++ on the box (`camoucrome/main`, new commit `windows-oracle`), Python generator/tests, PowerShell-driven host capture.

## Global Constraints
- Pin 507c6ee3e2 / 153.0.8010.36; export gate empty; checkout sync 39 (+ new files).
- Rule 5 fall-backs; no JS; a bad `fonts:local` line is skipped, never a crash.
- `chrome/renderer` needs a `//components/camoucfg` dep and a DEPS grant (check both: `gn check`, `checkdeps`).

---

### Task 1: `ua:brand`
- [ ] keys.json entry `kUaBrand` (`ua:brand`, string); `gen_keys.py`; `keys_unittest.cc` declared set.
- [ ] `user_agent_utils.cc` `GetUserAgentBrandList`: after the `#if !CHROMIUM_BRANDING` block, `if (auto b = camoucfg::GetString(camoucfg::ScopeFor(nullptr), camoucfg::keys::kUaBrand); b && !b->empty()) brand = *b;` (the file already includes camoucfg via sp1a).
- [ ] `gen.from_pool`: `config["ua:brand"] = "Google Chrome"`; `test_gen`: emitted; a registered key.
- [ ] Box: build chrome; oracle `uadHigh.brands` equal; `verify_sp1a_chrome.py` re-run (re-base its brand expectation on the host oracle if it reads a Chromium baseline).

### Task 2: claim-gated runtime features (WebShare, WebBluetooth, FontAccess)
- [ ] `chrome/renderer/chrome_content_renderer_client.cc` `RenderThreadStarted`, beside the existing `EnableWebShare` block: `const auto os = camoucfg::ClaimedOs(camoucfg::ScopeFor(nullptr)); if (os == camoucfg::OsFamily::kWindows || os == camoucfg::OsFamily::kMac) { EnableWebShare(true); EnableFeatureFromString("WebBluetooth", true); EnableFeatureFromString("FontAccess", true); }`. `chrome/renderer/BUILD.gn` dep + `chrome/renderer/DEPS` grant (`+components/camoucfg`).
- [ ] Box: build; oracle `windowNames`/`navProto` diff empty; O2 RED under a Linux claim (share absent).

### Task 3: `fonts:local`
- [ ] `capture_fonts_list.py --names` also writes `families.<os>.faces` = sorted list of `[ps, full, family, style]` for faces of captured families; keys.json `kFontsLocal` (`fonts:local`, string_list, tab-joined); `gen.fonts_keys` emits it.
- [ ] `font_access.cc` `DidGetEnumerationResponse`: after the permission-denied branch, if `camoucfg::GetStringList(scope, kFontsLocal)` is set, build `FontEnumerationEntry`s from the lines (4 tab-separated fields; skip malformed) sorted by PostScript name, resolve, return. DEPS grant for `modules/font_access` if needed.
- [ ] Verify O3 through the probe with `grant_permissions(["local-fonts"])` + a click for activation: `queryLocalFonts()` returns the manifest's faces and no bundle name.

### Task 4: voices
- [ ] `settings/voices.json` `{ "Windows": [ {name, lang, voiceURI, localService, default} x3 ] }` from the oracle's headed list (voiceURI = name, as Windows reports); `gen.fonts_keys`-style helper `voices_keys(platform)` emits `voices:list`; test.

### Task 5: oracle rows, docs, cut
- [ ] `verify_host_oracle.py`: ignore set with reasons; O1 (zero diffs) / O2 RED (Linux claim) / O3 / O4; exit code.
- [ ] Regressions on the box: sp1a chrome, sp2a, sp4-voices, sp4-fonts, fonts bundle, coherence.
- [ ] Commit on the box `windows-oracle`; export; gate; relink `out/Release`; seventh cut; archive-mode oracle.
- [ ] `docs/superpowers/measurements/2026-09-12-windows-oracle.md`; roadmap row; ledger; CLAUDE.md scripts row (`capture_host_oracle.py`).
