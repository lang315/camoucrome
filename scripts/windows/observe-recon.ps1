# Recon launcher for the camoucrome observer build. Headed, no CDP.
# Usage: recon.ps1 -Site facebook|instagram|threads -Arm 1|2|3|4 [-Force] [-Intl]
# Driven arms (1d 1s 3w 4a, unattended only): -Driver <python.exe> -Url <url>... [-Exe <stock chrome.exe>] [-Cpu] [-ExpectSession]
#        recon.ps1 -PostOnly -Dir <arm dir> -Profile <profile dir>
# Unattended (observe-auto.ps1): -Wait <s> -Out <run dir> [-FromProfile <dir>] [-KillBelowGB <n>]
param(
  [ValidateSet('facebook','instagram','threads')][string]$Site,
  [ValidateSet('1','2','3','4','1d','1s','3w','4a')][string]$Arm,
  [switch]$Force,
  [switch]$Intl,
  [switch]$PostOnly,
  [string]$Dir,
  [string]$Profile,
  [int]$Wait = 0,
  [string]$FromProfile,
  [string]$Out,
  [double]$KillBelowGB = 4,
  [string]$Driver,
  [string[]]$Url,
  [string]$Exe,
  [switch]$Cpu,
  [switch]$ExpectSession
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
  # the stock arm has no observe category, so no trace: skip the wait and pass '-' (Task 8's trace-less mode)
  if ($Exe -and -not (Test-Path $trace)) { $trace = '-'; $ok = $true }
  for ($i = 0; $i -lt 60 -and -not $ok; $i++) {
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
  foreach ($f in @(@('--ram', 'ram.json'), @('--channels', 'channels.json'), @('--matches', 'matches.json'))) {
    if (Test-Path (Join-Path $Dir $f[1])) { $pa += @($f[0], (Join-Path $Dir $f[1])) }
  }
  & $Py @pa | Out-File -Encoding utf8 $rep
  $script:ReportRc = $LASTEXITCODE
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
$driven = $Arm -in '1d','1s','3w','4a'
if ($driven -and (-not $Driver -or -not $Out)) { throw "arm $Arm is driven: needs -Driver and -Out (unattended only)" }
if ($driven -and -not $Url) { throw "arm $Arm needs -Url" }
$script:DriveRc = $null
# not $url: PowerShell variable names are case-insensitive and -Url is a parameter
$siteUrl = @{ facebook = 'https://www.facebook.com/'; instagram = 'https://www.instagram.com/'; threads = 'https://www.threads.com/' }[$Site]
if ($Out) {
  if (-not $Wait) { throw '-Out is for unattended runs; pass -Wait' }
  if ($Arm -in '3','3w','4a' -and -not $FromProfile) { throw "unattended arm $Arm needs -FromProfile" }
  $Dir     = Join-Path $Out "arm$Arm"
  $Profile = Join-Path $Out "profile-arm$Arm"
  if ((Test-Path $Dir) -or (Test-Path $Profile)) { throw "$Dir or $Profile exists; -Out wants a fresh run dir" }
} else {
  $Dir     = Join-Path $Root "$Site\arm$Arm"
  $Profile = Join-Path $Root "$Site\profile-arm$Arm"
}
if (-not $Out) {
if ($Arm -eq 3) {
  $Profile = Join-Path $Root "$Site\profile-arm2"
  if (-not (Test-Path $Profile)) { throw "arm 3 reuses arm 2's profile; $Profile does not exist. Run arm 2 first." }
} elseif ((Test-Path $Profile) -and -not $Force) {
  throw "$Profile already exists; use -Force to replace it (arms 1, 2, 4 want a FRESH profile)"
}
}
if ((Test-Path $Dir) -and (Get-ChildItem $Dir -Force | Select-Object -First 1) -and -not $Force) {
  throw "$Dir is not empty; use -Force to overwrite"
}
if (-not (Test-Path $Chrome)) { throw "missing $Chrome" }
New-Item -ItemType Directory -Force $Dir | Out-Null
if ($Force) { Remove-Item (Join-Path $Dir '*') -Recurse -Force -ErrorAction SilentlyContinue }
if ($Arm -ne 3 -and $Force -and (Test-Path $Profile)) { Remove-Item $Profile -Recurse -Force }
function Get-HeadroomGB { [math]::Round((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory / 1MB, 2) }
if ($FromProfile) {
  if (-not (Test-Path $FromProfile)) { throw "missing -FromProfile $FromProfile" }
  robocopy $FromProfile $Profile /E /COPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy $FromProfile failed rc=$LASTEXITCODE" }
}

$what = @{
  '1' = 'ARM 1 logged-out landing: let the page load, wait 30 s, close the browser.'
  '2' = 'ARM 2 fresh login: log in BY HAND, wait for the feed to load, close the browser.'
  '3' = "ARM 3 established session (arm 2's profile): browse the feed for about 2 minutes, close the browser."
  '4' = 'ARM 4 third-party page: type the URL of a public page that embeds the Meta Pixel or a social plugin, wait about 30 s, close the browser. NOTE THAT URL for the measurement doc.'
  '1d' = 'ARM 1d driven, logged out: landing page, wheel only.'
  '1s' = 'ARM 1s driven, stock Chrome, logged out: landing page, wheel only.'
  '3w' = 'ARM 3w driven: feed, watch, marketplace, messages, profile by URL, wheel only.'
  '4a' = 'ARM 4a driven: one third-party page with the Meta Pixel, logged-in profile copy, wheel only.'
}[$Arm]
Write-Host ''
Write-Host '=============================================================='
Write-Host "$Site  $what"
Write-Host 'Close the browser window normally - do NOT kill it, or no trace is written.'
Write-Host "Raw files stay in $Dir (host only)."
Write-Host '=============================================================='
Write-Host ''

# -Intl adds V8 entry slices and runtime call stats (needs v8_enable_runtime_call_stats = true)
$cats = '-*,disabled-by-default-camou.observe'
if ($Intl) { $cats += ',v8,disabled-by-default-v8.runtime_stats' }
if ($Cpu) { $cats += ',devtools.timeline' }
if ($Exe) {
  # stock Chrome has no observe category: netlog only
  $fl = @("--user-data-dir=$Profile", '--no-first-run', '--no-default-browser-check', "--log-net-log=$Dir\net.json")
} else {
  $fl = @(
    "--user-data-dir=$Profile", '--no-first-run', '--no-default-browser-check',
    "--trace-startup=$cats", '--trace-startup-format=json',
    "--trace-startup-file=$Dir\trace.json", '--trace-startup-duration=0',
    '--trace-startup-record-mode=record-as-much-as-possible', "--log-net-log=$Dir\net.json"
  )
}
# unattended runs log to <profile>\chrome_debug.log so a GPU process crash is countable
if ($Wait) { $fl += @('--enable-logging', '--v=0') }
if ($driven) {
  $exeUsed = if ($Exe) { $Exe } else { $Chrome }
  $args4drive = @($fl | Where-Object { $_ -notlike '--user-data-dir=*' })
  [IO.File]::WriteAllText((Join-Path $Dir 'chrome-args.json'), (ConvertTo-Json @($args4drive) -Compress))
  $da = @((Join-Path $Root 'observe_drive.py'), '--arm', $Arm, '--exe', $exeUsed, '--profile', $Profile, '--out', $Dir,
          '--chrome-args', (Join-Path $Dir 'chrome-args.json'))
  foreach ($u in $Url) { $da += @('--url', $u) }
  if ($Arm -eq '3w') { $da += @('--settle', '15', '--wheel', '60') } else { $da += @('--settle', '20', '--wheel', '40') }
  if (-not $Exe) { $da += '--fork' }
  if ($ExpectSession) { $da += '--expect-session' }
  # PS 5.1 Start-Process joins -ArgumentList with spaces and quotes nothing ('C:\Program Files\...')
  $da = $da | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }
  $drv = Start-Process -FilePath $Driver -ArgumentList $da -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Dir 'drive.out') -RedirectStandardError (Join-Path $Dir 'drive.err')
  $null = $drv.Handle   # PS 5.1 loses ExitCode of a -PassThru process unless the handle is cached
} else {
  if ($Arm -ne '4') { $fl += $siteUrl }
  Start-Process -FilePath $Chrome -ArgumentList ($fl | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } })
}

