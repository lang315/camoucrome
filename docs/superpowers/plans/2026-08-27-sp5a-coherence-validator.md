# SP5a — Invariant registry, validator and derivation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a configuration that describes an impossible machine fail at launch instead
of being discovered by a detector — one registry of invariants, one validator that runs in
the browser process before any renderer exists, and one function that answers "what
operating system are we claiming".

**Architecture:** `settings/invariants.json` is the single source of truth. A hand-written
generated form, `additions/camoucfg/invariants.h`, is what C++ compiles against; the JSON
is what the fingerprint generator and the test suite read. `coherence_validator.{h,cc}`
evaluates the registry against a parsed config and applies one of three policies per entry.
`derive.{h,cc}` holds values that are a function of other values and therefore have no
config key of their own. Validation runs from `BrowserMainLoop::EarlyInitialization`,
replacing the side effect SP0 left there.

**Tech Stack:** C++20 (Chromium style), GN/Siso, `content_shell`, Python 3 + Playwright over
CDP for the browser-level check.

## Why this sub-project is not speculative

SP1a shipped a defect and named this sub-project as its owner. `patches/sp1a-ua-producer.patch`
carries this comment, in code that is running today:

> This does not make a partial configuration coherent — `ua:platform` without `ua:osInfo`
> still yields a Linux string beside a Windows platform. Rejecting that combination is
> SP5a's invariant validator, and SP1's spec assigns it there explicitly.

So SP5a has a tracer bullet the way SP0 had `hardwareConcurrency`: **one real invariant,
over keys that already exist and are already read, describing an incoherence that is live
right now.** That is what proves the machinery. The catalogue of the remaining invariants
is SP5b and fills in as SP1b, SP3 and SP4 land.

## Global Constraints

Copied from `docs/superpowers/specs/00-conventions.md` and the SP5 spec. Every task's
requirements implicitly include this section.

- **No JavaScript injection into page-visible scopes.**
- **Native-looking accessors** and an unchanged `Object.keys(window)` against a stock build.
- **Worker parity** for any surface exposed to both.
- **Coherence over coverage.** A spoofed value contradicting another is worse than not
  spoofing. That is this sub-project's entire subject.
- **Fall back to the real value** when config is absent, never to a placeholder.
- **Bad config must never crash a renderer.** A crash is itself a fingerprint. Validation
  therefore runs in the **browser process**, before the first renderer is spawned, which is
  also the only point at which the fork can still refuse to start.
- **Every `camoucfg` getter takes a scope first.** In the browser process that is
  `camoucfg::GlobalScope()`.
- **A derived value gets no config key.** An independent override for something computed
  from another value creates the opportunity for incoherence rather than removing it.
- **A repair must be deterministic and idempotent.** Running the validator on its own
  output must produce no further change, and the suite asserts it.
- **A registry entry with no passing mutation test is documentation, not enforcement.**
- **Chromium API facts** that cost earlier sub-projects a build cycle each: the dictionary
  type is `base::DictValue`, not `base::Value::Dict`; `JSONReader::ReadDict` takes a
  **required** `int options`; `base::NoDestructor` static_asserts against a trivially
  destructible `T`.
- **`VLOG` expands through `LAZY_STREAM`** — an expression inside one is never evaluated at
  default verbosity. Never put a load-bearing call in one.
- **Never `git add -A`.** Stage explicit paths.
- Git identity in the Chromium checkout is `--local`, never `--global`.

## Design decisions this plan settles

The SP5 spec leaves two of these open and does not raise the third. Each is decided here
with its reasoning, so the implementation does not re-litigate them.

**Registry format: JSON, not an expression DSL.** The spec offers both and recommends JSON.
Adopted. A shared data file readable by the C++ validator, the generator and the test suite
is the entire point of having one registry, and JSON is the one format all three already
parse. A DSL would express relations more naturally at the cost of two evaluators that must
be kept identical — which is the same "one rule, several homes" failure the registry exists
to end.

**C++ compiles against a generated header; it does not read the JSON at runtime.** The spec
does not say where the registry lives at execution time. A browser should not depend on a
data file on disk at startup: it adds a path to resolve, a new failure mode when the file is
missing or stale, and I/O on the startup path. So `settings/invariants.json` is the source
of truth for the generator and the tests, and `additions/camoucfg/invariants.h` is the form
C++ sees — exactly the relationship `keys.h` already has with the key registry.

And exactly as with `keys.h`, **the generated header is hand-written for now.** Generation
buys one thing beyond what a hand-written header buys — a single source feeding both — and
it is worth building when there is a second consumer to feed. SP6a owns that, and must keep
these names identical so no call site moves.

**The tracer invariant repairs rather than rejects, and `ua:osInfo` wins.** When `ua:osInfo`
and `ua:platform` disagree about the OS family, a repair is possible and deterministic,
because the canonical OS-info strings are a closed set — they are the literals in
Chromium's own `GetUnifiedPlatform()`. Repairing exercises the more interesting policy and
makes verification item 2 (idempotence) testable from the first task.

`ua:osInfo` is authoritative because it lands in the **user-agent string**, the surface a
detector reads first. Repairing the less visible field to match the more visible one
minimises the change to what pages actually see. Stated here because "which one wins" is
not derivable from the spec and a later reader will ask.

## Environment

Two machines. Do not confuse them.

| | Path | Role |
|---|---|---|
| Mac | `/Users/lang/GolandProjects/github.com/lang315/camoucrome` | repo of record: `additions/`, `patches/`, `settings/`, `scripts/` |
| Build PC (WSL, ssh) | `~/chromium/src` and `~/camoucrome-verify` | where it compiles and runs |

```bash
cat > /tmp/myscript.sh <<'EOF'
cd ~/chromium/src
...
EOF
CM=~/.ssh/cm-buildpc
/usr/bin/ssh -o ControlMaster=auto -o ControlPath=$CM -o ControlPersist=8h -p 2222 \
  lang315@100.81.40.76 "wsl -d Ubuntu-24.04 -u lang -- bash -s" < /tmp/myscript.sh
```

`/usr/bin/ssh` — a shell wrapper shadows bare `ssh` on the Mac. Port **2222**, not 22.

**Never use `scp`.** The ssh server is Windows PowerShell, so `scp` lands on the *Windows*
filesystem while `wsl -- ...` reads its own. The copy prints `cannot stat`, the shell
continues, and the build compiles the **previous** file. Send contents by heredoc inside the
stdin script and compare `md5sum` remote against `md5 -q` local, every time.

**`/tmp` on the build machine does not survive between ssh invocations** — the VM is torn
down when the last client disconnects and `/tmp` is a tmpfs. Anything that must persist goes
under `~`.

