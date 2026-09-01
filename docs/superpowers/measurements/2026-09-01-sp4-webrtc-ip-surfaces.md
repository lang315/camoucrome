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
if (std::optional<std::string> policy = camoucfg::GetString(
        camoucfg::ScopeFor(nullptr), camoucfg::keys::kWebrtcIpHandlingPolicy);
    policy && !policy->empty()) {
  *ip_handling_policy = blink::ToWebRTCIPHandlingPolicy(*policy);
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
  selection. Setting `default_public_interface_only` suppresses local private-IP
  host candidates AT GATHERING — subsuming the mDNS-permission gap (§1) — and
  `disable_non_proxied_udp` additionally forces WebRTC through the proxy.
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

Verify proves the policy is APPLIED, observed via candidate suppression (the
public-IP routing benefit is not reproducible without a STUN server + proxy in
the WSL harness — stated as a limitation):

- **W1 (policy suppresses local IP):** launch with the fake-device flags (which
  leak `172.22.x` in stock, §1) AND `CAMOU_CONFIG {"webrtc:ipHandlingPolicy":
  "default_public_interface_only"}` → NO private IP (10./172.16-31./192.168.) in
  any candidate. RED pre-hook: the private IP is present. GREEN: absent.
- **W2 (no-op absent):** no config → candidate set equals the stock
  `--capture-baseline` (rule 5).
- Optionally **W3 (`disable_non_proxied_udp`):** no `typ host` UDP candidate.

## 5. Residual / out of scope (documented)

- **Public-IP proxy leak is the real threat but harness-unverifiable.** The
  policy addresses it (`disable_non_proxied_udp`), but proving it needs a STUN
  server + a proxy the WSL harness lacks. Verify proves the policy is applied
  (local suppression), not the public-IP routing. The launcher/proxy layer must
  choose a policy value coherent with its proxy (e.g. `disable_non_proxied_udp`
  for a UDP-incapable HTTP proxy).
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
