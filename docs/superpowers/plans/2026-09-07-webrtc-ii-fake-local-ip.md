# webrtc-ii fake-local-IP Implementation Plan

> **SUPERSEDED — slice REJECTED 2026-09-07.** Tasks 1–5 were executed to GREEN
> (verify 6/6; both review Criticals fixed) before the whole-slice review found a
> structural real-IP leak (peer-reflexive candidates bypass the hook and expose
> the real IP via `getStats()` on any completed ICE connectivity check). Root
> cause: a fake literal IP cannot resolve to the real socket, so force-mDNS is
> prflx-safe and this approach structurally cannot be. Reverted. See the
> measurement doc's VERDICT banner and §7. This plan is kept as the record of
> what was built.

> **For agentic workers:** Executed INLINE on the WSL build box by the controller
> (box access is a single shared tree over one SSH master — fresh per-task
> subagents cannot each drive it). Each task ends with a build/verify gate; a
> code-reviewer subagent reviews the whole diff before commit. Steps use checkbox
> (`- [ ]`) syntax.

**Goal:** Under a media-permission (bypass) context, emit a configured plausible
LAN IP (`webrtc:localipv4`) as the WebRTC host ICE candidate instead of the real
LAN IP or `.local`, coherently across `onicecandidate` / `localDescription.sdp` /
`getStats()`.

**Architecture:** Config lives Chromium-side (`FilteringNetworkManager`, which
already deps `//components/camoucfg` for force-mDNS) and is consumed by vendored
libwebrtc through a `GetFakeLocalIp()` virtual on the network provider — the same
bridge force-mDNS rode via `GetMdnsResponder()`. `Port::AddAddress` substitutes
the advertised address of a host candidate (base address left real). The
substitution fires ONLY in the bypass path where stock leaks the raw IP; the
common no-permission path is untouched (keeps `.local`).

**Tech Stack:** Chromium/Blink C++ (`platform/p2p`), vendored libwebrtc
(`third_party/webrtc`), `//components/camoucfg` config layer, Python verify infra
(`lib_shell`), content_shell on the WSL checkout.

**Design source:** `docs/superpowers/measurements/2026-09-07-webrtc-ii-fake-local-ip.md`
(§3 has the exact hunks; §4 the verify plan).

## Global Constraints

- **Layering (hard):** `third_party/webrtc` MUST NOT include or dep
  `//components/camoucfg`. libwebrtc reads only `network_->GetFakeLocalIp()`
  (webrtc types only: `std::optional<webrtc::IPAddress>`). The camoucfg read
  lives only in `filtering_network_manager.cc` (Chromium).
- **Anti-tell (hard):** `GetFakeLocalIp()` returns a value ONLY when
  `enumeration_permission() == ENUMERATION_ALLOWED || !allow_mdns_obfuscation_`
  (the bypass path). In the common path it returns `std::nullopt` → `.local`
  unchanged. A raw-looking IP in the common path is a shape no real Chrome
  common-path produces.
- **Rule 5:** key absent / empty / not a valid IPv4 → real address retained;
  invalid logs `LOG(WARNING)` (tz-locale fail-loud idiom).
- **Key triple-consistency:** a new key needs keys.h constant + `kAllKeys` entry +
  the `std::array` size bump + the `keys_unittest.cc` declared set. 83 → 84.
- **Scope:** IPv4 only. No `webrtc:localipv6` key (unmeasurable on WSL).
- **base_address untouched** in `Port::AddAddress` (foundation stays real-derived;
  not page-recoverable).
- **Stage explicit paths, never `git add -A`. Secret-scan every commit.**
- **New patch `patches/webrtc-fakeip.patch`** (do NOT fold into `webrtc-ii.patch`
  — isolating the vendored-libwebrtc hunk keeps the rebase-checklist item legible).

---

### Task 1: Verify script + RED baseline

**Files:**
- Create: `scripts/verify_webrtc_ii_fakeip.py`
- Push to box: `$VERIFY/verify_webrtc_ii_fakeip.py`

**Interfaces:**
- Consumes: `lib_shell.session(config, [expr], extra_flags=..., navigate_to=None)`;
  fake-device flags `["--use-fake-device-for-media-stream",
  "--use-fake-ui-for-media-stream"]` plus the content_shell default
  `--ozone-platform=headless` (pass the full list via `extra_flags`).
