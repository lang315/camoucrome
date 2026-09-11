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
if (-not $p.WaitForExit({timeout_s * 1000})) {{ Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue; "TIMEOUT" }}
Get-Process chrome -ErrorAction SilentlyContinue | Where-Object {{ $_.Path -eq "{CHROME}" -and $_.StartTime -gt (Get-Date).AddMinutes(-{timeout_s // 60 + 2}) -and $_.CommandLine -like "*$tmp*" }} | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Content -Raw $out
"----STDERR----"
Get-Content -Raw $err
Start-Sleep -Milliseconds 500
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
"""
    out = powershell(ps, timeout=timeout_s + 120)
    m = re.search(r'<pre id="o">(.*?)</pre>', out, re.S)
    if not m:
        raise RuntimeError("no #o in the dumped DOM: " + out[-800:])
    return json.loads(html.unescape(m.group(1)))



PS_CDP = r"""
Add-Type -AssemblyName System.Net.WebSockets
function Cdp-Connect($url) {
  $ws = New-Object System.Net.WebSockets.ClientWebSocket
  $ws.ConnectAsync([Uri]$url, [Threading.CancellationToken]::None).Wait()
  return $ws
}
function Cdp-Send($ws, $obj) {
  $bytes = [Text.Encoding]::UTF8.GetBytes(($obj | ConvertTo-Json -Compress -Depth 6))
  $ws.SendAsync([ArraySegment[byte]]$bytes, [Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None).Wait()
}
function Cdp-Recv($ws, $ms) {
  $buf = New-Object byte[] 4194304
  $seg = [ArraySegment[byte]]$buf
  $text = ""
  $cts = New-Object Threading.CancellationTokenSource($ms)
  do {
    $t = $ws.ReceiveAsync($seg, $cts.Token)
    try { $t.Wait() } catch { return $null }
    $r = $t.Result
    $text += [Text.Encoding]::UTF8.GetString($buf, 0, $r.Count)
  } while (-not $r.EndOfMessage)
  return $text
}
"""


def cdp_eval(page_html, expression="document.getElementById('o').textContent", args=(), headed=True, profile=None, wait_ms=1500):
    """Runs stock Chrome on the host with --remote-debugging-port (headed by
    default: --dump-dom does not work headed), loads `page_html` from a temp
    file, evaluates `expression` through a .NET ClientWebSocket on the host
    itself (no port forward: the ssh mux master refuses forwards), returns
    the JSON-parsed value. `profile` keeps a profile dir across calls."""
    b64 = base64.b64encode(page_html.encode()).decode()
    prof = profile or "$env:TEMP\\camou_cdp_" + str(os.getpid())
    argv = ["--no-first-run", "--no-default-browser-check", "--remote-debugging-port=9333", "--remote-allow-origins=*", *args]
    if not headed:
        argv.insert(0, "--headless=new")
    arglist = ", ".join(json.dumps(a) for a in argv)
    ps = PS_CDP + f"""
$tmp = Join-Path $env:TEMP ("camou_cdp_page_" + $PID)
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$html = Join-Path $tmp "page.html"
[IO.File]::WriteAllBytes($html, [Convert]::FromBase64String("{b64}"))
$url = "file:///" + ($html -replace '\\', '/')
Get-Process chrome -ErrorAction SilentlyContinue | Where-Object {{ $_.CommandLine -like "*remote-debugging-port=9333*" }} | Stop-Process -Force -ErrorAction SilentlyContinue
$p = Start-Process -FilePath "{CHROME}" -ArgumentList @({arglist}, "--user-data-dir={prof}", $url) -WindowStyle Hidden -PassThru
$ver = $null
for ($i = 0; $i -lt 40 -and -not $ver; $i++) {{ Start-Sleep -Milliseconds 500; try {{ $ver = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:9333/json/list).Content }} catch {{ }} }}
Start-Sleep -Milliseconds {wait_ms}
$pages = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:9333/json/list).Content | ConvertFrom-Json
$pg = $pages | Where-Object {{ $_.type -eq "page" -and $_.url -like "file:*" }} | Select-Object -First 1
if (-not $pg) {{ $pg = $pages | Where-Object {{ $_.type -eq "page" }} | Select-Object -First 1 }}
$ws = Cdp-Connect $pg.webSocketDebuggerUrl
Cdp-Send $ws @{{ id = 1; method = "Runtime.evaluate"; params = @{{ expression = {json.dumps(expression)}; returnByValue = $true }} }}
$resp = $null
for ($i = 0; $i -lt 20 -and -not $resp; $i++) {{ $m = Cdp-Recv $ws 5000; if ($m -and $m -match '"id":1[,}}]') {{ $resp = $m }} }}
"CDP_RESULT_BEGIN"
$resp
"CDP_RESULT_END"
$ws.Dispose()
Get-Process chrome -ErrorAction SilentlyContinue | Where-Object {{ $_.CommandLine -like "*remote-debugging-port=9333*" }} | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
"""
    out = powershell(ps, timeout=180)
    m = re.search(r"CDP_RESULT_BEGIN\n(.*?)\nCDP_RESULT_END", out, re.S)
    if not m or not m.group(1).strip():
        raise RuntimeError("no CDP result: " + out[-800:])
    resp = json.loads(m.group(1))
    value = resp["result"]["result"].get("value")
    return json.loads(value) if isinstance(value, str) and value[:1] in "{[" else value


class CdpChrome:
    """A stock Chrome on the host with --remote-debugging-port, reachable from
    here through an ssh -L forward; use as a context manager and connect with
    playwright's connect_over_cdp on `self.url`. Headed launches work (a
    window in the SSH session is invisible); --dump-dom does not in headed
    mode, which is why this exists. The temp profile is kept across
    launches when `profile` is given (the two-launch X-Client-Data RED)."""

    def __init__(self, args=(), headed=False, port=9333, profile=None):
        self.args, self.headed, self.port, self.profile = list(args), headed, port, profile
        self.url = f"http://127.0.0.1:{port}"
        self.forward = None

    def __enter__(self):
        prof = self.profile or "$env:TEMP\\camou_cdp_profile_" + str(os.getpid())
        argv = ["--no-first-run", "--no-default-browser-check", f"--remote-debugging-port={self.port}",
                "--remote-allow-origins=*", *self.args]
        if not self.headed:
            argv.insert(0, "--headless=new")
        arglist = ", ".join(json.dumps(a) for a in argv)
        powershell(f"""
Get-Process chrome -ErrorAction SilentlyContinue | Where-Object {{ $_.CommandLine -like "*remote-debugging-port={self.port}*" }} | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Process -FilePath "{CHROME}" -ArgumentList @({arglist}, "--user-data-dir={prof}", "about:blank") -WindowStyle Hidden
Start-Sleep -Seconds 3
"STARTED {prof}"
""")
        self.forward = subprocess.Popen(SSH[:-1] + ["-N", "-L", f"{self.port}:127.0.0.1:{self.port}", "buildpc"],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import time, urllib.request
        for _ in range(40):
            try:
                urllib.request.urlopen(f"{self.url}/json/version", timeout=2).read()
                return self
            except Exception:
                time.sleep(0.5)
        self.__exit__(None, None, None)
        raise RuntimeError("no CDP endpoint through the forward")

    def __exit__(self, *a):
        if self.forward:
            self.forward.kill()
        powershell(f"Get-Process chrome -ErrorAction SilentlyContinue | Where-Object {{ $_.CommandLine -like '*remote-debugging-port={self.port}*' }} | Stop-Process -Force -ErrorAction SilentlyContinue; 'STOPPED'")
