# SP4a screen/monitor-surface measurements

Measured 2026-08-31 against the WSL checkout `~/chromium/src` (HEAD `a727b57805`),
read-only `git grep`/`sed`. SP4a is the **monitor identity** slice of SP4
(spec `2026-08-26-sp4-remaining-surfaces-design.md` §3.1): the values that
describe the *screen*, decoupled from the browser window. The window-geometry
cluster (`window.inner*`/`outer*`/`screenX`/`screenY`/`devicePixelRatio`/
`document.body.clientWidth`/`history.length`) is deliberately **deferred** — see
"Scope decision" below.

## Scope decision (2026-08-31)

The spec's §5 coherence table wants the whole chain `inner ≤ outer ≤ avail ≤
screen` spoofed together. Measuring the call sites shows why that must be split:

- `screen.*` and CSS `device-*` describe the **monitor**. A large monitor with a
  small browser window is an ordinary desktop state, so spoofing the monitor
  stays coherent with a **truthful** viewport. No layout coupling.
- `window.innerWidth` reads the **live layout viewport**
  (`LocalDOMWindow::GetViewportSize()`). `document.body.clientWidth` /
  `getBoundingClientRect()` / `matchMedia('(width: …)')` are the same layout
  value read three other ways. Lying about `innerWidth` per-getter decouples it
  from all of them — a contradiction the project's own coherence philosophy
  forbids. The correct fix is to **size the real viewport**, not to lie per
  getter, so it belongs in its own slice.

**SP4a therefore covers `screen.*` + CSS `device-*` + `screen.orientation`
only.** Confirmed with the user 2026-08-31 ("Monitor-only"). This maps exactly
onto spec verification items **1, 2, and the `availHeight < height` half of 3**.

## Choke points (all pristine on this HEAD → clean `git diff` patch)

| Surface | Choke point | File:line | Reads |
|---|---|---|---|
| `screen.width/height`, `screen.availWidth/Height/Left/Top` | `Screen::GetRect(bool available)` | `core/frame/screen.cc:172` | `screen_info.rect` / `.available_rect` — **single** choke for all six dimension getters (`width/height/availWidth/availHeight/availLeft/availTop` all call it) |
| `screen.colorDepth` / `.pixelDepth` | `Screen::colorDepth()` | `core/frame/screen.cc:102` | `GetScreenInfo().depth`. `pixelDepth()` (:117) just returns `colorDepth()` |
| CSS `device-width` / `device-height` | `MediaValues::CalculateDeviceWidth/Height(LocalFrame*)` | `core/css/media_values.cc:165,177` | `screen_info.rect.width()/height()`. Static helpers; **both** `MediaValuesDynamic` (:171) and `MediaValuesCached` (:39,220) route through them — one edit covers the dynamic and cached media-query paths |
| `screen.orientation.type` / `.angle` | `ScreenOrientation::type()` / `angle()` | `modules/screen_orientation/screen_orientation.cc:90,94` | stored `type_` / `angle_` (set by the controller from the host display). **Derived, no config key** — must compute from the spoofed dims |

### The two-place invariant

`Screen::GetRect` (JS `screen.width`) and `MediaValues::CalculateDeviceWidth`
(CSS `device-width`) are independent reads of `screen_info.rect.width()`.
Patching only the first leaves `matchMedia('(device-width: 1920px)')`
contradicting `screen.width` — spec §4's headline bug. **Both must read the same
key** (`keys::kScreenWidth`) so they can never diverge. Same for height.

### Orientation derivation

`type_`/`angle_` come from the host display, not the dims, so a spoofed
1920×1080 would still report the host's real orientation. Derive instead, and
only when the dims are configured (rule 5 — no-op when absent):

- `width > height` → `landscape-primary`, angle `0`
- else → `portrait-primary`, angle `0`

`0` for the primary of either orientation is the device's natural position and
satisfies verify item 2 (1920×1080 → `landscape-primary`/`0`; 1080×1920 →
`portrait-primary`).

## No new camoucfg accessor

Both choke points read the same `uint32` key through the existing
`camoucfg::GetUint32(ScopeFor(execution_context), keys::kScreen*)`. As with
SP1b, SP4a needs **only new keys**, no new accessor. `core/BUILD.gn` and
`modules/screen_orientation` already have (or trivially add) the
`//components/camoucfg` dep — `core` already deps it; confirm `modules` deps it
for the orientation file.

## Keys (new, DOTTED — mirror real JS property paths)

`screen.width`, `screen.height`, `screen.availWidth`, `screen.availHeight`,
`screen.availLeft`, `screen.availTop`, `screen.colorDepth` — 7 keys.
`kAllKeys` 45 → 52; add all seven to the `declared` literal in
`keys_unittest.cc` too.

**`pixelDepth` gets no key of its own.** Real browsers always report
`pixelDepth == colorDepth`; a second key is a second source of truth that can
disagree — the `voiceURI` lesson. `pixelDepth()` already returns `colorDepth()`,
so spoofing `colorDepth` carries it for free. (Deviates from the spec's §3.1 key
list, which named both; the deviation is the spec's own no-second-key principle,
same argument it makes for orientation.)

## Resolved open decisions (spec §7)

- **`window.scrollMin*` / `scrollMax*`: DROPPED.** `git grep -i 'scrollmin|scrollmax'`
  under `core/frame/` returns nothing — these are Firefox-only properties with
  no Chromium counterpart. Carrying the keys over would make the registry assert
  something false. `pageXOffset`/`pageYOffset` are standard live scroll offsets
  (not a fingerprint) and stay unspoofed.
- **`document.body.clientWidth`: out of SP4a.** `Element::clientWidth/clientHeight`
  exist (`core/dom/element.cc:2541,2584`) but are layout-derived and must track
  actual rendering; belongs with the window-sizing slice, not a per-getter lie.

## Coherence SP4a owns vs delegates

SP4a **reports what it is told**; it does not choose or clamp values (spec §8:
"SP4 enforces invariants it is given; it does not choose values" — the load-time
validator is SP5a). The internal invariants SP4a keeps by construction:

- `screen.width` (JS) ≡ `device-width` (CSS) — same key, both places.
- `screen.orientation` ≡ the dims — derived, no override.
- `pixelDepth` ≡ `colorDepth` — one key.

`availHeight < height` (CreepJS `noTaskbar`) and `avail ≤ screen` are left to the
config author / SP5a validator, not clamped here.

## Deferred to the window-geometry slice (not SP4a)

`window.innerWidth/innerHeight` (viewport — needs real sizing),
`window.outerWidth/outerHeight/screenX/screenY` (`ChromeClient::RootWindowRect`),
`window.devicePixelRatio` (`LocalFrame::DevicePixelRatio`),
`document.body.clientWidth/clientHeight`, `window.history.length`
(`History::length`, `core/frame/history.cc:67` — a navigation-depth surface, not
geometry). Most cohere while truthful; `inner*` is the one that requires sizing.