# chrome may re-launch, so wait on the command line, not the started process
function Get-Mine { Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($Profile) } }
# a driver starts python and the launcher first, so give its browser longer to appear
for ($i = 0; $i -lt $(if ($driven) { 90 } else { 30 }) -and -not (Get-Mine); $i++) { Start-Sleep -Seconds 1 }
$started = Get-Date
$hLaunch = Get-HeadroomGB; $hMin = $hLaunch; $lowKill = $false; $closed = 0
if ($Wait) {
  # wait $Wait s, polling commit headroom every 5 s (S5: WSL's VM peaks mid-build)
  while (((Get-Date) - $started).TotalSeconds -lt $Wait -and (Get-Mine)) {
    Start-Sleep -Seconds 5
    $h = Get-HeadroomGB; if ($h -lt $hMin) { $hMin = $h }
    if ($h -lt $KillBelowGB) { $lowKill = $true; break }
  }
  if ($lowKill) {
    Write-Host "low-memory: headroom $hMin GB < $KillBelowGB GB; force-stopping"
    Get-Mine | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  } else {
    foreach ($id in @(Get-Mine).ProcessId) {
      $q = Get-Process -Id $id -ErrorAction SilentlyContinue
      # a process can exit between the handle read and the close once the browser shuts down (cal2/cal3, 2026-10-17)
      if ($q -and $q.MainWindowHandle -ne 0) { try { [void]$q.CloseMainWindow(); $closed++ } catch [InvalidOperationException] { Write-Host "close: pid $id exited before close" } }
    }
  }
  for ($i = 0; $i -lt 60 -and (Get-Mine); $i++) { Start-Sleep -Seconds 1 }
  $left = @(Get-Mine).Count
  if ($left) { Get-Mine | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }
  Write-Host "CLOSED=$closed LEFT=$left"
} else {
  while (Get-Mine) { Start-Sleep -Seconds 2 }
}
Write-Host 'browser exited; post-processing'
if ($driven) {
  # the driver writes channels.json and matches.json after the browser closes
  [void]$drv.WaitForExit(60000)
  if ($drv.HasExited) { $script:DriveRc = $drv.ExitCode } else { Stop-Process -Id $drv.Id -Force -ErrorAction SilentlyContinue }
  Write-Host "drive_rc=$script:DriveRc"
}
# run-interactive wraps this script in *>, where PS 5.1 turns native stderr (a report
# traceback on a killed arm, wsl, quser) into a terminating error under Stop: run.json must still be written
if ($Wait) { $ErrorActionPreference = 'Continue' }
Invoke-Post $Dir $Profile
if ($Wait) {
  $me = (quser 2>$null) | Where-Object { $_ -match '^>' }
  $state = if ($me -match '\s(Active|Disc)\s') { $Matches[1] } else { 'unknown' }
  $dbg = Join-Path $Profile 'chrome_debug.log'
  $gpu = if (Test-Path $dbg) { @(Select-String -Path $dbg -Pattern 'GPU process exited unexpectedly').Count } else { 0 }
  # the runner's WSL owner, by directory: WSL's default user is root, and no account name goes in the public repo
  $wu = (wsl -d Ubuntu-24.04 -- bash -c 'stat -c %U /home/*/actions-runner' 2>$null | Select-Object -First 1)
  $lock = (wsl -d Ubuntu-24.04 -u $wu -- bash -lc '$HOME/actions-runner/_work/camoucrome/camoucrome/scripts/build_lock.sh status' 2>&1) -join ' '
  $run = [ordered]@{
    session = (Get-Process -Id $PID).SessionId; session_state = $state
    wait_s = $Wait; closed = $closed; left = $left; low_memory_kill = $lowKill
    headroom_launch_gb = $hLaunch; headroom_min_gb = $hMin; wsl_build = ($lock -notmatch '^\s*free')
    gpu_exit_lines = $gpu; report_rc = $script:ReportRc; drive_rc = $script:DriveRc
    started = $started.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'); ended = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
  }
  [IO.File]::WriteAllText((Join-Path $Dir 'run.json'), ($run | ConvertTo-Json))
}
