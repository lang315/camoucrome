"""SP7 phone-home verify: a fresh headless `chrome` on about:blank makes NO
outbound request to a non-loopback host within the observation window.

P1 zero outbound hosts (RED build, measured 2026-09-09: 8 hosts -- component
   updater + gvt1 downloads, GCM checkin/register3, accounts ListAccounts,
   network time, omnibox AIM eligibility, spellcheck dictionary).
P2 probe capability: the same netlog carries >= 1 loopback request -- the
   page is navigated to a local echo server right after launch, so chrome
   itself issues one URLRequest we can see (the DevTools /json/version poll
   is INBOUND and never appears in the netlog; the first draft assumed it
   would). An empty host set is then not an empty capture. Assert presence
   before absence.
P3 control: the fork's config layer still works on this binary
   (navigator.hardwareConcurrency override), so P1 is about THIS build.

Mechanism: --log-net-log writes every URLRequest (REQUEST_ALIVE carries the
URL) regardless of DNS or TLS outcome, so this measures intent to connect,
not reachability -- a box with no route still reports the attempt. The
window is WINDOW_SECONDS after the DevTools port answers; the RED capture
showed every caller firing within 2.5 s and the component updater's second
wave at ~60 s, so 75 s covers both.

Safe Browsing's first list fetch is NOT inside 75 s by default: its timer is
uniform in 60..300 s (kTimerStartIntervalSecMin/Max,
sb_update_protocol_manager.h), so a 75 s window caught it about one start in
sixteen. --safebrowsing-fast-initial-lists-update moves it to 10..20 s,
which puts it in every window.

Measurement: docs/superpowers/measurements/2026-09-09-sp7-phone-home.md
P4 X-Client-Data on google.com over two launches on one profile: absent both
   times (stock sends it on the second launch, from the seed the first stored).
P5 probe capability for navigation-time lookups: the netlog carries the
   navigation to sb.test (a non-IP name mapped to loopback, so a URL
   lookup has a host to check), so P1's empty set covers what a navigation
   triggers too. Assert presence before absence.

P6 probe capability for external extensions: a seeded external extension (a
   crx registered the way a desktop app does -- HKCU\\Software\\Google\\Chrome\\
   Extensions\\<id> on Windows, <chrome dir>/extensions/<id>.json on Linux/macOS)
   is discovered when the profile sets extensions.block_external_extensions to
   false: its Preferences entry has an external location and, where Chrome
   prompts for external extensions (Windows and macOS; FeatureSwitch
   prompt_for_external_extensions is off on Linux), the netlog holds a request
   to chromewebstore.googleapis.com (the install prompt's store-data fetch,
   external_install_error_desktop.cc). Without this, P7's empty result could
   mean the fixture never worked. Measured 2026-10-24: the Windows host's own
   registered extension made that request ~1 s after launch (backlog 4b).
P7 the same fixture, default prefs: no request to chromewebstore.googleapis.com
   and no external-location entry in the profile. The fork defaults the pref to
   true (patches/block-external-extensions.patch). On Linux the entry is the
   only signal, and it is RED on a build without the patch.

A netlog that does not parse scores P1/P2/P5 UNMEASURED (exit 2), not FAIL.
"""
import hashlib, json, os, re, shutil, struct, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import echo_server
import lib_shell

WINDOW_SECONDS = int(os.environ.get("SP7_PHONEHOME_WINDOW", "75"))
NETLOG = os.path.join(tempfile.gettempdir(),
                      f"camoucrome_sp7_netlog.{os.getpid()}.json")
LOOPBACK = re.compile(r"^(127\.\d+\.\d+\.\d+|localhost|\[::1\])(:\d+)?$")
NAV_HOST = "sb.test"
NAV = re.compile(rf"^{re.escape(NAV_HOST)}(:\d+)?$")

EXT_CRX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "ext_probe.crx")
CWS_HOST = "chromewebstore.googleapis.com"
EXTERNAL_LOCATIONS = (2, 3, 6)  # ManifestLocation: ExternalPref, ExternalRegistry, ExternalPrefDownload
STORE_REQUEST = sys.platform in ("win32", "darwin")  # prompting is on by default there
EXT_SECONDS = int(os.environ.get("SP7_EXTERNAL_WINDOW", "30"))

results = {}
notes = []


