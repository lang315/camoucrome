#!/usr/bin/env python3
"""Roadmap step 5, layer 3: how often commercial anti-bot systems challenge the fork against stock Chrome, per vendor
(docs/superpowers/specs/2026-10-24-step5-layer3-design.md).

Run on the Windows host in the client venv, in the interactive session (run-interactive.ps1):
  python measure_layer3.py run --out DIR [--rounds 12] [--headed] [--warm] [--aa] [--plant ARG] [--resume RUNDIR]
  python measure_layer3.py report RUN
  python measure_layer3.py compare RUN_A RUN_B
  python measure_layer3.py budget RUN --sites N --rounds R [--limit-gb 5]
  python measure_layer3.py scrub RUN OUT        (on the Mac; the committable vendor table)

  python measure_layer3.py run --design first-visitor --arms S,F,N,S2 --approved-gb G [--fork-drop-key N=canvas:seed ...] ...
(the PerimeterX arms N and S2, docs plan 2026-10-28-px-arms-n-s2.md: every visit on its own fresh exit address, no pairs.)

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
import collections
import datetime
import hashlib
import json
import os
import pathlib
import random
import re
import secrets
import sys
import tempfile
import time
import urllib.parse

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


# --- first-visitor design (docs plan 2026-10-28-px-arms-n-s2.md): one arm per fresh exit address, arms S F N S2 ---

ARM_NAMES = ("S", "F", "N", "S2")
PAUSE_S = 1800  # a site that answered 429 twice in a row rests 30 minutes
BUDGET_STOP = 0.90
MAX_REUSED = 2


def parse_drop(spec):
    """`ARM=KEY` or `ARM=PREFIX` -> (arm, value). S is stock and has no config to drop from."""
    arm, sep, val = spec.partition("=")
    if not sep or not val or arm not in ARM_NAMES or arm == "S":
        sys.exit(f"--fork-drop-*: {spec!r} is not ARM=VALUE with ARM one of F, N, S2")
    return arm, val


def parse_arms(text):
    arms = text.split(",")
    if len(set(arms)) != len(arms) or not set(arms) <= set(ARM_NAMES) or not {"S", "F"} <= set(arms):
        raise argparse.ArgumentTypeError(f"--arms: {text!r} must be distinct names from {','.join(ARM_NAMES)} including S and F")
    return arms


def drop_keys(config, arm, drops):
    """A copy of the generated config without the keys and key prefixes bound to this arm.
    drops = {"keys": [(arm, key)], "prefixes": [(arm, prefix)]}"""
    keys = {k for a, k in drops["keys"] if a == arm}
    prefixes = tuple(p for a, p in drops["prefixes"] if a == arm)
    return {k: v for k, v in config.items() if k not in keys and not (prefixes and k.startswith(prefixes))}


def window_size_arg(arm, window):
    """The window handed to the launcher (which turns it into --window-size): none for S2, so the browser opens its default window."""
    return None if arm == "S2" else window


def launch_for_arm(arm, launch):
    """The launcher settings for an arm: S2 has no window spoof at all, so neither the size nor the position is passed (owner 2026-10-28)."""
    return {**launch, "window": window_size_arg(arm, launch.get("window")), "position": None if arm == "S2" else launch.get("position")}


def plan_visits(arms, site_idxs, rounds, seed):
    """[(round, site_idx, arm)]: every arm once per (round, site), in a random order per (round, site) from the seed."""
    rng = random.Random(seed)
    out = []
    for rnd in range(rounds):
        sites = list(site_idxs)
        rng.shuffle(sites)
        for idx in sites:
            order = list(arms)
            rng.shuffle(order)
            out += [(rnd, idx, arm) for arm in order]
    return out


class AddressLedger:
    """Exit addresses seen in this run, as salted hashes in memory only (the salt is per run, so the digests are no use outside
    it). Never written to a result; a resumed run starts with an empty one."""

    def __init__(self):
        self._salt = os.urandom(16)
        self._seen = set()

    def _h(self, addr):
        return hashlib.sha256(self._salt + addr.encode()).hexdigest()

    def seen(self, addr):
        return self._h(addr) in self._seen

    def add(self, addr):
        self._seen.add(self._h(addr))

    def digests(self):
        return sorted(self._seen)

    def __repr__(self):
        return f"AddressLedger({len(self._seen)} addresses)"


def should_stop(reused_address):
    """Stop rule 5: more than two visits on an address an earlier visit used."""
    return reused_address > MAX_REUSED


def apply_address_checks(row, ip, ledger):
    """Mark a proxied first-visitor row unknown when its exit address could not be read, was used before, or a WebRTC candidate
    named another one. Returns True for a reused address. The address goes into the ledger, never into the row."""
    reused = False
    if ip is None:
        row.update({"outcome": "unknown", "error": "ip_unread"})
    elif ledger.seen(ip):
        reused = True
        row.update({"outcome": "unknown", "error": "reused_address"})
    elif (row.get("webrtc_leaks") or 0) != 0:
        row.update({"outcome": "unknown", "error": "webrtc_leak"})
    if ip is not None:
        ledger.add(ip)
    return reused


def is_429(row):
    return any((st or {}).get("status") == 429 for st in (row.get("reason") or {}).values())


class Pause429:
    """Stop rule 2. Two 429 visits in a row at one site pause that site for 30 minutes; the third pause, or 429s on more than 10% of
    a full window of the last 20 attempts, stops the run. record() -> "OK" | "PAUSE" | "STOP"; allow(site) is False inside a pause,
    and the caller never visits a site it is not allowed (a 429 is not retried inside the pause)."""

    def __init__(self, clock):
        self.clock, self.streak, self.until, self.pauses = clock, collections.Counter(), {}, 0
        self.window = collections.deque(maxlen=20)

    def allow(self, site):
        return self.clock() >= self.until.get(site, 0)

    def wait_s(self, site):
        return max(0.0, self.until.get(site, 0) - self.clock())

    def record(self, site, got_429):
        self.window.append(bool(got_429))
        self.streak[site] = self.streak[site] + 1 if got_429 else 0
        if len(self.window) == 20 and sum(self.window) > 2:
            return "STOP"
        if self.streak[site] >= 2:
            self.streak[site] = 0
            self.pauses += 1
            self.until[site] = self.clock() + PAUSE_S
            return "STOP" if self.pauses >= 3 else "PAUSE"
        return "OK"


def budget_stop(bytes_so_far, approved_bytes, last_visit_bytes, last_ok):
    """Stop rule 3: the running total reached 90% of the approved bytes, or a SUCCESSFUL visit read 0 bytes (a broken byte
    counter). An exception visit has no bytes by nature: it counts as unknown (the over-10% rule), not as a stop (owner 2026-10-28)."""
    return (last_ok and last_visit_bytes == 0) or bytes_so_far >= BUDGET_STOP * approved_bytes


def first_visitor_cost(mean_bytes, sites, rounds, n_arms):
    """Bytes of one run-equivalent: one visit per arm per site per round."""
    return mean_bytes * sites * rounds * n_arms


def first_visitor_counts(rows):
    """{vendor: {arm: (challenged, measured, unknown)}} from result rows."""
    c = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, 0]))
    for r in rows:
        t = c[r["vendor"]][r["arm"]]
        if r["outcome"] in ("unknown", "unmeasured"):
            t[2] += 1
        else:
            t[1] += 1
            t[0] += lc.challenged(r["outcome"])
    return {v: {a: tuple(t) for a, t in arms.items()} for v, arms in c.items()}


def first_visitor_report(counts, rows=()):
    """Per vendor: rate and unknown per arm, per-site rates (site by index), gate G0, the N and S2 readings."""
    out = []
    for vendor, arms in counts.items():
        out += [f"{vendor}", "| arm | challenged/measured | rate | unknown |", "|---|---|---|---|"]
        for a in ARM_NAMES:
            if a in arms:
                x, n, u = arms[a]
                out.append(f"| {a} | {x}/{n} | {x / n:.2f} | {u} |" if n else f"| {a} | 0/0 | | {u} |")
        sites = sorted({r["site"] for r in rows if r["vendor"] == vendor})
        for idx in sites:
            cells = []
            for a in ARM_NAMES:
                m = [r for r in rows if r["vendor"] == vendor and r["site"] == idx and r["arm"] == a and r["outcome"] not in ("unknown", "unmeasured")]
                if m:
                    cells.append(f"{a} {sum(lc.challenged(r['outcome']) for r in m)}/{len(m)}")
            out.append(f"site #{idx}: " + ", ".join(cells))
        if "S" not in arms or "F" not in arms:
            out += ["G0: no S or F arm in this run", ""]
            continue
        g = ls.gate_g0(arms["F"][0], arms["F"][1], arms["S"][0], arms["S"][1])
        out.append(f"G0 d_FS {g['d']:+.2f} 95% [{g['lo']:+.2f}, {g['hi']:+.2f}]: " + ("passed" if g["passed"] else "not passed"))
        diffs = ls.arm_diffs(arms, g)
        if "conclusion" in diffs:
            out.append(diffs["conclusion"])
        for a, d in diffs.items():
            if a == "conclusion":
                continue
            out.append(f"{a}: UNMEASURED" if d == "UNMEASURED" else
                       f"{a}: d_X {d['d']:+.2f} 97.5% [{d['lo']:+.2f}, {d['hi']:+.2f}] carries_part {d['carries_part']} carries_all {d['carries_all']} "
                       f"(X - S 95% [{d['equiv_lo']:+.2f}, {d['equiv_hi']:+.2f}])")
        out.append("")
    return "\n".join(out)


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


ECHO_URLS = ("https://api.ipify.org", "https://checkip.amazonaws.com", "https://icanhazip.com")


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


def nav_failure(row):
    """A visit that never got a page: a navigation error (exception, no status) or a server error (5xx) in a stage that
    read unknown. A 200 on another host or a blank page with no status may be the vendor's block, so they are not this."""
    for st in (row.get("reason") or {}).values():
        status = st.get("status")
        if (st.get("exc") and status is None) or (status is not None and status >= 500):
            return True
    return False


