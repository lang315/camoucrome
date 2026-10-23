# Camoucrome

An anti-detect fork of Chromium. The Chromium counterpart to
[Camoufox](https://github.com/lang315/camoufox), which does the same job for Firefox.

**Status: the SP0–SP7 spoofing arc plus its follow-on residual-closing slices have
landed on `main`** — 37 patches in `patches/` (applied in the order of
`patches/series`, which `scripts/export.sh` regenerates from the checkout's
`camoucrome/main` branch) plus the proprietary-codec GN args in `settings/build-args.gn`.
Apply the whole set to a pristine Chromium checkout with
`scripts/apply.sh <chromium-src>`. The specs in `docs/superpowers/specs/` define the
design; `docs/superpowers/measurements/` records the per-surface measurement each
slice was built from. `docs/superpowers/` is local, not in git, since the
2026-10-18 recreate; a fresh clone restores it with
`git archive f46525dde7 docs/superpowers | tar -x`.

Shipped: the config layer and load-time coherence validator (SP0, SP5a); the
browser-process UA / UA-CH producer and Blink-side navigator leaves (SP1a, SP1b);
automation hiding and the humanized cursor (SP2a, SP2b); canvas and WebGL
fingerprints (SP3a, SP3b); the SP4 device-faking arc — screen, fonts, audio, media
devices, timezone/locale, WebRTC IP, voices, geolocation, battery; the proprietary
codec build (SP7 D2); and the follow-on slices that close residual tells the SP4
measurements deferred — window geometry, canvas metric jitter, media-device
getSettings/id coherence, phantom-webcam error coherence, render-thread audio input
masking, and SpeechSynthesis boundary/jitter/generation fixes. SP5b adds a
single-key config-domain validator (a generalized mechanism, populated with the
geolocation range-checks) so an out-of-range value is refused loudly at startup
instead of being dropped silently downstream. SP7 also compiles the field-trial
testing config out of the build (`disable_fieldtrial_testing_config`), so feature
state is the build's compiled defaults rather than the public per-milestone
testing set that an unbranded Chromium applies, and `sp7-phone-home.patch`
stops the component updater, GCM check-in, the startup `ListAccounts`, network
time, the omnibox AI-mode eligibility fetch, the spellcheck dictionary
download and Safe Browsing's list fetch (off by default, the "No protection"
state) — a fresh headless `chrome` on Linux now issues zero outbound requests
in 330 s (`scripts/verify_sp7_phonehome.py`). fonts-ii extends the sp4-fonts
allowlist to the `@font-face { src: local() }` path, closing the direct-vs-local()
cross-method inconsistency (a listed font still resolves; an unlisted one no
longer leaks) — the codepoint-fallback and native-host completeness parts remain
open. An open font bundle with a per-OS fontconfig layer and a `fonts:alias`
key lets a claimed family resolve without redistributing proprietary fonts.

**Windows is the flagship target.** A native `chrome.exe` 156.0.8078.48 builds
from the same change set on the build PC's Windows host. The Windows-specific
patches make a Windows claim behave like stock Windows Chrome past mere
presence (`windows-oracle`, `windows-behaviour`, `windows-behaviour-ii`),
keep `CAMOU_*` in the sandboxed renderer's environment (`windows-sandbox-env`)
and stop crash dumps (`crashpad-no-dumps`). The named Windows verify set
(`scripts/windows_verify_set.py`, 21 entries) reads 21/21 RED against the
host's stock Chrome 156 and 21/21 GREEN against the fork. One oracle row is a
known failure: a Linux claim does not hide `navigator.share` and
`navigator.bluetooth` on the Windows build. The Python, Go and Node clients all
run there (`docs/superpowers/measurements/2026-10-04-windows-verify-set.md`).

**Verification is per-slice and RED-first.** Each slice ships a `scripts/verify_*.py`
that drives a real `content_shell` over CDP, is confirmed to go red against the
pre-change binary, and is re-run after a full revert-and-reapply round-trip
(`gn check` + rebuild) so the committed patches — not just the working tree — are
what passed. Unit coverage backs the config layer and the invariant validator.

