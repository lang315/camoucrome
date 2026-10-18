# Public repo scrub: no host-identifying data, history included (2026-10-18)

The repository is public. Its history, its pull requests and its Actions logs
hold data that identifies the build host and its owner. The owner decided on
2026-10-18 to remove all of it, by rewriting the whole history and
recreating the GitHub repository, and to add rules and gates so it does not
come back.

This spec names categories and placeholders only. The literal values to
remove are kept in an untracked file outside the repository (§3.1). A spec
that spelled them out would re-publish them.

## 1. Decisions (owner, 2026-10-18)

| question | decision |
|---|---|
| what to remove | host data in files, commit dates' UTC offset, local-time clock times in docs, the machine user name in paths |
| GitHub-side copies (`refs/pull/*`, Actions logs, PR bodies) | delete and recreate the repository, as on 2026-09-26 |
| PR pages and Actions history | back up first: raw locally, scrubbed into one docs file |
| rules | a `CLAUDE.md` section, a gate script in CI and in local hooks, and capture scripts that write placeholders |

Kept on purpose:
- product data: the locale-to-zone table `settings/locale_zones.json`, the
  voice table `settings/voices.json`, and zone names in
  `settings/invariants.json`. They describe what the fork emulates, not the host.
- the GitHub account name, which is in the repository URL, and the commit
  author name and its noreply address.

## 2. Inventory (2026-10-18, `origin/main`, every reachable blob)

| category | tip files | history-only paths |
|---|---|---|
| host time zone name and offset in captures | 3 | 3 |
| Windows machine name, Windows profile path | 3 | 2 |
| tailnet IP of the box, WSL-internal IP | 2 | 3 |
| home paths with the OS user name (Linux and macOS) | 36 | 32 |
| clock times labelled with the local zone | 9 | 6 |
| country words that describe the host or owner (not product data) | about 4 | about 4 |
| commit author/committer dates with a non-zero offset | every commit | |

Outside git:
- `refs/pull/1..40` keep the pre-rewrite history fetchable by anyone, and
  force-push cannot remove them.
- 525 workflow runs (492 `checks`, 33 `build-verify`) with public logs, and
  31 artifacts (0.2 MB).