**`set -o pipefail`** before any command whose exit code you read through a pipe;
`cmd | tail -5; echo $?` reports `tail`'s status. Avoid `bash -lc '...; echo EXIT=$?'` for
the same reason.

**`venv/bin/python`, never `python3`,** in `~/camoucrome-verify`, which has a flat layout —
scripts sit directly in it, not in a `scripts/` subdirectory.

`~/depot_tools/autoninja` explicitly; `autoninja` is not on `PATH` in a non-interactive ssh
session. Keep long work in the foreground. Never start a second build in the same output
directory; if a client-side command exits 255, check `pgrep -c "siso|ninja"` first.

**Read this plan against the tree before running each task.** Four defects in SP1a were
found that way — stale expected counts, drifted duplicate constants, an incomplete commit
list, an omitted file — and none would have announced itself in a green run.

## Test-count reference

Assert the count, not the exit code. Ten checks in this project have reported success while
measuring almost nothing, or failure while measuring the wrong thing; not one was caught by
something failing.

| Filter | Expected |
|---|---|
| `'Camoucfg*:MaskConfig*:ParseConfig*:AssembleRawConfig*:Getters*'` | 21 before this plan |
| `'UserAgentUtilsCamoucfgTest.*'` | 5, each needing **its own process** (config is latched per process) |
| `'UserAgentUtilsTest.*'` | 23 — upstream regression. Never `'UserAgentUtils*'`, which sweeps in the new suite |
| `venv/bin/python verify_sp0.py` | 11 PASS |
| `venv/bin/python verify_sp1a.py` | 9 PASS |

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `additions/camoucfg/derive.h` / `.cc` | Values computed from other values; the single claimed-OS function | 1 |
| `additions/camoucfg/derive_unittest.cc` | Its tests | 1 |
| `settings/invariants.json` | The registry: source of truth for the generator and tests | 2 |
| `additions/camoucfg/invariants.h` | The generated form C++ compiles against | 2 |
| `additions/camoucfg/coherence_validator.h` / `.cc` | Evaluates the registry, applies policies | 3 |
| `additions/camoucfg/coherence_validator_unittest.cc` | Mutation and idempotence harness | 4 |
| `additions/camoucfg/BUILD.gn` | New sources and tests | 1,2,3,4 |
| `content/browser/browser_main_loop.cc` | Validator invocation, replacing SP0's side effect | 5 |
| `scripts/verify_sp5a.py` | Browser-level check | 6 |
| `patches/sp5a-coherence-validator.patch` | Extracted diff | 7 |

---

### Task 1: `derive.{h,cc}` and the claimed-OS function

The one function that answers "what OS are we claiming". Conventions assigns it here
explicitly, and the reason is worth restating: **two derivations of the same fact are two
chances to disagree.** SP1 populates its inputs; SP4 and SP7 consume its answer; SP5a's own
tracer invariant is its first consumer, which is why it is not speculative.

**Files:**
- Create: `additions/camoucfg/derive.h`, `additions/camoucfg/derive.cc`, `additions/camoucfg/derive_unittest.cc`
- Modify: `additions/camoucfg/BUILD.gn`

**Interfaces:**
- Consumes: `camoucfg::keys::{kUaOsInfo,kUaPlatform}`, `camoucfg::GetString`, `ConfigScope`.
- Produces: `enum class OsFamily`, `OsFamilyFromUaChPlatform`, `OsFamilyFromOsInfo`,
  `CanonicalOsInfoFor`, `CanonicalUaChPlatformFor`, `ClaimedOs`. Tasks 2 and 3 use all six.

- [ ] **Step 1: Write the failing tests**

Create `additions/camoucfg/derive_unittest.cc`:

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/derive.h"