def parse_hosts(path):
    """Returns (external_hosts: {host: count}, loopback_count, nav_count).

    Parsed line by line, because a netlog read at shutdown can be cut anywhere
    (re-pin 2026-10-02 sweep 2; twice on 2026-10-04 at 75 s). The writer puts
    the constants on line 1 and one event per line after `"events": [`; lines
    not starting with `{` (the array open, `"polledData"`, the closing brace)
    carry no events. Only the LAST event line may fail to parse -- the one cut
    off at shutdown, after the window; a bad line anywhere else raises."""
    lines = open(path, "r", encoding="utf-8", errors="replace").read().split("\n")
    constants = json.loads(lines[0].rstrip().rstrip(",") + "}")["constants"]
    types = {v: k for k, v in constants["logEventTypes"].items()}
    events, bad = [], []
    rows = [(i, s.strip()) for i, s in enumerate(lines[1:], 2)
            if s.strip().startswith("{")]
    for i, s in rows:
        s = s.rstrip(",")
        if s.endswith("]"):  # the last event closes the array
            s = s[:-1]
        try:
            events.append(json.loads(s))
        except ValueError:
            bad.append(i)
    if bad and bad != [rows[-1][0]]:
        raise ValueError(f"netlog lines {bad} do not parse")
    external, loopback, nav = {}, 0, 0
    for ev in events:
        if types.get(ev.get("type")) != "REQUEST_ALIVE":
            continue
        url = (ev.get("params") or {}).get("url")
        if not url:
            continue
        m = re.match(r"^[a-z]+://([^/?#]+)", url)
        if not m:
            continue
        host = m.group(1)
        if LOOPBACK.match(host):
            loopback += 1
        elif NAV.match(host):
            nav += 1
        else:
            external[host] = external.get(host, 0) + 1
    return external, loopback, nav


def run_p1_p2():
    if not os.path.exists(lib_shell.CHROME):
        results["P1"] = results["P2"] = results["P5"] = False
        notes.append("P1/P2/P5: no out/Default/chrome binary")
        return
    proc = stop = None
    try:
        base_url, _headers_for, stop = echo_server.start(lib_shell.ACCEPT_CH)
        proc = lib_shell.launch(
            None, shell=lib_shell.CHROME,
            extra_flags=[*lib_shell.CHROME_FLAGS, f"--log-net-log={NETLOG}",
                         "--net-log-capture-mode=Default",
                         "--safebrowsing-fast-initial-lists-update",
                         f"--host-resolver-rules=MAP {NAV_HOST} 127.0.0.1"])
        # One loopback URLRequest, issued by chrome, for P2; then one
        # navigation to a name, for P5.
        lib_shell.evaluate(proc, ["1"], navigate_to=base_url)
        lib_shell.evaluate(proc, ["1"], navigate_to=base_url.replace(
            "127.0.0.1", NAV_HOST, 1))
        time.sleep(WINDOW_SECONDS)
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        results["P1"] = results["P2"] = results["P5"] = False
        notes.append(f"P1/P2/P5 launch: {type(exc).__name__}: {exc}")
        return
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)
        if stop is not None:
            stop()
    try:
        external, loopback, nav = parse_hosts(NETLOG)
    except Exception as exc:  # noqa: BLE001
        # A netlog Chrome had not finished writing measures nothing either
        # way: UNMEASURED, not FAIL (re-pin 2026-10-02, sweep 2).
        results["P1"] = results["P2"] = results["P5"] = None
        notes.append(f"P1/P2/P5 netlog parse: {type(exc).__name__}: {exc}")
        return
    finally:
        try:
            os.remove(NETLOG)
        except OSError:
            pass
    results["P2"] = loopback >= 1
    if not results["P2"]:
        notes.append("P2: netlog holds no loopback request; P1's empty set is "
                     "not evidence")
    results["P5"] = nav >= 1
    if not results["P5"]:
        notes.append(f"P5: netlog holds no request to {NAV_HOST}; P1 says "
                     "nothing about navigation-time lookups")
    results["P1"] = results["P2"] and results["P5"] and not external
    notes.append(f"P1: external hosts in {WINDOW_SECONDS}s = "
                 f"{json.dumps(dict(sorted(external.items())))} (expect {{}})")
    notes.append(f"P2: loopback requests = {loopback}")
    notes.append(f"P5: {NAV_HOST} requests = {nav}")


def run_p3():
    vals, err = lib_shell.session(
        json.dumps({"navigator.hardwareConcurrency": 8}),
        ["navigator.hardwareConcurrency"], shell=lib_shell.CHROME,
        extra_flags=lib_shell.CHROME_FLAGS)
    if err is not None:
        results["P3"] = False
        notes.append(f"P3: {type(err).__name__}: {err}")
        return
    results["P3"] = vals[0] == 8
    notes.append(f"P3: hardwareConcurrency = {vals[0]} (expect 8)")


