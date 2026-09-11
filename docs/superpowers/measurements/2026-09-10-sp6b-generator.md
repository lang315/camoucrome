# SP6b generator, v1 (A4 #2) — 2026-09-10

Roadmap A4 #2: the client-side generator. Camoufox's `fingerprints.py` is
~1450 lines because Firefox reports whatever it is told and the client must
synthesise everything; Camoucrome's fork derives the version-bearing and the
derivable surfaces itself, so the Chrome generator is small and most of the
Camoufox code has no key to target here.

## 1. Shape

`python -m camoucrome.gen --os windows|macos|linux --timezone <IANA> [--locale tag] [--seed N]`
prints `{"config": {...}, "launch": {"window": [w, h], "dpr": x}}`: the
`CAMOU_CONFIG` and the two launcher flags that go with it. Go execs it
(`camoucrome.Generate`, `ParseGenerated`); the generator logic exists once,
in Python, tested once. The source is BrowserForge's `browser='chrome'`
pool (1.2.4), which carries real Chrome-shaped samples — including UA-CH
`platformVersion`/`architecture`/`bitness`, `devicePixelRatio`, and real
ANGLE `videoCard` pairs. Samples naming Brave or Edge in `brands` (Brave
farbles font enumeration), mobile samples, and samples without a UA-CH
platform are redrawn; in 60 draws the pool was 55 Chrome / 5 Brave,
platforms Windows 30, macOS 21, empty 6, Linux 2, Android 1, DPR 1 in 38,
2 in 15, 1.25 in 4.

The field → key table, the never-taken list and the reasons are at the top
of `client/python/camoucrome/gen.py`. The decisions worth restating:

- **DPR is a launcher flag, not a resample.** The pool's CSS-pixel geometry
  stays intact and `launch.dpr` becomes `--force-device-scale-factor`, so
  Camoufox's `resample_screen_for_dpr1` is not needed.
- **`--timezone` is required.** No locale→zone table exists (Camoufox gets
  the zone from GeoIP, not from the locale), and `locale:tag` without
  `timezone:id` trips `timezone-set-with-locale` at startup; the CLI refuses
  rather than emit a half-config.
- **No `webGl:*`.** BrowserForge's `videoCard` strings are real Chrome
  ANGLE pairs, not invented; the refusal rests on the parameter-table gap:
  a GeForce identity beside the host's SwiftShader limits is the
  incoherence A3 #2 owns. Unblocker: a real-hardware capture
  (`scripts/capture_preset.py`) and the profile database.
- **No `fonts:list`, `voices:*`, `geolocation:*`.** A font whitelist naming
  a font the host lacks is a measurable tell until packaging bundles fonts
  (A5); Chrome voice names and GeoIP are their own catalogues.
- **Three helpers copied, not shared.** `fix_screen_no_taskbar`,
  `clamp_window_dimensions`, `clamp_window_position` from
  `camoufox/pythonlib/camoufox/fingerprints.py` (lang315/camoufox
  `aa67f7b`), reduced to the keys this fork has (no `window.inner*`, no
  `oscpu`). SP6 §4.5 recommended a shared target-parameterised core; for
  ~60 lines a cross-repo core is not warranted. Revisit when a second
  target appears or the copies diverge. Everything else in Camoufox's
  generator (`fix_navigator_arch`, `resample_screen_for_dpr1`,
  `_build_init_script`, the font/voice subsetting, BrowserForge→Firefox
  casting) has no counterpart here.
- **The OS canonical forms are duplicated from `derive.cc`** and a test
  parses `kForms` out of the C++ and asserts equality, so the generator and
  the validator cannot disagree silently.

## 2. Unit checks (`client/python/tests/test_gen.py`, `client/go`)

Literal pool sample in, config out: every emitted key is in
`settings/keys.json`; the never-taken fields stay out; the helpers produce
avail = screen − taskbar, outer ≤ avail, 0 ≤ screenX/Y ≤ screen − outer
(the sample's 1600×900 window on a 1536×864 screen at 500,200 becomes
1536×824 at 0,40); `--locale` replaces all three locale keys with the head
equal to `navigator.language`; battery/media/seed mapping; the filter
redraws Brave, mobile and empty-platform samples; `--timezone` required;
the real pool is deterministic under `--seed`. Go parses a literal
two-part JSON into `Options` and builds the geometry flags from it.

## 3. The oracle: the fork's own validator (`scripts/verify_sp6b_generator.py`)

