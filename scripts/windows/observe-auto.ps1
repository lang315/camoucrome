# Unattended facebook recon: arm 1 (logged out) and arm 3 (backed-up login), one load each,
# no input, never scheduled or repeated. Takes no build_lock; gates on the owner's Active
# session, no native build, and commit headroom (S5, 2026-10-17). Exit 0 PASS, 1 FAIL, 3 UNMEASURED.
param(
  [string]$Backup = 'D:\camou-win\observe\backup\fb-login-20261017',
  [string]$Baseline = 'D:\camou-win\observe\baseline-facebook.json',
  [double]$MinHeadroomGB = 8,
  [double]$KillBelowGB = 4,
  [int[]]$Arms = @(1, 3),
  [switch]$NoIntl,
  [string]$FromProfileOverride
)
# Continue, not Stop: PS 5.1 turns native stderr (quser with nobody logged on, the judge's
# usage error) into a terminating error under Stop, and every arm must still get its line
$ErrorActionPreference = 'Continue'
$Root = 'D:\camou-win\observe'
$Ri = Join-Path $Root 'run-interactive.ps1'
$Wait = @{ 1 = 30; 3 = 120 }
$Limit = @{ 1 = 5; 3 = 8 }

function Get-Gate {
  if (-not ((quser 2>$null) | Where-Object { $_ -match '\sActive\s' })) { return 'no active session' }
  $nb = @(Get-Process ninja, siso -ErrorAction SilentlyContinue)
  if ($nb.Count) { return "native build running ($($nb[0].ProcessName))" }
  $h = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory / 1MB, 2)
  if ($h -lt $MinHeadroomGB) { return "low-memory $h GB < $MinHeadroomGB GB" }
  return $null
}

$run = Join-Path $Root ('auto\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force $run | Out-Null
$env:PYTHONUTF8 = '1'
$worst = 0
try {
  foreach ($a in $Arms) {
    $why = Get-Gate
    if ($why) { "UNMEASURED arm$a $why"; $worst = [math]::Max($worst, 3); continue }
    $cmd = "& $Root\recon.ps1 -Site facebook -Arm $a -Wait $($Wait[$a]) -Out $run -KillBelowGB $KillBelowGB"
    if (-not $NoIntl) { $cmd += ' -Intl' }
    if ($a -eq 3) { $cmd += ' -FromProfile ' + $(if ($FromProfileOverride) { $FromProfileOverride } else { $Backup }) }
    # a recon throw escapes run-interactive's *> block unlogged, with no EXIT= line (cal2, 2026-10-17);
    # log it and set the code instead. No exit here: it would end run.ps1 before its EXIT= line
    $cmd = "try { $cmd } catch { 'ERROR: ' + (`$_ | Out-String); `$_.ScriptStackTrace; `$global:LASTEXITCODE = 1 }"
    $log = Join-Path $run "arm$a.log"
    $name = "observe-auto-arm$a"
    powershell -NoProfile -ExecutionPolicy Bypass -File $Ri -Name $name -Log $log -Command $cmd | Out-Null
    $until = (Get-Date).AddMinutes($Limit[$a])
    while ((Get-Date) -lt $until -and -not ((Test-Path $log) -and (Select-String -Path $log -Pattern '^EXIT=' -Quiet))) { Start-Sleep -Seconds 3 }
    if (-not (Select-String -Path $log -Pattern '^EXIT=' -Quiet -ErrorAction SilentlyContinue)) {
      "UNMEASURED arm$a timeout after $($Limit[$a]) min"
      Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains("$run\profile-arm$a") } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
    powershell -NoProfile -ExecutionPolicy Bypass -File $Ri -Name $name -Remove | Out-Null
    Get-Content $log -ErrorAction SilentlyContinue | Select-String 'SESSION=|CLOSED=|low-memory|report exit|ERROR:' | ForEach-Object { $_.Line }
    python (Join-Path $Root 'observe_judge.py') judge --baseline $Baseline --arm $a (Join-Path $run "arm$a") --summary-out (Join-Path $run "arm$a\summary.json")
    $worst = [math]::Max($worst, $LASTEXITCODE)
  }
} finally {
  Get-ScheduledTask -TaskName 'camou-observe-auto-*' -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false
  Remove-Item (Join-Path $run 'profile-arm*') -Recurse -Force -ErrorAction SilentlyContinue
  Get-ChildItem $run -Recurse -Filter 'cookies.db' -ErrorAction SilentlyContinue | Remove-Item -Force
}
if ($worst -eq 2) { $worst = 3 }  # the judge's usage error (no baseline) measured nothing
"RESULT $(@{0 = 'PASS'; 1 = 'FAIL'; 3 = 'UNMEASURED'}[[int]$worst]) $run"
exit $worst
