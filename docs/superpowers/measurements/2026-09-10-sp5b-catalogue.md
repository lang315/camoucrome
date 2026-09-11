# SP5b catalogue, first fill (2026-09-10)

Five registry entries, each with its mutation test; the registry's own rule
("an entry without one is documentation, not enforcement") applied. Pin
`153.0.8010.36`.

## 1. Entries

| id | keys (authoritative → repaired) | relation | fires when |
|---|---|---|---|
| `navigator-language-heads-languages` | `navigator.languages` → `navigator.language` | `list-head-equals` | both set, `language != languages[0]` |
| `locale-tag-matches-navigator-language` | `locale:tag` → `navigator.language` | `same-string` | both set, unequal (exact) |
| `webgl2-vendor-agrees-with-webgl` | `webGl:vendor` → `webGl2:vendor` | `same-gl-string` | both sides resolve (key, else `parameters["37445"]`), unequal |
| `webgl2-renderer-agrees-with-webgl` | `webGl:renderer` → `webGl2:renderer` | `same-gl-string` | both sides resolve (key, else `parameters["37446"]`), unequal |
| `webgl-renderer-backend-fits-os` | `ua:osInfo` → `webGl:renderer` | `renderer-backend-fits-os` | OS known, renderer resolves (key, else `parameters["37446"]`) and its backend token names another family |

Authority choices, each written into the entry's `why`: the list over the
scalar (more information); `locale:tag` over `navigator.language` (the
core_initializer hook makes `locale:tag` win for Intl when both are set); WebGL1
over WebGL2 (profiles set it first); the OS over the renderer (no canonical
renderer exists, so `new_value` is descriptive and the mutation test asserts
`repaired_key`, which is the contract).

## 2. The backend-token table is measured, not recalled

| platform | `UNMASKED_RENDERER_WEBGL` | source |
|---|---|---|
| Linux, headless, no GPU | `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)` | stock M153 `chrome` on the box, both context types identical |
| Windows | `ANGLE (NVIDIA, NVIDIA GeForce … Direct3D11 vs_5_0 ps_5_0, D3D11)` | the shape the roadmap already quotes for the profile DB |
| macOS | `ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)` | ANGLE's Metal renderer description; the Mac headless capture returned no WebGL context under `--headless=new` with or without `--use-angle=metal`, so this row is from the string format, not a local measurement |

Only `Direct3D` (Windows) and `Metal` (macOS) fire. Vulkan/OpenGL renderers
map to unknown and constrain nothing: they occur on Linux, Android and older
macOS, and this build's own stock renderer is one of them.

## 3. Verification

RED first: the JSON with nine entries against the previous binary (header with
four) fails `RegistryMatchesGeneratedHeader` on `entries->size()` vs
`kAllInvariants.size()`. Then the rebuild, the suites, and the runner — recorded
in §5.

## 4. Deferred, named

- `timezone:id` set-with `locale:tag` and `mediaDevices:seed` non-zero when
  `mediaDevices:enabled`: presence relations with no concrete repair value;
  the `Violation` model (authoritative/repaired/old/new) cannot express them
  without bending. Needs a `Presence` violation kind first.
- geolocation ↔ timezone plausibility: needs a zone bounding-box table.
- DPR: no `devicePixelRatio` key exists yet.
- `Accept-Language` ↔ `navigator.language`: nothing in the tree derives the
  header from `locale:tag` (tz-locale measurement); a generator obligation,
  not a config invariant.
- WebGL identity set on ONE context only (spoofed WebGL1 beside a real
  WebGL2): `GLVendor`/`GLRenderer` have no WebGL1→WebGL2 fallback, so the
  page sees two GPUs. A presence relation, same kind as the two above.
