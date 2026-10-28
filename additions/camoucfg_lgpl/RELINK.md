# Replacing the LGPL component and rebuilding

`components/camoucfg_lgpl` is LGPL-3.0-or-later (see LICENSE, COPYING, NOTICE).
This file is the relinking path the project offers under LGPL-3.0 section
4(d)(0): you can modify this library and build a browser that uses your
version. You need Linux, about 100 GB of disk and many hours of build time.

1. Get the source: clone this repository at the release tag, e.g.
   `git clone https://github.com/lang315/camoucrome && cd camoucrome &&
   git checkout <release tag>`.
2. Install depot_tools:
   `git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git`
   and put it on `PATH`.
3. Fetch Chromium: `mkdir chromium && cd chromium && fetch --nohooks chromium`
   (the checkout is `chromium/src`).
4. Check out the pinned revision. `upstream.env` in this repository names it
   (`CHROMIUM_REV`, tag `CHROMIUM_TAG`):
   `cd src && git checkout <CHROMIUM_REV> && gclient sync -D --force &&
   gclient runhooks`.
   `scripts/apply.sh` refuses any other HEAD, because the patches are
   generated against that exact revision and would apply to something else
   silently or not at all.
5. Edit the files in `additions/camoucfg_lgpl/` of this repository.
6. Apply the change set to the checkout: `scripts/apply.sh <chromium-src>`
   (it copies `additions/` and applies `patches/` in order).
7. Configure: `gn gen out/Release --args="$(cat <repo>/settings/release-args.gn)"`
   (run in `<chromium-src>`).
8. Build: `autoninja -C out/Release chrome`
9. The relinked browser is `out/Release/chrome` (`chrome.exe` on Windows).
