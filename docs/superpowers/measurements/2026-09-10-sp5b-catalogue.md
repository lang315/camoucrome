# SP5b catalogue, first fill (2026-09-10)

Five registry entries, each with its mutation test; the registry's own rule
("an entry without one is documentation, not enforcement") applied. Pin
`153.0.8010.36`.

## 1. Entries

| id | keys (authoritative → repaired) | relation | fires when |
|---|---|---|---|
| `navigator-language-heads-languages` | `navigator.languages` → `navigator.language` | `list-head-equals` | both set, `language != languages[0]` |
| `locale-tag-matches-navigator-language` | `locale:tag` → `navigator.language` | `same-string` | both set, unequal (exact) |
| `webgl2-vendor-agrees-with-webgl` | `webGl:vendor` → `webGl2:vendor` | `same-string` | both set, unequal |
| `webgl2-renderer-agrees-with-webgl` | `webGl:renderer` → `webGl2:renderer` | `same-string` | both set, unequal |
| `webgl-renderer-backend-fits-os` | `ua:osInfo` → `webGl:renderer` | `renderer-backend-fits-os` | OS known, renderer resolves (via `GLRenderer()`, so the `webGl:parameters["37446"]` path counts) and its backend token names another family |

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
