# SP0 Config Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `//components/camoucfg`, a configuration layer readable from every Chromium process, and prove it end to end by driving `navigator.hardwareConcurrency` through it without any page-observable trace.

**Architecture:** A new GN component parses a JSON object out of chunked environment variables exactly once per process and serves typed lookups. Every lookup takes a `ConfigScope` first argument that today always resolves to one process-global configuration; the parameter exists so a later per-context store changes one function instead of every call site. Blink reaches the component through one added line in its DEPS allowlist. The tracer surface overrides `NavigatorConcurrentHardware::hardwareConcurrency()` in `NavigatorBase`, which is where an `ExecutionContext` is actually available and which both `Navigator` and `WorkerNavigator` inherit.

**Tech Stack:** C++20, Chromium `//base` (`base::Environment`, `base::JSONReader`, `base::DictValue`, `base::NoDestructor`, `base::FunctionRef`), GN/Siso build, gtest, Blink, the Chrome DevTools Protocol for runtime verification.

## Global Constraints

- Spoofing is implemented in C++ only. No JavaScript is injected into any page-visible scope, ever.
- After any change, `Object.getOwnPropertyDescriptor(...).get.toString()` must still contain `[native code]`, and `Object.keys(window)` must be byte-identical to a stock build of the same revision.
- Every getter takes a `ConfigScope` as its first argument. Never add a getter that omits it.
- Absent configuration falls back to the real value. Never fall back to a hardcoded placeholder.
- Malformed configuration must never crash a renderer. A crash is itself a fingerprint.
- No third-party JSON library is vendored. Chromium ships `base::JSONReader`.
- Environment transport is `CAMOU_CONFIG_1`, `CAMOU_CONFIG_2`, … concatenated in index order, falling back to a single `CAMOU_CONFIG`. This is byte-compatible with Camoufox on purpose.
- All code is written in the Chromium checkout at `~/chromium/src` on the build machine, as WSL user `lang`. depot_tools refuses to run as root.
- **The base revision is `0e8d4a9268118d323f62ca207b40514df39dcaa9`.** Verified as the checkout's `HEAD` before any task ran. Every patch extracted in Task 7 is generated against this revision, and it is what the Camoucrome README records.
- **A gclient checkout is in detached HEAD, so Task 1 must create a branch before its first commit.** Commits made in detached HEAD belong to no branch, and the next `gclient sync` or checkout discards them with no entry in `git log` to recover from. Every task in this plan commits, so this is not optional — it is the difference between the work existing and not.
- Build directory is `out/Default`. Never run `gn gen` with different args; the existing `args.gn` is `is_debug=false`, `is_component_build=true`, `symbol_level=0`, `blink_symbol_level=0`, `dcheck_always_on=false`, `use_remoteexec=false`.
- Every command in this plan runs inside WSL. From the controlling machine, pipe a script to `wsl -d Ubuntu-24.04 -u lang -- bash -s` over an ssh connection with `ControlMaster` and `ControlPersist` enabled. A long build must run in the foreground of that session; detaching with `nohup` or `setsid` gets the process killed.
- **Prefix every `tar` on the macOS side with `COPYFILE_DISABLE=1`.** macOS `tar` embeds AppleDouble sidecar files (`._name`) for any file carrying extended attributes, and they arrive in the Chromium checkout as untracked junk. Task 1 shipped six of them. They do not break the build, but `additions/` would copy them into the repository and every later `git status` reads dirty. Clean any that already exist with `find . -name '._*' -delete` inside the affected directory.
- A `git commit` in the Chromium checkout must never fail with `Author identity unknown`. Configure the identity repo-locally in Task 1 Step 0, before any commit.

## File Structure

| File | Responsibility |
|---|---|
| `components/camoucfg/BUILD.gn` | Declares the `camoucfg` static library and the `unit_tests` source set. |
| `components/camoucfg/mask_config.h` | Public API: `ConfigScope`, `GlobalScope()`, the typed getters. |
| `components/camoucfg/mask_config.cc` | Environment assembly, JSON parsing, the process-wide singleton, the getters. |
| `components/camoucfg/mask_config_internal.h` | Pure functions `AssembleRawConfig` and `ParseConfig`, split out so they are unit-testable without process-global state. |
| `components/camoucfg/blink_scope.h` | `ScopeFor(blink::ExecutionContext*)`. The only header Blink call sites include besides `mask_config.h`. |
| `components/camoucfg/mask_config_unittest.cc` | Tests for assembly, parsing, failure modes, and every getter. |
| `components/BUILD.gn` | Modified: registers `//components/camoucfg:unit_tests` in `components_unittests`. |
| `third_party/blink/renderer/DEPS` | Modified: two added `include_rules` entries. |
| `third_party/blink/renderer/core/execution_context/navigator_base.h` | Modified: declares the `hardwareConcurrency` override. |
| `third_party/blink/renderer/core/execution_context/navigator_base.cc` | Modified: the override body — the tracer bullet. |
| `content/browser/browser_main_loop.cc` | Modified: one browser-process smoke log. |

Splitting the pure functions into `mask_config_internal.h` is what makes Tasks 1 and 2 testable at all. Environment reading and one-time initialisation are process-global by nature; keeping the logic separate from the singleton means the tests never fight a `base::NoDestructor` that can only be initialised once.

---

### Task 1: Component skeleton and environment assembly

**Files:**
- Create: `components/camoucfg/BUILD.gn`
- Create: `components/camoucfg/mask_config_internal.h`
- Create: `components/camoucfg/mask_config_internal.cc`
- Create: `components/camoucfg/mask_config_unittest.cc`
- Modify: `components/BUILD.gn` (one added line in the `components_unittests` deps list)
- Test: `components/camoucfg/mask_config_unittest.cc`

**Interfaces:**
- Consumes: nothing.
- Produces: `camoucfg::internal::AssembleRawConfig(base::FunctionRef<std::optional<std::string>(const std::string&)> get) -> std::string`.

- [ ] **Step 0: Create the working branch**

The checkout is in detached HEAD. Commit there and the work belongs to no branch, and
the next `gclient sync` discards it with nothing left in `git log` to recover from.

Run:

```bash
cd ~/chromium/src
git rev-parse HEAD
git checkout -b camoucrome/sp0
git rev-parse --abbrev-ref HEAD
```

Expected: the first command prints `0e8d4a9268118d323f62ca207b40514df39dcaa9`, and
the last prints `camoucrome/sp0`. If the first prints a different hash, the checkout
moved since the plan was written — stop and report it rather than continuing, because
every patch in Task 7 is generated against that revision.

Then configure a git identity. A fresh gclient checkout has none, and `git commit`
fails with `Author identity unknown`:

```bash
git config --local user.name "Lãng"
git config --local user.email "30039912+lang315@users.noreply.github.com"
git config --local --get user.name
git config --local --get user.email
```

`--local` is deliberate. The same WSL distro is where Camoufox is built, and a global
identity would reach into unrelated work. Confirm both `--get` commands echo the name
back unmangled before committing — it contains non-ASCII characters, and a bad
encoding here is baked into every commit that follows.

This identity does not reach the deliverable. Task 7 extracts with
`git diff BASE HEAD -- <paths>`, which emits content only and carries no author,
committer, or date headers; author identity would travel only if Task 7 used
`git format-patch`, which it does not.

- [ ] **Step 1: Create the BUILD.gn**

Create `components/camoucfg/BUILD.gn`:

```gn
# Copyright 2026 The Camoucrome Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

static_library("camoucfg") {
  sources = [
    "mask_config_internal.cc",
    "mask_config_internal.h",
  ]

  deps = [ "//base" ]
}

source_set("unit_tests") {
  testonly = true
  sources = [ "mask_config_unittest.cc" ]

  deps = [
    ":camoucfg",
    "//base",
    "//testing/gtest",
  ]
}
```

- [ ] **Step 2: Register the test target**

In `components/BUILD.gn`, find the line reading `"//components/captive_portal/core:unit_tests",` inside the `components_unittests` deps list and insert immediately **above** it:

```gn
    "//components/camoucfg:unit_tests",
```

The list is alphabetical and `camoucfg` sorts before `captive_portal`.

- [ ] **Step 3: Write the failing test**

Create `components/camoucfg/mask_config_unittest.cc`:

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/mask_config_internal.h"

#include <map>
#include <optional>
#include <string>

#include "testing/gtest/include/gtest/gtest.h"

namespace camoucfg::internal {
namespace {

// Builds an environment lookup over a fixed map, so tests never touch the
// real process environment.
auto EnvFrom(const std::map<std::string, std::string>& vars) {
  return [&vars](const std::string& name) -> std::optional<std::string> {
    auto it = vars.find(name);
    if (it == vars.end()) {
      return std::nullopt;
    }
    return it->second;
  };
}

TEST(AssembleRawConfigTest, ReturnsEmptyWhenNothingSet) {
  std::map<std::string, std::string> vars;
  auto env = EnvFrom(vars);
  EXPECT_EQ(AssembleRawConfig(env), "");
}

TEST(AssembleRawConfigTest, ReadsUnnumberedFallback) {
  std::map<std::string, std::string> vars{{"CAMOU_CONFIG", "{\"a\":1}"}};
  auto env = EnvFrom(vars);
  EXPECT_EQ(AssembleRawConfig(env), "{\"a\":1}");
}

TEST(AssembleRawConfigTest, ConcatenatesChunksInIndexOrder) {
  std::map<std::string, std::string> vars{
      {"CAMOU_CONFIG_1", "{\"a\":"},
      {"CAMOU_CONFIG_2", "1,\"b\":"},
      {"CAMOU_CONFIG_3", "2}"},
  };
  auto env = EnvFrom(vars);
  EXPECT_EQ(AssembleRawConfig(env), "{\"a\":1,\"b\":2}");
}

TEST(AssembleRawConfigTest, StopsAtFirstMissingIndex) {
  std::map<std::string, std::string> vars{
      {"CAMOU_CONFIG_1", "one"},
      {"CAMOU_CONFIG_3", "three"},
  };
  auto env = EnvFrom(vars);
  EXPECT_EQ(AssembleRawConfig(env), "one");
}

TEST(AssembleRawConfigTest, NumberedChunksWinOverUnnumbered) {
  std::map<std::string, std::string> vars{
      {"CAMOU_CONFIG", "ignored"},
      {"CAMOU_CONFIG_1", "used"},
  };
  auto env = EnvFrom(vars);
  EXPECT_EQ(AssembleRawConfig(env), "used");
}

// The one case that tells the two candidate semantics apart. The fallback
// fires on the concatenation being empty, not on CAMOU_CONFIG_1 being
// absent, so a present-but-empty chunk still falls through to the
// unnumbered variable. Camoufox's MaskConfig.hpp behaves identically, and
// the byte-compatibility constraint makes that binding: a future change to
// presence-tracking would return "" here and silently diverge from the
// reference on identical environment bytes.
TEST(AssembleRawConfigTest, PresentButEmptyChunkFallsBackToUnnumbered) {
  std::map<std::string, std::string> vars{
      {"CAMOU_CONFIG_1", ""},
      {"CAMOU_CONFIG", "ignored"},
  };
  auto env = EnvFrom(vars);
  EXPECT_EQ(AssembleRawConfig(env), "ignored");
}

}  // namespace
}  // namespace camoucfg::internal
```

- [ ] **Step 4: Write the header**

Create `components/camoucfg/mask_config_internal.h`:

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_MASK_CONFIG_INTERNAL_H_
#define COMPONENTS_CAMOUCFG_MASK_CONFIG_INTERNAL_H_

#include <optional>
#include <string>

#include "base/functional/function_ref.h"

namespace camoucfg::internal {

// Signature of an environment lookup. Injected so tests never mutate the
// real process environment.
using EnvGetter =
    base::FunctionRef<std::optional<std::string>(const std::string&)>;

// Concatenates CAMOU_CONFIG_1, CAMOU_CONFIG_2, ... in index order, stopping
// at the first index that is absent. Falls back to the unnumbered
// CAMOU_CONFIG when that concatenation comes out **empty** — which covers
// both "no numbered variable was set at all" and "every numbered variable
// that was set held an empty string". Returns an empty string when neither
// form yields anything, the normal case for a stock run.
//
// The trigger is emptiness of the result, not absence of CAMOU_CONFIG_1.
// Those differ when a numbered variable is present but empty, and the
// difference is deliberate: Camoufox's MaskConfig.hpp checks
// `if (jsonString.empty())` after the same loop, and this transport has to
// stay byte-compatible with it. PresentButEmptyChunkFallsBackToUnnumbered
// is the test that pins the distinction.
//
// The chunking exists because Windows caps a single environment variable
// near 32KB and a full fingerprint exceeds that.
std::string AssembleRawConfig(EnvGetter get);

}  // namespace camoucfg::internal

#endif  // COMPONENTS_CAMOUCFG_MASK_CONFIG_INTERNAL_H_
```

- [ ] **Step 5: Run the test to verify it fails**

Run:

```bash
autoninja -C out/Default components_unittests && \
  ./out/Default/components_unittests --gtest_filter='AssembleRawConfigTest.*'
```

Expected: the build fails with

```
"../../components/camoucfg/mask_config_internal.cc", needed by
"obj/components/camoucfg/camoucfg/mask_config_internal.o",
missing and no known rule to make it
```

because `BUILD.gn` already lists a source file that has not been written. Siso stops at
source resolution and never reaches the link stage, so this is a build-graph error
rather than the `undefined reference` a linker would report. The cause is the same —
`AssembleRawConfig` is declared and not implemented — and this is the correct failure
to observe before Step 6.

- [ ] **Step 6: Write the minimal implementation**

Create `components/camoucfg/mask_config_internal.cc`:

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/mask_config_internal.h"

#include "base/strings/strcat.h"
#include "base/strings/string_number_conversions.h"

namespace camoucfg::internal {

std::string AssembleRawConfig(EnvGetter get) {
  std::string assembled;
  for (int index = 1;; ++index) {
    std::optional<std::string> chunk =
        get(base::StrCat({"CAMOU_CONFIG_", base::NumberToString(index)}));
    if (!chunk.has_value()) {
      break;
    }
    assembled += *chunk;
  }

  if (!assembled.empty()) {
    return assembled;
  }

  std::optional<std::string> single = get("CAMOU_CONFIG");
  return single.value_or(std::string());
}

}  // namespace camoucfg::internal
```

- [ ] **Step 7: Run the test to verify it passes**

Run:

```bash
autoninja -C out/Default components_unittests && \
  ./out/Default/components_unittests --gtest_filter='AssembleRawConfigTest.*'
```

Expected: `[  PASSED  ] 6 tests.`

- [ ] **Step 8: Commit**

```bash
cd ~/chromium/src
git add components/camoucfg/BUILD.gn \
        components/camoucfg/mask_config_internal.h \
        components/camoucfg/mask_config_internal.cc \
        components/camoucfg/mask_config_unittest.cc \
        components/BUILD.gn
git commit -m "camoucfg: assemble config from chunked environment variables"
```

---

### Task 2: JSON parsing and failure modes

**Files:**
- Modify: `components/camoucfg/mask_config_internal.h`
- Modify: `components/camoucfg/mask_config_internal.cc`
- Modify: `components/camoucfg/mask_config_unittest.cc`
- Modify: `components/camoucfg/BUILD.gn`

**Interfaces:**
- Consumes: `AssembleRawConfig` from Task 1.
- Produces: `camoucfg::internal::ParseConfig(std::string_view raw, bool strict) -> base::DictValue`.

- [ ] **Step 1: Write the failing tests**

Append inside the anonymous namespace of `components/camoucfg/mask_config_unittest.cc`, before its closing `}  // namespace`:

```cpp
TEST(ParseConfigTest, EmptyInputYieldsEmptyDict) {
  base::DictValue dict = ParseConfig("", /*strict=*/false);
  EXPECT_TRUE(dict.empty());
}

TEST(ParseConfigTest, ParsesFlatObject) {
  base::DictValue dict =
      ParseConfig(R"({"navigator.hardwareConcurrency":8})", /*strict=*/false);
  ASSERT_EQ(dict.size(), 1u);
  EXPECT_EQ(dict.FindInt("navigator.hardwareConcurrency"), 8);
}

TEST(ParseConfigTest, MalformedJsonYieldsEmptyDictWhenNotStrict) {
  base::DictValue dict = ParseConfig("{not json", /*strict=*/false);
  EXPECT_TRUE(dict.empty());
}

TEST(ParseConfigTest, NonObjectJsonYieldsEmptyDict) {
  base::DictValue dict = ParseConfig("[1,2,3]", /*strict=*/false);
  EXPECT_TRUE(dict.empty());
}

// The empty-input guard is load-bearing and easy to delete by accident,
// because EmptyInputYieldsEmptyDict passes without it: ReadDict("") also
// returns nullopt and reaches the same malformed branch. The difference
// only shows in strict mode, where losing the guard would CHECK-abort
// every ordinary unconfigured launch. This is the one test that fails if
// the guard goes away.
TEST(ParseConfigTest, EmptyInputIsNotAnErrorEvenInStrictMode) {
  base::DictValue dict = ParseConfig("", /*strict=*/true);
  EXPECT_TRUE(dict.empty());
}

// EXPECT_CHECK_DEATH_WITH rather than a bare EXPECT_DEATH matching the
// message. base/test/gtest_util.h branches on CHECK_WILL_STREAM(): in build
// configurations that strip CHECK message text it degrades to matching "",
// so a hand-written EXPECT_DEATH(..., "camoucfg") would fail there and read
// as a defect in the code rather than in the assertion.
TEST(ParseConfigDeathTest, MalformedJsonAbortsWhenStrict) {
  EXPECT_CHECK_DEATH_WITH(ParseConfig("{not json", /*strict=*/true),
                          "camoucfg");
}
```

Add `#include "base/values.h"` and `#include "base/test/gtest_util.h"` to the test
file's include block, and add `"//base/test:test_support",` to the `unit_tests`
target's `deps` in `components/camoucfg/BUILD.gn` — that is where
`EXPECT_CHECK_DEATH_WITH` comes from.

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
autoninja -C out/Default components_unittests && \
  ./out/Default/components_unittests --gtest_filter='ParseConfig*'
```

Expected: the build fails with `use of undeclared identifier 'ParseConfig'`. The test calls it unqualified from inside the namespace, so clang reports an undeclared identifier rather than a missing namespace member.

- [ ] **Step 3: Declare ParseConfig**

In `components/camoucfg/mask_config_internal.h`, add `#include "base/values.h"` to the include block and add before the closing namespace:

```cpp
// Parses the assembled configuration. The expected shape is a flat JSON
// object whose keys are dotted or colon-separated strings.
//
// Returns an empty dictionary when `raw` is empty, which is the normal
// stock-run case and is not logged. Malformed JSON, or valid JSON that is
// not an object, logs one error and returns an empty dictionary — every
// surface then falls back to its real value. When `strict` is true the same
// conditions abort the process instead, so that a misconfigured run fails
// loudly rather than silently exposing the real machine.
base::DictValue ParseConfig(std::string_view raw, bool strict);
```

- [ ] **Step 4: Implement ParseConfig**

In `components/camoucfg/mask_config_internal.cc`, add these includes:

```cpp
#include "base/json/json_reader.h"
#include "base/logging.h"
```

and add before the closing namespace:

```cpp
base::DictValue ParseConfig(std::string_view raw, bool strict) {
  if (raw.empty()) {
    return base::DictValue();
  }

  // ReadDict rejects both malformed JSON and valid JSON that is not an
  // object, in one call. `options` has no default in this revision and must
  // be passed; JSON_PARSE_RFC is the strict reading, which is right for a
  // machine-generated configuration — comments and trailing commas in a
  // fingerprint would mean the generator is broken.
  std::optional<base::DictValue> parsed =
      base::JSONReader::ReadDict(raw, base::JSON_PARSE_RFC);
  if (!parsed.has_value()) {
    LOG(ERROR) << "camoucfg: configuration is not a JSON object; "
               << "all spoofing is disabled and real values will be reported";
    CHECK(!strict) << "camoucfg: refusing to start with an invalid "
                   << "configuration because CAMOU_CONFIG_STRICT is set";
    return base::DictValue();
  }

  return std::move(*parsed);
}
```

`CHECK` is used rather than a bare `LOG(FATAL)` so the strict path produces a stack trace naming this function.

Two API notes for this Chromium revision, both verified against the checkout. The dictionary type is `base::DictValue`, a standalone class at `base/values.h:242` — `base::Value::Dict` does not exist here, and `components/` contains 4520 uses of the former and none of the latter. And `base::JSONReader::Read` takes a required `int options` parameter with no default, which is why `ReadDict` is called with one.

- [ ] **Step 5: Add the values dependency**

In `components/camoucfg/BUILD.gn` the `//base` dependency already covers `base::Value` and `base::JSONReader`; no change is needed. Confirm by rebuilding.

- [ ] **Step 6: Run the tests to verify they pass**

Run:

```bash
autoninja -C out/Default components_unittests && \
  ./out/Default/components_unittests --gtest_filter='ParseConfig*'
```

Expected: six ParseConfig tests pass. gtest isolates the death test into its own batch, so this arrives as `[  PASSED  ] 5 tests.` plus `[  PASSED  ] 1 test.` — read the total.

- [ ] **Step 7: Write the failing getter tests**

The typed getters take a dictionary rather than reading process-global state, so
every type path is testable with an ordinary fixture. Append inside the anonymous
namespace of `components/camoucfg/mask_config_unittest.cc`:

```cpp
base::DictValue Fixture() {
  return ParseConfig(R"({
    "s": "text",
    "u": 8,
    "neg": -3,
    "d": 1.5,
    "b": true,
    "list": ["a", "b"],
    "mixed": ["a", 1]
  })",
                     /*strict=*/false);
}

TEST(GettersTest, ReadCorrectTypes) {
  base::DictValue cfg = Fixture();
  EXPECT_EQ(GetStringFrom(cfg, "s"), "text");
  EXPECT_EQ(GetUint32From(cfg, "u"), 8u);
  EXPECT_EQ(GetInt32From(cfg, "neg"), -3);
  EXPECT_EQ(GetDoubleFrom(cfg, "d"), 1.5);
  EXPECT_EQ(GetBoolFrom(cfg, "b"), true);
  EXPECT_EQ(GetStringListFrom(cfg, "list"),
            (std::vector<std::string>{"a", "b"}));
  EXPECT_TRUE(HasKeyIn(cfg, "s"));
}

TEST(GettersTest, AbsentKeysAreSilentlyEmpty) {
  base::DictValue cfg = Fixture();
  EXPECT_FALSE(GetStringFrom(cfg, "missing").has_value());
  EXPECT_FALSE(GetUint32From(cfg, "missing").has_value());
  EXPECT_FALSE(GetInt32From(cfg, "missing").has_value());
  EXPECT_FALSE(GetDoubleFrom(cfg, "missing").has_value());
  EXPECT_FALSE(GetBoolFrom(cfg, "missing").has_value());
  EXPECT_TRUE(GetStringListFrom(cfg, "missing").empty());
  EXPECT_FALSE(HasKeyIn(cfg, "missing"));
}

TEST(GettersTest, WrongTypesReturnEmpty) {
  base::DictValue cfg = Fixture();
  EXPECT_FALSE(GetStringFrom(cfg, "u").has_value());
  EXPECT_FALSE(GetUint32From(cfg, "s").has_value());
  EXPECT_FALSE(GetInt32From(cfg, "s").has_value());
  EXPECT_FALSE(GetDoubleFrom(cfg, "s").has_value());
  EXPECT_FALSE(GetBoolFrom(cfg, "u").has_value());
  EXPECT_TRUE(GetStringListFrom(cfg, "s").empty());
  EXPECT_TRUE(GetStringListFrom(cfg, "mixed").empty());
}

TEST(GettersTest, NegativeIntegerIsNotAnUnsigned) {
  base::DictValue cfg = Fixture();
  EXPECT_FALSE(GetUint32From(cfg, "neg").has_value());
}

TEST(GettersTest, WholeNumberWidensToDouble) {
  base::DictValue cfg = Fixture();
  EXPECT_EQ(GetDoubleFrom(cfg, "u"), 8.0);
}

// GetStringListFrom returns {} for an absent key, a wrong-typed key, and a
// genuinely empty list alike. That collapse is accepted rather than
// accidental: all three mean "no list configured" and the caller falls back
// to the real value either way. A caller that needs to tell them apart has
// HasKeyIn. Pinned so the ambiguity stays a recorded decision.
TEST(GettersTest, ExplicitEmptyListIsEmptyButPresent) {
  base::DictValue cfg = ParseConfig(R"({"empty": []})", /*strict=*/false);
  EXPECT_TRUE(GetStringListFrom(cfg, "empty").empty());
  EXPECT_TRUE(HasKeyIn(cfg, "empty"));
  EXPECT_FALSE(HasKeyIn(cfg, "absent"));
}
```