**What `content_shell` cannot reach is stated, not hidden.** Surfaces it
reimplements or omits are verified against `chrome` instead: the `Sec-CH-UA*`
header and `userAgentData` channels (`scripts/verify_sp1a_chrome.py`), and the
whole Windows set on `chrome.exe`. Some still need a backend the headless Linux
host lacks — `AudioWorklet` input (its worklet thread never starts headless) and
the backend-present SpeechSynthesis paths. These are documented as residuals in
the owning slice's measurement doc rather than claimed as verified. Coherence
across channels is the project's thesis (see below), and the rows that remain
unproven are named where they live.

There is no release yet. The path to the first one is the long-term roadmap,
[`docs/superpowers/plans/2026-10-02-long-term-roadmap.md`](docs/superpowers/plans/2026-10-02-long-term-roadmap.md):
steps 0 (re-pin and safety) and 1 (Windows foundation) are done; step 2 measures
the fork against an oracle and public detectors with a like-for-like stock
control; step 3 is the first release, a Windows flagship plus a Linux beta. The
per-slice residuals (geo-ii, battery-ii, fonts-ii, webrtc-ii) stay in
[`docs/superpowers/plans/2026-09-02-followon-roadmap.md`](docs/superpowers/plans/2026-09-02-followon-roadmap.md).

The change set is generated against Chromium **`d0c02bfad0`, the Chrome stable
tag `156.0.8078.48`** (full SHA and tag in `upstream.env`; `scripts/apply.sh`
refuses any other HEAD). The pin is the current stable tag so the fork reports
a version real users run; it moves to the newest stable tag each milestone. The
next re-pin, to 157, is due by 2026-11-03 (`docs/superpowers/specs/repin-runbook.md`).

## Install

`<tag>` is the release tag, `v<chrome-version>-<n>` (for example `v157.0.8103.NN-1`).
`<sha>` is a full commit SHA from this repository, for the Go module.
`<chrome-version>` is the Chrome version the release is built on.

Run everything below in an elevated PowerShell ("Run as administrator"), because the
first step installs machine-wide, in one working folder. A clean Windows machine has
no prerequisites installed. Go users also need Go 1.22 or newer; Node users also need
Node.js LTS and `npm install patchright@1.62.1` (the peer dependency).

1. Install Python 3.12 (with the py launcher) and Git for Windows, silently. Open a new
   PowerShell window afterwards so `py` and `git` are on the path.

```powershell
$ErrorActionPreference = 'Stop'
Invoke-WebRequest https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe -OutFile python-installer.exe
$p = Start-Process .\python-installer.exe -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1 Include_launcher=1' -Wait -PassThru
if ($p.ExitCode -ne 0) { throw "Python installer exit code $($p.ExitCode)" }
Invoke-WebRequest https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe -OutFile git-installer.exe
$g = Start-Process .\git-installer.exe -ArgumentList '/VERYSILENT /NORESTART' -Wait -PassThru
if ($g.ExitCode -ne 0) { throw "Git installer exit code $($g.ExitCode)" }
```

2. Download the zip and `SHA256SUMS` from the release.

```powershell
$ErrorActionPreference = 'Stop'
$base = 'https://github.com/lang315/camoucrome/releases/download/<tag>'
Invoke-WebRequest "$base/camoucrome-<chrome-version>-windows-x64.zip" -OutFile camoucrome-<chrome-version>-windows-x64.zip
Invoke-WebRequest "$base/SHA256SUMS" -OutFile SHA256SUMS
```

3. Check the zip. It must print `True` (`-eq` on strings ignores case, and `sha256sum`
   writes lowercase hex).

```powershell
(Get-FileHash camoucrome-<chrome-version>-windows-x64.zip -Algorithm SHA256).Hash -eq ((Get-Content SHA256SUMS | Select-String windows-x64.zip).Line -split '\s+')[0]
```

4. Extract it in the same folder (Windows 10 and later). `chrome.exe` ends up at
   `.\camoucrome-<chrome-version>-windows-x64\chrome.exe`. If you use Explorer instead,
   extract into the current folder, not a new one.

```powershell
tar -xf camoucrome-<chrome-version>-windows-x64.zip
```

5. Install the Python client. The wheel carries its settings tables; no checkout is
   needed. patchright installs its driver on first use.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\pip install "git+https://github.com/lang315/camoucrome@<sha>#subdirectory=client/python"
