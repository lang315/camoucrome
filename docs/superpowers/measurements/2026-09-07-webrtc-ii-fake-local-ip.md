# webrtc-ii fake-local-IP measurement (2026-09-07)

Checkout HEAD `a727b57805`, `out/Default` content_shell. Follow-on to
[sp4-webrtc-ip](2026-09-01-sp4-webrtc-ip-surfaces.md) §5 (*"Camoufox
fake-local-IP (`webrtc:localipv4/ipv6`) not ported … deferred (webrtc-ii)"*) and
to [webrtc-ii force-mDNS](2026-09-06-webrtc-ii-force-mdns.md) §5, which closes the
*leak* but leaves a *shape* tell this slice closes.

The roadmap filed this residual as "needs a real network." That is **wrong for
the local-IP half**: host ICE candidates are gathered from local interfaces, so
faking them is fully reproducible on the WSL box (§1). Only the *srflx/public-IP*
half needs a STUN/public route — a different, still-deferred residual.

## 1. The residual (RED, reproduced)

Two levers already shipped for the local-IP surface, each leaving a tell:

- **sp4-webrtc-ip `webrtc:ipHandlingPolicy`** — protective values *empty* the
  candidate set on a single-interface box (itself a tell; sp4 §5).
- **webrtc-ii `webrtc:hideLocalIps`** — forces mDNS on, so a media-permission
  page sees `.local` host candidates. But real Chrome under permission emits the
  **raw private IP**, never `.local` — so `.local`-under-permission is a candidate
  *shape no real Chrome state produces* (force-mDNS §5 coherence note).

Stock leak, `scratchpad/probe_webrtc_gate0.py`, fake-device flags
(`--use-fake-device-for-media-stream --use-fake-ui-for-media-stream`, a
media-permission context), no config (from sp4 §1 / force-mdns §1):

```
candidate count: 2
  candidate:... 172.22.42.251 58703 typ host ...
  candidate:... 172.22.42.251 9 typ host tcptype active ...
raw-private-IP candidates: 2   mdns (.local): 0
```

The raw WSL LAN IP `172.22.42.251` leaks (2 host candidates, udp + tcp).

**The coherent fix** = under the bypass path, emit a **configured plausible LAN
IP** (`webrtc:localipv4`, e.g. `192.168.1.37`) instead of the raw IP *or*
`.local`. This matches real-Chrome-under-permission shape (one private IP) while
never revealing the real one. It is the geo-cadence class (an operator-supplied
value replacing a measured real leak), NOT the accuracy-derive class (no invented
distribution). Value is modest — media-permission-gated, and force-mDNS already
closes the *leak*; this closes the *distinguishability*.

## 2. Approach: why a Blink-only / mDNS-piggyback hook is wrong, and (b) is forced

**Cross-surface coherence requires the libwebrtc `Candidate` object.** The local
IP surfaces in three places fed from one `cricket::Candidate`:
`onicecandidate` (→ `RTCIceCandidate.candidate`/`.address`),
`pc.localDescription.sdp`, and `getStats()` local-candidate `address`/`ip`. A
rewrite at Chromium's `RTCPeerConnectionHandler::OnIceCandidate`
(`rtc_peer_connection_handler.cc:2061`) touches only the event — localDescription
and getStats derive from the same libwebrtc session and would keep the real IP →
a self-inflicted inconsistency tell. The single point that feeds all three is
`Port::AddAddress` (`third_party/webrtc/p2p/base/port.cc:207`), where the
`Candidate` is constructed.

**Approach (a) — a custom mDNS responder returning a fake-IP string — is DEAD.**
`Port::MaybeObfuscateAddress` builds `SocketAddress hostname_address(name, port)`
then calls `hostname_address.SetResolvedIP(real_addr)`. Read
(`rtc_base/socket_address.cc`):

```cpp
void SocketAddress::SetIP(absl::string_view hostname) {
  hostname_ = std::string(hostname);
  literal_ = IPFromString(hostname, &ip_);   // "192.168.1.37" -> literal_ = true, ip_ = fake
  ...
}
void SocketAddress::SetResolvedIP(const IPAddress& ip) { ip_ = ip; ... }  // ip_ = REAL, overwrites fake
std::string SocketAddress::HostAsURIString() const {
  if (!literal_ && !hostname_.empty()) return hostname_;   // taken for "abc.local"
  ... return ip_.ToString();                                // taken for a literal IP -> emits ip_ = REAL
}
```

A `.local` name is non-literal, so serialization returns `hostname_`. A fake IP
*string* is literal, so serialization returns `ip_` — which `SetResolvedIP` has
overwritten with the **real** address. Approach (a) would signal the real IP,
worse than shipping nothing. It cannot be salvaged without patching `Port` to
skip `SetResolvedIP` — at which point a libwebrtc hunk exists anyway.

**Approach (b): a small libwebrtc hunk + a Chromium implementation.** This is the
`MdnsResponderProvider` pattern force-mDNS rode. `FilteringNetworkManager`
(`third_party/blink/renderer/platform/p2p/filtering_network_manager.cc:207-208`)
already copies each network and sets itself as the network's provider
(`set_mdns_responder_provider(this)`); `webrtc::Network::GetMdnsResponder()`
delegates to it. Add a sibling on the same bridge.

## 3. Port design (this slice)

### 3a. libwebrtc hunk (`third_party/webrtc`, vendored — re-diff on rebase)

Three small edits, mirroring the mDNS provider:

1. **`rtc_base/network.h`** — on `MdnsResponderProvider` (line ~86), add
   `virtual std::optional<webrtc::IPAddress> GetFakeLocalIp() const { return std::nullopt; }`
   (default keeps every other implementer a no-op).
2. **`rtc_base/network.h/.cc`** — `webrtc::Network::GetFakeLocalIp()` delegating
   to `mdns_responder_provider_->GetFakeLocalIp()` (mirror `GetMdnsResponder()`,
   network.cc:1252), null-safe when no provider.
3. **`p2p/base/port.cc` `Port::AddAddress`** — a branch BEFORE
   `MaybeObfuscateAddress`, taking precedence:

   ```cpp
   // webrtc-ii fake-local-IP: for a host candidate, if the network supplies a
   // configured fake local IP, advertise it instead of the real address. The
   // base_address (foundation input) is left real-derived and is not page-visible.
   if (c.is_local()) {
     if (std::optional<IPAddress> fake = network_->GetFakeLocalIp()) {
       SocketAddress fake_addr(*fake, c.address().port());
       c.set_address(fake_addr);
       FinishAddingAddress(c, is_final);
       return;
     }
   }
   bool pending = MaybeObfuscateAddress(c, is_final);
   ...
   ```

   `set_address(IPAddress, port)` sets a literal IP with no `SetResolvedIP`
   overwrite → `HostAsURIString` returns the fake (the §2 trap does not apply
   here because we never call `SetResolvedIP`). No mDNS name → a plain host
   candidate.

### 3b. Chromium side (`FilteringNetworkManager`, camoucfg reachable)

`GetFakeLocalIp()` returns the configured IP **only in the bypass path** — the
same condition under which stock leaks the raw IP:

```cpp
std::optional<webrtc::IPAddress> FilteringNetworkManager::GetFakeLocalIp() const {
  // Only substitute where stock would emit a RAW IP (permission / enterprise
  // bypass). In the common no-permission path mDNS emits .local; substituting a
  // raw-looking IP there would be a shape no real Chrome common-path produces.
  if (!(enumeration_permission() == ENUMERATION_ALLOWED || !allow_mdns_obfuscation_))
    return std::nullopt;
  std::optional<std::string> v = camoucfg::GetString(
      camoucfg::ScopeFor(nullptr), camoucfg::keys::kWebrtcLocalIpv4);
  if (!v || v->empty()) return std::nullopt;
  webrtc::IPAddress ip;
  if (!webrtc::IPFromString(*v, &ip) || ip.family() != AF_INET) {
    LOG(WARNING) << "camoucfg: webrtc:localipv4 '" << *v
                 << "' not a valid IPv4; real address retained";
    return std::nullopt;   // fail-loud, keep real (tz-locale idiom)
  }
  return ip;
}
```

And `GetMdnsResponder()` gains one clause so the two levers compose: when
`GetFakeLocalIp()` is engaged, return `nullptr` (do NOT obfuscate — let the
fake-IP substitution win, and keep `MdnsObfuscationEnabled()` false so
`SanitizeCandidate` leaves the plain fake IP untouched).

### 3c. Interplay (advisor constraint — the anti-tell)

| context | `hideLocalIps` | `localipv4` | host candidate emits |
|---|---|---|---|
| no permission (common) | any | any | **`.local`** (stock mDNS; substitution suppressed) |
| permission / enterprise bypass | off | off | raw IP (stock leak) |
| bypass | on | off | `.local` (force-mDNS) |
| bypass | off/on | **set** | **fake IP** (substitution wins) |

The substitution fires **only** in a bypass path; the common path is never given
a raw-looking IP.

### 3d. Config + layering

- **Key `webrtc:localipv4`** (string, a private IPv4 literal). Colon namespace
  `webrtc:`, matching the family. Absent/empty/invalid → real address (rule 5,
  fail-loud on invalid). Key count 83 → 84 (triple edit: keys.h constant +
  kAllKeys + std::array size + keys_unittest declared set).
- **Layering:** `third_party/webrtc` cannot dep `//components/camoucfg` (DEPS
  confirms; zero existing includes). The config decision stays Chromium-side
  (`FilteringNetworkManager`, which already deps camoucfg for force-mDNS);
  libwebrtc consumes it through the network-provider virtual — exactly the mDNS
  bridge. No new BUILD/DEPS grant on the webrtc side.
- **`SanitizeCandidate`** (`p2p/base/port_allocator.cc:315`) replaces a host IP
  with its hostname only when `MdnsObfuscationEnabled()` (default `false`,
  per-allocator). In the fake-IP path the responder is null → obfuscation off →
  the plain fake IP passes through unsanitized. (Verified by RI-STATS/RI-SDP
  empirically.)

## 4. Verification plan

`scripts/verify_webrtc_ii_fakeip.py`, fake-device flags, private-IP regex
`10.|172.16-31.|192.168.`, fake `192.168.1.37`:

- **RI-FAKE (fix, event):** flags + `{"webrtc:localipv4":"192.168.1.37"}` → every
  host candidate in `onicecandidate` shows the fake; **0** `172.22.x`; **0**
  `.local`. RED pre-hook: 2× `172.22.x`.
- **RI-SDP (localDescription coherence):** same → `pc.localDescription.sdp`
  contains the fake, NOT `172.22.` and NOT `.local`.
- **RI-STATS (getStats coherence):** same → `getStats()` local-candidate
  `address`/`ip` == the fake; no raw. (These two are the whole justification for
  the libwebrtc-level hook — a Blink-event rewrite would fail them.)
- **RI-STOCK (rule 5):** flags, no key → ≥1 raw `172.22.x` (count 2, = Gate 0).
- **RI-NOPERM (bypass-only anti-tell):** `localipv4` set, **no** fake-device
  flags → still `.local`, 0 raw, **0 fake** — the substitution must NOT fire in
  the common path (§3c row 1).
- **RI-HIDE (force-mDNS regression):** `{"webrtc:hideLocalIps":true}` alone →
  `.local`, 0 raw (existing `verify_webrtc_ii.py` R-LEAK still holds).

## 5. Residual / out of scope

- **IPv6 (`webrtc:localipv6`): deferred, unmeasurable here.** The WSL box emits no
  v6 host candidate (Gate 0: 2 candidates, both `172.22.x` v4), so a v6 fake is
  untestable on this harness → not a key this slice (same rule that rejected
  battery event-timing and geo v6-less paths). A future v6-capable harness earns
  it.
- **Connectivity breaks (documented, accepted).** A fake advertised IP is not
  connectable — *worse* than `.local`, which is LAN-resolvable via mDNS. Opt-in,
  scraping context, same class as the policy lever's empty set. The operator owns
  the pairing with a working relay if connectivity is needed.
- **Public-IP srflx leak stays unverifiable** on WSL (no STUN/public route), same
  as sp4 §5. This slice is the *local* half only.
- **libwebrtc hunk is a vendored patch → rebase checklist item.** `Port::AddAddress`
  and the `network.h` provider addition must be re-diffed on every Chromium/webrtc
  roll (upstream may reshape `AddAddress` or the `Candidate` ctor). The Chromium
  half (`FilteringNetworkManager`) is ordinary fork code.
- **The shape-tell's magnitude is not independently confirmed** — force-mDNS §5
  noted confirming "`.local`-under-permission is anomalous" needs a real-Chrome
  no-permission capture on a multi-homed box (unavailable on WSL). This slice
  moves toward the known-real shape (a single private IP under permission) on
  first principles; it does not measure the tell's probe frequency.

## 6. Slice scope summary

| surface | this slice |
|---|---|
| host candidate under bypass (permission/enterprise) | **fake IP** via `Port::AddAddress` + `FilteringNetworkManager::GetFakeLocalIp`, key `webrtc:localipv4` |
| host candidate, no permission (common path) | unchanged `.local` (substitution suppressed — anti-tell) |
| onicecandidate / localDescription / getStats | all show the fake (single `Candidate` source) |
| IPv6 host candidate | defer (unmeasurable on WSL) |
| public-IP srflx | defer (no STUN/public route) |
| WebRTC connectivity | breaks under the key (opt-in, documented) |
