# webrtc-ii force-mDNS measurement (2026-09-06)

Checkout HEAD `a727b57805`, `out/Default` content_shell. Follow-on to
[sp4-webrtc-ip](2026-09-01-sp4-webrtc-ip-surfaces.md), which named this slice at
its §5/§6: *"force-mDNS-always-on (permission gap) → defer (webrtc-ii) —
different lever."* This is that lever.

## 1. The residual leak (RED, reproduced)

sp4-webrtc-ip's `webrtc:ipHandlingPolicy` is opt-in and its protective values
**empty** the candidate set on a single-interface box (no public route/STUN) —
itself a tell (sp4 §5). It also leaves the **permission-case local-IP leak**
open: a page holding camera/mic permission bypasses mDNS and sees the raw LAN IP.

Gate 0 (`scratchpad/probe_webrtc_gate0.py`), fake-device flags
(`--use-fake-device-for-media-stream --use-fake-ui-for-media-stream`, which put
the page in a media-permission context), no config:

```
candidate count: 2
  candidate:... 172.22.42.251 58703 typ host ...
  candidate:... 172.22.42.251 9 typ host tcptype active ...
raw-private-IP candidates: 2
mdns (.local) candidates: 0
```

The raw WSL LAN IP `172.22.42.251` leaks in 2 host candidates (udp + tcp), 0
mDNS. This is the leak this slice closes.

## 2. The lever

`FilteringNetworkManager::GetMdnsResponder()`
(`third_party/blink/renderer/platform/p2p/filtering_network_manager.cc:115`) —
a single Blink `platform/p2p` conditional (NOT deep libwebrtc; the sp4 roadmap
over-estimated). The port allocator asks this method per network for the mDNS
responder; a non-null responder makes every host candidate emit as `<uuid>.local`
instead of the raw IP.

```cpp
webrtc::MdnsResponderInterface* FilteringNetworkManager::GetMdnsResponder() const {
  DCHECK_CALLED_ON_VALID_THREAD(thread_checker_);
  if (!network_manager_for_signaling_thread_)
    return nullptr;
  // mDNS responder is set to null if we have the enumeration permission or the
  // mDNS obfuscation of IPs is disallowed.
  if (enumeration_permission() == ENUMERATION_ALLOWED ||   // <-- media-permission bypass
      !allow_mdns_obfuscation_) {                          // <-- enterprise allow-list bypass
    return nullptr;                                        //     (WebRtcLocalIpsAllowedUrls)
  }
  return network_manager_for_signaling_thread_->GetMdnsResponder();
}
```

Both null-return conditions are IP-leaking bypasses of mDNS:
`ENUMERATION_ALLOWED` (media permission, set async after two `HasPermission`
callbacks) and `!allow_mdns_obfuscation_` (the enterprise
`WebRtcLocalIpsAllowedUrls` allow-list, wired through
`GetWebRTCRendererPreferences`). For an anti-detect build both are leaks.

## 3. Port design (this slice)

New key **`webrtc:hideLocalIps`** (bool). Named for the *effect*, not the lever:
per advisor, forcing mDNS overrides BOTH bypasses above — so the key owns the
second semantic honestly (it also overrides the enterprise `allow_mdns_obfuscation`
path that sp4 §5 line 175 left as the real pref). Absent/false → stock (rule 5).

The hook is placed AFTER the existing null-guard (so the force can never
null-deref `network_manager_for_signaling_thread_`) and BEFORE the two bypass
conditions, short-circuiting to force the responder on:

```cpp
  if (!network_manager_for_signaling_thread_)
    return nullptr;

  // webrtc-ii: webrtc:hideLocalIps forces the mDNS responder on unconditionally,
  // so host candidates emit as .local even under media permission
  // (ENUMERATION_ALLOWED) or an enterprise policy that disabled obfuscation.
  // Absent/false => stock behavior (rule 5).
  if (camoucfg::GetBool(camoucfg::ScopeFor(nullptr),
                        camoucfg::keys::kWebrtcHideLocalIps)
          .value_or(false)) {
    return network_manager_for_signaling_thread_->GetMdnsResponder();
  }

  if (enumeration_permission() == ENUMERATION_ALLOWED ||
      !allow_mdns_obfuscation_) {
    return nullptr;
  }
  return network_manager_for_signaling_thread_->GetMdnsResponder();
```

- **Config read from the signaling thread is safe.** `ParsedConfig()` is a
  `static const base::NoDestructor<base::DictValue>` (function-local static,
  thread-safe init; immutable after first parse); `GetBool` is a lock-free
  lookup. `ScopeFor(nullptr)` → `GlobalScope()` (CAMOU_CONFIG is process-wide),
  the same idiom as sp4-webrtc-ip's `GetString`.
