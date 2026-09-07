# webrtc-ii fake-local-IP measurement (2026-09-07)

> ## VERDICT: REJECTED 2026-09-07 (structural, not a fixable gap)
>
> Built to GREEN (verify 6/6, host + srflx-raddr surfaces coherent) before the
> whole-slice review found a **structural real-IP leak the passive harness probe
> cannot see**: peer-reflexive (prflx) candidates, created in
> `Connection::MaybeUpdateLocalCandidate` from a STUN binding response's mapped
> address, **bypass `Port::AddAddress`** and carry the real socket IP into
> `getStats()` on *any completed ICE connectivity check*. The root cause is
> fundamental (see §7): a fake **literal** IP cannot use `SetResolvedIP(real)` —
> the §2 trap — which is exactly the mechanism that makes mDNS connectivity-
> coherent. So **force-mDNS (already shipped) is prflx-safe and this approach
> structurally cannot be.** The fake-IP lever traded a *mild* shape tell for a
> *verifiable* real-IP leak under connectivity — net-negative, the geo
> accuracy-derive class. Reverted; the design/RED are kept as the record of why
> fake-local-IP is a dead lever in libwebrtc. §1–§6 below are the pre-rejection
> analysis; read §7 first.

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
appearing to never reveal the real one. **This paragraph's class claim was WRONG
(§7):** it reads as the geo-cadence class (operator-supplied value replacing a
measured leak), but because a fake literal IP cannot resolve to the real socket,
it re-introduces a real-IP leak via prflx under connectivity — the battery/
accuracy-derive class wearing an operator-supplied value. Value was assessed as
modest (media-permission-gated; force-mDNS already closes the *leak*, this only
closes *distinguishability*) — and even that modest value is net-negative once
the prflx leak is counted.

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
   `MaybeObfuscateAddress`, taking precedence, covering BOTH local-IP surfaces a
   host+srflx pair exposes:

   ```cpp
   if (std::optional<IPAddress> fake = network_->GetFakeLocalIp()) {
     // Host candidate: its address IS the real local IP. Advertise the fake.
     // IPv4 only -- guarding family also prevents overwriting a v6 address with
     // the v4 fake (which would desync the already-computed priority byte).
     if (c.is_local() && c.address().family() == AF_INET) {
       c.set_address(SocketAddress(*fake, c.address().port()));
       FinishAddingAddress(c, is_final);
       return;
     }
     // srflx candidate: address is the public reflexive IP (deferred), but its
     // related_address (raddr) carries the REAL local IP (stun_port.cc sets it to
     // socket_->GetLocalAddress()). Rewrite raddr so host and raddr agree and no
     // real local IP leaks; then fall through to the normal emission path.
     if (c.is_stun() && !c.related_address().IsNil() &&
         c.related_address().family() == AF_INET) {
       c.set_related_address(SocketAddress(*fake, c.related_address().port()));
     }
   }
   bool pending = MaybeObfuscateAddress(c, is_final);
   ...
   ```

   `set_address(IPAddress, port)` sets a literal IP with no `SetResolvedIP`
   overwrite → `HostAsURIString` returns the fake (the §2 trap does not apply
   here because we never call `SetResolvedIP`). No mDNS name → a plain host
   candidate. **The srflx `related_address` rewrite (found in review) closes the
   raddr local-IP leak** — see §5; it is inspection-only, since the WSL harness
   emits no srflx candidate (no STUN/public route). The `AF_INET` family guard is
   the fix for the v6-corruption the review found (§5).

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