Add `#include <vector>` to the test file's include block.

- [ ] **Step 8: Run the getter tests to verify they fail**

Run:

```bash
autoninja -C out/Default components_unittests && \
  ./out/Default/components_unittests --gtest_filter='GettersTest.*'
```

Expected: the build fails with `use of undeclared identifier 'GetStringFrom'` — unqualified call from inside the namespace, so clang reports an undeclared identifier.

- [ ] **Step 9: Declare the getters**

In `components/camoucfg/mask_config_internal.h`, add `#include <cstdint>`, `#include <vector>`, and `#include <string_view>` to the include block, then add before the closing namespace:

```cpp
// Typed lookups over an already-parsed configuration.
//
// Each returns nullopt when the key is absent, and logs a warning naming the
// key and returns nullopt when the key is present with the wrong type. A
// caller that gets nullopt falls back to the real value; never to a
// placeholder.
//
// These take the dictionary explicitly rather than reading process-global
// state so that every type path is testable. The public API in
// mask_config.h forwards to them with the process configuration.
std::optional<std::string> GetStringFrom(const base::DictValue& cfg,
                                         std::string_view key);
std::optional<uint32_t> GetUint32From(const base::DictValue& cfg,
                                      std::string_view key);
std::optional<int32_t> GetInt32From(const base::DictValue& cfg,
                                    std::string_view key);
std::optional<double> GetDoubleFrom(const base::DictValue& cfg,
                                    std::string_view key);
std::optional<bool> GetBoolFrom(const base::DictValue& cfg,
                                std::string_view key);
std::vector<std::string> GetStringListFrom(const base::DictValue& cfg,
                                           std::string_view key);
bool HasKeyIn(const base::DictValue& cfg, std::string_view key);
```

- [ ] **Step 10: Implement the getters**

In `components/camoucfg/mask_config_internal.cc`, add inside the namespace, above the getters:

```cpp
namespace {

void WarnWrongType(std::string_view key, const char* expected) {
  LOG(WARNING) << "camoucfg: key '" << key << "' is not " << expected
               << "; falling back to the real value";
}

}  // namespace

std::optional<std::string> GetStringFrom(const base::DictValue& cfg,
                                         std::string_view key) {
  const base::Value* value = cfg.Find(key);
  if (!value) {
    return std::nullopt;
  }
  if (!value->is_string()) {
    WarnWrongType(key, "a string");
    return std::nullopt;
  }
  return value->GetString();
}

std::optional<uint32_t> GetUint32From(const base::DictValue& cfg,
                                      std::string_view key) {
  const base::Value* value = cfg.Find(key);
  if (!value) {
    return std::nullopt;
  }
  if (!value->is_int()) {
    WarnWrongType(key, "an integer");
    return std::nullopt;
  }
  const int as_int = value->GetInt();
  if (as_int < 0) {
    WarnWrongType(key, "a non-negative integer");
    return std::nullopt;
  }
  return static_cast<uint32_t>(as_int);
}

std::optional<int32_t> GetInt32From(const base::DictValue& cfg,
                                    std::string_view key) {
  const base::Value* value = cfg.Find(key);
  if (!value) {
    return std::nullopt;
  }
  if (!value->is_int()) {
    WarnWrongType(key, "an integer");
    return std::nullopt;
  }
  return value->GetInt();
}

std::optional<double> GetDoubleFrom(const base::DictValue& cfg,
                                    std::string_view key) {
  const base::Value* value = cfg.Find(key);
  if (!value) {
    return std::nullopt;
  }
  // A JSON number with no fractional part parses as an int. Widening it is
  // what a configuration author expects, so accept both.
  if (value->is_int()) {
    return static_cast<double>(value->GetInt());
  }
  if (!value->is_double()) {
    WarnWrongType(key, "a number");
    return std::nullopt;
  }
  return value->GetDouble();
}

std::optional<bool> GetBoolFrom(const base::DictValue& cfg,
                                std::string_view key) {
  const base::Value* value = cfg.Find(key);
  if (!value) {
    return std::nullopt;
  }
  if (!value->is_bool()) {
    WarnWrongType(key, "a boolean");
    return std::nullopt;
  }
  return value->GetBool();
}

std::vector<std::string> GetStringListFrom(const base::DictValue& cfg,
                                           std::string_view key) {
  const base::Value* value = cfg.Find(key);
  if (!value) {
    return {};
  }
  if (!value->is_list()) {
    WarnWrongType(key, "a list");
    return {};
  }

  std::vector<std::string> out;
  for (const base::Value& entry : value->GetList()) {
    if (!entry.is_string()) {
      WarnWrongType(key, "a list of strings");
      return {};
    }
    out.push_back(entry.GetString());
  }
  return out;
}

bool HasKeyIn(const base::DictValue& cfg, std::string_view key) {
  return cfg.Find(key) != nullptr;
}
```

A wrong-typed entry in a list rejects the whole list rather than skipping the bad
entry. Silently dropping one entry would leave a shorter list that still looks
plausible, which is worse than falling back to the real value — Camoufox reached the
same conclusion for `MVoices()` and says so in a comment there.

- [ ] **Step 11: Run the getter tests to verify they pass**

Run:
Expected: eighteen tests pass in total — six assembly, six parsing, six getter. gtest isolates the death test into its own batch, so the total arrives across two `[  PASSED  ] N tests.` lines rather than one, closing with `SUCCESS: all tests passed.`
```bash
autoninja -C out/Default components_unittests && \
  ./out/Default/components_unittests --gtest_filter='GettersTest.*'
```

Expected: `[  PASSED  ] 6 tests.`

- [ ] **Step 12: Run the whole component's tests**

Run:

```bash
./out/Default/components_unittests \
  --gtest_filter='AssembleRawConfig*:ParseConfig*:GettersTest*'
```

Expected: `[  PASSED  ] 16 tests.`

- [ ] **Step 13: Commit**

```bash
cd ~/chromium/src
git add components/camoucfg/
git commit -m "camoucfg: parse configuration JSON and add typed lookups"
```

---

### Task 3: Public API, typed getters, and the process singleton

**Files:**
- Create: `components/camoucfg/mask_config.h`
- Create: `components/camoucfg/mask_config.cc`
- Modify: `components/camoucfg/BUILD.gn`
- Modify: `components/camoucfg/mask_config_unittest.cc`

**Interfaces:**
- Consumes: `AssembleRawConfig` and `ParseConfig` from Tasks 1 and 2.
- Produces: `camoucfg::ConfigScope`, `camoucfg::GlobalScope()`, and the getters `GetString`, `GetUint32`, `GetInt32`, `GetDouble`, `GetBool`, `GetStringList`, `HasKey` — each taking `(const ConfigScope&, std::string_view)` and returning `std::optional<T>` except `GetStringList` (returns `std::vector<std::string>`, empty when absent) and `HasKey` (returns `bool`).

