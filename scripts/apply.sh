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

echo "applying patches"
for patch in "$ROOT"/patches/*.patch; do
  echo "  $(basename "$patch")"
  git -C "$SRC" apply --3way "$patch"
done

echo "done. build with: autoninja -C out/Default content_shell"
