"""Runs stock Chrome 154.0.8037.93 on the build box's Windows host (the
same tag as the pin) and returns what a page reports. PowerShell over
OpenSSH; every launch gets a temp profile and --dump-dom, so nothing on
the host's own Chrome is touched. Linux side: scripts/lib_shell.py.

Every script runs in the owner's interactive session through a temporary
scheduled task (S4: in session 0, where sshd puts this shell, the GPU
process crashes once per launch); output from session 0 is refused, and
the CDP paths refuse a browser whose chrome://gpu reports a crash
(gpu_gate.py). CAMOU_WINHOST_NO_TASK=1 / CAMOU_ALLOW_SESSION0=1 are for REDs."""
import base64
import html
import json
import os
import re
import subprocess

import gpu_gate

SSH = ["/usr/bin/ssh", "-o", "BatchMode=yes", "-o", "PasswordAuthentication=no",
       "-o", "PubkeyAuthentication=no", "-o", "ControlMaster=no",
       "-o", f"ControlPath={os.path.expanduser('~')}/.ssh/cm-buildpc", "buildpc"]
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def ps_quote(s):
    """A PowerShell single-quoted literal: no $ expansion, no escapes, a quote
    (PowerShell also counts the typographic ones) is doubled."""
    return "'" + re.sub("(['\u2018\u2019\u201a\u201b])", r"\1\1", s) + "'"


PS_IN_SESSION = r"""
$t = "camou-winhost-" + $PID
$d = Join-Path $env:TEMP $t
New-Item -ItemType Directory -Force -Path $d | Out-Null
$body = Join-Path $d "body.ps1"
$out = Join-Path $d "out.txt"
$inner = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("__B64__"))
[IO.File]::WriteAllText($body, "& {`n" + $inner + "`n} *> '" + $out + "'", (New-Object Text.UTF8Encoding $true))
$a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ("-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File " + $body)
$p = New-ScheduledTaskPrincipal -UserId (whoami) -LogonType Interactive
Register-ScheduledTask -TaskName $t -Action $a -Principal $p -Force | Out-Null
Start-ScheduledTask -TaskName $t
Start-Sleep -Seconds 1
$deadline = (Get-Date).AddSeconds(__TIMEOUT__)
while ((Get-ScheduledTask -TaskName $t).State -eq "Running" -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
if ((Get-ScheduledTask -TaskName $t).State -eq "Running") { Stop-ScheduledTask -TaskName $t; "IN_SESSION_TIMEOUT" }
Unregister-ScheduledTask -TaskName $t -Confirm:$false
if (Test-Path $out) { Get-Content -Raw $out }
Remove-Item -Recurse -Force $d -ErrorAction SilentlyContinue
"""
SESSION_LINE = '"SESSION=" + (Get-Process -Id $PID).SessionId\n'


def in_session(script, timeout_s):
    """`script` run by a temporary scheduled task in the owner's interactive session
    (S4: in session 0, where sshd puts this shell, the GPU process crashes once per
    launch). The output comes back through a file; the task is removed afterwards."""
    b64 = base64.b64encode(script.encode()).decode()
    return PS_IN_SESSION.replace("__B64__", b64).replace("__TIMEOUT__", str(int(timeout_s)))


def session_gate(out):
    """Refuse output from session 0, or with no SESSION line, unless CAMOU_ALLOW_SESSION0=1 (a RED)."""
    if os.environ.get("CAMOU_ALLOW_SESSION0") == "1":
        return
    m = re.search(r"^SESSION=(\d+)$", out, re.M)
    why = (gpu_gate.session_problem(int(m.group(1))) if m
           else "UNMEASURED session=unknown: the host printed no SESSION line")
    if why:
        print(why, flush=True)
        raise gpu_gate.Unmeasured(why)


def powershell(script, timeout=300):
    """Runs `script` on the host in the owner's interactive session (CAMOU_WINHOST_NO_TASK=1:
    in this ssh session, which is session 0 -- a RED) and refuses output from session 0."""
    script = SESSION_LINE + script
    if os.environ.get("CAMOU_WINHOST_NO_TASK") != "1":
        script = in_session(script, timeout)
    p = subprocess.run(SSH + [script], capture_output=True, text=True, timeout=timeout + 60)
    if p.returncode != 0:
        raise RuntimeError(f"powershell rc={p.returncode}: {p.stderr[-800:]}")
    out = p.stdout.replace("\r", "")
    session_gate(out)
    return out


