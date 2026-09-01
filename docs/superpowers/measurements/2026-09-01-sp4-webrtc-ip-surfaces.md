# SP4-webrtc-ip surfaces measurement (2026-09-01)

Checkout HEAD `a727b57805`, `out/Default` content_shell.

WebRTC leaks the client's IP addresses through `RTCPeerConnection` ICE
candidates — the classic anti-detect failure, because a WebRTC candidate can
carry the client's **real public IP** even behind an HTTP/SOCKS proxy (defeating
the proxy) and its **local LAN IP** (a fingerprint/correlation signal). Like
timezone/locale, Chromium already has native, page-invisible C++ levers; the
camoucrome gap is that the config layer does not drive them. Per the 2026-09-01
scope decision, this slice config-drives the **`webrtc_ip_handling_policy`**
renderer preference — one native lever that both suppresses local-IP candidates
and stops non-proxied UDP (the public-IP proxy leak).

---

## 1. Surfaces & measured stock behavior (content_shell)

Probe: `new RTCPeerConnection({iceServers:[]})` + `createDataChannel` +
`setLocalDescription(createOffer())`, collect `onicecandidate` strings.

- **No media permission (default flags):** ONE host candidate, mDNS-obfuscated:
  `candidate:... 41f844f3-...-....local 40284 typ host`. No raw local IP in the
  SDP. Chromium's `kWebRtcHideLocalIpsWithMdns` (Blink feature,
  `FEATURE_ENABLED_BY_DEFAULT`, `features.cc:2449`) already replaces the local IP
  with a random `.local` mDNS name. **The raw-local-IP leak Camoufox spoofs is
  not present in stock Chromium's no-permission path.**
- **With `--use-fake-device-for-media-stream --use-fake-ui-for-media-stream`
  (simulating media permission):** TWO host candidates carrying the **RAW LOCAL
  IP `172.22.42.251`** (the WSL interface) — mDNS obfuscation is bypassed once
  the page is in a media-permission context. **This is the residual local-IP
  gap:** a page with camera/mic access sees the real LAN IP.