Ten configs per OS (windows, macos, linux), each launched through
`python -m camoucrome.probe --strict --window --dpr` on the box's `chrome`
with the driver's browser log captured (`DEBUG=pw:browser`):

| item | result (30 configs) |
|---|---|
| G1 browser starts under `CAMOU_CONFIG_STRICT` | 30/30 |
| G2 zero `invariant '` and zero `falling back` lines | 30/30 |
| G3 page sees `screen.width/height`, `navigator.language`, `languages[0]`, timezone, `devicePixelRatio`, `window.outerWidth` == emitted | 30/30 |
| G4 `innerWidth ≤ outerWidth` | 30/30, after the finding below |
| RED: a Windows config with `ua:platform` flipped to `Linux` under strict | refused; log names `ua-os-family-agrees` |

**Finding: headless honours `--window-size`, and adds 2 px at DPR 1.25 and
1.75.** First run 26/31: five configs reported `innerWidth` 2 px above the
configured `window.outerWidth` (2048 → 2050, 1528 → 1530, 1536 → 1538). A
first guess (DIP rounding, fix by aligning the window to the DPR's
denominator) did not survive its own test — 2048 is a multiple of 4 and
still came back 2050. Measured directly, no config, sizes 1528/1600/2048 at
DPR 1.25, 1.75, 2.5, 3 (and 1, 1.5, 2 earlier): a constant +2 px on both
axes at 1.25 and 1.75, exact at every other DPR, independent of size. The
generator now emits `launch.window = outer − offset[dpr]` and redraws
samples with a DPR outside the measured set. Also visible in those runs:
headless `innerHeight = outerHeight − 143` (Chrome's own window chrome,
reported as is) and the real headless screen shrinks with the DPR (800×600
→ 640×480 at 1.25), which the `screen.*` keys override.

Wall time at N=10: 81 s for 31 launches, inside the sweep's 400 s budget.
`camoucrome.Generate` from Go against the real CLI on the box:
`window [1920 1032] dpr 1, 33 keys, ua:platform Windows, tz Europe/Paris`.

**`navigator.deviceMemory`: the pool says what Chrome never does.** 200
draws: 8 ×76, 16 ×76, 32 ×33, 4 ×15. Chrome clamps the API to a power of
two in [0.25, 8], so over half the pool's values are impossible on a
Chrome UA, and the strict oracle cannot see it — `domain_validator.cc`
ranges only the geolocation axes. The generator snaps to the largest
allowed value ≤ the pool's; a `deviceMemory` domain entry is a C++
follow-up. A 200-draw unseeded property test now holds the pool-wide
invariants the fixed-seed oracle cannot (deviceMemory in the set,
hardwareConcurrency ≥ 1, DPR in the measured set, outer ≤ avail ≤ screen,
`languages[0] == language == locale:tag`, screenX in range, every key
registered). Writing it found that browserforge 1.2.4 raises `TypeError`
on every draw when `os=None` is passed explicitly — the keyword must be
absent for "any OS".

Unit: 17 Python tests; Go 5 tests including `ParseGenerated`. G2 counts
every `camoucfg:` line (invariant, domain, wrong-type), not just the
invariant ones.

## 4. Not done, named

`webGl:*` (A3 #2), `fonts:list` (A5 bundling), `voices:*`, `geolocation:*`
(GeoIP), a `navigator.deviceMemory` domain entry in the C++ validator, a
locale→timezone table, `Accept-Language` (a generator obligation
named by SP5b; the fork derives nothing for it yet), and the shared
generator core SP6 §4.5 asked for. Headed launches are unmeasured; the +2 px
offset was measured headless only.

## 5. 2026-09-11: three tables the generator now reads

- **`settings/webgl/*.json`** — real-GPU profiles (`2026-09-11-webgl-profiles.md`); `--gpu <id>`, default the first profile for the claimed OS; emits identity, the numeric table, the extension list and the 12 precision cells on both contexts. The "No `webGl:*`" refusal above is closed.
- **`settings/locale_zones.json`** — 46 locale tags → plausible IANA zones; `--timezone` is now optional (seeded choice from the row of `--locale`, else the pool's `navigator.language`); a locale outside the table still refuses with the old message. No GeoIP by decision (spec 2026-09-11 §4): a proxy-exit lookup is the caller's, this is the offline default. `test_gen.py` validates every zone against `zoneinfo`.
- **`settings/fonts.json`** — the captured family list of the claimed OS becomes `fonts:list` (plus the macOS system-font keywords) and the generated `alias_map` becomes `fonts:alias` (`2026-09-11-fonts-bundle.md`). Linux claims get neither.
