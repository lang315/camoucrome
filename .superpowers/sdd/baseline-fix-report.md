# Stale SP1a baseline after SP2a — fix report

Chromium checkout: `/home/lang/chromium/src`, commit `70cb99fedc` (SP2a applied, already
built — no rebuild needed for this task). Camoucrome repo:
`/Users/lang/GolandProjects/github.com/lang315/camoucrome`, base commit `797de05`.

## What was actually failing, confirmed before touching anything

Ran `verify_sp1a_chrome.py` against the SP2a binary with the pre-SP2a baseline still in
place:

```
FAIL  1 spoofed UA leaves the product token untouched
FAIL  1 spoofed UA reports the build's own version
FAIL  8 unconfigured UA is byte-identical to the baseline
FAIL  8 unconfigured request headers match the baseline
30 PASS / 4 FAIL, EXIT:1
```

Two more than the one criterion the task description named. Root cause traced in
`components/embedder_support/user_agent_utils.cc`: SP2a's `GetUserAgentInternal()` change
strips `Headless` **unconditionally** — on the unconfigured path too, not only the spoofed
one — so the pre-SP2a baseline's `HeadlessChrome/154.0.0.0` string is wrong for **every**
comparison that touches the product token, not just the one the task called out.
`"1 spoofed UA reports the build's own version"` does `base_token in ua`, a literal
substring test, so it fails outright rather than partially. `"8 unconfigured UA is
byte-identical"` and `"8 unconfigured request headers match"` fail for the same reason:
`CHROME_FLAGS` (`lib_shell.py:64`) always passes `--headless`, so the unconfigured session
was headless too, both when the baseline was captured and now.

## Design choice: refuse on stale provenance (Option B), not rename-for-visibility (Option A)

Chose: extend `capture_ua_baseline.py`'s existing provenance record and add a reader for
it in `verify_sp1a_chrome.py`'s `load_baseline()` that refuses to run any baseline
comparison when the checkout has moved since capture, rather than comparing against
stale data.

This needed less new machinery than it sounds: `capture_ua_baseline.py` already writes
`provenance.captured_at_commit`, derived from `git -C ~/chromium/src rev-parse --short
HEAD` at capture time — nothing was asserted, it already reads the checkout the same way
I needed to. What was missing was a reader on the verify side. Confirmed on the build
machine that Camoucrome patches land in that checkout as real git commits (`git log`
shows `b04b4e77f4 sp2a: suppress the HeadlessChrome product token unconditionally` etc.,
`git status` clean) — so the checkout's HEAD is not a proxy for "what patches are
applied," it *is* the applied patch set, verifiable the same way at both capture and
verify time.

`load_baseline()` now also requires `provenance` among the baseline's keys, reads the
checkout's current commit the same way `current_checkout_commit()` reads it (mirrors
`capture_ua_baseline.py`'s subprocess call exactly, same guarded try/except), and returns
a `RuntimeError` — routed through the existing `baseline_err` plumbing used at all four
of the file's baseline-consumption sites — naming both commits and the exact recapture
command, if they don't match.

