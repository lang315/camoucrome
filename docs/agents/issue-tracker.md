# Issue tracker: private notes markdown, plus public GitHub issues

Two trackers, split by what an issue may name:

- **GitHub issues** (`gh issue ...`, public): defects with no host data, worded so anyone may read them (for example #47, a DEPS grant). Run `python3 scripts/check_privacy.py --file <body>` before `gh issue create` or `gh issue comment`.
- **The private tracker** (below): anything that names the owner's accounts, fb, host details, or anything the owner keeps private, and the specs and tickets the engineering skills write.

## Where the private tracker lives

`docs/superpowers/issues/` in the owner's main clone: the private notes repository (see `CLAUDE.md` "Read first"). Edit it in the main clone only, never in a worktree: worktree copies of `docs/superpowers/` are not kept in sync. Commit and push it to the private notes remote after each edit, as specs and plans are. A session without the owner's folder asks the owner.

## Conventions

- One feature per directory: `docs/superpowers/issues/<feature-slug>/`
- The spec is `docs/superpowers/issues/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `docs/superpowers/issues/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`, never a single combined tickets file
- Triage state is recorded as a `Status:` line near the top of each issue file (see `triage-labels.md` for the role strings)
- Comments and conversation history append to the bottom of the file under a `## Comments` heading
- Times are UTC (`HH:MM UTC`), as everywhere in the repository.

## When a skill says "publish to the issue tracker"

Create a new file under `docs/superpowers/issues/<feature-slug>/` in the main clone (creating the directory if needed), then commit and push the notes repository. Use a GitHub issue instead only when the issue is public and host-free.

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path, or `gh issue view <number> --comments` for a GitHub issue. The user will normally pass the path or the issue number directly.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a file with one **child** file per ticket.

- **Map**: `docs/superpowers/issues/<effort>/map.md` (the Notes / Decisions-so-far / Fog body).
- **Child ticket**: `docs/superpowers/issues/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `claimed`/`resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is `resolved`.
- **Frontier**: scan `docs/superpowers/issues/<effort>/issues/` for files that are open, unblocked, and unclaimed; first by number wins.
- **Claim**: set `Status: claimed`, then commit and push before any work, so other sessions see the claim.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then append a context pointer (a one-line summary and the file path) to the map's Decisions-so-far in `map.md`.