def run_p4():
    """X-Client-Data on a Google host (SP7 'still open', B1). Stock Chrome sends
    the header only from a profile that already holds a variations seed with
    ids, so a fresh profile proves nothing: measured 2026-09-11 on stock
    Chrome 153 on the box's Windows host, two launches on one temp profile,
    launch 1 -> no header on google.com/generate_204, launch 2 -> x-client-data
    present (scripts/winhost.py cdp_headers). The fork, same two-launch shape:
    no header either time, and no request to the variations/update hosts."""
    import tempfile
    from playwright.sync_api import sync_playwright
    prof = tempfile.mkdtemp(prefix="camoucrome-p4-")
    seen = []
    # Presence before absence: launch 1 must have written its profile into
    # `prof`, or launch 2 is not "the same profile" and an absent header on it
    # proves nothing.
    reused = False
    try:
        for launch in (1, 2):
            proc = None
            if launch == 2:
                reused = os.path.exists(os.path.join(prof, "Local State"))
            try:
                proc = lib_shell.launch(None, shell=lib_shell.CHROME,
                                        extra_flags=lib_shell.CHROME_FLAGS,
                                        user_data_dir=prof)
                with sync_playwright() as p:
                    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{proc.cdp_port}")
                    context = browser.contexts[0]
                    page = context.pages[0] if context.pages else context.new_page()
                    cdp = context.new_cdp_session(page)
                    reqs, extra = {}, []
                    cdp.on("Network.requestWillBeSent", lambda e: reqs.__setitem__(e["requestId"], e["request"]["url"]))
                    cdp.on("Network.requestWillBeSentExtraInfo", lambda e: extra.append(e))
                    cdp.send("Network.enable")
                    try:
                        page.goto("https://www.google.com/generate_204", wait_until="load", timeout=30000)
                    except Exception as nav:  # noqa: BLE001  204 No Content aborts the navigation; the request was sent
                        if "ERR_ABORTED" not in str(nav):
                            raise
                    page.wait_for_timeout(20000 if launch == 1 else 8000)
                    for e in extra:
                        seen.append((launch, reqs.get(e["requestId"], "?"), {k.lower() for k in e["headers"]}))
            except Exception as exc:  # noqa: BLE001
                notes.append(f"P4 launch {launch}: {type(exc).__name__}: {exc}")
                results["P4"] = False
                return
            finally:
                if proc is not None:
                    lib_shell.shutdown(proc)
    finally:
        shutil.rmtree(prof, ignore_errors=True)
    hosts = sorted({re.match(r"^[a-z]+://([^/?#]+)", u).group(1) for _, u, _ in seen if re.match(r"^[a-z]+://([^/?#]+)", u)})
    xcd = [(l, u[:60]) for l, u, h in seen if "x-client-data" in h]
    bad_hosts = [h for h in hosts if h in ("clientservices.googleapis.com", "update.googleapis.com")]
    results["P4"] = reused and bool(seen) and not xcd and not bad_hosts
    notes.append(f"P4: {len(seen)} requests over two launches on one profile, hosts={hosts}, x-client-data on {xcd} (stock M153: on launch 2), variations/update hosts {bad_hosts}")
    notes.append(f"P4: launch 1 wrote its profile where launch 2 reads it = {reused} (expect True)")


def crx_id(path):
    """Extension id of a CRX3: first 16 bytes of sha256(public key), a-p."""
    d = open(path, "rb").read()
    hdr = d[12:12 + struct.unpack("<I", d[8:12])[0]]

    def varint(b, i):
        r = sh = 0
        while True:
            c = b[i]
            i += 1
            r |= (c & 0x7F) << sh
            sh += 7
            if c < 128:
                return r, i
    n, i = varint(hdr, 1)            # field 2: sha256_with_rsa proof
    proof = hdr[i:i + n]
    n, i = varint(proof, 1)          # its field 1: public_key
    key = proof[i:i + n]
    return "".join(chr(97 + int(c, 16)) for c in hashlib.sha256(key).hexdigest()[:32])


