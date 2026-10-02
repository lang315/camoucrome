#!/bin/bash
# Rebuilds the camoucrome/main branch (what scripts/export.sh exports from) in
# a Chromium checkout from this repository: a worktree at the pin, additions/
# and settings/invariants.json in the first commit, then one commit per
# patches/series entry with the patch stem as subject. Deterministic, so the
# branch is disposable -- the repo stays the source of truth.
#
# Usage: scripts/rebuild_branch.sh <chromium-src-dir> [worktree-dir] [branch]
# Refuses to run while the branch (default camoucrome/main) exists: delete it
# first, on purpose (if ~/chromium/src is checked out on it, detach src first,
# then delete; afterwards `git -C src checkout camoucrome/main` and drop the
# worktree). Atomic: the series is applied on a temporary branch that is
# renamed only when every patch has landed, and a failure removes the
# temporary branch and the worktree, so a failed run can simply be repeated.
set -euo pipefail

SRC="${1:?usage: rebuild_branch.sh <chromium-src-dir> [worktree-dir] [branch]}"
WT="${2:-/home/lang/camoumain}"
BRANCH="${3:-camoucrome/main}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=../upstream.env
. "$ROOT/upstream.env"

if git -C "$SRC" show-ref --quiet "refs/heads/$BRANCH"; then
  echo "error: $BRANCH already exists in $SRC; remove its worktree and branch first" >&2
  exit 1
fi
if [ -e "$WT" ]; then
  echo "error: $WT already exists; remove it or name another worktree dir" >&2
  exit 1
fi

TMP="camoucrome/rebuild-$$"
CURRENT="setup"
cleanup() {
  rc=$?
  if [ "$rc" -ne 0 ]; then
    git -C "$SRC" worktree remove --force "$WT" 2>/dev/null || rm -rf "$WT"
    git -C "$SRC" worktree prune
    git -C "$SRC" branch -q -D "$TMP" 2>/dev/null || true
    echo "error: rebuild failed at $CURRENT; the temporary branch and $WT were removed" >&2
  fi
  exit "$rc"
}
trap cleanup EXIT

git -C "$SRC" worktree add -q -b "$TMP" "$WT" "$CHROMIUM_REV"
mkdir -p "$WT/components/camoucfg"
cp "$ROOT"/additions/camoucfg/* "$WT/components/camoucfg/"
cp "$ROOT/settings/invariants.json" "$WT/components/camoucfg/invariants.json"
while read -r p; do
  case "$p" in ""|\#*) continue ;; esac
  CURRENT="$p"
  git -C "$WT" apply --3way "$ROOT/patches/$p"
  git -C "$WT" add -A
  git -C "$WT" -c user.name=camoucrome -c user.email=camoucrome@localhost commit -q -m "${p%.patch}"
  echo "  ${p%.patch}"
done < "$ROOT/patches/series"
CURRENT="rename"
git -C "$WT" branch -m "$TMP" "$BRANCH"
echo "$BRANCH: $(git -C "$WT" rev-list --count "$CHROMIUM_REV..HEAD") commits above $CHROMIUM_REV at $WT"