#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg {
namespace {

TEST(DeriveTest, RecognisesEachUaChPlatformString) {
  EXPECT_EQ(OsFamilyFromUaChPlatform("Windows"), OsFamily::kWindows);
  EXPECT_EQ(OsFamilyFromUaChPlatform("macOS"), OsFamily::kMac);
  EXPECT_EQ(OsFamilyFromUaChPlatform("Linux"), OsFamily::kLinux);
  EXPECT_EQ(OsFamilyFromUaChPlatform("Android"), OsFamily::kAndroid);
  EXPECT_EQ(OsFamilyFromUaChPlatform("Chrome OS"), OsFamily::kChromeOs);
}

// Anything not in the closed set is unknown, not a guess. A key holding a
// typo must not silently resolve to a plausible OS.
TEST(DeriveTest, UnrecognisedUaChPlatformIsUnknown) {
  EXPECT_EQ(OsFamilyFromUaChPlatform("windows"), OsFamily::kUnknown);
  EXPECT_EQ(OsFamilyFromUaChPlatform("Win32"), OsFamily::kUnknown);
  EXPECT_EQ(OsFamilyFromUaChPlatform(""), OsFamily::kUnknown);
}

// osInfo is the OS segment of a user-agent string, not a whole user agent.
// Matching a token in it is not user-agent parsing, and this is the only
// place in the project permitted to look at it at all.
TEST(DeriveTest, RecognisesOsInfoSegments) {
  EXPECT_EQ(OsFamilyFromOsInfo("Windows NT 10.0; Win64; x64"), OsFamily::kWindows);
  EXPECT_EQ(OsFamilyFromOsInfo("Macintosh; Intel Mac OS X 10_15_7"), OsFamily::kMac);
  EXPECT_EQ(OsFamilyFromOsInfo("X11; Linux x86_64"), OsFamily::kLinux);
  EXPECT_EQ(OsFamilyFromOsInfo("Linux; Android 10; K"), OsFamily::kAndroid);
  EXPECT_EQ(OsFamilyFromOsInfo("X11; CrOS x86_64 14541.0.0"), OsFamily::kChromeOs);
  EXPECT_EQ(OsFamilyFromOsInfo("nonsense"), OsFamily::kUnknown);
}

// Android and ChromeOS both contain "Linux"; order of matching decides the
// answer, so the ambiguity is asserted rather than left to reading order.
// Verified by mutation before the file was written: moving the Linux entry to
// the front of kForms fails the Android assertion and PASSES the ChromeOS one,
// because "Linux; Android 10; K" contains the token "Linux" and
// "X11; CrOS x86_64 14541.0.0" does not. So they are split, and each says what
// it actually guards -- the first the current ordering, the second a future
// change to the canonical string, since real ChromeOS user agents are
// sometimes spelled "X11; CrOS Linux x86_64".
//
// Merged, they read as two checks on the ordering. They are one.
TEST(DeriveTest, AndroidIsNotMistakenForLinux) {
  EXPECT_NE(OsFamilyFromOsInfo("Linux; Android 10; K"), OsFamily::kLinux);
}

TEST(DeriveTest, ChromeOsIsNotMistakenForLinux) {
  EXPECT_NE(OsFamilyFromOsInfo("X11; CrOS x86_64 14541.0.0"), OsFamily::kLinux);
}

// The canonical strings are the ones Chromium's own GetUnifiedPlatform()
// returns per platform, so a repaired value is byte-identical to what a real
// Chrome on that OS emits rather than something we invented.
TEST(DeriveTest, CanonicalFormsRoundTrip) {
  for (OsFamily os : {OsFamily::kWindows, OsFamily::kMac, OsFamily::kLinux,
                      OsFamily::kAndroid, OsFamily::kChromeOs}) {
    EXPECT_EQ(OsFamilyFromOsInfo(CanonicalOsInfoFor(os)), os);
    EXPECT_EQ(OsFamilyFromUaChPlatform(CanonicalUaChPlatformFor(os)), os);
  }
}

TEST(DeriveTest, CanonicalFormsOfUnknownAreEmpty) {
  EXPECT_TRUE(CanonicalOsInfoFor(OsFamily::kUnknown).empty());
  EXPECT_TRUE(CanonicalUaChPlatformFor(OsFamily::kUnknown).empty());
}

}  // namespace
}  // namespace camoucfg
```

`ClaimedOs()` reads configuration, and configuration is latched per process, so it is not
tested here — Task 3 covers it through the validator, where a config can be supplied
externally. Testing it in this file would need a fifth per-process invocation for one
function.

- [ ] **Step 2: Run it and watch it fail**

Add `derive_unittest.cc` to `source_set("unit_tests")` in `additions/camoucfg/BUILD.gn`,
alphabetically after `coherence_validator_unittest.cc`'s eventual slot and before
`keys_unittest.cc`:

```gn
source_set("unit_tests") {
  testonly = true
  sources = [
    "derive_unittest.cc",
    "keys_unittest.cc",
    "mask_config_unittest.cc",
  ]
  ...
}
```

Copy both the header-less test and the BUILD.gn into the checkout by heredoc, then:

```bash
set -o pipefail
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default components_unittests
```

Expected: FAIL — `fatal error: 'components/camoucfg/derive.h' file not found`.

- [ ] **Step 3: Write the header**

Create `additions/camoucfg/derive.h`:

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_DERIVE_H_
#define COMPONENTS_CAMOUCFG_DERIVE_H_

#include <string_view>

#include "components/camoucfg/mask_config.h"

// Values that are a function of other values.
//
// Conventions: a derived value gets no configuration key of its own, because
// an independent override creates the opportunity for incoherence rather than
// removing it. Everything declared here is computed, never configured.

namespace camoucfg {

enum class OsFamily {
  kUnknown,
  kWindows,
  kMac,
  kLinux,
  kAndroid,
  kChromeOs,
};

// The UA-CH platform token, as `navigator.userAgentData.platform` reports it
// and as Sec-CH-UA-Platform carries it. A closed set: anything else is
// kUnknown rather than a guess, because a key holding a typo must not
// silently resolve to a plausible operating system.
OsFamily OsFamilyFromUaChPlatform(std::string_view ua_ch_platform);

// The OS segment of a user-agent string -- what `ua:osInfo` holds, e.g.
// "Windows NT 10.0; Win64; x64". Not a whole user agent.
//
// This is the ONLY place in the project permitted to look at that text. SP1's
// spec forbids every sub-project from deriving the claimed OS locally, and
// conventions assigns the single derivation here, because two derivations of
// one fact are two chances to disagree.
OsFamily OsFamilyFromOsInfo(std::string_view os_info);

// The canonical spelling of each form, for repairs.
//
// These are Chromium's own literals from GetUnifiedPlatform() in
// components/embedder_support/user_agent_utils.cc, so a repaired value is
// byte-identical to what a real Chrome on that OS emits rather than something
// this project invented. kUnknown yields the empty string in both.
std::string_view CanonicalOsInfoFor(OsFamily os);
std::string_view CanonicalUaChPlatformFor(OsFamily os);

// The operating system this configuration is claiming.
//
// `ua:osInfo` is consulted first because it lands in the user-agent string,
// which is the surface a detector reads first; `ua:platform` is the fallback.
// With neither set, the answer is kUnknown -- meaning "not claiming anything",
// which is different from claiming the host's real OS, and callers that need
// the real one should ask the platform rather than this function.
OsFamily ClaimedOs(const ConfigScope& scope);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_DERIVE_H_
```

- [ ] **Step 4: Write the implementation**

Create `additions/camoucfg/derive.cc`:

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/derive.h"

#include <array>
#include <optional>
#include <string>
#include <utility>

#include "components/camoucfg/keys.h"

