# SP0 — Config layer and tracer-bullet surface

Assumes the decisions in [00-conventions.md](00-conventions.md).

## 1. Goal

Give every future sub-project one way to ask "what should this value be?" from any
Chromium process, and prove that path works end to end by driving a single real
surface through it. After SP0, adding a spoofed surface is a matter of finding the
call site and adding a config lookup — the plumbing question is settled once.

The tracer surface is `navigator.hardwareConcurrency`. It was chosen because it has a
single call site, its correct value is a small integer that is trivial to assert, and
it is exposed to both windows and workers, so it exercises the worker-parity rule on
the very first surface rather than deferring that discovery.

## 2. Depends on

Nothing. SP0 is the foundation; every other SP depends on it.

## 3. Surfaces

| Value | Config key | Chromium location | Process |
|---|---|---|---|
| `navigator.hardwareConcurrency` | `navigator.hardwareConcurrency` | `third_party/blink/renderer/core/execution_context/navigator_base.cc` | renderer |
| `WorkerNavigator.hardwareConcurrency` | same key | same override, inherited | renderer (worker) |
| parsed-key count at startup | — (diagnostic only) | `content/browser/browser_main_loop.cc` | browser |

**Correction from implementation planning.** This spec originally named
`core/frame/navigator_concurrent_hardware.cc`. That location is unusable:
`NavigatorConcurrentHardware::hardwareConcurrency()` takes no arguments and is a bare
mixin with no access to an `ExecutionContext`, so the scope-shaped API this whole SP
exists to establish could not be exercised there at all.

The method is `virtual`, and `NavigatorBase`
(`core/execution_context/navigator_base.h:41`, verified) inherits the mixin, lives in
the execution-context directory, and is the common base of both `Navigator` and
`WorkerNavigator`. Overriding there gives the lookup a real execution context to scope
by, and makes window-and-worker agreement structural rather than something a separate
mechanism has to maintain. Section 5's parity requirement is satisfied by construction.

This is exactly what a tracer bullet is for: the first surface found the flaw in the
pattern before twenty surfaces had copied it.

## 4. Design

### 4.1 Component

A new GN target `//components/camoucfg/` containing `mask_config.h`,
`mask_config.cc`, `blink_scope.h`, `mask_config_unittest.cc`, and `BUILD.gn`. It
depends only on `//base`. It is added to the allowlist in
`third_party/blink/renderer/DEPS` with the single line `"+components/camoucfg",` so
Blink code may include it directly.

Placing the component under `//components` rather than inside Blink is the decision
that lets SP1 and SP3 reuse it. SP1 needs the browser process, because Chromium emits
`Sec-CH-UA*` headers from `components/embedder_support/user_agent_utils.cc`; SP3 may
need the GPU process, because the true WebGL vendor and renderer strings originate in
`gpu::GPUInfo`. A Blink-only config layer would force both to grow a duplicate.

### 4.2 Reading and parsing

On first access within a process, the component reads `CAMOU_CONFIG_1`,
`CAMOU_CONFIG_2`, and so on, stopping at the first index that is absent, and
concatenates the values in order. If no numbered variable exists it falls back to a
single `CAMOU_CONFIG`. The chunking exists because Windows caps one environment
variable near 32KB and a full fingerprint exceeds that; Camoufox solved it the same
way, and matching its transport byte-for-byte is what allows Camoufox's Python
generator to drive Camoucrome later without a rewrite.

The concatenated string is parsed with `base::JSONReader` into a `base::Value::Dict`
stored in a function-local `base::NoDestructor`, initialised under a thread-safe
static so parsing happens exactly once per process. Chromium already ships a JSON
parser, so unlike Camoufox no third-party library is vendored.

On Windows the environment must be read as UTF-16 and converted, not through the
narrow `getenv`, or non-ASCII values in a fingerprint (a font name, a locale) are
corrupted. Camoufox hit this and uses `GetEnvironmentVariableW`; `base::Environment`
handles it on Chromium's behalf.

### 4.3 API

```cpp
namespace camoucfg {

class ConfigScope;                       // opaque; SP0 has exactly one instance
const ConfigScope& GlobalScope();

std::optional<std::string> GetString(const ConfigScope&, std::string_view key);
std::optional<uint32_t>    GetUint32(const ConfigScope&, std::string_view key);
std::optional<int32_t>     GetInt32 (const ConfigScope&, std::string_view key);
std::optional<double>      GetDouble(const ConfigScope&, std::string_view key);
std::optional<bool>        GetBool  (const ConfigScope&, std::string_view key);
std::vector<std::string>   GetStringList(const ConfigScope&, std::string_view key);
bool HasKey(const ConfigScope&, std::string_view key);

}  // namespace camoucfg
```

`blink_scope.h` supplies `const camoucfg::ConfigScope& ScopeFor(blink::ExecutionContext*)`,
which in SP0 ignores its argument and returns `GlobalScope()`. It lives in the
component rather than in Blink so that Blink call sites need exactly one include.

