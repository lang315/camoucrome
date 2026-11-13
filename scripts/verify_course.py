"""Obstacle course: the fork against vendored CreepJS and mutant (R) rows.

K1-K5 read a page (PAGE) the fork loads untouched; each R row runs the same checks under a deliberate
lie (an init script, main world) and passes only if the check named for that lie notices it. The control
row runs them under a no-op init script, so a harness that always reports problems cannot pass the R rows.
K6 / R6 run the vendored CreepJS (served under /creep/, index.html with HARNESS appended) against the fork with no
config (base) and with the generated identity; a CreepJS lie, trash or stealth hit that the base lacks is a problem.

Box-only: needs patchright and the fork build (lib_shell layout). The pure checks run anywhere.
"""
import hashlib
import http.server
import json
import os
import struct
import subprocess
import sys
import threading
from pathlib import Path

CREEP_DIR = Path(__file__).parent / "third_party" / "creepjs"
EXPECTED_ROWS = 12  # K1-K6, R1-R4, R6, CTRL
# Box calibration (measured there, never guessed here). While either is None, main() refuses to run.
K2_FLOOR = None  # fewest functions the K2 sweep must visit, or it measured nothing
K4_VOLATILE = None  # leaf -> reason, for K4 leaves that legitimately differ between loads


def f32(x):
    return struct.unpack("f", struct.pack("f", x))[0]


WANT = {"threshold": f32(-24), "knee": f32(30), "ratio": f32(12), "attack": f32(0.003), "release": f32(0.25), "reduction": 0}

MUTANTS = {
    "R1": ("Object.defineProperty(navigator,'hardwareConcurrency',{get:()=>8})", "k1 nav own hardwareConcurrency"),
    "R2": ("Object.defineProperty(Navigator.prototype,'hardwareConcurrency',{get(){return 8},configurable:true,enumerable:true})",
           "k2 tostring Navigator.prototype.get hardwareConcurrency"),
    "R3": ("(()=>{const o=BaseAudioContext.prototype.createDynamicsCompressor;"
           "BaseAudioContext.prototype.createDynamicsCompressor=function(){const n=o.apply(this,arguments);n.threshold.value=-23;return n}})()",
           "k3 rt.threshold"),
    "R4": ("(()=>{const v=crypto.getRandomValues(new Uint32Array(1))[0];"
           "Object.defineProperty(Navigator.prototype,'hardwareConcurrency',{get(){return v},configurable:true,enumerable:true})})()",
           "k4 nav.hardwareConcurrency"),
}
MUTANTS["R6"] = (MUTANTS["R2"][0], "k6 lie")
CTRL_JS = "void 0"