namespace camoucfg {
namespace {

struct OsForms {
  OsFamily family;
  std::string_view ua_ch_platform;  // navigator.userAgentData.platform
  std::string_view os_info;         // the UA string's OS segment
  std::string_view marker;          // the token that identifies os_info
};

// Order matters for `marker`: "Android 10" and "CrOS" both appear alongside
// text a naive Linux match would also accept, so the more specific markers are
// tested first. DeriveTest.AndroidAndChromeOsAreNotMistakenForLinux asserts it
// rather than leaving it to whoever next edits this array.
constexpr std::array<OsForms, 5> kForms = {{
    {OsFamily::kAndroid, "Android", "Linux; Android 10; K", "Android"},
    {OsFamily::kChromeOs, "Chrome OS", "X11; CrOS x86_64 14541.0.0", "CrOS"},
    {OsFamily::kWindows, "Windows", "Windows NT 10.0; Win64; x64", "Windows NT"},
    {OsFamily::kMac, "macOS", "Macintosh; Intel Mac OS X 10_15_7", "Macintosh"},
    {OsFamily::kLinux, "Linux", "X11; Linux x86_64", "Linux"},
}};

}  // namespace

OsFamily OsFamilyFromUaChPlatform(std::string_view ua_ch_platform) {
  for (const OsForms& form : kForms) {
    if (ua_ch_platform == form.ua_ch_platform) {
      return form.family;
    }
  }
  return OsFamily::kUnknown;
}

OsFamily OsFamilyFromOsInfo(std::string_view os_info) {
  for (const OsForms& form : kForms) {
    if (os_info.find(form.marker) != std::string_view::npos) {
      return form.family;
    }
  }
  return OsFamily::kUnknown;
}

std::string_view CanonicalOsInfoFor(OsFamily os) {
  for (const OsForms& form : kForms) {
    if (form.family == os) {
      return form.os_info;
    }
  }
  return {};
}

std::string_view CanonicalUaChPlatformFor(OsFamily os) {
  for (const OsForms& form : kForms) {
    if (form.family == os) {
      return form.ua_ch_platform;
    }
  }
  return {};
}

OsFamily ClaimedOs(const ConfigScope& scope) {
  if (std::optional<std::string> os_info = GetString(scope, keys::kUaOsInfo)) {
    OsFamily from_os_info = OsFamilyFromOsInfo(*os_info);
    if (from_os_info != OsFamily::kUnknown) {
      return from_os_info;
    }
  }
  if (std::optional<std::string> platform = GetString(scope, keys::kUaPlatform)) {
    return OsFamilyFromUaChPlatform(*platform);
  }
  return OsFamily::kUnknown;
}

}  // namespace camoucfg
```

- [ ] **Step 5: Add the sources and build**

Add `"derive.cc"` and `"derive.h"` to `static_library("camoucfg")`'s `sources`,
alphabetically after `"blink_scope.h"`:

```gn
static_library("camoucfg") {
  sources = [
    "blink_scope.h",
    "derive.cc",
    "derive.h",
    "keys.h",
    "mask_config.cc",
    "mask_config.h",
    "mask_config_internal.cc",
    "mask_config_internal.h",
  ]

  deps = [ "//base" ]
}
```

```bash
set -o pipefail
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default components_unittests
./out/Default/components_unittests --gtest_filter='DeriveTest.*'
```

Expected: **7 tests pass**. Assert the number.

*Corrected 2026-08-27 while writing the file.* The draft above showed six, with one test
named `AndroidAndChromeOsAreNotMistakenForLinux`. It is split in two, because mutation
testing showed the two halves are not equally load-bearing and merging them hid that.

- [ ] **Step 6: Confirm nothing regressed**

```bash
./out/Default/components_unittests \
  --gtest_filter='Camoucfg*:MaskConfig*:ParseConfig*:AssembleRawConfig*:Getters*:DeriveTest*'
```

Expected: **28** — the 21 that existed before plus these 7.

- [ ] **Step 7: Commit, both repositories**

```bash
# Chromium checkout
cd ~/chromium/src
git add components/camoucfg/derive.h components/camoucfg/derive.cc \
        components/camoucfg/derive_unittest.cc components/camoucfg/BUILD.gn
git commit -m "camoucfg: the single function that answers which OS we claim"

# Mac
cd /Users/lang/GolandProjects/github.com/lang315/camoucrome
git add additions/camoucfg/derive.h additions/camoucfg/derive.cc \
        additions/camoucfg/derive_unittest.cc additions/camoucfg/BUILD.gn
git commit -m "camoucfg: the single function that answers which OS we claim"
```

---

### Task 2: The registry file and its generated form

**Files:**
- Create: `settings/invariants.json`, `additions/camoucfg/invariants.h`
- Modify: `additions/camoucfg/BUILD.gn`

**Interfaces:**
- Consumes: nothing at compile time.
- Produces: `camoucfg::invariants::Policy`, `Invariant`, `kAllInvariants`. Tasks 3 and 4
  iterate that array.

- [ ] **Step 1: Write the registry**

Create `settings/invariants.json`. One entry — the tracer. SP5b adds the rest.

```json
{
  "$comment": [
    "The registry of cross-surface invariants. Source of truth for the",
    "fingerprint generator's self-check and for the generated mutation tests.",
    "C++ compiles against additions/camoucfg/invariants.h, which SP6a will",
    "generate from this file; until then the two are kept in step by hand and",
    "CoherenceValidatorTest.RegistryMatchesGeneratedHeader asserts it.",
    "",
    "Entries are added by the sub-project that owns the keys they constrain.",
    "An SP is not complete until its invariants are here with a passing",
    "mutation test -- an entry without one is documentation, not enforcement."
  ],
  "invariants": [
    {
      "id": "ua-os-family-agrees",
      "keys": ["ua:osInfo", "ua:platform"],
      "relation": "same-os-family",
      "policy": "repair",
      "repair": "set ua:platform to the canonical UA-CH platform for the OS family of ua:osInfo",
      "why": [
        "ua:osInfo lands in the user-agent string and ua:platform lands in",
        "navigator.userAgentData.platform and the Sec-CH-UA-Platform header.",
        "A page reads both. A Windows user agent beside a Linux platform is a",
        "stronger signal than either value alone would be honest.",
        "",
        "ua:osInfo wins because it is the more visible of the two, so",
        "repairing the other minimises the change to what pages see.",
        "",
        "SP1a ships this incoherence today and names SP5a as its owner --",
        "see the comment above ConfigPresentsUserAgentIdentity in",
        "patches/sp1a-ua-producer.patch."
      ]
    }
  ]
}
```

- [ ] **Step 2: Write the generated form**

Create `additions/camoucfg/invariants.h`:

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_INVARIANTS_H_
#define COMPONENTS_CAMOUCFG_INVARIANTS_H_

#include <array>
#include <string_view>

// The invariant registry, in the form C++ compiles against.
//
// settings/invariants.json is the source of truth; it is what the fingerprint
// generator self-checks against and what the mutation tests are built from.
// This header is its generated form.
//
// It is generated BY HAND for now, exactly as keys.h is. A browser should not
// read a data file from disk at startup -- that adds a path to resolve, a
// failure mode when the file is missing or stale, and I/O on the startup path
// -- so the registry reaches C++ compiled in. SP6a owns replacing this with
// real generation and must keep these names identical so no call site moves.
//
// Until then CoherenceValidatorTest.RegistryMatchesGeneratedHeader asserts the
// two agree, because a registry that has drifted from the code enforcing it is
// worse than no registry: it reads as coverage.

namespace camoucfg::invariants {

enum class Policy {
  // Refuse to launch. For violations no repair can make plausible.
  kReject,
  // Fix deterministically and log the key, the old value and the new one.
  // Must be idempotent: validating the repaired output changes nothing.
  kRepair,
};

// What relation the listed keys must hold.
enum class Relation {
  // Every listed key that is present must describe the same OS family, as
  // camoucfg::OsFamily computes it.
  kSameOsFamily,
};

struct Invariant {
  std::string_view id;
  Relation relation;
  Policy policy;
  std::array<std::string_view, 2> keys;
};

// Adding an entry here without adding it to settings/invariants.json, or
// without a mutation test, is what the two guard tests exist to catch.
inline constexpr std::array<Invariant, 1> kAllInvariants = {{
    {"ua-os-family-agrees",
     Relation::kSameOsFamily,
     Policy::kRepair,
     {"ua:osInfo", "ua:platform"}},
}};

}  // namespace camoucfg::invariants

#endif  // COMPONENTS_CAMOUCFG_INVARIANTS_H_
```

