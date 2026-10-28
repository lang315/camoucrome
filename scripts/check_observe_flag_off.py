"""F0 gate for the tracking observer: with camou_observe = false every observer call compiles to nothing.

Recompiles two objects of an existing out dir with BUILDFLAG(CAMOU_OBSERVE) forced to 0 (a shadow
buildflags.h placed first on the include path) and checks with nm that:
  - the flag-on objects the build produced DO reference the observer (a check that cannot fail
    on a stripped object measures nothing), and
  - the flag-off recompiles reference none of camou_observe::Emit / EmitListener / CountDispatch.
Usage (on the build box, tree root as cwd or --src): check_observe_flag_off.py [--src ~/chromium/src] [--out out/Default]
Compiles two files: a minute, no ninja state is touched.
"""
import argparse
import os
import shlex
import subprocess
import sys
import tempfile

OBJECTS = ("obj/third_party/blink/renderer/core/core/event_target.o",
           "obj/third_party/blink/renderer/bindings/core/v8/v8/v8_performance.o")
FLAG = "BUILDFLAG_INTERNAL_CAMOU_OBSERVE() (1)"
RELPATH = "third_party/blink/renderer/platform/bindings/buildflags.h"


def references_observer(nm_output):
    return "camou_observe::Emit" in nm_output or "camou_observe::CountDispatch" in nm_output


def nm(path):
    return subprocess.run(["nm", "-C", path], capture_output=True, text=True, check=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.expanduser("~/chromium/src"))
    ap.add_argument("--out", default="out/Default")
    a = ap.parse_args()
    out = os.path.join(a.src, a.out)
    header = open(os.path.join(out, "gen", RELPATH)).read()
    if FLAG not in header:
        print("FAIL the out dir was not built with camou_observe = true; nothing to compare")
        return 1
    tmp = tempfile.mkdtemp(prefix="camoucrome-flagoff-")
    shadow = os.path.join(tmp, "shadow", RELPATH)
    os.makedirs(os.path.dirname(shadow))
    open(shadow, "w").write(header.replace(FLAG, "BUILDFLAG_INTERNAL_CAMOU_OBSERVE() (0)"))
    ok = True
    for obj in OBJECTS:
        on = references_observer(nm(os.path.join(out, obj)))
        # the command list can hold non-UTF-8 bytes (other targets' flags): decode leniently
        cmd = subprocess.run(["ninja", "-C", out, "-t", "commands", obj], capture_output=True,
                             check=True).stdout.decode("utf-8", "replace").strip().splitlines()[-1]
        argv = shlex.split(cmd)
        i = argv.index("-o")
        new_o = os.path.join(tmp, os.path.basename(obj))
        argv[i + 1] = new_o
        for flag in ("-MMD",):
            if flag in argv:
                argv.remove(flag)
        if "-MF" in argv:
            j = argv.index("-MF")
            del argv[j:j + 2]
        argv.insert(1, "-I" + os.path.join(tmp, "shadow"))
        subprocess.run(argv, cwd=out, check=True)
        off = references_observer(nm(new_o))
        good = on and not off
        ok &= good
        print(f"{'PASS' if good else 'FAIL'} {os.path.basename(obj)}: flag on references the observer: {on}; "
              f"flag off references it: {off} (want True / False)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