- Produces: the RED record for the slice.

- [ ] **Step 1: Write the verify script** (6 cases; a helper `run(cfg, flags)`
  that opens an `RTCPeerConnection({iceServers:[]})`, `createDataChannel`,
  `setLocalDescription(createOffer())`, collects `onicecandidate` strings until
  `null`, then returns `{cands:[...], sdp: pc.localDescription.sdp, stats:[...]}`
  where stats are local-candidate `address`/`ip` from `pc.getStats()`).

```python
"""Verifies webrtc-ii fake-local-IP (webrtc:localipv4).

Under a media-permission (bypass) context (--use-fake-device flags), stock leaks
the raw LAN IP (172.22.x) in host candidates. With webrtc:localipv4 set, every
host candidate must show the configured fake IP -- coherently across
onicecandidate, pc.localDescription.sdp, and getStats() -- and zero raw / zero
.local. The substitution must NOT fire in the common no-permission path
(RI-NOPERM), which keeps .local.

RED (pre-hook): RI-FAKE/RI-SDP/RI-STATS FAIL (fake absent, raw 172.22.x present);
RI-STOCK/RI-NOPERM/RI-HIDE already PASS. GREEN: all pass.
"""
import json
import re
import sys

import lib_shell

FAKE = "192.168.1.37"
PRIV = re.compile(r"\b(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.)")
FLAGS = ["--ozone-platform=headless",
         "--use-fake-device-for-media-stream",
         "--use-fake-ui-for-media-stream"]
NOPERM_FLAGS = ["--ozone-platform=headless"]

GATHER = r"""(async () => {
  const pc = new RTCPeerConnection({iceServers: []});
  const cands = [];
  pc.onicecandidate = (e) => { if (e.candidate) cands.push(e.candidate.candidate); };
  pc.createDataChannel("x");
  await pc.setLocalDescription(await pc.createOffer());
  await new Promise((res) => {
    if (pc.iceGatheringState === "complete") return res();
    pc.addEventListener("icegatheringstatechange",
      () => { if (pc.iceGatheringState === "complete") res(); });
    setTimeout(res, 8000);
  });
  const stats = [];
  (await pc.getStats()).forEach((r) => {
    if (r.type === "local-candidate") stats.push(r.address || r.ip || "");
  });
  return {cands, sdp: pc.localDescription.sdp, stats};
})()"""

results = {}
notes = []


def run(cfg, flags):
    config = json.dumps(cfg) if cfg is not None else None
    v, e = lib_shell.session(config, [GATHER], extra_flags=flags)
    return (None, e) if e else (v[0], None)


def host_ips(cands):
    out = []
    for c in cands:
        m = re.search(r"candidate:\S+ \d+ \S+ \d+ (\S+) \d+ typ host", c)
        if m:
            out.append(m.group(1))
    return out


# --- bypass path (fake-device flags) ---
w, e = run({"webrtc:localipv4": FAKE}, FLAGS)
if e or not isinstance(w, dict):
    for k in ("RI-FAKE", "RI-SDP", "RI-STATS"):
        results[k] = False
    notes.append(f"fake session error: {e or w}")
else:
    ips = host_ips(w["cands"])
    notes.append(f"fake host IPs: {ips}; stats: {w['stats']}")
    results["RI-FAKE onicecandidate host IPs all == fake, no raw, no .local"] = (
        len(ips) >= 1 and all(ip == FAKE for ip in ips)
        and not any(".local" in c for c in w["cands"]))
    results["RI-SDP localDescription has fake, not raw, not .local"] = (
        FAKE in w["sdp"] and not PRIV.search(w["sdp"].replace(FAKE, ""))
        and ".local" not in w["sdp"])
    results["RI-STATS getStats local-candidate address == fake, no raw"] = (
        any(s == FAKE for s in w["stats"])
        and not any(PRIV.search(s) and s != FAKE for s in w["stats"]))

# --- rule 5: no key -> raw leak untouched ---
w2, e2 = run(None, FLAGS)
if e2 or not isinstance(w2, dict):
    results["RI-STOCK no key -> raw private IP present"] = False
    notes.append(f"stock session error: {e2 or w2}")
else:
    ips2 = host_ips(w2["cands"])
    results["RI-STOCK no key -> raw private IP present"] = any(
        PRIV.search(ip) for ip in ips2)
    notes.append(f"stock host IPs: {ips2}")

# --- anti-tell: no permission -> substitution must NOT fire, keeps .local ---
w3, e3 = run({"webrtc:localipv4": FAKE}, NOPERM_FLAGS)
if e3 or not isinstance(w3, dict):
    results["RI-NOPERM no-perm keeps .local, no fake, no raw"] = False
    notes.append(f"noperm session error: {e3 or w3}")
else:
    results["RI-NOPERM no-perm keeps .local, no fake, no raw"] = (
        any(".local" in c for c in w3["cands"])
        and FAKE not in w3["sdp"]
        and not any(PRIV.search(ip) for ip in host_ips(w3["cands"])))
    notes.append(f"noperm cands: {w3['cands']}")

# --- regression: force-mDNS (webrtc-ii R-LEAK) still holds ---
w4, e4 = run({"webrtc:hideLocalIps": True}, FLAGS)
if e4 or not isinstance(w4, dict):
    results["RI-HIDE hideLocalIps still -> .local, no raw"] = False
    notes.append(f"hide session error: {e4 or w4}")
else:
    results["RI-HIDE hideLocalIps still -> .local, no raw"] = (
        any(".local" in c for c in w4["cands"])
        and not any(PRIV.search(ip) for ip in host_ips(w4["cands"])))

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for n in notes:
    print(f"      {n}")

sys.exit(0 if results and all(results.values()) else 1)
```

