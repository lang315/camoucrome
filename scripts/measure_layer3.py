#!/usr/bin/env python3
"""Roadmap step 5, layer 3: how often commercial anti-bot systems challenge the fork against stock Chrome, per vendor
(docs/superpowers/specs/2026-10-24-step5-layer3-design.md).

Run on the Windows host in the client venv, in the interactive session (run-interactive.ps1):
  python measure_layer3.py run --out DIR [--rounds 12] [--headed] [--warm] [--aa] [--plant ARG] [--resume RUNDIR]
  python measure_layer3.py report RUN
  python measure_layer3.py compare RUN_A RUN_B
  python measure_layer3.py budget RUN --sites N --rounds R [--limit-gb 5]
  python measure_layer3.py scrub RUN OUT        (on the Mac; the committable vendor table)

Two arms, S (stock) and F (fork), through the same client, argv and proxy. One ROUND = one site on one sticky exit IP,
visited by both arms back to back in random order. Images, media and fonts are blocked in BOTH arms the same way
(traffic budget, owner 2026-10-24): rates here are for that traffic shape. --aa puts stock in the F arm (the noise
floor); --plant ARG adds a browser argument to F only (a RED: the harness must see it).
The warm variant (--warm) is deferred and not part of the `budget` run-equivalents.
Private inputs, never in the repository: the site list ($CAMOU_L3_SITES, default ~/.config/camoucrome/layer3-sites.json)
and the proxy file ($CAMOU_L3_PROXY_FILE: {"server", "username_template" with {session}, "password"}). Results name a
site by index and vendor only; cookie VALUES are never read into a result. The proxy host IS on the live browser command line
(--proxy-server); argv_of launches without a proxy, and nothing the harness writes contains an argv."""
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
RUN_EQUIVALENTS = 4  # primary 1 + A/A 1 + planted RED 1 + second run 1 (the warmed variant is deferred, spec 10.11)
VENDORS = ("cloudflare", "datadome", "akamai", "perimeterx")
DEFAULT_SITES = "~/.config/camoucrome/layer3-sites.json"
# --force-webrtc-ip-handling-policy is a no-op in //chrome (only content_shell and headless read it), so stock Chrome
# leaked a srflx candidate with the host's address behind the proxy. Only the pref works: both arms' profiles get it.
WEBRTC_PREF = {"ip_handling_policy": "disable_non_proxied_udp"}


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
    return list(extra)


ECHO_URL = "https://api.ipify.org"


def pair_exit_ips(rows, ips):
    """Both arms of a round share one sticky session, so they must exit on one address. A pair on two addresses, or with an
    address that could not be read, compares nothing: both rows become unknown. The address itself is never stored."""
    ok = bool(ips.get("S")) and bool(ips.get("F"))
    tag = "unread" if not ok else "same" if ips["S"] == ips["F"] else "differ"
    leak = any((r.get("webrtc_leaks") or 0) != 0 for r in rows.values())
    for r in rows.values():
        r["ip_pair"] = tag
        if tag != "same":
            r.update({"outcome": "unknown", "error": "ip_" + tag})
        elif leak:  # a page that could name an address other than the exit one compares nothing
            r.update({"outcome": "unknown", "error": "webrtc_leak"})
    return rows


def seed_profile(user_data_dir):
    """Write the WebRTC policy into the profile's Preferences before launch, keeping anything already there."""
    f = pathlib.Path(user_data_dir) / "Default" / "Preferences"
    f.parent.mkdir(parents=True, exist_ok=True)
    prefs = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    prefs["webrtc"] = {**prefs.get("webrtc", {}), **WEBRTC_PREF}
    f.write_text(json.dumps(prefs), encoding="utf-8")


