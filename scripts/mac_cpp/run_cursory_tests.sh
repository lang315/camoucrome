#!/usr/bin/env bash
# dev-only; not part of the Chromium build; not in any GN target.
# Builds and runs additions/camoucfg_lgpl/cursory_unittest.cc on the Mac against
# the shims in scripts/mac_cpp. Extra args go to clang++ (e.g. -fsanitize=address,undefined).
# Env: CURSORY_STAGE (staging dir), CURSORY_CXXFLAGS (extra flags).
set -euo pipefail
repo="$(cd "$(dirname "$0")/../.." && pwd)"
stage="${CURSORY_STAGE:-${TMPDIR:-/tmp}/cursory_stage}"
mkdir -p "$stage/components"
# Staged copy, not a symlink: Apple clang does not know Chromium's
# `#pragma allow_unsafe_buffers`, so the copy maps it to the standard clang form.
rm -rf "$stage/components/camoucfg_lgpl"
cp -R "$repo/additions/camoucfg_lgpl" "$stage/components/camoucfg_lgpl"
for f in "$stage"/components/camoucfg_lgpl/*.cc; do
  sed 's/#pragma allow_unsafe_buffers/#pragma clang diagnostic ignored "-Wunsafe-buffer-usage"/' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
done
lgpl="$stage/components/camoucfg_lgpl"
# -Wunsafe-buffer-usage -Werror with UNSAFE_BUFFERS_BUILD mirrors Chromium: raw-array
# indexing must sit behind `#pragma allow_unsafe_buffers`. CURSORY_NO_UNSAFE_DEFINE=1 drops
# the define (RED check: the pragma disappears and the build must fail).
unsafe_def="-DUNSAFE_BUFFERS_BUILD"; [ -n "${CURSORY_NO_UNSAFE_DEFINE:-}" ] && unsafe_def=""
clang++ -std=c++20 -O1 -Wall -Wextra -Wunsafe-buffer-usage -Werror $unsafe_def ${CURSORY_CXXFLAGS:-} "$@" \
  -I "$repo/scripts/mac_cpp" -I "$stage" \
  "$lgpl/cursory.cc" "$lgpl/cursory_data.cc" "$lgpl/cursory_unittest.cc" \
  -o "$stage/cursory_tests"
"$stage/cursory_tests"