def run_pair_with_retries(attempt, retries, check=True):
    """attempt(k) -> (rows by arm, exit addresses by arm) for try k on its own fresh session. A pair on two addresses (or an
    unread one, or one with a visit that never got a page: nav_failure) is tried again on a new session, at most `retries` times; the bytes the discarded tries spent stay on the
    final rows as retry_bytes, because the proxy charged for them. A half pair (a resumed run) has no partner and is returned as is."""
    spent = {"S": 0, "F": 0}
    for k in range(retries + 1):
        rows, ips = attempt(k)
        if len(rows) < 2 or not check:  # no partner, or no proxy: there is no exit address to compare
            return rows
        pair_exit_ips(rows, ips)
        if any(r.get("error") == "webrtc_leak" for r in rows.values()):
            break  # a leak is not luck of the session: a retry would only spend bytes
        if rows["S"]["ip_pair"] == "same" and not any(nav_failure(r) for r in rows.values()):
            break
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
    """The exit address as the page sees it, or None. Kept in memory for pair_exit_ips; never written to a result.
    The echo services are asked in order and the first that answers with an address wins."""
    for url in ECHO_URLS:
        try:
            page.goto(url, wait_until="load", timeout=30000)
            ip = page.inner_text("body").strip()
        except Exception:  # noqa: BLE001 - an unread address makes the pair unknown, not the run a crash
            continue
        if re.fullmatch(r"[0-9a-fA-F:.]{3,45}", ip):
            return ip
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