# One IIFE, no global. Every anomaly is [kind, label].
PAGE = r"""<!doctype html><title>k</title><pre id="o"></pre><script>(async()=>{
const out = {};
try {
const own = o => { try { return Object.getOwnPropertyNames(o) } catch (e) { return 'throws' } };
out.k1 = {
  nav: own(navigator), scr: own(screen), uad: own(navigator.userAgentData),
  navP: Object.getPrototypeOf(navigator) === Navigator.prototype,
  scrP: Object.getPrototypeOf(screen) === Screen.prototype,
  uadP: Object.getPrototypeOf(navigator.userAgentData) === NavigatorUAData.prototype,
};
const ifr = document.createElement('iframe'); document.documentElement.appendChild(ifr);
const xts = ifr.contentWindow.Function.prototype.toString, ts = Function.prototype.toString;
const NATIVE = /^function (get |set )?[^(){}]*\(\) \{\s*\[native code\]\s*\}$/;
const anomalies = []; let visited = 0; const seen = new Set();
const check = (f, label, protoToo) => {
  if (typeof f !== 'function' || seen.has(f) || visited >= 50000) return; seen.add(f); visited++;
  let a, b; try { a = ts.call(f) } catch (e) { a = 'throws' } try { b = xts.call(f) } catch (e) { b = 'throws' }
  if (!NATIVE.test(a)) anomalies.push(['tostring', label]);
  else if (a !== b) anomalies.push(['xrealm', label]);
  if (protoToo && Object.prototype.hasOwnProperty.call(f, 'prototype')) anomalies.push(['proto', label]);
};
const sweep = (obj, base) => {
  for (const k of Object.getOwnPropertyNames(obj)) {
    let d; try { d = Object.getOwnPropertyDescriptor(obj, k) } catch (e) { continue }
    if (!d) continue;
    if (d.get) check(d.get, base + '.get ' + k, true);
    if (d.set) check(d.set, base + '.set ' + k, true);
    if (typeof d.value === 'function') {
      // rule (c), no own prototype, only for methods on an X.prototype: constructors and aliases carry one
      check(d.value, base + '.' + k, base.endsWith('.prototype') && k !== 'constructor');
      if (obj === window && d.value.prototype && typeof d.value.prototype === 'object') { sweep(d.value.prototype, k + '.prototype'); sweep(d.value, k); }
    }
  }
};
sweep(window, 'window');
ifr.remove();
out.k2 = { visited, anomalies: anomalies.slice(0, 40) };
const f = Math.fround;
const comp = ctx => { const c = ctx.createDynamicsCompressor(); const r = {}; for (const k of ['threshold', 'knee', 'ratio', 'attack', 'release']) r[k] = c[k].value; r.reduction = c.reduction; return r };
out.k3 = { rt: comp(new AudioContext()), off: comp(new OfflineAudioContext(1, 128, 44100)) };
const fnv = s => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0 } return h.toString(16) };
const uadh = await navigator.userAgentData.getHighEntropyValues(['architecture', 'bitness', 'platformVersion', 'model', 'uaFullVersion']);
const gl = c => { const g = document.createElement('canvas').getContext(c), d = g && g.getExtension('WEBGL_debug_renderer_info'); return g && d ? [g.getParameter(d.UNMASKED_VENDOR_WEBGL), g.getParameter(d.UNMASKED_RENDERER_WEBGL)] : null };
const cv = document.createElement('canvas'); cv.width = 220; cv.height = 40; const x = cv.getContext('2d');
x.font = '16px Arial'; x.fillText('Cwm fjordbank glyphs vext quiz 1234', 4, 26); x.fillStyle = '#f60'; x.beginPath(); x.arc(50, 20, 15, 0, 7); x.fill();
const oc = new OfflineAudioContext(1, 5000, 44100); const osc = oc.createOscillator(); const cp = oc.createDynamicsCompressor();
osc.connect(cp); cp.connect(oc.destination); osc.start();
const d = (await oc.startRendering()).getChannelData(0); let s = 0; for (let i = 4000; i < 5000; i++) s += Math.abs(d[i]);
const mq = q => matchMedia(q).matches;
out.k4 = {
  nav: { hardwareConcurrency: navigator.hardwareConcurrency, deviceMemory: navigator.deviceMemory, platform: navigator.platform, languages: navigator.languages, maxTouchPoints: navigator.maxTouchPoints },
  screen: { width: screen.width, height: screen.height, availWidth: screen.availWidth, availHeight: screen.availHeight, colorDepth: screen.colorDepth },
  dpr: devicePixelRatio,
  uadHigh: { architecture: uadh.architecture, bitness: uadh.bitness, platformVersion: uadh.platformVersion, model: uadh.model },
  webgl: { webgl: gl('webgl'), webgl2: gl('webgl2') },
  canvas: fnv(cv.toDataURL()),
  audioFp: s.toFixed(6),
  intl: { timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone, locale: Intl.DateTimeFormat().resolvedOptions().locale },
  media: { dark: mq('(prefers-color-scheme: dark)'), pointerFine: mq('(pointer: fine)'), anyHover: mq('(any-hover: hover)') },
};
out.k5 = uadh.uaFullVersion;
} catch (e) { out.error = String(e) }
out.done = true;
document.getElementById('o').textContent = JSON.stringify(out.error ? { error: out.error } : out);
})()</script>"""


# Appended to the served index.html only (the vendored files stay byte for byte). Reads window.Fingerprint, which
# CreepJS sets when done, into <pre id="o">; 90 s without it is {"error": "timeout"}.
HARNESS = r"""(()=>{const t0=Date.now();const w=s=>{const p=document.createElement('pre');p.id='o';p.hidden=true;p.textContent=s;document.body.appendChild(p)};
const i=setInterval(()=>{const fp=window.Fingerprint;
if(fp){clearInterval(i);try{w(JSON.stringify({lies:Object.fromEntries(Object.entries(fp.lies?.data||{}).map(([k,v])=>[k,v])),
trash:(fp.trash?.trashBin||[]).map(t=>t.name),stealth:Object.keys(fp.headless?.stealth||{}).filter(k=>fp.headless.stealth[k]),
workerLied:!!fp.workerScope?.lied,done:true}))}catch(e){w(JSON.stringify({error:String(e)}))}}
else if(Date.now()-t0>90000){clearInterval(i);w('{"error": "timeout"}')}},250)})()"""
CREEP_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
               ".ico": "image/x-icon"}


