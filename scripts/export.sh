#!/bin/bash
# Regenerates the change set from a Chromium checkout's camoucrome/main branch:
# one commit per patch above the pin in upstream.env, commit subject == patch
# stem. Writes patches/*.patch, patches/series (the order apply.sh follows),
# additions/camoucfg/ and settings/invariants.json into this repository.
#
# Usage: scripts/export.sh <chromium-src-dir> [branch]      (default camoucrome/main)
#
# The gate: after an export, `git status --porcelain additions patches settings`
# must be empty. Anything it prints is drift between the reviewed branch and the
# committed change set -- a hand-extracted patch that lost a hunk, an edit that
# never left the checkout -- and the branch, not the repo, is what was built.
#
# The branch lives in the checkout; the repo lives on the Mac. Run this on the
# build box against a copy of the repo (tar additions settings/invariants.json
# patches upstream.env scripts/export.sh), then bring the four outputs back.
set -euo pipefail

SRC="${1:?usage: export.sh <chromium-src-dir> [branch]}"
BRANCH="${2:-camoucrome/main}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=../upstream.env
. "$ROOT/upstream.env"

if [ "$(git -C "$SRC" merge-base "$CHROMIUM_REV" "$BRANCH")" != "$CHROMIUM_REV" ]; then
  echo "error: $BRANCH is not based on the pinned $CHROMIUM_REV (upstream.env)" >&2
  exit 1
fi
mapfile -t COMMITS < <(git -C "$SRC" rev-list --reverse --first-parent "$CHROMIUM_REV..$BRANCH")
if [ "${#COMMITS[@]}" -eq 0 ]; then
  echo "error: $BRANCH has no commits above $CHROMIUM_REV" >&2
  exit 1
fi

# Validate every subject before touching patches/: a bad commit half-way down
# the branch must not leave the repo with the first half deleted.
NAMES=()
for c in "${COMMITS[@]}"; do
  name="$(git -C "$SRC" log -1 --format=%s "$c")"
  case "$name" in
    ""|*[!a-z0-9-]*) echo "error: commit $c subject '$name' is not a patch stem ([a-z0-9-]+)" >&2; exit 1 ;;
  esac
  case " ${NAMES[*]-} " in
    *" $name "*) echo "error: two commits on $BRANCH share the subject '$name'" >&2; exit 1 ;;
  esac
  NAMES+=("$name")
done

rm -f "$ROOT"/patches/*.patch
: > "$ROOT/patches/series"
for i in "${!COMMITS[@]}"; do
  c="${COMMITS[$i]}"; name="${NAMES[$i]}"
  # components/camoucfg is additions/, exported whole from the tip below; a
  # commit that only touches it produces no patch and no series line.
  git -C "$SRC" diff --no-color "$c^" "$c" -- . ':(exclude)components/camoucfg' > "$ROOT/patches/$name.patch"
  if [ -s "$ROOT/patches/$name.patch" ]; then
    echo "$name.patch" >> "$ROOT/patches/series"
    echo "  $name.patch"
  else
    rm "$ROOT/patches/$name.patch"
    echo "  $name (additions only, no patch)"
  fi
done

rm -rf "$ROOT/additions/camoucfg"
mkdir -p "$ROOT/additions/camoucfg"
git -C "$SRC" archive "$BRANCH" components/camoucfg | tar -x -C "$ROOT/additions" --strip-components=1
# The one place the two layouts differ (see apply.sh): the registry is edited
# in settings/ and read from beside the header in the tree.
mv "$ROOT/additions/camoucfg/invariants.json" "$ROOT/settings/invariants.json"

echo "exported ${#COMMITS[@]} commits from $BRANCH. Gate: git status --porcelain additions patches settings"
