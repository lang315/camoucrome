#!/usr/bin/env python3
"""Create a DRAFT GitHub Release from built archives. Never publishes: that is the owner's step.

  release.py <tag> --stamp <win.json> --stamp <linux.json> [--asset F]... [--tables DIR] --notes FILE

Exit 0 after `gh release create --draft`; exit 2 with the reason on any refusal.
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import package  # noqa: E402

TAG_RE = re.compile(r"^v(\d+\.\d+\.\d+\.\d+)-\d+$")
TEXT_SUFFIXES = {".md", ".txt", ".json", ".csv", ".tsv"}
WORKFLOWS = ("checks", "build-verify")


def gh(args):
    p = subprocess.run(["gh", *args], capture_output=True, text=True)
    return p.returncode, p.stdout


def origin_main():
    subprocess.run(["git", "fetch", "-q", "origin"], check=True)
    return subprocess.run(["git", "rev-parse", "origin/main"], check=True, capture_output=True, text=True).stdout.strip()


def privacy_hits(path):
    here = pathlib.Path(__file__).resolve().parent
    p = subprocess.run([sys.executable, str(here / "check_privacy.py"), "--file", str(path)],
                       capture_output=True, text=True)
    m = re.search(r"check_privacy: (\d+) hit", p.stdout + p.stderr)
    return int(m.group(1)) if m else 1  # unparseable output counts as a hit


def release_listed(tag):
    """True when a release or draft with this tag exists (`release view` does not see drafts)."""
    rc, out = gh(["release", "list", "--json", "tagName,isDraft", "--limit", "1000"])
    if rc != 0:
        raise RuntimeError("gh release list failed")
    return any(r.get("tagName") == tag for r in json.loads(out or "[]"))


def remote_tag(tag):
    p = subprocess.run(["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"],
                       capture_output=True, text=True, check=True)
    return bool(p.stdout.strip())


def sha256sums(paths):
    return "".join(f"{hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()}  {pathlib.Path(p).name}\n"
                   for p in paths)


def refuse(msg):
    print(f"release: refused: {msg}", file=sys.stderr)
    return 2


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--stamp", action="append", required=True)
    ap.add_argument("--asset", action="append", default=[])
    ap.add_argument("--tables")
    ap.add_argument("--notes", required=True)
    a = ap.parse_args(argv)

    if len(a.stamp) < 2:
        return refuse("need at least 2 --stamp")
    m = TAG_RE.match(a.tag)
    if not m:
        return refuse(f"tag {a.tag!r} does not match vA.B.C.D-N")
    stamps = [json.loads(pathlib.Path(s).read_text()) for s in a.stamp]
    if any(s["version"] != m.group(1) for s in stamps):
        return refuse("tag version differs from the stamps' version")
    try:
        package.check(a.stamp)
    except SystemExit as e:
        return refuse(f"stamps disagree: {e}")
    sha = stamps[0]["changeset_commit"]
    main_sha = origin_main()
    if any(s["changeset_commit"] != main_sha for s in stamps):
        return refuse(f"stamps' changeset_commit is not origin/main ({main_sha})")
    rc, out = gh(["run", "list", "--commit", sha, "--json", "workflowName,conclusion"])
    runs = json.loads(out) if rc == 0 and out else []
    for w in WORKFLOWS:
        if not any(r.get("workflowName") == w and r.get("conclusion") == "success" for r in runs):
            return refuse(f"CI {w} is not success on {sha}")
    if release_listed(a.tag):
        return refuse(f"a release or draft {a.tag} exists")
    if remote_tag(a.tag):
        return refuse(f"tag {a.tag} exists on the remote")
    for p in a.asset:
        if not pathlib.Path(p).is_file():
            return refuse(f"asset {p} is not a file")
    if a.tables and not pathlib.Path(a.tables).is_dir():
        return refuse(f"--tables {a.tables} is not a directory")

    tables = sorted(p for p in pathlib.Path(a.tables).rglob("*") if p.is_file()) if a.tables else []
    text = [a.notes] + [p for p in a.asset if pathlib.Path(p).suffix.lower() in TEXT_SUFFIXES] + [str(p) for p in tables]
    for p in text:
        if privacy_hits(p):
            return refuse(f"check_privacy hit in {p}")

    d = pathlib.Path(a.asset[0]).parent if a.asset else pathlib.Path(tempfile.mkdtemp())
    sums = d / "SHA256SUMS"
    sums.write_text(sha256sums(a.asset))
    rc, out = gh(["release", "create", a.tag, "--draft", "--title", a.tag, "--notes-file", a.notes,
                  *a.asset, str(sums), *map(str, tables)])
    if rc != 0:
        return refuse("gh release create failed")
    print(out.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
