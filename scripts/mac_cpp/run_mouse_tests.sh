#!/usr/bin/env bash
# dev-only; not part of the Chromium build; not in any GN target.
# Builds and runs additions/camoucfg/mouse_trajectories_unittest.cc on the Mac against
# the shims in scripts/mac_cpp (cursory + the adapter). Extra args go to clang++.
# Env: MOUSE_STAGE (staging dir), MOUSE_CXXFLAGS (extra flags).
set -euo pipefail
repo="$(cd "$(dirname "$0")/../.." && pwd)"
stage="${MOUSE_STAGE:-${TMPDIR:-/tmp}/mouse_stage}"
rm -rf "$stage"
mkdir -p "$stage/components"
# Staged copies, not symlinks: Apple clang does not know Chromium's
# `#pragma allow_unsafe_buffers`, so the copy maps it to the standard clang form.
cp -R "$repo/additions/camoucfg_lgpl" "$stage/components/camoucfg_lgpl"
mkdir "$stage/components/camoucfg"
cp "$repo/additions/camoucfg/mouse_trajectories"* "$stage/components/camoucfg/"
for f in "$stage"/components/*/*.cc; do
  sed 's/#pragma allow_unsafe_buffers/#pragma clang diagnostic ignored "-Wunsafe-buffer-usage"/' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
done
lgpl="$stage/components/camoucfg_lgpl"
cfg="$stage/components/camoucfg"
clang++ -std=c++20 -O1 -Wall -Wextra -Wunsafe-buffer-usage -Werror -DUNSAFE_BUFFERS_BUILD ${MOUSE_CXXFLAGS:-} "$@" \
  -isystem "$repo/scripts/mac_cpp" -I "$stage" \
  "$lgpl/cursory.cc" "$lgpl/cursory_data.cc" "$cfg/mouse_trajectories.cc" \
  "$cfg/mouse_trajectories_unittest.cc" -o "$stage/mouse_tests"
"$stage/mouse_tests"
