# window-geometry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Config-drive `window.outerWidth/outerHeight/screenX/screenY` at the Blink level so the window cluster stops contradicting the sp4a-spoofed `screen.*`.

**Architecture:** SP0 per-getter override in `LocalDOMWindow::outerWidth/outerHeight/screenX/screenY` (`core/frame/local_dom_window.cc`) — config value first, else the real `RootWindowRect` computation. Layout-driving surfaces (inner*/client*/devicePixelRatio) are launcher-layer, NOT spoofed here.

**Tech Stack:** Chromium/Blink C++ (`core/frame`), `//components/camoucfg`, GN, Playwright verify over content_shell CDP.

## Global Constraints

- All spoofing at the C++/Blink level, NEVER injected JS. (project invariant)
- SP0 hook pattern: real value first, config override applied when the key is present; no-op when absent (rule 5). Independent per getter.
- Config-key naming: DOT mirrors the JS property path. `window.outerWidth`, `window.outerHeight`, `window.screenX`, `window.screenY`.
- Keys triple-consistency: (1) `keys.h` constant, (2) `kAllKeys` array + `std::array<…, N>` size, (3) `declared` set in `keys_unittest.cc`. Count 74 → 78.
- Type: `camoucfg::GetInt32(scope, key)` → `std::optional<int32_t>` (integer pixel values). `ScopeFor(this)` — `LocalDOMWindow` IS an `ExecutionContext` (or `ScopeFor(nullptr)`, equivalent GlobalScope).
- No `BUILD.gn` change: `core/` already deps `//components/camoucfg`; add the 3 camoucfg includes to `local_dom_window.cc`.
- OUT of scope (launcher-layer / deferred): `innerWidth`/`innerHeight`, `document.*.clientWidth`, `devicePixelRatio`, `history.length`, `getScreenDetails`.
- Verify apparatus: window geometry is NOT secure-context-gated — `about:blank` is fine (no echo_server needed). Launch with `CAMOU_CONFIG`, NO CDP.
- Stock (about:blank) baseline: `outerWidth 812, outerHeight 680, screenX 0, screenY 0, innerWidth 800`.
- Blink files live only in the checkout; edit via `pullfile`/`pushto`; extract to `patches/` in the final task. Confirm NON-ZERO build steps.

---

### Task 1: Config keys `window.outerWidth/outerHeight/screenX/screenY`

**Files:**
- Modify: `additions/camoucfg/keys.h` (4 constants, `kAllKeys` 74→78)
- Modify: `additions/camoucfg/keys_unittest.cc` (4 in `declared` set)

**Interfaces:**
- Produces: `camoucfg::keys::kWindowOuterWidth` = `"window.outerWidth"`, `kWindowOuterHeight` = `"window.outerHeight"`, `kWindowScreenX` = `"window.screenX"`, `kWindowScreenY` = `"window.screenY"`. Task 2 reads these.

- [ ] **Step 1: keys.h — add 4 constants after the battery keys** (after `kBatteryDischargingTime`):

```cpp
// Window-geometry getters (window-geometry slice). Dot-namespaced (mirror the JS
// property path). Coherence-coupled to the sp4a screen.* spoof (operator keeps
// outer* <= screen.*, screenX/Y within avail). inner*/dpr are launcher-layer, not
// here. Each absent => the real RootWindowRect value (rule 5).
inline constexpr char kWindowOuterWidth[] = "window.outerWidth";
inline constexpr char kWindowOuterHeight[] = "window.outerHeight";
inline constexpr char kWindowScreenX[] = "window.screenX";
inline constexpr char kWindowScreenY[] = "window.screenY";
```
Grow `std::array<std::string_view, 74>` → `78`; append the 4 constants after
`kBatteryDischargingTime,` in `kAllKeys`.

- [ ] **Step 2: keys_unittest.cc — add the 4 to the `declared` set** (after the battery keys):
```cpp
      kBatteryDischargingTime,
      kWindowOuterWidth, kWindowOuterHeight, kWindowScreenX, kWindowScreenY,
  };
```

