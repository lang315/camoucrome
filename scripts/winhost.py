"""Runs stock Chrome 153.0.8010.36 on the build box's Windows host (the
same tag as the pin) and returns what a page reports. PowerShell over
OpenSSH; every launch gets a temp profile and --dump-dom, so nothing on
the host's own Chrome is touched. Linux side: scripts/lib_shell.py."""
import base64
import html
import json
import os
import re
import subprocess

SSH = ["/usr/bin/ssh", "-o", "BatchMode=yes", "-o", "PasswordAuthentication=no",
       "-o", "PubkeyAuthentication=no", "-o", "ControlMaster=no",
       "-o", f"ControlPath={os.path.expanduser('~')}/.ssh/cm-buildpc", "buildpc"]
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def powershell(script, timeout=300):
    p = subprocess.run(SSH + [script], capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"powershell rc={p.returncode}: {p.stderr[-800:]}")
    return p.stdout.replace("\r", "")


def dump_dom(page_html, args=(), headed=False, timeout_s=60):
    """Loads `page_html` (a page that writes JSON into <pre id="o">) in stock
    Chrome on the host and returns that JSON."""
    b64 = base64.b64encode(page_html.encode()).decode()
    argv = ["--no-first-run", "--no-default-browser-check", *args]
    if not headed:
        argv.insert(0, "--headless=new")
    arglist = ", ".join(json.dumps(a) for a in argv)
    ps = f"""
$tmp = Join-Path $env:TEMP ("camou_" + $PID)
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$html = Join-Path $tmp "page.html"
[IO.File]::WriteAllBytes($html, [Convert]::FromBase64String("{b64}"))
$out = Join-Path $tmp "dom.html"
$err = Join-Path $tmp "err.txt"
$url = "file:///" + ($html -replace '\\\\', '/')
$p = Start-Process -FilePath "{CHROME}" -ArgumentList @({arglist}, "--user-data-dir=$tmp\\profile", "--dump-dom", $url) -RedirectStandardOutput $out -RedirectStandardError $err -PassThru -WindowStyle Hidden
if (-not $p.WaitForExit({timeout_s * 1000})) {{ $p.Kill(); "TIMEOUT" }}
Get-Content -Raw $out
"----STDERR----"
Get-Content -Raw $err
Remove-Item -Recurse -Force $tmp
"""
    out = powershell(ps, timeout=timeout_s + 120)
    m = re.search(r'<pre id="o">(.*?)</pre>', out, re.S)
    if not m:
        raise RuntimeError("no #o in the dumped DOM: " + out[-800:])
    return json.loads(html.unescape(m.group(1)))