**Rejected: Option A (encode fork state in the baseline's filename/identity).** Renaming
`chrome-0e8d4a9268-stock-ua.json` to something carrying a Camoucrome commit or patch-set
hash would only make staleness visible to a human who happens to read the filename; it
adds no check, so a future SP that changes unconfigured output would still pass this file
silently until someone noticed the name looked wrong — the exact failure mode this task
exists to close. It would also break with this project's existing (inconsistent) naming:
one tracked baseline is named for the Chromium base revision
(`content_shell-0e8d4a9268-stock.json`), another for a fork milestone
(`content_shell-sp0-stock-ua.json`) — unifying that convention is a separate, cosmetic
concern this task doesn't need to take on. Left the filename alone; the field that
actually carries freshness now is `provenance.captured_at_commit`, checked by code, not
the name.

I did not rebuild anything — the checkout was already built with SP2a, matching the task
brief.

## Comments updated

- `verify_sp1a_chrome.py:127-139` (`product_token()` docstring) — no longer cites
  `user_agent_utils.cc:218`'s now-deleted `product.insert(0, "Headless")` as a live fact.
  States that SP2a removed it unconditionally, so `product_token()`'s tokens are now
  plain `Chrome/<version>`, and explains the `in`-not-`startswith` choice is kept for
  forward compatibility with a prefix that might reappear, not for a prefix that exists
  today.
- `verify_sp1a_chrome.py:285-...` (the criterion-1 "KNOWN GAP" comment) — rewritten past
  tense: records that SP2a (`b04b4e77f4`) closed the gap, names what the assertion still
  guards (SP1a must never start touching the product token), and explains that
  `load_baseline()`'s new provenance refusal is what keeps this comparison trustworthy
  going forward rather than merely currently-passing.

## Baseline recaptured

```
$ ./venv/bin/python3 capture_ua_baseline.py --shell /home/lang/chromium/src/out/Default/chrome \
    > baselines/chrome-0e8d4a9268-stock-ua.json
```

Before → after (the only fields that changed):

| field | before | after |
|---|---|---|
| `user_agent` | `...HeadlessChrome/154.0.0.0...` | `...Chrome/154.0.0.0...` |
| `provenance.captured_at_commit` | `0e8d4a9268` | `70cb99fedc` |

`platform`, `mobile`, `brands`, `high_entropy`, `*_keys`, `known_absent` unchanged.
SHA256 `6fe9540a037fd2e98e839675d247b854a3b8b70ea7ec3b3d4decb325965e1173`, verified
identical between the WSL box, this repo's working tree, and
`~/camoucrome-verify/baselines/` after transfer (all three `sha256sum` outputs matched
before commit).

## Task 3 — no other consumer of a pre-SP2a value

Grepped every `verify_*.py` and `baselines/` for baseline usage:

- `verify_sp0.py`, `verify_sp1a.py`, `verify_sp5a.py` read `content_shell-0e8d4a9268-stock.json`
  / `content_shell-sp0-stock-ua.json` — both `content_shell`, never `chrome`.
- `verify_sp2.py` reads no baseline file at all (self-contained, compares live sessions).
- Only `verify_sp1a_chrome.py` reads `chrome-0e8d4a9268-stock-ua.json`.

Confirmed in source, not inferred from the docstring: `content/shell/browser/
shell_content_browser_client.cc:732 ShellContentBrowserClient::GetUserAgent()` builds its
own product string (`base::StringPrintf("Chrome/%s.0.0.0", CONTENT_SHELL_MAJOR_VERSION)`)
and calls `BuildUnifiedPlatformUserAgentFromProduct()` directly — grepping that file for
`GetUserAgentInternal` and `embedder_support::GetUserAgent` returns nothing. SP2a's patch
touches only `GetUserAgentInternal()`. content_shell's UA path never reaches it, so its
two tracked baselines are unaffected and need no recapture.

## Verification

Staged the fixed `verify_sp1a_chrome.py` and the recaptured baseline onto the build
machine (base64, 3 chunks for the script — the single-file transfer silently failed once
at ~34KB and was caught by a post-transfer `sha256sum`/`py_compile` check, matching the
project's own "verify what actually landed" discipline), then ran:

```
$ ./venv/bin/python3 verify_sp1a_chrome.py
[... 34 lines, all PASS ...]
EXIT:0
```

34 PASS, exit 0 — matches the suite table; no criteria moved.

**Staleness guard, made to fail on purpose:** mutated the deployed baseline's
`provenance.captured_at_commit` from `70cb99fedc` back to `0e8d4a9268` (simulating a
baseline that predates the current checkout) and re-ran:

```
FAIL  1 spoofed UA carries no Linux token
[... every baseline-dependent assertion FAILs ...]
      baseline load from .../chrome-0e8d4a9268-stock-ua.json: RuntimeError: baseline is
      stale: captured at checkout commit '0e8d4a9268', but the checkout at
      /home/lang/chromium/src is now at '70cb99fedc'. A patch has landed since capture
      that may have changed the unconfigured build's output -- exactly what SP2a's
      HeadlessChrome removal did. Recapture with: python3 capture_ua_baseline.py --shell
      /home/lang/chromium/src/out/Default/chrome > .../chrome-0e8d4a9268-stock-ua.json
EXIT:1
```

The named message appears once per baseline-consumption site (four), and every assertion
that depends on the baseline fails rather than a subset — deliberate: once the baseline
can't be trusted, nothing derived from it should read as evidence, including the
assertions that happened not to touch the changed field. Restored the file
(`sha256sum` confirmed byte-identical to the committed version) and reran: back to 34
PASS, exit 0.

Unchanged suites, all still green:

```
verify_sp2.py   PASS=9  FAIL=0 EXIT=0
verify_sp0.py   PASS=11 FAIL=0 EXIT=0
verify_sp1a.py  PASS=9  FAIL=0 EXIT=0
verify_sp5a.py  PASS=4  FAIL=0 EXIT=0
```

## Disagreement / open item

None with the framing. The task predicted one broken criterion; three more were broken
by the same root cause and are fixed by the same recapture + guard — worth flagging
since a narrower fix (patching only the named criterion's comparison) would have left
two `"8 unconfigured..."` assertions red.