- [ ] **Step 3: Push + build + run keys tests**
```bash
source /private/tmp/.../scratchpad/buildpc.sh
pushcfg keys.h && pushcfg keys_unittest.cc
unittests 'CamoucfgKeysTest.*'
```
Expected: NON-ZERO build, all PASS incl. `EveryDeclaredConstantIsInAllKeys` (78 triple).

- [ ] **Step 4: Commit**
```bash
git add additions/camoucfg/keys.h additions/camoucfg/keys_unittest.cc
git commit -m "feat(window-geometry): add window.outerWidth/outerHeight/screenX/screenY keys"
```

---

### Task 2: Blink — config-override the four LocalDOMWindow getters

**Files:**
- Modify (checkout): `third_party/blink/renderer/core/frame/local_dom_window.cc`
- Create (Mac): `scripts/verify_window_geometry.py`

**Interfaces:** Consumes `camoucfg::keys::kWindow*`.

- [ ] **Step 1: verify script `scripts/verify_window_geometry.py`** (about:blank, NO CDP):
- **W1 (outerWidth):** config `{"window.outerWidth":1440}` → `outerWidth===1440` (stock 812).
- **W2 (outerHeight):** config `{"window.outerHeight":900}` → `outerHeight===900` (stock 680).
- **W3 (screenX):** config `{"window.screenX":120}` → `screenX===120` (stock 0).
- **W4 (screenY):** config `{"window.screenY":80}` → `screenY===80` (stock 0).
- **W5 (screenLeft/Top alias):** the W3/W4 config → `screenLeft===120 && screenTop===80` (they must reflect the screenX/Y override).
- **W6 (no-op absent):** config `{}` → `outerWidth===812, outerHeight===680, screenX===0, screenY===0` (stock).
- **W7 (inner* untouched):** config `{"window.outerWidth":1440}` → `innerWidth===800` (unchanged — this slice does NOT spoof the viewport).

```python
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell

PROBE = r"""(() => ({outerWidth:outerWidth, outerHeight:outerHeight,
  screenX:screenX, screenY:screenY, screenLeft:screenLeft, screenTop:screenTop,
  innerWidth:innerWidth}))()"""

def run(config):
    v,e = lib_shell.session(config, [PROBE], navigate_to="about:blank")
    if e: raise e
    return v[0]

def cfg(d): return json.dumps(d)

def main():
    r = {}
    a = run(cfg({"window.outerWidth":1440}));   r["W1"] = a["outerWidth"]==1440
    b = run(cfg({"window.outerHeight":900}));   r["W2"] = b["outerHeight"]==900
    c = run(cfg({"window.screenX":120,"window.screenY":80}))
    r["W3"] = c["screenX"]==120
    r["W4"] = c["screenY"]==80
    r["W5"] = c["screenLeft"]==120 and c["screenTop"]==80
    s = run(cfg({}))
    r["W6"] = (s["outerWidth"]==812 and s["outerHeight"]==680
               and s["screenX"]==0 and s["screenY"]==0)
    r["W7"] = a["innerWidth"]==800
    EXPECTED=7
    for k in ("W1","W2","W3","W4","W5","W6","W7"): print(f"{k}: {'PASS' if r[k] else 'FAIL'}")
    n=sum(r.values()); print(f"{n}/{EXPECTED} " + ("ALL_PASS" if n==EXPECTED else "FAIL"))
    sys.exit(0 if n==EXPECTED else 1)

if __name__=="__main__": main()
```

- [ ] **Step 2: RED-first** — push + run; RED: W1-W4 FAIL (stock), W5 FAIL (0 not 120), W6/W7 PASS. Record.
```bash
pushfile scripts/verify_window_geometry.py "$VERIFY/verify_window_geometry.py"
verify verify_window_geometry.py
```

- [ ] **Step 3: local_dom_window.cc — includes + the 4 getter overrides**

Add includes (alphabetical): `components/camoucfg/blink_scope.h`, `components/camoucfg/keys.h`, `components/camoucfg/mask_config.h`.

