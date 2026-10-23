#!/usr/bin/env python3
"""Clean-machine test: run the README's Install and Quickstart blocks inside Windows Sandbox on the
build host (through winhost's interactive task), time the run, and write a PASS/FAIL report.

Exit: 0 PASS, 1 FAIL, 2 bad input, 3 UNMEASURED (Windows Sandbox not enabled on the host).
The Mac downloads the draft release with gh and copies every file to the host by scp, so no
credential and no payload goes through winhost.powershell, which carries short commands only.
One sanctioned deviation: the README's download block is skipped, because the Mac staged the
assets into the working folder; the report names it."""
import argparse
import datetime
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import winhost  # noqa: E402

MAX_ELAPSED_S = 900
POLL_CAP_S = 20 * 60
HOST_ROOT = "D:/camou-win/clean-test"
STAGED = "download step staged by the runner"


def fenced_blocks(readme, heading):
    """[(lang, text)] of the fenced blocks under `## heading`, up to the next `## `."""
    m = re.search(r"^## " + re.escape(heading) + r"\s*$(.*?)(?=^## |\Z)", readme, re.M | re.S)
    if not m:
        return []
    return [(lang, body.rstrip("\n")) for lang, body in re.findall(r"^```(\w*)\n(.*?)^```", m.group(1), re.M | re.S)]


def parse_transcript(text):
    """(verdict, reasons, identities). PASS needs: every step rc 0, the checksum step printing True,
    RUN_DONE with elapsed <= 15 min, both identities printed, and screen.width or
    hardwareConcurrency differing."""
    why = [f"step {n} rc={rc}" for n, rc in re.findall(r"^=== END (\S+) rc=(-?\d+)$", text, re.M) if rc != "0"]
    for n, body in re.findall(r"^=== BEGIN (\S*checksum\S*)\n(.*?)^=== END \1 rc=", text, re.M | re.S):
        if not re.search(r"^True$", body, re.M):
            why.append(f"checksum step {n} did not print True")
    ids = {n: (int(a), int(b)) for n, a, b in re.findall(r"^(alice|bob) \[(\d+), (\d+)\]$", text, re.M)}
    for n in ("alice", "bob"):
        if n not in ids:
            why.append(f"identity {n} printed no values")
    if len(ids) == 2 and ids["alice"] == ids["bob"]:
        why.append("identities do not differ in hardwareConcurrency or screen.width")
    m = re.search(r"^RUN_DONE elapsed=(\d+)$", text, re.M)
    if not m:
        why.append("no RUN_DONE line (run did not finish)")
    elif int(m.group(1)) > MAX_ELAPSED_S:
        why.append(f"elapsed {m.group(1)} s > {MAX_ELAPSED_S} s")
    return ("FAIL" if why else "PASS"), why, ids


def gh_download(repo, tag, dest):
    """The Mac fetches the draft release's assets with its own gh login."""
    subprocess.run(["gh", "release", "download", tag, "--repo", repo, "--dir", str(dest)],
                   check=True, capture_output=True, text=True)