- **srflx `related_address` (raddr): rewritten, but inspection-only.** Found in
  review: when a page configures a STUN server, the srflx candidate's raddr is set
  to the real local IP (`stun_port.cc` `related_address = socket_->GetLocalAddress()`),
  a *local*-IP surface (distinct from the srflx *address*, which is the public IP).
  A host-only fix would leak the real IP off `RTCIceCandidate.relatedAddress` /
  SDP `raddr` / `getStats().relatedAddress` and create a host≠raddr shape no real
  Chrome makes. The `Port::AddAddress` branch now rewrites raddr to the same fake
  (§3a). This is the **same verified mechanism** (rewrite a `SocketAddress` field
  on the `Candidate` before `FinishAddingAddress`) as the host path, applied to a
  sibling field — but **unexercised on WSL** (no STUN/public route → no srflx
  candidate forms). It is structurally guaranteed to run: all ports funnel through
  `Port::AddAddress`, so the only skip is a nil / non-v4 raddr. Inspection-only,
  same status as force-mDNS's `!allow_mdns_obfuscation_` branch.
- **IPv6 / dual-stack: v6 host candidates stay at stock (v4-only slice).** Found in
  review: `is_local()` does not test family, so without a guard the v4 fake would
  overwrite a real v6 candidate and desync the priority byte (computed from the
  real v6 precedence). The `AF_INET` family guard (§3a) fixes that corruption. The
  residual: on a dual-stack host, v6 host candidates are left at stock (which
  already leaks raw v6 under permission — not a regression), so a page correlating
  a faked v4 beside a real v6 sees an inconsistency. v6 support is the deferred
  half; a v6-capable harness earns a `webrtc:localipv6` key. (The WSL box emits no
  v6 host candidate — Gate 0: 2 candidates, both `172.22.x` v4 — so this is
  untestable here.)
- **Multi-homed host: one configured value on every interface — a shape tell.**
  The fake is a single static value applied to every v4 `Network`. On a multi-NIC
  host (VPN + physical is common) two host candidates from genuinely different
  interfaces show *distinct* `foundation` / `network-id` / `network-cost` (all
  derived from the real per-interface `Network`, unaffected here) but the
  *identical* advertised address — a shape neither stock nor `.local` produces
  (mDNS names are per-address). **Deliberately not "fixed":** deriving a
  distinct-but-fake IP per interface would invent a distribution with no capture
  of what a real multi-NIC host looks like — the accuracy-derive trap. Documented
  as an operator constraint: a host with multiple active v4 NICs should not enable
  `webrtc:localipv4`. Untestable on the single-NIC WSL box.
- **Connectivity breaks (documented, accepted).** A fake advertised IP is not
  connectable — *worse* than `.local`, which is LAN-resolvable via mDNS. Opt-in,
  scraping context, same class as the policy lever's empty set. The operator owns
  the pairing with a working relay if connectivity is needed.
- **Public-IP srflx *address* leak stays unverifiable** on WSL (no STUN/public
  route), same as sp4 §5. This slice rewrites the srflx *raddr* (local) but leaves
  the srflx *address* (public) — the proxy-defeating leak — to the deferred
  libwebrtc/public residual.
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
| srflx `related_address` (raddr, a local-IP surface) | **rewritten to the fake** (host≠raddr coherence); inspection-only (no srflx on WSL) |
| IPv6 host candidate | `AF_INET` guard (no corruption); v6 left at stock — deferred half |
| multi-homed (many v4 NICs) | same fake on all — documented operator constraint (not "fixed": per-NIC fake = manufactured distribution) |
| public-IP srflx *address* | defer (no STUN/public route) |
| WebRTC connectivity | breaks under the key (opt-in, documented) |

## 7. Why rejected (the structural leak §1–§6 missed)

The whole-slice review found a candidate surface §2's "single point feeds all
three surfaces" claim does not cover, and tracing it to its root shows the
approach is not salvageable.