- [ ] **Step 1: Write the header**

Create `components/camoucfg/mask_config.h`:

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_MASK_CONFIG_H_
#define COMPONENTS_CAMOUCFG_MASK_CONFIG_H_

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "base/no_destructor.h"

namespace camoucfg {

// Identifies which configuration a lookup reads.
//
// Today there is exactly one, returned by GlobalScope(). The parameter
// exists so that a later per-context store — pushed from the browser process
// or set over the DevTools protocol — can be introduced by changing how a
// scope is obtained, without editing a single call site. Camoufox reached
// the same conclusion the hard way: its issue #57, per-context timezone not
// working, is what a global-only configuration costs when the requirement
// arrives later.
class ConfigScope {
 public:
  ConfigScope(const ConfigScope&) = delete;
  ConfigScope& operator=(const ConfigScope&) = delete;

 private:
  // base::NoDestructor constructs the singleton in place with a placement
  // new inside its own constructor, so it is NoDestructor — not
  // GlobalScope — that needs access to this constructor. Befriending
  // GlobalScope instead does not compile. This is the established Chromium
  // idiom; components/ carries several precedents.
  friend class base::NoDestructor<ConfigScope>;
  ConfigScope() = default;
};

// The process-wide configuration. Parsed from the environment on first use.
const ConfigScope& GlobalScope();

// Each getter returns nullopt when the key is absent, and logs a warning and
// returns nullopt when the key is present with the wrong type. Callers are
// expected to fall back to the real value; never to a placeholder.
std::optional<std::string> GetString(const ConfigScope& scope,
                                     std::string_view key);
std::optional<uint32_t> GetUint32(const ConfigScope& scope,
                                  std::string_view key);
std::optional<int32_t> GetInt32(const ConfigScope& scope,
                                std::string_view key);
std::optional<double> GetDouble(const ConfigScope& scope,
                                std::string_view key);
std::optional<bool> GetBool(const ConfigScope& scope, std::string_view key);

// Returns an empty vector when the key is absent or is not a list of strings.
std::vector<std::string> GetStringList(const ConfigScope& scope,
                                       std::string_view key);

bool HasKey(const ConfigScope& scope, std::string_view key);

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_MASK_CONFIG_H_
```

- [ ] **Step 2: Write the failing tests**

Append inside the anonymous namespace of `components/camoucfg/mask_config_unittest.cc`:

```cpp
TEST(MaskConfigTest, AbsentKeysReturnNullopt) {
  const camoucfg::ConfigScope& scope = camoucfg::GlobalScope();
  EXPECT_FALSE(camoucfg::GetUint32(scope, "nope.not.here").has_value());
  EXPECT_FALSE(camoucfg::GetString(scope, "nope.not.here").has_value());
  EXPECT_FALSE(camoucfg::HasKey(scope, "nope.not.here"));
  EXPECT_TRUE(camoucfg::GetStringList(scope, "nope.not.here").empty());
}
```

Add `#include "components/camoucfg/mask_config.h"` to the test file's include block.

This test asserts the stock behaviour that matters most: with no configuration set, every getter is silent and empty, so every surface falls back to its real value. It is deliberately the only unit test at this layer — every type path is already covered by Task 2's `GettersTest` cases against explicit fixtures, and these functions are one-line forwards to those. Re-testing conversion here would only exercise the forwarding.

- [ ] **Step 3: Run the test to verify it fails**

Run:

```bash
autoninja -C out/Default components_unittests && \
  ./out/Default/components_unittests --gtest_filter='MaskConfigTest.*'
```

Expected: `mask_config.h` exists and compiles, but `mask_config.cc` has not been written and is not yet in `BUILD.gn`, so the test links against nothing and the build fails with `undefined reference to camoucfg::GlobalScope()`.

Note the difference from Task 1 Step 5, and do not mistake one for the other. There, `BUILD.gn` named a `.cc` that did not exist, so Siso failed at source resolution with `missing and no known rule to make it`. Here `BUILD.gn` names no such file, compilation succeeds, and the failure is a genuine link error. If you see the Task 1 shape of error at this step, `BUILD.gn` was edited too early.

- [ ] **Step 4: Implement**

Create `components/camoucfg/mask_config.cc`:

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "components/camoucfg/mask_config.h"

#include <utility>

#include "base/environment.h"
#include "base/logging.h"
#include "base/no_destructor.h"
#include "base/values.h"
#include "components/camoucfg/mask_config_internal.h"

namespace camoucfg {
namespace {

// Parsed exactly once per process, on first access, in whichever process
// touches the configuration first.
const base::DictValue& Config() {
  static const base::NoDestructor<base::DictValue> dict([] {
    std::unique_ptr<base::Environment> env = base::Environment::Create();
    auto get = [&env](const std::string& name) -> std::optional<std::string> {
      return env->GetVar(name);
    };
    const std::string raw = internal::AssembleRawConfig(get);
    const bool strict = env->GetVar("CAMOU_CONFIG_STRICT").has_value();
    base::DictValue parsed = internal::ParseConfig(raw, strict);
    VLOG(1) << "camoucfg: parsed " << parsed.size() << " key(s)";
    return parsed;
  }());
  return *dict;
}

}  // namespace

const ConfigScope& GlobalScope() {
  static const base::NoDestructor<ConfigScope> scope;
  return *scope;
}

std::optional<std::string> GetString(const ConfigScope& scope,
                                     std::string_view key) {
  return internal::GetStringFrom(Config(), key);
}

std::optional<uint32_t> GetUint32(const ConfigScope& scope,
                                  std::string_view key) {
  return internal::GetUint32From(Config(), key);
}

std::optional<int32_t> GetInt32(const ConfigScope& scope,
                                std::string_view key) {
  return internal::GetInt32From(Config(), key);
}

std::optional<double> GetDouble(const ConfigScope& scope,
                                std::string_view key) {
  return internal::GetDoubleFrom(Config(), key);
}

std::optional<bool> GetBool(const ConfigScope& scope, std::string_view key) {
  return internal::GetBoolFrom(Config(), key);
}

std::vector<std::string> GetStringList(const ConfigScope& scope,
                                       std::string_view key) {
  return internal::GetStringListFrom(Config(), key);
}

bool HasKey(const ConfigScope& scope, std::string_view key) {
  return internal::HasKeyIn(Config(), key);
}

}  // namespace camoucfg
```

The `scope` parameter is intentionally unused in every body. That is the point:
resolving a scope to a configuration happens in exactly one place — `Config()` today,
a per-context lookup later — and the signature is what keeps every call site from
having to change when that happens.

Each public getter is a one-line forward to the tested function from Task 2. The
duplication of the seven names is deliberate and not worth a macro: the header is the
project's public contract and reads better spelled out.

- [ ] **Step 5: Add the new files to the build**

In `components/camoucfg/BUILD.gn`, replace the `sources` list of the `camoucfg` target with:

```gn
  sources = [
    "mask_config.cc",
    "mask_config.h",
    "mask_config_internal.cc",
    "mask_config_internal.h",
  ]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run:

```bash
autoninja -C out/Default components_unittests && \
  ./out/Default/components_unittests \
    --gtest_filter='AssembleRawConfig*:ParseConfig*:MaskConfigTest*'
```

Expected: thirteen tests pass in total — six assembly, six parsing, one public-API. gtest isolates the death test into its own batch, so the total arrives across two lines. Read the total and the closing `SUCCESS: all tests passed.`

- [ ] **Step 7: Commit**

```bash
cd ~/chromium/src
git add components/camoucfg/
git commit -m "camoucfg: add the scope-shaped public API and typed getters"
```

---

### Task 4: The tracer bullet — navigator.hardwareConcurrency

**Files:**
- Create: `components/camoucfg/blink_scope.h`
- Modify: `components/camoucfg/BUILD.gn`
- Modify: `third_party/blink/renderer/DEPS`
- Modify: `third_party/blink/renderer/core/execution_context/navigator_base.h`
- Modify: `third_party/blink/renderer/core/execution_context/navigator_base.cc`

**Interfaces:**
- Consumes: `camoucfg::GlobalScope()`, `camoucfg::GetUint32` from Task 3.
- Produces: `camoucfg::ScopeFor(blink::ExecutionContext*) -> const ConfigScope&`, and a spoofable `navigator.hardwareConcurrency`.

The override goes in `NavigatorBase`, not in `NavigatorConcurrentHardware`, for two reasons. `NavigatorConcurrentHardware::hardwareConcurrency()` takes no arguments and is a bare mixin with no access to an execution context, so the scope-shaped API could not be exercised there at all. `NavigatorBase` at `third_party/blink/renderer/core/execution_context/navigator_base.h:41` inherits that mixin, lives in the execution-context directory, and is the common base of both `Navigator` and `WorkerNavigator` — so one override gives window and worker the same answer by construction, which is exactly the parity the conventions require.

- [ ] **Step 1: Confirm the base class still exposes an execution context**

Already verified against this checkout: `NavigatorBase` inherits `ScriptWrappable`,
`NavigatorConcurrentHardware`, `NavigatorDeviceMemory`, `NavigatorID`,
`NavigatorLanguage`, `NavigatorOnLine`, `NavigatorUA`, **`ExecutionContextClient`**
(at `navigator_base.h:47`), and `Supplementable<NavigatorBase>`.
`ExecutionContextClient` is what supplies `ExecutionContext* GetExecutionContext() const`.

Re-confirm before editing, since this is the one assumption the whole task rests on:

```bash
cd ~/chromium/src
grep -n "ExecutionContextClient" \
  third_party/blink/renderer/core/execution_context/navigator_base.h
```

Expected: a line reading `public ExecutionContextClient,`. If it is absent, stop and
report — Step 5's call is the only line that depends on it, but there is no correct
way to write that line without knowing which base provides the context.

- [ ] **Step 2: Write the Blink scope adapter**

Create `components/camoucfg/blink_scope.h`:

```cpp
// Copyright 2026 The Camoucrome Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_CAMOUCFG_BLINK_SCOPE_H_
#define COMPONENTS_CAMOUCFG_BLINK_SCOPE_H_

#include "components/camoucfg/mask_config.h"

namespace blink {
class ExecutionContext;
}

namespace camoucfg {

// Resolves a Blink execution context to the configuration it should read.
//
// Today every context resolves to the one process-global configuration, and
// the argument is ignored. This function is the single place that changes
// when a per-context store is introduced; no call site moves. It is declared
// here rather than inside Blink so that a Blink call site needs exactly one
// include.
inline const ConfigScope& ScopeFor(blink::ExecutionContext*) {
  return GlobalScope();
}

}  // namespace camoucfg

#endif  // COMPONENTS_CAMOUCFG_BLINK_SCOPE_H_
```

Add `"blink_scope.h",` to the `sources` list of the `camoucfg` target in `components/camoucfg/BUILD.gn`, keeping the list alphabetical:

```gn
  sources = [
    "blink_scope.h",
    "mask_config.cc",
    "mask_config.h",
    "mask_config_internal.cc",
    "mask_config_internal.h",
  ]
```

- [ ] **Step 3: Allow Blink to include the component**

`third_party/blink/renderer/DEPS` lists individual headers, for example `"+components/crash/core/common/crash_key.h",` at line 95. Follow that convention: add these two entries to the `include_rules` list, alphabetically among the other `+components` entries:

```
    "+components/camoucfg/blink_scope.h",
    "+components/camoucfg/mask_config.h",
```

- [ ] **Step 4: Declare the override**

In `third_party/blink/renderer/core/execution_context/navigator_base.h`, inside the `public:` section of `class CORE_EXPORT NavigatorBase`, add:

```cpp
  // NavigatorConcurrentHardware override. Reports the configured value when
  // one is set, and the machine's real processor count otherwise. Overriding
  // here rather than in the mixin gives Navigator and WorkerNavigator the
  // same answer by construction.
  unsigned hardwareConcurrency() const override;
```

- [ ] **Step 5: Implement the override**

In `third_party/blink/renderer/core/execution_context/navigator_base.cc`, add to the include block:

```cpp
#include "base/system/sys_info.h"
#include "components/camoucfg/blink_scope.h"
#include "components/camoucfg/mask_config.h"
```

and add inside `namespace blink {`:

```cpp
unsigned NavigatorBase::hardwareConcurrency() const {
  std::optional<uint32_t> configured = camoucfg::GetUint32(
      camoucfg::ScopeFor(GetExecutionContext()),
      "navigator.hardwareConcurrency");
  if (configured.has_value()) {
    return *configured;
  }
  return static_cast<unsigned>(base::SysInfo::NumberOfProcessors());
}
```

The fallback repeats the original expression from `NavigatorConcurrentHardware` verbatim rather than a constant. That is the pattern every later surface copies.

- [ ] **Step 6: Add the build dependency**

In `third_party/blink/renderer/core/BUILD.gn`, the `deps` list's `//components/`
entries begin at line 411 with `"//components/paint_preview/common",` and are
alphabetical. Insert immediately **above** that line:

```gn
    "//components/camoucfg",
```

- [ ] **Step 7: Build**

Run:

```bash
autoninja -C out/Default content_shell
```

Expected: build succeeds. A DEPS violation would report `Illegal include: "components/camoucfg/mask_config.h"`; if that appears, Step 3 was not applied correctly.

- [ ] **Step 8: Commit**

```bash
cd ~/chromium/src
git add components/camoucfg/ \
        third_party/blink/renderer/DEPS \
        third_party/blink/renderer/core/BUILD.gn \
        third_party/blink/renderer/core/execution_context/navigator_base.h \
        third_party/blink/renderer/core/execution_context/navigator_base.cc
git commit -m "camoucfg: drive navigator.hardwareConcurrency through the config layer"
```

---

### Task 5: Browser-process smoke check

**Files:**
- Modify: `content/browser/browser_main_loop.cc`

**Interfaces:**
- Consumes: `camoucfg::GlobalScope()`, `camoucfg::HasKey` from Task 3.
- Produces: nothing consumed by later tasks.

This spoofs nothing. It exists so that SP1, which patches `components/embedder_support/user_agent_utils.cc` in the browser process, does not discover a broken configuration path at that point. Five lines now against a much harder debugging session later.

- [ ] **Step 1: Add the call**

In `content/browser/browser_main_loop.cc`, add to the include block:

```cpp
#include "components/camoucfg/mask_config.h"
```

Then inside `int BrowserMainLoop::EarlyInitialization()` — the function begins at line 542 with a `TRACE_EVENT0("startup", ...)` on the following line — add immediately after that `TRACE_EVENT0` line:

```cpp
  // Touches the configuration so that its one-time parse happens here, in the
  // browser process, and its VLOG(1) confirms the non-renderer path works.
  // SP1 is the first sub-project to depend on this path for real.
  VLOG(1) << "camoucfg: browser process configuration reachable, "
          << "navigator.hardwareConcurrency configured="
          << camoucfg::HasKey(camoucfg::GlobalScope(),
                              "navigator.hardwareConcurrency");
```

- [ ] **Step 2: Add the build dependency**

In `content/browser/BUILD.gn`, the `deps` list already carries `//components/`
entries — `"//components/download/database",` is at line 153 — and they are
alphabetical. Insert `"//components/camoucfg",` in alphabetical position among them,
which is above the `download` entries.

- [ ] **Step 3: Build**

Run:

```bash
autoninja -C out/Default content_shell
```

Expected: build succeeds.

- [ ] **Step 4: Verify the browser process reads the configuration**

Run:

`content_shell` has no `--headless` or `--dump-dom` switch; those belong to `chrome`.
The equivalent here is `--ozone-platform=headless`, verified working against this
build. The shell does not exit on its own, so `timeout` ends it.

```bash
cd ~/chromium/src
CAMOU_CONFIG='{"navigator.hardwareConcurrency":8}' \
  timeout 15 ./out/Default/content_shell --no-sandbox \
  --ozone-platform=headless \
  --vmodule=browser_main_loop=1,mask_config=1 \
  about:blank 2>&1 | grep camoucfg
```

Expected: two lines, one reading `camoucfg: parsed 1 key(s)` and one reading `camoucfg: browser process configuration reachable, navigator.hardwareConcurrency configured=1`.

- [ ] **Step 5: Commit**

```bash
cd ~/chromium/src
git add content/browser/browser_main_loop.cc content/browser/BUILD.gn
git commit -m "camoucfg: log configuration reachability from the browser process"
```

---

### Task 6: Runtime verification against the spec's acceptance criteria

**Files:**
- Create: `~/camoucrome-verify/verify_sp0.py` (a scratch script on the build machine, not committed to the Chromium tree)

**Interfaces:**
- Consumes: the `content_shell` binary built by Tasks 4 and 5.
- Produces: a pass or fail report covering all six criteria in the SP0 spec.

- [ ] **Step 1: Install the driver**

Run:

```bash
python3 -m venv ~/camoucrome-verify/venv
~/camoucrome-verify/venv/bin/pip install playwright==1.55.0
```

Playwright is used only as a CDP client here; no browser download is needed because it connects to the locally built `content_shell`.

- [ ] **Step 2: Write the verification script**

Create `~/camoucrome-verify/verify_sp0.py`:

```python
"""Verifies the six SP0 acceptance criteria against a built content_shell."""

import json
import os
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

SHELL = os.path.expanduser("~/chromium/src/out/Default/content_shell")
PORT = 9333


def launch(config):
    env = dict(os.environ)
    env.pop("CAMOU_CONFIG", None)
    if config is not None:
        env["CAMOU_CONFIG"] = config
    # content_shell has no --headless switch; --ozone-platform=headless is the
    # equivalent and is verified working against this build. CDP is served on
    # --remote-debugging-port exactly as chrome serves it.
    proc = subprocess.Popen(
        [SHELL, "--no-sandbox", "--ozone-platform=headless",
         f"--remote-debugging-port={PORT}", "about:blank"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    time.sleep(5)
    return proc


def evaluate(expressions):
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        return [page.evaluate(e) for e in expressions]


WORKER_PROBE = """
() => new Promise(resolve => {
  const src = 'self.postMessage(navigator.hardwareConcurrency)';
  const url = URL.createObjectURL(new Blob([src], {type: 'text/javascript'}));
  const w = new Worker(url);
  w.onmessage = e => resolve(e.data);
})
"""

DESCRIPTOR_PROBE = """
() => Object.getOwnPropertyDescriptor(
    Navigator.prototype, 'hardwareConcurrency').get.toString()
"""

results = {}

# Criteria 2 and 5: spoofed value, and worker parity under spoofing.
proc = launch('{"navigator.hardwareConcurrency":8}')
window_value, worker_value, descriptor, keys = evaluate(
    ["navigator.hardwareConcurrency", WORKER_PROBE, DESCRIPTOR_PROBE,
     "Object.keys(window).join(',')"])
proc.terminate()
results["2 spoofed value is 8"] = window_value == 8
results["5 worker agrees when spoofed"] = worker_value == 8
# Criterion 4, first half: the accessor still looks native.
results["4 accessor reports [native code]"] = "[native code]" in descriptor
spoofed_keys = keys

# Criteria 3 and 5: real value, and worker parity without configuration.
proc = launch(None)
real_window, real_worker, stock_keys = evaluate(
    ["navigator.hardwareConcurrency", WORKER_PROBE,
     "Object.keys(window).join(',')"])
proc.terminate()
results["3 falls back to the real 16"] = real_window == 16
results["5 worker agrees when unconfigured"] = real_worker == real_window
# Criterion 4, second half: no property was added or removed.
results["4 window keys unchanged"] = spoofed_keys == stock_keys

# Criterion 6: malformed configuration does not crash and reports the truth.
proc = launch("{not json")
malformed_value = evaluate(["navigator.hardwareConcurrency"])[0]
proc.terminate()
stderr = proc.stderr.read().decode("utf-8", "replace")
results["6 malformed config reports the real value"] = malformed_value == 16
results["6 malformed config logs an error"] = "camoucfg" in stderr

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")

sys.exit(0 if all(results.values()) else 1)
```

- [ ] **Step 3: Run the unit tests (criterion 1)**

Run:

```bash
cd ~/chromium/src
autoninja -C out/Default components_unittests && \
  ./out/Default/components_unittests \
    --gtest_filter='AssembleRawConfig*:ParseConfig*:GettersTest*:MaskConfigTest*'
```

Expected: nineteen tests pass in total — six assembly, six parsing, six getter, one public-API — reported across two batches because gtest isolates the death test, closing with `SUCCESS: all tests passed.`

- [ ] **Step 4: Run the runtime verification (criteria 2 through 6)**

Run:

```bash
~/camoucrome-verify/venv/bin/python ~/camoucrome-verify/verify_sp0.py
```

Expected: eight `PASS` lines and exit status 0.

The one to read carefully is `4 window keys unchanged`. That assertion is what separates a C++ implementation from an injected one, and it is the single most important line in this plan. If it fails, something added a property to `window`, and the change is detectable no matter how correct the value is.

- [ ] **Step 5: Commit the verification script to the Camoucrome repository**

The script was authored on the controlling machine in Step 2 and pushed to the build
machine; commit the local copy, which is the source of truth.

```bash
cd /Users/lang/GolandProjects/github.com/lang315/camoucrome
mkdir -p scripts
cp "$STAGED_VERIFY_SCRIPT" scripts/verify_sp0.py
git add scripts/verify_sp0.py
git commit -m "test: add the SP0 runtime verification script"
```

where `STAGED_VERIFY_SCRIPT` is the path the file was written to in Step 2. If the
script was instead authored directly on the build machine, pull it back with the same
`cat`-over-ssh pattern Task 7 Step 2 uses.

---

### Task 7: Extract the change set into the Camoucrome repository

**Files:**
- Create: `additions/camoucfg/BUILD.gn`, `mask_config.h`, `mask_config.cc`, `mask_config_internal.h`, `mask_config_internal.cc`, `blink_scope.h`, `mask_config_unittest.cc`
- Create: `patches/sp0-config-layer.patch`
- Create: `scripts/apply.sh`
- Modify: `README.md`

**Interfaces:**
- Consumes: the commits produced by Tasks 1 through 5 in `~/chromium/src`.
- Produces: a reproducible change set that survives `gclient sync` wiping the Chromium tree.

This is the task that makes the previous six durable. Until it runs, all of SP0 exists only as commits on a branch inside a generated directory that the next `gclient sync` can rewrite.

- [ ] **Step 1: Confirm the base revision**

The base revision is pinned in this plan's Global Constraints, not derived from a
commit count. `HEAD~5` would be wrong the moment a review loop adds a fix commit, and
would silently produce a patch missing part of the work.

Run on the build machine:

```bash
cd ~/chromium/src
echo 0e8d4a9268118d323f62ca207b40514df39dcaa9 > /tmp/camoucrome_base_revision
git merge-base --is-ancestor $(cat /tmp/camoucrome_base_revision) HEAD && \
  echo "base is an ancestor of HEAD: OK"
git log --oneline $(cat /tmp/camoucrome_base_revision)..HEAD
```

Expected: `base is an ancestor of HEAD: OK`, followed by the commits from Tasks 1
through 5 — five of them if no review loop added a fix, more if one did. Either count
is fine; that is the point of pinning the revision rather than counting backwards.

- [ ] **Step 2: Copy the whole new files into `additions/`**

Every file under `components/camoucfg/` is new, so it is an addition rather than a
diff. Pull all seven back to the Camoucrome repository. `PCWSL` is the wrapper that
pipes a script to `wsl -d Ubuntu-24.04 -u lang -- bash -s` over the persistent ssh
connection:

```bash
cd /Users/lang/GolandProjects/github.com/lang315/camoucrome
mkdir -p additions/camoucfg
for f in BUILD.gn blink_scope.h mask_config.h mask_config.cc \
         mask_config_internal.h mask_config_internal.cc mask_config_unittest.cc; do
  echo "cat ~/chromium/src/components/camoucfg/$f" | "$PCWSL" > "additions/camoucfg/$f"
done
wc -l additions/camoucfg/*
```

Expected: seven files, none of them empty. An empty file means the `cat` failed and
the redirect truncated it — check the path before continuing.

- [ ] **Step 3: Generate the patch for pre-existing files**

Run on the build machine:

```bash
cd ~/chromium/src
git diff $(cat /tmp/camoucrome_base_revision) HEAD -- \
  components/BUILD.gn \
  content/browser/BUILD.gn \
  content/browser/browser_main_loop.cc \
  third_party/blink/renderer/DEPS \
  third_party/blink/renderer/core/BUILD.gn \
  third_party/blink/renderer/core/execution_context/navigator_base.h \
  third_party/blink/renderer/core/execution_context/navigator_base.cc \
  > /tmp/sp0-config-layer.patch
wc -l /tmp/sp0-config-layer.patch
```

Expected: a patch of roughly 60 to 90 lines touching exactly seven files. Copy it to `patches/sp0-config-layer.patch` in the Camoucrome repository.

Note how small it is. Every line in `patches/` is a line that can conflict on a Chromium rebase, while `additions/` never conflicts. Keeping that ratio is why SP6a promotes additions-over-patches from a preference to a policy.

- [ ] **Step 4: Write the apply script**

Create `scripts/apply.sh` in the Camoucrome repository:

```bash
#!/bin/bash
# Applies the Camoucrome change set to a Chromium checkout.
# Usage: scripts/apply.sh /path/to/chromium/src
set -euo pipefail

SRC="${1:?usage: apply.sh <chromium-src-dir>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -d "$SRC/third_party/blink" ]; then
  echo "error: $SRC does not look like a Chromium checkout" >&2
  exit 1
fi

echo "copying additions"
mkdir -p "$SRC/components/camoucfg"
cp "$ROOT"/additions/camoucfg/* "$SRC/components/camoucfg/"

echo "applying patches"
for patch in "$ROOT"/patches/*.patch; do
  echo "  $(basename "$patch")"
  git -C "$SRC" apply --3way "$patch"
done

echo "done. build with: autoninja -C out/Default content_shell"
```

Make it executable with `chmod +x scripts/apply.sh`.

- [ ] **Step 5: Verify the change set reproduces**

Run on the build machine:

First push the Camoucrome change set to the build machine. From the controlling
machine:

```bash
cd /Users/lang/GolandProjects/github.com/lang315/camoucrome
COPYFILE_DISABLE=1 tar czf - additions patches scripts | \
  base64 | \
  { echo 'mkdir -p ~/camoucrome && cd ~/camoucrome && base64 -d | tar xzf -'; cat; } | \
  "$PCWSL"
echo 'ls -R ~/camoucrome | head -20' | "$PCWSL"
```

Expected: the listing shows `additions/camoucfg` with seven files, `patches` with one
`.patch`, and `scripts/apply.sh`.

Then, on the build machine:

```bash
cd ~/chromium/src
git stash list  # expected: empty
git checkout -b camoucrome-verify $(cat /tmp/camoucrome_base_revision)
chmod +x ~/camoucrome/scripts/apply.sh
~/camoucrome/scripts/apply.sh ~/chromium/src
git -C ~/chromium/src diff --stat
```

Expected: `git diff --stat` reports the same seven modified files as Step 3, and `git status` reports `components/camoucfg/` as untracked. Then rebuild and re-run Task 6's verification to confirm the reconstructed tree behaves identically:

```bash
autoninja -C out/Default content_shell && \
  ~/camoucrome-verify/venv/bin/python ~/camoucrome-verify/verify_sp0.py
```

Expected: eight `PASS` lines and exit status 0.

- [ ] **Step 6: Update the repository status**

In `README.md`, replace the line reading `**Status: design phase.** No code yet. The specs in` and its continuation with:

```markdown
**Status: SP0 landed.** The configuration layer exists and drives
`navigator.hardwareConcurrency`. Apply it to a Chromium checkout with
`scripts/apply.sh <chromium-src>`. The specs in
```

Also record the pinned base revision by adding, immediately after that paragraph:

```markdown
The change set is generated against Chromium revision
`<paste the hash from Step 1>`. Rebasing onto a newer revision is SP6a's job.
```

- [ ] **Step 7: Commit**

```bash
cd /Users/lang/GolandProjects/github.com/lang315/camoucrome
git add additions/ patches/ scripts/ README.md
git commit -m "feat: land SP0, the camoucfg configuration layer

The layer parses a JSON object out of chunked environment variables once
per process and serves typed lookups to the browser, renderer and GPU
processes. Every getter takes a ConfigScope first argument that today
always resolves to one process-global configuration, so that introducing
a per-context store later changes one function rather than every call
site.

navigator.hardwareConcurrency is driven through it as a tracer. The
override lives in NavigatorBase rather than in the NavigatorConcurrentHardware
mixin, because the mixin takes no arguments and has no execution context
to scope a lookup by, while NavigatorBase has one and is the common base
of Navigator and WorkerNavigator -- so window and worker agree by
construction rather than by a separate mechanism.

Verified: 11 unit tests pass; the value is 8 when configured and the
machine's real 16 when not; a worker agrees in both cases; the accessor
still reports [native code] and Object.keys(window) is unchanged against
a stock build; malformed configuration logs an error, reports the real
value, and does not crash."
```

---

## Self-Review

**Spec coverage.** SP0's spec has eight sections. Section 4.1, the component and its DEPS entry, is Tasks 1 and 4. Section 4.2, reading and parsing, is Tasks 1 and 2. Section 4.3, the API, is Tasks 3 and 4. Section 4.4, the call-site pattern, is Task 4. Section 4.5, the browser-process smoke check, is Task 5. Section 5, worker parity, is covered structurally by the choice of `NavigatorBase` in Task 4 and asserted in Task 6. All six of Section 6's verification criteria are Task 6, with criterion 1 as its Step 3. Section 7's open decisions are settled: the smoke check goes in `BrowserMainLoop::EarlyInitialization` (Task 5), `ConfigScope` is a class (Task 3), and the key registry stays absent (SP6a owns it). Section 8's exclusions are respected — no per-context store, no coherence validation, no key registry, one surface.

One thing the spec did not anticipate and this plan resolves: `NavigatorConcurrentHardware::hardwareConcurrency()` takes no arguments and cannot supply an `ExecutionContext`, so the spec's own call-site pattern was unimplementable at the location it named. Overriding in `NavigatorBase` fixes it and improves worker parity from a thing to test into a thing that cannot break. The spec should be amended to match.

**Placeholder scan.** No TBD, TODO, "similar to Task N", or "add appropriate error handling". Every code step contains the code. Two steps depend on output that must be read rather than assumed — Task 4 Step 1 confirms which base supplies `GetExecutionContext()`, and Task 6 Step 4's `window keys unchanged` assertion compares against a stock build — and both state the expected output and what to do if it differs.

**Type consistency.** `EnvGetter` is `base::FunctionRef<std::optional<std::string>(const std::string&)>` in Task 1 and is used with that exact signature in Task 3's `Config()`. `AssembleRawConfig` returns `std::string` and `ParseConfig` takes `std::string_view`; the conversion is implicit and correct. `GetUint32` returns `std::optional<uint32_t>` in Task 3 and is consumed as such in Task 4. `hardwareConcurrency()` returns `unsigned` in both the mixin and the override, matching the base declaration probed from the real header.