```

The archive carries `LICENSE`, `LICENSE.chromium` and `about_credits.html`. A Linux
beta, `camoucrome-<chrome-version>-linux-x64-beta.tar.xz`, is on the same release.

Other clients:

- Go: `go get github.com/lang315/camoucrome/client/go@<sha>`, where `<sha>` is the
  release's commit, named in the release notes. Go generates identities by
  calling `python -m camoucrome.gen`, so install the Python package above too.
- Node: `npm install https://github.com/lang315/camoucrome/releases/download/<tag>/camoucrome-0.1.0.tgz`.
  Node also calls `python -m camoucrome.gen`, so install the Python package above too.

## Quickstart: two identities

Two Windows identities, each with its own persistent profile. `profile_seeds` draws the
canvas, audio and media-device seeds once into the profile's `user_data_dir` and reads
them back on every later launch, so each profile keeps its fingerprint. The fixed `seed` given to `generate` is what keeps
a profile's screen, cores and user agent the same on every run. Save the script
as `quickstart.py` in the working folder, where you extracted the zip and created
`.venv`, and run it with `.venv\Scripts\python quickstart.py`.

```python
import camoucrome
import camoucrome.gen
from patchright.sync_api import sync_playwright

CHROME = r"camoucrome-<chrome-version>-windows-x64\chrome.exe"

with sync_playwright() as pw:
    for name, seed in (("alice", 1), ("bob", 2)):
        udd = rf"profiles\{name}"
        fp = camoucrome.gen.generate(os="windows", seed=seed)
        ctx = camoucrome.launch(pw, CHROME, user_data_dir=udd, headless=False,
                                config={**fp["config"], **camoucrome.profile_seeds(udd)},
                                window=tuple(fp["launch"]["window"]), dpr=fp["launch"]["dpr"])
        page = ctx.pages[0]
        page.goto("https://example.com")
        print(name, page.evaluate("[navigator.hardwareConcurrency, screen.width]"))
        ctx.close()
```

The two identities differ in screen size and CPU cores, and in the noise seeds stored in
each profile. They share the host's GPU, the stock Windows font list, voices and the
snapped `deviceMemory`.

## The defining constraint

Fingerprint spoofing is implemented in **C++ at the Blink and browser level, never by
injecting JavaScript into the page**. A page must not be able to observe that a value
was substituted — accessors keep reporting `[native code]`, and no property appears on
`window` that is not on a stock build.

This is inherited from Camoufox and is the whole reason the project exists. Anything
achievable by injecting a script into the page can already be done with an existing
tool; the hard, durable part is doing it below the point where page JavaScript can look.

## Relationship to Camoufox

Camoufox is the reference design, not a codebase to copy. Firefox and Chromium share no
code. What ports is the architecture: a C++ config layer that patched call sites
consult, fed by an out-of-process fingerprint generator.

Two things deliberately carry over byte-for-byte so tooling can be shared:

- the `CAMOU_CONFIG_1..N` environment-variable transport, chunked to survive the
  Windows environment-variable size cap
- the flat JSON config format with dotted and colon-separated keys

Two things explicitly do **not** port:

- Camoufox hides Juggler, Firefox's automation protocol. Chromium uses CDP, a different
  model with different leaks. That work is new (SP2).
- Camoufox cross-compiles Windows and macOS binaries from Linux. Chromium cannot — a
  Windows build needs Windows and Visual Studio, a macOS build needs macOS and Xcode
  (SP6).

## Layout

| Path | Contents |
|---|---|
| `docs/superpowers/specs/` | design specs, one per sub-project |
| `docs/superpowers/plans/` | implementation plans, one per slice |
| `docs/superpowers/measurements/` | per-surface measurements each slice was built from |
| `additions/` | whole new files, copied into the Chromium tree verbatim |
| `patches/` | diffs against files that already exist in Chromium |
| `settings/` | the invariant registry (`invariants.json`), the key registry (`keys.json`), captured device presets (`presets/`), the launcher contract (`launcher.json`), canonical GN args (`build-args.gn`, `release-args.gn`), the font bundle manifest and per-OS fontconfig (`fonts.json`, `fontconfig/`), captured GPU profiles (`webgl/`), and the audio, voice and locale-to-zone tables |
| `client/` | launchers for Python (`camoucrome` on patchright), Go (`playwright-go` on the `patchright-core` driver) and Node (patchright), all implementing `settings/launcher.json`, plus the generator (`python -m camoucrome.gen`) |
| `baselines/` | stock reference captures, recaptured at every re-pin |
| `dist/` | release archives from `scripts/package.py` (not committed) |
| `scripts/` | apply and export, the re-pin script, packaging, per-slice `verify_*.py` browser verifications, and the Windows verify set |

