# Windows behaviour past presence — measurements

Slice `windows-behaviour`, 2026-09-12. Spec
`specs/2026-09-12-windows-behaviour-design.md`, plan
`plans/2026-09-12-windows-behaviour.md`. Binary under test: the box's
`out/Default/chrome` (content_shell has no `chrome/browser` binders), driven
by the patchright client.

## 1. The defect the oracle could not see

windows-oracle exposed `navigator.share` under a Windows or macOS claim and
O1 matched stock Windows Chrome leaf for leaf. Calling it:

| call | fork before this slice | why |
|---|---|---|
| `share({title,text,url})` after a click, Windows claim | **renderer killed** — the driver reports `Target crashed` | Blink binds `blink.mojom.ShareService`; `chrome_browser_interface_binders.cc` registers a binder only for Win/ChromeOS/Mac/Android; the broker's `ReportNoBinderForInterface` → `ReportBadMessage` |
| same, macOS claim | renderer killed | same path |
| `share()` without a gesture | `NotAllowedError` | renderer-side check, before any browser call |
| `bluetooth.getAvailability()` / `requestDevice({acceptAllDevices:true})` after a click | `false` / `NotFoundError: Bluetooth adapter not available.` in 5 ms | content registers `WebBluetoothService` on Linux; this is the answer of a Windows PC without an adapter (the oracle host is one) |

The windows-oracle measurement doc called the share case "the promise
hangs"; that was wrong (erratum added there). The seventh archive cut ships
the kill.

## 2. What changed

- **Linux `ShareService` stub** (`chrome_browser_interface_binders.cc`,
  anonymous namespace, `#if BUILDFLAG(IS_LINUX)`): a
  `content::DocumentService<blink::mojom::ShareService>` whose `Share()`
  posts `ShareError::CANCELED` after `share:cancelMs`. `CANCELED` is what
  both real hosts return when the user dismisses the sheet
  (`webshare/win/share_operation.cc` 387/402,
  `webshare/mac/sharing_service_operation.mm` 88); Blink reports it as
  `AbortError: Share canceled`. Registered unconditionally on Linux beside
  the platform binders: stock Linux never exposes `navigator.share`, so it
  is unreachable without the claim gate.
- **Key `share:cancelMs`** (88th, int32, clamped 0–60000, plus 0–500 ms of
  per-call `base::RandIntInclusive` jitter so two gestures in one page differ). Absent → cancel
  at once: the fail-closed exception to rule 5, since the real behaviour on
  the build OS is the broker kill. No invariant (no cross-surface partner;
  the clamp bounds it). The generator emits 900–2600 ms under a Windows or
  macOS claim and nothing under Linux.
- `chrome/browser` gained the `//components/camoucfg` dep and the
  `+components/camoucfg` DEPS grant; the webshare mojom include guard was
  widened to `IS_LINUX`. `gn check //chrome/browser:browser` "Header
  dependency check OK"; `checkdeps.py chrome/browser` SUCCESS.
- **Voices per locale.** `settings/voices.json` is a table of 49 language
  packs / 78 voices: which voices a pack carries from Microsoft's "Appendix
  A: Supported languages and voices" (Windows 10 and 11 tabs identical), the
  display strings from the WebbIE list of Windows 10 OneCore tokens, kept
  verbatim with Windows' quirks (`Korean (Korean)`, `Catalan (Catalan)`,
  `Arabic (Saudi)`, `Norwegian (Bokmål)`, `English (United Kingdom)`).
  Appendix A spells "Hortence"; the token is `Hortense`. Only `en-US` is
  measured (the host's David/Mark/Zira capture, unchanged); the manifest
  says so. `gen.voices_keys(platform, locale)`: the locale's row, else the
  same language's first row in table order, else `en-US`.

## 3. Rows (`verify_windows_behaviour.py`, box `out/Default/chrome`, 2026-09-12)

| row | result |
|---|---|
| S1 Windows claim + click: `AbortError: Share canceled` after 2922 ms with `share:cancelMs` 2543 (+ jitter), page alive. **RED pre-fix: `Target crashed`** (same page, same identity) | PASS |
| S1b two gestures in one page: 2992 ms then 2859 ms, both within the bound, the delays differ | PASS |
| S2 Windows claim, no gesture: `NotAllowedError: … Must be handling a user gesture to perform a share request.`, page alive | PASS |
| S3 Linux claim: `typeof navigator.share === "undefined"` | PASS |
| S4 key absent: `AbortError: Share canceled` within the jitter alone (< 700 ms), page alive (fail-closed, never the kill) | PASS |
| V1 fr-FR Windows identity: `voices:list` = Hortense (default), Julie, Paul, all `fr-FR` | PASS |
| V2 `en-NZ` → the `en-AU` row; `uk-UA` → `en-US` | PASS |
| `verify_host_oracle.py` O1–O4 | 4/4 |
| `verify_sp4_voices.py` | 5/5 |
| `verify_sp6b_generator.py` N=3 (the two new keys under strict) | 15/15 |
| `CamoucfgKeysTest` (88 keys), `gen_keys.py --check`, `check_additions_build.py`, client tests 27 | PASS |

Build: `out/Default` chrome + components_unittests 95 steps, 1 m 36 s (then
2 steps for the jitter amend). Box tip `305e949a77 windows-behaviour` (keys.h doc regen amended) above
`1ae7cdb240 windows-oracle`; export gate empty (35 commits; the patch
carries all three paths).

## 4. Residuals, named

- Host-side share dismissal timing is unmeasured: opening the sheet on the
  user's Windows host leaves a live OS window there. `CANCELED` is cited
  from the code paths above, not measured.
- Every voices row but `en-US` is quoted, not measured. A non-English host
  capture would turn a row into a measurement.
- Windows 11: no host. `gen.fonts_keys` pins `ua:platformVersion` to the
  manifest's `10.0.0` for every Windows claim, so no Windows 11 identity is
  produced and nothing is manufactured.
- The Linux pool's empty `platformVersion` stays (Windows first).
- A macOS claim has no voices row (`voices_keys("macOS", …)` → `{}`), so
  it exposes the box's real `getVoices()`: **0 voices** on `out/Default/chrome`
  (no speech-dispatcher there; a Linux claim reads the same 0). A real Mac
  lists dozens; skipped by direction, a manufactured-silence tell to close
  when macOS is taken up.
- `share()` with `files` is answered the same way (CANCELED); stock Windows
  would first run the safe-browsing and file-type checks, whose rejections
  (`PERMISSION_DENIED` → `NotAllowedError`) the stub does not reproduce.