The scope parameter is the whole point of the API's shape. Every call site is written
as `camoucfg::GetUint32(ScopeFor(GetExecutionContext()), "navigator.hardwareConcurrency")`.
When a per-context backing store is introduced — pushed from the browser process over
Mojo, or set through a CDP command — only `ScopeFor` and the store change. No call site
moves. Camoufox reached the same conclusion by a harder route: its spoofing patches
each grew a per-BrowsingContext `*Manager` class, and its issue #57 (per-context
timezone not working) is what a global-only config costs when the requirement arrives
later.

Getters deliberately return `std::optional` rather than taking a default. Forcing the
caller to write the fallback keeps the real value visible at the call site, which is
what a reviewer needs to see.

### 4.4 Call-site pattern

`NavigatorConcurrentHardware::hardwareConcurrency()` currently returns
`base::SysInfo::NumberOfProcessors()`. `NavigatorBase` gains an override that consults
the configuration and falls back to that same expression when the key is absent. This
two-line shape — look up, fall back to the *original expression* rather than to a
constant — is the pattern every later SP repeats, and copying the real expression
verbatim is what keeps a stock run honest.

### 4.5 Browser-process smoke check

A single `VLOG` at browser startup reports how many keys parsed. It spoofs nothing.
Its only job is to prove the component initialises correctly outside the renderer
before SP1 depends on that, and it costs about five lines. It stays behind the debug
flag afterwards rather than being deleted, because "did my config reach the browser
process" is a question that will recur.

## 5. Coherence constraints

SP0 controls one surface, so cross-surface coherence does not yet apply. One
intra-surface invariant does: the window and any worker must report the same value.
This is the first instance of conventions rule 3, and it is worth catching here
because the machinery that guarantees it — a single parse shared by every execution
context in the process — is exactly what SP0 is building. Camoufox needed a dedicated
patch (`cross-process-storage.patch`, sync IPC for `roverfox.*` prefs) to make seeds
agree across content and worker processes; verifying parity at SP0 confirms
Camoucrome does not inherit that problem.

## 6. Verification

Each item is independently runnable. Build target is `content_shell` in `out/Default`.

1. **Unit tests** — `mask_config_unittest.cc` covers: chunks concatenate in index
   order; a gap in the numbering stops collection; the unnumbered `CAMOU_CONFIG`
   fallback works; malformed JSON yields an empty config; malformed JSON with
   `CAMOU_CONFIG_STRICT=1` aborts; a key of the wrong type returns `nullopt` and logs;
   an absent key returns `nullopt` silently. Run with
   `autoninja -C out/Default components_unittests` and the matching gtest filter.

2. **Spoofed value** — launch with
   `CAMOU_CONFIG='{"navigator.hardwareConcurrency":8}'` and evaluate
   `navigator.hardwareConcurrency` over the DevTools protocol. Expected: `8`.

3. **Fallback** — launch with no `CAMOU_CONFIG` set. Expected: `16`, the real logical
   processor count of the build machine. This is the check that catches a spoof which
   silently replaces the real value with a constant.

4. **Native accessor** — evaluate
   `Object.getOwnPropertyDescriptor(Navigator.prototype,'hardwareConcurrency').get.toString()`.
   Expected: a string containing `[native code]`. Then diff `Object.keys(window)` and
   `Object.getOwnPropertyNames(Navigator.prototype)` against a stock `content_shell`
   built from the same revision. Expected: no difference. This is the check that would
   fail if the value were injected from JavaScript instead of C++, and it is the single
   most important assertion in SP0.

5. **Worker parity** — from the same page, construct a `Worker` that posts back
   `navigator.hardwareConcurrency`. Expected: the same value the window reports, in
   both the spoofed and the fallback case.

6. **Malformed config does not crash** — launch with
   `CAMOU_CONFIG='{not json'` and without the strict flag. Expected: the browser
   starts, one error is logged, `navigator.hardwareConcurrency` reports the real `16`,
   and no renderer crashes. A crash on bad input would itself be a fingerprint.

## 7. Open decisions

**Where the browser-process smoke check is installed.** `content/browser/browser_main_loop.cc`
is the obvious host but has not been read yet; a `//components`-level init hook may be
tidier. Low stakes, decide during implementation.

**Whether `ConfigScope` should be a class or an enum-like token in SP0.** A class costs
nothing now and gives the per-context store somewhere to hang state later. An
alternative is a plain opaque integer handle, which is cheaper to pass but harder to
extend. Recommendation: class, because the extension is a known requirement rather
than a speculative one.

**Where the key registry lives.** SP0 has one key and needs no registry. SP6a owns
`settings/keys.json`, from which both the C++ constants and the client's validation
table are generated. Until it exists, keys are string literals at call sites —
acceptable for one key and not for twenty, which is why the amended sub-project map
places SP6a immediately after SP0 and before SP1. SP5a's `settings/invariants.json` is
a different file with a different job; neither subsumes the other.

## 8. Explicitly out of scope

No per-context override channel: the API is shaped for one, and no Mojo interface,
CDP command, or per-context store is implemented. No coherence validation. No key
registry or config schema validation. No surface other than
`hardwareConcurrency` — in particular `navigator.webdriver` belongs to SP2, and the
rest of the navigator identity block to SP1.
