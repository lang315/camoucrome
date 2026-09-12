# Windows behaviour Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** `navigator.share()` under a Windows/macOS claim behaves like a dismissed share sheet instead of killing the renderer; voices follow the claimed locale.

**Architecture:** one new patch stem `windows-behaviour` (a Linux `ShareService` stub in `chrome_browser_interface_binders.cc` + the `//components/camoucfg` dep/DEPS for `chrome/browser`), one new key `share:cancelMs`, a per-locale `settings/voices.json`, generator + tests, one verify with a measured RED.

**Tech Stack:** Chromium 153 pin, camoucfg getters, patchright client, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-09-12-windows-behaviour-design.md`.
- Binary under test is `out/Default/chrome` (content_shell has no `chrome/browser` binders).
- Never open the share sheet on the user's Windows host.
- Export, never hand-extract: commit on the box with subject `windows-behaviour`, then `export.sh`.

---

### Task 1: key, voices table, generator, tests (Mac)

**Files:** `settings/keys.json`, `additions/camoucfg/keys.h` (generated), `additions/camoucfg/keys_unittest.cc`, `settings/voices.json`, `client/python/camoucrome/gen.py`, `client/python/tests/test_gen.py`.

- [x] Add `kShareCancelMs` / `share:cancelMs` (int32); `gen_keys.py`; `declared` set.
- [x] Rewrite `voices.json` as `{"$comment", "measured": ["en-US"], "Windows": {tag: [voice...]}}`, 49 tags from Appendix A, OneCore token strings verbatim.
- [x] `voices_keys(platform, locale)` with the fallback rule; `from_pool` passes the locale tag and emits `share:cancelMs` in 900–2600 for Windows/macOS.
- [x] `test_voices_follow_the_locale_and_share_cancel_is_human_paced`; `pytest client/python/tests` green; `gen_keys.py --check` PASS.

### Task 2: the Linux ShareService stub (box)

**Files (patch `windows-behaviour`):** `chrome/browser/chrome_browser_interface_binders.cc`, `chrome/browser/BUILD.gn`, `chrome/browser/DEPS`.

- [x] Widen the webshare mojom include guard to `IS_LINUX`; add `#include "components/camoucfg/keys.h"`, `mask_config.h`, `base/task/single_thread_task_runner.h`, `base/time/time.h`, `content/public/browser/document_service.h`.
- [x] In the anonymous namespace, under `#if BUILDFLAG(IS_LINUX)`:

```cpp
// windows-behaviour: a Windows/macOS claim exposes navigator.share (the
// renderer gate in ChromeContentRendererClient); Linux has no ShareService
// binder, and a frame asking the broker for an unbound interface is killed
// (ReportNoBinderForInterface -> ReportBadMessage). This stub answers as a
// dismissed share sheet does on both real hosts: ShareError::CANCELED after
// share:cancelMs (absent -> at once), which Blink reports as AbortError
// "Share canceled". Unreachable under a Linux claim (share is undefined).
class CamouShareServiceStub
    : public content::DocumentService<blink::mojom::ShareService> {
 public:
  static void Create(content::RenderFrameHost* host,
                     mojo::PendingReceiver<blink::mojom::ShareService> receiver) {
    CHECK(host);
    new CamouShareServiceStub(*host, std::move(receiver));
  }
  void Share(const std::string& title, const std::string& text, const GURL& url,
             std::vector<blink::mojom::SharedFilePtr> files,
             ShareCallback callback) override {
    int32_t ms = camoucfg::GetInt32(camoucfg::GlobalScope(),
                                    camoucfg::keys::kShareCancelMs).value_or(0);
    ms = std::clamp(ms, 0, 60000);
    base::SingleThreadTaskRunner::GetCurrentDefault()->PostDelayedTask(
        FROM_HERE,
        base::BindOnce(std::move(callback), blink::mojom::ShareError::CANCELED),
        base::Milliseconds(ms));
  }
 private:
  CamouShareServiceStub(content::RenderFrameHost& host,
                        mojo::PendingReceiver<blink::mojom::ShareService> receiver)
      : content::DocumentService<blink::mojom::ShareService>(host, std::move(receiver)) {}
};
#endif
```

- [x] Register beside the platform binders: `#if BUILDFLAG(IS_LINUX) map->Add<blink::mojom::ShareService>(&CamouShareServiceStub::Create); #endif`.
- [x] `chrome/browser/BUILD.gn`: `"//components/camoucfg",` in the `browser` target deps (next to `//components/embedder_support`); `chrome/browser/DEPS`: `"+components/camoucfg",`.
- [x] Push `keys.h`, `keys_unittest.cc` to `components/camoucfg/`; `autoninja -C out/Default chrome components_unittests` (non-zero steps); `gn check out/Default //chrome/browser:browser`; `checkdeps.py chrome/browser`.

### Task 3: verify (RED first)

**Files:** `scripts/verify_windows_behaviour.py`.

- [x] Rows S1–S4, V1–V2 per the spec §5; S1's RED is the pre-fix "Target crashed" line (already measured, recorded in the doc). Run on the box: 7/7 (S1b: two gestures in one page see different delays — the per-call jitter).
- [x] Regressions: `verify_host_oracle.py` 4/4, `verify_sp4_voices.py` 5/5, `CamoucfgKeysTest`, `verify_sp6b_generator.py` N=3.

### Task 4: export, docs, eighth cut

- [x] Commit on the box (`windows-behaviour`), `export.sh`, gate empty, `check_checkout_sync.sh`, `check_additions_build.py`.
- [x] Docs: measurement `2026-09-12-windows-behaviour.md`; erratum lines in the windows-oracle and packaging docs (seventh cut kills the renderer on `share()`); sp4-voices §4 superseded; roadmap row 8c; conventions catalogue rule (claim-gated interface needs a build-OS binder); CLAUDE.md layout line; sp5b catalogue if a key row table exists.
- [x] Release relink (`job_release.sh`), `package.py`, `post_pkg.sh`; oracle 4/4 + S1–S4 on the archived chrome; packaging doc eighth cut; commit, push, CI.
