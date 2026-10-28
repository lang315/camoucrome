#!/usr/bin/env bash
# dev-only; not part of the Chromium build; not in any GN target.
# Builds and runs additions/camoucfg/input_queue_unittest.cc on the Mac against
# the shims in scripts/mac_cpp. Extra args go to clang++.
set -euo pipefail
repo="$(cd "$(dirname "$0")/../.." && pwd)"
stage="${QUEUE_STAGE:-${TMPDIR:-/tmp}/queue_stage}"
rm -rf "$stage"
mkdir -p "$stage/components/camoucfg"
cp "$repo"/additions/camoucfg/input_queue* "$stage/components/camoucfg/"
cfg="$stage/components/camoucfg"
clang++ -std=c++20 -O1 -Wall -Wextra -Wunsafe-buffer-usage -Werror -DUNSAFE_BUFFERS_BUILD "$@" \
  -isystem "$repo/scripts/mac_cpp" -I "$stage" \
  "$cfg/input_queue.cc" "$cfg/input_queue_unittest.cc" -o "$stage/queue_tests"
"$stage/queue_tests"
