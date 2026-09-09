#!/bin/bash
# Rebuilds the camoucrome/main branch (what scripts/export.sh exports from) in
# a Chromium checkout from this repository: a worktree at the pin, additions/
# and settings/invariants.json in the first commit, then one commit per
# patches/series entry with the patch stem as subject. Deterministic, so the
# branch is disposable -- the repo stays the source of truth.
#
# Usage: scripts/rebuild_branch.sh <chromium-src-dir> [worktree-dir]
# Refuses to run while camoucrome/main exists: delete it first, on purpose.
set -euo pipefail

SRC="${1:?usage: rebuild_branch.sh <chromium-src-dir> [worktree-dir]}"
WT="${2:-/home/lang/camoumain}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=../upstream.env
. "$ROOT/upstream.env"

if git -C "$SRC" show-ref --quiet refs/heads/camoucrome/main; then
  echo "error: camoucrome/main already exists in $SRC; remove its worktree and branch first" >&2
  exit 1
fi
git -C "$SRC" worktree add -q -b camoucrome/main "$WT" "$CHROMIUM_REV"
mkdir -p "$WT/components/camoucfg"
cp "$ROOT"/additions/camoucfg/* "$WT/components/camoucfg/"
cp "$ROOT/settings/invariants.json" "$WT/components/camoucfg/invariants.json"
while read -r p; do
  case "$p" in ""|\#*) continue ;; esac
  git -C "$WT" apply --3way "$ROOT/patches/$p"
  git -C "$WT" add -A
  git -C "$WT" -c user.name=camoucrome -c user.email=camoucrome@localhost commit -q -m "${p%.patch}"
  echo "  ${p%.patch}"
done < "$ROOT/patches/series"
echo "camoucrome/main: $(git -C "$WT" rev-list --count "$CHROMIUM_REV..HEAD") commits above $CHROMIUM_REV at $WT"
