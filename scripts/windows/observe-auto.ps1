# Unattended facebook recon: arm 1 (logged out) and arm 3 (backed-up login), one load each,
# no input, never scheduled or repeated. Takes no build_lock; gates on the owner's Active
# session, no native build, and commit headroom (S5, 2026-10-17). Exit 0 PASS, 1 FAIL, 3 UNMEASURED.
# Tracking-map arms (2026-10-29): -Arms 1,3,1d,1s,3w,4a. 1d 1s 3w 4a run observe_drive.py (wheel only).
# Pass the arm list through -File (strings): in a PowerShell session 1d would parse as the decimal 1.
param(
  [string]$Backup = 'D:\camou-win\observe\backup\fb-login-20261017',
  [string]$Baseline = 'D:\camou-win\observe\baseline-facebook.json',
  [double]$MinHeadroomGB = 8,
  [double]$KillBelowGB = 4,
  [string[]]$Arms = @('1', '3'),
  [switch]$NoIntl,
  [switch]$CpuAll,
  [string]$FromProfileOverride
)
# Continue, not Stop: PS 5.1 turns native stderr (quser with nobody logged on, the judge's
# usage error) into a terminating error under Stop, and every arm must still get its line
$ErrorActionPreference = 'Continue'
$Root = 'D:\camou-win\observe'
$Ri = Join-Path $Root 'run-interactive.ps1'
$Arms = @($Arms | ForEach-Object { "$_" -split ',' } | Where-Object { $_ })
$bad = @($Arms | Where-Object { $_ -notin '1', '3', '1d', '1s', '3w', '4a' })
if ($bad.Count) { "UNMEASURED unknown arm: $($bad -join ' ')"; exit 3 }
$Wait  = @{ '1' = 30; '3' = 120; '1d' = 90; '1s' = 90; '3w' = 480; '4a' = 90 }   # 3w: 5 x (15 + 60) s + 5 loads + truth + tail, about 400 s
$Limit = @{ '1' = 5;  '3' = 8;   '1d' = 6;  '1s' = 6;  '3w' = 12;  '4a' = 6 }
$Venv  = Join-Path $Root 'venv\Scripts\python.exe'
$Stock = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$Fb    = 'https://www.facebook.com'
$Urls  = @{ '1d' = @("$Fb/"); '1s' = @("$Fb/"); '3w' = @("$Fb/", "$Fb/watch/", "$Fb/marketplace/", "$Fb/messages/", "$Fb/me/") }
$Driven   = @('1d', '1s', '3w', '4a')
$LoggedIn = @('3', '3w', '4a')
$Discovery = Join-Path $Root 'baseline-empty.json'   # contains {}

function Get-Gate {
  if (-not ((quser 2>$null) | Where-Object { $_ -match '\sActive\s' })) { return 'no active session' }
  $nb = @(Get-Process ninja, siso -ErrorAction SilentlyContinue)
  if ($nb.Count) { return "native build running ($($nb[0].ProcessName))" }
  $h = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory / 1MB, 2)
  if ($h -lt $MinHeadroomGB) { return "low-memory $h GB < $MinHeadroomGB GB" }
  return $null
}

# account-risk cap (owner ruling 6, 2026-10-29): at most 3 runs a UTC day that include a logged-in arm,
# 15 minutes apart. The run is recorded when it starts, so a run that ends UNMEASURED still counts
if (@($Arms | Where-Object { $_ -in $LoggedIn }).Count) {
  New-Item -ItemType Directory -Force (Join-Path $Root 'auto') | Out-Null
  $Ledger = Join-Path $Root 'auto\ledger.json'
  $now = (Get-Date).ToUniversalTime()
  $utc = [Globalization.DateTimeStyles]::AdjustToUniversal -bor [Globalization.DateTimeStyles]::AssumeUniversal
  $past = @(@(if (Test-Path $Ledger) { Get-Content -Raw $Ledger | ConvertFrom-Json }) | ForEach-Object { [datetime]::Parse("$_", [Globalization.CultureInfo]::InvariantCulture, $utc) })
  $today = @($past | Where-Object { $_.Date -eq $now.Date })
  if ($today.Count -ge 3) { "RESULT UNMEASURED cap: 3 logged-in runs today (UTC)"; exit 3 }
  $last = $past | Sort-Object | Select-Object -Last 1
  if ($last -and ($now - $last).TotalMinutes -lt 15) { "RESULT UNMEASURED cap: last logged-in run $([int]($now - $last).TotalMinutes) min ago (< 15)"; exit 3 }
  $all = @($past | Select-Object -Last 9 | ForEach-Object { $_.ToString('o') }) + $now.ToString('o')
  [IO.File]::WriteAllText($Ledger, (ConvertTo-Json @($all)))
}