- **Public IP (srflx):** requires a STUN server (not configured in the probe) and
  external network — not reproducible in the WSL harness. This is the
  proxy-defeating leak (real public IP via a STUN-reflexive candidate that
  bypasses the proxy's TCP tunnel).

## 2. Native levers (Chromium)

- **mDNS obfuscation** — `blink::features::kWebRtcHideLocalIpsWithMdns`, consumed
  at `peer_connection_dependency_factory.cc:~793` (creates the
  `MdnsResponderAdapter`). Default-on; bypassed under media permission (§1).
- **`webrtc_ip_handling_policy`** (the chosen lever) — a
  `blink::mojom::WebRtcIpHandlingPolicy` produced by
  `RendererBlinkPlatformImpl::GetWebRTCRendererPreferences`
  (`content/renderer/renderer_blink_platform_impl.cc:649`), read from
  `render_frame->GetRendererPreferences().webrtc_ip_handling_policy` (line 667),
  then per-URL overrides. content_shell forces it via the
  `--force-webrtc-ip-handling-policy` switch (`content/shell/browser/shell.cc:127`).
  Enum + string map in `third_party/blink/public/common/peerconnection/webrtc_ip_handling_policy.h`:
  - `kWebRTCIPHandlingDefault` = `"default"` — enumerate all interfaces (Chrome
    default; relies on mDNS to hide locals).
  - `kWebRTCIPHandlingDefaultPublicAndPrivateInterfaces` =
    `"default_public_and_private_interfaces"` — default route + its private addr.
  - `kWebRTCIPHandlingDefaultPublicInterfaceOnly` =
    `"default_public_interface_only"` — default route only, **exposes no local
    addresses**.
  - `kWebRTCIPHandlingDisableNonProxiedUdp` = `"disable_non_proxied_udp"` — only
    TCP/relay unless the proxy supports UDP; **no local addresses, no
    non-proxied public IP**.
  `blink::ToWebRTCIPHandlingPolicy(std::string_view)` maps a string → enum
  (unknown/empty → default, per its unittest).

## 3. Port design (this slice)

Single hook in `GetWebRTCRendererPreferences`
(`content/renderer/renderer_blink_platform_impl.cc`), AFTER the base pref read
and the per-URL loop (so config is the source of truth, overriding both):

```cpp
// As shipped: validate against the four known policy strings first, so an
// unrecognized value warns and keeps the real pref rather than silently
// degrading to `default` (ToWebRTCIPHandlingPolicy maps unknown -> default).
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

- **Key:** `webrtc:ipHandlingPolicy` (colon namespace `webrtc:`, matching
  Camoufox's `webrtc:` family). Value = a policy string
  (`"default_public_interface_only"` / `"disable_non_proxied_udp"` / …). Keys
  63 → 64.
- **Rule 5 no-op:** key absent → the real renderer pref is used unchanged (stock
  behavior, mDNS-hidden local IP).
- **Why this choke:** `GetWebRTCRendererPreferences` is the single point where the
  effective `ip_handling_policy` is produced for the peer-connection factory;
  overriding `*ip_handling_policy` here feeds the port allocator's interface
  selection. The override reads `GlobalScope` (not the frame's `RendererPreferences`),
  so it is frame-independent — any caller of this function, including a
  dedicated-worker peer connection (same `RendererBlinkPlatformImpl`), gets the
  override. Setting `default_public_interface_only` suppresses local private-IP
  host candidates AT GATHERING — subsuming the mDNS-permission gap (§1) — and
  `disable_non_proxied_udp` additionally forces WebRTC through the proxy.
  (Worker/worklet PC routing was reasoned, not re-verified against upstream
  source; the frame-independent read makes a bypass unlikely.)
- **Measured effect of the protective policies (whole-branch characterization).**
  On the WSL box (a single private interface, no STUN/public route), BOTH
  `default_public_interface_only` and `disable_non_proxied_udp` produce **ZERO ICE
  candidates** — the raw `172.22.x` host candidate (2 of them, udp+tcp, in the
  no-config baseline) simply disappears; there is no public interface to emit and
  no STUN reflexive candidate. So "suppresses local-IP candidates" here means
  **empties the candidate set**, NOT masks-to-a-public-IP. On a real deployment
  WITH a public route + STUN/TURN, `default_public_interface_only` emits a
  public-only srflx candidate (the intended mask) and `disable_non_proxied_udp`
  routes via the proxy — the empty result is a harness artifact. The
  detectability/connectivity consequences of the empty set are in §5.
- **content/renderer needs the camoucfg dep** — `content/renderer/BUILD.gn` has
  none today (this is the first camoucrome hook in content/renderer). Add
  `//components/camoucfg`. `camoucfg::ScopeFor(nullptr)` returns GlobalScope
  (CAMOU_CONFIG is process-wide).
- **Malformed input (tz-locale lesson):** `ToWebRTCIPHandlingPolicy` maps an
  unrecognized string to `default` silently. A config typo would therefore
  silently fall back to the leaky default. The hook should validate against the
  four known policy strings and `LOG(WARNING)` on an unrecognized value (same
  fail-loud idiom as sp4-tz-locale), rather than silently degrading.

## 4. Verification plan

Verify is a **"hook-took-effect" gate, NOT a "masking works" gate.** It proves
the config key changes the candidate set end-to-end; it does NOT prove
real-world public-IP masking (no STUN/proxy in the WSL harness — a stated
limitation). Because both protective policies EMPTY the set here (§3
characterization), W1's "no private IP" passes on an empty candidate list
(`any([]) == False`); its causal force comes from the RED-first record (pre-hook
W1 FAIL with `172.22.x` present) plus the captured baseline JSON containing the
private IP — NOT from W1 alone on the shipped binary.

- **W1 (hook took effect):** fake-device flags (which leak `172.22.x` in stock,
  §1) + `CAMOU_CONFIG {"webrtc:ipHandlingPolicy":"default_public_interface_only"}`
  → NO private IP (10./172.16-31./192.168.) in any candidate. RED pre-hook: the
  private IP is present. GREEN: absent (empty set on this box).
- **W2 (no-op absent):** no config → candidate set equals the stock
  `--capture-baseline` (rule 5) — and that baseline contains the `172.22.x` leak,
  which is what makes W1's GREEN meaningful.
- Optional (not shipped) hardening: have W2 also assert the baseline is
  non-empty / contains a private IP, making the verify self-contained rather
  than dependent on the one-time RED record.

## 5. Residual / out of scope (documented)

- **Public-IP proxy leak is the real threat but harness-unverifiable.** The
  policy addresses it (`disable_non_proxied_udp`), but proving it needs a STUN
  server + a proxy the WSL harness lacks. Verify proves the policy is applied
  (local suppression), not the public-IP routing. The launcher/proxy layer must
  choose a policy value coherent with its proxy (e.g. `disable_non_proxied_udp`
  for a UDP-incapable HTTP proxy).
- **Empty-candidate-set is itself a tell, and breaks connectivity.** When a
  protective policy yields zero candidates (the §3 no-public-route/no-STUN case),
  that is detectable: a normal browser on a real network returns ≥1 candidate
  (an mDNS host, or a STUN srflx), so an otherwise-normal browser with zero
  candidates is anomalous. It also means WebRTC cannot connect at all. Therefore
  a protective policy is only coherent alongside a working TURN/relay (or a
  UDP-capable proxy) that supplies a plausible non-local candidate; setting
  `disable_non_proxied_udp`/`default_public_interface_only` without one degrades
  from "masked" to "empty + broken". The launcher/proxy layer owns this pairing.
- **Opt-in, not default-on.** Protection is only as strong as the configured
  policy value. Key absent → stock `default` (mDNS hides local IP with the
  permission-case gap of §1 still open). Closing the permission-case local leak
  unconditionally would need forcing mDNS always-on (a different lever, not this
  slice) — documented as a follow-on (webrtc-ii).
- **Camoufox fake-local-IP (`webrtc:localipv4/ipv6`) not ported.** A configured
  plausible LAN IP is stealthier than `.local`/suppression but needs libwebrtc
  port-allocator surgery; deferred (webrtc-ii). This slice uses the native policy
  lever only.
- **`allow_mdns_obfuscation` and `webrtc_udp_min/max_port`** in the same function
  are left as the real prefs (not config-driven) — out of scope.

## 6. Slice scope summary

| surface | this slice |
|---|---|
| `webrtc_ip_handling_policy` | **config-drive** — override in `GetWebRTCRendererPreferences`, key `webrtc:ipHandlingPolicy` |
| local-IP host candidate | suppressed when policy = `default_public_interface_only`/`disable_non_proxied_udp` (opt-in) |
| public-IP srflx (proxy leak) | addressed by `disable_non_proxied_udp` policy; harness-unverifiable (no STUN/proxy) |
| fake local IP (`webrtc:localipv4/ipv6`) | defer (webrtc-ii) — libwebrtc port-allocator surgery |
| force-mDNS-always-on (permission gap) | defer (webrtc-ii) — different lever |