- [ ] **Step 2: Push + run RED against the current (pre-hook) content_shell**

```
pushto scripts/verify_webrtc_ii_fakeip.py $VERIFY/verify_webrtc_ii_fakeip.py
verify verify_webrtc_ii_fakeip.py
```
Expected RED: `RI-FAKE`, `RI-SDP`, `RI-STATS` FAIL (fake absent, raw `172.22.x`
present); `RI-STOCK`, `RI-NOPERM`, `RI-HIDE` PASS. Record the exact output in the
ledger. (If `RI-STOCK` or the candidate-count differs from Gate 0's 2, stop and
re-baseline before implementing.)

- [ ] **Step 3: Commit the verify script + RED record**

```bash
git add scripts/verify_webrtc_ii_fakeip.py
git commit -m "test(webrtc-ii): RED for fake-local-IP (raw 172.22.x leaks under permission)"
```

---

### Task 2: Config key `webrtc:localipv4`

**Files (box checkout):**
- Modify: `components/camoucfg/keys.h`
- Modify: `components/camoucfg/keys_unittest.cc`

**Interfaces:**
- Produces: `camoucfg::keys::kWebrtcLocalIpv4` == `"webrtc:localipv4"`, registered
  in `kAllKeys`, size 84.

- [ ] **Step 1: Read the anchor** — `runwsl "grep -n kWebrtcHideLocalIps
  $CHECKOUT/components/camoucfg/keys.h $CHECKOUT/components/camoucfg/keys_unittest.cc"`.
  Add the new key immediately after each `kWebrtcHideLocalIps` occurrence.

- [ ] **Step 2: Edit keys.h** — add the constant beside `kWebrtcHideLocalIps`:

```cpp
inline constexpr char kWebrtcLocalIpv4[] = "webrtc:localipv4";
```
add `kWebrtcLocalIpv4,` to the `kAllKeys` array (after `kWebrtcHideLocalIps,`),
and bump the `std::array<..., 83>` size to `84` (the count assertion / array
declaration that lists `kAllKeys`).

- [ ] **Step 3: Edit keys_unittest.cc** — add `keys::kWebrtcLocalIpv4,` to the
  declared-set literal (the test that cross-checks every key appears in
  `kAllKeys`), beside `keys::kWebrtcHideLocalIps,`.

- [ ] **Step 4: Build + run the keys unit tests** (confirm NON-ZERO build steps)

```
unittests 'CamoucfgKeys*:*Keys*'
```
Expected: `BUILD_DONE` with non-zero ninja steps, all key tests PASS (no
duplicate/missing key assertion failure). If ninja reports 0 steps, the .o is
stale — touch keys.h and rebuild.