def scp(local, remote):
    """Copy `local` (file or directory) to the build host over the existing master connection."""
    subprocess.run(["/usr/bin/scp", "-r", *winhost.SSH[1:-1], str(local), f"{winhost.SSH[-1]}:{remote}"],
                   check=True, capture_output=True, text=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--chrome-version", required=True)
    ap.add_argument("--repo", default="lang315/camoucrome")
    ap.add_argument("--readme", default=str(HERE.parent.parent / "README.md"))
    ap.add_argument("--report-dir", default=str(pathlib.Path.home() / ".local/share/camoucrome/clean-test"))
    ap.add_argument("--poll-s", type=float, default=20)
    a = ap.parse_args(argv)

    out = winhost.powershell(
        "$s = (Get-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -ErrorAction SilentlyContinue).State\n"
        "'FEATURE=' + $s\n", timeout=60)
    m = re.search(r"^FEATURE=(\w*)$", out, re.M)
    if not m or m.group(1) != "Enabled":
        print(f"UNMEASURED: Windows Sandbox not available on the host (Containers-DisposableClientVM "
              f"state: {m.group(1) if m and m.group(1) else 'unknown'}); enabling it needs a reboot", flush=True)
        return 3

    readme = pathlib.Path(a.readme).read_text()
    install = fenced_blocks(readme, "Install")
    quick = fenced_blocks(readme, "Quickstart: two identities")
    if not install or len(quick) != 1:
        print(f"README: {len(install)} fenced Install blocks (need >= 1), {len(quick)} Quickstart blocks (need 1)")
        return 2

    def fill(s):
        return s.replace("<tag>", a.tag).replace("<sha>", a.sha).replace("<chrome-version>", a.chrome_version)

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%MZ")
    host = f"{HOST_ROOT}/{stamp}"
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="camou-clean-"))
    ran, skipped = [], []
    (tmp / "in" / "assets").mkdir(parents=True)
    for i, (lang, body) in enumerate(install, 1):
        if lang not in ("powershell", "ps1", "pwsh"):
            print(f"README Install block {i}: unsupported language {lang!r}")
            shutil.rmtree(tmp)
            return 2
        name = f"install-{i}" + ("-checksum" if "Get-FileHash" in body else "-download" if "releases/download/<tag>" in body else "")
        if name.endswith("-download"):
            skipped.append(name)
            continue
        (tmp / "in" / f"{name}.ps1").write_text(fill(body) + "\n")
        ran.append((name, fill(body)))
    (tmp / "in" / "quickstart.py").write_text(fill(quick[0][1]) + "\n")
    shutil.copy(HERE / "clean-test-run.ps1.template", tmp / "in" / "run.ps1")
    (tmp / "in" / "README.md").write_text(readme)
    wsb = (HERE / "clean-test.wsb.template").read_text()
    host_win = host.replace("/", "\\")
    (tmp / "clean.wsb").write_text(wsb.replace("{{IN_DIR}}", host_win + "\\in").replace("{{OUT_DIR}}", host_win + "\\out"))

    d = f"$d = '{host}'\n"
    t0 = time.monotonic()
    transcript, warn = "", ""
    mkdir_done = False
    try:
        gh_download(a.repo, a.tag, tmp / "in" / "assets")
        winhost.powershell(d + "New-Item -ItemType Directory -Force -Path (Join-Path $d 'out') | Out-Null\n", timeout=60)
        mkdir_done = True
        scp(tmp / "in", host + "/")
        scp(tmp / "clean.wsb", host + "/clean.wsb")
        winhost.powershell(d + "Start-Process WindowsSandbox.exe -ArgumentList (Join-Path $d 'clean.wsb')\n", timeout=60)
        poll = (d + "$f = Join-Path $d 'out\\transcript.txt'\n'TRANSCRIPT_BEGIN'\n"
                "if (Test-Path $f) { Get-Content -Raw $f }\n'TRANSCRIPT_END'\n")
        while True:
            r = winhost.powershell(poll, timeout=60)
            mt = re.search(r"TRANSCRIPT_BEGIN\n(.*)TRANSCRIPT_END", r, re.S)
            transcript = mt.group(1) if mt else ""
            if "RUN_DONE" in transcript or time.monotonic() - t0 > POLL_CAP_S:
                break
            time.sleep(a.poll_s)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if mkdir_done:
            r = winhost.powershell(d + "Get-Process WindowsSandbox* -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue\n"
                                   "Start-Sleep -Seconds 3\nRemove-Item -Recurse -Force -ErrorAction SilentlyContinue $d\n"
                                   "if (Test-Path $d) { 'WARN: host folder still present: ' + $d }\n", timeout=60)
            warn = "\n".join(l for l in r.splitlines() if l.startswith("WARN"))
            if warn:
                print(warn)

    transcript = transcript.replace("\r", "")
    verdict, why, ids = parse_transcript(transcript)
    shown = f"{verdict} ({STAGED})" if verdict == "PASS" else verdict
    rep = pathlib.Path(a.report_dir)
    rep.mkdir(parents=True, exist_ok=True)
    path = rep / f"clean-test-{stamp}.md"
    blocks = "\n".join(f"### {n}\n```\n{c}\n```\n" for n, c in ran)
    path.write_text(f"# Clean-machine test {stamp}\n\nVerdict: {shown}\n\n"
                    + "".join(f"- {w}\n" for w in why)
                    + f"\nSanctioned deviation: README block(s) {', '.join(skipped) or 'none'} skipped; {STAGED}.\n"
                    + (f"{warn}\n" if warn else "")
                    + f"\nIdentities (hardwareConcurrency, screen.width): {ids}\nWall time: {int(time.monotonic() - t0)} s\n\n"
                    f"## README commands run\n\n{blocks}\n## Transcript\n\n```\n{transcript}\n```\n")
    print(f"{shown}: {path}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
