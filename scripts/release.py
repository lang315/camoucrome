#!/usr/bin/env python3
"""Create a DRAFT GitHub Release from built archives. Never publishes: that is the owner's step.

  release.py <tag> --stamp <win.json> --stamp <linux.json> [--asset F]... [--tables DIR] --notes FILE
             [--release-commit SHA]

--release-commit is for a client-only release that reuses binaries built at an earlier commit. SHA must be an
ancestor of origin/main, and from the stamps' commit to SHA the change set (patches, additions, the GN args)
may differ only in `//` comment lines of additions/camoucfg/keys.h. CI, `--target` and the notes then name SHA.

Exit 0 after `gh release create --draft`; exit 2 with the reason on any refusal.
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import check_privacy  # noqa: E402
import package  # noqa: E402

TAG_RE = re.compile(r"^v(\d+\.\d+\.\d+\.\d+)-\d+$")
TEXT_SUFFIXES = check_privacy.TEXT_SUFFIXES
WORKFLOWS = ("checks", "build-verify")
CHANGE_SET = ("patches", "additions", "settings/build-args.gn", "settings/release-args.gn")
COMMENT_ONLY_FILES = ("additions/camoucfg/keys.h",)


def gh(args):
    p = subprocess.run(["gh", *args], capture_output=True, text=True)
    return p.returncode, p.stdout


def origin_main():
    subprocess.run(["git", "fetch", "-q", "origin"], check=True)
    return subprocess.run(["git", "rev-parse", "origin/main"], check=True, capture_output=True, text=True).stdout.strip()


def is_ancestor(sha, ref):
    return subprocess.run(["git", "merge-base", "--is-ancestor", sha, ref]).returncode == 0


def change_set_diff(old, new):
    return subprocess.run(["git", "diff", "-U0", old, new, "--", *CHANGE_SET],
                          check=True, capture_output=True, text=True).stdout


def comment_only(diff):
    """True when every changed line of a `git diff -U0` is a `//` comment line of a COMMENT_ONLY_FILES file.
    Any other header (rename, mode change, binary, new or deleted file) is not."""
    path = None
    for line in diff.splitlines():
        if not line:
            continue
        if line.startswith("diff --git "):
            path = line.split(" b/", 1)[1]
        elif line.startswith(("index ", "--- ", "+++ ", "@@")):
            continue
        elif line[:1] in "+-":
            if path not in COMMENT_ONLY_FILES or not line[1:].lstrip().startswith("//"):
                return False
        else:
            return False
    return True


def privacy_hits(path):
    here = pathlib.Path(__file__).resolve().parent
    p = subprocess.run([sys.executable, str(here / "check_privacy.py"), "--file", str(path)],
                       capture_output=True, text=True)
    m = re.search(r"check_privacy: (\d+) hit", p.stdout + p.stderr)
    return int(m.group(1)) if m else 1  # unparseable output counts as a hit


def members(path):
    """(name, bytes) of each file in a .zip, .tar, .tgz or .tar.*, one at a time, in memory;
    any other asset is one member, itself."""
    name = pathlib.Path(path).name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            for i in z.infolist():
                if not i.is_dir():
                    yield i.filename, z.read(i)
    elif name.endswith((".tar", ".tgz")) or ".tar." in name:
        with tarfile.open(path) as t:
            for m in t:
                if m.isfile():
                    yield m.name, t.extractfile(m).read()
    else:
        yield pathlib.Path(path).name, pathlib.Path(path).read_bytes()


def scan_archive(path, terms):
    """(member, placeholder) for every member of an asset whose bytes hold a private term."""
    return [(n, h) for n, data in members(path) for h in check_privacy.byte_hits(data, terms, n)]


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
    ap.add_argument("--release-commit", metavar="SHA")
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
    built = stamps[0]["changeset_commit"]
    main_sha = origin_main()
    sha = a.release_commit or built
    if a.release_commit:
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            return refuse("--release-commit must be a full 40-hex sha")
        if any(s["changeset_commit"] != built for s in stamps):
            return refuse("stamps disagree on changeset_commit")
        if not is_ancestor(sha, main_sha):
            return refuse(f"--release-commit {sha} is not an ancestor of origin/main ({main_sha})")
        if not is_ancestor(built, sha):
            return refuse(f"the stamps' commit {built} is not an ancestor of --release-commit")
        if not comment_only(change_set_diff(built, sha)):
            return refuse(f"the change set differs between the stamps' commit {built} and {sha} by more than keys.h comments: "
                          "the binaries are not this commit's")
    elif any(s["changeset_commit"] != main_sha for s in stamps):
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

    terms = check_privacy.load_terms()
    if not check_privacy.term_count(terms):
        return refuse("0 non-empty private terms loaded: the archive scan would measure nothing "
                      "(PRIVATE_TERMS or ~/.config/camoucrome/private-terms.json)")
    if not check_privacy.identity_term_count(terms):
        return refuse("0 non-empty identity (non-GEO) private terms loaded: binaries would be scanned for nothing")
    for p in a.stamp:
        found = check_privacy.byte_hits(pathlib.Path(p).read_bytes(), terms, p)
        if found:
            return refuse(f"{p} holds a private term ({found[0]})")
    notes_text = pathlib.Path(a.notes).read_text()
    for named in dict.fromkeys((sha, built)):
        if named not in notes_text:
            return refuse(f"--notes does not contain the full changeset sha {named} (the README's <sha> is read from there)")
    stamp_bytes = [pathlib.Path(p).read_bytes() for p in a.stamp]
    # platform archive = name starts camoucrome-<version>-, so the npm tarball (camoucrome-0.1.0.tgz) is not one
    prefix = f"camoucrome-{m.group(1)}-"
    for p in a.asset:
        n = pathlib.Path(p).name
        if n.startswith(prefix) and n.lower().endswith((".zip", ".tar", ".tgz")) or n.startswith(prefix) and ".tar." in n.lower():
            try:
                embedded = [d for name, d in members(p) if re.fullmatch(r"[^/]+/camoucrome-release\.json", name)]
            except (zipfile.BadZipFile, tarfile.TarError, RuntimeError, NotImplementedError) as e:
                return refuse(f"{p} is not a readable archive: {e}")
            if len(embedded) != 1 or embedded[0] not in stamp_bytes:
                return refuse(f"{p}: embedded camoucrome-release.json is missing or matches no --stamp")
    for p in a.asset:
        try:
            for member, label in scan_archive(p, terms):
                return refuse(f"{p}: member {member} holds a private term ({label})")
        # RuntimeError: an encrypted zip member; NotImplementedError: an unsupported compression method
        except (zipfile.BadZipFile, tarfile.TarError, RuntimeError, NotImplementedError) as e:
            return refuse(f"{p} is not a readable archive: {e}")

    tables = sorted(p for p in pathlib.Path(a.tables).rglob("*") if p.is_file()) if a.tables else []
    text = [a.notes] + [p for p in a.asset if pathlib.Path(p).suffix.lower() in TEXT_SUFFIXES] + [str(p) for p in tables]
    for p in text:
        if privacy_hits(p):
            return refuse(f"check_privacy hit in {p}")

    d = pathlib.Path(a.asset[0]).parent if a.asset else pathlib.Path(tempfile.mkdtemp())
    sums = d / "SHA256SUMS"
    sums.write_text(sha256sums(a.asset))
    rc, out = gh(["release", "create", a.tag, "--draft", "--target", sha, "--title", a.tag, "--notes-file", a.notes,
                  *a.asset, str(sums), *map(str, tables)])
    if rc != 0:
        return refuse("gh release create failed")
    print(out.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
