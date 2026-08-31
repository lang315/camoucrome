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
# Order is semantic, not alphabetical, and is listed explicitly rather than
# globbed. Each patch after the first is a diff generated from a checkout
# that already had every earlier one applied, so a patch's base is the
# previous patch's output for any file they share -- content/browser/
# browser_main_loop.cc is edited by all three of these. A glob sorts
# lexicographically, which matches this order today only by luck: "sp2-*"
# will sort between "sp1a-*" and "sp5a-*", but SP2 is extracted from a tree
# that already has SP5a applied (00-conventions.md's sub-project order), so a
# glob would apply it too early and fail on a base that does not match.
PATCHES=(
  "$ROOT/patches/sp0-config-layer.patch"
  "$ROOT/patches/sp1a-ua-producer.patch"
  "$ROOT/patches/sp5a-coherence-validator.patch"
  "$ROOT/patches/sp2a-automation-hiding.patch"
  "$ROOT/patches/sp2b-humanized-cursor.patch"
  "$ROOT/patches/sp3a-canvas-noise.patch"
  "$ROOT/patches/sp3b-webgl-profile.patch"
  "$ROOT/patches/sp1b-navigator-leaves.patch"
  "$ROOT/patches/sp4a-screen.patch"
  "$ROOT/patches/sp4-fonts.patch"
)
for patch in "${PATCHES[@]}"; do
  echo "  $(basename "$patch")"
  git -C "$SRC" apply --3way "$patch"
done

echo "done. build with: autoninja -C out/Default content_shell"