**The prflx leak (verifiable, zero-infra).** `Port::AddPrflxCandidate` does
`candidates_.push_back(local)` directly — it never calls `Port::AddAddress`, so
neither the host nor the srflx-raddr substitution touches it. Its caller,
`Connection::MaybeUpdateLocalCandidate` (`p2p/base/connection.cc`, on a STUN
binding response), reads `STUN_ATTR_XOR_MAPPED_ADDRESS`; if that mapped address
matches no known candidate it copies `local_candidate_`, sets `type = kPrflx`,
`set_address(mapped_addr)` with the **real** address, and adds it. The mapped
address is the real socket source the far end observed — a network-layer fact
Chromium's candidate object does not control. `SanitizeCandidate` gates prflx on
`(is_local() || is_prflx()) && MdnsObfuscationEnabled()`; the fake path forces
`GetMdnsResponder() → nullptr`, so `MdnsObfuscationEnabled()` is false and the
prflx real address passes **raw into `getStats()`** (reported as
`type:"local-candidate"`, the exact field `RI-STATS` reads). Trigger: **any
completed ICE connectivity check.** Because the advertised host candidate is a
bogus/unreachable IP, the moment the real socket sends a STUN request and gets a
response, the mapped address won't match the fake → prflx is created → real IP.
Repro needs no STUN/TURN and no remote peer: two same-page `RTCPeerConnection`s,
exchange SDP, `addIceCandidate` guessed LAN IPs paired with **the real port this
slice deliberately preserves** (`SocketAddress(*fake, c.address().port())`); the
guess that lands reaches the real socket and the STUN round-trip yields a prflx
with the real IP in seconds. `verify_webrtc_ii_fakeip.py`'s 6/6 GREEN says
nothing about this: `iceServers:[]` + no connectivity phase means no prflx is
ever created.

**Root cause — why it cannot be fixed.** mDNS is prflx-safe because a `.local`
candidate is a *non-literal* hostname: it advertises the name but carries
`SetResolvedIP(real)` internally, so the connectivity mapped-address *matches* the
`.local` candidate → no prflx is created. A fake **literal** IP cannot do this:
`SetResolvedIP(real)` on a literal address makes `HostAsURIString` serialize the
real IP (the §2 trap that already killed approach (a)). So the fake candidate can
never resolve to the real socket, the mapped address never matches it, and prflx
is *always* created on connectivity. This is intrinsic to advertising a literal
fake that differs from the bound socket — not a missed call site.

**Why not intercept `MaybeUpdateLocalCandidate` too.** (1) The prflx address *is*
the real mapped address; if the peer is behind NAT it is the real **public** IP,
so rewriting it to a configured LAN IP is a new incoherence, not a fix. (2) The
brute-force still fires — it is the STUN round-trip itself that reveals the
socket, not the prflx object; hiding the readout leaves the leak. (3) Faking the
port too (to kill the brute-force) makes the candidate fully fictional, so every
connectivity attempt fails identically — i.e. the policy lever's empty-set
outcome with extra steps, having lost the "matches real-Chrome shape" rationale
that was the entire value.

**Conclusion.** force-mDNS (shipped, `webrtc:hideLocalIps`) is correct in every
scenario this slice touches: `.local` under permission (a mild shape tell),
LAN-resolvable, **prflx-safe**, connectivity works. The fake-IP lever trades that
mild shape tell for a verifiable real-IP leak under connectivity plus a
brute-force primitive — strictly net-negative. It stays rejected until a
libwebrtc mechanism exists to advertise a fake that *resolves* to the real socket
(which is what mDNS already is). The reviewer's secondary point was the same root
cause from another angle: with both `hideLocalIps` and `localipv4` set, the
fake-engaged `GetMdnsResponder() → nullptr` is family-blind and silently disables
the v6 `.local` protection the operator asked for — forcing obfuscation *off* to
emit a literal fake defeats the mechanism that protects everything else.

**Empirical RED (designed, source-verified, not harness-run).** The two-PC
connectivity probe above fails on the fake-IP binary (real IP in `getStats()`)
and passes on force-mDNS. It was not added as a live verify case: writing a
reliable headless connectivity round-trip is fiddly and the rejection stands on
the reviewer's line-by-line verification against live upstream libwebrtc
(`connection.cc` / `port.cc` / `port_allocator.cc`). A future "let's just fake the
IP" attempt should add it before believing a GREEN passive probe.