RTC_PROBE = """async () => {
 const out = []; const pc = new RTCPeerConnection({iceServers: [{urls: 'stun:stun.l.google.com:19302'}]});
 pc.createDataChannel('x'); pc.onicecandidate = e => { if (e.candidate) out.push(e.candidate.candidate) };
 await pc.setLocalDescription(await pc.createOffer());
 await new Promise(r => { pc.onicegatheringstatechange = () => pc.iceGatheringState === 'complete' && r(); setTimeout(r, 5000) });
 pc.close(); return out }"""


def webrtc_leaks(candidates, exit_ip):
    """How many ICE candidates name an address other than the exit address (an mDNS name hides the real one and is fine)."""
    n = 0
    for c in candidates:
        parts = c.split()
        addr = parts[4] if len(parts) > 4 else ""
        if addr != exit_ip and not addr.endswith(".local"):
            n += 1
    return n


def read_webrtc_leaks(page, exit_ip):
    """-1 when the probe could not run: an unread channel is as unmeasured as a leaking one."""
    try:
        return webrtc_leaks(page.evaluate(RTC_PROBE), exit_ip)
    except Exception:  # noqa: BLE001
        return -1


def run_pair_with_retries(attempt, retries, check=True):
    """attempt(k) -> (rows by arm, exit addresses by arm) for try k on its own fresh session. A pair on two addresses (or an
    unread one) is tried again on a new session, at most `retries` times; the bytes the discarded tries spent stay on the
    final rows as retry_bytes, because the proxy charged for them. A half pair (a resumed run) has no partner and is returned as is."""
    spent = {"S": 0, "F": 0}
    for k in range(retries + 1):
        rows, ips = attempt(k)
        if len(rows) < 2 or not check:  # no partner, or no proxy: there is no exit address to compare
            return rows
        pair_exit_ips(rows, ips)
        if rows["S"]["ip_pair"] == "same" or any(r.get("error") == "webrtc_leak" for r in rows.values()):
            break  # a leak is not luck of the session: a retry would only spend bytes
        if k < retries:
            for name, r in rows.items():
                spent[name] += r.get("bytes", 0)
    for name, r in rows.items():
        r["retries"], r["retry_bytes"] = k, spent[name]
    return rows


def visit_cost(row):
    """What one measured visit cost the proxy: its own page bytes plus the tries thrown away before it."""
    return row.get("bytes", 0) + row.get("retry_bytes", 0)


def read_exit_ip(page):
    """The exit address as the page sees it, or None. Kept in memory for pair_exit_ips; never written to a result."""
    try:
        page.goto(ECHO_URL, wait_until="load", timeout=30000)
        ip = page.inner_text("body").strip()
        return ip if re.fullmatch(r"[0-9a-fA-F:.]{3,45}", ip) else None
    except Exception:  # noqa: BLE001 - an unread address makes the pair unknown, not the run a crash
        return None


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
    own_profile = user_data_dir is None
    if own_profile:
        user_data_dir = tempfile.mkdtemp(prefix="l3-")
    seed_profile(user_data_dir)
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
        exit_ip = read_exit_ip(page) if proxy else "direct"
        leaks = read_webrtc_leaks(page, exit_ip) if proxy and exit_ip else (-1 if proxy else 0)
        r1, saw1 = settle(page, ctx, site, load(page, site["url"]), a.settle)
        page.wait_for_timeout(int(a.dwell * 1000))
        for _ in range(3):
            page.mouse.wheel(0, 100)
            page.wait_for_timeout(int(min(0.7, a.dwell) * 1000))
        r2, saw2 = settle(page, ctx, site, load(page, site["next_url"]), a.settle)
        if a.gpu_gate:
            gpu_gate.check(gpu_gate.read_ctx(ctx))  # a crash during the visit is as unmeasured as one at launch
        return {"stage1": r1["outcome"], "stage2": r2["outcome"], "outcome": lc.combine(r1, r2),
                "interstitial_seen": saw1 or saw2, "markers": sorted(set(r1["markers"] + r2["markers"])),
                "cookie_names": sorted(set(r1["cookies"] + r2["cookies"])), "bytes": total[0], "webrtc_leaks": leaks, "_exit_ip": exit_ip}
    finally:
        try:
            ctx.close()
        except Exception as exc:  # noqa: BLE001 - a good result is kept; the close error is a note
            print(f"NOTE: closing the browser failed: {type(exc).__name__}", file=sys.stderr)
        if own_profile:
            from camoucrome.launcher import remove_dir
            remove_dir(user_data_dir)