- [ ] **Step 5: Commit** — deferred to Task 5's single patch extraction (the key
  lines ship inside `patches/webrtc-fakeip.patch`; do not commit box state).

---

### Task 3: libwebrtc bridge (inert)

**Files (box checkout, `third_party/webrtc`):**
- Modify: `rtc_base/network.h` (the `MdnsResponderProvider` interface + `Network`)
- Modify: `rtc_base/network.cc` (`Network::GetFakeLocalIp` body)
- Modify: `p2p/base/port.cc` (`Port::AddAddress`)

**Interfaces:**
- Produces: `webrtc::Network::GetFakeLocalIp()` →
  `std::optional<webrtc::IPAddress>` (default `nullopt`); consumed in
  `Port::AddAddress`.
- Consumes: `webrtc::IPAddress`, `SocketAddress::set_address`? — the candidate is
  mutable via `c.set_address(SocketAddress)`; `SocketAddress(const IPAddress&,
  int port)` constructs a literal-IP address with NO `SetResolvedIP` overwrite.

- [ ] **Step 1: `rtc_base/network.h`** — on `class MdnsResponderProvider` (near
  the `GetMdnsResponder()` pure virtual, ~line 94) add a defaulted virtual:

```cpp
  // camoucfg webrtc-ii fake-local-IP: a configured LAN IP to advertise for host
  // candidates on this network, or nullopt for stock behavior. Defaulted so
  // every existing provider is a no-op.
  virtual std::optional<webrtc::IPAddress> GetFakeLocalIp() const {
    return std::nullopt;
  }
```
and on `class Network` (beside `MdnsResponderInterface* GetMdnsResponder() const;`,
~line 340) declare:

```cpp
  std::optional<webrtc::IPAddress> GetFakeLocalIp() const;
```
Confirm `#include <optional>` is present in network.h (add if missing).

- [ ] **Step 2: `rtc_base/network.cc`** — mirror `Network::GetMdnsResponder`
  (~line 1252):

```cpp
std::optional<webrtc::IPAddress> Network::GetFakeLocalIp() const {
  if (mdns_responder_provider_ == nullptr) {
    return std::nullopt;
  }
  return mdns_responder_provider_->GetFakeLocalIp();
}
```

- [ ] **Step 3: `p2p/base/port.cc` `Port::AddAddress`** — insert BEFORE
  `bool pending = MaybeObfuscateAddress(c, is_final);` (~line 291), after the
  `Candidate c(...)` is fully populated:

```cpp
  // camoucfg webrtc-ii fake-local-IP: for a host candidate, advertise a
  // configured LAN IP instead of the real address. base_address (foundation
  // input, computed above) is left real and is not page-visible. Takes
  // precedence over mDNS; a plain fake IP is emitted (no .local, and
  // SanitizeCandidate leaves it since obfuscation is off on this network).
  if (c.is_local()) {
    if (std::optional<IPAddress> fake = network_->GetFakeLocalIp()) {
      c.set_address(SocketAddress(*fake, c.address().port()));
      FinishAddingAddress(c, is_final);
      return;
    }
  }
  bool pending = MaybeObfuscateAddress(c, is_final);
```
Confirm `port.cc` already includes `<optional>` and `rtc_base/ip_address.h`
(it uses `IPAddress` already via the network); add `#include <optional>` if the
compiler complains.

- [ ] **Step 4: Build content_shell** (bridge is inert — no provider returns a
  fake IP yet):

```
contentshell
```
Expected: non-zero ninja steps, links clean (a compile error here is a layering
or include mistake — the webrtc side must reference NO camoucfg symbol).

- [ ] **Step 5: Verify still RED, unchanged** — the branch is inert
  (`GetFakeLocalIp` defaults `nullopt`):

```
verify verify_webrtc_ii_fakeip.py
```
Expected: identical to Task 1 RED (RI-FAKE/SDP/STATS FAIL, rest PASS). Proves the
libwebrtc edit compiles and changes nothing without the Chromium provider.

---

### Task 4: Chromium provider → GREEN

**Files (box checkout, `third_party/blink/renderer/platform/p2p`):**
- Modify: `filtering_network_manager.h` (declare `GetFakeLocalIp` override)
- Modify: `filtering_network_manager.cc` (impl + `GetMdnsResponder` clause)