- [ ] **Step 3: Add to the build and confirm it compiles**

Add `"invariants.h"` to `static_library("camoucfg")`'s `sources`, alphabetically after
`"derive.h"`. Copy across and build `components_unittests`; nothing includes it yet, so this
only proves the header is well-formed.

```bash
set -o pipefail
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default components_unittests
```

Expected: `Build Succeeded`.

- [ ] **Step 4: Commit, both repositories**

```bash
cd ~/chromium/src
git add components/camoucfg/invariants.h components/camoucfg/BUILD.gn
git commit -m "camoucfg: the invariant registry and its generated form"

cd /Users/lang/GolandProjects/github.com/lang315/camoucrome
git add settings/invariants.json additions/camoucfg/invariants.h additions/camoucfg/BUILD.gn
git commit -m "camoucfg: the invariant registry and its generated form"
```

---

### Task 3: The validator

**Files:**
- Create: `additions/camoucfg/coherence_validator.h`, `.cc`
- Modify: `additions/camoucfg/BUILD.gn`

**Interfaces:**
- Consumes: `derive.h` (Task 1), `invariants.h` (Task 2), `mask_config.h`.
- Produces: `struct Violation`, `std::vector<Violation> Validate(const ConfigScope&)`,
  `bool ValidateAtStartup(const ConfigScope&)`. Task 5 calls the second.

- [ ] **Step 1: Write the failing tests**

Create `additions/camoucfg/coherence_validator_unittest.cc` with the two guard tests. The
mutation harness is Task 4; these two are what make the registry trustworthy at all.

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/coherence_validator.h"

#include <set>
#include <string>
#include <string_view>

#include "base/files/file_path.h"
#include "base/files/file_util.h"
#include "base/json/json_reader.h"
#include "base/path_service.h"
#include "components/camoucfg/invariants.h"
#include "components/camoucfg/keys.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg {
namespace {

using invariants::kAllInvariants;

// A registry that has drifted from the code enforcing it is worse than no
// registry, because it reads as coverage. Until SP6a generates the header,
// this is what keeps the two in step.
TEST(CoherenceValidatorTest, RegistryMatchesGeneratedHeader) {
  base::FilePath root;
  ASSERT_TRUE(base::PathService::Get(base::DIR_SRC_TEST_DATA_ROOT, &root));
  base::FilePath json = root.AppendASCII("components")
                            .AppendASCII("camoucfg")
                            .AppendASCII("invariants.json");
  std::string raw;
  ASSERT_TRUE(base::ReadFileToString(json, &raw)) << json;

  std::optional<base::DictValue> parsed =
      base::JSONReader::ReadDict(raw, base::JSON_PARSE_RFC);
  ASSERT_TRUE(parsed.has_value());
  const base::ListValue* entries = parsed->FindList("invariants");
  ASSERT_TRUE(entries);

  std::set<std::string> in_json;
  for (const base::Value& entry : *entries) {
    const std::string* id = entry.GetDict().FindString("id");
    ASSERT_TRUE(id);
    in_json.insert(*id);
  }
  std::set<std::string> in_header;
  for (const invariants::Invariant& inv : kAllInvariants) {
    in_header.insert(std::string(inv.id));
  }
  EXPECT_EQ(in_json, in_header);
}

// Found while writing the registry, not planned: an entry naming a key that
// does not exist in keys.h is SILENT. The validator asks for it, gets nullopt,
// treats the key as absent, and skips -- so the entry reads as protection and
// provides none. That is the registry's own version of the failure it exists
// to prevent, and it costs four lines to close.
TEST(CoherenceValidatorTest, EveryInvariantKeyIsDeclaredInTheRegistry) {
  std::set<std::string_view> declared(keys::kAllKeys.begin(),
                                      keys::kAllKeys.end());
  for (const invariants::Invariant& inv : kAllInvariants) {
    for (std::string_view key : inv.keys) {
      EXPECT_TRUE(declared.count(key))
          << "invariant '" << inv.id << "' names an undeclared key: " << key;
    }
  }
}

TEST(CoherenceValidatorTest, EveryInvariantIdIsUnique) {
  std::set<std::string_view> seen;
  for (const invariants::Invariant& inv : kAllInvariants) {
    EXPECT_TRUE(seen.insert(inv.id).second) << "duplicate id: " << inv.id;
  }
  EXPECT_EQ(seen.size(), kAllInvariants.size());
}

}  // namespace
}  // namespace camoucfg
```

The JSON must be reachable from the checkout, so `apply.sh` copies `settings/invariants.json`
to `components/camoucfg/invariants.json`. Add that in this task and say so in the report —
the file lives in `settings/` in the repository and beside the header in the tree, which is
the one place those two layouts differ.

- [ ] **Step 2: Watch it fail**

```bash
set -o pipefail
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default components_unittests
```

Expected: FAIL — `'components/camoucfg/coherence_validator.h' file not found`.

- [ ] **Step 3: Write the header**

Create `additions/camoucfg/coherence_validator.h`:

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_COHERENCE_VALIDATOR_H_
#define COMPONENTS_CAMOUCFG_COHERENCE_VALIDATOR_H_

#include <string>
#include <string_view>
#include <vector>

#include "components/camoucfg/mask_config.h"

namespace camoucfg {

struct Violation {
  std::string_view invariant_id;
  // What the validator would change, or did. Empty for a rejection.
  std::string repaired_key;
  std::string old_value;
  std::string new_value;
};

// Evaluates every registry entry against the configuration and reports what
// is wrong. Pure: it reports, it does not repair.
std::vector<Violation> Validate(const ConfigScope& scope);

// Called once from the browser process before any renderer exists.
//
// Returns false when startup must be refused. Under CAMOU_CONFIG_STRICT every
// violation refuses; otherwise a kRepair entry is repaired with a loud log and
// only a kReject entry refuses.
//
// This runs in the BROWSER process by design. Conventions forbid a renderer
// crashing on bad configuration -- a crash is itself a fingerprint -- and the
// browser process is the only point at which the fork can still decline to
// start. It is also the only place that can see the whole configuration at
// once, which a global invariant needs.
bool ValidateAtStartup(const ConfigScope& scope);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_COHERENCE_VALIDATOR_H_
```

- [ ] **Step 4: Write the implementation**

Create `additions/camoucfg/coherence_validator.cc`:

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/coherence_validator.h"

#include <optional>

