#!/usr/bin/env python3
"""The browser verifies CI runs (scripts/ci_verify_set.txt).

  ci_verify_set.py list    "<script> <KEY=VAL ...>" for each `run` line, in order (build-verify.yml loops over it)
  ci_verify_set.py check   exit 1 unless every scripts/verify_*.py is on the list exactly once and every
                           scripts/measure_*.py is on scripts/measure_set.txt with a `where=`

A `run` line's `unmeasured-ok` word is printed right after the script name, before the KEY=VAL words.
"""
import collections
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
Entry = collections.namedtuple("Entry", "kind script env reason unmeasured_ok where")
WHERES = ("box", "host", "manual", "retired")


def where_of(reason):
    m = re.match(r"where=(\w+):\s*\S", reason)
    return m.group(1) if m and m.group(1) in WHERES else None


def parse(text, kinds=("run", "external", "skip"), name=r"verify_\w+\.py"):
    out = []
    for n, raw in enumerate(text.splitlines(), 1):
        body, _, reason = raw.partition("#")
        words = body.split()
        if not words:
            continue
        kind, script, env = words[0], (words[1] if len(words) > 1 else ""), words[2:]
        if kind not in kinds or not re.fullmatch(name, script):
            raise ValueError(f"line {n}: expected `{'|'.join(kinds)} {name}`, got {raw!r}")
        ok = kind == "run" and env[:1] == ["unmeasured-ok"]
        env = env[ok:]
        if kind != "run" and env or any(not re.fullmatch(r"[A-Z_][A-Z0-9_]*=\S*", e) for e in env):
            raise ValueError(f"line {n}: only `run` takes [unmeasured-ok] KEY=VAL words, and they must look like that: {raw!r}")
        if kind != "run" and not reason.strip():
            raise ValueError(f"line {n}: a {kind} line needs a reason after #")
        where = where_of(reason.strip()) if kind in ("skip", "measure") else None
        if kind in ("skip", "measure") and not where:
            raise ValueError(f"line {n}: a {kind} line's reason must start `where=<{'|'.join(WHERES)}>: why`: {raw!r}")
        out.append(Entry(kind, script, env, reason.strip(), ok, where))
    return out


def parse_measure(text):
    return parse(text, kinds=("measure",), name=r"measure_\w+\.py")


def load():
    return parse((HERE / "ci_verify_set.txt").read_text())


def load_measure():
    return parse_measure((HERE / "measure_set.txt").read_text())


def check_measure(entries, scripts_dir):
    names = [e.script for e in entries]
    on_disk = sorted(p.name for p in pathlib.Path(scripts_dir).glob("measure_*.py"))
    problems = [f"{n} is listed twice" for n, c in collections.Counter(names).items() if c > 1]
    problems += [f"{n} is listed but does not exist" for n in names if n not in on_disk]
    problems += [f"{n} is not in measure_set.txt (measure <script>  # where=<box|host|manual|retired>: why)" for n in on_disk if n not in names]
    return problems


def check(entries, scripts_dir):
    names = [e.script for e in entries]
    on_disk = sorted(p.name for p in pathlib.Path(scripts_dir).glob("verify_*.py"))
    problems = [f"{n} is listed twice" for n, c in collections.Counter(names).items() if c > 1]
    problems += [f"{n} is listed but does not exist" for n in names if n not in on_disk]
    problems += [f"{n} is not in ci_verify_set.txt (run, external or skip with a reason)" for n in on_disk if n not in names]
    return problems


def listing(entries):
    return [" ".join([e.script, *(["unmeasured-ok"] if e.unmeasured_ok else []), *e.env]) for e in entries if e.kind == "run"]


def main(argv):
    if argv[:1] == ["list"]:
        print("\n".join(listing(load())))
        return 0
    if argv[:1] == ["check"]:
        problems = check(load(), HERE) + check_measure(load_measure(), HERE)
        print("\n".join(problems) or "ci_verify_set: ok")
        return 1 if problems else 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
