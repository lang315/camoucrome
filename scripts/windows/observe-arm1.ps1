param([string]$Url, [string]$Dir, [string]$Profile, [int]$Wait = 30)
$ErrorActionPreference = 'Stop'
$Chrome = 'D:\camou-win\chromium\src\out\Observe\chrome.exe'
if ((Test-Path $Profile) -or ((Test-Path $Dir) -and (Get-ChildItem $Dir -Force | Select-Object -First 1))) { throw "dir or profile exists: $Dir" }
New-Item -ItemType Directory -Force $Dir | Out-Null
$fl = @("--user-data-dir=$Profile", '--no-first-run', '--no-default-browser-check',
  '--trace-startup=-*,disabled-by-default-camou.observe', '--trace-startup-format=json',
  "--trace-startup-file=$Dir\trace.json", '--trace-startup-duration=0',
  '--trace-startup-record-mode=record-as-much-as-possible', "--log-net-log=$Dir\net.json",
  '--remote-debugging-port=0', $Url)
Start-Process -FilePath $Chrome -ArgumentList $fl | Out-Null
function Get-Mine { Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($Profile) } }
$t0 = Get-Date
$dt = Join-Path $Profile 'DevToolsActivePort'
for ($i = 0; $i -lt 30 -and -not (Test-Path $dt); $i++) { Start-Sleep -Seconds 1 }
if (-not (Test-Path $dt)) { throw 'no DevToolsActivePort' }
$l = Get-Content $dt
$uri = "ws://127.0.0.1:$($l[0])$($l[1])"
$rem = $Wait - ((Get-Date) - $t0).TotalSeconds
if ($rem -gt 0) { Start-Sleep -Seconds ([int][math]::Ceiling($rem)) }
# exactly one CDP message on the browser websocket
$ws = New-Object System.Net.WebSockets.ClientWebSocket
$ws.ConnectAsync([Uri]$uri, [Threading.CancellationToken]::None).Wait()
$bytes = [Text.Encoding]::UTF8.GetBytes('{"id":1,"method":"Browser.close"}')
$ws.SendAsync([ArraySegment[byte]]$bytes, 'Text', $true, [Threading.CancellationToken]::None).Wait()
Write-Host 'sent Browser.close'
for ($i = 0; $i -lt 40 -and (Get-Mine); $i++) { Start-Sleep -Seconds 1 }
$left = @(Get-Mine).Count
Write-Host "chrome processes left: $left"
if ($left) {
  Get-Mine | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  throw 'browser hung; own-profile processes force-stopped'
}
foreach ($f in 'trace.json', 'net.json') {
  $p = Join-Path $Dir $f
  for ($i = 0; $i -lt 30 -and -not (Test-Path $p); $i++) { Start-Sleep -Seconds 1 }
  python -c "import json,sys; json.load(open(sys.argv[1],encoding='utf-8')); print('parse ok', sys.argv[1])" $p
}