**Interfaces:**
- Consumes: `webrtc::Network::GetFakeLocalIp` (Task 3);
  `camoucfg::GetString(camoucfg::ScopeFor(nullptr), camoucfg::keys::kWebrtcLocalIpv4)`
  (Task 2); `enumeration_permission()`, `allow_mdns_obfuscation_` (existing
  members used by `GetMdnsResponder`).

- [ ] **Step 1: `filtering_network_manager.h`** — beside the
  `webrtc::MdnsResponderInterface* GetMdnsResponder() const override;` declaration,
  add:

```cpp
  std::optional<webrtc::IPAddress> GetFakeLocalIp() const override;
```

- [ ] **Step 2: `filtering_network_manager.cc`** — add the impl (uses the
  already-present `#include "components/camoucfg/keys.h"` + `blink_scope.h` from
  force-mDNS; add `#include "components/camoucfg/blink_scope.h"` /
  `#include "third_party/webrtc/rtc_base/ip_address.h"` only if not already
  pulled in):

```cpp
std::optional<webrtc::IPAddress> FilteringNetworkManager::GetFakeLocalIp() const {
  DCHECK_CALLED_ON_VALID_THREAD(thread_checker_);
  // Anti-tell: substitute ONLY where stock would emit a RAW IP (the bypass
  // paths). In the common no-permission path mDNS emits .local; a raw-looking IP
  // there is a shape no real Chrome common-path produces.
  if (!(enumeration_permission() == ENUMERATION_ALLOWED ||
        !allow_mdns_obfuscation_)) {
    return std::nullopt;
  }
  std::optional<std::string> v = camoucfg::GetString(
      camoucfg::ScopeFor(nullptr), camoucfg::keys::kWebrtcLocalIpv4);
  if (!v || v->empty()) {
    return std::nullopt;
  }
  webrtc::IPAddress ip;
  if (!webrtc::IPFromString(*v, &ip) || ip.family() != AF_INET) {
    LOG(WARNING) << "camoucfg: webrtc:localipv4 '" << *v
                 << "' not a valid IPv4; real address retained";
    return std::nullopt;
  }
  return ip;
}
```

- [ ] **Step 3: `GetMdnsResponder()` clause** — so the two levers compose: when a
  fake IP is engaged, do NOT obfuscate (return nullptr), letting the fake-IP
  substitution win and keeping `MdnsObfuscationEnabled()` false so
  `SanitizeCandidate` leaves the plain fake IP. Insert AFTER the existing
  `if (!network_manager_for_signaling_thread_) return nullptr;` guard and BEFORE
  the `webrtc:hideLocalIps` force block:

```cpp
  // If a fake local IP will be substituted (bypass path + webrtc:localipv4),
  // keep the responder null so the fake plain IP is emitted, not .local.
  if (GetFakeLocalIp().has_value()) {
    return nullptr;
  }
```

- [ ] **Step 4: Build content_shell**

```
contentshell
```
Expected: non-zero steps, links clean.

- [ ] **Step 5: Run verify — expect GREEN 6/6**

```
verify verify_webrtc_ii_fakeip.py
```
Expected: all 6 PASS — RI-FAKE (host IPs all `192.168.1.37`, no raw, no `.local`),
RI-SDP (fake in `localDescription.sdp`), RI-STATS (getStats address == fake),
RI-STOCK (no key → raw present), RI-NOPERM (no-perm keeps `.local`, no fake),
RI-HIDE (force-mDNS regression). If RI-NOPERM fails (fake fired in the common
path), the bypass gate in Step 2 is wrong — fix before proceeding.

- [ ] **Step 6: Regression — webrtc-ii + config unit tests still green**

```
verify verify_webrtc_ii.py
unittests 'CamoucfgKeys*:*Keys*'
```
Expected: `verify_webrtc_ii.py` R-LEAK/R-STOCK/R-NOPERM all PASS; keys tests PASS.

---

### Task 5: Extract patch + round-trip proof + review + commit