def load(page, url, note=None):
    try:
        resp = page.goto(url, wait_until="load", timeout=60000)
        return resp.status if resp else None
    except Exception as exc:  # noqa: BLE001 - a page that does not finish loading is classified from what is there
        if note is not None:
            note["exc"] = type(exc).__name__
        return None


def unknown_reason(page, url, status, note):
    """Why a stage read unknown: the navigation exception class, the main-document status, the body text length and
    whether the page ended on the host it started on. Nothing else: no host, no text, no markup."""
    try:
        body_len = page.evaluate("document.body ? document.body.innerText.length : 0")
    except Exception:  # noqa: BLE001 - an unreadable page is a None, not a failed run
        body_len = None
    try:
        same_host = urllib.parse.urlparse(page.url).hostname == urllib.parse.urlparse(url).hostname
    except Exception:  # noqa: BLE001
        same_host = None
    return {"exc": note.get("exc"), "status": status, "body_len": body_len, "same_host": same_host}


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
                 args=arm.args + lo.get("args", []), window=tuple(lo["window"]) if lo.get("window") else None, dpr=lo.get("dpr"),
                 position=tuple(lo["position"]) if lo.get("position") else None, proxy=proxy)
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
        n1, n2 = {}, {}
        s1 = load(page, site["url"], n1)
        r1, saw1 = settle(page, ctx, site, s1, a.settle)
        reason = {"stage1": unknown_reason(page, site["url"], s1, n1)} if r1["outcome"] == "unknown" else {}
        page.wait_for_timeout(int(a.dwell * 1000))
        for _ in range(3):
            page.mouse.wheel(0, 100)
            page.wait_for_timeout(int(min(0.7, a.dwell) * 1000))
        s2 = load(page, site["next_url"], n2)
        r2, saw2 = settle(page, ctx, site, s2, a.settle)
        if r2["outcome"] == "unknown":
            reason["stage2"] = unknown_reason(page, site["next_url"], s2, n2)
        if a.gpu_gate:
            gpu_gate.check(gpu_gate.read_ctx(ctx))  # a crash during the visit is as unmeasured as one at launch
        return {"stage1": r1["outcome"], "stage2": r2["outcome"], "outcome": lc.combine(r1, r2),
                "interstitial_seen": saw1 or saw2, "markers": sorted(set(r1["markers"] + r2["markers"])),
                "cookie_names": sorted(set(r1["cookies"] + r2["cookies"])), "bytes": total[0], "webrtc_leaks": leaks, "_exit_ip": exit_ip,
                **({"reason": reason} if reason else {})}
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