def read_results(run_dir):
    p = pathlib.Path(run_dir) / "results.jsonl"
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()] if p.exists() else []


def build_identity(a):
    """The fork's generated identity, in the HOST's zone and locale: stock reports the real host zone and the proxy exits in
    the host region, so an identity in another zone would contradict its IP in the fork arm only (spec 3.3)."""
    if a.aa or a.no_identity:
        return None
    if not (a.timezone and a.locale):
        sys.exit("precondition: an identity run needs --timezone and --locale (the host's own, so the fork is the only difference)")
    from camoucrome.gen import generate
    return generate("windows", seed=a.identity_seed, timezone=a.timezone, locale=a.locale)


def window_problems(window, desktop):
    """A headed window cannot exceed the desktop; a clamped window would be a fork-only inconsistency."""
    if not window or not desktop:
        return []
    if window[0] > desktop[0] or window[1] > desktop[1]:
        return [f"the identity window {window[0]}x{window[1]} is larger than the desktop {desktop[0]}x{desktop[1]}"]
    return []


def version_problems_for(versions, pin, aa):
    import step2_rows
    return [] if aa else step2_rows.version_problems(versions, pin)


def measured_rows(run_dir):
    return [r for r in read_results(run_dir) if r["outcome"] not in ("unknown", "unmeasured")]


def parity_problems(argv_s, argv_f, plant, on_windows):
    """Problems with the two arms' command lines. An unread argv is a problem on Windows (as in measure_step2); off Windows
    there is no /proc to read, so the check is skipped and says so."""
    import step2_rows
    if not on_windows and not (argv_s and argv_f):
        print("argv parity not checked: no /proc here")
        return []
    return step2_rows.argv_problems(argv_s or [], argv_f or [], step2_rows.ARGV_ALLOWED + ((plant,) if plant else ()))


def flags_of(a):
    # the zone and locale values are host-identifying and meta.json leaves the host: only that they were given is recorded, so a
    # resume cannot compare them (accepted)
    return {**{k: getattr(a, k) for k in ("headed", "warm", "aa", "plant", "arg", "no_identity", "identity_seed", "seed", "dwell", "settle", "min_gap")},
            "identity_zone_given": bool(a.timezone and a.locale)}


