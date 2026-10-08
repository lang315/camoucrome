bash /home/lang/camoucrome-client/scripts/build_lock.sh release "s2c webgl fix"
set -e
cd ~/chromium-s2c/src
test "$(git branch --show-current)" = camoucrome/s2c
SP3A=$(git log --format=%H --grep='^sp3a-canvas-noise$' f89f3a4363..HEAD); test -n "$SP3A"
BUILDGN=$(git log -1 --format=%H f89f3a4363..HEAD -- components/camoucfg/BUILD.gn)
for f in $(git status --porcelain -uall components/camoucfg third_party/blink | awk '{print $2}'); do
  case "$f" in
    third_party/*) t=$SP3A ;;
    *) t=$(git log -1 --format=%H f89f3a4363..HEAD -- "$f"); t=${t:-$BUILDGN} ;;
  esac
  git add -- "$f"
  git commit -q --fixup="$t" -- "$f" || true
done
GIT_SEQUENCE_EDITOR=: git rebase -q -i --autosquash f89f3a4363
git log --format=%s f89f3a4363..HEAD | wc -l
git log --format=%s f89f3a4363..HEAD | grep -c fixup || true
git status --porcelain -- . ':(exclude)out' | wc -l
cd /tmp/s2c-tree && bash scripts/export.sh ~/chromium-s2c/src camoucrome/s2c 2>&1 | tail -3
sed 's#camoucrome/main#camoucrome/s2c#g' scripts/check_checkout_sync.sh > scripts/check_sync_s2c.sh
bash scripts/check_sync_s2c.sh local ~/chromium-s2c/src | tail -1
(find additions patches -type f; echo settings/invariants.json) | sort | xargs sha256sum > /tmp/s2c/export.sums
wc -l /tmp/s2c/export.sums
cd /tmp/s2c-tree && cat patches/sp3a-canvas-noise.patch | sha256sum; wc -c patches/sp3a-canvas-noise.patch
git -C ~/chromium-s2c/src log --oneline -1 | cut -c1-60
