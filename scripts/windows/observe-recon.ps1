# Recon launcher for the camoucrome observer build. Owner-driven, headed, no CDP.
# Usage: recon.ps1 -Site facebook|instagram|threads -Arm 1|2|3|4 [-Force]
#        recon.ps1 -PostOnly -Dir <arm dir> -Profile <profile dir>
param(
  [ValidateSet('facebook','instagram','threads')][string]$Site,
  [ValidateSet(1,2,3,4)][int]$Arm,
  [switch]$Force,
  [switch]$PostOnly,
  [string]$Dir,
  [string]$Profile
)
$ErrorActionPreference = 'Stop'
$Root   = 'D:\camou-win\observe'
$Chrome = 'D:\camou-win\chromium\src\out\Observe\chrome.exe'
$Py     = 'python'
$ReportPy = Join-Path $Root 'observe_report.py'

function Invoke-Post([string]$Dir, [string]$Profile) {
  # trace must exist and parse (the browser writes it at shutdown)
  $trace = Join-Path $Dir 'trace.json'
  $ok = $false
  for ($i = 0; $i -lt 60; $i++) {
    if (Test-Path $trace) {
      & $Py -c "import json,sys; json.load(open(sys.argv[1], encoding='utf-8'))" $trace 2>$null
      if ($LASTEXITCODE -eq 0) { $ok = $true; break }
    }
    Start-Sleep -Seconds 1
  }
  if (-not $ok) { Write-Warning 'trace.json missing or not valid JSON after 60 s (browser killed?)' }

  $ck = Join-Path $Profile 'Default\Network\Cookies'
  if (-not (Test-Path $ck)) { $ck = Join-Path $Profile 'Default\Cookies' }
  $cookiesDb = Join-Path $Dir 'cookies.db'
  if (Test-Path $ck) { Copy-Item $ck $cookiesDb -Force } else { Write-Warning "no Cookies file under $Profile" }

  $net = Join-Path $Dir 'net.json'
  $rep = Join-Path $Dir 'report.md'
  $pa = @($ReportPy, $trace, $net)
  if (Test-Path $cookiesDb) { $pa += @('--cookies', $cookiesDb) }
  & $Py @pa | Out-File -Encoding utf8 $rep
  Write-Host "report exit=$LASTEXITCODE -> $rep"
  Get-Content $rep -TotalCount 40

  # request count from the netlog: URL_REQUEST_START_JOB events, with and without /ajax/bz
  $cnt = Join-Path $Root 'count_requests.py'
  Set-Content -Encoding ascii $cnt @'
import json, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
t = d['constants']['logEventTypes']['URL_REQUEST_START_JOB']
b = d['constants']['logEventPhase']['PHASE_BEGIN']
urls = [e['params']['url'] for e in d['events'] if e.get('type') == t and e.get('phase') == b]
print('total requests:', len(urls))
print('/ajax/bz requests:', sum('/ajax/bz' in u.split('?')[0] for u in urls))
'@
  & $Py $cnt $net
}

if ($PostOnly) {
  if (-not $Dir -or -not $Profile) { throw '-PostOnly needs -Dir and -Profile' }
  Invoke-Post $Dir $Profile
  return
}

if (-not $Site -or -not $Arm) { throw '-Site and -Arm are required' }
$url = @{ facebook = 'https://www.facebook.com/'; instagram = 'https://www.instagram.com/'; threads = 'https://www.threads.com/' }[$Site]
$Dir     = Join-Path $Root "$Site\arm$Arm"
$Profile = Join-Path $Root "$Site\profile-arm$Arm"
if ($Arm -eq 3) {
  $Profile = Join-Path $Root "$Site\profile-arm2"
  if (-not (Test-Path $Profile)) { throw "arm 3 reuses arm 2's profile; $Profile does not exist. Run arm 2 first." }
} elseif ((Test-Path $Profile) -and -not $Force) {
  throw "$Profile already exists; use -Force to replace it (arms 1, 2, 4 want a FRESH profile)"
}
if ((Test-Path $Dir) -and (Get-ChildItem $Dir -Force | Select-Object -First 1) -and -not $Force) {
  throw "$Dir is not empty; use -Force to overwrite"
}
if (-not (Test-Path $Chrome)) { throw "missing $Chrome" }
New-Item -ItemType Directory -Force $Dir | Out-Null
if ($Force) { Remove-Item (Join-Path $Dir '*') -Recurse -Force -ErrorAction SilentlyContinue }
if ($Arm -ne 3 -and $Force -and (Test-Path $Profile)) { Remove-Item $Profile -Recurse -Force }

$what = @{
  1 = 'ARM 1 logged-out landing: let the page load, wait 30 s, close the browser.'
  2 = 'ARM 2 fresh login: log in BY HAND, wait for the feed to load, close the browser.'
  3 = "ARM 3 established session (arm 2's profile): browse the feed for about 2 minutes, close the browser."
  4 = 'ARM 4 third-party page: type the URL of a public page that embeds the Meta Pixel or a social plugin, wait about 30 s, close the browser. NOTE THAT URL for the measurement doc.'
}[$Arm]
Write-Host ''
Write-Host '=============================================================='
Write-Host "$Site  $what"
Write-Host 'Close the browser window normally - do NOT kill it, or no trace is written.'
Write-Host "Raw files stay in $Dir (host only)."
Write-Host '=============================================================='
Write-Host ''

$fl = @(
  "--user-data-dir=$Profile", '--no-first-run', '--no-default-browser-check',
  '--trace-startup=-*,disabled-by-default-camou.observe', '--trace-startup-format=json',
  "--trace-startup-file=$Dir\trace.json", '--trace-startup-duration=0',
  '--trace-startup-record-mode=record-as-much-as-possible', "--log-net-log=$Dir\net.json"
)
if ($Arm -ne 4) { $fl += $url }
Start-Process -FilePath $Chrome -ArgumentList ($fl | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } })

# chrome may re-launch, so wait on the command line, not the started process
function Get-Mine { Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($Profile) } }
for ($i = 0; $i -lt 30 -and -not (Get-Mine); $i++) { Start-Sleep -Seconds 1 }
while (Get-Mine) { Start-Sleep -Seconds 2 }
Write-Host 'browser exited; post-processing'
Invoke-Post $Dir $Profile