def resume_meta(old, new):
    """A resumed run must be the same experiment: refuse a changed flag, keep the original start, allow more rounds."""
    of, nf = old.get("flags"), new["flags"]
    if of is None:
        sys.exit("resume: the run's meta.json records no flags")
    diff = sorted(k for k in set(of) | set(nf) if of.get(k) != nf.get(k))
    if diff:
        sys.exit("resume: flags differ from the run being resumed: " + ", ".join(diff))
    changed = [k for k in ("versions", "sites_per_vendor") if old.get(k) != new.get(k)]
    if changed:
        sys.exit("resume: the run being resumed differs in " + ", ".join(changed) + " (a rebuilt browser or an edited site list)")
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
    ident = build_identity(a)
    desktop = m2.desktop_size() if a.headed and ident else None
    bad = window_problems(ident["launch"].get("window") if ident else None, desktop)
    if bad:
        sys.exit("precondition: " + "; ".join(bad))
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
                    "argv_read": bool(argv["S"] and argv["F"]), "proxy": bool(proxy_cfg), "started": m2.run_stamp(), "flags": flags_of(a), "desktop": desktop}
            if os.name == "nt":
                import windows_verify_set
                bad = version_problems_for(meta["versions"], windows_verify_set.pin_tag(os.environ.get("CAMOU_CLIENT", str(HERE.parent))), a.aa)
                if bad:
                    sys.exit("precondition: " + "; ".join(bad))
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
                    def attempt(k, site=site, pair=pair, rnd=rnd):
                        # the retry's session id differs, so the proxy gives it a fresh exit address
                        proxy = proxy_for(proxy_cfg, f"{run_id}-{rnd}-{site['idx']}" + (f"-r{k}" if k else ""))
                        pending, ips = {}, {}
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
                            ips[name] = row.pop("_exit_ip", None)
                            pending[name] = row
                        return pending, ips
                    pending = run_pair_with_retries(attempt, a.ip_retries, check=bool(proxy_cfg))
                    for name, row in pending.items():
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
        vr = [{"site": r["site"], "round": r["round"], "arm": r["arm"], "order": r.get("order"),
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


BYTES_NOTE = "page bytes (request+response sizes of the page's requests: a lower bound, not the proxy's counter)"


def report_cmd(a):
    rows = vendor_rows(a.run_dir)
    print(table(rows))
    rs = measured_rows(a.run_dir)
    if rs:
        print(f"\n{BYTES_NOTE}: mean {sum(visit_cost(r) for r in rs) / len(rs):.0f} over {len(rs)} measured visits")
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
    rs = measured_rows(a.run_dir)
    if not rs:
        sys.exit("budget: the run has no measured visits")
    if any(not r.get("bytes") for r in rs):
        sys.exit("budget: a measured visit has 0 bytes (the size could not be read): the extrapolation would be too low")
    mean = sum(visit_cost(r) for r in rs) / len(rs)
    total = mean * a.sites * a.rounds * 2 * RUN_EQUIVALENTS
    gb = total / 1e9
    print(f"{BYTES_NOTE}: mean {mean:.0f} bytes per visit; {a.sites} sites x {a.rounds} rounds x 2 arms x {RUN_EQUIVALENTS} run-equivalents = {gb:.2f} GB")
    if gb > a.limit_gb:
        print(f"OVER the {a.limit_gb} GB budget: do not start the paid run", file=sys.stderr)
        return 2
    return 0


def scrub_cmd(a):
    import check_privacy
    src, dst = pathlib.Path(a.run_dir), pathlib.Path(a.out_dir)
    meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))
    rows = vendor_rows(src)
    thin = {v: r["sites"] for v, r in rows.items() if "sites" in r and r["sites"] < 3}
    if thin:
        sys.exit(f"scrub: fewer than 3 sites for {sorted(thin)}: a vendor with one or two sites names its sites")
    header = (f"Run {meta['run']} (UTC). Images, media and fonts blocked in both arms; {meta['rounds']} rounds per site; "
              f"{'headed' if meta.get('flags', {}).get('headed') else 'headless'}; {'warmed profiles' if meta['warm'] else 'fresh profiles'}; {'stock against stock' if meta['aa'] else 'fork (no identity) against stock' if meta.get('flags', {}).get('no_identity') else 'fork against stock'}"
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


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out")
    r.add_argument("--resume")
    r.add_argument("--rounds", type=int, default=12)
    r.add_argument("--ip-retries", type=int, default=2, help="tries of a round on a fresh session when the arms exit on different addresses")
    r.add_argument("--sites")
    r.add_argument("--proxy-file")
    r.add_argument("--stock-exe")
    r.add_argument("--fork-exe")
    r.add_argument("--headed", action=argparse.BooleanOptionalAction, default=os.name == "nt")
    r.add_argument("--timezone", help="the host's IANA zone, for the fork identity (not recorded in meta)")
    r.add_argument("--locale", help="the host's locale tag, for the fork identity (not recorded in meta)")
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
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    return {"run": run_cmd, "report": report_cmd, "compare": compare_cmd, "budget": budget_cmd, "scrub": scrub_cmd}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
