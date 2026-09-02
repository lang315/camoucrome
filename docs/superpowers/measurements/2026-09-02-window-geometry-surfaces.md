# window-geometry surfaces measurement (2026-09-02)

Checkout HEAD `a727b57805`, `out/Default` content_shell.

sp4a spoofs `screen.*` but left the WINDOW cluster truthful — a coherence gap: a
page reading `window.outerWidth`/`screenX` alongside the spoofed `screen.*` sees
the real (content_shell) values. This slice config-drives the safe getter cluster
(`window.outerWidth/outerHeight/screenX/screenY`), coupled to the spoofed screen.
Per the 2026-09-02 scope decision, the layout-driving surfaces
(`innerWidth`/`clientWidth`/`devicePixelRatio`) are NOT getter-spoofed here — they
belong to the launcher (see §4).

---

## 1. Stock behavior (content_shell, about:blank)

```json
{ "outerWidth":812, "outerHeight":680, "innerWidth":800, "innerHeight":595,
  "screenX":0, "screenY":0, "screenLeft":0, "screenTop":0, "dpr":1,
  "historyLength":1 }
```

Tells:
- **`screenX`/`screenY` = 0** — the window sits at the screen origin; a real
  windowed browser has a non-zero offset (0,0 reads as maximized/headless).
- **`outerWidth 812` vs `innerWidth 800`** (and 680 vs 595) — the outer−inner
  delta is content_shell's chrome size, not a real Chrome's; a fingerprinter reads
  it to characterise the browser chrome.
- (`screen.width` reads 1 on headless without sp4a config — sp4a owns `screen.*`.)

## 2. Blink choke points

`third_party/blink/renderer/core/frame/local_dom_window.cc` — four getters, each
returning a component of `chrome_client.RootWindowRect(*frame)`:
- `outerWidth()` (~1699) → `RootWindowRect.width()`
- `outerHeight()` (~1667) → `RootWindowRect.height()`
- `screenX()` (~1782) → `RootWindowRect.x()`
- `screenY()` (~1807) → `RootWindowRect.y()`

`screenLeft`/`screenTop` are IDL attributes (`window.idl:198-199`) that report the
same values (measured 0/0 = `screenX`/`screenY`); confirm they resolve to the
`screenX()`/`screenY()` getters (an override there covers them) or override them
too if they are separate.

`innerWidth()` (~1773) returns `AdjustForAbsoluteZoom::AdjustInt(GetViewportSize()…)`
— the actual viewport; NOT touched (§4).

## 3. Port design

SP0 per-getter override — config value first (return it), else the real
`RootWindowRect` computation:

```cpp
int LocalDOMWindow::outerWidth() const {
  if (std::optional<int32_t> v = camoucfg::GetInt32(
          camoucfg::ScopeFor(this), camoucfg::keys::kWindowOuterWidth)) {
    return *v;
  }
  // ... existing body (frame/page null-checks, RootWindowRect().width()) ...
}
```
and likewise `outerHeight()` (`kWindowOuterHeight`), `screenX()`
(`kWindowScreenX`), `screenY()` (`kWindowScreenY`). `LocalDOMWindow` *is* an
`ExecutionContext`, so `ScopeFor(this)` (or `ScopeFor(nullptr)` — GlobalScope
today) is fine. `GetInt32` because these are integer pixel values.

- **Keys (DOT — mirror the JS property path):** `window.outerWidth`,
  `window.outerHeight`, `window.screenX`, `window.screenY`. Keys 74 → 78.
- **Rule 5:** each key absent → the real `RootWindowRect` value.
- **No BUILD change:** `core/` already deps `//components/camoucfg` (sp4a screen,
  tz-locale, geo live in `core`); add the 3 camoucfg includes to
  `local_dom_window.cc`.

## 4. Coherence & residual (documented)

- **Coherence with the spoofed screen (the sp4a caveat):** the operator/preset
  must keep `window.outerWidth ≤ screen.width`, `outerHeight ≤ screen.height`, and
  `(screenX,screenY)` within the spoofed `screen.avail*` — a window larger than or
  outside its monitor is a contradiction. Also `outer* ≥ inner*` (chrome delta).
  Not enforced here (operator/preset responsibility; a SP5a validator follow-on
  could range-check).
- **Viewport is LAUNCHER-layer, not this slice (scope decision):**
  `innerWidth`/`innerHeight`, `document.documentElement.clientWidth/clientHeight`,
  and `devicePixelRatio` DRIVE layout and rendering. A getter-lie there is
  incoherent — the page still lays out / renders at the real size, so
  `getBoundingClientRect`, media queries, and canvas resolution contradict the
  lied getter (a demonstrable tell). The coherent fix is to launch at the target
  size/scale (`--window-size`, `--force-device-scale-factor`); documented for the
  launcher/preset layer, NOT spoofed here.
- **`history.length` left truthful** — a navigation-depth surface, not geometry;
  spoofing it is dubious (a freshly-loaded page reporting a high `history.length`
  is itself anomalous). Excluded by the scope decision.
- **`getScreenDetails()`/`ScreenDetailed`/`screen.isExtended`** (permission-gated
  multi-monitor, sp4a's third path) — audit is deferred; `isExtended==false` is
  coherent with any single spoofed monitor.
- **Fenced-frame guard (respected).** `outerWidth()`/`outerHeight()` carry a stock
  guard `if (frame->IsInFencedFrameTree()) return innerWidth();` — a deliberate
  isolation so a fenced frame cannot read the embedder's outer window size. The
  config override is placed AFTER that guard (not at the very top), so a fenced
  frame keeps stock's `return innerWidth()` and only a non-fenced frame gets the
  configured value — matching real Chrome in fenced-frame context. `screenX()`/
  `screenY()` have no such guard, so their override sits at the top. (The
  fenced-frame path is correct-by-construction; a `<fencedframe>` is not exercised
  by the W1–W7 verify.)

## 5. Slice scope summary

| surface | this slice |
|---|---|
| `window.outerWidth/outerHeight/screenX/screenY` | **spoof** — SP0 getter override, keys `window.*` (dot) |
| `screenLeft/screenTop` | covered via `screenX/screenY` (verify) |
| `innerWidth`/`clientWidth`/`devicePixelRatio` | **launcher-layer** — real sizing (documented, not spoofed) |
| `history.length` | left truthful (scope decision) |
| `getScreenDetails`/`isExtended` | defer (audit) |
