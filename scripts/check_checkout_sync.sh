#!/bin/bash
# Every file apply.sh copies must be byte-identical in the repo and the checkout.
#
# This exists because the drift happened twice in one day, and both times it was
# found by accident rather than by a check.
#
#   keys.h     edited in the repo when an SP1a review finding was closed, never
#              mirrored. Found by a task that hashed every additions/ file before
#              extracting patches -- a discipline it applied on its own initiative.
#   derive.cc  edited in the repo minutes after that, same omission, caught only
#              because the harness happened to print a "changed on disk" notice.
#
# The repository is the source of truth and the checkout is a deployment, so the
# checkout being stale is not itself a defect. It becomes one the moment anything
# is measured on the checkout and reported as a property of the repo -- which is
# what every verification here does. A comment-only drift still invalidates
# "reconstruction is byte-identical", which is SP5a Task 7's whole claim.
#
# Usage: scripts/check_checkout_sync.sh [ssh-target|local] [checkout-path]
# Defaults match this project's build machine.

set -u

SSH_TARGET="${1:-buildpc}"
SRC="${2:-/home/lang/chromium/src}"
CONTROL="${CONTROL_PATH:-$HOME/.ssh/cm-buildpc}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Mirrors apply.sh: additions/camoucfg/* land in components/camoucfg/, and
# settings/invariants.json lands beside them. That one asymmetry is deliberate
# and is the reason this list is derived from apply.sh's behaviour rather than
# from a glob of the tree.
declare -a REPO_FILES=()
declare -a TREE_FILES=()
for f in "$ROOT"/additions/camoucfg/*; do
  REPO_FILES+=("$f")
  TREE_FILES+=("components/camoucfg/$(basename "$f")")
done
REPO_FILES+=("$ROOT/settings/invariants.json")
TREE_FILES+=("components/camoucfg/invariants.json")

# One SSH round trip, not one per file: a per-file loop over this link takes
# minutes, and a check that is slow enough to skip is a check nobody runs.
# The newline is appended OUTSIDE the command substitution. $(...) strips
# trailing newlines, so `remote_script+=$(printf '...\n')` silently joins every
# line into one -- "cd /path || exit 1sha256sum components/..." -- which then
# fails on the far side and looks exactly like a dead SSH link.
remote_script="cd $SRC || exit 1"$'\n'
for t in "${TREE_FILES[@]}"; do
  remote_script+="sha256sum '$t' 2>/dev/null || echo \"MISSING $t\""$'\n'
done
# The patched files are covered the other way round: the build tree must equal
# the camoucrome/main branch that scripts/export.sh exports from. The 09-09
# input_handler.cc drift (an un-reviewed rework sitting in the build tree while
# the branch and the repo carried the reviewed one) is what this line is for.
# camoucfg is excluded because it is untracked in the build tree and would read
# as 26 deletions; the sha256 loop above already covers it.
# `git diff` cannot see an untracked file, so a new .cc added in the build tree
# and never committed to the branch is listed separately (out/ and camoucfg
# excluded for the reasons above).
# A failing git (no such branch, not a repo) must print something here, or the
# section is empty and reads as "in sync".
remote_script+="echo BUILDTREE_BEGIN; git diff camoucrome/main --stat -- . ':(exclude)components/camoucfg' || echo 'git diff camoucrome/main failed (no such branch?)'; git status --porcelain --untracked-files=all -- . ':(exclude)out' ':(exclude)components/camoucfg' | grep '^??' || true; echo BUILDTREE_END"$'\n'
# And the repo's patches/ against the branch: each commit's diff, generated
# exactly as export.sh generates it, hashed on the far side. A hand-edited
# patches/*.patch or a stale series reads as a mismatch below.
. "$ROOT/upstream.env"
remote_script+="PIN=$CHROMIUM_REV"$'\n'
remote_script+='for c in $(git rev-list --reverse --first-parent "$PIN..camoucrome/main"); do
  d=$(git diff --no-ext-diff --no-color --src-prefix=a/ --dst-prefix=b/ "$c^" "$c" -- . ":(exclude)components/camoucfg" | sha256sum | cut -d" " -f1)
  [ "$d" = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 ] || echo "PATCH $(git log -1 --format=%s "$c").patch $d"
done'$'\n'
# On the build box itself (the self-hosted runner, or a shell in WSL) there is
# no link to cross: SSH_TARGET=local runs the same script against $SRC directly.
if [ "$SSH_TARGET" = local ] || { [ -z "${1:-}" ] && [ -d "$SRC/.git" ]; }; then
  remote_out=$(bash -c "$remote_script" 2>/dev/null)
else
  remote_out=$(ssh -o ControlPath="$CONTROL" -o ControlMaster=no "$SSH_TARGET" \
    "wsl -d Ubuntu-24.04 -u lang -- bash -lc \"echo $(printf '%s' "$remote_script" | base64 | tr -d '\n') | base64 -d > /tmp/sync.sh; bash /tmp/sync.sh\"" 2>/dev/null)
fi

if [ -z "$remote_out" ]; then
  # Deliberately does NOT guess a cause. The first version of this said "is the
  # SSH master up?" and the link was fine -- the real fault was a quoting bug in
  # the script above. A diagnostic that names the wrong cause is worse than one
  # that names none, because it sends the reader somewhere else entirely.
  echo "FAIL  the checkout returned nothing. Could be the SSH master, the wsl" >&2
  echo "      invocation, or this script's own remote command. Check with:" >&2
  echo "      ssh -o ControlPath=$CONTROL -o ControlMaster=no $SSH_TARGET \\" >&2
  echo "        'wsl -d Ubuntu-24.04 -u lang -- bash -lc \"echo LINK_OK\"'" >&2
  exit 2
fi

fails=0
for i in "${!REPO_FILES[@]}"; do
  local_sha=$( (shasum -a 256 "${REPO_FILES[$i]}" 2>/dev/null || sha256sum "${REPO_FILES[$i]}") | cut -d' ' -f1)
  tree="${TREE_FILES[$i]}"
  remote_sha=$(printf '%s\n' "$remote_out" | awk -v f="$tree" '$2 == f {print $1}')
  base=$(basename "${REPO_FILES[$i]}")
  if [ -z "$remote_sha" ]; then
    echo "FAIL  $base is not in the checkout at $tree"
    fails=$((fails + 1))
  elif [ "$local_sha" != "$remote_sha" ]; then
    echo "FAIL  $base differs: repo ${local_sha:0:16} vs checkout ${remote_sha:0:16}"
    fails=$((fails + 1))
  fi
done

buildtree=$(printf '%s\n' "$remote_out" | sed -n '/^BUILDTREE_BEGIN/,/^BUILDTREE_END/p' | sed '1d;$d')
if [ -n "$buildtree" ]; then
  echo "FAIL  the build tree differs from camoucrome/main (what export.sh exports):"
  printf '%s\n' "$buildtree" | sed 's/^/      /'
  echo "      commit it on camoucrome/main (checked out in the build tree) or check it out of the branch."
  fails=$((fails + 1))
fi

want=$(grep -v '^#' "$ROOT/patches/series" | sed '/^$/d' | while read -r p; do
  echo "PATCH $p $( (shasum -a 256 "$ROOT/patches/$p" 2>/dev/null || sha256sum "$ROOT/patches/$p" 2>/dev/null || echo MISSING) | cut -d' ' -f1)"
done)
got=$(printf '%s\n' "$remote_out" | grep '^PATCH ')
if [ "$want" != "$got" ]; then
  echo "FAIL  patches/ differs from what export.sh would write from camoucrome/main (< repo, > branch):"
  diff <(printf '%s\n' "$want") <(printf '%s\n' "$got") | grep '^[<>]' | sed 's/^/      /'
  fails=$((fails + 1))
fi

if [ "$fails" -ne 0 ]; then
  echo "$fails file(s) drifted. The repo is the source of truth: copy TO the"
  echo "checkout, commit there, and rebuild -- a header comment still forces a"
  echo "recompile of its dependents, and measuring the old binary proves nothing."
  exit 1
fi
echo "PASS  all ${#REPO_FILES[@]} copied files are identical in repo and checkout"
