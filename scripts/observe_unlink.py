"""Facebook profile unlinking (social mode part 2): which fields link three fork profiles on one host.

Runs on the host after observe-auto's lf and lc arms. It reads each arm's capture, compares
values across profiles in memory, and writes only field names, value classes, counts and classes
(spec docs/superpowers/specs/2026-10-30-fb-unlink-design.md, local).
"""
import argparse
import collections
import hashlib
import json
import pathlib
import sys
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import observe_drive as d  # noqa: E402

ENDPOINTS = ("/ajax/bz", "/ajax/qm/", "/ajax/webstorage/process_keys/")


def endpoint_path(url):
    p = urllib.parse.urlsplit(url).path.rstrip("/")
    return next((e for e in ENDPOINTS if e.rstrip("/") == p), None)


def profile_values(requests):
    """{"<endpoint> <path>": [values]} over one profile's captured POST bodies on ENDPOINTS."""
    out = collections.defaultdict(list)
    for r in requests:
        ep = None if r.get("missing") else endpoint_path(r.get("url", ""))
        if ep:
            for path, v in d.fields(d._b64(r["body_b64"]), r.get("content_type", ""))[1]:
                out[f"{ep} {path}"].append(v)
    return dict(out)


def _form(v):
    # shortcut: an opaque part keeps only its length, so two opaque parts of one length read as equal; multipart file parts only
    return json.dumps(v, sort_keys=True, default=lambda o: f"opaque<{getattr(o, 'n', '?')}>")


def digest(values):
    """One profile's values for a path, order-free: the hash of its sorted distinct forms."""
    return hashlib.sha256("\n".join(sorted({_form(v) for v in values})).encode()).hexdigest()


def field_key(path, fields):
    """The fb_fields.json key a captured path belongs to: equal to it, or ending in '.' + key (longest key wins)."""
    p = path.split(" ", 1)[1]
    for k in sorted(fields, key=len, reverse=True):
        if p == k or p.endswith("." + k):
            return k
    return None


def _same(a, b):
    return type(a) is type(b) and a == b  # step2_rows._same: type-strict, so True is not 1


def explain(key, doc, constants, accepted, fork_vals, stock_vals):
    """Why a gap is acceptable, or None: an owner limit, a machine constant, or an accepted default (ruling R6)."""
    if key in doc.get("limits", {}):
        return "limit"
    leaves = (doc["fields"].get(key) or {}).get("leaves") or []
    prefixes = tuple(k for k in constants if k.endswith("."))  # step2_rows.unexplained: a key ending in '.' is a prefix
    if any(leaf in constants or leaf.startswith(prefixes) for leaf in leaves):
        return "machine-constant"
    for leaf in leaves:
        row = accepted.get(leaf)
        if row and stock_vals and all(_same(v, row["value"]) for v in fork_vals + stock_vals):
            return "accepted-default"
    return None


def classify(fork, stock, doc, constants, accepted):
    """fork, stock: one profile_values() dict per profile. Returns the unlink document (no values)."""
    fields, ip_bound = doc["fields"], set(doc["ip_bound"])
    rows, counts = [], collections.Counter()
    paths = sorted(set().union(*fork, *stock))
    for path in paths:
        fv = [p[path] for p in fork if path in p]
        sv = [p[path] for p in stock if path in p]
        key = field_key(path, fields)
        fd, sd = len({digest(v) for v in fv}), len({digest(v) for v in sv})
        r = {"field": path, "key": key, "value_class": d.value_class((fv or sv)[0][0]),
             "fork_n": len(fv), "stock_n": len(sv), "fork_distinct": fd, "stock_distinct": sd}
        if key in ip_bound:
            cls = "ip-bound"
        elif len(fv) < 2:
            cls = "sparse"
        elif fd > 1:
            cls = "unlinked"
        elif key is None and len(sv) >= 2 and sd == 1 and digest(sv[0]) == digest(fv[0]):
            cls = "site-constant"
        elif sd > 1:
            cls = "pinned"
        else:
            cls = "gap"
            r["explained_by"] = explain(key, doc, constants, accepted, fv[0], sv[0] if sv else [])
            r["low_cardinality"] = all(d._weak(v) for v in fv[0])
            if r["explained_by"] is None:
                counts["net_gap"] += 1
        r["class"] = cls
        counts[cls] += 1
        rows.append(r)
    seen = {r["key"] for r in rows if r["key"] and r["fork_n"]}
    for k in sorted(set(fields) - seen):
        rows.append({"field": k, "key": k, "class": "absent"})
        counts["absent"] += 1
    counts["raw_gap"] = counts.pop("gap", 0)
    in_fork = {p for f in fork for p in f}
    in_stock = {p for s in stock for p in s}
    sjd = next((r["fork_distinct"] for r in rows if r.get("key") == "sjd" and "fork_distinct" in r), None)
    return {"rows": rows, "counts": {k: counts.get(k, 0) for k in
                                     ("net_gap", "raw_gap", "pinned", "unlinked", "ip-bound", "site-constant", "sparse", "absent")},
            "fork_only": sorted(in_fork - in_stock), "stock_only": sorted(in_stock - in_fork), "sjd_fork_distinct": sjd}