def seed_external(ext_id):
    """Registers EXT_CRX as an external extension. Returns (browser, undo).
    Linux/macOS: a symlink copy of the out dir with the fixture in its own
    extensions/ dir (chrome::DIR_EXTERNAL_EXTENSIONS is <chrome dir>/extensions),
    so nothing lands in the shared ~/.config or the build dir. Windows: an HKCU
    key, removed by undo."""
    if sys.platform == "win32":
        import winreg
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                               rf"Software\Google\Chrome\Extensions\{ext_id}")
        winreg.SetValueEx(key, "path", 0, winreg.REG_SZ, EXT_CRX)
        winreg.SetValueEx(key, "version", 0, winreg.REG_SZ, "1.0")
        winreg.CloseKey(key)
        return lib_shell.CHROME, lambda: winreg.DeleteKey(
            winreg.HKEY_CURRENT_USER, rf"Software\Google\Chrome\Extensions\{ext_id}")
    out = os.path.dirname(lib_shell.CHROME)
    farm = tempfile.mkdtemp(prefix="camoucrome-p6-farm-")
    for name in os.listdir(out):
        if name == "extensions":
            continue
        src, dst = os.path.join(out, name), os.path.join(farm, name)
        if name == os.path.basename(lib_shell.CHROME):
            os.link(src, dst)  # a hard link, so the browser's own dir is the farm
        else:
            os.symlink(src, dst)
    os.mkdir(os.path.join(farm, "extensions"))
    with open(os.path.join(farm, "extensions", ext_id + ".json"), "w") as f:
        json.dump({"external_crx": EXT_CRX, "external_version": "1.0"}, f)
    return os.path.join(farm, os.path.basename(lib_shell.CHROME)), \
        lambda: shutil.rmtree(farm, ignore_errors=True)


def run_external(shell, allow):
    """One launch with the fixture. allow=True pre-seeds the profile pref
    extensions.block_external_extensions=false. Returns (store requests,
    external-location entries in the profile's Preferences files)."""
    prof = tempfile.mkdtemp(prefix="camoucrome-p6-")
    netlog = prof + "-net.json"
    if allow:
        os.makedirs(os.path.join(prof, "Default"))
        with open(os.path.join(prof, "Default", "Preferences"), "w") as f:
            json.dump({"extensions": {"block_external_extensions": False}}, f)
    proc = None
    try:
        proc = lib_shell.launch(
            None, shell=shell, user_data_dir=prof,
            extra_flags=[*lib_shell.CHROME_FLAGS, f"--log-net-log={netlog}",
                         "--net-log-capture-mode=Default"])
        time.sleep(EXT_SECONDS)
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)
    try:
        external, _, _ = parse_hosts(netlog)
        entries = []
        for name in ("Preferences", "Secure Preferences"):
            try:
                prefs = json.load(open(os.path.join(prof, "Default", name)))
            except OSError:
                continue
            for eid, ent in prefs.get("extensions", {}).get("settings", {}).items():
                if ent.get("location") in EXTERNAL_LOCATIONS:
                    entries.append(eid)
        return external.get(CWS_HOST, 0), sorted(set(entries))
    finally:
        shutil.rmtree(prof, ignore_errors=True)
        try:
            os.remove(netlog)
        except OSError:
            pass


def run_p6_p7():
    undo = None
    try:
        ext_id = crx_id(EXT_CRX)
        shell, undo = seed_external(ext_id)
        c_req, c_ent = run_external(shell, allow=True)
        t_req, t_ent = run_external(shell, allow=False)
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        results["P6"] = results["P7"] = False
        notes.append(f"P6/P7: {type(exc).__name__}: {exc}")
        return
    finally:
        if undo is not None:
            undo()
    results["P6"] = (c_req >= 1 or not STORE_REQUEST) and ext_id in c_ent
    results["P7"] = results["P6"] and t_req == 0 and not t_ent
    notes.append(f"P6: pref off, fixture {ext_id[:6]}..: store requests = {c_req}, external entries = {len(c_ent)} (expect {'>=1' if STORE_REQUEST else 'any'}, fixture listed)")
    notes.append(f"P7: default prefs: store requests = {t_req}, external entries = {len(t_ent)} (expect 0, 0)")


def main():
    run_p1_p2()
    run_p3()
    run_p4()
    run_p6_p7()
    for n in notes:
        print("note:", n)
    rc = 0
    for k in ("P1", "P2", "P3", "P4", "P5", "P6", "P7"):
        v = results.get(k, False)
        print(f"{k}: {'UNMEASURED' if v is None else 'PASS' if v else 'FAIL'}")
        if v is None and rc == 0:
            rc = 2
        elif v is False:
            rc = 1
    sys.exit(rc)


if __name__ == "__main__":
    main()