def build_identity(a, host_draw=None):
    """The fork's generated identity, in the HOST's zone and locale: stock reports the real host zone and the proxy exits in
    the host region, so an identity in another zone would contradict its IP in the fork arm only (spec 3.3).
    `host_draw` is measure_step2.probe_host_draw(): the host's renderer, fonts, display and Windows build. Without it the
    identity claims no GPU (gen.gpu_for fails closed); the run passes it, so a Gen9 host draws a Gen9 identity and any other
    host keeps its real GPU."""
    if a.aa or a.no_identity:
        return None
    if not (a.timezone and a.locale):
        sys.exit("precondition: an identity run needs --timezone and --locale (the host's own, so the fork is the only difference)")
    from camoucrome.gen import generate
    return generate("windows", seed=a.identity_seed, timezone=a.timezone, locale=a.locale, **(host_draw or {}))


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
    fv = {} if a.design == "pair" else {"design": a.design, "arms": a.arms, "fork_drop_key": a.fork_drop_key, "fork_drop_prefix": a.fork_drop_prefix}
    return {**{k: getattr(a, k) for k in ("headed", "warm", "aa", "plant", "arg", "no_identity", "identity_seed", "seed", "dwell", "settle", "min_gap")},
            "identity_zone_given": bool(a.timezone and a.locale), **fv}


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
    kept = {"reused_address": old["reused_address"]} if "reused_address" in old else {}
    return {**new, "started": old["started"], "rounds": max(old["rounds"], new["rounds"]), **kept}


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
    ident = build_identity(a, None if a.aa or a.no_identity else m2.probe_host_draw(fork_exe))
    desktop = m2.desktop_size() if a.headed and ident else None
    bad = window_problems(ident["launch"].get("window") if ident else None, desktop)
    if bad:
        sys.exit("precondition: " + "; ".join(bad))
    common = common_args(proxy_cfg, a.arg)
    arms = {"S": m2.Arm("stock", stock_exe, None, common), "F": m2.Arm("fork", fork_exe, ident, common + ([a.plant] if a.plant else []))}
    drops = {"keys": a.fork_drop_key, "prefixes": a.fork_drop_prefix}
    if a.design != "pair":
        if a.aa or a.warm or not ident or a.approved_gb is None:
            sys.exit("first-visitor: needs an identity, --approved-gb, and neither --aa nor --warm")
        for name in a.arms:
            if name not in arms:
                lo = launch_for_arm(name, ident["launch"])
                arms[name] = m2.Arm(name, fork_exe, {**ident, "config": drop_keys(ident["config"], name, drops), "launch": lo}, common)
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
                    "argv_read": bool(argv["S"] and argv["F"]), "proxy": bool(proxy_cfg), "started": m2.run_stamp(), "flags": flags_of(a), "desktop": desktop,
                    **({} if a.design == "pair" else {"design": a.design, "arms": a.arms, "drops": drops, "approved_bytes": int(a.approved_gb * 1e9),
                                                      "reused_address": 0, "stop": None})}
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
            stop = None if a.design == "pair" else run_first_visitor(pw, arms, sites, proxy_cfg, a, out_dir, run_id, done, meta)
            for rnd in (range(a.rounds) if a.design == "pair" else ()):
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
    if stop:
        print(f"UNMEASURED: the run stopped ({stop}); what it left open is UNMEASURED", file=sys.stderr)
        return 4
    results = read_results(out_dir)
    if results and all(r["outcome"] in ("unknown", "unmeasured") for r in results):
        print("nothing was measured: every visit is unknown or unmeasured", file=sys.stderr)
        return 1
    print(f"run {out_dir}")
    return 0