$run = Join-Path $Root ('auto\' + (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force $run | Out-Null
$env:PYTHONUTF8 = '1'
$worst = 0
$checkpoint = $false
# the report args recon.ps1 builds, rebuilt once ram.json exists
function Get-ReportArgs([string]$d) {
  $trace = Join-Path $d 'trace.json'
  if (-not (Test-Path $trace)) { $trace = '-' }
  $pa = @((Join-Path $Root 'observe_report.py'), $trace, (Join-Path $d 'net.json'))
  if (Test-Path (Join-Path $d 'cookies.db')) { $pa += @('--cookies', (Join-Path $d 'cookies.db')) }
  foreach ($f in @(@('--ram', 'ram.json'), @('--channels', 'channels.json'), @('--matches', 'matches.json'))) {
    if (Test-Path (Join-Path $d $f[1])) { $pa += @($f[0], (Join-Path $d $f[1])) }
  }
  return $pa
}
try {
  foreach ($a in $Arms) {
    if ($checkpoint -and $a -in $LoggedIn) { "UNMEASURED arm$a skipped after checkpoint"; $worst = [math]::Max($worst, 3); continue }
    $why = Get-Gate
    if ($why) { "UNMEASURED arm$a $why"; $worst = [math]::Max($worst, 3); continue }
    $drivenArm = $a -in $Driven
    $armUrls = $Urls[$a]
    if ($a -eq '4a') {
      $f4 = Join-Path $Root 'arm4a-url.txt'
      if (-not (Test-Path $f4)) { "UNMEASURED arm4a no arm4a-url.txt"; $worst = [math]::Max($worst, 3); continue }
      $armUrls = @((Get-Content $f4 -TotalCount 1).Trim())
    }
    $armDir = Join-Path $run "arm$a"
    $existed = Test-Path $armDir
    # the arm name is quoted: PowerShell 5.1 reads an unquoted 1d as the decimal 1 (run 20261029-145829)
    $cmd = "& $Root\recon.ps1 -Site facebook -Arm '$a' -Wait $($Wait[$a]) -Out $run -KillBelowGB $KillBelowGB"
    if (-not $NoIntl) { $cmd += ' -Intl' }
    if ($a -in '3', '3w', '4a') { $cmd += ' -FromProfile ' + $(if ($FromProfileOverride) { $FromProfileOverride } else { $Backup }) }
    if ($drivenArm) {
      # no double quotes: the command is passed through a nested powershell -File call
      $cmd += " -Driver '$Venv' -Url @(" + (($armUrls | ForEach-Object { "'$_'" }) -join ',') + ')'
      if ($a -eq '1s') { $cmd += " -Exe '$Stock'" }
      if ($a -in '1d', '3w', '4a') { $cmd += ' -Cpu' }
      if ($a -in '3w', '4a') { $cmd += ' -ExpectSession' }
    } elseif ($CpuAll) { $cmd += ' -Cpu' }
    # a recon throw escapes run-interactive's *> block unlogged, with no EXIT= line (cal2, 2026-10-17);
    # log it and set the code instead. No exit here: it would end run.ps1 before its EXIT= line
    $cmd = "try { $cmd } catch { 'ERROR: ' + (`$_ | Out-String); `$_.ScriptStackTrace; `$global:LASTEXITCODE = 1 }"
    $log = Join-Path $run "arm$a.log"
    $name = "observe-auto-arm$a"
    powershell -NoProfile -ExecutionPolicy Bypass -File $Ri -Name $name -Log $log -Command $cmd | Out-Null
    $until = (Get-Date).AddMinutes($Limit[$a])
    # driven arms: private memory per process type every second turn (6 s); ram.json states the real interval
    $samples = New-Object System.Collections.ArrayList; $t0 = Get-Date; $tick = 0
    while ((Get-Date) -lt $until -and -not ((Test-Path $log) -and (Select-String -Path $log -Pattern '^EXIT=' -Quiet))) {
      Start-Sleep -Seconds 3; $tick++
      if ($drivenArm -and $tick % 2 -eq 0) {
        $by = @{}
        Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains("$run\profile-arm$a") } | ForEach-Object {
          $ty = if ($_.CommandLine -match '--type=(\S+)') { $Matches[1] } else { 'browser' }
          $by[$ty] = [int64]$by[$ty] + [int64]$_.PrivatePageCount
        }
        if ($by.Count) { [void]$samples.Add([ordered]@{ t = [int]((Get-Date) - $t0).TotalSeconds; by_type = $by }) }
      }
    }
    if ($drivenArm -and -not $existed -and (Test-Path $armDir)) {
      [IO.File]::WriteAllText((Join-Path $run "arm$a\ram.json"), (ConvertTo-Json -Depth 4 ([ordered]@{ interval_s = 6; samples = @($samples) })))
    }
    $timedOut = -not (Select-String -Path $log -Pattern '^EXIT=' -Quiet -ErrorAction SilentlyContinue)
    if ($timedOut) {
      "UNMEASURED arm$a timeout after $($Limit[$a]) min"
      $worst = [math]::Max($worst, 3)
      # -Remove (Unregister) leaves a running instance alive (host, 2026-10-17): stop recon before its late cookie copy
      Stop-ScheduledTask -TaskName "camou-$name" -ErrorAction SilentlyContinue
      Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains("$run\profile-arm$a") } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
    powershell -NoProfile -ExecutionPolicy Bypass -File $Ri -Name $name -Remove | Out-Null
    Get-Content $log -ErrorAction SilentlyContinue | Select-String 'SESSION=|CLOSED=|low-memory|report exit|ERROR:|drive_rc=' | ForEach-Object { $_.Line }
    if ($timedOut) { continue }
    # a recon that threw, or one that never made this arm's dir, measured nothing: judging a dir that
    # another arm made would print that arm's verdict under this arm's name
    $errored = (Test-Path $log) -and (Select-String -Path $log -Pattern '^ERROR:' -Quiet)
    if ($errored -or $existed -or -not (Test-Path $armDir)) {
      "UNMEASURED arm$a recon error"; $worst = [math]::Max($worst, 3); continue
    }
    # a python that fails to launch leaves the -Remove call's 0 in LASTEXITCODE; global, or a script-scope copy shadows it
    $global:LASTEXITCODE = 3
    if ($drivenArm) {
      # recon wrote report.md before ram.json existed: write it again with the RAM section
      $pa = Get-ReportArgs (Join-Path $run "arm$a")
      python @pa | Out-File -Encoding utf8 (Join-Path $run "arm$a\report.md")
      $dj = Get-Content -Raw (Join-Path $run "arm$a\run.json") -ErrorAction SilentlyContinue | ConvertFrom-Json
      $drc = if ($dj) { $dj.drive_rc } else { $null }
      $hasCh = Test-Path (Join-Path $run "arm$a\channels.json")
      if ($a -eq '1s') {
        if ($drc -eq 0 -and $hasCh) { "INFO arm1s measured (stock: no observer trace, no judge)" }
        else { "UNMEASURED arm1s drive_rc=$drc"; $worst = [math]::Max($worst, 3) }
        continue
      }
      if ($drc -eq 4) { "UNMEASURED arm$a checkpoint"; $worst = [math]::Max($worst, 3); $checkpoint = $true; continue }
      if (-not $hasCh) { "UNMEASURED arm$a no channels.json"; $worst = [math]::Max($worst, 3); continue }
      $judgeBase = $Discovery; $judgeArm = if ($a -eq '1d') { '1' } else { '3' }
    } else { $judgeBase = $Baseline; $judgeArm = $a }
    python (Join-Path $Root 'observe_judge.py') judge --baseline $judgeBase --arm $judgeArm (Join-Path $run "arm$a") --summary-out (Join-Path $run "arm$a\summary.json")
    $rc = $LASTEXITCODE; if ($rc -notin 0, 1, 2, 3) { $rc = 3 }  # a crash code is no verdict
    $worst = [math]::Max($worst, $rc)
  }
} finally {
  Get-ScheduledTask -TaskName 'camou-observe-auto-*' -ErrorAction SilentlyContinue |
    ForEach-Object { $_ | Stop-ScheduledTask; $_ | Unregister-ScheduledTask -Confirm:$false }
  Remove-Item (Join-Path $run 'profile-arm*') -Recurse -Force -ErrorAction SilentlyContinue
  Get-ChildItem $run -Recurse -Filter 'cookies.db' -ErrorAction SilentlyContinue | Remove-Item -Force
  # the driver's raw captures (bodies, WebSocket payloads, truth) and the saved document HTML stay only until the report is done;
  # resources\js (public Meta code) and truth.json stay on the host
  @(Get-ChildItem $run -Directory -Recurse -Filter 'capture' -ErrorAction SilentlyContinue) | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  @(Get-ChildItem $run -Recurse -Directory -Filter 'html' -ErrorAction SilentlyContinue | Where-Object { $_.Parent.Name -eq 'resources' }) | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
if ($worst -eq 2) { $worst = 3 }  # the judge's usage error (no baseline) measured nothing
"RESULT $(@{0 = 'PASS'; 1 = 'FAIL'; 3 = 'UNMEASURED'}[[int]$worst]) $run"
exit $worst
