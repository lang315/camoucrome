#!/usr/bin/env python3
"""Refuse host-identifying data in what this public repository publishes.

  check_privacy.py                  every tracked file in the working tree
  check_privacy.py --staged         the index (the pre-commit hook)
  check_privacy.py --file PATH      one file: a PR body, a comment, a commit message
  check_privacy.py --range REVS     messages and date offsets of `git rev-list REVS` (e.g. A..B, HEAD, --all)
  check_privacy.py --history        every blob and path reachable from every ref
  check_privacy.py --ci             tracked files, then the range of the push or PR in $PR_BASE/$PR_HEAD/$BEFORE
  ... --require-terms               exit 2 when no private terms load (a check with none measures nothing)

Host-specific strings (zone names, offsets, machine and place names) come from $PRIVATE_TERMS, or
else ~/.config/camoucrome/private-terms.json, in CAMOU_SCRUB's shape {placeholder: [strings]};
neither is ever committed. A hit prints where and which category, never the matched text, so a CI
log does not re-publish it. Exit 1 on any hit.
"""
import argparse
import ipaddress
import json
import os
import pathlib
import re
import subprocess
import sys

# Product data: what the fork emulates, not the host (spec 2026-10-18 §1).
ALLOW_PATHS = {"settings/locale_zones.json", "settings/voices.json", "settings/invariants.json"}
# Addresses that are not the host's, each with where it comes from.
ALLOW_IPS = {
    "1.2.3.4": "placeholder address in the SP1a and SP4 plans",
    "192.168.1.37": "the configured fake webrtc:localipv4 (WebRTC II)",
    "156.0.1.1": "a version string in the step2 version tests",
    "205.185.123.167": "tls.peet.ws's own server address in scripts/fixtures/step2/peet.json",
}
# The gate's own code, tests and design docs quote the generic patterns as examples: private terms only.
GATE_FILES = {"scripts/check_privacy.py", "scripts/test_check_privacy.py", "scripts/test_capture_host_oracle.py",
              "scripts/test_measure_step2_scrub.py",
              "docs/superpowers/specs/2026-10-18-public-repo-scrub-design.md",
              "docs/superpowers/plans/2026-10-18-public-repo-scrub.md"}
_SEP = r"(?:/|\\{1,2})"
GENERIC = {
    "machine-name": re.compile(r"\bDESKTOP-[A-Z0-9]{7}\b"),
    "windows-profile": re.compile(rf"(?i)\b[A-Z]:{_SEP}Users{_SEP}(?!<|user\b|public\b|default\b)[\w.-]+"),
    # a home directory with a name after it, not inside a longer path ("ui/webui/home/x"), or a WSL UNC path
    "home-path": re.compile(rf"(?<![\w.-]){_SEP}(?:home|Users){_SEP}(?!<|runner\b|user\b|Shared\b)[A-Za-z_][\w.-]*"
                            r"|(?i:\\\\wsl(?:\.localhost|\$)\\[^\\\s]+\\home\\(?!<)[A-Za-z_])"),
    "home-slug": re.compile(r"(?:(?<=[/\s`'\"(])|^)-(?:home|Users)-(?!<)[a-z][a-z0-9_]*-"),
    "tailnet": re.compile(r"\.ts\.net\b"),
    "session-link": re.compile(r"claude\.ai/code/session"),
    # a clock time labelled with a zone abbreviation other than UTC/GMT ("16:37 XST")
    "local-clock": re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s+(?!UTC\b|GMT\b)[A-Z]{2,4}T\b"),
}
_OCTET = r"(?:25[0-5]|2[0-4]\d|1?\d?\d)"
IPV4 = re.compile(rf"(?<![\d.]){_OCTET}(?:\.{_OCTET}){{3}}(?!\d|\.\d)")
DOC_NETS = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]


def load_terms():
    raw = os.environ.get("PRIVATE_TERMS")
    if raw is None:
        f = pathlib.Path(os.path.expanduser("~/.config/camoucrome/private-terms.json"))
        raw = f.read_text(encoding="utf-8") if f.exists() else ""
    terms = json.loads(raw) if raw.strip() else {}
    if not isinstance(terms, dict) or not all(isinstance(v, list) and all(isinstance(s, str) for s in v)
                                              for v in terms.values()):
        sys.exit("check_privacy: private terms must be a JSON object {placeholder: [strings]}")
    return terms


def _ip_hit(s):
    if re.fullmatch(r"\d+\.0\.0\.0", s) or s in ALLOW_IPS:  # a reduced UA version, or a known non-host address
        return False
    a = ipaddress.ip_address(s)
    return not (a.is_loopback or a.is_unspecified or a.is_multicast or a.is_reserved or a.is_link_local
                or any(a in n for n in DOC_NETS))


def hits(text, terms, generic=True):
    needles = [(label, n.lower()) for label, ns in terms.items() for n in ns if n]
    out = set()
    for i, line in enumerate(text.splitlines(), 1):
        if generic:
            for cat, rx in GENERIC.items():
                if rx.search(line):
                    out.add((i, cat))
            if any(_ip_hit(m.group(0)) for m in IPV4.finditer(line)):
                out.add((i, "ip"))
        low = line.lower()
        for label, n in needles:
            if n in low:
                out.add((i, label))
    return sorted(out)


