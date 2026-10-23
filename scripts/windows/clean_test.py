#!/usr/bin/env python3
"""Clean-machine test: run the README's Install and Quickstart blocks inside Windows Sandbox on the
build host (through winhost's interactive task), time the run, and write a PASS/FAIL report.

Exit: 0 PASS, 1 FAIL, 2 bad input, 3 UNMEASURED (Windows Sandbox not enabled on the host).
The GitHub token goes into token.env in the read-only mapped folder, is removed in a `finally`,
and is redacted from everything the runner prints or writes."""
import argparse
import base64
import datetime
import pathlib
import re
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import winhost  # noqa: E402

MAX_ELAPSED_S = 900
POLL_CAP_S = 20 * 60
EXT = {"powershell": "ps1", "ps1": "ps1", "pwsh": "ps1", "cmd": "cmd", "bat": "cmd"}
HOST_DIR = "(Join-Path $env:TEMP 'camou-clean-{stamp}')"


def fenced_blocks(readme, heading):
    """[(lang, text)] of the fenced blocks under `## heading`, up to the next `## `."""
    m = re.search(r"^## " + re.escape(heading) + r"\s*$(.*?)(?=^## |\Z)", readme, re.M | re.S)
    if not m:
        return []
    return [(lang, body.rstrip("\n")) for lang, body in re.findall(r"^```(\w*)\n(.*?)^```", m.group(1), re.M | re.S)]


def parse_transcript(text):
    """(verdict, reasons, identities). PASS needs: every step rc 0, RUN_DONE with elapsed <= 15 min,
    both identities printed, and screen.width or hardwareConcurrency differing."""
    why = [f"step {n} rc={rc}" for n, rc in re.findall(r"^=== END (\S+) rc=(-?\d+)$", text, re.M) if rc != "0"]
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


def redact(s, token):
    return s.replace(token, "[REDACTED]") if token else s


def fill(s, **kv):
    for k, v in kv.items():
        s = s.replace("{{" + k + "}}", v)
    return s


def _put(d, rel, data):
    b = base64.b64encode(data if isinstance(data, bytes) else data.encode()).decode()
    return (f"$p = Join-Path {d} '{rel}'; New-Item -ItemType Directory -Force -Path (Split-Path $p) | Out-Null; "
            f"[IO.File]::WriteAllBytes($p, [Convert]::FromBase64String('{b}'))\n")


def main(argv=None, get_token=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--chrome-version", required=True)
    ap.add_argument("--repo", default="lang315/camoucrome")
    ap.add_argument("--readme", default=str(HERE.parent.parent / "README.md"))
    ap.add_argument("--report-dir", default=str(pathlib.Path.home() / ".local/share/camoucrome/clean-test"))
    ap.add_argument("--poll-s", type=float, default=20)
    a = ap.parse_args(argv)
    get_token = get_token or (lambda: subprocess.check_output(["gh", "auth", "token"], text=True).strip())

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

    def fill_readme(s):
        return s.replace("<tag>", a.tag).replace("<sha>", a.sha).replace("<chrome-version>", a.chrome_version)

    files = {}
    for i, (lang, body) in enumerate(install, 1):
        if lang not in EXT:
            print(f"README Install block {i}: unsupported language {lang!r}")
            return 2
        files[f"install-{i}.{EXT[lang]}"] = fill_readme(body) + "\n"
    files["quickstart.py"] = fill_readme(quick[0][1]) + "\n"
    files["README.md"] = readme
    files["run.ps1"] = fill(( HERE / "clean-test-run.ps1.template").read_text(),
                            REPO=a.repo, TAG=a.tag, CHROME_VERSION=a.chrome_version)
    wsb = (HERE / "clean-test.wsb.template").read_text()

    token = get_token()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%MZ")
    d = HOST_DIR.format(stamp=stamp)
    transcript = ""
    t0 = time.monotonic()
    try:
        setup = f"$d = {d}\n" + "".join(_put("$d", "in/" + n, c) for n, c in files.items())
        setup += _put("$d", "in/token.env", "GH_TOKEN=" + token)
        setup += ("New-Item -ItemType Directory -Force -Path (Join-Path $d 'out') | Out-Null\n"
                  f"$w = '{base64.b64encode(wsb.encode()).decode()}'\n"
                  "$x = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($w))"
                  ".Replace('{{IN_DIR}}', (Join-Path $d 'in')).Replace('{{OUT_DIR}}', (Join-Path $d 'out'))\n"
                  "Set-Content -Path (Join-Path $d 'clean.wsb') -Value $x -Encoding UTF8\n")
        winhost.powershell(setup, timeout=120)
        winhost.powershell(f"$d = {d}\nStart-Process WindowsSandbox.exe -ArgumentList (Join-Path $d 'clean.wsb')\n", timeout=60)
        poll = (f"$d = {d}\n$f = Join-Path $d 'out\\transcript.txt'\n'TRANSCRIPT_BEGIN'\n"
                "if (Test-Path $f) { Get-Content -Raw $f }\n'TRANSCRIPT_END'\n")
        while True:
            r = winhost.powershell(poll, timeout=60)
            mt = re.search(r"TRANSCRIPT_BEGIN\n(.*)TRANSCRIPT_END", r, re.S)
            transcript = mt.group(1) if mt else ""
            if "RUN_DONE" in transcript or time.monotonic() - t0 > POLL_CAP_S:
                break
            time.sleep(a.poll_s)
    except Exception as e:
        raise RuntimeError(redact(str(e), token)) from None
    finally:
        try:
            winhost.powershell(f"$d = {d}\nRemove-Item -Force -ErrorAction SilentlyContinue (Join-Path $d 'in\\token.env')\n"
                               "Get-Process WindowsSandbox*,vmmem* -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue\n"
                               "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $d\n", timeout=60)
        except Exception as e:
            print("CLEANUP FAILED, remove the host temp folder by hand:", redact(str(e), token)[-200:])

    transcript = redact(transcript.replace("\r", ""), token)
    verdict, why, ids = parse_transcript(transcript)
    rep = pathlib.Path(a.report_dir)
    rep.mkdir(parents=True, exist_ok=True)
    path = rep / f"clean-test-{stamp}.md"
    blocks = "\n".join(f"### {n}\n```\n{c}```\n" for n, c in files.items() if n.startswith(("install-", "quickstart")))
    path.write_text(f"# Clean-machine test {stamp}\n\nVerdict: {verdict}\n\n"
                    + "".join(f"- {w}\n" for w in why)
                    + f"\nIdentities (hardwareConcurrency, screen.width): {ids}\nWall time: {int(time.monotonic() - t0)} s\n\n"
                    f"## README commands run\n\n{blocks}\n## Transcript\n\n```\n{transcript}\n```\n")
    print(f"{verdict}: {path}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
