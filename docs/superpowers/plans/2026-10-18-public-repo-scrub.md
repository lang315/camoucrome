# Public Repo Scrub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove host-identifying data from the whole public history and from GitHub's side by rewriting history and recreating the repository, and add the rules and gates that keep it out.

**Architecture:** First, tooling lands on the branch `privacy-scrub` under TDD:
- `scripts/check_privacy.py`, the gate, with its hooks and its CI step;
- capture scripts that write placeholders.

It is reviewed before anything irreversible. Then comes a one-off operation, each step closed by a measured check:
1. a raw local backup;
2. untracked rule files;
3. a `git-filter-repo` rewrite in a scratch clone;
4. a scrubbed archive of the PRs and runs;
5. deleting and recreating the GitHub repository;
6. restoring its settings and the runner;
7. syncing the clones.

**Tech Stack:** Python 3 (stdlib only), git 2.56, git-filter-repo, `gh`, GitHub Actions, sshgate to the build box (PowerShell outside, `wsl -u <user>` / `wsl -d Ubuntu-24.04 -u root` inside).

**Spec:** `docs/superpowers/specs/2026-10-18-public-repo-scrub-design.md`

## Global Constraints

- This plan, the spec and every committed file name categories and placeholders only. A literal value to remove never appears in a committed file, a commit message, a PR body or a CI log.
- Untracked private files, never committed and never copied off the Mac:
  - `~/.config/camoucrome/private-terms.json`: `{placeholder: [strings]}`, the `CAMOU_SCRUB` shape;
  - `~/.config/camoucrome/scrub-rules.txt`: `git-filter-repo` replace-text format;
  - `~/Backups/camoucrome-github-2026-10-18/`: the raw export and the bundle.
- Placeholders:

  | value | placeholder |
  |---|---|
  | host zone name | `<host-tz>` |
  | host zone's display name | `<host-tz-name>` |
  | host offset strings | `<host-offset>` |
  | Windows profile directory | `user.HOST` |
  | machine name | `HOST` |
  | tailnet IP | `<box-tailnet-ip>` |
  | WSL IP | `<wsl-ip>` |
  | home paths | `~/` |
  | city | `<host-city>` |
  | country | `<host-country>` |
  | ISP | `<host-isp>` |
  | session URLs | `<removed>` |

- Times written into the repository are UTC, as `HH:MM UTC`. So are `YYYYMMDD-HHMMSS` stamps in names (spec §6.5).
- Every commit is made as `TZ=UTC git commit -F <file>`, and its date carries `+0000`.
- Commit identity is the repository config (`Lãng <30039912+lang315@users.noreply.github.com>`), never the session's email.
- Product data stays: `settings/locale_zones.json`, `settings/voices.json` and `settings/invariants.json`.
- The GitHub account name `lang315` stays.
- Kept branches: `main`, `e-fb-auto` and `repin/8078-prep`. No other branch is pushed to the new repository.
- **The owner gates (stop and ask):**
  - the `delete_repo` scope refresh;
  - the typed `delete` before Task 9;
  - any clone with uncommitted work;
  - any sudo the box needs beyond `wsl -u root`.
- Never touch `D:\camou-win\camoucrome`, `~/chromium-s2c`, `~/s2c-*` or `observe-backup`.
- No `git gc` or prune. Never break another holder's `build_lock`.
- Commit message files end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. They carry no `Claude-Session` trailer.

## Rulings carried from the spec

- **The private-terms file is JSON in the `CAMOU_SCRUB` shape** (`private-terms.json`), not one regex per line. `scripts/step2_rows.scrub` already takes that shape, so one file feeds the gate, the capture scripts and `measure_step2.py scrub`. Task 2 updates the spec line.
- **No generic `UTC±N` / `GMT±N` pattern.** The measurement data legitimately holds the offsets of the identities the fork emulates (for example a `GMT-0600` `date0`). The host's own offset strings go in the private terms instead. Task 2 updates the spec line.
- ~~Commits made by GitHub are exempt from the date-offset check.~~ Reversed after the Task 4 review: all 40 GitHub-made merges carried the owner's offset. There is no exemption, and PRs are merged locally with `TZ=UTC` (owner, 2026-10-18). The code shipped in Tasks 1 to 3, after the Task 4 fix pass, supersedes the code embedded below where they differ: `GATE_FILES`, `--ci`, `--require-terms`, path checks, wider home-path patterns, and `capture_host_oracle --raw-out/--from-raw`.
- **The tooling review runs after Task 3**, not at the end. Tasks 5 to 11 are irreversible operations, and their gates are measured checks, not code.

## Review Focus

1. **A GitHub-made merge commit in a pushed range.** It carries the owner's offset, so the gate must fail it. PRs are merged locally in UTC. Pinned by `test_range_refuses_a_github_made_commit_with_an_offset` (Task 4 fix pass).
2. **CI without the secret** (fork PRs, or a secret not yet set). `PRIVATE_TERMS` is the empty string, and the gate must still run the generic patterns. Pinned by `test_empty_private_terms_still_runs_generic` (Task 1).
3. **A hit reaches a public log.** The gate's output must never contain the matched text. Pinned by `test_output_never_contains_the_matched_text` (Task 1).
4. **A lower-case or mixed-case private term** (detector pages print a city in lower case). Pinned by the `near plantville` row of `test_each_category_is_caught` (Task 1).
5. **A capture script that runs without private terms, or a new host value the terms do not cover.** It must refuse to write, not write the raw value. Pinned by `test_committable_refuses_without_terms` and `test_committable_refuses_a_leftover_hit` (Task 3).

---

### Task 1: `scripts/check_privacy.py`, the gate

**Files:**
- Create: `scripts/check_privacy.py`
- Test: `scripts/test_check_privacy.py`

**Interfaces:**
- Produces:
  - `load_terms() -> dict[str, list[str]]`. It reads `$PRIVATE_TERMS` when the variable is set (the empty string means none); otherwise `~/.config/camoucrome/private-terms.json` when it exists; otherwise `{}`.
  - `hits(text: str, terms: dict) -> list[tuple[int, str]]`: sorted unique `(line number, category)`.
  - `main(argv=None) -> int`, with the modes default (tracked files), `--staged`, `--file PATH`, `--range REVS` and `--history`. It returns 0 when clean and 1 on any hit.
  - Constants `ALLOW_PATHS`, `ALLOW_IPS` and `GENERIC`.

- [ ] **Step 1: Write the failing tests**