At the TOP of each of `outerWidth()`, `outerHeight()`, `screenX()`, `screenY()` (before the existing `if (!GetFrame())` body), add the config override:
```cpp
int LocalDOMWindow::outerWidth() const {
  if (std::optional<int32_t> v = camoucfg::GetInt32(
          camoucfg::ScopeFor(const_cast<LocalDOMWindow*>(this)),
          camoucfg::keys::kWindowOuterWidth)) {
    return *v;
  }
  // ... existing body unchanged ...
}
```
(`ScopeFor` takes a non-const `ExecutionContext*`; the getters are `const`, so
`const_cast<LocalDOMWindow*>(this)` — or use `ScopeFor(nullptr)` if simpler.
`LocalDOMWindow` derives from `ExecutionContext`.) Same shape for `outerHeight()`
(`kWindowOuterHeight`), `screenX()` (`kWindowScreenX`), `screenY()`
(`kWindowScreenY`).

- [ ] **Step 4: screenLeft/screenTop** — confirm (`window.idl` + build) that `screenLeft`/`screenTop` resolve to the `screenX()`/`screenY()` C++ getters (`[ImplementedAs=screenX]` or equivalent); W5 proves it. If they are SEPARATE getters, add the same override to them (reading `kWindowScreenX`/`kWindowScreenY`).

- [ ] **Step 5: Build + verify GREEN** — `contentshell` (NON-ZERO steps), `verify verify_window_geometry.py` → 7/7 ALL_PASS.

- [ ] **Step 6: Commit the Mac verify script**
```bash
git add scripts/verify_window_geometry.py
git commit -m "test(window-geometry): verify W1-W7 (outer/screenX-Y overrides, inner untouched)"
```

---

### Task 3: Extract patch, wire apply.sh, regression

**Files:** Create `patches/window-geometry.patch`; Modify `scripts/apply.sh`.

- [ ] **Step 1: Extract** the diff (`core/frame/local_dom_window.cc`) to `patches/window-geometry.patch` (redirect Mac-side; `git diff HEAD --` if staged). Confirm ONE file, non-empty.

- [ ] **Step 2: Round-trip** — `git checkout --` the file, `pushto` the patch, `git apply --3way`, `echo APPLY_OK`, `contentshell` (NON-ZERO), `verify verify_window_geometry.py` → 7/7.

- [ ] **Step 3: apply.sh** — append `"$ROOT/patches/window-geometry.patch"` LAST, after `"$ROOT/patches/sp4-battery.patch"`.

- [ ] **Step 4: Full regression** (record counts):
```bash
unittests 'CamoucfgKeysTest.*:AssembleRawConfigTest.*:ParseConfigTest.*:ParseConfigDeathTest.*:GettersTest.*:MaskConfigTest.*:DeriveTest.*:DeriveDeltaTest.*:DeriveUnitTest.*:PerturbRgbaTest.*:MouseTrajectoriesTest.*'
verify verify_window_geometry.py  # 7/7
verify verify_sp4a.py             # 6/6 (screen.* — the coherence neighbour)
verify verify_sp4_battery.py      # 5/5
verify verify_sp4_geo.py          # 6/6
verify verify_sp1b.py             # 8/8
```
Expected: camoucfg all PASS (78 keys), prior verifies unchanged. Missing-baseline → `--capture-baseline` once, note it.

- [ ] **Step 5: Commit**
```bash
git add patches/window-geometry.patch scripts/apply.sh
git commit -m "feat(window-geometry): config-driven window.outer*/screenX-Y — patch + apply wiring"
```

---

## Self-Review notes

- **Spec coverage:** four getter overrides (measurement §3) → keys + local_dom_window.cc. inner*/dpr = launcher (§4), history.length excluded (scope decision).
- **Type consistency:** `GetInt32` (integer pixels); each getter independent (rule 5 per key). W7 pins that inner* is NOT touched.
- **screenLeft/screenTop** covered via screenX/screenY (W5 verifies); add explicit overrides only if they are separate getters.
