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

# Every patch below is a diff against ONE revision, recorded in upstream.env.
# On any other HEAD `git apply --3way` may still succeed on most hunks and
# fail late on one, or worse succeed with a shifted context -- so refuse up
# front. A deliberate rebase sets CAMOU_PIN_OVERRIDE=1 and expects conflicts.
# shellcheck source=../upstream.env
. "$ROOT/upstream.env"
HEAD_REV="$(git -C "$SRC" rev-parse HEAD)"
if [ "$HEAD_REV" != "$CHROMIUM_REV" ]; then
  if [ "${CAMOU_PIN_OVERRIDE:-0}" = "1" ]; then
    echo "warning: HEAD $HEAD_REV is not the pinned $CHROMIUM_REV; continuing because CAMOU_PIN_OVERRIDE=1" >&2
  else
    echo "error: HEAD $HEAD_REV is not the pinned $CHROMIUM_REV (upstream.env); set CAMOU_PIN_OVERRIDE=1 to rebase" >&2
    exit 1
  fi
fi

echo "copying additions"
mkdir -p "$SRC/components/camoucfg"
cp "$ROOT"/additions/camoucfg/* "$SRC/components/camoucfg/"

# The invariant registry lives in settings/ in this repository and beside the
# header in the tree. That is the one place the two layouts differ, and it is
# deliberate: settings/ is where a human edits configuration, while
# CoherenceValidatorTest.RegistryMatchesGeneratedHeader reads it from
# DIR_SRC_TEST_DATA_ROOT and so needs it inside the checkout.
cp "$ROOT/settings/invariants.json" "$SRC/components/camoucfg/invariants.json"

echo "applying patches"
# Order is semantic, not alphabetical: each patch after the first is a diff
# generated from a tree that already had every earlier one applied, so a
# patch's base is the previous patch's output for any file they share
# (content/browser/browser_main_loop.cc is edited by three of them). A glob
# would sort "sp2-*" between "sp1a-*" and "sp5a-*", but SP2 is extracted from a
# tree that already has SP5a applied. patches/series is written by
# scripts/export.sh from the camoucrome/main branch order; do not hand-sort it.
# The process substitution's exit status is invisible to set -e, so a missing
# or empty series would otherwise apply nothing and still print "done".
[ -s "$ROOT/patches/series" ] || { echo "error: $ROOT/patches/series is missing or empty" >&2; exit 1; }
mapfile -t PATCHES < <(grep -v '^#' "$ROOT/patches/series" | sed '/^$/d; s#^#'"$ROOT"'/patches/#')
[ "${#PATCHES[@]}" -gt 0 ] || { echo "error: $ROOT/patches/series lists no patches" >&2; exit 1; }
applied=0
for patch in "${PATCHES[@]}"; do
  echo "  $(basename "$patch")"
  git -C "$SRC" apply --3way "$patch"
  applied=$((applied + 1))
done
echo "applied $applied/${#PATCHES[@]} patches"

echo "done. build with: autoninja -C out/Default content_shell"
