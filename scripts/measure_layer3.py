#!/usr/bin/env python3
"""Roadmap step 5, layer 3: how often commercial anti-bot systems challenge the fork against stock Chrome, per vendor
(docs/superpowers/specs/2026-10-24-step5-layer3-design.md).

Run on the Windows host in the client venv, in the interactive session (run-interactive.ps1):
  python measure_layer3.py run --out DIR [--rounds 20] [--headed] [--warm] [--aa] [--plant ARG] [--resume RUNDIR]
  python measure_layer3.py report RUN
  python measure_layer3.py compare RUN_A RUN_B
  python measure_layer3.py budget RUN --sites N --rounds R [--limit-gb 5]
  python measure_layer3.py scrub RUN OUT        (on the Mac; the committable vendor table)

Two arms, S (stock) and F (fork), through the same client, argv and proxy. One ROUND = one site on one sticky exit IP,
visited by both arms back to back in random order. Images, media and fonts are blocked in BOTH arms the same way
(traffic budget, owner 2026-10-24): rates here are for that traffic shape. --aa puts stock in the F arm (the noise
floor); --plant ARG adds a browser argument to F only (a RED: the harness must see it).
Private inputs, never in the repository: the site list ($CAMOU_L3_SITES, default ~/.config/camoucrome/layer3-sites.json)
and the proxy file ($CAMOU_L3_PROXY_FILE: {"server", "username_template" with {session}, "password"}). Results name a
site by index and vendor only; cookie VALUES are never read into a result."""
import argparse
import datetime
import json
import os
import pathlib
import random
import re
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import layer3_classify as lc  # noqa: E402
import layer3_stats as ls  # noqa: E402

BLOCKED_TYPES = {"image", "media", "font"}
SETTLE_S = 15
RUN_EQUIVALENTS = 4.5  # primary 1 + A/A 1 + planted RED 1 + warmed variant 0.5 (10 of 20 rounds) + second run 1
VENDORS = ("cloudflare", "datadome", "akamai", "perimeterx")
DEFAULT_SITES = "~/.config/camoucrome/layer3-sites.json"
# With a proxy, WebRTC can reveal the host's own address; the same policy goes to both arms or only one leaks.
WEBRTC_POLICY = "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"


def load_sites(path):
    """[{"idx", "vendor", "id", "url", "next_url", "ok_marker"}], refusing a list that is not ready to run."""
    doc = json.loads(pathlib.Path(os.path.expanduser(path)).read_text(encoding="utf-8"))
    sites = []
    for vendor in VENDORS:
        for s in doc.get(vendor) or []:
            missing = [k for k in ("id", "url", "next_url", "ok_marker") if not s.get(k)]
            if missing:
                sys.exit(f"site list: {vendor}/{s.get('id', '?')} lacks {missing} (fill next_url and ok_marker from a real page load)")
            sites.append({**s, "vendor": vendor, "idx": len(sites)})
    if not sites:
        sys.exit("site list: no sites")
    return sites


def load_proxy(path):
    if not path:
        return None
    cfg = json.loads(pathlib.Path(os.path.expanduser(path)).read_text(encoding="utf-8"))
    for k in ("server", "username_template", "password"):
        if not cfg.get(k):
            sys.exit(f"proxy file lacks {k}")
    return cfg


def proxy_for(cfg, session):
    """The same value goes to both arms of a round; the session id picks the sticky exit IP."""
    if not cfg:
        return None
    return {"server": cfg["server"], "username": cfg["username_template"].format(session=session), "password": cfg["password"]}


def common_args(proxy_cfg, extra=()):
    """Browser arguments both arms get, identically."""
    return ([WEBRTC_POLICY] if proxy_cfg else []) + list(extra)


def secrets_of(cfg):
    if not cfg:
        return []
    host = re.sub(r"^\w+://", "", cfg["server"]).split("/")[0].rsplit(":", 1)[0].strip("[]")
    return [cfg["password"]] + ([host] if len(host) >= 4 else [])


