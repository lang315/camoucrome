// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/coherence_validator.h"

#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <variant>

#include "base/environment.h"
#include "base/logging.h"
#include "base/strings/string_number_conversions.h"
#include "components/camoucfg/derive.h"
#include "components/camoucfg/domain_validator.h"
#include "components/camoucfg/gl_params.h"
#include "components/camoucfg/invariants.h"
#include "components/camoucfg/keys.h"

namespace camoucfg {
namespace {

OsFamily OsFamilyOfKey(const ConfigScope& scope, std::string_view key) {
  std::optional<std::string> value = GetString(scope, key);
  if (!value.has_value()) {
    return OsFamily::kUnknown;
  }
  // Which reading applies is a property of the key, not of the text. osInfo
  // holds a user-agent OS segment and platform holds a UA-CH token; guessing
  // from the string would make "Linux" ambiguous between the two, since it is
  // a valid value of one and a substring of the other.
  return key == keys::kUaOsInfo ? OsFamilyFromOsInfo(*value)
                                : OsFamilyFromUaChPlatform(*value);
}

// A key that is absent, or present but unrecognised, constrains nothing.
//
// That is deliberate and worth stating, because "unrecognised" looks like
// something a validator should complain about. This entry's job is catching
// values that CONTRADICT each other. An absent key constrains nothing FOR
// THIS RELATIONAL ENTRY -- the incoherence an absent partner creates (one
// channel spoofed, the other silently reporting the real OS) is reported by
// the startup diagnostic in content/browser/browser_main_loop.cc, not here.
// An unrecognised value is a per-key type question rather than a relational
// one -- SP5b's to reject, not this entry's to guess about. Treating an
// unparseable string as a disagreement would make the validator report a
// contradiction it cannot actually demonstrate.
std::vector<Violation> CheckSameOsFamily(const ConfigScope& scope,
                                         const invariants::Invariant& inv) {
  OsFamily first = OsFamilyOfKey(scope, inv.keys[0]);
  OsFamily second = OsFamilyOfKey(scope, inv.keys[1]);
  if (first == OsFamily::kUnknown || second == OsFamily::kUnknown ||
      first == second) {
    return {};
  }

  // keys[0] is authoritative. For this entry that is ua:osInfo, which lands in
  // the user-agent string -- the surface a detector reads first -- so naming
  // the other as the one to change minimises the difference from what pages
  // already see.
  Violation v;
  v.invariant_id = inv.id;
  v.authoritative_key = std::string(inv.keys[0]);
  v.repaired_key = std::string(inv.keys[1]);
  v.old_value = GetString(scope, inv.keys[1]).value_or(std::string());
  v.new_value = std::string(CanonicalUaChPlatformFor(first));
  return {v};
}

// keys[1] must be <= keys[0]. Both are read with GetUint32 because that is how
// sp4a-screen consumes them; a value that is absent, or present with a type
// GetUint32 rejects, yields nullopt and constrains nothing -- the same
// boundary CheckSameOsFamily draws, and for the same reasons. A lone spoofed
// key (keys[1] configured, keys[0] left real) is not a contradiction this
// entry can demonstrate: with only one value present there is nothing to
// compare. Equality is allowed -- availWidth == width is the real no-taskbar /
// fullscreen state, so the check fires only on strictly greater.
std::vector<Violation> CheckFitsWithin(const ConfigScope& scope,
                                       const invariants::Invariant& inv) {
  std::optional<uint32_t> bound = GetUint32(scope, inv.keys[0]);
  std::optional<uint32_t> value = GetUint32(scope, inv.keys[1]);
  if (!bound.has_value() || !value.has_value() || *value <= *bound) {
    return {};
  }

  // keys[0] is the authoritative bound -- the display the work area is carved
  // out of -- so the log names keys[1] as the value to lower and suggests the
  // bound as its new value. Not applied: ValidateAtStartup reports, it does
  // not write (see the LOG below).
  Violation v;
  v.invariant_id = inv.id;
  v.authoritative_key = std::string(inv.keys[0]);
  v.repaired_key = std::string(inv.keys[1]);
  v.old_value = base::NumberToString(*value);
  v.new_value = base::NumberToString(*bound);
  return {v};
}

// keys[0] (ua:osInfo) claims an OS; keys[1] (navigator.platform) must be that
// OS's canonical reduced platform ("Win32", "MacIntel", "Linux x86_64",
// "Linux armv81"). Only the OS family of keys[0] is read, with OsFamilyOfKey --
// the same helper CheckSameOsFamily uses -- so keys[0] stays literally
// authoritative and the log names a key that is actually set. A ua:platform-
// only OS claim is therefore out of this entry's reach, the same boundary
// CheckSameOsFamily draws, and the startup diagnostic warns on it instead.
//
// A canonical-STRING compare, not a family one: Linux and ChromeOS both report
// "Linux x86_64" (CanonicalNavigatorPlatformFor collapses them), so comparing
// the strings accepts either OS beside that value -- the "platform bucket".
// Fires only when the OS is known AND navigator.platform is configured AND its
// value is not the canonical one. An ABSENT navigator.platform is the SP1b
// derive's job (it fills the key from the claimed OS); this entry and the
// derive never both fire on one config.
// keys[0] is a string list, keys[1] a string. Fires only when both are
// present and disagree; the list is authoritative (it carries the whole
// preference order), so keys[1] is repaired to its head.
std::vector<Violation> CheckListHeadEquals(const ConfigScope& scope,
                                           const invariants::Invariant& inv) {
  std::vector<std::string> list = GetStringList(scope, inv.keys[0]);
  std::optional<std::string> value = GetString(scope, inv.keys[1]);
  if (list.empty() || !value.has_value() || list[0] == *value) {
    return {};
  }
  Violation v;
  v.invariant_id = inv.id;
  v.authoritative_key = std::string(inv.keys[0]);
  v.repaired_key = std::string(inv.keys[1]);
  v.old_value = *value;
  v.new_value = list[0];
  return {v};
}

// Both strings present and unequal. Exact, case-sensitive: every value these
// entries compare is one Chrome reports canonically (BCP-47 tags, ANGLE
// strings), so a case difference is itself a wrong value, not a spelling.
std::vector<Violation> CheckSameString(const ConfigScope& scope,
                                       const invariants::Invariant& inv) {
  std::optional<std::string> first = GetString(scope, inv.keys[0]);
  std::optional<std::string> second = GetString(scope, inv.keys[1]);
  if (!first.has_value() || !second.has_value() || *first == *second) {
    return {};
  }
  Violation v;
  v.invariant_id = inv.id;
  v.authoritative_key = std::string(inv.keys[0]);
  v.repaired_key = std::string(inv.keys[1]);
  v.old_value = *second;
  v.new_value = *first;
  return {v};
}

// The OS family an ANGLE renderer description commits to, from the backend
// token it carries. Only tokens exclusive to one family are recognised:
// Direct3D ships on Windows alone, Metal on Apple platforms alone. OpenGL and
// Vulkan renderers exist on Linux, Android and older macOS, so they return
// kUnknown and constrain nothing -- the registry's rule for unrecognised
// values. Measured shapes on 2026-09-10 are in invariants.json's `why`.
OsFamily OsFamilyOfRendererBackend(std::string_view renderer) {
  if (renderer.find("Direct3D") != std::string_view::npos) {
    return OsFamily::kWindows;
  }
  if (renderer.find("Metal") != std::string_view::npos) {
    return OsFamily::kMac;
  }
  return OsFamily::kUnknown;
}

// keys[0] is kUaOsInfo; the renderer is resolved through GLRenderer() -- the
// helper the pairing check uses -- so a renderer supplied through
// webGl:parameters["37446"] rather than webGl:renderer is checked too. There
// is no canonical renderer for an OS, so new_value is descriptive; the
// mutation test asserts repaired_key, which is the contract.
std::vector<Violation> CheckRendererBackendFitsOs(
    const ConfigScope& scope, const invariants::Invariant& inv) {
  OsFamily claimed = OsFamilyOfKey(scope, inv.keys[0]);
  std::optional<std::string> renderer = GLRenderer(scope, /*is_webgl2=*/false);
  if (claimed == OsFamily::kUnknown || !renderer.has_value()) {
    return {};
  }
  OsFamily backend = OsFamilyOfRendererBackend(*renderer);
  if (backend == OsFamily::kUnknown || backend == claimed) {
    return {};
  }
  Violation v;
  v.invariant_id = inv.id;
  v.authoritative_key = std::string(inv.keys[0]);
  v.repaired_key = std::string(inv.keys[1]);
  v.old_value = *renderer;
  v.new_value = std::string("a renderer whose ANGLE backend runs on ") +
                std::string(CanonicalUaChPlatformFor(claimed)) +
                (claimed == OsFamily::kWindows ? " (Direct3D11)"
                 : claimed == OsFamily::kMac   ? " (Metal)"
                                               : " (OpenGL or Vulkan)");
  return {v};
}

std::vector<Violation> CheckSamePlatformBucket(
    const ConfigScope& scope, const invariants::Invariant& inv) {
  OsFamily claimed = OsFamilyOfKey(scope, inv.keys[0]);
  if (claimed == OsFamily::kUnknown) {
    return {};
  }
  std::optional<std::string> configured = GetString(scope, inv.keys[1]);
  if (!configured.has_value()) {
    return {};
  }
  std::string_view canonical = CanonicalNavigatorPlatformFor(claimed);
  // A known OS family always maps to a non-empty canonical platform (only
  // kUnknown, excluded above, yields empty). Guarded anyway so that if the
  // OsFamily enum ever grows a member without a CanonicalNavigatorPlatformFor
  // case, this reports nothing rather than "should be ''" -- the misleading
  // repair target this project forbids.
  if (canonical.empty() || *configured == canonical) {
    return {};
  }

  Violation v;
  v.invariant_id = inv.id;
  v.authoritative_key = std::string(inv.keys[0]);
  v.repaired_key = std::string(inv.keys[1]);
  v.old_value = *configured;
  v.new_value = std::string(canonical);
  return {v};
}

// Whether an API's renderer (or vendor, when `vendor` is true) resolves to a
// value the page would actually read. This mirrors the two-step resolution
// getParameter() performs in webgl_rendering_context_base.cc (sp3b patch,
// UNMASKED_*_WEBGL cases): the dedicated key wins, else a STRING entry in the
// parameters table at that pname. Reading only the dedicated key here would
// call a config that spoofs via the parameters table "absent" -- and under
// strict that refuses a fingerprint the page sees whole. 0x9245 is
// UNMASKED_VENDOR_WEBGL, 0x9246 UNMASKED_RENDERER_WEBGL; GLParam reads
// ParsedConfig() and ignores `scope`, which is correct at browser startup.
bool GLStringResolves(const ConfigScope& scope, bool is_webgl2, bool vendor) {
  if ((vendor ? GLVendor(scope, is_webgl2) : GLRenderer(scope, is_webgl2))
          .has_value()) {
    return true;
  }
  std::optional<GLValue> param =
      GLParam(scope, vendor ? 0x9245u : 0x9246u, is_webgl2);
  return param.has_value() && std::holds_alternative<std::string>(*param);
}

}  // namespace

std::vector<Violation> Validate(const ConfigScope& scope) {
  std::vector<Violation> violations;
  for (const invariants::Invariant& inv : invariants::kAllInvariants) {
    switch (inv.relation) {
      case invariants::Relation::kSameOsFamily: {
        std::vector<Violation> found = CheckSameOsFamily(scope, inv);
        violations.insert(violations.end(), found.begin(), found.end());
        break;
      }
      case invariants::Relation::kFitsWithin: {
        std::vector<Violation> found = CheckFitsWithin(scope, inv);
        violations.insert(violations.end(), found.begin(), found.end());
        break;
      }
      case invariants::Relation::kSamePlatformBucket: {
        std::vector<Violation> found = CheckSamePlatformBucket(scope, inv);
        violations.insert(violations.end(), found.begin(), found.end());
        break;
      }
      case invariants::Relation::kListHeadEquals: {
        std::vector<Violation> found = CheckListHeadEquals(scope, inv);
        violations.insert(violations.end(), found.begin(), found.end());
        break;
      }
      case invariants::Relation::kSameString: {
        std::vector<Violation> found = CheckSameString(scope, inv);
        violations.insert(violations.end(), found.begin(), found.end());
        break;
      }
      case invariants::Relation::kRendererBackendFitsOs: {
        std::vector<Violation> found = CheckRendererBackendFitsOs(scope, inv);
        violations.insert(violations.end(), found.begin(), found.end());
        break;
      }
    }
  }
  return violations;
}

std::optional<PairingViolation> CheckPairing(bool renderer_resolves,
                                             bool vendor_resolves,
                                             std::string_view renderer_key,
                                             std::string_view vendor_key) {
  // Both set or both absent is coherent. Only the exclusive-or is a violation:
  // one channel spoofed while the other reports the real GPU.
  if (renderer_resolves == vendor_resolves) {
    return std::nullopt;
  }
  PairingViolation v;
  if (renderer_resolves) {
    v.present_key = std::string(renderer_key);
    v.absent_key = std::string(vendor_key);
  } else {
    v.present_key = std::string(vendor_key);
    v.absent_key = std::string(renderer_key);
  }
  return v;
}

std::vector<PairingViolation> ValidatePairing(const ConfigScope& scope) {
  std::vector<PairingViolation> violations;
  // webGl and webGl2 are independent surfaces: a page can read one, the other,
  // or both, so each pair is checked on its own. A config spoofing webGl:
  // renderer beside webGl2:vendor is two violations, not zero.
  for (bool is_webgl2 : {false, true}) {
    std::optional<PairingViolation> v = CheckPairing(
        GLStringResolves(scope, is_webgl2, /*vendor=*/false),
        GLStringResolves(scope, is_webgl2, /*vendor=*/true),
        is_webgl2 ? keys::kWebGl2Renderer : keys::kWebGlRenderer,
        is_webgl2 ? keys::kWebGl2Vendor : keys::kWebGlVendor);
    if (v.has_value()) {
      violations.push_back(*v);
    }
  }
  return violations;
}

bool CapabilityLeaksIdentity(bool capability_configured,
                             bool renderer_resolves,
                             bool vendor_resolves) {
  return capability_configured && !renderer_resolves && !vendor_resolves;
}

std::vector<CapabilityViolation> ValidateCapabilityIdentity(
    const ConfigScope& scope) {
  std::vector<CapabilityViolation> violations;
  for (bool is_webgl2 : {false, true}) {
    // Both identity strings must be absent for this entry to fire: when exactly
    // one resolves, ValidatePairing already names the missing one. GLStringResolves
    // (the pairing check's helper) mirrors the consumer's full resolution, so a
    // renderer supplied through the parameters table counts as resolved here too.
    const bool renderer_resolves =
        GLStringResolves(scope, is_webgl2, /*vendor=*/false);
    const bool vendor_resolves =
        GLStringResolves(scope, is_webgl2, /*vendor=*/true);

    struct Cap {
      std::string_view key;
      bool configured;
    };
    // present-AND-non-empty per gl_params (empty map/list resolves to the host
    // value on every read, so it spoofs nothing and is not a leak).
    const Cap caps[] = {
        {is_webgl2 ? keys::kWebGl2Parameters : keys::kWebGlParameters,
         GLParamsConfigured(scope, is_webgl2)},
        {is_webgl2 ? keys::kWebGl2Extensions : keys::kWebGlExtensions,
         GLExtensionsConfigured(scope, is_webgl2)},
        {is_webgl2 ? keys::kWebGl2ShaderPrecision : keys::kWebGlShaderPrecision,
         GLShaderPrecisionConfigured(scope, is_webgl2)},
        {is_webgl2 ? keys::kWebGl2ContextAttrs : keys::kWebGlContextAttrs,
         GLContextAttrsConfigured(scope, is_webgl2)},
    };
    for (const Cap& cap : caps) {
      if (!CapabilityLeaksIdentity(cap.configured, renderer_resolves,
                                   vendor_resolves)) {
        continue;
      }
      CapabilityViolation v;
      v.capability_key = std::string(cap.key);
      v.renderer_key = std::string(is_webgl2 ? keys::kWebGl2Renderer
                                             : keys::kWebGlRenderer);
      v.vendor_key =
          std::string(is_webgl2 ? keys::kWebGl2Vendor : keys::kWebGlVendor);
      violations.push_back(v);
    }
  }
  return violations;
}

bool ValidateAtStartup(const ConfigScope& scope) {
  std::vector<Violation> violations = Validate(scope);
  // Single-key domain checks (SP5b) run alongside the relational ones. They
  // must be collected BEFORE the early return: a configuration with no
  // relational violation can still carry an out-of-range value, and returning
  // true on an empty relational result would skip the domain check entirely.
  std::vector<DomainViolation> domain_violations = ValidateDomains(scope);
  // WebGL renderer/vendor pairing: a presence incoherence, not a value one, so
  // it is collected here beside the domain checks rather than in the invariant
  // registry (which owns relations between keys that are both present). Design
  // sp3-webgl-canvas-design.md:283 requires rejection, so it feeds the
  // strict-refusal path below. The analogous ua: half-config in the sp5a
  // diagnostic block only WARNS -- SP1 asked for the same all-or-nothing
  // rejection there (sp1-navigator-identity-design.md:419-423) but sp5a shipped
  // it warn-only; realigning ua: is that block's business, not this slice's.
  std::vector<PairingViolation> pairing_violations = ValidatePairing(scope);
  // A spoofed GL capability with both identity strings absent (design sec.7.1:
  // the unit of configuration is a whole captured profile, not editable fields).
  std::vector<CapabilityViolation> capability_violations =
      ValidateCapabilityIdentity(scope);
  if (violations.empty() && domain_violations.empty() &&
      pairing_violations.empty() && capability_violations.empty()) {
    return true;
  }

  std::unique_ptr<base::Environment> env = base::Environment::Create();
  const bool strict = env->GetVar("CAMOU_CONFIG_STRICT").has_value();

  for (const Violation& v : violations) {
    // The message says what is true: the value is wrong and it has NOT been
    // changed. Applying repairs needs a write path into the cached
    // configuration, which is a change to a component three sub-projects
    // depend on and gets its own task and its own tests.
    //
    // The function is called ValidateAtStartup and not
    // ValidateAndRepairAtStartup for the same reason. A name that claims an
    // action it does not perform is the failure this project has counted
    // repeatedly, and it is worse in an identifier than in a log line because
    // it misleads at the call site rather than at the console.
    LOG(ERROR) << "camoucfg: invariant '" << v.invariant_id << "' violated. '"
               << v.repaired_key << "' is '" << v.old_value
               << "', which disagrees with '" << v.authoritative_key
               << "'. It should be '" << v.new_value
               << "'. Not repaired: set it yourself, or set "
                  "CAMOU_CONFIG_STRICT=1 to refuse startup instead of running "
                  "an incoherent fingerprint.";
  }

  for (const DomainViolation& v : domain_violations) {
    // Same report-don't-repair posture: the value is wrong and untouched, so
    // the surface it feeds will not be spoofed. Said loudly because the
    // alternative -- a silently dropped value and a stock-looking result -- is
    // exactly the footgun this check exists to remove.
    LOG(ERROR) << "camoucfg: '" << v.key << "' is '" << v.value
               << "', out of range: " << v.reason
               << ". The spoof for this surface will not apply -- a consumer "
                  "that rejects one field rejects the whole surface, so a valid "
                  "neighbour is lost with it. Fix it, or set "
                  "CAMOU_CONFIG_STRICT=1 to refuse startup instead of running "
                  "with it silently dropped.";
  }

  for (const PairingViolation& v : pairing_violations) {
    // Presence, not value: naming a "should be" here would mean inventing the
    // missing string, which is exactly the fingerprint the operator did not
    // choose. So the message names the two keys and the leak, and stops there.
    LOG(ERROR) << "camoucfg: '" << v.present_key << "' is set but its pair '"
               << v.absent_key
               << "' is not. A page reads both through "
                  "WEBGL_debug_renderer_info, so the configured value sits "
                  "beside this machine's real one -- an incoherent pair. Set "
                  "both, or neither, or set CAMOU_CONFIG_STRICT=1 to refuse "
                  "startup.";
  }

  for (const CapabilityViolation& v : capability_violations) {
    // A capability without its identity: a spoofed GPU capability beside the
    // real GPU identity. No repair target -- inventing renderer/vendor would be
    // inventing a fingerprint -- so the message names the capability and both
    // identity keys and stops.
    LOG(ERROR) << "camoucfg: '" << v.capability_key
               << "' is set but neither '" << v.renderer_key << "' nor '"
               << v.vendor_key
               << "' is. A page reads the configured GPU capability beside this "
                  "machine's real GPU identity -- an incoherent profile. Set "
                  "the identity strings from the same capture, or set "
                  "CAMOU_CONFIG_STRICT=1 to refuse startup.";
  }
  return !strict;
}

}  // namespace camoucfg