#include "base/environment.h"
#include "base/logging.h"
#include "components/camoucfg/derive.h"
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
  // holds a user-agent OS segment; platform holds a UA-CH token. Guessing
  // from the string would make "Linux" ambiguous between them.
  return key == keys::kUaOsInfo ? OsFamilyFromOsInfo(*value)
                                : OsFamilyFromUaChPlatform(*value);
}

// A key that is absent, or present but unrecognised, constrains nothing. That
// is deliberate: this validator's job is catching values that CONTRADICT each
// other, and conventions rule 5 already covers an absent key by falling back
// to the real value. An unrecognised value is SP5b's problem to reject with a
// per-key type invariant, not this entry's to guess about.
std::vector<Violation> CheckSameOsFamily(const ConfigScope& scope,
                                         const invariants::Invariant& inv) {
  OsFamily first = OsFamilyOfKey(scope, inv.keys[0]);
  OsFamily second = OsFamilyOfKey(scope, inv.keys[1]);
  if (first == OsFamily::kUnknown || second == OsFamily::kUnknown ||
      first == second) {
    return {};
  }
  // keys[0] wins. For this entry that is ua:osInfo, which lands in the
  // user-agent string -- the surface a detector reads first -- so repairing
  // the other minimises the change to what pages actually see.
  Violation v;
  v.invariant_id = inv.id;
  v.repaired_key = std::string(inv.keys[1]);
  v.old_value = GetString(scope, inv.keys[1]).value_or(std::string());
  v.new_value = std::string(CanonicalUaChPlatformFor(first));
  return {v};
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
    }
  }
  return violations;
}

bool ValidateAtStartup(const ConfigScope& scope) {
  std::vector<Violation> violations = Validate(scope);
  if (violations.empty()) {
    return true;
  }

  std::unique_ptr<base::Environment> env = base::Environment::Create();
  const bool strict = env->GetVar("CAMOU_CONFIG_STRICT").has_value();

  for (const Violation& v : violations) {
    LOG(ERROR) << "camoucfg: invariant '" << v.invariant_id
               << "' violated. '" << v.repaired_key << "' was '" << v.old_value
               << "'"
               << (strict ? "; refusing to start (CAMOU_CONFIG_STRICT)"
                          : ", repaired to '" + v.new_value + "'");
  }
  // The repair itself lands in a later task: the configuration is currently a
  // read-only base::DictValue behind GlobalScope(), and giving it a mutating
  // path is a change to SP0's component that this task deliberately does not
  // make while proving the detection half. Until then a non-strict violation
  // is loud and unrepaired, which is the honest state and never silent.
  return !strict;
}

}  // namespace camoucfg
```

> **Read this before implementing Step 4.** The last comment describes a real gap: detection
> lands here, repair does not. That is deliberate sequencing, not an oversight — mutating the
> cached configuration means adding a write path to SP0's `mask_config.cc`, which is a change
> to a component three sub-projects already depend on. Prove detection first, then add the
> write path with its own tests. **If you find you cannot honestly log "repaired to X" while
> not repairing, change the log text rather than the plan** — the message must not claim an
> action that did not happen. That is exactly the class of overclaim this project has found
> ten times.

- [ ] **Step 5: Build and run**

```bash
set -o pipefail
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default components_unittests
./out/Default/components_unittests --gtest_filter='CoherenceValidatorTest.*'
```

Expected: **3 tests pass**.

- [ ] **Step 6: Commit, both repositories**

Stage explicit paths; include `scripts/apply.sh` on the Mac side for the JSON copy.

---

### Task 4: The mutation harness

Verification item 1: *a registry entry with no passing mutation test is documentation, not
enforcement.* This task makes that structural — the test iterates `kAllInvariants`, so an
entry added without a corresponding mutation is a failing test rather than a silent gap.

**Files:**
- Modify: `additions/camoucfg/coherence_validator_unittest.cc`

**Interfaces:**
- Consumes: `Validate` (Task 3), `kAllInvariants` (Task 2).
- Produces: nothing further tasks call.

- [ ] **Step 1: Write the harness**

The configuration is latched per process, so each mutation needs its own invocation, exactly
as SP1a's UA tests do. The harness therefore reads which invariant to exercise from the
environment and the runner supplies one per process.

```cpp
// Each case runs in its own process: camoucfg::Config() reads the environment
// once and caches it (mask_config.cc:18), so several differently-configured
// cases in one binary would all see whichever config latched first. The runner
// below supplies CAMOU_CONFIG and CAMOUCFG_TEST_INVARIANT per invocation.
//
// The loop over kAllInvariants is what makes this structural rather than
// diligent: an entry added to the registry with no mutation defined here fails
// MutationsExistForEveryInvariant, so "documentation, not enforcement" cannot
// happen quietly.

struct Mutation {
  std::string_view invariant_id;
  std::string_view config;          // violates exactly this invariant
  std::string_view expect_repaired; // the key the validator should name
};

constexpr std::array<Mutation, 1> kMutations = {{
    {"ua-os-family-agrees",
     R"({"ua:osInfo":"Windows NT 10.0; Win64; x64","ua:platform":"Linux"})",
     "ua:platform"},
}};

TEST(CoherenceValidatorTest, MutationsExistForEveryInvariant) {
  for (const invariants::Invariant& inv : invariants::kAllInvariants) {
    bool found = false;
    for (const Mutation& m : kMutations) {
      found = found || m.invariant_id == inv.id;
    }
    EXPECT_TRUE(found) << "no mutation defined for invariant: " << inv.id;
  }
}

// Run once per mutation, with CAMOU_CONFIG set to that mutation's config.
// Asserts the validator reports THAT entry and no other -- an entry that fires
// on an unrelated corruption is as useless as one that never fires.
TEST(CoherenceValidatorTest, MutationIsCaughtAndNothingElseIs) {
  std::unique_ptr<base::Environment> env = base::Environment::Create();
  std::optional<std::string> which = env->GetVar("CAMOUCFG_TEST_INVARIANT");
  ASSERT_TRUE(which.has_value())
      << "set CAMOUCFG_TEST_INVARIANT and CAMOU_CONFIG; see the runner in the "
         "task report";

  const Mutation* mutation = nullptr;
  for (const Mutation& m : kMutations) {
    if (m.invariant_id == *which) {
      mutation = &m;
    }
  }
  ASSERT_TRUE(mutation) << "no mutation named " << *which;

  std::vector<Violation> violations = Validate(GlobalScope());
  ASSERT_EQ(violations.size(), 1u);
  EXPECT_EQ(violations[0].invariant_id, mutation->invariant_id);
  EXPECT_EQ(violations[0].repaired_key, mutation->expect_repaired);
}