def dump_dom(page_html, args=(), headed=False, timeout_s=60):
    """Loads `page_html` (a page that writes JSON into <pre id="o">) in stock
    Chrome on the host and returns that JSON."""
    b64 = base64.b64encode(page_html.encode()).decode()
    argv = ["--no-first-run", "--no-default-browser-check", *args]
    if not headed:
        argv.insert(0, "--headless=new")
    arglist = ", ".join(ps_quote(a) for a in argv)
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
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object {{ $_.CommandLine -like "*$tmp*" }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
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


# Opens chrome://gpu as a new target of the browser on `port` and prints Runtime.evaluate's answer.
PS_GPU = r"""
try { $gt = (Invoke-WebRequest -UseBasicParsing -Method Put "http://127.0.0.1:__PORT__/json/new?chrome://gpu").Content | ConvertFrom-Json } catch { $gt = $null }
"GPU_BEGIN"
if ($gt) {
  Start-Sleep -Seconds 3
  $gw = Cdp-Connect $gt.webSocketDebuggerUrl
  Cdp-Send $gw @{ id = 9; method = "Runtime.evaluate"; params = @{ expression = __JS__; returnByValue = $true } }
  for ($i = 0; $i -lt 10; $i++) { $m = Cdp-Recv $gw 5000; if ($m -and $m.StartsWith('{"id":9,')) { $m; break } }
  $gw.Dispose()
}
"GPU_END"
"""


def ps_gpu(port=9333):
    return PS_GPU.replace("__PORT__", str(port)).replace("__JS__", ps_quote(gpu_gate.GPU_JS))


def crash_gate(out):
    """GpuCrashed unless the GPU block reads a crash count of 0 (a missing reading is not a pass)."""
    m = re.search(r"GPU_BEGIN\n(.*?)GPU_END", out, re.S)
    text = None
    if m and m.group(1).strip():
        try:
            text = json.loads(m.group(1).strip().splitlines()[0])["result"]["result"]["value"]
        except (ValueError, KeyError, IndexError, TypeError):
            text = None
    n = gpu_gate.crash_count(text)
    if n != 0:
        e = gpu_gate.GpuCrashed(n)
        print(e, flush=True)
        raise e


def cdp_eval(page_html, expression="document.getElementById('o').textContent", args=(), headed=True, profile=None, wait_ms=1500, act_ps="", window_style="Hidden"):
    """Runs stock Chrome on the host with --remote-debugging-port (headed by
    default: --dump-dom does not work headed), loads `page_html` from a temp
    file, evaluates `expression` through a .NET ClientWebSocket on the host
    itself (no port forward: the ssh mux master refuses forwards), returns
    the JSON-parsed value. `profile` keeps a profile dir across calls.
    `act_ps` runs after the page socket `$ws` connects and before the
    evaluate (input to measure); `window_style` "Normal" for real OS input."""
    b64 = base64.b64encode(page_html.encode()).decode()
    prof = profile or "$env:TEMP\\camou_cdp_" + str(os.getpid())
    argv = ["--no-first-run", "--no-default-browser-check", "--remote-debugging-port=9333", "--remote-allow-origins=*", *args]
    if not headed:
        argv.insert(0, "--headless=new")
    arglist = ", ".join(ps_quote(a) for a in argv)
    ps = PS_CDP + f"""
$tmp = Join-Path $env:TEMP ("camou_cdp_page_" + $PID)
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$html = Join-Path $tmp "page.html"
[IO.File]::WriteAllBytes($html, [Convert]::FromBase64String("{b64}"))
$url = "file:///" + ($html -replace '\\\\', '/')
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object {{ $_.CommandLine -like "*remote-debugging-port=9333*" }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
Start-Sleep -Seconds 2
$p = Start-Process -FilePath "{CHROME}" -ArgumentList @({arglist}, "--user-data-dir={prof}", $url) -WindowStyle {window_style} -PassThru
$ver = $null
for ($i = 0; $i -lt 40 -and -not $ver; $i++) {{ Start-Sleep -Milliseconds 500; try {{ $ver = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:9333/json/list).Content }} catch {{ }} }}
Start-Sleep -Milliseconds {wait_ms}
try {{ $raw = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:9333/json/list -ErrorAction Stop).Content }} catch {{ "list error: " + $_; $raw = "[]" }}
$pages = $raw | ConvertFrom-Json
$pg = $pages | Where-Object {{ $_.type -eq "page" -and $_.url -like "file:*" }} | Select-Object -First 1
if (-not $pg) {{ $pg = $pages | Where-Object {{ $_.type -eq "page" }} | Select-Object -First 1 }}
$ws = Cdp-Connect $pg.webSocketDebuggerUrl
{act_ps}
Cdp-Send $ws @{{ id = 1; method = "Runtime.evaluate"; params = @{{ expression = {ps_quote(expression)}; returnByValue = $true }} }}
$resp = $null
for ($i = 0; $i -lt 20 -and -not $resp; $i++) {{ $m = Cdp-Recv $ws 5000; if ($m -and $m.StartsWith('{{"id":1,')) {{ $resp = $m }} }}
"CDP_RESULT_BEGIN"
$resp
"CDP_RESULT_END"
{ps_gpu()}
$ws.Dispose()
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object {{ $_.CommandLine -like "*remote-debugging-port=9333*" }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
Start-Sleep -Milliseconds 500
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
{"Remove-Item -Recurse -Force " + prof + " -ErrorAction SilentlyContinue" if profile is None else "# profile kept for the caller"}
"""
    out = powershell(ps, timeout=180)
    crash_gate(out)
    m = re.search(r"CDP_RESULT_BEGIN\n(.*?)\nCDP_RESULT_END", out, re.S)
    if not m or not m.group(1).strip():
        raise RuntimeError("no CDP result: " + out[-3000:])
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
        arglist = ", ".join(ps_quote(a) for a in argv)
        powershell(f"""
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object {{ $_.CommandLine -like "*remote-debugging-port={self.port}*" }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
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
        # The count is read over the forward before it closes; a run already failing keeps its own exception.
        n = gpu_gate.read_port(self.port) if self.forward and a[0] is None else 0
        if self.forward:
            self.forward.kill()
        powershell(f"Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object {{ $_.CommandLine -like '*remote-debugging-port={self.port}*' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}; 'STOPPED'")
        if n != 0:
            e = gpu_gate.GpuCrashed(n)
            print(e, flush=True)
            raise e


def cdp_headers(url, seconds=20, headed=True, profile=None, args=()):
    """Second-launch shape for the X-Client-Data RED: starts stock Chrome on the
    host (on `profile`, kept across launches), enables Network on the first
    page, navigates to `url`, collects Network.requestWillBeSentExtraInfo
    headers for `seconds`, returns [{url, headers}] for every request seen."""
    prof = profile or "$env:TEMP\\camou_cdp_" + str(os.getpid())
    argv = ["--no-first-run", "--no-default-browser-check", "--remote-debugging-port=9333", "--remote-allow-origins=*", *args]
    if not headed:
        argv.insert(0, "--headless=new")
    arglist = ", ".join(ps_quote(a) for a in argv)
    ps = PS_CDP + f"""
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object {{ $_.CommandLine -like "*remote-debugging-port=9333*" }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
Start-Sleep -Seconds 2
$p = Start-Process -FilePath "{CHROME}" -ArgumentList @({arglist}, "--user-data-dir={prof}", "about:blank") -WindowStyle Hidden -PassThru
$ver = $null
for ($i = 0; $i -lt 40 -and -not $ver; $i++) {{ Start-Sleep -Milliseconds 500; try {{ $ver = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:9333/json/list -ErrorAction Stop).Content }} catch {{ }} }}
$pages = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:9333/json/list).Content | ConvertFrom-Json
$pg = $pages | Where-Object {{ $_.type -eq "page" }} | Select-Object -First 1
$ws = Cdp-Connect $pg.webSocketDebuggerUrl
Cdp-Send $ws @{{ id = 1; method = "Network.enable"; params = @{{}} }}
Cdp-Send $ws @{{ id = 2; method = "Page.navigate"; params = @{{ url = {ps_quote(url)} }} }}
$deadline = (Get-Date).AddSeconds({seconds})
$urls = @{{}}
"CDP_EVENTS_BEGIN"
while ((Get-Date) -lt $deadline) {{
  $m = Cdp-Recv $ws 3000
  if (-not $m) {{ continue }}
  if ($m -match '"method":"Network.requestWillBeSent"') {{ $o = $m | ConvertFrom-Json; $urls[$o.params.requestId] = $o.params.request.url }}
  if ($m -match '"method":"Network.requestWillBeSentExtraInfo"') {{ $o = $m | ConvertFrom-Json; $h = @{{}}; $o.params.headers.PSObject.Properties | ForEach-Object {{ $h[$_.Name.ToLower()] = $_.Value }}; @{{ url = $urls[$o.params.requestId]; headers = $h }} | ConvertTo-Json -Compress -Depth 4 }}
}}
"CDP_EVENTS_END"
{ps_gpu()}
$ws.Dispose()
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object {{ $_.CommandLine -like "*remote-debugging-port=9333*" }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
{"Start-Sleep -Milliseconds 500; Remove-Item -Recurse -Force " + prof + " -ErrorAction SilentlyContinue" if profile is None else "# profile kept for the caller"}
"""
    out = powershell(ps, timeout=seconds + 120)
    crash_gate(out)
    m = re.search(r"CDP_EVENTS_BEGIN\n(.*?)\nCDP_EVENTS_END", out, re.S)
    if not m:
        raise RuntimeError("no CDP events: " + out[-1500:])
    return [json.loads(l) for l in m.group(1).splitlines() if l.strip().startswith("{")]