def _git(*a, inp=None):
    return subprocess.run(["git", *a], input=inp, capture_output=True, check=True).stdout


def _text(data):
    return None if b"\0" in data[:8000] else data.decode("utf-8", "replace")


def _name(p, n, terms):
    """How a path is printed: itself, or `<path #n>` when the path itself is a hit (printing it would leak)."""
    cats = {c for _, c in hits(p, terms, generic=p not in GATE_FILES)}
    return (f"<path #{n}>", [f"<path #{n}>: path {c}" for c in sorted(cats)]) if cats else (p, [])


def _scan(paths, read, terms):
    bad = []
    for n, p in enumerate(paths, 1):
        name, path_hits = _name(p, n, terms)
        bad += path_hits
        if p in ALLOW_PATHS:
            continue
        t = _text(read(p))
        if t is not None:
            bad += [f"{name}:{i}: {c}" for i, c in hits(t, terms, generic=p not in GATE_FILES)]
    return bad


def _tracked(terms):
    paths = [p for p in _git("ls-files", "-z").decode().split("\0") if p and os.path.isfile(p)]
    return _scan(paths, lambda p: pathlib.Path(p).read_bytes(), terms)


def _staged(terms):
    paths = [p for p in _git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR").decode().split("\0") if p]
    return _scan(paths, lambda p: _git("show", f":{p}"), terms)


def _range(revs, terms):
    bad = []
    log = _git("log", "--format=%H%x00%ae%x00%ce%x00%ai%x00%ci%x00%B%x01", *revs.split())
    for rec in log.split(b"\x01"):
        rec = rec.strip(b"\n")
        if not rec:
            continue
        sha, ae, ce, ai, ci, msg = rec.split(b"\0", 5)
        s = sha.decode()[:10]
        # no exemption for GitHub-made commits: its web merges carry the owner's offset (all 40 before 2026-10-18)
        if not (ai.endswith(b"+0000") and ci.endswith(b"+0000")):
            bad.append(f"{s}: date offset not +0000 (commit with TZ=UTC)")
        bad += [f"{s}: message line {i}: {c}" for i, c in hits(msg.decode("utf-8", "replace"), terms)]
    return bad


def _history(terms):
    path_of, names, bad = {}, {}, set()
    for line in _git("rev-list", "--objects", "--all").decode().splitlines():
        sha, _, p = line.partition(" ")
        if p:
            path_of.setdefault(sha, p)
            if p not in names:
                names[p], path_hits = _name(p, len(names) + 1, terms)
                bad |= {f"history {h}" for h in path_hits}
    kinds = _git("cat-file", "--batch-check=%(objectname) %(objecttype)", inp="\n".join(path_of).encode()).decode()
    blobs = [k.split()[0] for k in kinds.splitlines() if k.endswith(" blob") and path_of[k.split()[0]] not in ALLOW_PATHS]
    data, i = _git("cat-file", "--batch", inp="\n".join(blobs).encode()), 0
    while i < len(data):
        nl = data.index(b"\n", i)
        sha, _t, size = data[i:nl].decode().split()
        body = data[nl + 1:nl + 1 + int(size)]
        i = nl + 1 + int(size) + 1
        t, p = _text(body), path_of[sha]
        if t is not None:
            bad |= {f"history {names[p]}: {c}" for _, c in hits(t, terms, generic=p not in GATE_FILES)}
    return sorted(bad)


def _ci_revs():
    base, head, before = (os.environ.get(k, "") for k in ("PR_BASE", "PR_HEAD", "BEFORE"))
    if base:
        return f"{base}..{head}"
    known = subprocess.run(["git", "cat-file", "-e", f"{before}^{{commit}}"], capture_output=True).returncode == 0
    if before and set(before) != {"0"} and known:
        return f"{before}..HEAD"
    return "HEAD"  # a new branch, or a force-push whose old tip is gone: the whole history


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--staged", action="store_true")
    g.add_argument("--file")
    g.add_argument("--range", metavar="REVS")
    g.add_argument("--history", action="store_true")
    g.add_argument("--ci", action="store_true")
    ap.add_argument("--require-terms", action="store_true")
    a = ap.parse_args(argv)
    terms = load_terms()
    if a.require_terms and not terms:
        print("check_privacy: --require-terms, and no private terms loaded", file=sys.stderr)
        return 2
    if a.ci:
        bad = _tracked(terms) + _range(_ci_revs(), terms)
    elif a.staged:
        bad = _staged(terms)
    elif a.file:
        bad = _scan([a.file], lambda p: pathlib.Path(p).read_bytes(), terms)
    elif a.range:
        bad = _range(a.range, terms)
    elif a.history:
        bad = _history(terms)
    else:
        bad = _tracked(terms)
    for b in bad:
        print(b)
    print(f"check_privacy: {len(bad)} hit(s); {sum(map(len, terms.values()))} private terms loaded", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