New files go in `additions/` and edits to existing files go in `patches/`. This split
held up across Camoufox's ~64 patches and keeps rebase conflicts confined to the small
diffs.

`CLAUDE.md` at the repo root is the operational guide for agents working here; it
distills the apply/verify loop, the config-layer API, and the patch-extraction traps.

## Sub-projects

Read [`00-conventions.md`](docs/superpowers/specs/00-conventions.md) first — every spec
assumes the architecture decisions recorded there.

| SP | Scope | Depends on |
|----|-------|-----------|
| SP0 | Config layer plus a tracer-bullet surface | — |
| SP6a | Patch management and the key registry | SP0 |
| SP5a | Invariant registry, reader, load-time validator | SP0 |
| SP1a | Browser-process UA producer: `navigator.userAgent`, `userAgentData`, `Sec-CH-UA*` headers | SP0 |
| SP1b | Blink-side leaf accessors and languages | SP1a, SP6a, SP5a |
| SP2 | Automation hiding and CDP invisibility | SP0 |
| SP3 | WebGL and canvas fingerprints | SP0 |
| SP4 | Audio, fonts, screen, media devices, battery, WebRTC | SP1a, SP1b, SP3, SP5a |
| SP5b | Invariant catalogue and fingerprint presets | SP1a, SP1b, SP3, SP4 |
| SP6b | Packaging and driver API | SP1a–SP5b |
| SP7 | Phone-home removal and build-level hardening | — |

SP5 and SP6 are each split. Both specs argue that half their content is needed far
earlier than the other half: a branch in the Chromium tree is at risk from the next
`gclient sync` the moment SP0's first commit exists, and a key registry that arrives
after twenty keys have been added as string literals has already failed. Deferring
either to the end is the mistake the split prevents.

SP2 and SP3 are independent of each other and of SP1. SP7 is GN arguments and build
configuration, so it depends on nothing and can start at any time.

TLS, JA3 and HTTP/2 fingerprinting are deliberately not a sub-project. Camoucrome is a
real Chromium build on BoringSSL and Chromium's own network stack, so those
fingerprints are already Chrome's. The exposure is a proxy or driver in front that
re-terminates TLS — a deployment constraint to verify, not a surface to build.

## Why coherence matters more than coverage

A spoofed value that contradicts another spoofed value is a stronger detection signal
than not spoofing at all. A user agent claiming Windows alongside a WebGL renderer
string naming a Mac GPU is worse than an honest Linux fingerprint. Camoufox learned
this the expensive way and ended up enforcing coherence in three uncoordinated places
— C++ patches, an all-or-nothing schema, and Python fixup functions. SP5 exists so
Camoucrome does not repeat that.

## Known limits

- Every identity on one host shares that host's GPU: only one real GPU profile exists.
- No Widevine.
- No auto-update. Re-pins are the security channel, and a release more than one
  milestone behind Chrome stable is unsupported.
- Windows SmartScreen warns on first run: choose More info, then Run anyway.
- The build includes the H.264 and AAC codecs; see [Licence and codecs](#licence-and-codecs).
- Linux is a beta. A Linux host claiming Windows is the weaker identity.
- The archive is about <size> MB (stated per release).

## Licence and codecs

MPL-2.0 (`LICENSE`).

Released binaries include the H.264 and AAC codecs that stock Chrome ships,
because leaving them out is itself a detectable difference. Google's licence
for those codecs covers Google's builds, not this one. Patent obligations for
distributing and using them may apply in your jurisdiction, and you accept that
risk by using a released binary. The source can be built without them (delete
`proprietary_codecs` and `ffmpeg_branding` from `settings/build-args.gn`), at
the cost of that detectable difference. This is not legal advice.