def creep_response(rel):
    """(body, content type) of a vendored CreepJS file; index.html carries HARNESS. None: not a file in CREEP_DIR."""
    f = (CREEP_DIR / (rel or "index.html")).resolve()
    if f.parent != CREEP_DIR.resolve() or not f.is_file():
        return None
    body = f.read_bytes()
    if f.name == "index.html":
        i = body.rindex(b"</body>")
        body = body[:i] + b"<script>" + HARNESS.encode() + b"</script>" + body[i:]
    return body, CREEP_TYPES.get(f.suffix, "application/octet-stream")


def k6_problems(base, ident):
    out = [f"k6 error {side} {r['error']}" for side, r in (("base", base), ("ident", ident)) if "error" in r]
    if out:
        return out
    out = [f"k6 lie {k} {json.dumps(v)[:200]}" for k, v in ident["lies"].items() if k not in base["lies"]]
    out += [f"k6 trash {t}" for t in ident["trash"] if t not in base["trash"]]
    out += [f"k6 stealth {k}" for k in ident["stealth"]]
    return out + (["k6 worker lied"] if ident["workerLied"] else [])


def check_vendor(d: Path) -> list[str]:
    """One string per file whose sha256 differs from, or is missing against, SHA256SUMS."""
    bad = []
    for line in (d / "SHA256SUMS").read_text().splitlines():
        want, name = line.split("  ", 1)
        p = d / name
        if not p.is_file():
            bad.append(f"{name}: missing")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != want:
            bad.append(f"{name}: sha256 differs from SHA256SUMS")
    return bad


def k1_problems(rep):
    k = rep["k1"]
    out = []
    for name in ("nav", "scr", "uad"):
        if not isinstance(k[name], list):
            out.append(f"k1 {name} own properties: {k[name]}")
        out += [f"k1 {name} own {p}" for p in k[name]] if isinstance(k[name], list) else []
        if not k[name + "P"]:
            out.append(f"k1 {name}P")
    return out


def k2_problems(rep, floor):
    k = rep["k2"]
    out = [f"k2 {kind} {label}" for kind, label in k["anomalies"]]
    if k["visited"] < floor:
        out.append(f"k2 visited {k['visited']} < floor {floor}")
    return out


def k3_problems(rep):
    out = []
    for which in ("rt", "off"):
        for key, want in WANT.items():
            got = rep["k3"][which].get(key)
            if got != want:
                out.append(f"k3 {which}.{key} {got} != {WANT_SHOWN[key]}")
    return out


# The want as a person reads it (-24, not the float32's repr).
WANT_SHOWN = {"threshold": -24, "knee": 30, "ratio": 12, "attack": 0.003, "release": 0.25, "reduction": 0}


def _flat(v, prefix=""):
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            out.update(_flat(x, f"{prefix}.{k}" if prefix else k))
        return out
    return {prefix: v}


def k4_problems(reports, volatile):
    flats = [_flat(r["k4"]) for r in reports]
    out = []
    for leaf in sorted(set().union(*flats)):
        vals = [f.get(leaf) for f in flats]  # absent counts as a value (None)
        if leaf not in volatile and any(v != vals[0] for v in vals):
            out.append(f"k4 {leaf} {vals}")
    return out


def k5_problems(rep, pin):
    return [] if rep["k5"] == pin else [f"k5 uaFullVersion {rep['k5']} != {pin}"]


def r_row_ok(problems, expect):
    return any(expect in p for p in problems)


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/creep/"):
            got = creep_response(self.path[7:].split("?")[0])
        else:
            got = PAGE.encode(), "text/html; charset=utf-8"
        if got is None:
            self.send_error(404)
            return
        body, ctype = got
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def _load(page, url):
    page.goto(url)
    page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=60000)
    rep = json.loads(page.locator("#o").text_content())
    if "error" in rep:
        raise RuntimeError("page error: " + rep["error"])
    return rep