```python
"""check_privacy: every category caught, clean text passes, and no matched value is ever printed."""
import json
import os
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_privacy as cp  # noqa: E402

TERMS = {"<host-place>": ["Plantville"], "<host-offset>": ["GMT+0999"]}


@pytest.mark.parametrize("line,cat", [
    ("built on DESKTOP-AB12CD3 today", "machine-name"),
    (r"C:\Users\someone.BOX\AppData\Local", "windows-profile"),
    ("file:///C:/Users/someone/AppData/x.html", "windows-profile"),
    ("cd /home/someone/chromium/src", "home-path"),
    ("open /Users/someone/Go/x", "home-path"),
    ("memory at ~/.claude/projects/-Users-someone-Go-x/memory", "home-slug"),
    ("box at mybox.tail1234.ts.net", "tailnet"),
    ("Claude-Session: <removed>", "session-link"),
    ("ran 16:03-16:37 XST on the host", "local-clock"),
    ("peer 100.101.102.103 up", "ip"),
    ("wsl at 172.20.1.9", "ip"),
    ("near Plantville", "<host-place>"),
    ("near plantville", "<host-place>"),
    ("date0 GMT+0999 (x)", "<host-offset>"),
])
def test_each_category_is_caught(line, cat):
    assert (1, cat) in cp.hits(line, TERMS)


@pytest.mark.parametrize("line", [
    "Chrome/154.0.0.0 and 154.0.8037.93 and 156.0.8078.36",
    "doc address 203.0.113.7, 127.0.0.1 and 0.0.0.0:54021",
    "fake webrtc ip 192.168.1.37",
    "~/chromium/src, $HOME/x, /home/runner/work and /home/<user>/x",
    r"C:\Users\user.HOST\AppData and C:\Users\<user>",
    "file:///C:/Users/user.HOST/AppData/x.html",
    "at 22:28 UTC; Thu Jan 01 1970 00:00:00 GMT+0000",
    "Wed Dec 31 1969 18:00:00 GMT-0600 (Central Standard Time)",
])
def test_clean_lines_pass(line):
    assert cp.hits(line, TERMS) == []


def git(repo, *a, tz="UTC", check=True):
    env = dict(os.environ, TZ=tz, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    return subprocess.run(["git", "-C", str(repo), *a], env=env, capture_output=True, text=True, check=check)


def commit(repo, path, data, msg="m", tz="UTC", env_extra=None):
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data if isinstance(data, bytes) else data.encode())
    git(repo, "add", path)
    return git(repo, "commit", "-q", "-m", msg, tz=tz)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps(TERMS))
    return tmp_path


def test_tracked_clean_passes(repo):
    commit(repo, "a.md", "nothing here\n")
    assert cp.main([]) == 0


def test_output_never_contains_the_matched_text(repo, capsys):
    commit(repo, "a.md", "line one\nnear Plantville on DESKTOP-AB12CD3\n")
    assert cp.main([]) == 1
    out = capsys.readouterr()
    assert "a.md:2: <host-place>" in out.out and "a.md:2: machine-name" in out.out
    assert "Plantville" not in out.out + out.err and "AB12CD3" not in out.out + out.err


def test_allowlisted_product_file_passes(repo):
    commit(repo, "settings/locale_zones.json", '{"x": "Plantville"}\n')
    assert cp.main([]) == 0


def test_binary_file_is_skipped(repo):
    commit(repo, "b.bin", b"\0\0DESKTOP-AB12CD3")
    assert cp.main([]) == 0


def test_staged_checks_the_index(repo):
    commit(repo, "a.md", "clean\n")
    (repo / "a.md").write_text("near Plantville\n")
    git(repo, "add", "a.md")
    assert cp.main(["--staged"]) == 1


def test_file_mode(repo, tmp_path):
    body = tmp_path / "body.md"
    body.write_text("see <removed>\n")
    assert cp.main(["--file", str(body)]) == 1


def test_range_refuses_a_non_utc_commit(repo, capsys):
    commit(repo, "a.md", "clean\n", tz="Etc/GMT-5")
    assert cp.main(["--range", "HEAD"]) == 1
    assert "date offset" in capsys.readouterr().out


def test_range_checks_messages(repo):
    commit(repo, "a.md", "clean\n", msg="x\n\nClaude-Session: <removed>")
    assert cp.main(["--range", "HEAD"]) == 1


def test_range_passes_a_clean_utc_commit(repo):
    commit(repo, "a.md", "clean\n")
    assert cp.main(["--range", "HEAD"]) == 0


def test_range_exempts_github_made_commits(repo):
    commit(repo, "a.md", "clean\n")
    env = dict(os.environ, TZ="Etc/GMT-5", GIT_AUTHOR_NAME="GitHub", GIT_AUTHOR_EMAIL="noreply@github.com",
               GIT_COMMITTER_NAME="GitHub", GIT_COMMITTER_EMAIL="noreply@github.com")
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "Merge pull request #1"], env=env, check=True)
    assert cp.main(["--range", "HEAD"]) == 0


def test_history_finds_a_term_removed_at_the_tip(repo):
    commit(repo, "a.md", "near Plantville\n")
    commit(repo, "a.md", "clean\n")
    assert cp.main([]) == 0
    assert cp.main(["--history"]) == 1


def test_empty_private_terms_still_runs_generic(repo, monkeypatch):
    monkeypatch.setenv("PRIVATE_TERMS", "")
    commit(repo, "a.md", "near Plantville\n")
    assert cp.main([]) == 0
    commit(repo, "b.md", "on DESKTOP-AB12CD3\n")
    assert cp.main([]) == 1


def test_bad_terms_shape_exits(monkeypatch):
    monkeypatch.setenv("PRIVATE_TERMS", '["x"]')
    with pytest.raises(SystemExit):
        cp.load_terms()
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `python3 -m pytest -q scripts/test_check_privacy.py`
Expected: collection error, `ModuleNotFoundError: No module named 'check_privacy'`.

- [ ] **Step 3: Write `scripts/check_privacy.py`**

```python
#!/usr/bin/env python3
"""Refuse host-identifying data in what this public repository publishes.

  check_privacy.py                  every tracked file in the working tree
  check_privacy.py --staged         the index (the pre-commit hook)
  check_privacy.py --file PATH      one file: a PR body, a comment, a commit message
  check_privacy.py --range REVS     messages and date offsets of `git rev-list REVS` (e.g. A..B, HEAD, --all)
  check_privacy.py --history        every blob reachable from every ref

Host-specific strings (zone names, offsets, machine and place names) come from $PRIVATE_TERMS, or
else ~/.config/camoucrome/private-terms.json, in CAMOU_SCRUB's shape {placeholder: [strings]};
neither is ever committed. A hit prints where and which category, never the matched text, so a CI
log does not re-publish it. Exit 1 on any hit.
"""
import argparse
import ipaddress
import json
import os
import pathlib
import re
import subprocess
import sys

# Product data: what the fork emulates, not the host (spec 2026-10-18 §1).
ALLOW_PATHS = {"settings/locale_zones.json", "settings/voices.json", "settings/invariants.json"}
# Addresses that are not the host's, each with where it comes from.
ALLOW_IPS = {
    "1.2.3.4": "placeholder address in the SP1a and SP4 plans",
    "192.168.1.37": "the configured fake webrtc:localipv4 (WebRTC II)",
    "156.0.1.1": "a version string in the step2 version tests",
    "205.185.123.167": "tls.peet.ws's own server address in scripts/fixtures/step2/peet.json",
}
GENERIC = {
    "machine-name": re.compile(r"\bDESKTOP-[A-Z0-9]{7}\b"),
    "windows-profile": re.compile(r"(?i)\bC:(?:\\{1,2}|/)Users(?:\\{1,2}|/)(?!<|user[.\\/]|public\b|default\b)[\w.-]+"),
    "home-path": re.compile(r"/(?:home|Users)/(?!<|runner/|user[./]|Shared/)[A-Za-z_][\w.-]*/"),
    "home-slug": re.compile(r"-(?:home|Users)-(?!<)[a-z][a-z0-9_]*-"),
    "tailnet": re.compile(r"\.ts\.net\b"),
    "session-link": re.compile(r"claude\.ai/code/session"),
    # a clock time labelled with a zone abbreviation other than UTC/GMT ("16:37 XST")
    "local-clock": re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s+(?!UTC\b|GMT\b)[A-Z]{2,4}T\b"),
}
_OCTET = r"(?:25[0-5]|2[0-4]\d|1?\d?\d)"
IPV4 = re.compile(rf"(?<![\d.]){_OCTET}(?:\.{_OCTET}){{3}}(?!\d|\.\d)")
DOC_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
GITHUB = b"noreply@github.com"


def load_terms():
    raw = os.environ.get("PRIVATE_TERMS")
    if raw is None:
        f = pathlib.Path(os.path.expanduser("~/.config/camoucrome/private-terms.json"))
        raw = f.read_text(encoding="utf-8") if f.exists() else ""
    terms = json.loads(raw) if raw.strip() else {}
    if not isinstance(terms, dict) or not all(isinstance(v, list) and all(isinstance(s, str) for s in v)
                                              for v in terms.values()):
        sys.exit("check_privacy: private terms must be a JSON object {placeholder: [strings]}")
    return terms


def _ip_hit(s):
    if re.fullmatch(r"\d+\.0\.0\.0", s) or s in ALLOW_IPS:  # a reduced UA version, or a known non-host address
        return False
    a = ipaddress.ip_address(s)
    return not (a.is_loopback or a.is_unspecified or a.is_multicast or a.is_reserved or a.is_link_local
                or any(a in n for n in DOC_NETS))


def hits(text, terms):
    needles = [(label, n.lower()) for label, ns in terms.items() for n in ns if n]
    out = set()
    for i, line in enumerate(text.splitlines(), 1):
        for cat, rx in GENERIC.items():
            if rx.search(line):
                out.add((i, cat))
        if any(_ip_hit(m.group(0)) for m in IPV4.finditer(line)):
            out.add((i, "ip"))
        low = line.lower()
        for label, n in needles:
            if n in low:
                out.add((i, label))
    return sorted(out)


def _git(*a, inp=None):
    return subprocess.run(["git", *a], input=inp, capture_output=True, check=True).stdout


def _text(data):
    return None if b"\0" in data[:8000] else data.decode("utf-8", "replace")


def _scan(paths, read, terms):
    bad = []
    for p in paths:
        if p in ALLOW_PATHS:
            continue
        t = _text(read(p))
        if t is not None:
            bad += [f"{p}:{i}: {c}" for i, c in hits(t, terms)]
    return bad


def _tracked(terms):
    paths = [p for p in _git("ls-files", "-z").decode().split("\0") if p and os.path.isfile(p)]
    return _scan(paths, lambda p: pathlib.Path(p).read_bytes(), terms)


