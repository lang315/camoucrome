"""navigator.connection and maxChannelCount on the Windows host: stock Chrome
against the fork without config, N launches per arm, alternating.

Run in the client venv on the host, holding the build lock:
  python measure_netinfo.py run [--runs 10] [--mode headed|headless] [--out DIR] [--label L]
Prints one verdict line per row and writes the launches to DIR/<label>.json.
Spec: docs/superpowers/specs/2026-11-13-netinfo-channels-design.md.
"""
import argparse
import datetime
import json
import os
import pathlib
import statistics
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# The fetches warm the network estimator (it reads Chrome's default before any
# observation); `fetched` lets verdicts() drop a launch that read too early. The
# worker is read after the window: a worker that never answers is null, not a mismatch.
PAGE = b"""<!doctype html><title>netinfo</title><pre id="o"></pre><script>
const rd=c=>({effectiveType:c.effectiveType,rtt:c.rtt,downlink:c.downlink,saveData:c.saveData,hasType:'type' in c});
(async()=>{const out={fetched:0,win:null,worker:null,audio:null};
try{const r=await Promise.allSettled(Array.from({length:10},()=>fetch('https://www.gstatic.com/generate_204',{mode:'no-cors',cache:'no-store'})));
out.fetched=r.filter(x=>x.status==='fulfilled').length;
await new Promise(r=>setTimeout(r,5000));
out.win=rd(navigator.connection);
const u=URL.createObjectURL(new Blob(['const c=navigator.connection;postMessage({effectiveType:c.effectiveType,rtt:c.rtt,downlink:c.downlink,saveData:c.saveData,hasType:"type" in c})']));
const w=new Worker(u);
out.worker=await new Promise(res=>{w.onmessage=e=>res(e.data);w.onerror=()=>res(null);setTimeout(()=>res(null),10000)});
w.terminate();
try{const a=new AudioContext();out.audio=[a.destination.maxChannelCount,a.destination.channelCount];a.close()}catch(e){out.audio=null}
}catch(e){out.error=String(e)}
document.getElementById('o').textContent=JSON.stringify(out)})();
</script>"""

NEED = 5  # usable launches per arm below which a row measured nothing
KEYS = ("effectiveType", "rtt", "downlink", "saveData", "hasType")


def verdicts(stock, fork):
    """(name, ok, detail) rows; ok is None when the row measured nothing."""
    s, f = ([r for r in a if r["fetched"] >= 8 and r["win"]] for a in (stock, fork))
    out = []

    def row(name, s_, f_, check):
        if min(len(s_), len(f_)) < NEED:
            out.append((name, None, f"usable launches: stock {len(s_)}, fork {len(f_)}, need {NEED}"))
        else:
            out.append((name,) + check(s_, f_))

    # Chrome salts rtt/downlink per read, so stock's own worker differs from its window
    # (run 20261113-025840: downlink 10/10): exact keys must agree, the estimates must read as stock's worker.
    def v1(s_, f_):
        exact = ("effectiveType", "saveData", "hasType")
        diff = lambda a: sum(any(r["win"][k] != r["worker"][k] for k in exact) for r in a)
        ok, d = diff(f_) == 0, [f"exact keys differ: fork {diff(f_)}/{len(f_)}, stock {diff(s_)}/{len(s_)}"]
        for k in ("rtt", "downlink"):
            col = lambda a: [r["worker"][k] for r in a]
            lo, hi, med = min(col(s_)), max(col(s_)), statistics.median(col(f_))
            ok &= lo <= med <= hi
            d.append(f"worker {k} fork median {med} stock [{lo}, {hi}]")
        return ok, ", ".join(d)

    def v2(s_, f_):
        vals = lambda a, k: {r["win"][k] for r in a}
        ok = all(vals(s_, k) == vals(f_, k) for k in ("effectiveType", "hasType"))
        return ok, (f"effectiveType stock {sorted(vals(s_, 'effectiveType'))} fork {sorted(vals(f_, 'effectiveType'))}, "
                    f"type present stock {sorted(vals(s_, 'hasType'))} fork {sorted(vals(f_, 'hasType'))}")

    def v3(s_, f_):
        col = lambda a, k: [r["win"][k] for r in a]
        z = lambda a: col(a, "rtt").count(0)
        ok = z(f_) <= z(s_) + 2
        d = [f"rtt0 stock {z(s_)} fork {z(f_)}"]
        for k in ("rtt", "downlink"):
            lo, hi, med = min(col(s_, k)), max(col(s_, k)), statistics.median(col(f_, k))
            ok &= lo <= med <= hi
            d.append(f"{k} fork median {med} stock [{lo}, {hi}]")
        d.append(f"rtt values stock {sorted(set(col(s_, 'rtt')))} fork {sorted(set(col(f_, 'rtt')))}")
        return ok, ", ".join(d)

    row("V1 worker reads what the window reads", [r for r in s if r["worker"]], [r for r in f if r["worker"]], v1)
    row("V2 effectiveType set and type presence equal stock", s, f, v2)
    row("V3 rtt and downlink within stock range, rtt 0 no more often", s, f, v3)

    # Audio does not depend on the estimator, so fetched does not filter it.
    au = lambda a: [r["audio"] for r in a if r["audio"]]
    pairs = {tuple(p) for p in au(stock) + au(fork)}
    row("V4 maxChannelCount and channelCount equal in every launch", au(stock), au(fork),
        lambda *_: (len(pairs) == 1, f"pairs seen: {sorted(pairs)}"))
    return out


def run_cmd(a):
    from patchright.sync_api import sync_playwright

    import measure_step2 as m2
    import step2_rows as rows
    from windows_verify_set import STOCK_APP, pin_tag

    client = os.environ.get("CAMOU_CLIENT", str(HERE.parent))
    stock_exe = os.path.join(os.environ.get("CAMOU_STOCK_APP", STOCK_APP), "chrome.exe")
    fork_exe = os.environ["CAMOU_FORK_EXE"]
    bad = rows.version_problems({"control": m2.exe_version(stock_exe), "fork": m2.exe_version(fork_exe)},
                                pin_tag(client))
    if bad:
        sys.exit("precondition: " + "; ".join(bad))

    def launch(pw, exe):
        with m2.serve(PAGE) as url, m2.opened(pw, m2.Arm("x", exe, None, stock=exe == stock_exe), a.mode, config=None) as ctx:
            page = m2.first_page(ctx)
            page.goto(url, wait_until="load")
            page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=60000)
            return json.loads(page.locator("#o").text_content())

    stock, fork = [], []
    with m2.seeded_control(stock_exe), sync_playwright() as pw:
        for _ in range(a.runs):
            stock.append(launch(pw, stock_exe))
            fork.append(launch(pw, fork_exe))
    rows_out = verdicts(stock, fork)
    label = a.label or datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = pathlib.Path(a.out or tempfile.gettempdir())
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{label}.json").write_text(json.dumps(
        {"mode": a.mode, "runs": a.runs, "stock": stock, "fork": fork, "verdicts": rows_out}, indent=1), encoding="utf-8")
    for name, ok, detail in rows_out:
        print(f"{'UNMEASURED' if ok is None else 'PASS' if ok else 'FAIL'}  {name}  ({detail})")
    print(f"launches: {out_dir / (label + '.json')}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--runs", type=int, default=10)
    r.add_argument("--mode", choices=("headed", "headless"), default="headed")
    r.add_argument("--out")
    r.add_argument("--label")
    return run_cmd(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
