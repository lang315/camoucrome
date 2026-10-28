#!/usr/bin/env bash
# dev-only; not part of the Chromium build; not in any GN target.
# Builds and runs additions/camoucfg_lgpl/cursory_unittest.cc on the Mac against
# the shims in scripts/mac_cpp. Extra args go to clang++ (e.g. -fsanitize=address,undefined).
# Env: CURSORY_STAGE (staging dir), CURSORY_CXXFLAGS (extra flags).
set -euo pipefail
repo="$(cd "$(dirname "$0")/../.." && pwd)"
stage="${CURSORY_STAGE:-${TMPDIR:-/tmp}/cursory_stage}"
mkdir -p "$stage/components"
ln -sfn "$repo/additions/camoucfg_lgpl" "$stage/components/camoucfg_lgpl"
lgpl="$stage/components/camoucfg_lgpl"
clang++ -std=c++20 -O1 -Wall -Wextra ${CURSORY_CXXFLAGS:-} "$@" \
  -I "$repo/scripts/mac_cpp" -I "$stage" \
  "$lgpl/cursory.cc" "$lgpl/cursory_data.cc" "$lgpl/cursory_unittest.cc" \
  -o "$stage/cursory_tests"
"$stage/cursory_tests"
