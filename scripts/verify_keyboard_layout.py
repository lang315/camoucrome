"""Step 6 Task 2: navigator.keyboard.getLayoutMap() follows keyboard:layoutMap.

Under CAMOU_CONFIG {"keyboard:layoutMap": {KeyA: q, KeyQ: a, Backquote: 2-superscript, Digit1: &}} the page asks
getLayoutMap() for the four codes and compares.
  K1 (config): expected "4 of 4 match". RED before patches/keyboard-layout-map.patch: "0 of 4 match" (the map
     is the host's). The count is asserted, not the exit code.
  K2 (no config, rule 5): the four values equal a bare run's, i.e. the real map is untouched.
Run on a build that has the patch, with the box rule (build lock, no CPU contention) respected:

    ~/camoucrome-verify/venv/bin/python3 scripts/verify_keyboard_layout.py
"""
import json
import sys

import lib_shell

CODES = ("Backquote", "Digit1", "KeyA", "KeyQ")
AZERTY = {"KeyA": "q", "KeyQ": "a", "Backquote": "²", "Digit1": "&"}
JS = """async () => { const m = await navigator.keyboard.getLayoutMap();
  return JSON.stringify(%s.map(c => m.get(c))); }""" % json.dumps(list(CODES))


def read(config):
    vals, err = lib_shell.session(config, [JS])
    if err is not None or vals is None:
        return None, err
    return json.loads(vals[0]), None


def main():
    got, err = read(json.dumps({"keyboard:layoutMap": AZERTY}))
    if got is None:
        print(f"UNMEASURED K1: {err}")
        return 2
    n = sum(g == AZERTY[c] for c, g in zip(CODES, got))
    print(f"K1 {n} of {len(CODES)} match (got {got})")
    bare, err = read(None)
    bare2, _ = read(json.dumps({}))
    if bare is None or bare2 is None:
        print(f"UNMEASURED K2: {err}")
        return 2
    print(f"K2 {'PASS' if bare == bare2 else 'FAIL'}: bare {bare} vs empty config {bare2}")
    return 0 if n == len(CODES) and bare == bare2 else 1


if __name__ == "__main__":
    sys.exit(main())