- Value coherence of the WebGL parameter table against the claimed renderer:
  the profile database (A3 #2).

## 5. Result (2026-09-10)

| check | result |
|---|---|
| RED: 9-entry registry vs the 4-entry binary | `RegistryMatchesGeneratedHeader` FAILED on `entries->size()` vs `kAllInvariants.size()` |
| `components_unittests`, 19 Camoucfg suites | 109 PASSED |
| `run_coherence_tests.sh` (one process per case) | 6/6 PASS, `MutationIsCaughtAndNothingElseIs` green for all nine ids |
| `CleanConfigProducesNoViolations` | the runner's `COHERENT` now carries every new pair and the test asserts their presence, so a pass means the relations ran |
| startup path (content_shell relinked, 1 step) | `verify_sp5a.py` 6/6; a Metal renderer under a Windows `ua:osInfo` logs `invariant 'webgl-renderer-backend-fits-os' violated … should be 'a renderer whose ANGLE backend runs on Windows (Direct3D11)'` |
| branch / repo | committed on `camoucrome/main` as `sp5b-catalogue` (additions-only); export gate empty; `check_checkout_sync` PASS |

Two compile failures on the way, both the same: a `R"(…)"` raw string is
terminated by the first `)"`, which every ANGLE string contains (`(NVIDIA)"`).
The mutation literals use `R"json(…)json"`.

## 6. Fix-forward the same day: the parameters supply path

Review of `007ca80` found that the two agreement entries read only the
`webGl(2):vendor` / `:renderer` keys, while the pairing check (and the
registry's own rule) treats an identity supplied through
`webGl(2):parameters["37445"/"37446"]` as configured — and the backend
entry's comment claimed that path was covered when `GLRenderer()` reads the
key alone. A profile setting WebGL1's renderer through the map and WebGL2's
through the key, disagreeing, passed. That is the catalogued "check that
measures nothing" for one of two supply paths. Fixed: `ResolvedGLString()`
(key, else the map string) feeds a new `same-gl-string` relation for the two
agreement entries and the backend entry; a `static_assert` pins the
agreement entries to the two identity pairs; the renderer mutation now
supplies WebGL1 through the map so the harder path is the one proven.

Result after the fix: build 10 steps; 19 suites 109 OK; `run_coherence_tests.sh`
6/6 with all nine mutations caught alone — the renderer one now through the
parameter map; box commit `sp5b-catalogue` amended (`7d54ea20df`); export gate
empty; `check_checkout_sync` PASS.

## 7. Second fill, same day: the presence relations

The deferred list's first three items needed a relation that fires on
*absence*. Two relations, three entries, registry 9 → 12:

| id | keys | relation | fires when |
|---|---|---|---|
| `timezone-set-with-locale` | `locale:tag` → `timezone:id` | `requires-key` | `locale:tag` set, `timezone:id` unset |
| `mediadevices-seed-when-enabled` | `mediaDevices:enabled` → `mediaDevices:seed` | `requires-key` | enabled **true**, seed absent **or 0** (the consumer's own no-op rule) |
| `android-claims-touch` | `ua:osInfo` (via `ClaimedOs`) → `navigator.maxTouchPoints` | `touch-fits-os` | claimed OS Android, touch points absent **or 0** (added 2026-09-11 with `d-pointer-touch`, which derives a coarse pointer from the claim) |
| `webgl-identity-set-on-both-contexts` | `webGl:renderer` ↔ `webGl2:renderer` | `gl-identity-set-together` | exactly one context type resolves an identity (vendor or renderer, key or map); the missing side is the repaired key and the resolved strings are the repair value |
| `fonts-alias-requires-list` | `fonts:alias` → `fonts:list` | `requires-key` | alias map set, allowlist absent: the bundle's own names (Selawik, Inter Variable…) would resolve beside the families aliased to them (added 2026-09-11 with `fonts-iii-alias`, measurements/2026-09-11-fonts-bundle.md) |

No new violation kind after all: `Violation.old_value` empty is the presence
marker, and `ValidateAtStartup` prints the "'A' is set but 'B' is not. It
should be …" form for those instead of quoting an empty wrong value. The
`requires-key` entries' `new_value` is descriptive (no canonical zone for a
locale, no canonical seed); the GL one is concrete.

Registry 9 → 12, `kMutations` 12. Two of the earlier mutations collided with
the new entries (a `locale:tag`-only config also trips `timezone-set-with-locale`;
a WebGL1-only Metal renderer also trips the set-together entry) and now carry
the extra key so each still produces exactly one violation.

One defect found by review, not by any gate: the first `KeyIsSet` probed the
key through `GetBool` then `GetUint32`, and each getter logs
`key '…' is not a boolean; falling back to the real value` on a type it does
not expect — five false warnings per startup on a coherent config, for values
that were in fact used. It reads the raw `base::Value` now. The runner grew a
check (c) that counts `falling back` lines on the coherent run, which needed
`--test-launcher-print-test-stdio=always`: the launcher swallows a passing
child's stderr, and the count was 0 against the binary known to warn until
the flag was added.

| check | result |
|---|---|
| RED: 12-entry registry vs the 9-entry binary | `RegistryMatchesGeneratedHeader` FAILED |
| RED: pre-fix `KeyIsSet` under check (c) | `5 wrong-type warning(s) on the coherent config`, 5/6 |
| `components_unittests`, 19 Camoucfg suites | 109 PASSED |
| `run_coherence_tests.sh` | 6/6 PASS, all twelve mutation ids, 0 wrong-type warnings |
| startup path (content_shell) | `{"locale:tag":"fr-FR"}` logs `invariant 'timezone-set-with-locale' violated. 'locale:tag' is set but 'timezone:id' is not. It should be set, because 'locale:tag' is.`; 0 `falling back` lines |
| branch / repo | `camoucrome/main` `sp5b-presence` 60127a801d (additions-only); export gate empty; `check_checkout_sync` PASS |

Still deferred from §4: geolocation ↔ timezone (zone table), DPR (no key),
`Accept-Language` (generator obligation), parameter-table value coherence
(A3 #2). Not done, noted: an explicitly configured empty string
(`"navigator.language":""`) would print in the presence wording because the
marker is an empty `old_value`; an explicit flag on `Violation` would remove
the ambiguity.