// A configuration that satisfies every invariant must produce nothing. Without
// this, a validator that reported a violation unconditionally would pass every
// test above.
TEST(CoherenceValidatorTest, CleanConfigProducesNoViolations) {
  EXPECT_TRUE(Validate(GlobalScope()).empty());
}
```

- [ ] **Step 2: Run each case in its own process**

```bash
set -o pipefail
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default components_unittests
T=./out/Default/components_unittests

env -u CAMOU_CONFIG $T --gtest_filter='CoherenceValidatorTest.RegistryMatchesGeneratedHeader'
echo "registry exit=$?"
env -u CAMOU_CONFIG $T --gtest_filter='CoherenceValidatorTest.EveryInvariantIdIsUnique'
echo "unique exit=$?"
env -u CAMOU_CONFIG $T --gtest_filter='CoherenceValidatorTest.MutationsExistForEveryInvariant'
echo "coverage exit=$?"

CAMOU_CONFIG='{"ua:osInfo":"Windows NT 10.0; Win64; x64","ua:platform":"Windows"}' \
  $T --gtest_filter='CoherenceValidatorTest.CleanConfigProducesNoViolations'
echo "clean exit=$?"

CAMOUCFG_TEST_INVARIANT=ua-os-family-agrees \
CAMOU_CONFIG='{"ua:osInfo":"Windows NT 10.0; Win64; x64","ua:platform":"Linux"}' \
  $T --gtest_filter='CoherenceValidatorTest.MutationIsCaughtAndNothingElseIs'
echo "mutation exit=$?"
```

Expected: all five exit 0. Paste all five exit codes into the report; one summary line
cannot show that each ran under its own configuration.

- [ ] **Step 3: Prove the mutation test can fail**

A check that has never failed is a check nobody has confirmed is wired up, and this project
has found a mutation test that reported a pass because its mutant did not compile.

Temporarily change `CheckSameOsFamily` to `return {};` unconditionally, rebuild, and re-run
the mutation case.

**Confirm the build printed `Build Succeeded` before believing the result.** A mutant that
fails to compile leaves the previous binary in place, the test runs against it, and it
prints a pass. If the edit causes an unused-parameter or unused-function error, adjust the
mutation so it still compiles rather than accepting an inconclusive run.

Expected: `MutationIsCaughtAndNothingElseIs` FAILS on `ASSERT_EQ(violations.size(), 1u)`.
Then restore, rebuild, and confirm all five pass again. Record both transcripts.

- [ ] **Step 4: Commit, both repositories**

---

### Task 5: Run the validator at startup, and retire SP0's side effect

Conventions records this as an open weakness left by SP0:

> Making strict mode depend on the side effect of a line whose stated purpose is logging is
> fragile. A future sub-project should give startup validation its own explicit call rather
> than leaving it as an operand.

**This is that sub-project.** `ValidateAtStartup()` is the explicit call, and it
forces the parse as a byproduct of doing real work, so the fragile arrangement can go.

**Files:**
- Modify: `content/browser/browser_main_loop.cc`, `content/browser/DEPS` (verify only)

**Interfaces:**
- Consumes: `ValidateAtStartup` (Task 3).
- Produces: nothing.

- [x] **Step 1: Read what is there now**

```bash
grep -n "camoucfg" ~/chromium/src/content/browser/browser_main_loop.cc
grep -n "camoucfg" ~/chromium/src/content/browser/DEPS
```

SP0's forced parse and SP1a's unsupported-key warning are both in
`BrowserMainLoop::EarlyInitialization`. `content/browser/DEPS` grants
`"+components/camoucfg",` directory-wide, so the new include needs no DEPS change — confirm
rather than assume, and say so in the report.

- [x] **Step 2: Replace the side effect with the call**

> **Two deviations, both recorded rather than quietly absorbed.**
>
> **`return 1` became a named 13.** `EarlyInitialization()` does return `int`, so the plan's
> `return 1` compiles — but 1 is `RESULT_CODE_KILLED`, and reporting a deliberate, explained
> refusal as a kill misfiles it in crash reporting. There is no content-level code for "bad
> configuration" and there cannot be one: `content::ResultCode` is frozen behind a
> `static_assert` pinning `RESULT_CODE_LAST_CODE` at 5, and `result_codes.h` forbids new
> values. 13 is what `chrome::ResultCode` calls `RESULT_CODE_UNSUPPORTED_PARAM`, and
> `CrashExitCodeToString(13)` already prints that name, so the number is accurate even
> though the symbol is unreachable from `//content`. Written as a named local constant with
> that reasoning beside it.
>
> **Three review findings landed here.** SP1a's whole-branch review left 1.1, 1.2 and 1.3
> open, and 1.2 and 1.3 are startup diagnostics — the same insertion point, the same build.
> Doing them elsewhere would have meant a second cycle for four lines each.
> **1.1 is NOT done**: it changes `ConfigPresentsUserAgentIdentity` in
> `user_agent_utils.cc`, a different file and SP1a's concern, and belongs in its own commit
> rather than smuggled into this task.
>
> `keys::kUaMetadataKeys` and `camoucfg::UnrecognisedKeys()` are new, both needed by the
> diagnostics. The first has two guard tests, because a hand-written subset that drifts from
> `kAllKeys` would silently stop covering whatever fell out while every existing assertion
> still passed.

Add `#include "components/camoucfg/coherence_validator.h"` beside the existing camoucfg
includes. Then replace SP0's `camou_configured` statement and its `VLOG` with:

```cpp
  // Validate the configuration here, in the browser process, before any
  // renderer exists.
  //
  // This call replaces the arrangement SP0 left behind, where the parse was
  // forced by the side effect of a HasKey() in a logging line and conventions
  // recorded the fragility as an open weakness. Validation is real work that
  // has to happen here, and forcing the parse is now its byproduct rather than
  // its purpose.
  //
  // Two things still depend on it happening here rather than lazily at first
  // surface access. The first surface to touch configuration is in a RENDERER,
  // and CAMOU_CONFIG_STRICT is specified to refuse startup -- so a lazy parse
  // would fire its CHECK in a renderer, turning "refuse to start" into a
  // renderer crash, which conventions forbids because a crash is itself a
  // fingerprint. And a global invariant needs to see the whole configuration
  // at once, which only the browser process can.
  if (!camoucfg::ValidateAtStartup(camoucfg::GlobalScope())) {
    LOG(ERROR) << "camoucfg: configuration is incoherent and "
                  "CAMOU_CONFIG_STRICT is set; refusing to start.";
    return 1;
  }
```

Keep SP1a's `navigator.userAgent` warning exactly where it is.

Check `EarlyInitialization`'s signature before writing `return 1` — if it does not return
`int`, use whatever the surrounding code uses to abort startup, and say which in the report.