def secret_scan(out_dir, secrets):
    """Names of files under out_dir that contain any secret. The host never gets the private terms, so this is its own leak gate.
    profiles/ (--warm) is skipped: it holds vendor cookie values, never leaves the host, and must not be copied to the Mac
    (only meta.json and results.jsonl are)."""
    bad = []
    for p in pathlib.Path(out_dir).rglob("*"):
        if p.is_file() and p.relative_to(out_dir).parts[0] != "profiles":
            data = p.read_bytes().lower()
            if any(s and s.lower().encode() in data for s in secrets):
                bad.append(str(p))
    return bad


def snapshot(page, ctx, site, status):
    """What the classifier reads. Cookie VALUES are dropped here: only names leave this function."""
    data = page.evaluate("""() => ({
      title: document.title,
      text: (document.body ? document.body.innerText : '').slice(0, 20000),
      html: document.documentElement.outerHTML.slice(0, 200000),
      frames: [...document.querySelectorAll('iframe,script')].map(e => e.src).filter(Boolean)})""")
    data["status"] = status
    data["ok"] = page.locator(site["ok_marker"]).count() > 0
    data["cookies"] = [c["name"] for c in ctx.cookies()]
    return data


def settle(page, ctx, site, status, limit=SETTLE_S):
    """Poll once a second until the page is a pass or a block, or SETTLE_S: a JS interstitial that clears by itself is
    not a challenge, one that is still up is. Returns the last classification and whether an interstitial was ever seen."""
    deadline, saw = time.monotonic() + limit, False
    while True:
        try:
            res = lc.classify(site["vendor"], snapshot(page, ctx, site, status))
        except Exception:  # noqa: BLE001 - a navigation during the poll destroys the context: wait for it and look again
            res = {"outcome": "unknown", "markers": [], "cookies": []}
            try:
                page.wait_for_load_state(timeout=5000)
            except Exception:  # noqa: BLE001
                pass
        saw = saw or res["outcome"] == "challenge"
        if res["outcome"] in ("pass", "block") or time.monotonic() > deadline:
            return res, saw
        page.wait_for_timeout(1000)


def load(page, url):
    try:
        resp = page.goto(url, wait_until="load", timeout=60000)
        return resp.status if resp else None
    except Exception:  # noqa: BLE001 - a page that does not finish loading is classified from what is there
        return None


def visit(pw, arm, site, proxy, a, user_data_dir=None):
    """One run of one arm on one site: stage 1, a fixed interaction, stage 2. Returns the result row fields."""
    import gpu_gate
    from camoucrome import launch
    ident = arm.ident
    lo = ident["launch"] if ident else {}
    ctx = launch(pw, arm.exe, config=ident["config"] if ident else None, headless=not a.headed, user_data_dir=user_data_dir,
                 args=arm.args, window=tuple(lo["window"]) if lo.get("window") else None, dpr=lo.get("dpr"), proxy=proxy)
    total = [0]
    try:
        if a.gpu_gate:
            gpu_gate.check(gpu_gate.read_ctx(ctx))
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        ctx.route("**/*", lambda route: route.abort() if route.request.resource_type in BLOCKED_TYPES else route.continue_())

        def count(request):
            try:
                total[0] += sum(request.sizes().values())
            except Exception:  # noqa: BLE001 - a size that cannot be read is not worth a failed run
                pass
        page.on("requestfinished", count)
        r1, saw1 = settle(page, ctx, site, load(page, site["url"]), a.settle)
        page.wait_for_timeout(int(a.dwell * 1000))
        for _ in range(3):
            page.mouse.wheel(0, 100)
            page.wait_for_timeout(int(min(0.7, a.dwell) * 1000))
        r2, saw2 = settle(page, ctx, site, load(page, site["next_url"]), a.settle)
        return {"stage1": r1["outcome"], "stage2": r2["outcome"], "outcome": lc.combine(r1, r2),
                "interstitial_seen": saw1 or saw2, "markers": sorted(set(r1["markers"] + r2["markers"])),
                "cookie_names": sorted(set(r1["cookies"] + r2["cookies"])), "bytes": total[0]}
    finally:
        try:
            ctx.close()
        except Exception as exc:  # noqa: BLE001 - a good result is kept; the close error is a note
            print(f"NOTE: closing the browser failed: {type(exc).__name__}", file=sys.stderr)


def read_results(run_dir):
    p = pathlib.Path(run_dir) / "results.jsonl"
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()] if p.exists() else []


