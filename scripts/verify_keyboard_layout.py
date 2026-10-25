"""Step 6 Task 2: navigator.keyboard.getLayoutMap() follows keyboard:layoutMap.

Under CAMOU_CONFIG {"keyboard:layoutMap": {KeyA: q, KeyQ: a, Backquote: 2-superscript, Digit1: &}} the page asks
getLayoutMap() for the four codes and compares.
  K1 (config): expected "4 of 4 match". RED before patches/keyboard-layout-map.patch: "0 of 4 match" (the map
     is the host's). The count is asserted, not the exit code.
  K2 (no layout key, rule 5): a run with an unrelated key set gives the bare run's four values, i.e. the real map is untouched.
Run on a build that has the patch, with the box rule (build lock, no CPU contention) respected:

    ~/camoucrome-verify/venv/bin/python3 scripts/verify_keyboard_layout.py
"""
import json
import sys

import lib_shell

CODES = ("Backquote", "Digit1", "KeyA", "KeyQ")
AZERTY = {"KeyA": "q", "KeyQ": "a", "Backquote": "²", "Digit1": "&"}
# page.evaluate calls a function string and awaits its promise (siblings do the same). A rejection or a missing
# navigator.keyboard returns {"err"}: UNMEASURED, never "0 of 4".
JS = """async () => { try { const m = await navigator.keyboard.getLayoutMap();
  return JSON.stringify(%s.map(c => m.get(c))); } catch (e) { return JSON.stringify({err: String(e)}); } }""" % json.dumps(list(CODES))


def read(config):
    vals, err = lib_shell.session(config, [JS])
    if err is not None or vals is None:
        return None, err
    got = json.loads(vals[0])
    if isinstance(got, dict):
        return None, got["err"]
    return got, None


def main():
    got, err = read(json.dumps({"keyboard:layoutMap": AZERTY}))
    if got is None:
        print(f"UNMEASURED K1: {err}")
        return 2
    n = sum(g == AZERTY[c] for c, g in zip(CODES, got))
    print(f"K1 {n} of {len(CODES)} match (got {got})")
    bare, err = read(None)
    other, err2 = read(json.dumps({"window.outerWidth": 1000}))  # an unrelated key: no layout spoof without ours
    if bare is None or other is None:
        print(f"UNMEASURED K2: {err or err2}")
        return 2
    print(f"K2 {'PASS' if bare == other else 'FAIL'}: bare {bare} vs unrelated-key config {other}")
    return 0 if n == len(CODES) and bare == other else 1


if __name__ == "__main__":
    sys.exit(main())
