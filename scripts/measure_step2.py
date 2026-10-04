#!/usr/bin/env python3
"""Roadmap step 2: the fork and stock Chrome through the same client and argv,
headed and headless, every differing row labelled
(docs/superpowers/specs/2026-10-04-step2-measurement-design.md).

Run on the Windows host in the client venv, holding the build lock (owner step2):
  python measure_step2.py run [--only oracle,noise,...] [--modes headed,headless]
                              [--null] [--plant ARG] [--fresh-seeds] [--two-colour]
  python measure_step2.py compare RUN_A RUN_B
  python measure_step2.py tables RUN
--null puts the control executable, unconfigured, in the fork arm: the noise floor.
--plant adds ARG to the fork arm only (a RED). --fresh-seeds draws new seeds per
launch in the stability probe (its RED). --two-colour makes the fork arm's noise
page draw two colours (its RED). The fork is CAMOU_FORK_EXE; the control is the
stock chrome.exe under CAMOU_STOCK_APP (default: the Program Files install)."""
import argparse
import contextlib
import datetime
import http.server
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import capture_host_oracle as cap  # noqa: E402
import step2_rows as rows  # noqa: E402
from windows_verify_set import STOCK_APP, pin_tag  # noqa: E402

PROBES = {}  # name -> fn(pw, arm, mode, run) -> {row: value}; filled below


class Arm:
    """`ident` is a whole camoucrome.gen result ({"config", "launch": {"window", "dpr"}}) or None (stock)."""
    def __init__(self, name, exe, ident, args=()):
        self.name, self.exe, self.ident, self.args = name, exe, ident, list(args)

    @property
    def config(self):
        return self.ident["config"] if self.ident else None

    def without_seeds(self):
        from camoucrome import SEED_KEYS
        return {k: v for k, v in self.config.items() if k not in SEED_KEYS}


def identity(seed):
    """The whole generated identity: the config AND the launch window/dpr a client passes with it."""
    from camoucrome.gen import generate
    return generate("windows", seed=seed)


def exe_version(path):
    p = subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"(Get-Item -LiteralPath '{path}').VersionInfo.ProductVersion"],
                       capture_output=True, text=True, timeout=60)
    return p.stdout.strip()


@contextlib.contextmanager
def serve(body):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}/"
    finally:
        srv.shutdown()


@contextlib.contextmanager
def opened(pw, arm, mode, user_data_dir=None, config="arm", ident=None):
    """`ident` overrides the arm's identity (linkability's second profile); `config`
    overrides only the config (stability's seeds), keeping the identity's window/dpr."""
    from camoucrome import launch
    ident = ident or arm.ident
    lo = ident["launch"] if ident else {}
    ctx = launch(pw, arm.exe, config=(ident["config"] if ident else None) if config == "arm" else config,
                 headless=mode == "headless", user_data_dir=user_data_dir, args=arm.args,
                 window=tuple(lo["window"]) if lo.get("window") else None, dpr=lo.get("dpr"))
    try:
        yield ctx
    finally:
        ctx.close()


def first_page(ctx):
    return ctx.pages[0] if ctx.pages else ctx.new_page()


def read_oracle(ctx, url):
    page = first_page(ctx)
    page.goto(url, wait_until="load")
    page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=90000)
    return rows.flatten(json.loads(page.locator("#o").text_content()))


def probe_oracle(pw, arm, mode, run):
    with serve(cap.page().encode()) as url, opened(pw, arm, mode) as ctx:
        return {f"oracle.{k}": v for k, v in read_oracle(ctx, url).items()}


PROBES["oracle"] = probe_oracle


def argv_of(pw, arm):
    from camoucrome.probe import browser_argv
    with opened(pw, arm, "headless") as ctx:
        first_page(ctx).goto("about:blank")
        return browser_argv(arm.exe)


