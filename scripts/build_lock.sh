#!/usr/bin/env bash
# One Chromium build at a time on the build PC.
#
# The WSL checkout (~/chromium/src, CI) and the native Windows tree
# (D:\camou-win\chromium\src) share one machine. Neither can see the other's
# processes: WSL interop is off, and CI's own "is a ninja running" check sees
# only WSL. So both sides take this lock, a directory in WSL's home that the
# Windows side reaches with `wsl -u lang -e bash .../build_lock.sh`.
# `mkdir` is the atomic test-and-set.
#
#   build_lock.sh acquire <owner>   take the lock, or exit 1 naming the holder
#   build_lock.sh release <owner>   drop it, only if <owner> holds it
#   build_lock.sh status            exit 0 if free, 1 (naming the holder) if held
#
# A lock left by a build that died is removed by hand after checking that no
# build is running: rm -rf ~/.camou-build.lock
set -euo pipefail

LOCK="${CAMOU_BUILD_LOCK:-$HOME/.camou-build.lock}"
usage() { echo "usage: build_lock.sh acquire|release <owner> | status" >&2; exit 2; }
holder() { cat "$LOCK/owner" 2>/dev/null || echo "an unknown owner"; }

case "${1:-}" in
  acquire)
    owner="${2:-}"; [ -n "$owner" ] || usage
    if pgrep -f "ninja -C out/(Default|Release)" >/dev/null; then
      echo "refused: a ninja is already running in the WSL checkout" >&2; exit 1
    fi
    if ! mkdir "$LOCK" 2>/dev/null; then
      echo "refused: the build lock is held by $(holder)" >&2; exit 1
    fi
    printf '%s since %s\n' "$owner" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$LOCK/owner"
    echo "acquired by $owner" ;;
  release)
    owner="${2:-}"; [ -n "$owner" ] || usage
    [ -d "$LOCK" ] || { echo "not held"; exit 0; }
    case "$(holder)" in
      "$owner since "*) rm -rf "$LOCK"; echo "released by $owner" ;;
      *) echo "refused: $owner does not hold the lock; $(holder) does" >&2; exit 1 ;;
    esac ;;
  status)
    if [ -d "$LOCK" ]; then echo "held by $(holder)"; exit 1; fi
    echo "free" ;;
  *) usage ;;
esac