- 40 PR bodies: 6 hold home paths or local-zone times, and 27 (#2 to #28)
  hold Claude session links, which the owner's rules already forbid.

The branch `e-fb-auto` was scrubbed and force-pushed earlier on 2026-10-18
(ISP, city and extension id). This spec covers everything else.

## 3. Rewrite

### 3.1 Rules

`git-filter-repo` runs on a fresh mirror clone, holding the kept branches
(§3.3). Replacements are exact strings or anchored regexes, never bare words,
because product files legitimately hold some of the same zone names. The rule
file lives at `~/.config/camoucrome/scrub-rules.txt` and is never committed.

| category | placeholder |
|---|---|
| host time zone name in captures | `<host-tz>` |
| host time zone offset in captures | `<host-offset>` |
| Windows profile directory (`<user>.<machine>`) and machine name | `user.HOST`, `HOST` |
| tailnet IP of the box | `<box-tailnet-ip>` |
| WSL-internal IP | `<wsl-ip>` |
| Linux and macOS home paths | `~/` in prose, `$HOME/` where a shell expands it |
| clock times labelled with the local zone | the same instant in UTC, written `HH:MM UTC`, with the date moved back where the conversion crosses midnight. One mapping row per occurrence, reviewed by hand |
| country words that describe the host or owner | neutral wording, per occurrence |
| local-clock timestamps in names (run directories and run ids, `YYYYMMDD-HHMMSS`) | the same instant in UTC, same format. Only stamps made on a machine whose clock is local are converted: the Windows host and the Mac. The box's WSL clock is UTC, so its stamps stay. One literal rule per stamp, classified by producer |
| tracked scratch under `.superpowers/` | removed from every commit |
| commit messages | the same rules (`--replace-message`) |
| author and committer dates | the same instant with offset `+0000` |

IPv4-looking strings that are version numbers (`154.0.0.0`) or
documentation addresses are not IPs. The plan lists every real IP found,
and only those get a rule.

### 3.2 Tip fixes after the rewrite

These are one commit on the rewritten `main`, not rules:
- Workflow and script paths that must still run on the runner use `$HOME`.
  `build-verify` must be green after the recreate (§5 step 8).
- Links to `github.com/<account>/camoucrome/pull/<n>` and
  `.../actions/runs/<id>` point to anchors in the archive file (§4).

### 3.3 Branches

The kept branches are `main`, `e-fb-auto` (open PR) and `repin/8078-prep`
(another session's live work). Merged branches are not pushed again.

### 3.4 Verification before anything changes on GitHub

1. The inventory script over every kept ref gives 0 hits in every category,
   apart from the product-data allowlist.
2. The rule file's literal values occur nowhere in the rewritten history:
   blobs, messages and paths.
3. The tip tree differs from the old tip only in the expected files.
4. `python3 -m pytest -q client/python/tests scripts/`, `gen_keys.py --check`,
   `gen_fontconfig.py --check` and `check_additions_build.py` pass on the
   rewritten tip.
5. Every commit date in the kept refs has offset `+0000`.
6. Commit counts match the old refs, minus commits that touched only
   `.superpowers/` and so became empty.

## 4. Backup of the GitHub-side history

### 4.1 Raw, local only

Export before the rewrite and before the delete. The export holds:
- every PR as JSON (body, title, branches, dates, merge commit);
- every workflow run as JSON, with its log zip;
- every artifact.

It goes to `~/Backups/camoucrome-github-2026-10-18/` on the Mac. It is never
committed and never pushed: logs hold runner paths and box details.

The same directory keeps a `git bundle` of the full pre-rewrite history of
every remote branch. That bundle is the rollback (§7).

### 4.2 Scrubbed, one docs file

The file is `docs/archive/2026-10-18-github-history.md`:
- an index of the 40 PRs: number, title, head branch, state, opened and
  merged dates (UTC), and the merge commit's new SHA;
- one section per PR with its body verbatim. The §3.1 rules are applied,
  session links are removed, and SHAs are mapped old→new through
  `filter-repo`'s commit map. A SHA with no new commit is marked
  `(not in the rewritten history)`;
- an appendix table of every run: workflow, event, branch, head SHA (new),
  conclusion, start (UTC) and duration. It holds no logs.

It is the last commit on the rewritten `main` before the first push, and
§3.4 covers it.

Checks:
- it has exactly 40 PR sections and as many run rows as the raw export;
- it has 0 inventory hits and 0 session links;
- every SHA in it resolves in the new history (`git cat-file -e`);
- the raw export holds one log zip per run and every artifact.

## 5. Recreate sequence

1. **Hold.** Tell every session to push its work and then stop pushing until
   told. Record the open sessions and their branches.
2. **Prepare.** Run the raw export (§4.1), the rewrite (§3), the archive
   file (§4.2) and the tip fixes (§3.2). Pass §3.4. Nothing on GitHub has
   changed yet.
3. **Record the settings to restore:**
   - repository description and merge settings;
   - `has_wiki` false;
   - the Actions permissions, including the selected-actions list;
   - fork-PR approval;
   - branch protection on `main`: `checks` required, 0 approvals, no force
     push or deletion, admins not enforced;
   - the runner's name and labels.
4. **Owner step.** The owner runs `gh auth refresh -h github.com -s delete_repo`
   and confirms the deletion by typing `delete`. The deletion cannot be
   undone.
5. Delete `lang315/camoucrome`, then create it again, public, with the
   recorded description and settings.
6. Push `main`, then the other kept branches.
7. Restore the Actions permissions, the fork-PR approval and the branch
   protection. Add the secret `PRIVATE_TERMS` (§6.2).
8. **Re-register the runner `buildpc-wsl` on the box.**
   - Use a new registration token and `config.sh --replace`.
   - Where the service needs sudo, the owner runs that command.
   - `gh workflow run build-verify` on `main` must be green.
9. **Reopen the open PR** from `e-fb-auto`, with its body scrubbed and
   passing `check_privacy.py --file`.
10. **Sync the clones.**
    - This session's clones: fetch the new history and reset the kept
      branches. Delete local branches that only hold pre-rewrite history.
      Old objects stay local (no `gc`).
    - Other sessions' clones on the Mac and the box get a message with the
      old→new SHA map.
    - The Windows host clone that this session must not touch stays as it
      is. The rule (§6.1) forbids pushing from any clone made before the
      recreate.
11. **Memory.** The `repo-recreated` note gets the second recreate, with
    the new tip and the rule above.

## 6. Rules and gates

### 6.1 `CLAUDE.md`

A new section, "Public repo: no host-identifying data (never violate)":
- **Never commit:**
  - the host's time zone or UTC offset;
  - a machine name;
  - an OS user name or a home path. Use `~` or `$HOME`;
  - an IP other than loopback or the RFC 5737 documentation ranges;
  - a city, region, country, ISP or ASN of the host or owner;
  - a session URL.

  This extends the existing list of things never to commit (traces,
  cookies, account ids and so on).
- **Times in the repository are UTC.** How times are given to the owner in
  chat is a memory rule, not a repository rule.
- **Commit with `TZ=UTC git commit ...`**, so commit dates carry `+0000`.
- **Host captures use placeholders before they are written** (`<host-tz>`,
  `user.HOST`).
- **PR bodies and comments go through `check_privacy.py --file`** before
  `gh pr create` or `gh pr comment`.
- **Never push from a clone made before 2026-10-18's recreate.**
- **Enable the hooks with `git config core.hooksPath scripts/hooks`** in
  every clone.

### 6.2 `scripts/check_privacy.py`

- **Generic patterns** (safe to commit):
  - a Windows default machine name (`DESKTOP-` plus 7 characters);
  - a Windows profile path under `C:\Users\` that is not a placeholder;
  - `/home/<name>/` and `/Users/<name>/`, except placeholders (`<user>`)
    and GitHub-hosted runners' `/home/runner/`;
  - IPv4 outside an allowlist (loopback, RFC 5737, `x.0.0.0` version
    strings, test fixtures named in the script);
  - `.ts.net`;
  - a clock time followed by a zone abbreviation other than `UTC`, and
    `UTC±N` or `GMT±N` offsets;
  - `claude.ai/code/session`.
- **Host-specific terms** (city, ISP, zone name, machine name) are read from
  `~/.config/camoucrome/private-terms.txt` locally, or from the environment
  variable `PRIVATE_TERMS` in CI (an Actions secret). Neither is ever in the
  repository. Fork PRs get no secrets and run the generic patterns only.
- **Path allowlist for product data:** `settings/locale_zones.json`,
  `settings/voices.json` and `settings/invariants.json`.
- **Modes:**
  - tracked files: all, or the staged ones;
  - `--range A..B`: commit messages, and author and committer date offsets,
    which must be `+0000`;
  - `--file PATH`: a PR body or comment.
- **Output:** path, line and category, never the matched value, so a CI log
  does not re-publish it. Exit 1 on any hit.
- **Tests, `scripts/test_check_privacy.py`,** written first and watched to
  fail:
  - one planted line per category fails, and so does one planted private
    term;
  - a clean file passes;
  - an allowlisted product file passes;
  - a commit with a non-zero offset fails `--range`;
  - the output holds no planted value.

### 6.3 Wiring

- **CI:** `checks.yml` checks out with `fetch-depth: 0` and gets a step
  "no host-identifying data". It checks the tracked files on every push, and
  `--range` over the pushed or PR commits.
- **Local hooks** in `scripts/hooks/`:
  - `pre-commit` checks the staged files and refuses when `date +%z` is not
    `+0000`;
  - `commit-msg` checks the message.
- `.gitignore` gains `.superpowers/`.

### 6.5 Timestamps are UTC at the source (owner, 2026-10-18)

Every producer of a timestamp that reaches the repository uses a UTC clock:
- `observe-auto.ps1` run directories;
- `observe-recon.ps1`'s `run.json` `started`/`ended`;
- `measure_step2.py` and `measure_canvas_noise.py` run ids.

A test fails on a local-clock call in `scripts/` (`Get-Date -Format` or
`(Get-Date).ToString(` without `ToUniversalTime()`, and `datetime.now()`
without a time zone). The host run directories that the docs name are
renamed to their UTC names, so the docs and the host agree.

### 6.4 Capture scripts write placeholders

The Windows host captures (`capture_host_oracle.py` and the scripts that
write `step2*/rows.json` and `tables.md`) replace the host's own time zone,
offset, machine name and profile path with the §3.1 placeholders before
writing. The plan lists every reader of those files and makes each one
accept the placeholders, so a comparison that used the host value still
means the same. The 2026-10-20 re-pin recapture is the first real run.

## 7. Rollback and residual risk

- **Before step 5,** GitHub is unchanged, and stopping costs nothing.
- **After step 5,** the old repository cannot be restored. The `git bundle`
  of §4.1 can re-push the old history, and the raw export keeps every PR
  and run.
- **Copies outside our control remain:**
  - public-event archives may have recorded PR bodies and push events;
  - search engines may have cached pages;
  - clones made by others may exist.

  The repository has 0 forks and 0 stars as of 2026-10-18.

## 8. Success criteria

- Every §3.4 check passes on the rewritten history, and every §4.2 check
  passes on the archive.
- The recreated repository holds only the rewritten refs. `refs/pull/*`
  starts empty, and the Actions history starts empty.
- `checks` and `build-verify` are green on the new `main`, and the reopened
  PR's `checks` is green.
- `check_privacy.py` exits 0 on the new `main`, including with the private
  terms. A planted line makes it exit 1, locally and in CI.
- Branch protection, Actions permissions and the runner match the
  settings recorded in step 3.