def run_cmd(a):
    from patchright.sync_api import sync_playwright
    client = os.environ.get("CAMOU_CLIENT", str(HERE.parent))
    stock = os.path.join(os.environ.get("CAMOU_STOCK_APP", STOCK_APP), "chrome.exe")
    fork_exe = stock if a.null else os.environ["CAMOU_FORK_EXE"]
    control = Arm("control", stock, None)  # stock: no config, no window/dpr (its defaults)
    fork = Arm("fork", fork_exe, None if a.null else identity(1), [a.plant] if a.plant else [])
    pin = pin_tag(client)
    versions = {"control": exe_version(control.exe), "fork": exe_version(fork.exe)}
    bad = rows.version_problems(versions, pin)
    if bad:
        sys.exit("precondition: " + "; ".join(bad))
    run_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ("-null" if a.null else "") + ("-plant" if a.plant else "")
    out_dir = pathlib.Path(a.out or tempfile.gettempdir()) / "step2" / run_id
    (out_dir / "raw").mkdir(parents=True)
    run = argparse.Namespace(dir=out_dir, fresh_seeds=a.fresh_seeds, two_colour=a.two_colour)
    doc = {"run": run_id, "versions": versions, "argv": {}, "errors": {},
           "flags": {k: v for k, v in vars(a).items() if k in ("null", "plant", "fresh_seeds", "two_colour") and v},
           "rows": {}}
    with sync_playwright() as pw:
        doc["argv"] = {"control": argv_of(pw, control), "fork": argv_of(pw, fork)}
        bad = rows.argv_problems(doc["argv"]["control"], doc["argv"]["fork"],
                                 rows.ARGV_ALLOWED + ((a.plant,) if a.plant else ()))
        if bad:
            sys.exit("precondition, argv parity: " + "; ".join(bad))
        for probe in a.only.split(","):
            for mode in a.modes.split(","):
                for arm in (control, fork):
                    cell = doc["rows"].setdefault(probe, {}).setdefault(arm.name, {})
                    t0 = time.monotonic()
                    try:
                        cell[mode] = PROBES[probe](pw, arm, mode, run)
                    except Exception as exc:  # noqa: BLE001 - a failed cell is UNMEASURED, recorded
                        cell[mode] = None
                        doc["errors"][f"{probe}/{arm.name}/{mode}"] = f"{type(exc).__name__}: {str(exc)[:300]}"
                    print(f"{probe}/{arm.name}/{mode}: {'ok' if cell[mode] is not None else 'ERROR'} "
                          f"{time.monotonic() - t0:.0f}s", flush=True)
    (out_dir / "rows.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    write_tables(out_dir)
    print(f"run {out_dir}; {len(doc['errors'])} errors")
    return 1 if doc["errors"] else 0


def write_tables(out_dir):
    doc = json.loads((out_dir / "rows.json").read_text(encoding="utf-8"))
    texts = {}
    for site in rows.PARSERS.keys() | {"browserscan", "pixelscan"}:
        for mode in rows.MODES:
            got = [out_dir / "raw" / f"{site}-{arm}-{mode}.txt" for arm in rows.ARMS]
            if any(p.exists() for p in got):
                texts[(site, mode)] = tuple(p.read_text(encoding="utf-8") if p.exists() else None for p in got)
    (out_dir / "tables.md").write_text(rows.render_tables(doc, texts), encoding="utf-8")


def compare_cmd(a):
    docs = [json.loads((pathlib.Path(p) / "rows.json").read_text(encoding="utf-8")) for p in (a.run_a, a.run_b)]
    diffs = rows.compare_runs(*docs)
    for path, va, vb in diffs:
        print(f"DISAGREE {path}: {json.dumps(va)[:120]} vs {json.dumps(vb)[:120]}")
    print(f"{len(diffs)} rows disagree outside VOLATILE")
    return 1 if diffs else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--only", default=",".join(PROBES))
    r.add_argument("--modes", default=",".join(rows.MODES))
    r.add_argument("--out")
    r.add_argument("--null", action="store_true")
    r.add_argument("--plant")
    r.add_argument("--fresh-seeds", action="store_true")
    r.add_argument("--two-colour", action="store_true")
    c = sub.add_parser("compare")
    c.add_argument("run_a")
    c.add_argument("run_b")
    t = sub.add_parser("tables")
    t.add_argument("run_dir")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return run_cmd(a)
    if a.cmd == "compare":
        return compare_cmd(a)
    write_tables(pathlib.Path(a.run_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