def _group(pw, exe, cfg, fonts_dir, url, init_js, pin):
    """K1-K5 problems under one init script (None: the product untouched). K4 takes three loads."""
    from camoucrome.launcher import launch
    ctx = launch(pw, exe, config=cfg, headless=True, args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader"], fonts_dir=fonts_dir)
    try:
        if init_js is not None:
            ctx.add_init_script(init_js)
        page = ctx.new_page()
        reps = [_load(page, url)]
        reps.append(_load(page, url))
        p2 = ctx.new_page()
        reps.append(_load(p2, url))
    finally:
        ctx.close()
    return {"k1": k1_problems(reps[0]), "k2": k2_problems(reps[0], K2_FLOOR), "k3": k3_problems(reps[0]),
            "k4": k4_problems(reps, K4_VOLATILE), "k5": k5_problems(reps[0], pin)}


def _creep(pw, exe, cfg, fonts_dir, url, init_js):
    """The harness's report for one CreepJS load; a launch or page failure is an error report (FAIL), never a crash."""
    from camoucrome.launcher import launch
    try:
        ctx = launch(pw, exe, config=cfg, headless=True, args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader"], fonts_dir=fonts_dir)
        try:
            if init_js is not None:
                ctx.add_init_script(init_js)
            page = ctx.new_page()
            page.goto(url)
            page.wait_for_selector("#o", state="attached", timeout=100000)
            return json.loads(page.locator("#o").text_content())
        finally:
            ctx.close()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def main() -> int:
    for name, v in (("K2_FLOOR", K2_FLOOR), ("K4_VOLATILE", K4_VOLATILE)):
        if v is None:
            print(f"course not calibrated: {name}")
            return 2
    global CREEP_DIR
    from lib_shell import CHROME, layout
    _home, py, node, CLIENT, fonts_dir = layout()
    # CI runs this file from $VERIFY, which holds no third_party/; the rsynced $CLIENT/scripts does
    CREEP_DIR = CLIENT / "scripts" / "third_party" / "creepjs"
    bad = check_vendor(CREEP_DIR)
    if bad:
        print("vendored CreepJS differs:", bad)
        return 1
    sys.path.insert(0, str(CLIENT / "scripts"))
    sys.path.insert(0, str(CLIENT / "client" / "python"))
    import oracle_rules
    from patchright.sync_api import sync_playwright
    os.environ["PLAYWRIGHT_NODEJS_PATH"] = node
    pin = oracle_rules.read_pin((CLIENT / "upstream.env").read_text(encoding="utf-8"))
    g = subprocess.run([py, "-m", "camoucrome.gen", "--os", "windows", "--seed", os.environ.get("CAMOU_SEED", "1"),
                        "--gpu", "windows-intel-uhd-630-d3d11"], capture_output=True, text=True, timeout=120)
    if g.returncode != 0:
        sys.exit(g.stderr[-500:])
    cfg = json.loads(g.stdout)["config"]
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    creep_url = url + "creep/index.html"
    rows = {}  # label -> (ok, problems)
    with sync_playwright() as pw:
        def grp(js):
            return _group(pw, CHROME, cfg, fonts_dir, url, js, pin)
        try:
            k = grp(None)
        except Exception as e:  # a page that did not report is every K row failing, not a crash
            k = {c: [f"{c} did not report: {e}"] for c in ("k1", "k2", "k3", "k4", "k5")}
        for c in ("k1", "k2", "k3", "k4", "k5"):
            rows[c.upper()] = (not k[c], k[c])
        k6_base = _creep(pw, CHROME, None, fonts_dir, creep_url, None)  # a plain launch: the launcher default
        k6 = k6_problems(k6_base, _creep(pw, CHROME, cfg, fonts_dir, creep_url, None))
        rows["K6"] = (not k6, k6)
        try:
            ctrl = grp(CTRL_JS)
        except Exception as e:
            ctrl = {c: [f"{c} did not report: {e}"] for c in ("k1", "k2", "k3", "k4", "k5")}
        ctrl_clean = not any(ctrl.values())
        rows["CTRL"] = (ctrl_clean, [p for ps in ctrl.values() for p in ps])
        for rid in ("R1", "R2", "R3", "R4", "R6"):
            js, expect = MUTANTS[rid]
            try:
                got = k6_problems(k6_base, _creep(pw, CHROME, cfg, fonts_dir, creep_url, js)) if rid == "R6" else grp(js)[expect.split()[0]]
            except Exception as e:
                rows[rid] = (False, [f"did not report: {e}"])
                continue
            rows[rid] = (r_row_ok(got, expect) and ctrl_clean, got)
    srv.shutdown()
    n = 0
    for label, (ok, problems) in rows.items():
        n += ok
        print("PASS " if ok else "FAIL ", label, "; ".join(problems)[:300])
    print(f"{n} PASS {len(rows) - n} FAIL")
    if len(rows) != EXPECTED_ROWS:
        print(f"FAIL  {len(rows)} rows, expected {EXPECTED_ROWS}")
        return 1
    return 0 if n == EXPECTED_ROWS else 1


if __name__ == "__main__":
    sys.exit(main())
