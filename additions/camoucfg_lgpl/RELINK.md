# Replacing the LGPL component and rebuilding

`components/camoucfg_lgpl` is LGPL-3.0-or-later (see LICENSE, NOTICE). This
file is the relinking path the project offers under LGPL-3.0 section 4(d)(0):
you can modify this library and build a browser that uses your version.

1. Clone this repository and the Chromium tag pinned in `upstream.env`
   (`CHROMIUM_REV`) into `<chromium-src>`.
2. Edit the files in `additions/camoucfg_lgpl/`.
3. Apply the change set to the checkout:
   `scripts/apply.sh <chromium-src>`
4. In `<chromium-src>`:
   `gn gen out/Release --args="$(cat <repo>/settings/release-args.gn)"`
5. Build: `autoninja -C out/Release chrome`

The result is a browser built with your modified `camoucfg_lgpl`.