- **Force is unconditional**, so libwebrtc caching the responder pointer once at
  session start (if it does) cannot defeat it — there is no window where the key
  is set and the responder is null.
- **No BUILD.gn hunk:** `filtering_network_manager.cc` compiles in
  `platform/BUILD.gn`, which already deps `//components/camoucfg` (sp4-fonts).
  **Cross-patch build coupling (noted per final review):** this `.cc`-only patch
  links only because `sp4-fonts.patch` adds `//components/camoucfg` to the
  `component("platform")` target — the same way core-target files ride sp0's
  `core/BUILD.gn` dep. `gn check //third_party/blink/renderer/platform:*` passes
  with the stack applied, so it is not a defect, but a future `sp4-fonts` revert
  that dropped that dep would silently break this patch's build. (Task 4
  consolidated the *checkdeps* grants into sp0; the *gn* deps still live per-slice.)
- **DEPS:** `platform/p2p/DEPS` gains `+components/camoucfg/keys.h` only —
  `blink_scope.h`/`mask_config.h` are already granted renderer-wide
  (`third_party/blink/renderer/DEPS:95-97`). (The parallel `media_values.cc`
  keys.h gap from sp4a-screen is a separate consolidate-task fix, not touched
  here.)
- **Key count:** 82 → 83 (triple edit: keys.h constant + kAllKeys + std::array
  size + keys_unittest declared set).

## 4. Verification plan

`scripts/verify_webrtc_ii.py`, three cases, private-IP regex
`10.|172.16-31.|192.168.` + `.local` substring:

- **R-LEAK (the fix):** fake-device flags + `{"webrtc:hideLocalIps":true}` → 0
  raw-private-IP candidates AND ≥1 `.local`. The `.local`-present half is what
  distinguishes this fix from sp4's policy lever (which *empties* the set). RED
  on the pre-fix binary: 2 raw, 0 `.local` (§1).
- **R-STOCK (rule 5):** fake-device flags, no key → ≥1 raw private IP present
  (matches Gate 0's 2). Asserts the leak is untouched when the key is absent.
- **R-NOPERM (no new tell in the common path):** no fake-device flags,
  `{"webrtc:hideLocalIps":true}` → 0 raw, ≥1 `.local`. Confirms the force is a
  no-op where mDNS was already on (mDNS is default-on without permission).

Two `.local` names are random per session — assert by `.local` substring
presence, never cross-session name equality.

## 5. Residual / out of scope (documented)

- **Public-IP srflx leak stays unverifiable** on WSL (no STUN/public route),
  same as sp4-webrtc-ip §5. This slice closes the *local* leak.
- **Coherence note — the residual is candidate *shape*, not just the `.local`
  name.** With `hideLocalIps:true`, a page holding camera+mic that sees only
  `.local` host candidates is a mildly unusual combination (real Chrome shows the
  raw IP there). It is the strictly-more-private direction and far rarer as a
  probe than a raw-IP check, but the tell is sharper than "`.local` under
  permission": the force leaves `enumeration_permission()==ENUMERATION_ALLOWED`,
  so `GetNetworks()` still enumerates every interface and the allocator emits the
  *permission-path* candidate set (R-LEAK = 2, udp + `tcptype active`, vs
  R-NOPERM's 1), merely renamed `.local`. If real Chrome never emits
  tcp-active / per-interface candidates in the no-permission state — the only
  state where it emits `.local` — the fork's output is a candidate *shape* no
  real Chrome state produces. The precondition to observe this is identical to
  the precondition for the raw-IP leak it closes (both are permission-gated), and
  the `.local` count leaks only interface count, which the raw IP already leaked
  plus the addresses — so no new leak, just a shape signal. The fully coherent
  answer — a configured plausible LAN IP — remains the `webrtc:localipv4`
  libwebrtc residual (sp4 §5, still deferred); **this slice closes the leak, not
  the distinguishability.** (Confirming the shape claim needs a real-Chrome
  no-permission capture on a multi-homed box — unavailable on the WSL harness.)
- **Enterprise branch verified by inspection, not a runtime case.** The key
  overrides two stock bypasses, but only the `ENUMERATION_ALLOWED` one has a
  runtime test (R-LEAK). The force `return`s before the `|| !allow_mdns_obfuscation_`
  is evaluated, so the enterprise semantic is entailed by placement with the same
  certainty as the first, and the only unverified piece ("does forcing mDNS emit
  `.local` under that config") is the same mDNS mechanism R-LEAK already proves.
  The enterprise-policy plumbing (`WebRtcLocalIpsAllowedUrls`) is not exercised.
- **Opt-in, default OFF (rule 5).** The permission-path leak stays open unless
  the operator sets `webrtc:hideLocalIps`; a fleet on default config is NOT
  protected.
- **`webrtc_udp_min/max_port`** untouched (out of scope, as in sp4).
