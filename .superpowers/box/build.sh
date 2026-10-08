# usage: build.sh <edits-file-in-box-dir> <log>
cd ~/chromium-s2c/src
python3 /tmp/s2c/apply_edits.py /tmp/s2c-tree/.superpowers/box/$1 || exit 1
cat > /tmp/s2c/b.sh <<'EOT'
cd ~/chromium-s2c/src && export PATH=/home/lang/depot_tools:$PATH
autoninja -C out/Default content_shell components_unittests 2>&1 | tail -4
echo BUILD_DONE
EOT
setsid nohup bash /tmp/s2c/b.sh < /dev/null > ~/$2 2>&1 &
sleep 1; echo started
