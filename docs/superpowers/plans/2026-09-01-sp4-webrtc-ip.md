# SP4-webrtc-ip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `CAMOU_CONFIG` drive Chromium's native `webrtc_ip_handling_policy` so WebRTC ICE candidates stop leaking the client's local (and, behind a proxy, public) IP — page-invisible, at the C++ level.

**Architecture:** Override `*ip_handling_policy` in `RendererBlinkPlatformImpl::GetWebRTCRendererPreferences` (`content/renderer/renderer_blink_platform_impl.cc`) from the config key `webrtc:ipHandlingPolicy`, using the existing `blink::ToWebRTCIPHandlingPolicy` string→enum mapping. Reuses the native lever the peer-connection factory already consumes; NOT a libwebrtc port-allocator rewrite (Camoufox's fake-IP approach is deferred to webrtc-ii).

**Tech Stack:** Chromium content/renderer C++, `//components/camoucfg`, GN, Playwright verify over content_shell CDP.

## Global Constraints

- All spoofing at the C++ level, NEVER injected JS. (project invariant)
- SP0 hook pattern: real value first, config override applied only when the key is present; no-op when absent (rule 5). Key absent → the real renderer pref is used unchanged.
- Config-key naming: colon names a synthetic namespace. `webrtc:ipHandlingPolicy` (colon; matches Camoufox's `webrtc:` family). Bare words are BANNED (`EveryKeyIsNamespaced`).
- Keys registry triple-consistency: (1) `keys.h` constant, (2) `kAllKeys` array + `std::array<…, N>` size, (3) `declared` set in `keys_unittest.cc`. Count 63 → 64.
- The config value is one of the four native policy strings: `"default"`, `"default_public_and_private_interfaces"`, `"default_public_interface_only"`, `"disable_non_proxied_udp"` (constants `blink::kWebRTCIPHandling*` in `third_party/blink/public/common/peerconnection/webrtc_ip_handling_policy.h`). `blink::ToWebRTCIPHandlingPolicy(std::string_view)` maps string → `blink::mojom::WebRtcIpHandlingPolicy` (unknown/empty → default).
- Malformed-input fail-loud (sp4-tz-locale lesson): an unrecognized non-empty value must `LOG(WARNING)` and leave the real pref, NOT silently degrade to default.
- `camoucfg::GetString(scope, key)` → `std::optional<std::string>`. `camoucfg::ScopeFor(nullptr)` returns GlobalScope (CAMOU_CONFIG is process-wide).
- `content/renderer/BUILD.gn` has NO camoucfg dep today (first camoucrome hook in content/renderer) — add `//components/camoucfg`.
- Verify apparatus: launch content_shell with the fake-device flags (`--use-fake-device-for-media-stream --use-fake-ui-for-media-stream`, which make stock leak the raw local IP `172.22.x`) + `CAMOU_CONFIG`, and NO CDP override. Assert candidate suppression. The public-IP/proxy benefit is NOT verifiable in the WSL harness (no STUN/proxy) — verify proves the policy is APPLIED via local-candidate suppression.
- Blink/content files live only in the checkout; edit via `pullfile`/`pushto`; extract to `patches/` in the final task. Confirm NON-ZERO build steps after each change.

---

### Task 1: Config key `webrtc:ipHandlingPolicy`

**Files:**
- Modify: `additions/camoucfg/keys.h` (add 1 constant, grow `kAllKeys` 63→64)
- Modify: `additions/camoucfg/keys_unittest.cc` (add 1 to `declared` set)

**Interfaces:**
- Produces: `camoucfg::keys::kWebrtcIpHandlingPolicy` = `"webrtc:ipHandlingPolicy"`. Task 2 reads it.

- [ ] **Step 1: Add the constant after `kLocaleTag` in `keys.h`**

```cpp
// WebRTC IP-handling policy (SP4-webrtc-ip). Synthetic webrtc: namespace. Value
// is one of the native policy strings ("default", "default_public_interface_only",
// "default_public_and_private_interfaces", "disable_non_proxied_udp"); drives the
// renderer's webrtc_ip_handling_policy. Absent => real pref unchanged (rule 5).
inline constexpr char kWebrtcIpHandlingPolicy[] = "webrtc:ipHandlingPolicy";
```

- [ ] **Step 2: Grow the array size to 64 and append to `kAllKeys`**

Change `inline constexpr std::array<std::string_view, 63> kAllKeys = {` to `64`. Append after `kLocaleTag,`:

```cpp
    kLocaleTag,
    kWebrtcIpHandlingPolicy,
};
```

- [ ] **Step 3: Add it to the `declared` set in `keys_unittest.cc`**

After `kTimezoneId, kLocaleTag,`:

```cpp
      kTimezoneId, kLocaleTag,
      kWebrtcIpHandlingPolicy,
  };
```

- [ ] **Step 4: Push camoucfg + build/run the keys tests**

```bash
source /private/tmp/.../scratchpad/buildpc.sh   # the session harness
pushcfg keys.h
pushcfg keys_unittest.cc
unittests 'CamoucfgKeysTest.*'
```
Expected: `BUILD_DONE` NON-ZERO steps, all `CamoucfgKeysTest.*` PASS. `EveryDeclaredConstantIsInAllKeys` enforces the 64/array/declared triple.

- [ ] **Step 5: Commit**

```bash
git add additions/camoucfg/keys.h additions/camoucfg/keys_unittest.cc
git commit -m "feat(sp4-webrtc-ip): add webrtc:ipHandlingPolicy key"
```

---

### Task 2: Config-drive the policy in GetWebRTCRendererPreferences

**Files:**
- Modify (checkout only): `content/renderer/renderer_blink_platform_impl.cc`
- Modify (checkout only): `content/renderer/BUILD.gn` (add camoucfg dep)
- Create (Mac, for verify): `scripts/verify_sp4_webrtc.py`

**Interfaces:**
- Consumes: `camoucfg::keys::kWebrtcIpHandlingPolicy`.

- [ ] **Step 1: Write the failing verify script `scripts/verify_sp4_webrtc.py`**

Launches content_shell with the fake-device flags (so stock leaks the raw local IP) + `CAMOU_CONFIG`, NO CDP. Criteria:
- **W1 (policy suppresses local IP):** config `{"webrtc:ipHandlingPolicy":"default_public_interface_only"}` → NO candidate address matches the private-IPv4 pattern `\b(10\.\d+\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)`.
- **W2 (no-op absent):** config `{}` → candidate set (the sorted list of addresses) equals the stock baseline captured with `--capture-baseline` (rule 5).

```python
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell

FLAGS = ["--ozone-platform=headless",
         "--use-fake-device-for-media-stream",
         "--use-fake-ui-for-media-stream"]

PROBE = r"""(async () => {
  try {
    const pc = new RTCPeerConnection({iceServers: []});
    pc.createDataChannel("x");
    const cands = [];
    pc.onicecandidate = (e) => { if (e.candidate) cands.push(e.candidate.candidate); };
    await pc.setLocalDescription(await pc.createOffer());
    await new Promise((res)=>{ if(pc.iceGatheringState==='complete')return res();
      pc.onicegatheringstatechange=()=>{if(pc.iceGatheringState==='complete')res()}; setTimeout(res,4000); });
    const addrs = cands.map(c => c.split(' ')[4]);
    pc.close();
    return { addrs };
  } catch(e){ return {error:String(e)}; }
})()"""

PRIV = re.compile(r"\b(10\.\d+\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)")
BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sp4_webrtc_baseline.json")

def run(config):
    vals, err = lib_shell.session(config, [PROBE], navigate_to="about:blank", extra_flags=FLAGS)
    if err: raise err
    return vals[0]

def cfg(d): return json.dumps(d)

def main():
    if "--capture-baseline" in sys.argv:
        b = run(cfg({}))
        with open(BASELINE,"w") as f: json.dump(b,f)
        print("baseline:", json.dumps(b)); return
    r = {}
    a = run(cfg({"webrtc:ipHandlingPolicy":"default_public_interface_only"}))
    addrs = a.get("addrs", ["1.2.3.4"])  # sentinel non-empty so a probe error can't vacuously pass
    r["W1"] = "error" not in a and not any(PRIV.search(x or "") for x in addrs)
    b = run(cfg({}))
    with open(BASELINE) as f: base=json.load(f)
    r["W2"] = sorted(b.get("addrs",[])) == sorted(base.get("addrs",[]))
    EXPECTED=2
    for k in ("W1","W2"): print(f"{k}: {'PASS' if r[k] else 'FAIL'}")
    n=sum(r.values()); print(f"{n}/{EXPECTED} " + ("ALL_PASS" if n==EXPECTED else "FAIL"))
    sys.exit(0 if n==EXPECTED else 1)

if __name__=="__main__": main()
```

- [ ] **Step 2: Capture baseline + run RED-first**

```bash
pushfile scripts/verify_sp4_webrtc.py "$VERIFY/verify_sp4_webrtc.py"
verify verify_sp4_webrtc.py --capture-baseline
verify verify_sp4_webrtc.py
```
Expected RED: W1 FAIL (config unread → the `172.22.x` private IP still leaks under the fake-device flags), W2 PASS. Record it. (If the baseline shows NO private IP even with the fake-device flags, the leak did not reproduce on this run — report before proceeding; the whole slice's RED depends on it.)

- [ ] **Step 3: Add the override in `renderer_blink_platform_impl.cc`**

Add includes (in the existing include block, alphabetically):
```cpp
#include "base/logging.h"
#include "components/camoucfg/blink_scope.h"
#include "components/camoucfg/keys.h"
#include "components/camoucfg/mask_config.h"
#include "third_party/blink/public/common/peerconnection/webrtc_ip_handling_policy.h"
```
In `GetWebRTCRendererPreferences`, immediately AFTER the `for (const auto& per_url_entry : ip_handling_urls)` loop (so config wins over the base pref and per-URL entries):

```cpp
  // SP4-webrtc-ip: config overrides the effective IP-handling policy so a
  // standalone (non-CDP) launch controls WebRTC IP exposure. Absent => real
  // pref. An unrecognized value warns rather than silently degrading.
  if (std::optional<std::string> policy = camoucfg::GetString(
          camoucfg::ScopeFor(nullptr), camoucfg::keys::kWebrtcIpHandlingPolicy);
      policy && !policy->empty()) {
    if (*policy == blink::kWebRTCIPHandlingDefault ||
        *policy == blink::kWebRTCIPHandlingDefaultPublicAndPrivateInterfaces ||
        *policy == blink::kWebRTCIPHandlingDefaultPublicInterfaceOnly ||
        *policy == blink::kWebRTCIPHandlingDisableNonProxiedUdp) {
      *ip_handling_policy = blink::ToWebRTCIPHandlingPolicy(*policy);
    } else {
      LOG(WARNING) << "camoucfg: webrtc:ipHandlingPolicy '" << *policy
                   << "' unrecognized; real policy retained";
    }
  }
```

- [ ] **Step 4: Add the camoucfg dep to `content/renderer/BUILD.gn`**

Find the main `renderer` target's `deps = [` list (the one that compiles `renderer_blink_platform_impl.cc`) and add, keeping alphabetical order:
```gn
    "//components/camoucfg",
```

- [ ] **Step 5: Build content_shell + run verify GREEN**

```bash
contentshell   # NON-ZERO steps
verify verify_sp4_webrtc.py
```
Expected: `2/2 ALL_PASS`. If `blink::ToWebRTCIPHandlingPolicy` / the `k*` constants are undeclared, confirm the `webrtc_ip_handling_policy.h` include; if `camoucfg::ScopeFor` needs a different include in content/renderer, adjust (it lives in `components/camoucfg/blink_scope.h`).

- [ ] **Step 6: Commit the Mac-side verify script**

```bash
git add scripts/verify_sp4_webrtc.py
git commit -m "test(sp4-webrtc-ip): verify_sp4_webrtc W1-W2 (policy suppresses local IP)"
```

---

### Task 3: Extract patch, wire apply.sh, regression

**Files:**
- Create: `patches/sp4-webrtc-ip.patch`
- Modify: `scripts/apply.sh` (append LAST)

**Interfaces:**
- Consumes: the checkout edits from Task 2 (`renderer_blink_platform_impl.cc`, `content/renderer/BUILD.gn`).

- [ ] **Step 1: Extract the two-file diff to `patches/sp4-webrtc-ip.patch`**

```bash
runwsl "cd $CHECKOUT && git diff -- content/renderer/renderer_blink_platform_impl.cc content/renderer/BUILD.gn" > patches/sp4-webrtc-ip.patch
```
Confirm exactly TWO `diff --git` headers, non-empty.

- [ ] **Step 2: Round-trip verify (patch == working tree)**

```bash
runwsl "cd $CHECKOUT && git checkout -- content/renderer/renderer_blink_platform_impl.cc content/renderer/BUILD.gn"
pushto patches/sp4-webrtc-ip.patch /tmp/sp4-webrtc-ip.patch
runwsl "cd $CHECKOUT && git apply --3way /tmp/sp4-webrtc-ip.patch && echo APPLY_OK"
contentshell   # NON-ZERO steps
verify verify_sp4_webrtc.py   # 2/2 ALL_PASS
```

- [ ] **Step 3: Wire apply.sh LAST**

In `scripts/apply.sh`, append after `"$ROOT/patches/sp4-tz-locale.patch"`:
```bash
  "$ROOT/patches/sp4-tz-locale.patch"
  "$ROOT/patches/sp4-webrtc-ip.patch"
)
```

- [ ] **Step 4: Full regression (record every count)**

```bash
unittests 'CamoucfgKeysTest.*:AssembleRawConfigTest.*:ParseConfigTest.*:ParseConfigDeathTest.*:GettersTest.*:MaskConfigTest.*:DeriveTest.*:DeriveDeltaTest.*:DeriveUnitTest.*:PerturbRgbaTest.*:MouseTrajectoriesTest.*'
verify verify_sp4_webrtc.py     # 2/2
verify verify_sp4_tzlocale.py   # 6/6
verify verify_sp4_media.py      # 4/4
verify verify_sp4_audio.py      # 12/12
verify verify_sp4_fonts.py      # 7/7
verify verify_sp4a.py           # 6/6
verify verify_sp1b.py           # 8/8
```
Expected: camoucfg all PASS (64 keys), all prior verifies unchanged. Missing-baseline errors → run once with `--capture-baseline`, note it.

- [ ] **Step 5: Commit**

```bash
git add patches/sp4-webrtc-ip.patch scripts/apply.sh
git commit -m "feat(sp4-webrtc-ip): config-driven WebRTC IP-handling policy — patch + apply wiring"
```

---

## Self-Review notes

- **Spec coverage:** `webrtc_ip_handling_policy` (measurement §2/§3) → key + override in `GetWebRTCRendererPreferences`. Fake-local-IP + force-mDNS deferred to webrtc-ii (§5). Public-IP/proxy benefit real but harness-unverifiable (§4/§5).
- **Type consistency:** `*ip_handling_policy` is `blink::mojom::WebRtcIpHandlingPolicy*`; `ToWebRTCIPHandlingPolicy` returns that enum. Validation uses the `blink::kWebRTCIPHandling*` string constants.
- **Malformed input** warns (not silent-degrade) — sp4-tz-locale lesson applied up front.
- **First content/renderer hook** — BUILD.gn dep added; if `ScopeFor(nullptr)`/blink_scope.h is awkward in content/renderer, that surfaces at Task 2 Step 5 build.