def _staged(terms):
    paths = [p for p in _git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR").decode().split("\0") if p]
    return _scan(paths, lambda p: _git("show", f":{p}"), terms)


def _range(revs, terms):
    bad = []
    log = _git("log", "--format=%H%x00%ae%x00%ce%x00%ai%x00%ci%x00%B%x01", *revs.split())
    for rec in log.split(b"\x01"):
        rec = rec.strip(b"\n")
        if not rec:
            continue
        sha, ae, ce, ai, ci, msg = rec.split(b"\0", 5)
        s = sha.decode()[:10]
        if ce != GITHUB and not (ai.endswith(b"+0000") and ci.endswith(b"+0000")):
            bad.append(f"{s}: date offset not +0000 (commit with TZ=UTC)")
        bad += [f"{s}: message line {i}: {c}" for i, c in hits(msg.decode("utf-8", "replace"), terms)]
    return bad


def _history(terms):
    path_of = {}
    for line in _git("rev-list", "--objects", "--all").decode().splitlines():
        sha, _, p = line.partition(" ")
        if p:
            path_of.setdefault(sha, p)
    kinds = _git("cat-file", "--batch-check=%(objectname) %(objecttype)", inp="\n".join(path_of).encode()).decode()
    blobs = [k.split()[0] for k in kinds.splitlines() if k.endswith(" blob") and path_of[k.split()[0]] not in ALLOW_PATHS]
    data, i, bad = _git("cat-file", "--batch", inp="\n".join(blobs).encode()), 0, set()
    while i < len(data):
        nl = data.index(b"\n", i)
        sha, _t, size = data[i:nl].decode().split()
        body = data[nl + 1:nl + 1 + int(size)]
        i = nl + 1 + int(size) + 1
        t = _text(body)
        if t is not None:
            bad |= {f"history {path_of[sha]}: {c}" for _, c in hits(t, terms)}
    return sorted(bad)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--staged", action="store_true")
    g.add_argument("--file")
    g.add_argument("--range", metavar="REVS")
    g.add_argument("--history", action="store_true")
    a = ap.parse_args(argv)
    terms = load_terms()
    if a.staged:
        bad = _staged(terms)
    elif a.file:
        bad = _scan([a.file], lambda p: pathlib.Path(p).read_bytes(), terms)
    elif a.range:
        bad = _range(a.range, terms)
    elif a.history:
        bad = _history(terms)
    else:
        bad = _tracked(terms)
    for b in bad:
        print(b)
    print(f"check_privacy: {len(bad)} hit(s); {sum(map(len, terms.values()))} private terms loaded", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and watch them pass**

Run: `python3 -m pytest -q scripts/test_check_privacy.py`
Expected: every test passes (35: 14 caught rows, 8 clean rows, 13 tests).

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest -q client/python/tests scripts/`
Expected: all pass (458 + the new ones).

- [ ] **Step 6: Commit**

```bash
git add scripts/check_privacy.py scripts/test_check_privacy.py
TZ=UTC git commit -F <msg file>   # "feat(privacy): check_privacy.py, the public-repo gate"
```

---

### Task 2: hooks, CI step, `.gitignore`, `CLAUDE.md` and spec rulings

**Files:**
- Create: `scripts/hooks/pre-commit` and `scripts/hooks/commit-msg` (both executable)
- Modify: `.github/workflows/checks.yml` (checkout `fetch-depth: 0`, plus a new step)
- Modify: `.gitignore` (add `.superpowers/`)
- Modify: `CLAUDE.md` (new section)
- Modify: `docs/superpowers/specs/2026-10-18-public-repo-scrub-design.md` §6.2 (the two rulings)
- Test: `scripts/test_check_privacy.py` (hook tests appended)

**Interfaces:**
- Consumes: `check_privacy.py` modes `--staged`, `--file` and `--range` (Task 1).
- Produces: the hooks, which call `"$(dirname "$0")/../check_privacy.py"`, and the CI step name `no host-identifying data`.

- [ ] **Step 1: Append the failing hook tests**

```python
HOOKS = HERE / "hooks"


def hooked(repo):
    git(repo, "config", "core.hooksPath", str(HOOKS))
    return repo


def try_commit(repo, path, text, msg="m", tz="UTC"):
    (repo / path).write_text(text)
    git(repo, "add", path)
    return git(repo, "commit", "-q", "-m", msg, tz=tz, check=False)


def test_pre_commit_hook_refuses_a_non_utc_date(repo):
    assert try_commit(hooked(repo), "a.md", "clean\n", tz="Etc/GMT-5").returncode != 0


def test_pre_commit_hook_refuses_a_planted_file(repo):
    assert try_commit(hooked(repo), "a.md", "near Plantville\n").returncode != 0


def test_commit_msg_hook_refuses_a_session_link(repo):
    r = try_commit(hooked(repo), "a.md", "clean\n", msg="x\n\nClaude-Session: <removed>")
    assert r.returncode != 0


def test_hooks_pass_a_clean_utc_commit(repo):
    assert try_commit(hooked(repo), "a.md", "clean\n").returncode == 0
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python3 -m pytest -q scripts/test_check_privacy.py -k hook`
Expected: the three refusal tests FAIL (the commit succeeds: no hooks exist yet). The clean one passes.

- [ ] **Step 3: Write the hooks**

`scripts/hooks/pre-commit`:

```sh
#!/bin/sh
# Public repo (CLAUDE.md): no host-identifying data, and commit dates in UTC.
if [ "$(date +%z)" != "+0000" ]; then
  echo "pre-commit: commit with TZ=UTC so the date carries +0000" >&2
  exit 1
fi
exec python3 "$(dirname "$0")/../check_privacy.py" --staged
```

`scripts/hooks/commit-msg`:

```sh
#!/bin/sh
# The message is published with the commit (CLAUDE.md "Public repo").
exec python3 "$(dirname "$0")/../check_privacy.py" --file "$1"
```

Then run `chmod +x scripts/hooks/pre-commit scripts/hooks/commit-msg`.

- [ ] **Step 4: Run the hook tests and watch them pass**

Run: `python3 -m pytest -q scripts/test_check_privacy.py`
Expected: every test passes.

- [ ] **Step 5: Add the CI step.** In `.github/workflows/checks.yml`, replace `- uses: actions/checkout@v4` with:

```yaml
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
```

After `- uses: actions/setup-python@v5` and its `with:` line, add:

```yaml
      # The repository is public: every file, message and commit date is published (spec 2026-10-18).
      - name: no host-identifying data
        env:
          PRIVATE_TERMS: ${{ secrets.PRIVATE_TERMS }}
          PR_BASE: ${{ github.event.pull_request.base.sha }}
          PR_HEAD: ${{ github.event.pull_request.head.sha }}
          BEFORE: ${{ github.event.before }}
        run: |
          python3 scripts/check_privacy.py
          if [ -n "$PR_BASE" ]; then revs="$PR_BASE..$PR_HEAD"
          elif [ -n "$BEFORE" ] && [ "$BEFORE" != 0000000000000000000000000000000000000000 ]; then revs="$BEFORE..HEAD"
          else revs=HEAD; fi
          python3 scripts/check_privacy.py --range "$revs"
```

- [ ] **Step 6: RED the CI commands locally.** In a scratch clone of this branch, plant a line with a generic hit in a tracked file, commit it with `TZ=Etc/GMT-5`, and run the two step commands with `PRIVATE_TERMS=` and `BEFORE` set to the parent commit.
Expected: the first command exits 1 with `<file>:<line>: machine-name`. The second exits 1 with `date offset not +0000`. Delete the scratch clone.

- [ ] **Step 7: `.gitignore`.** Append the lines `.superpowers/` and `docs/superpowers/`. The 152 files that are already tracked stay tracked until Task 8 Step 5b. Until then, edit them as usual; a new file under `docs/superpowers/` needs `git add -f`.

- [ ] **Step 8: `CLAUDE.md`.** Insert after the section "The defining constraint (never violate)":

```markdown
## Public repo: no host-identifying data (never violate)

The repository is public, and so is every file, commit message, commit date,
PR body and CI log (2026-10-18: history rewritten and the repository
recreated to remove them; spec `docs/superpowers/specs/2026-10-18-public-repo-scrub-design.md`).

- Never commit the host's time zone or UTC offset, a machine name, an OS
  user name or home path (write `~` or `$HOME`), an IP other than loopback
  or the RFC 5737 documentation ranges, the city, region, country, ISP or
  ASN of the host or owner, or a session URL. This adds to the list of
  things never committed: traces, cookies, account ids, screenshots.
- Times in the repository are UTC (`HH:MM UTC`), and so are timestamps in
  names (run directories and run ids). Producers take a UTC clock
  (`ToUniversalTime()`, `datetime.now(datetime.timezone.utc)`), and
  `scripts/test_utc_stamps.py` fails on a local one.
- Commit with `TZ=UTC git commit ...`, so dates carry `+0000`. Enable the
  hooks once per clone: `git config core.hooksPath scripts/hooks`.
- Host captures write placeholders (`<host-tz>`, `user.HOST`) before they
  write a file. `capture_host_oracle.py` and `measure_step2.py scrub` refuse
  without private terms.
- The host-specific strings live in `~/.config/camoucrome/private-terms.json`
  (`{placeholder: [strings]}`, never committed), and CI reads them from the
  secret `PRIVATE_TERMS`.
- Run `python3 scripts/check_privacy.py --file <body>` on every PR body or
  comment before `gh pr create` or `gh pr comment`. CI runs the gate on every
  push.
- Never push from a clone made before the 2026-10-18 recreate. Its history
  is the one that was removed.
```

- [ ] **Step 9: Spec rulings.** In spec §6.2:
  - Replace "`~/.config/camoucrome/private-terms.txt` locally" with "`~/.config/camoucrome/private-terms.json` (`{placeholder: [strings]}`, `CAMOU_SCRUB`'s shape) locally".
  - In the generic patterns list, replace the bullet "a clock time followed by a zone abbreviation other than `UTC`, and `UTC±N` or `GMT±N` offsets" with "a clock time followed by a zone abbreviation other than `UTC` or `GMT`. There is no generic `UTC±N`/`GMT±N` pattern, because the measurement data holds the emulated identities' offsets. The host's own offset strings are private terms".
  - Add a line to the modes list: "`--history`: every blob reachable from every ref".

- [ ] **Step 10: Run the suite and commit**

Run: `python3 -m pytest -q client/python/tests scripts/`
Expected: all pass.

```bash
git add scripts/hooks .github/workflows/checks.yml .gitignore CLAUDE.md docs/superpowers/specs/2026-10-18-public-repo-scrub-design.md scripts/test_check_privacy.py
TZ=UTC git commit -F <msg file>   # "feat(privacy): hooks, CI gate and the CLAUDE.md rule"
```

---

### Task 3: capture scripts write placeholders

**Files:**
- Modify: `scripts/capture_host_oracle.py` (`committable()`, used by `main()`)
- Modify: `scripts/measure_step2.py` (`scrub_cmd` falls back to `check_privacy.load_terms()`)
- Test: `scripts/test_capture_host_oracle.py` (new) and `scripts/test_measure_step2_scrub.py` (new)

**Interfaces:**
- Consumes: `check_privacy.load_terms()` and `check_privacy.hits()` (Task 1), and `step2_rows.scrub(value, geo)` (existing).
- Produces: `capture_host_oracle.committable(doc: dict, terms: dict) -> dict`, which exits when `terms` is empty or a hit is left.

- [ ] **Step 1: Write the failing tests**

`scripts/test_capture_host_oracle.py`:

```python
"""capture_host_oracle writes only a scrubbed doc, and refuses rather than write a host value."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import capture_host_oracle as cho  # noqa: E402

TERMS = {"<host-tz>": ["Mars/Olympus"], "user.HOST": ["someone.BOX"]}
DOC = {"headed": {"intl": {"dtf": {"timeZone": "Mars/Olympus"}},
                  "err": {"stack": r"at file:///C:/Users/someone.BOX/AppData/Local/Temp/p.html"}}}


def test_committable_replaces_host_values():
    out = cho.committable(DOC, TERMS)
    assert out["headed"]["intl"]["dtf"]["timeZone"] == "<host-tz>"
    assert out["headed"]["err"]["stack"] == "at file:///C:/Users/user.HOST/AppData/Local/Temp/p.html"


def test_committable_refuses_without_terms():
    with pytest.raises(SystemExit):
        cho.committable(DOC, {})


def test_committable_refuses_a_leftover_hit():
    doc = {"headed": {"where": "built on DESKTOP-AB12CD3"}}
    with pytest.raises(SystemExit):
        cho.committable(doc, TERMS)
```

`scripts/test_measure_step2_scrub.py`:

```python
"""measure_step2 scrub takes the private terms when CAMOU_SCRUB is unset."""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import measure_step2 as ms  # noqa: E402


def test_scrub_falls_back_to_private_terms(tmp_path, monkeypatch):
    monkeypatch.delenv("CAMOU_SCRUB", raising=False)
    monkeypatch.setenv("PRIVATE_TERMS", json.dumps({"<host-tz>": ["Mars/Olympus"]}))
    src, dst = tmp_path / "run", tmp_path / "out"
    src.mkdir()
    (src / "rows.json").write_text(json.dumps({"tz": "Mars/Olympus"}))
    (src / "tables.md").write_text("| tz | Mars/Olympus |\n")
    assert ms.scrub_cmd(argparse.Namespace(run_dir=str(src), out_dir=str(dst))) == 0
    assert json.loads((dst / "rows.json").read_text()) == {"tz": "<host-tz>"}
    assert "Mars/Olympus" not in (dst / "tables.md").read_text()
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python3 -m pytest -q scripts/test_capture_host_oracle.py scripts/test_measure_step2_scrub.py`
Expected:
- `AttributeError: module 'capture_host_oracle' has no attribute 'committable'` (3 failures);
- `SystemExit: scrub: set CAMOU_SCRUB ...` (1 failure).

- [ ] **Step 3: Implement.** In `scripts/capture_host_oracle.py`, after the `OUT = ...` line, add the function below. Its imports are inside it on purpose: `build-verify` copies `capture_host_oracle.py` alone into `$VERIFY`, and the verifies import it for `page()`.

```python
def committable(doc, terms):
    """`doc` with the host's own values replaced by placeholders (CLAUDE.md "Public repo").
    Refuses without terms, or when the scrub leaves a hit, rather than write the host value."""
    import check_privacy
    import step2_rows
    if not terms:
        sys.exit("capture_host_oracle: no private terms ($PRIVATE_TERMS or ~/.config/camoucrome/private-terms.json)")
    out = step2_rows.scrub(doc, terms)
    left = check_privacy.hits(json.dumps(out, ensure_ascii=False), terms)
    if left:
        sys.exit(f"capture_host_oracle: host-identifying data left after the scrub: {sorted({c for _, c in left})}")
    return out
```

In `main()`, replace the `OUT.write_text(json.dumps({...}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")` call with:

```python
    import check_privacy
    doc = committable({"chrome": "154.0.8037.93", "where": "stock Google Chrome on the build box's Windows 10 host (build 19045), temp profile; headed through the host CDP client, headless --dump-dom",
                       "headed": headed, "headless": headless}, check_privacy.load_terms())
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
```

In `scripts/measure_step2.py` `scrub_cmd`, replace the first three lines of the body with:

```python
    import check_privacy
    geo = json.loads(os.environ["CAMOU_SCRUB"]) if os.environ.get("CAMOU_SCRUB") else check_privacy.load_terms()
    if not isinstance(geo, dict) or not geo:
        sys.exit("scrub: set CAMOU_SCRUB or the private terms ({placeholder: [host strings]}); neither is ever committed")
```

Fix the module docstring line `python measure_step2.py scrub RUN OUT   (needs CAMOU_SCRUB; ...)` to say `(needs CAMOU_SCRUB or the private terms; ...)`.

- [ ] **Step 4: Run the tests and watch them pass**

Run: `python3 -m pytest -q scripts/test_capture_host_oracle.py scripts/test_measure_step2_scrub.py`
Expected: 4 passed.

- [ ] **Step 5: Readers accept placeholders.** Run `grep -n '"intl.dtf.timeZone"\|"intl.date0"\|"err.stack"' scripts/oracle_rules.py`.
Expected: all three are in `SHAPE_ONLY`, so a placeholder string keeps the leaf's type and the comparison means the same. Record that in the ledger.

- [ ] **Step 6: Run the suite and commit**

Run: `python3 -m pytest -q client/python/tests scripts/`
Expected: all pass.

```bash
git add scripts/capture_host_oracle.py scripts/measure_step2.py scripts/test_capture_host_oracle.py scripts/test_measure_step2_scrub.py
TZ=UTC git commit -F <msg file>   # "feat(privacy): host captures write placeholders and refuse without terms"
```

- [ ] **Step 7: Write the failing UTC-stamp test** (spec §6.5), `scripts/test_utc_stamps.py`:

```python
"""Timestamps that reach the repository come from a UTC clock (spec 2026-10-18 §6.5)."""
import datetime
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
LOCAL = [
    (re.compile(r"Get-Date\s+-Format|\(Get-Date\)\.ToString\(|\$\w+\.ToString\('yyyy"), "*.ps1"),
    (re.compile(r"datetime\.(?:datetime\.)?(?:now|today)\(\s*\)|time\.(?:localtime|strftime)\("), "*.py"),
]


def test_no_local_clock_formatting_in_scripts():
    bad = []
    for rx, glob in LOCAL:
        for f in sorted(HERE.rglob(glob)):
            if f.name.startswith("test_"):
                continue
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if rx.search(line) and "ToUniversalTime" not in line:
                    bad.append(f"{f.relative_to(HERE)}:{i}")
    assert bad == []


def test_run_stamp_is_utc():
    import measure_step2
    s = measure_step2.run_stamp()
    got = datetime.datetime.strptime(s, "%Y%m%d-%H%M%S").replace(tzinfo=datetime.timezone.utc)
    assert abs((datetime.datetime.now(datetime.timezone.utc) - got).total_seconds()) < 5
```

Run: `python3 -m pytest -q scripts/test_utc_stamps.py`
Expected: FAIL. The first test lists `measure_canvas_noise.py:133` and `measure_step2.py:324`. The second fails with `AttributeError: ... 'run_stamp'`.

- [ ] **Step 8: Make the Python producers use UTC.** In `scripts/measure_step2.py`, add near the other helpers:

```python
def run_stamp():
    """A run id's time, in UTC (spec 2026-10-18 §6.5): a local clock in a committed name reveals the host's offset."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
```

Then replace `datetime.datetime.now().strftime("%Y%m%d-%H%M%S")` with `run_stamp()` on the `run_id =` line.

In `scripts/measure_canvas_noise.py`, replace `datetime.datetime.now().strftime("%Y%m%d-%H%M%S")` with `datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")`.

Run: `python3 -m pytest -q scripts/test_utc_stamps.py`
Expected: 2 passed. Then run the whole suite: all pass. Commit with `TZ=UTC`: "fix(privacy): run ids are UTC at the source, and a test keeps them so".

- [ ] **Step 9: The Windows producers, on `e-fb-auto`.** `observe-auto.ps1` and the unattended `observe-recon.ps1` exist only there.
  - In a worktree of `e-fb-auto`, change `scripts/windows/observe-auto.ps1` line 30 to `$run = Join-Path $Root ('auto\' + (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss'))`.
  - In `scripts/windows/observe-recon.ps1`, change the `run.json` `started`/`ended` line to `started = $started.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'); ended = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')`.
  - RED/GREEN: copy `scripts/test_utc_stamps.py` from `privacy-scrub` into that worktree, uncommitted.
    - Before the edit, `python3 -m pytest -q scripts/test_utc_stamps.py::test_no_local_clock_formatting_in_scripts` fails and lists both `.ps1` lines.
    - After the edit, it lists none (it still lists the two Python lines, which `privacy-scrub` fixes).
    - Then delete the copy.
  - Parse-check both files on the host with `[System.Management.Automation.Language.Parser]::ParseFile`, through sshgate with base64 as in `docs/observer/README.md`. Expected: 0 errors.
  - Commit with `TZ=UTC` ("fix(observer): run directories and run.json times are UTC"), then `git push origin e-fb-auto`. It is pushed before Task 5, so the mirror holds it.

---

### Task 4: tooling review before anything irreversible

- [ ] **Step 1:** Run the executing-plans final-review procedure on `privacy-scrub` (merge base `origin/main`, through HEAD):
  - `review-package`;
  - a fresh reviewer on the most capable model, given this plan's Review Focus and the spec;
  - Critical and Important findings fixed under TDD in one pass;
  - minor findings to the ledger.
- [ ] **Step 2:** Run `python3 -m pytest -q client/python/tests scripts/`. Expected: all pass. Ledger: `Task 4: complete`.

---

### Task 5: hold every session, then the raw export and the bundle

**Files:** none in the repository. Output goes to `~/Backups/camoucrome-github-2026-10-18/` (`B` below).

- [ ] **Step 1: Hold.**
  - `ListAgents`; send each live session: "Repo recreate in progress (owner, 2026-10-18): push everything now and reply with your branch and tip; then do not push to lang315/camoucrome until I message again."
  - Wait for each reply, or for 30 minutes.
  - Record each branch and tip in the ledger.
  - Check `git ls-remote origin` against the replies.
  - Expected: `repin/8078-prep` matches S5's reported tip.
- [ ] **Step 2: Write `B/export.py`** (outside the repository):

```python
"""Raw, unscrubbed export of the GitHub side of lang315/camoucrome. Local only, never committed."""
import json, pathlib, subprocess

R, B = "lang315/camoucrome", pathlib.Path(__file__).resolve().parent

def api(path, slurp=True):
    a = ["gh", "api"] + (["--paginate", "--slurp"] if slurp else []) + [path]
    return json.loads(subprocess.run(a, capture_output=True, text=True, check=True).stdout)

def raw(path, out):
    with open(out, "wb") as f:
        subprocess.run(["gh", "api", path], stdout=f, check=True)

prs = [p for page in api(f"repos/{R}/pulls?state=all&per_page=100") for p in page]
for p in prs:
    n = p["number"]
    p["_issue_comments"] = [c for pg in api(f"repos/{R}/issues/{n}/comments?per_page=100") for c in pg]
    p["_review_comments"] = [c for pg in api(f"repos/{R}/pulls/{n}/comments?per_page=100") for c in pg]
    p["_reviews"] = [c for pg in api(f"repos/{R}/pulls/{n}/reviews?per_page=100") for c in pg]
(B / "prs.json").write_text(json.dumps(prs, indent=1))
runs = [r for page in api(f"repos/{R}/actions/runs?per_page=100") for r in page["workflow_runs"]]
(B / "runs.json").write_text(json.dumps(runs, indent=1))
(B / "logs").mkdir(exist_ok=True)
for r in runs:
    raw(f"repos/{R}/actions/runs/{r['id']}/logs", B / "logs" / f"{r['id']}.zip")
arts = [a for page in api(f"repos/{R}/actions/artifacts?per_page=100") for a in page["artifacts"]]
(B / "artifacts.json").write_text(json.dumps(arts, indent=1))
(B / "artifacts").mkdir(exist_ok=True)
for a in arts:
    if not a["expired"]:
        raw(f"repos/{R}/actions/artifacts/{a['id']}/zip", B / "artifacts" / f"{a['id']}.zip")
def setting(path):
    try:
        return api(f"repos/{R}{path}", slurp=False)
    except subprocess.CalledProcessError as e:  # an endpoint this plan or account lacks: record it, restore by hand
        return {"_error": (e.stderr or "")[:200]}

settings = {k: setting(p) for k, p in {
    "repo": "", "protection": "/branches/main/protection", "actions": "/actions/permissions",
    "selected_actions": "/actions/permissions/selected-actions", "workflow": "/actions/permissions/workflow",
    "fork_pr_approval": "/actions/permissions/fork-pr-contributor-approval", "runners": "/actions/runners"}.items()}
(B / "settings.json").write_text(json.dumps(settings, indent=1))
print(len(prs), "prs;", len(runs), "runs;", len(arts), "artifacts")
```

- [ ] **Step 3: Run it.** `mkdir -p B`, then `python3 B/export.py`.
Expected: `40 prs; <N> runs; 31 artifacts`, with N ≥ 525. `ls B/logs | wc -l` equals N, and `ls B/artifacts | wc -l` equals the unexpired artifact count.
- [ ] **Step 4: Bundle the old history.**
  - `git clone --mirror git@github.com:lang315/camoucrome.git B/old.git`
  - `git -C B/old.git bundle create B/pre-rewrite.bundle --all`
  - `git bundle verify B/pre-rewrite.bundle`

  Expected: "is okay". Its refs list every remote branch.
- [ ] **Step 5:** Ledger line with the counts, the bundle's ref count and `du -sh B`.

---

### Task 6: the private rule files

**Files:** `~/.config/camoucrome/private-terms.json` and `~/.config/camoucrome/scrub-rules.txt` (both untracked; mode 600). Scratch scripts and reports live in `W=~/scrub-2026-10-18/`.

- [ ] **Step 1: Collect the host values, without echoing them into anything shared.**
  - Sources:
    - generic hits from `python3 scripts/check_privacy.py --history`, run with `PRIVATE_TERMS=` in a clone of `B/old.git`;
    - the city and ISP terms from the privacy grep in Task 8 of the pre-rewrite `e-fb-auto` plan (the local backup branch `e-fb-auto-pre-rewrite`, commit `4c54e9f`);
    - the host's zone name, display name and offset strings from `baselines/chrome-8037-stock-oracle-windows.json` (`intl.dtf.timeZone`, `intl.date0`) and from `docs/superpowers/measurements/step2-154/tables.md`;
    - the Windows profile directory and machine name from the oracle's `err.stack`;
    - the box IPs (the tailnet one and the WSL one) from the 2026-10-18 IP inventory: every `ip` hit that is not in `ALLOW_IPS`.
  - Write `private-terms.json` with the keys:
    - `<host-tz>`, `<host-tz-name>`, `<host-offset>`: every form found, including the numeric offset in minutes, `GMT+hhmm`, `UTC+hh:mm` and the Windows display list;
    - `user.HOST`, `HOST`;
    - `<box-tailnet-ip>`, `<wsl-ip>`;
    - `<host-city>`, `<host-country>`, `<host-isp>`.
  - Run `chmod 600`.
- [ ] **Step 2: Build the clock-time list.** Write `W/clocks.py`, which prints every distinct line (trimmed to 160 characters) that holds a `local-clock` hit or a `<host-offset>` term, in any blob or commit message of `B/old.git` for the kept branches. Write the output to `W/clocks.txt` (local).

```python
import re, subprocess, sys
sys.path.insert(0, sys.argv[2] + "/scripts")
import check_privacy as cp
repo, refs = sys.argv[1], ["main", "e-fb-auto", "repin/8078-prep"]
terms = cp.load_terms()
off = [n.lower() for n in terms.get("<host-offset>", [])]
def git(*a, inp=None):
    return subprocess.run(["git", "-C", repo, *a], input=inp, capture_output=True, check=True).stdout
blobs = [l.split()[0] for l in git("rev-list", "--objects", *refs).decode().splitlines() if " " in l]
kinds = git("cat-file", "--batch-check=%(objectname) %(objecttype)", inp="\n".join(blobs).encode()).decode()
data = git("cat-file", "--batch", inp="\n".join(k.split()[0] for k in kinds.splitlines() if k.endswith(" blob")).encode())
text = data.decode("utf-8", "replace") + git("log", "--format=%B", *refs).decode("utf-8", "replace")
seen = set()
for line in text.splitlines():
    if cp.GENERIC["local-clock"].search(line) or any(o in line.lower() for o in off):
        seen.add(line.strip()[:160])
print("\n".join(sorted(seen)))
```

  Run: `python3 W/clocks.py B/old.git <this worktree> > W/clocks.txt; wc -l W/clocks.txt`.
- [ ] **Step 3: Write `scrub-rules.txt`.** It holds one rule per line, in `git-filter-repo` `--replace-text` syntax (`literal==>replacement` or `regex:pattern==>replacement`), in this order:
  1. **Each clock fragment from `W/clocks.txt`:** a literal rule from the exact fragment (date included when it is on the line) to the same instant in UTC, `HH:MM UTC`. Move the date back when the conversion crosses midnight. Where a fragment has no date and crosses midnight, write `HH:MM UTC (previous day)`. Where a sentence names the zone ("times are in <zone>"), reword it to UTC.
  2. **Each private term:** a literal rule to its placeholder, longest needle first. Windows profile paths come before the machine name.
  3. **Home paths:** `regex:/home/<user>/==>~/` and `regex:/Users/<user>/==>~/`, with `<user>` the OS user name. Also cover:
     - the forms without a trailing slash;
     - backslash forms (`\home\<user>`, `\\wsl.localhost\<distro>\home\<user>`, `\\wsl$\...`) and their JSON-escaped doubles;
     - `C:\Users\<user>` and `<drive>:\Users\<user>`. The Task 4 review found a UNC WSL path in kept history. Also `-Users-<user>-` / `-home-<user>-` slugs go to `-Users-<user>-` as written literally with angle brackets. Phrases naming the OS user (`user \`<user>\``, `User=<user>`, `-u <user>`) go to `<user>`.
  4. **Session URLs:** `regex:https://claude\.ai/code/session_[A-Za-z0-9]+==><removed>`.
  5. **Country words describing the host or owner:** one literal rule per occurrence (`check_privacy --history` hits with key `<host-country>`, outside `ALLOW_PATHS`), with neutral wording, for example "a large regional shop".
  6. **Local-clock stamps** (spec §3.1, last row): one literal rule per stamp, from the classification in Step 3b. Run `chmod 600`.
- [ ] **Step 3b: Classify every `YYYYMMDD-HHMMSS` stamp.** Write `W/stamps.py`. For every distinct `\b20\d{6}-\d{6}\b` token in the blobs and messages of the kept branches of `B/old.git`, it prints:
  - the token;
  - the first commit that added it (`git log -S<token> --reverse --format='%H %at'`, oldest);
  - one context line, trimmed to 120 characters;
  - its producer, guessed from the context:
    - `observe-auto`/`auto\` or `recon` run dirs, meaning the Windows host, local;
    - `step2` run ids from `measure_step2.py`, meaning the Mac, local;
    - `canvas-noise` labels from `measure_canvas_noise.py`, meaning the box's WSL, UTC;
    - otherwise `unknown`.

  Output goes to `W/stamps.txt`, local. Then classify:
  - **A stamp read as UTC that is later than the epoch of the commit that added it** cannot be UTC: a run comes before its commit. It is local.
  - **A Windows-host or Mac stamp** is local.
  - **A WSL stamp** stays.
  - **An `unknown` stamp the commit-time test cannot decide** is resolved by reading the doc around it. Ledger each one with its reason.

  For every local stamp, convert with the host offset from the private terms, and write the literal rule `<local>==><utc>`, same format. Keep the list of local→UTC pairs as `W/stamp-map.txt`; Task 11 renames the host directories from it.
- [ ] **Step 4: Coverage check.** In a fresh clone of `B/old.git`, run `git filter-repo --force --replace-text ~/.config/camoucrome/scrub-rules.txt --replace-message ~/.config/camoucrome/scrub-rules.txt`. Then run `python3 <this worktree>/scripts/check_privacy.py --history --require-terms`.
Before this, RED: run the same command in an unrewritten clone. Expected: hits in every category the rules cover, and exit 2 with `PRIVATE_TERMS=`.
Expected: the only remaining hits are `.superpowers/` paths, which Task 7 removes, and `ip` hits that are not host addresses. Add each of those to `ALLOW_IPS` with its source, in a `TZ=UTC` commit on `privacy-scrub`. Iterate the rules until this holds. Delete the clone.

---

### Task 7: the rewrite and its verification

**Files:** the scratch clone `W/new`. In the repository: a merge of `privacy-scrub` into `main`, made inside `W/new`.

- [ ] **Step 1: The scratch clone.**
  - `git clone --no-local B/old.git W/new`
  - `git -C W/new checkout -b e-fb-auto origin/e-fb-auto`
  - `git -C W/new checkout -b repin/8078-prep origin/repin/8078-prep`
  - `git -C W/new checkout main`
  - `git -C W/new fetch <this worktree> privacy-scrub:privacy-scrub`
  - `TZ=UTC git -C W/new merge --no-ff privacy-scrub -F <msg file>`, with the message "Merge privacy-scrub: the public-repo gate, hooks and rules (spec 2026-10-18)"
  - `git -C W/new branch -D privacy-scrub`
  - `git -C W/new remote remove origin`

  Expected: `git -C W/new branch` lists exactly `e-fb-auto`, `main` and `repin/8078-prep`.
- [ ] **Step 2: Record the old tips.** Run `git -C W/new rev-parse main e-fb-auto repin/8078-prep > W/old-tips.txt` and `git -C W/new rev-list --count main e-fb-auto repin/8078-prep`.
- [ ] **Step 3: Rewrite.**

```bash
git -C W/new filter-repo --force \
  --invert-paths --path .superpowers/ \
  --replace-text ~/.config/camoucrome/scrub-rules.txt \
  --replace-message ~/.config/camoucrome/scrub-rules.txt \
  --commit-callback '
for a in ("author_date", "committer_date"):
    ts, _off = getattr(commit, a).split(b" ")
    setattr(commit, a, ts + b" +0000")
'
```

Expected: "Completely finished". `W/new/.git/filter-repo/commit-map` exists.
- [ ] **Step 4: Verify (spec §3.4).** Each check is one command, with its expected result:
  1. Run `cd W/new && python3 scripts/check_privacy.py --history --require-terms`. Expected: `0 hit(s)`. With `--require-terms`, a missing terms file exits 2 instead of passing.
  2. Run `cd W/new && python3 scripts/check_privacy.py --range=--all --require-terms`. Expected: `0 hit(s)`. This covers messages and `+0000` dates.
  3. Run `cd W/new && python3 -m pytest -q client/python/tests scripts/ && python3 scripts/gen_keys.py --check && python3 scripts/gen_fontconfig.py --check && python3 scripts/check_additions_build.py`. Expected: all pass.
  4. Run `git -C W/new rev-list --count main e-fb-auto repin/8078-prep`. Expected: the Step 2 count minus the commits that touched only `.superpowers/`.
  5. Run `grep -c . W/new/.git/filter-repo/commit-map`. Expected: one line per old commit plus the header.
  6. Run `python3 W/stamps.py W/new > W/stamps-after.txt`. Expected: no left-hand stamp of `W/stamp-map.txt` remains, and every remaining stamp is either a right-hand (UTC) stamp of the map or one classified as UTC in Step 3b.
  7. This one runs last, because it brings old objects in:
     - `git -C W/new fetch B/old.git main:refs/old/main`
     - `git -C W/new diff --stat refs/old/main main`
     - `git -C W/new update-ref -d refs/old/main`

     Expected: only files with scrubbed content, the removed `.superpowers/` files, and `privacy-scrub`'s own files. Review the list by hand. Then re-run check 1. Expected: `0 hit(s)`, which shows the old ref is gone.

  Any failure goes back to Task 6 Step 3. Fix the rules, re-clone, and rewrite again.

---

### Task 8: the archive file and the tip fixes

**Files (in `W/new`, on `main`):**
- Create: `docs/archive/2026-10-18-github-history.md`
- Modify: `.github/workflows/build-verify.yml`, `scripts/check_checkout_sync.sh`, `scripts/rebuild_branch.sh` (home paths that must run)
- Modify: every tracked file with a link to an old PR or run page

- [ ] **Step 1: Write `W/render_archive.py`** (outside the repository):

```python
"""Render the scrubbed archive of PRs and runs from the raw export, the scrub rules and filter-repo's commit map."""
import datetime as dt, json, pathlib, re, sys
B = pathlib.Path.home() / "Backups/camoucrome-github-2026-10-18"
new = pathlib.Path(sys.argv[1])
rules = []
for line in (pathlib.Path.home() / ".config/camoucrome/scrub-rules.txt").read_text(encoding="utf-8").splitlines():
    if "==>" not in line:
        continue
    pat, repl = line.split("==>", 1)
    rules.append((re.compile(pat[6:]) if pat.startswith("regex:") else re.compile(re.escape(pat)), repl))
cmap = {}
for line in (new / ".git/filter-repo/commit-map").read_text().splitlines()[1:]:
    old, nw = line.split()
    cmap[old] = nw
def remap(m):
    h = m.group(0)
    full = [o for o in cmap if o.startswith(h)]
    return cmap[full[0]][:len(h)] if len(full) == 1 and not set(cmap[full[0]]) == {"0"} else h
def scrub(t):
    t = t or ""
    t = re.sub(r"(?m)^.*claude\.ai/code/session\S*.*\n?", "", t)
    for rx, repl in rules:
        t = rx.sub(lambda _m: repl, t)
    return re.sub(r"\b[0-9a-f]{7,40}\b", remap, t)
prs = sorted(json.loads((B / "prs.json").read_text()), key=lambda p: p["number"])
runs = sorted(json.loads((B / "runs.json").read_text()), key=lambda r: r["id"])
def newsha(s):
    return cmap.get(s) or "(not in the rewritten history)"
out = ["# GitHub history before the 2026-10-18 recreate", "",
       "The repository was deleted and recreated on 2026-10-18 to remove host-identifying data",
       "(spec `docs/superpowers/specs/2026-10-18-public-repo-scrub-design.md`). This file keeps its",
       f"{len(prs)} pull requests and {len(runs)} workflow runs. Bodies are verbatim, apart from the scrub",
       "rules, removed session links and commit ids mapped to the rewritten history. Runs keep no logs.",
       "PR numbers below are the old ones; the recreated repository numbers from 1 again.", "",
       "| PR | title | branch | state | opened (UTC) | merged (UTC) | merge commit |", "|---|---|---|---|---|---|---|"]
for p in prs:
    st = "merged" if p.get("merged_at") else p["state"]
    mc = newsha(p["merge_commit_sha"])[:10] if p.get("merged_at") else ""
    out.append(f"| [#{p['number']}](#pr-{p['number']}) | {scrub(p['title'])} | `{p['head']['ref']}` | {st} | "
               f"{p['created_at']} | {p.get('merged_at') or ''} | {mc} |")
for p in prs:
    out += ["", f'<a id="pr-{p["number"]}"></a>', f"## #{p['number']} {scrub(p['title'])}", "",
            f"`{p['head']['ref']}` into `{p['base']['ref']}`, opened {p['created_at']}, "
            f"{'merged ' + p['merged_at'] if p.get('merged_at') else p['state']}.", "", scrub(p.get("body"))]
    for c in p["_issue_comments"] + p["_review_comments"] + p["_reviews"]:
        if c.get("body"):
            out += ["", f"**Comment, {c.get('created_at') or c.get('submitted_at')}:**", "", scrub(c["body"])]
out += ["", "## Workflow runs", "", "| run | workflow | event | branch | head | conclusion | started (UTC) | seconds |",
        "|---|---|---|---|---|---|---|---|"]
for r in runs:
    secs = int((dt.datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00")) -
                dt.datetime.fromisoformat(r["run_started_at"].replace("Z", "+00:00"))).total_seconds())
    out.append(f'| <a id="run-{r["id"]}"></a>{r["id"]} | {r["name"]} | {r["event"]} | `{r["head_branch"]}` | '
               f'{newsha(r["head_sha"])[:10]} | {r["conclusion"]} | {r["run_started_at"]} | {secs} |')
(new / "docs/archive").mkdir(exist_ok=True)
(new / "docs/archive/2026-10-18-github-history.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print(len(prs), "prs,", len(runs), "runs")
```

- [ ] **Step 2: Render and check (spec §4.2).**
  - Run `python3 W/render_archive.py W/new`. Expected: `40 prs, <N> runs`, with N the same as Task 5.
  - `grep -c '^<a id="pr-' W/new/docs/archive/2026-10-18-github-history.md` → 40.
  - `grep -c '<a id="run-' ...` → N.
  - `cd W/new && python3 scripts/check_privacy.py --file docs/archive/2026-10-18-github-history.md` → `0 hit(s)`.
  - Every merge commit cell resolves: run `git -C W/new cat-file -e <sha>` for each 10-character id in the index table. Expected: all succeed, apart from cells that read "(not in the rewritten history)", which are listed in the ledger.
- [ ] **Step 3: Home paths that must run.**
  - In `.github/workflows/build-verify.yml`, delete the job-level `env:` block (`SRC`, `VERIFY`, `CLIENT`, `PLAYWRIGHT_NODEJS_PATH`) and make this the job's first step:

```yaml
      - name: box paths
        run: |
          { echo "SRC=$HOME/chromium/src"; echo "VERIFY=$HOME/camoucrome-verify"
            echo "CLIENT=$HOME/camoucrome-client"; echo "PLAYWRIGHT_NODEJS_PATH=$HOME/camoucrome-driver/node"; } >> "$GITHUB_ENV"
```

    Replace `export PATH=~/depot_tools:$PATH`, which is what the rewrite left, with `export PATH=$HOME/depot_tools:$PATH`.
  - In `scripts/check_checkout_sync.sh` and `scripts/rebuild_branch.sh`, the default argument the rewrite left as `~/...` inside double quotes becomes `$HOME/...`. A tilde in double quotes does not expand.
  - Then run `bash -n` on both scripts, and `grep -n '~/' .github/workflows/build-verify.yml scripts/check_checkout_sync.sh scripts/rebuild_branch.sh`. Expected: no output.
  - On `e-fb-auto`, in `scripts/windows/observe-recon.ps1`: the rewrite left the `run.json` build-lock call as `wsl -d Ubuntu-24.04 -u <user> -- bash ~/actions-runner/...` (Task 3 ruling). Make it `wsl -d Ubuntu-24.04 -- bash -lc '$HOME/actions-runner/_work/camoucrome/camoucrome/scripts/build_lock.sh status'`, which relies on WSL's default user, and commit with `TZ=UTC`. Task 11 checks it with one host call.
- [ ] **Step 4: Links to old pages.**
  - Run `git -C W/new grep -l -E 'github\.com/lang315/camoucrome/(pull|actions/runs)/[0-9]+'`.
  - For each file, replace `https://github.com/lang315/camoucrome/pull/<n>` with `https://github.com/lang315/camoucrome/blob/main/docs/archive/2026-10-18-github-history.md#pr-<n>`, and `.../actions/runs/<id>` with the same file `#run-<id>`.
  - Expected: re-running the grep gives no output.
- [ ] **Step 5: Gate and commit.**
  - Run `cd W/new && python3 scripts/check_privacy.py --require-terms`, `python3 -m pytest -q client/python/tests scripts/` and `python3 scripts/check_privacy.py --range=--all --require-terms`. Expected: 0 hits, all pass, 0 hits.
  - Then `git add -A docs/archive .github scripts docs` and `TZ=UTC git commit -F <msg file>`, with the message "docs(archive): the GitHub history before the 2026-10-18 recreate; repoint old links; $HOME paths".
  - Run `python3 scripts/check_privacy.py --range HEAD~1..HEAD`. Expected: 0 hits.
- [ ] **Step 5b: Stop tracking `docs/superpowers/`** (owner, 2026-10-18; spec §3.2).
  - Record `D=$(git -C W/new rev-parse HEAD)`. This is the last commit that tracks the folder.
  - Run `git -C W/new rm -r -q --cached docs/superpowers`. Expected: `git -C W/new ls-files docs/superpowers | wc -l` gives 0, and the files are still on disk in `W/new`.
  - In `CLAUDE.md`, under "Read first", add this paragraph, with `<D>` replaced by the recorded id's first 10 characters:

```markdown
`docs/superpowers/` (specs, plans, measurements) is local, not in git, since
the 2026-10-18 recreate (`.gitignore`). Its history up to then is in git. A
fresh clone restores the folder with
`git archive <D> docs/superpowers | tar -x`, and new specs and plans stay in
the local folder.
```

  - In `README.md`, add the same sentence where it first links into `docs/superpowers/`.
  - Commit with `TZ=UTC git -C W/new commit -F <msg file>`: "chore: stop tracking docs/superpowers (owner, 2026-10-18); it stays local".
  - Run `python3 scripts/check_privacy.py` and `python3 -m pytest -q client/python/tests scripts/` in `W/new`. Expected: 0 hits, and all pass. No code reads `docs/superpowers/`; it is cited only in comments.
  - Write `D` into the ledger. Task 11 uses it.
- [ ] **Step 6: The other kept branches.**
  - `e-fb-auto` and `repin/8078-prep` were rewritten with `main` and stay on the rewritten history. Neither is rebased onto the new tip commits.
  - Both branches add files under `docs/superpowers/`, and merging either one would track them again: `.gitignore` does not stop a merge.
  - On `e-fb-auto`, this session's branch, make the same untrack commit as Step 5b: `git -C W/new checkout e-fb-auto`, then `git rm -r -q --cached docs/superpowers`, then `TZ=UTC git commit -F <msg file>`, then `git -C W/new checkout main`. Expected: `git -C W/new ls-tree -r --name-only e-fb-auto docs/superpowers | wc -l` gives 0.
  - `repin/8078-prep` belongs to S5. Do not commit on it. The Task 11 message tells S5 to make that commit before its PR.

---

### Task 9: delete and recreate the GitHub repository (owner gate)

- [ ] **Step 1: Owner scope.** Ask the owner to run `! gh auth refresh -h github.com -s delete_repo`. Expected: `gh auth status` lists `delete_repo`.
- [ ] **Step 2: Owner confirmation.** Show the owner:
  - what is deleted: `lang315/camoucrome` with its PRs, runs and settings;
  - what holds it: the bundle and the raw export in `B`;
  - the new tips of the three branches.

  Ask them to reply with the word `delete`. Without that word, stop here.
- [ ] **Step 3: Delete and create.**
  - `gh repo delete lang315/camoucrome --yes`
  - `gh repo create lang315/camoucrome --public --description "$(jq -r .repo.description B/settings.json)" --disable-wiki`
  - `gh api -X PATCH repos/lang315/camoucrome -F has_issues=true -F has_projects=true -F allow_merge_commit=true -F allow_squash_merge=true -F allow_rebase_merge=true -F delete_branch_on_merge=false`

  Expected: `gh repo view lang315/camoucrome --json visibility` gives `PUBLIC`.
- [ ] **Step 4: Push.**
  - `git -C W/new remote add origin git@github.com:lang315/camoucrome.git`
  - `git -C W/new push origin main`
  - `git -C W/new push origin e-fb-auto repin/8078-prep`

  Expected: `git ls-remote --heads origin` lists exactly the three branches, at `W/new`'s tips.
- [ ] **Step 5: Restore the settings from `B/settings.json`.**
  - `gh api -X PUT repos/lang315/camoucrome/actions/permissions -F enabled=true -f allowed_actions=selected`
  - `jq .selected_actions B/settings.json | gh api -X PUT repos/lang315/camoucrome/actions/permissions/selected-actions --input -`
  - `jq '{default_workflow_permissions: .workflow.default_workflow_permissions, can_approve_pull_request_reviews: .workflow.can_approve_pull_request_reviews}' B/settings.json | gh api -X PUT repos/lang315/camoucrome/actions/permissions/workflow --input -`
  - `gh api -X PUT repos/lang315/camoucrome/actions/permissions/fork-pr-contributor-approval -f approval_policy="$(jq -r .fork_pr_approval.approval_policy B/settings.json)"`
  - `jq '{required_status_checks: {strict: .protection.required_status_checks.strict, contexts: .protection.required_status_checks.contexts}, enforce_admins: .protection.enforce_admins.enabled, required_pull_request_reviews: {required_approving_review_count: .protection.required_pull_request_reviews.required_approving_review_count}, restrictions: null, allow_force_pushes: false, allow_deletions: false}' B/settings.json | gh api -X PUT repos/lang315/camoucrome/branches/main/protection --input -`
  - `gh secret set PRIVATE_TERMS -R lang315/camoucrome < ~/.config/camoucrome/private-terms.json`

  Expected: re-reading each endpoint matches `B/settings.json` field for field, and `gh secret list` shows `PRIVATE_TERMS`.

---

### Task 10: runner and CI

- [ ] **Step 1: Re-register `buildpc-wsl`.** This follows `docs/superpowers/measurements/2026-10-repin.md`, "Runner re-registered". Use one sshgate call per step:
  1. As root (`wsl -d Ubuntu-24.04 -u root`), in the runner directory: `./svc.sh stop; ./svc.sh uninstall`.
  2. As `<user>`: remove `.runner`, `.runner_migrated`, `.credentials` and `.credentials_rsaparams`. Then run `./config.sh --unattended --url https://github.com/lang315/camoucrome --token <token> --name buildpc-wsl --labels buildpc-wsl --replace`, with the token from `gh api -X POST repos/lang315/camoucrome/actions/runners/registration-token --jq .token`. Expected: "Runner successfully added".
  3. As root: `./svc.sh install <user>; ./svc.sh start`. Expected: `active (running)`.

  Then `gh api repos/lang315/camoucrome/actions/runners` lists `buildpc-wsl` as `online`.
- [ ] **Step 2: CI.**
  - `checks` runs on the pushes from Task 9 Step 4. Run `gh run list -R lang315/camoucrome --workflow checks --limit 3`. Expected: `success` on `main`. The new step "no host-identifying data" passed with the secret.
  - Run `gh workflow run build-verify -R lang315/camoucrome --ref main`, then watch it with `gh run watch`. Expected: `success`. A failure in the `box paths` step or the sync gate means the `$HOME` fix: fix it in a `TZ=UTC` commit through a PR.
- [ ] **Step 3: Planted RED in CI.**
  - Push a branch `privacy-red` with one commit that adds a file holding a generic hit (`DESKTOP-` plus 7 characters), made with `TZ=UTC`.
  - Expected: `checks` fails at "no host-identifying data". The log names the path and `machine-name`, and does not show the planted value.
  - Delete the branch with `git push origin :privacy-red`, and delete its run with `gh run delete <id>`.

---

### Task 11: reopen the PR, sync the clones, close out

- [ ] **Step 1: Reopen the `e-fb-auto` PR.**
  - Take the old #40 body from the archive section `#pr-40`, and add a first line: "Reopened after the 2026-10-18 recreate; was #40."
  - Run `python3 scripts/check_privacy.py --file <body>`. Expected: 0 hits.
  - Run `gh pr create -R lang315/camoucrome --base main --head e-fb-auto --title "<old #40 title>" --body-file <body>`.
  - When the owner approves merging it (not in this plan), merge locally: `TZ=UTC git merge --no-ff e-fb-auto` on an up-to-date `main`, then `git push origin main`. Never use the merge button or `gh pr merge` (`CLAUDE.md`).
  - Expected: `checks` is `success` on the PR.
- [ ] **Step 2: This session's clones.**
  - In the main checkout (the parent repository of this worktree): run `git status --porcelain`. If it is dirty, stop and ask the owner.
  - Otherwise:
    - `git fetch origin --prune`
    - `git checkout main`
    - `git reset --hard origin/main`
  - In this worktree, switch to `e-fb-auto` and run `git reset --hard origin/e-fb-auto`.
  - Delete the local branches `privacy-scrub` and `e-fb-auto-pre-rewrite`, which hold pre-rewrite history; the bundle keeps it.
  - Run `git config core.hooksPath scripts/hooks` in the main checkout.
  - The reset deletes `docs/superpowers/` from disk, because the tip stopped tracking it. Restore it in the main checkout and in this worktree with `git archive <D> docs/superpowers | tar -x`, run at the checkout root, with `D` from Task 8 Step 5b. Expected: `ls docs/superpowers` shows `measurements`, `plans` and `specs`, and `git status --porcelain docs/superpowers` is empty, because the folder is ignored.
  - Expected: `git log -1 --format='%ai' origin/main` ends in `+0000`.
- [ ] **Step 3: Other sessions' clones.** Do not modify them. Send each held session, and S5 for `repin/8078-prep`, a message:
  - the recreate is done;
  - the new tips;
  - the path of the commit map, `W/new/.git/filter-repo/commit-map`;
  - "re-clone or `git fetch origin && git reset --hard origin/<branch>` after saving local work; then `git archive <D> docs/superpowers | tar -x` to get the local docs back; before opening a PR from a branch that adds files under `docs/superpowers/` (S5: `repin/8078-prep`), commit `git rm -r --cached docs/superpowers` on it, or the merge tracks them again; never push from a pre-recreate clone; run `git config core.hooksPath scripts/hooks`".

  The box clones (`~/camoucrome-x8037`, `~/observe-A/cs`, `~/repin-prep/repo`, `~/camoucrome-cs-review`) and the Windows host clone are listed to the owner, untouched.
- [ ] **Step 3b: The host follows the docs.**
  - For each pair in `W/stamp-map.txt` whose local name is a directory under `D:\camou-win\observe\` (`auto\<stamp>` and any other run directory), rename it to the UTC name with `Rename-Item`, through sshgate. This touches no other tree, and never `observe\backup`.
  - Expected: every UTC name the docs cite exists on the host, and no local name does.
  - Install the UTC versions of `observe-auto.ps1` and `observe-recon.ps1` from the new repository, as `docs/observer/README.md` says: `Invoke-WebRequest` from `raw.githubusercontent.com/lang315/camoucrome/<new e-fb-auto sha>/...`, then `Get-FileHash` against the repository and `ParseFile` with 0 errors.
- [ ] **Step 4: Memory.**
  - The `repo-recreated` note gets the second recreate: date, new tips, and the rule "never push from a pre-2026-10-18 clone".
  - A new `feedback` memory, "public repo privacy": what is never committed, where the private terms live, `TZ=UTC` commits, and the hooks.
  - The `MEMORY.md` lines.
- [ ] **Step 5: Success criteria (spec §8).** Re-run each check and paste its output into the ledger:
  - `check_privacy.py --history` on a fresh clone of the new repository, with the terms;
  - `gh api repos/lang315/camoucrome/pulls?state=all --jq length` (1);
  - `gh run list` contains only runs after the recreate;
  - `checks` and `build-verify` are green;
  - the settings match;
  - the planted RED from Task 10 Step 3.
- [ ] **Step 6: Report to the owner** (in the owner's language, local clock times in chat only). Include:
  - the counts;
  - the new tips;
  - the rulings and the deferred minor findings;
  - what stays outside our reach: public-event archives, caches, and the untouched clones;
  - the stamp conversion: how many were converted, how many WSL stamps stayed, and the host directories renamed.

  Then release the hold.