**Files (local repo):**
- Create: `patches/webrtc-fakeip.patch`
- Modify: `scripts/apply.sh` (add `webrtc-fakeip.patch` to the ordered list, AFTER
  `webrtc-ii.patch` and after `sp0`/keys-owning patches so the keys.h hunk applies
  on the stacked state)
- Modify: `.superpowers/sdd/progress.md` (ledger)

- [ ] **Step 1: Extract the patch git-native** from the box checkout — the 5
  changed files (`components/camoucfg/keys.h`, `components/camoucfg/keys_unittest.cc`,
  `third_party/webrtc/rtc_base/network.h`, `third_party/webrtc/rtc_base/network.cc`,
  `third_party/webrtc/p2p/base/port.cc`, `third_party/blink/renderer/platform/p2p/
  filtering_network_manager.h`, `filtering_network_manager.cc`). Use the
  stage-pristine-then-overwrite technique so a-blobs are the real stacked-base
  blobs (per `patch-reextraction-all-paths` memory). Pull the resulting patch to
  `patches/webrtc-fakeip.patch`.

- [ ] **Step 2: Confirm no BUILD.gn / DEPS hunk is needed** — `filtering_network_
  manager.cc` already deps camoucfg (force-mDNS via `platform/BUILD.gn` +
  `platform/p2p/DEPS` keys.h grant); the webrtc side references no camoucfg symbol.
  Run whole-renderer checkdeps + gn check:

```
runwsl "cd $CHECKOUT && python3 buildtools/checkdeps/checkdeps.py --root=. third_party/blink/renderer/platform/p2p && gn check out/Default //third_party/blink/renderer/platform:*"
```
Expected: SUCCESS, no new violation. (If checkdeps flags a webrtc→camoucfg edge,
the layering constraint was violated — fix Task 3/4.)

- [ ] **Step 3: Round-trip from pristine** — revert the touched dirs, apply the
  full stack `--3way`, checkdeps, rebuild, reverify. Per the
  `camoucrome-full-reconstruction` memory (worktree at base `0e8d4a9268`, run
  `scripts/apply.sh`). Expected: all patches apply `--3way` clean (0 drift),
  `checkdeps` SUCCESS, content_shell rebuilds, `verify_webrtc_ii_fakeip.py` 6/6 +
  `verify_webrtc_ii.py` 3/3 + keys unittests PASS.

- [ ] **Step 4: Reviewer subagent** — dispatch `agent-skills:code-reviewer` on the
  diff (`patches/webrtc-fakeip.patch` + the verify script + apply.sh). Global
  constraints block = this plan's Global Constraints verbatim. Fix Critical +
  Important findings, re-review.

- [ ] **Step 5: Secret-scan + commit + push**

```bash
git add patches/webrtc-fakeip.patch scripts/apply.sh scripts/verify_webrtc_ii_fakeip.py .superpowers/sdd/progress.md
# secret-scan the staged diff with the session security-protocol pattern
# (SSH host/user/credential, Tailscale IP, user email) — expect no output
git commit -m "feat(webrtc-ii): fake-local-IP host candidate via webrtc:localipv4"
git push origin HEAD
```

- [ ] **Step 6: Update roadmap** — mark webrtc-ii fake-local-IP shipped (row 10 +
  §10 + execution note): correct the "needs a real network" mis-shelf (only the
  srflx half does), add the vendored-libwebrtc-hunk rebase-checklist item.

---

## Rebase checklist additions (record in the roadmap)

- `third_party/webrtc/p2p/base/port.cc` `Port::AddAddress` — re-diff on every
  webrtc roll; upstream may reshape the `Candidate` ctor or `AddAddress`.
- `third_party/webrtc/rtc_base/network.{h,cc}` `GetFakeLocalIp` provider virtual +
  `Network` delegate — re-diff if the `MdnsResponderProvider` interface moves.

## Self-review notes

- Spec coverage: §3a→Task 3, §3b→Task 4, §3c anti-tell→RI-NOPERM (Task 1/4 Step 5),
  §3d key→Task 2, §4 verify→Task 1, §5 residuals→roadmap (Task 5 Step 6).
- No `webrtc:localipv6` task (Global Constraint: v4 only).
- Type consistency: `GetFakeLocalIp()` returns `std::optional<webrtc::IPAddress>`
  in all three of network.h provider, Network delegate, and FilteringNetworkManager
  override.