def run_first_visitor(pw, arms, sites, proxy_cfg, a, out_dir, run_id, done, meta, clock=time.monotonic, sleep=time.sleep):
    """The first-visitor loop: every visit on its own fresh sticky session, the stop rules of the plan. Returns the stop reason or
    None. Writes the final reused_address count and stop into meta.json. Thin on purpose: the rules are the pure functions above;
    this wiring is only exercised on the host."""
    import gpu_gate
    by_idx = {s["idx"]: s for s in sites}
    pending = [v for v in plan_visits(a.arms, list(by_idx), a.rounds, a.seed) if v not in done]
    ledger, pause = AddressLedger(), Pause429(clock)
    reused, spent, approved, last, stop = meta.get("reused_address", 0), sum(visit_cost(r) for r in read_results(out_dir)), a.approved_gb * 1e9, {}, None
    while pending and not stop:
        ready = [v for v in pending if pause.allow(v[1])]
        if not ready:
            sleep(min(pause.wait_s(v[1]) for v in pending))
            continue
        rnd, idx, name = visit_id = ready[0]
        pending.remove(visit_id)
        site = by_idx[idx]
        wait = a.min_gap - (clock() - last.get(idx, -1e9))
        if wait > 0:
            sleep(wait)
        retry_bytes = 0
        for k in range(a.ip_retries + 1):
            # a new random session id per try, never reused: the proxy gives it a fresh exit address
            proxy = proxy_for(proxy_cfg, f"{run_id}-{secrets.token_hex(6)}")
            row = {"round": rnd, "site": idx, "vendor": site["vendor"], "arm": name,
                   "t": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
            try:
                row.update(visit(pw, arms[name], site, proxy, a))
            except Exception as exc:  # noqa: BLE001 - a failed visit is unknown/unmeasured, recorded, never a crash of the batch
                row.update({"outcome": "unmeasured" if isinstance(exc, gpu_gate.Unmeasured) else "unknown", "error": type(exc).__name__, "bytes": 0})
            ip = row.pop("_exit_ip", None)
            if not proxy_cfg or (ip is not None and not nav_failure(row)) or (row.get("webrtc_leaks") or 0) != 0 or k == a.ip_retries:
                break
            retry_bytes += row.get("bytes", 0)
        if proxy_cfg:
            reused += apply_address_checks(row, ip, ledger)
        row["retries"], row["retry_bytes"] = k, retry_bytes
        with (out_dir / "results.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        print(f"round {rnd} {site['vendor']}#{idx} {name}: {row['outcome']}", flush=True)
        last[idx] = clock()
        spent += visit_cost(row)
        if pause.record(idx, is_429(row)) == "STOP":
            stop = "http_429"
        elif should_stop(reused):
            stop = "reused_address"
        elif budget_stop(spent, approved, row.get("bytes", 0), row.get("outcome") not in ("unknown", "unmeasured")):
            stop = "budget"
    meta.update({"reused_address": reused, "stop": stop})
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return stop


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
    meta_file = pathlib.Path(a.run_dir) / "meta.json"
    if meta_file.exists() and json.loads(meta_file.read_text(encoding="utf-8")).get("design") == "first-visitor":
        rs = read_results(a.run_dir)
        print(first_visitor_report(first_visitor_counts(rs), rs))
        return 0
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
    if getattr(a, "design", "pair") == "first-visitor":
        gb = first_visitor_cost(mean, a.sites, a.rounds, len(a.arms)) / 1e9
        print(f"{BYTES_NOTE}: mean {mean:.0f} bytes per visit; {a.sites} sites x {a.rounds} rounds x {len(a.arms)} arms = "
              f"{a.sites * a.rounds * len(a.arms)} visits, one run-equivalent = {gb:.2f} GB")
    else:
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
    r.add_argument("--design", choices=("pair", "first-visitor"), default="pair")
    r.add_argument("--arms", type=parse_arms, default=list(ARM_NAMES), help="first-visitor only; S and F required")
    r.add_argument("--fork-drop-key", type=parse_drop, action="append", default=[], help="ARM=KEY: remove a config key from that arm's identity")
    r.add_argument("--fork-drop-prefix", type=parse_drop, action="append", default=[], help="ARM=PREFIX: remove the config keys with this prefix")
    r.add_argument("--approved-gb", type=float, help="first-visitor only: the approved proxy bytes; the run stops at 90%%")
    for name in ("report", "budget", "scrub"):
        p = sub.add_parser(name)
        p.add_argument("run_dir")
        if name == "budget":
            p.add_argument("--sites", type=int, required=True)
            p.add_argument("--rounds", type=int, required=True)
            p.add_argument("--limit-gb", type=float, default=5.0)
            p.add_argument("--design", choices=("pair", "first-visitor"), default="pair")
            p.add_argument("--arms", type=parse_arms, default=list(ARM_NAMES))
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
