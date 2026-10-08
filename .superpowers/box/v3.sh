cd ~/chromium-s2c/src && export PATH=/home/lang/depot_tools:/usr/bin:$PATH
out/Default/components_unittests --gtest_filter='PerturbRgba*:CanvasNoise*:NoisedImage*:NoisedRegion*:CanvasNoiseMask*:Derive*' 2>&1 | grep -E '^\[  (PASSED|FAILED) |FAILED TEST' | sort | uniq -c
gn check out/Default //third_party/blink/renderer/modules/webgl:webgl 2>&1 | tail -1
python3 buildtools/checkdeps/checkdeps.py third_party/blink/renderer/modules/webgl 2>&1 | tail -3
export CAMOU_OUT=/home/lang/chromium-s2c/src/out/Default
cd ~/camoucrome-verify
venv/bin/python3 /tmp/s2c-tree/scripts/verify_sp3a.py > /tmp/s2c/sp3a.out 2>&1; echo sp3a_rc=$?
grep -E '^FAIL' /tmp/s2c/sp3a.out; grep -c '^PASS' /tmp/s2c/sp3a.out; grep -E '^PASS +(37|41|28|36|17|18|19|20|29|35|38)' /tmp/s2c/sp3a.out | cut -c1-60; grep -E '^ +[0-9]+ :' /tmp/s2c/sp3a.out | cut -c1-300
venv/bin/python3 /tmp/s2c-tree/scripts/verify_review_2026_09_24.py 2>&1 | tail -1
echo ---COST
venv/bin/python3 /tmp/s2c-tree/scripts/measure_canvas_cost.py 2>&1 | grep -E '^(gl_|target)'