def parity_problems(argv_s, argv_f, plant, on_windows):
    """Problems with the two arms' command lines. An unread argv is a problem on Windows (as in measure_step2); off Windows
    there is no /proc to read, so the check is skipped and says so."""
    import step2_rows
    if not on_windows and not (argv_s and argv_f):
        print("argv parity not checked: no /proc here")
        return []
    return step2_rows.argv_problems(argv_s or [], argv_f or [], step2_rows.ARGV_ALLOWED + ((plant,) if plant else ()))


def flags_of(a):
    return {k: getattr(a, k) for k in ("headed", "warm", "aa", "plant", "arg", "no_identity", "identity_seed", "seed", "dwell", "settle", "min_gap")}


def resume_meta(old, new):
    """A resumed run must be the same experiment: refuse a changed flag, keep the original start, allow more rounds."""
    of, nf = old.get("flags"), new["flags"]
    if of is None:
        sys.exit("resume: the run's meta.json records no flags")
    diff = sorted(k for k in set(of) | set(nf) if of.get(k) != nf.get(k))
    if diff:
        sys.exit("resume: flags differ from the run being resumed: " + ", ".join(diff))
    return {**new, "started": old["started"], "rounds": max(old["rounds"], new["rounds"])}


def run_cmd(a):
    from patchright.sync_api import sync_playwright
    import measure_step2 as m2
    if a.gpu_gate:
        import gpu_gate
        gpu_gate.require_interactive()
    sites = load_sites(a.sites or os.environ.get("CAMOU_L3_SITES", DEFAULT_SITES))
    proxy_cfg = load_proxy(a.proxy_file or os.environ.get("CAMOU_L3_PROXY_FILE"))
    stock_exe = a.stock_exe or os.path.join(os.environ.get("CAMOU_STOCK_APP", m2.STOCK_APP), "chrome.exe")
    fork_exe = stock_exe if a.aa else (a.fork_exe or os.environ["CAMOU_FORK_EXE"])
    ident = None if (a.aa or a.no_identity) else m2.identity(a.identity_seed)
    common = common_args(proxy_cfg, a.arg)
    arms = {"S": m2.Arm("stock", stock_exe, None, common), "F": m2.Arm("fork", fork_exe, ident, common + ([a.plant] if a.plant else []))}
    if a.resume:
        out_dir = pathlib.Path(a.resume)
    else:
        run_id = m2.run_stamp() + ("-aa" if a.aa else "") + ("-plant" if a.plant else "") + ("-warm" if a.warm else "")
        out_dir = pathlib.Path(a.out or tempfile.gettempdir()) / "layer3" / run_id
        out_dir.mkdir(parents=True)
    run_id = out_dir.name
    done = {(r["round"], r["site"], r["arm"]) for r in read_results(out_dir)}
    rng = random.Random(a.seed)
    last = {}
    try:
        with sync_playwright() as pw:
            argv = {k: m2.argv_of(pw, arm) for k, arm in arms.items()}
            bad = parity_problems(argv["S"], argv["F"], a.plant, os.name == "nt")
            if bad:
                sys.exit("precondition, argv parity: " + "; ".join(bad))
            meta = {"run": run_id, "rounds": a.rounds, "warm": a.warm, "aa": a.aa, "plant": bool(a.plant), "blocked": sorted(BLOCKED_TYPES),
                    "sites_per_vendor": {v: sum(1 for s in sites if s["vendor"] == v) for v in VENDORS},
                    "versions": {k: m2.exe_version(arm.exe) if os.name == "nt" else "" for k, arm in arms.items()},
                    "argv_read": bool(argv["S"] and argv["F"]), "proxy": bool(proxy_cfg), "started": m2.run_stamp(), "flags": flags_of(a)}
            if a.resume:
                meta_file = out_dir / "meta.json"
                if not meta_file.exists():
                    sys.exit("resume: no meta.json in " + str(out_dir))
                meta = resume_meta(json.loads(meta_file.read_text(encoding="utf-8")), meta)
            (out_dir / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
            for rnd in range(a.rounds):
                order_sites = list(sites)
                rng.shuffle(order_sites)
                for site in order_sites:
                    pair = ["S", "F"]
                    rng.shuffle(pair)
                    wait = a.min_gap - (time.monotonic() - last.get(site["idx"], -1e9))
                    if wait > 0:
                        time.sleep(wait)
                    proxy = proxy_for(proxy_cfg, f"{run_id}-{rnd}-{site['idx']}")
                    for name in pair:
                        if (rnd, site["idx"], name) in done:
                            continue
                        row = {"round": rnd, "site": site["idx"], "vendor": site["vendor"], "arm": name, "order": "".join(pair),
                               "t": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
                        udd = None
                        if a.warm:
                            udd = out_dir / "profiles" / f"{name}-{site['idx']}"
                            udd.mkdir(parents=True, exist_ok=True)
                        try:
                            row.update(visit(pw, arms[name], site, proxy, a, str(udd) if udd else None))
                        except Exception as exc:  # noqa: BLE001 - a failed run is unknown/unmeasured, recorded, never a crash of the batch
                            import gpu_gate
                            row.update({"outcome": "unmeasured" if isinstance(exc, gpu_gate.Unmeasured) else "unknown",
                                        "error": type(exc).__name__, "bytes": 0})
                        with (out_dir / "results.jsonl").open("a", encoding="utf-8") as f:
                            f.write(json.dumps(row) + "\n")
                        print(f"round {rnd} {site['vendor']}#{site['idx']} {name}: {row['outcome']}", flush=True)
                    last[site["idx"]] = time.monotonic()
    finally:
        leaked = secret_scan(out_dir, secrets_of(proxy_cfg))
        if leaked:
            print("LEAK: the proxy secret is in " + ", ".join(leaked), file=sys.stderr)
            sys.exit(3)
    results = read_results(out_dir)
    if results and all(r["outcome"] in ("unknown", "unmeasured") for r in results):
        print("nothing was measured: every visit is unknown or unmeasured", file=sys.stderr)
        return 1
    print(f"run {out_dir}")
    return 0


def vendor_rows(run_dir, resamples=10000):
    rows = read_results(run_dir)
    out = {}
    for vendor in VENDORS:
        vr = [{"site": r["site"], "round": r["round"], "arm": r["arm"], "order": r["order"],
               "challenged": None if r["outcome"] in ("unknown", "unmeasured") else lc.challenged(r["outcome"])}
              for r in rows if r["vendor"] == vendor]
        if vr:
            out[vendor] = ls.vendor_row(vr, resamples)
    return out


FOOTNOTE = ("* zero-width interval: no variation observed in this vendor's runs (not certainty); with 3 sites the clustered "
            "interval is coarse, read it with the paired interval")


def table(rows_by_vendor, header=""):
    lines = [header] if header else []
    lines.append("| vendor | sites | pairs | unknown | stock | fork | d (fork - stock, site-weighted) | 95% bootstrap | paired 95% | order effect |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    starred = False
    for v, r in rows_by_vendor.items():
        if r.get("n") == 0 or r.get("unmeasured"):
            lines.append(f"| {v} | {r.get('sites', 0)} | {r.get('n', 0)} | {r.get('unknown', 0)} | UNMEASURED | | | | | |")
            continue
        oe = "" if r["order_effect"] is None else f"{r['order_effect']:+.2f}"
        p = r["paired"]
        star = "*" if r.get("degenerate") else ""
        starred = starred or bool(star)
        lines.append(f"| {v} | {r['sites']} | {r['n']} | {r['unknown']} | {r['rate_stock']:.2f} | {r['rate_fork']:.2f} | {r['d']:+.2f} "
                     f"| [{r['lo']:+.2f}, {r['hi']:+.2f}]{star} | [{p['lo']:+.2f}, {p['hi']:+.2f}] | {oe} |")
    if starred:
        lines += ["", FOOTNOTE]
    return "\n".join(lines)


def report_cmd(a):
    rows = vendor_rows(a.run_dir)
    print(table(rows))
    rs = read_results(a.run_dir)
    if rs:
        print(f"\nbytes per visit: mean {sum(r.get('bytes', 0) for r in rs) / len(rs):.0f} over {len(rs)} visits")
    return 0


def compare_cmd(a):
    ra, rb = vendor_rows(a.run_a), vendor_rows(a.run_b)
    verdicts = []
    for v in VENDORS:
        if v in ra and v in rb:
            ok = ls.runs_agree(ra[v], rb[v])
            print(f"{v}: {'agree' if ok else 'UNMEASURED' if ok is None else 'DISAGREE'}")
            verdicts.append(ok)
    if any(ok is False for ok in verdicts):
        return 2
    return 3 if not verdicts or any(ok is None for ok in verdicts) else 0


def budget_cmd(a):
    rs = [r for r in read_results(a.run_dir) if r["outcome"] not in ("unknown", "unmeasured")]
    if not rs:
        sys.exit("budget: the run has no measured visits")
    mean = sum(r.get("bytes", 0) for r in rs) / len(rs)
    total = mean * a.sites * a.rounds * 2 * RUN_EQUIVALENTS
    gb = total / 1e9
    print(f"mean {mean:.0f} bytes per visit; {a.sites} sites x {a.rounds} rounds x 2 arms x {RUN_EQUIVALENTS} run-equivalents = {gb:.2f} GB")
    if gb > a.limit_gb:
        print(f"OVER the {a.limit_gb} GB budget: do not start the paid run", file=sys.stderr)
        return 2
    return 0


def scrub_cmd(a):
    import check_privacy
    src, dst = pathlib.Path(a.run_dir), pathlib.Path(a.out_dir)
    meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))
    rows = vendor_rows(src)
    thin = {v: r.get("sites", 0) for v, r in rows.items() if r.get("sites", 0) < 3}
    if thin:
        sys.exit(f"scrub: fewer than 3 sites for {sorted(thin)}: a vendor with one or two sites names its sites")
    header = (f"Run {meta['run']} (UTC). Images, media and fonts blocked in both arms; {meta['rounds']} rounds per site; "
              f"{'warmed profiles' if meta['warm'] else 'fresh profiles'}; {'stock against stock' if meta['aa'] else 'fork (no identity) against stock' if meta.get('flags', {}).get('no_identity') else 'fork against stock'}"
              f"{'; planted RED' if meta['plant'] else ''}; {'residential proxy in the host region' if meta['proxy'] else 'no proxy'}.\n")
    text = header + "\n" + table(rows) + "\n"
    terms = check_privacy.load_terms()
    if check_privacy.term_count(terms) == 0:
        sys.exit("scrub: no private terms loaded (~/.config/camoucrome/private-terms.json or $PRIVATE_TERMS): the gate would pass anything")
    left = check_privacy.hits(text, terms)
    if left:
        sys.exit(f"scrub: host-identifying data left: {sorted({c for _, c in left})}")
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "layer3-baseline.md").write_text(text, encoding="utf-8")
    print(f"scrubbed {src} -> {dst}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out")
    r.add_argument("--resume")
    r.add_argument("--rounds", type=int, default=20)
    r.add_argument("--sites")
    r.add_argument("--proxy-file")
    r.add_argument("--stock-exe")
    r.add_argument("--fork-exe")
    r.add_argument("--headed", action="store_true")
    r.add_argument("--warm", action="store_true")
    r.add_argument("--aa", action="store_true")
    r.add_argument("--plant")
    r.add_argument("--arg", action="append", default=[], help="a browser argument for BOTH arms")
    r.add_argument("--no-identity", action="store_true")
    r.add_argument("--identity-seed", type=int, default=1)
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--dwell", type=float, default=3.0)
    r.add_argument("--settle", type=float, default=SETTLE_S, help="seconds to wait for a challenge to clear or a pass to show")
    r.add_argument("--min-gap", type=float, default=90.0)
    r.add_argument("--gpu-gate", action="store_true", default=os.name == "nt")
    for name in ("report", "budget", "scrub"):
        p = sub.add_parser(name)
        p.add_argument("run_dir")
        if name == "budget":
            p.add_argument("--sites", type=int, required=True)
            p.add_argument("--rounds", type=int, required=True)
            p.add_argument("--limit-gb", type=float, default=5.0)
        if name == "scrub":
            p.add_argument("out_dir")
    c = sub.add_parser("compare")
    c.add_argument("run_a")
    c.add_argument("run_b")
    a = ap.parse_args(argv)
    return {"run": run_cmd, "report": report_cmd, "compare": compare_cmd, "budget": budget_cmd, "scrub": scrub_cmd}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
