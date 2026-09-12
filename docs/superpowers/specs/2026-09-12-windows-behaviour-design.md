# Windows behaviour past presence — design

Date: 2026-09-12. Follows `2026-09-12-windows-oracle-design.md`, whose
residual list this slice takes up: `navigator.share()` behaviour past the
first call, voices for a non-`en-US` locale, the Windows 11 host, the
Linux pool's empty `platformVersion`. Windows first, macOS skipped by
direction (the share fix covers a macOS claim too, since the crash is the
same code path).

## 1. The finding that reshapes the slice

The oracle measured presence: under a Windows claim `navigator.share`
exists, as on the host. Calling it with a user gesture on the fork kills
the renderer ("Target crashed" from the driver; `share_probe.py`, 2026-09-12,
`out/Default/chrome`, both a Windows and a macOS claim). The path:

1. `chrome/renderer` enables `WebShare` for the claim (windows-oracle);
2. `NavigatorShare::share` binds `blink.mojom.ShareService` through the
   frame's `BrowserInterfaceBroker`;
3. `chrome_browser_interface_binders.cc` registers a `ShareService` binder
   only under `IS_WIN || IS_CHROMEOS || IS_MAC || IS_ANDROID`; on Linux the
   broker finds none and `RenderFrameHostImpl::ReportNoBinderForInterface`
   → `ReportBadMessage` — the renderer is killed.

A renderer kill on one call is a fingerprint and breaks the CLAUDE.md rule
that config must never crash a renderer. The seventh cut ships it. Rule for
the future (goes into the conventions catalogue): **exposing a renderer
interface under a claim requires its browser-side binder on the build OS;
otherwise the first call is a renderer kill, and a presence-only oracle
cannot see it.**

`navigator.bluetooth` does not share the defect: content registers
`WebBluetoothService` on Linux; `getAvailability()` → `false` and
`requestDevice({acceptAllDevices:true})` with a gesture → `NotFoundError:
Bluetooth adapter not available.` in 5 ms (measured, `bt_probe.py`). That is
the answer of a Windows PC without an adapter (the oracle host is one), so
it stays.

## 2. Share: a Linux binder that behaves like a dismissed sheet

On Windows, `share()` opens the OS share sheet and the promise stays pending
until the user picks a target or dismisses it; dismissal completes with
`ShareError::CANCELED` (`chrome/browser/webshare/win/share_operation.cc`
lines 387 and 402; the Mac picker does the same in
`sharing_service_operation.mm` line 88), which Blink maps to
`AbortError` "Share canceled" (`navigator_share.cc`, `ErrorToString`).

The fork registers, on Linux only, a `content::DocumentService<
blink::mojom::ShareService>` stub in `chrome_browser_interface_binders.cc`
beside the existing platform binders. Its `Share()` completes with
`CANCELED` after `share:cancelMs` milliseconds: the observable outcome of a
user who dismissed the sheet. `CanShare` is renderer-side and unchanged.
Registration is unconditional under `IS_LINUX`: stock Linux Chrome never
exposes `navigator.share`, so the binder is unreachable without the claim
gate, and a Linux claim keeps `share` undefined (O2 already measures that).

Key **`share:cancelMs`** (88th, int32): the delay before the stub cancels,
clamped to 0–60000, plus 0–500 ms of per-call jitter (the key is per
identity; two gestures in one page must not see the identical delay). Absent → cancel immediately. This is the fail-closed
exception to rule 5: the "real" behaviour on the build OS is a renderer
kill, which is forbidden, so absence falls back to the cheapest
non-crashing answer rather than to the real one. No invariant row: the key
has no cross-surface partner and the clamp bounds it (a numeric-range
invariant would only restate the clamp). The generator emits a value in
900–2600 ms under a Windows or macOS claim (a human dismisses the sheet in
seconds, never in 0 ms; a constant would be a signature).

`chrome/browser` gains the `//components/camoucfg` dep and `+components/
camoucfg` DEPS grant (it has neither today), and the mojom include guard in
the binders file is widened to `IS_LINUX`. Three paths in one patch stem,
`windows-behaviour`; `gn check` and `checkdeps` run explicitly.

## 3. Voices follow the locale

`settings/voices.json` becomes a per-locale table for Windows. Source:
Microsoft's "Appendix A: Supported languages and voices" (the Windows 10
and Windows 11 tabs are identical) for which voices each language pack
carries, and the OneCore token display strings
(`Microsoft <Name> - <Language> (<Region>)`) as published in the WebbIE
list of Windows 10 voices, which match the one string measured on the host
(`Microsoft David - English (United States)`) and carry Windows' own
quirks verbatim (`Korean (Korean)`, `Catalan (Catalan)`, `Arabic (Saudi)`,
`Norwegian (Bokmål)`, `English (United Kingdom)` not "Great Britain").
Appendix A spells "Hortence"; the token string is `Hortense`.

Shape follows the measured host: one language pack's voices only,
alphabetical by name, the first one `default: true`, `voiceURI == name`,
`localService: true`, `lang` = the pack's tag. Rows exist for every language pack
Appendix A names (49 tags, 78 voices). `gen.voices_keys(platform, locale)`: the locale's
row; else the same language's first row in table order (`fr-BE` → `fr-FR`,
`en-NZ` → `en-AU`, `uk-UA` → `en-US`); else `en-US`. Only `en-US` is measured; every other row is
quoted, not measured, and the manifest says so per row. The sp4-voices
doc's "operator responsibility" paragraph is superseded: the generator
does it.

## 4. Closed by fact / out of scope

- **Windows 11 host.** None exists. `gen.fonts_keys` already pins
  `ua:platformVersion` to the manifest's `10.0.0` for every Windows claim
  (`test_gen` asserts it), so no Windows 11 identity can be produced and
  the fonts, voices and oracle data stay coherent with the claim. Residual:
  Windows 11 identities need a Windows 11 host; nothing is manufactured.
- **Linux pool `platformVersion` empty.** Windows first; one residual line.
- **Host-side share dismissal timing** is unmeasured: opening the sheet on
  the user's PC leaves a live OS window there. The `CANCELED` path is cited
  from the code, not measured.

## 5. Verification (`verify_windows_behaviour.py`, box `out/Default/chrome`)

| row | expectation | RED |
|---|---|---|
| S1 Windows claim, gesture | `AbortError: Share canceled` after ≥ `share:cancelMs` and < cancelMs + 3000 (jitter ≤ 500); the page still answers afterwards (no crash) | pre-fix: "Target crashed" (measured) |
| S1b two gestures in one page | both within the bound, delays differ (per-call jitter 0–500 ms) | — |
| S2 Windows claim, no gesture | `NotAllowedError` (renderer-side, unchanged) | — |
| S3 Linux claim | `navigator.share` undefined | — |
| S4 key absent | cancels within the jitter alone (< 700 ms), no crash | — |
| V1 fr-FR Windows identity | `voices:list` = Hortense (default), Julie, Paul, all `fr-FR` | — |
| V2 en-NZ / uk-UA | fall back to the `en-AU` row (same language) / the `en-US` row | — |

Regressions: `verify_host_oracle.py` 4/4, `verify_sp4_voices.py` 5/5,
`test_gen`, `verify_sp6b_generator.py` N=3, `gen_keys.py --check`,
`CamoucfgKeysTest`, `gn check` + `checkdeps` on `//chrome/browser`. Then
the eighth archive cut (the seventh's chrome kills the renderer on
`share()`), oracle 4/4 and S1–S4 on the archived chrome.
