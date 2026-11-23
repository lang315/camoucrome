# Sourced by apply.sh, export.sh, rebuild_branch.sh and check_checkout_sync.sh.
# The Python twin is lib_additions.py; scripts/test_lib_additions.py keeps them equal.
_LIB_ADDITIONS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The one rule for patches/series and additions_map.txt: trim each line, drop
# blank lines and lines starting with '#'.
series_list() {
  sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e '/^#/d' -e '/^$/d' "$1"
}

# "additions/<dir> <tree dir>" per line, paths relative to the repo / the tree.
additions_map() {
  series_list "$_LIB_ADDITIONS_DIR/additions_map.txt"
}

# copy_additions <repo root> <tree root>: every mapped dir that exists, whole.
copy_additions() {
  local a t
  while read -r a t; do
    [ -d "$1/$a" ] || continue
    mkdir -p "$2/$t"
    cp -R "$1/$a/." "$2/$t/"
  done < <(additions_map)
}
