# Camoucrome

An anti-detect browser built on Chromium: real Chrome stable, with the fingerprint a page can read set
per profile. It is the Chromium counterpart of [Camoufox](https://github.com/lang315/camoufox), which does
the same for Firefox.

Every substituted value is set in C++, inside Blink and the browser process, never by injecting
JavaScript into the page. Accessors still report `[native code]`, `Object.keys(window)` matches stock
Chrome, and a worker reads what its window reads. A config is checked at startup against a registry of
cross-surface rules, because a spoofed value that contradicts another (a Windows user agent with a Mac
GPU) is worse than no spoofing at all.

## What it covers

- User agent and client hints (`navigator.userAgent`, `userAgentData`, `Sec-CH-UA*`), platform,
  languages and the `Accept-Language` header.
- Screen, window geometry and device pixel ratio.
- Canvas and WebGL, with a per-profile noise seed, and the GPU name on Intel Gen9 hosts.
- Audio, fonts (a per-profile subset of the host's fonts), speech voices and media devices.
- Time zone, locale, geolocation, battery and the WebRTC address.
- Automation hiding over CDP, and human-like mouse, wheel and keyboard input.
- No phone-home: the component updater, GCM check-in, network time and Safe Browsing's list fetch are off.

A generator (`python -m camoucrome.gen`) draws a coherent identity per profile, and the profile keeps it
on every later launch. Python, Go and Node clients launch the browser with it through patchright.

## Platforms and versions

- **Windows x64** is the main target, checked against stock Chrome on a real Windows machine.
- **Linux x64** is for headless server and container use; desktop use is not tested.

Each release is built on a Chrome stable tag, currently `157.0.8103.51`, so the browser reports a
version real users run. The pin may lag: it stays while it is at most 3 milestones behind Chrome stable,
then moves to the newest stable tag. There is no rebuild for a patch release, so **the binary lacks the
security fixes of newer Chrome, including later patches of its own milestone.** Releases are on the
[releases page](https://github.com/lang315/camoucrome/releases/latest).

## Install

`<tag>` is the release tag, `v<chrome-version>-<n>`, as shown on the release page.
`<sha>` is a full commit SHA from this repository. For the Latest release, `v157.0.8103.51-14`,
it is `e13a29b7bb05e642a62c3000dd28b72fc632e3ff`; the Go and Node lines below already name it.
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

2. Download the zip and `SHA256SUMS` from the release. From the next release on, the same tree is
   also published as `camoucrome-<chrome-version>-windows-x64.tar.xz`, about 30 % smaller, for tools
   that unpack xz themselves. Windows 10's `tar` (bsdtar 3.5.2, zlib only) cannot read xz, so the
   steps below use the zip.

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

The archive carries `LICENSE`, `LICENSE.chromium` and `about_credits.html`.

Other clients:

- Go: `go get github.com/lang315/camoucrome/client/go@e13a29b7bb05e642a62c3000dd28b72fc632e3ff`. Go generates identities by
  calling `python -m camoucrome.gen`, so install the Python package above too.
- Node: `npm install https://github.com/lang315/camoucrome/releases/download/v157.0.8103.51-14/camoucrome-0.1.6.tgz`.
  Node also calls `python -m camoucrome.gen`, so install the Python package above too.

**BREAKING in `v157.0.8103.51-14`: the clients are strict by default** (a malformed or incoherent config exits 13 instead of falling
back to real values; lax is the opt-out), and the Node and Python clients refuse an `env` option.

## Install on Linux (headless server use)

The archive is on the same release: `camoucrome-<chrome-version>-linux-x64.tar.xz` (releases up to
`v156.0.8078.48-4` name it `...-linux-x64-beta.tar.xz`).

**`v157.0.8103.51-14` is Windows only and has no Linux archive. On Linux, use `v157.0.8103.51-12`**
(`<tag>` below; its commit is `0eb6cbfb1a2f5639d9aeb602a60228ba2ddf0a62`).

1. As root, install the shared libraries the browser needs, plus Python 3, `git` and `xz`. Fedora and RHEL:

```sh
dnf install python3 python3-pip git xz tar nspr nss atk at-spi2-atk at-spi2-core dbus-libs \
  cups-libs libxcb libxkbcommon alsa-lib mesa-libgbm libX11 libXext cairo pango \
  libXcomposite libXdamage libXfixes libXrandr
```

   Debian and Ubuntu (on Debian 12, drop the `t64` suffixes):

```sh
apt-get install python3 python3-venv python3-pip git xz-utils libasound2t64 libatk-bridge2.0-0t64 \
  libatk1.0-0t64 libatspi2.0-0t64 libcairo2 libcups2t64 libdbus-1-3 libgbm1 libnspr4 libnss3 \
  libpango-1.0-0 libx11-6 libxcb1 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxkbcommon0 \
  libxrandr2
```

2. As a normal user, download, check and extract the archive.

```sh
base=https://github.com/lang315/camoucrome/releases/download/<tag>
curl -fsSLO "$base/camoucrome-<chrome-version>-linux-x64.tar.xz"
curl -fsSLO "$base/SHA256SUMS"
grep linux-x64 SHA256SUMS | sha256sum -c
tar -xf camoucrome-<chrome-version>-linux-x64.tar.xz
```

3. Install the Python client as in step 5 above, with `python3 -m venv .venv` and
   `.venv/bin/pip install ...`. The quickstart below then applies with `headless=True` and
   `CHROME = "camoucrome-<chrome-version>-linux-x64/chrome"`.

The browser's sandbox needs unprivileged user namespaces. In a container that forbids them, allow them or
pass `--no-sandbox` in `args` (less isolation). Ubuntu 24.04 servers restrict them through AppArmor
(`kernel.apparmor_restrict_unprivileged_userns=1`): add an AppArmor profile for `chrome` or set that
sysctl to `0`.

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
                                window=tuple(fp["launch"]["window"]), dpr=fp["launch"]["dpr"],
                                position=tuple(fp["launch"]["position"]), args=fp["launch"]["args"])
        page = ctx.pages[0]
        page.goto("https://example.com")
        print(name, page.evaluate("[navigator.hardwareConcurrency, screen.width]"))
        ctx.close()
```

The two identities differ in screen, CPU cores, memory, fonts and noise seeds. To keep a site's login
alive across launches and updates, see [`docs/profiles-and-sessions.md`](docs/profiles-and-sessions.md).

All three clients take an opt-in `light` option (default off) that adds browser flags which lower memory
use without changing what a page can read.

## Human input

The Python and Node clients ship `click`, `hold` and `type` helpers on a patchright page; the Go client
has the same model. Input goes only through `page.mouse` and `page.keyboard`, with no page JavaScript.

```python
from camoucrome import human
human.click(page, "#buy")                          # press point in the inner 70%, settle, lognormal hold
human.hold(page, "#hold-me", 1200)                 # ms; 1-2 px tremor, released at the last point
human.type(page, "#name", "Hello, World!")         # dwell, digraph flights, real ShiftLeft, key rollover
human.type(page, "#name", "Hello", typos=True)     # opt-in neighbour-key typos, corrected with Backspace
```

## Behind a proxy: time zone and locale from the exit address

A time zone that contradicts your exit address is a tell detectors check. Generate the identity from the
proxy's exit address, and `launch` warns if the zone and the address still disagree. This needs
`pip install maxminddb timezonefinder` (or the client's `geoip` extra) and the free DB-IP
"IP to City Lite" database (<https://db-ip.com/db/download/ip-to-city-lite>, an `.mmdb`, updated monthly).

```python
import camoucrome, camoucrome.gen
from camoucrome import geoip

proxy = {"server": "http://proxy.example:8000", "username": "user", "password": "secret"}
db = r"dbip-city-lite-2026-10.mmdb"
ip = geoip.exit_ip(proxy)              # the address the world sees; raises GeoIPError if none answers
fp = camoucrome.gen.generate(os="windows", seed=1, exit_ip=ip, geoip_db=db)
ctx = camoucrome.launch(pw, CHROME, config=fp["config"], proxy=proxy, geoip=db, exit_ip=ip,
                        window=tuple(fp["launch"]["window"]), dpr=fp["launch"]["dpr"],
                        position=tuple(fp["launch"]["position"]), args=fp["launch"]["args"])
```

An explicit `timezone` or `locale` passed to `generate` always wins. `exit_ip` asks only through an
`http` proxy. Go and Node call the same Python module.

IP Geolocation by [DB-IP](https://db-ip.com), licensed CC BY 4.0.

## Go without Python (client/go/core)

`client/go/core` is a Go module with no dependencies (standard library only) that does what the Python
generator and launcher do, for a Windows claim on a machine with no Python. The identity pool is embedded.

```go
import "github.com/lang315/camoucrome/client/go/core"

host, _ := core.ProbeHost()                 // cores, work area, platform version (Windows)
host.Display = display                      // see below; store it per machine
id, _ := core.Draw("windows", nil, &host)   // once per account; store the JSON (core.Identity)
r, err := core.Resolve(id, host, &core.Exit{Timezone: "Europe/Berlin", Country: "DE"}) // every launch
env, cleanup, err := core.Env(r, core.LaunchOpts{ExecutablePath: exe}, os.Environ()) // exe: the archive's chrome[.exe]; check err
argv := core.Argv(r, core.LaunchOpts{UserDataDir: dir, Headless: true})
err = core.Pinned(r.Cores, func() error { return spawn(env, argv) })
```

- **The identity is the account's device.** Draw it once and store it: it holds the whole pool entry, the
  seeds and a host seed (`hostSeed` is a JSON string), so a later release cannot change it. `Resolve` is
  deterministic for the same identity, host and exit, and applies the host (cores, window, platform
  version, display flags) and the exit (time zone, locale, languages, voices, and
  `webrtc:ipHandlingPolicy=disable_non_proxied_udp`) fresh each time. An invalid zone is an error.
- **No GPU claim.** The page keeps the real WebGL strings. `core` sets no geolocation either.
- **Display.** Run `core.DisplayProbeJS` once in a headless page of the fork with no config, pass the
  result through `core.ParseDisplay` and store it with the machine's `Host`.
- **The spawner owns the transport and the proxy.** `Argv` emits no `--remote-debugging-*` and no
  `--proxy-*` flag (`settings/launcher.json` `transports`, including the Windows `io_pipes` form, is the
  contract for those). It also starts the browser: every Chrome start in the process must go through
  `core.Pinned`, pinned or not, so a start never inherits another's CPU mask.
- **Pairing.** `core.ForkVersion` is the fork version the data was generated for (157.0.8103.51; the
  release's `-N` is in its tag). Pin a commit of this repository, not a tag. `scripts/gen_go_core_data.py`
  regenerates the embedded pool and tables, and `--check` fails when they are stale.

## Strict mode (the default)

Every launcher starts the browser with `CAMOU_CONFIG_STRICT=1`: a config the browser cannot take refuses to
start instead of running with the real values. An incoherent or malformed (not JSON) config exits with code 13, in chrome and
content_shell alike (fork PR #242; the `CHECK` stays only as a child-process backstop). Builds before -14 die on that `CHECK` instead for a malformed
config (exit `0x80000003` on Windows, SIGABRT/SIGTRAP on Linux). Treat 13 as the refusal code. No client reads exit codes: under
Playwright/patchright `launch` throws and the message carries the exit code, and with rodclient `Launch`
succeeds and the first CDP call returns `EOF` plus the browser stderr tail, within about 2 s. `strict=True` is kept
for compatibility and changes nothing. To opt out, pass `lax=True` (Python, Node) or `Lax: true` (Go
`Options`, `core.LaunchOpts`; the probes take `--lax`): the variable is then left unset, also when the parent
environment had one. Strict together with lax is an error. `CAMOU_CONFIG_STRICT=0` in your own environment is not an opt-out for the launchers: they overwrite it. A caller `env` option is refused (it would replace the whole child environment).

## Known limits

- Profiles on one machine stay linkable through what stock Chrome profiles on that machine share too:
  the GPU, audio output, display class, keyboard layout, codecs, network estimate and Windows build.
- Only Intel Gen9 GPUs can be claimed per profile; on any other host every identity keeps the real GPU.
- A Linux host claiming Windows is the weaker identity: no HEVC playback, and the host's GPU.
- No Widevine. No auto-update: releases are the only security channel, and they lag Chrome.
- `navigator.webdriver` is always false, including under `--enable-automation`, where stock Chrome
  reports true. Do not pass that switch yourself; the bundled clients never do.
- Windows SmartScreen warns on first run: choose More info, then Run anyway.

## Building from source

The repository is a change set, not the Chromium source: new files in `additions/` and diffs in
`patches/`, applied in `patches/series` order to a Chromium checkout at the tag in `upstream.env` with
`scripts/apply.sh <chromium-src>`. GN arguments are in `settings/build-args.gn` and
`settings/release-args.gn`. [`CLAUDE.md`](CLAUDE.md) is the working guide for building, verifying and
exporting the change set.

| Path | Contents |
|---|---|
| `additions/`, `patches/` | the change set |
| `settings/` | config keys, invariants, presets, GPU profiles, fonts, launcher contract, GN args |
| `client/` | the Python, Go and Node clients and the identity generator |
| `scripts/` | apply, export, packaging and the verification scripts |
| `baselines/` | stock Chrome reference captures |
| `docs/` | user docs and the tracking observer's guide |

## Licence and codecs

MPL-2.0 (`LICENSE`).

Released binaries include the H.264 and AAC codecs that stock Chrome ships,
because leaving them out is itself a detectable difference. Google's licence
for those codecs covers Google's builds, not this one. Patent obligations for
distributing and using them may apply in your jurisdiction, and you accept that
risk by using a released binary. The source can be built without them (delete
`proprietary_codecs` and `ffmpeg_branding` from `settings/build-args.gn`), at
the cost of that detectable difference. This is not legal advice.