- [x] **Step 3: Build and verify both paths**

```bash
set -o pipefail
cd ~/chromium/src && ~/depot_tools/autoninja -C out/Default content_shell
cd ~/camoucrome-verify
venv/bin/python verify_sp0.py;  echo "sp0 exit=$?"    # expect 11 PASS
venv/bin/python verify_sp1a.py; echo "sp1a exit=$?"   # expect 9 PASS
```

Both must still pass. SP0's criterion 6 covers malformed configuration under strict mode and
is the one most likely to notice if this refactor broke the fail-closed path.

- [x] **Step 4: Commit**

---

### Task 6: Browser-level verification

**Files:**
- Create: `scripts/verify_sp5a.py`

- [ ] **Step 1: Write the assertions**

Follow `verify_sp1a.py`'s shape exactly — `lib_shell.session()`, every fault becoming FAIL
lines rather than a traceback, the baseline load guarded. Four assertions:

1. **A coherent configuration is untouched.** `ua:osInfo` Windows with `ua:platform`
   `"Windows"` produces a Windows UA string, and stderr carries no `invariant` line.
2. **An incoherent configuration is detected and says so.** `ua:osInfo` Windows with
   `ua:platform` `"Linux"` logs `ua-os-family-agrees` naming `ua:platform`, and the browser
   still starts.
3. **Strict mode refuses to start.** The same incoherent configuration with
   `CAMOU_CONFIG_STRICT=1` must fail to open a DevTools endpoint. `lib_shell.launch()`
   already distinguishes "exited during startup" from "never opened a port", and this
   assertion wants the first — assert on the exit rather than on the timeout, so a hang
   cannot pass as a refusal.
4. **No config is still silent.** With no `CAMOU_CONFIG`, stderr carries no `camoucfg:`
   line at all and the UA is byte-identical to the SP1a baseline.

Assertion 3 is the one worth writing carefully. A refusal and a hang look identical to a
naive check, and a hang would mean the browser is unusable rather than fail-closed.

- [ ] **Step 2: Run**

```bash
cd ~/camoucrome-verify && venv/bin/python verify_sp5a.py; echo "exit=$?"
```

Expected: **4 PASS, exit=0.** Assert the count.

- [ ] **Step 3: Commit**

---

### Task 7: Extract and prove it reconstructs

Same discipline as SP1a Task 7, and for the same reason: `~/chromium/src` is regenerable.

- [ ] **Step 1: Derive the file list rather than trusting one written here**

```bash
set -o pipefail
cd ~/chromium/src
BASE=<SP1a's head, recorded in the ledger>

echo "=== everything SP5a changed ==="
git diff --stat $BASE..HEAD
echo "=== additions/ owns, and must NOT be in the patch ==="
git diff --name-only $BASE..HEAD -- components/camoucfg/
echo "=== the patch owns ==="
git diff --name-only $BASE..HEAD -- . ':!components/camoucfg/'
```

Expected: `components/camoucfg/{derive.h,derive.cc,derive_unittest.cc,invariants.h,invariants.json,coherence_validator.h,coherence_validator.cc,coherence_validator_unittest.cc,BUILD.gn}` owned by `additions/`, and `content/browser/browser_main_loop.cc` alone in the patch.

Reconcile against what the commands actually print. A patch missing a file is **invisible
downstream**: the reconstruction applies, builds and passes the browser checks, because
those run no unit tests.

```bash
git diff $BASE..HEAD -- . ':!components/camoucfg/' > /tmp/sp5a-coherence-validator.patch
grep -c '^diff --git' /tmp/sp5a-coherence-validator.patch   # assert the count
git apply --check --reverse /tmp/sp5a-coherence-validator.patch; echo "reverse exit=$?"
```

- [ ] **Step 2: Reconstruct from the pinned base and verify by count**

Fresh branch at `0e8d4a9268118d323f62ca207b40514df39dcaa9`, `scripts/apply.sh` alone, then
every suite **run**, not listed:

| Check | Expected |
|---|---|
| `verify_sp0.py` | 11 PASS |
| `verify_sp1a.py` | 9 PASS |
| `verify_sp5a.py` | 4 PASS |
| `'Camoucfg*:MaskConfig*:ParseConfig*:AssembleRawConfig*:Getters*:DeriveTest*:CoherenceValidatorTest*'` | count it and record it |
| `'UserAgentUtilsCamoucfgTest.*'` | 5, each in its own process |
| `'UserAgentUtilsTest.*'` | 23 |

Then return the checkout to the working branch and rebuild.

- [ ] **Step 3: Update the README and commit**

State what is verified, not what is patched — the SP1a status table is the shape to follow.

---

## Deferred out of SP5a, stated so a green run is not misread

| Item | Why |
|---|---|
| The invariant catalogue | **SP5b.** An invariant over a key nothing reads is untestable, so entries arrive with SP1b, SP3 and SP4. |
| Applying repairs | Detection lands in SP5a; mutating the cached configuration needs a write path in SP0's `mask_config.cc`, which three sub-projects depend on. Own task, own tests. |
| Generating `invariants.h` from the JSON | **SP6a**, with `keys.h`. Until then `RegistryMatchesGeneratedHeader` keeps them in step. |
| Verification items 3–8 | Generated-config sweeps, presets, cross-process identity, A/A determinism, DST, detector canaries — each needs a sub-project SP5a does not have yet. |
| Per-context validation | Open decision in SP5's spec; belongs with whichever sub-project introduces the per-context store. |

## Self-review

**Spec coverage.** SP5a's five artifacts in the spec's §3 table each have a task: `derive.{h,cc}`
(1), `settings/invariants.json` (2), the reader and validator (3), the test harness (4), the
startup invocation (5). Verification items 1 and 2 are Task 4; the rest are tabled above.

**Placeholders.** None. Every code step carries its code; every command its expected count.

**Type consistency.** `OsFamily`, `OsFamilyFromUaChPlatform`, `OsFamilyFromOsInfo`,
`CanonicalOsInfoFor`, `CanonicalUaChPlatformFor`, `ClaimedOs` are defined in Task 1 and used
with those signatures in Tasks 3 and 4. `Violation`, `Validate`, `ValidateAtStartup`
are defined in Task 3 and used in Tasks 4 and 5. `invariants::{Policy,Relation,Invariant,kAllInvariants}`
are defined in Task 2 and used in Tasks 3 and 4.

**Known weakness, stated rather than hidden.** Task 3 ships detection without repair, and its
log text must not claim a repair it did not perform. The step says so explicitly because a
message overclaiming its own action is precisely the failure this project has now found ten
times.
