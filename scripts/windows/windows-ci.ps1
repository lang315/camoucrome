# On-demand Windows CI (spec 2026-10-28-windows-ci-design). Copy byte-equal to D:\camou-win\ci\windows-ci.ps1,
# with windows_ci_summary.py beside it. Never scheduled, never looped, no retry, loads no site.
# Exit 0 PASS or SKIPPED, 1 FAIL, 2 UNMEASURED; the last stdout line is `RESULT <verdict> <run id>`.
#
# Host config OutRoot\host.config.ps1 (never committed) sets, as plain assignments:
#   $WslUser    = '<wsl-user>'
#   $LockScript = '<absolute WSL path of the runner clone>/scripts/build_lock.sh'
#   $RepoClone  = '<absolute WSL path of the runner clone>'
param(
  [string]$Commit = 'origin/main',
  [switch]$Observe,
  [switch]$DryRun,
  [switch]$Force,
  [string]$ForceReason,
  [string]$OutRoot = 'D:\camou-win\ci',
  [int]$DryStubSteps = 5,
  [string]$DryVerifyJson
)
if ($Force -and -not $ForceReason) { throw '-Force needs -ForceReason' }
if ($DryRun -and -not $env:CAMOU_BUILD_LOCK) { throw '-DryRun needs CAMOU_BUILD_LOCK (a test lock path inside WSL); the real lock is never used in a dry run' }
if ($DryRun -and -not $DryVerifyJson) { throw '-DryRun needs -DryVerifyJson' }
$ErrorActionPreference = 'Continue'
$HostConfig = Join-Path $OutRoot 'host.config.ps1'
if (-not (Test-Path $HostConfig)) { throw "missing host config $HostConfig (WslUser, LockScript, RepoClone)" }
. $HostConfig

$Src = 'D:\camou-win\chromium\src'
$Tree = Join-Path $OutRoot 'tree'
$GitBash = 'C:\Program Files\Git\bin\bash.exe'
$Ri = 'D:\camou-win\observe\run-interactive.ps1'
$OutDir = if ($Observe) { 'out\Observe' } else { 'out\Release' }
$env:DEPOT_TOOLS_WIN_TOOLCHAIN = '0'
$env:DEPOT_TOOLS_UPDATE = '0'
$env:vs2022_install = 'C:\Program Files\Microsoft Visual Studio\2022\Community'
$env:PATH = 'D:\camou-win\depot_tools;C:\Program Files\Git\usr\bin;' + $env:PATH
$env:PYTHONUTF8 = '1'

function Get-Stamp { (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') }
function Get-RunId { (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') }
function Invoke-Wsl([string]$cmd) { cmd /c "wsl -d Ubuntu-24.04 -u $WslUser -- $cmd 2>&1" }

# One verb on the shared lock, owner windows-ci. No waiting: the caller reads the exit code.
function Invoke-Lock([string]$verb) {
  $envPart = if ($DryRun) { "env CAMOU_BUILD_LOCK=$env:CAMOU_BUILD_LOCK " } else { '' }
  $out = cmd /c "wsl -d Ubuntu-24.04 -u $WslUser -- ${envPart}bash $LockScript $verb windows-ci 2>&1"
  [pscustomobject]@{ Rc = $LASTEXITCODE; Out = (($out | Out-String).Trim()) }
}

function Get-Headroom { [math]::Round((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory / 1MB, 2) }
function Test-Session { [bool]((quser 2>$null) | Where-Object { $_ -match '\sActive\s' }) }

# Never bypassed by -DryRun. Reset --hard destroys the applied state the recon builds use.
function Get-ObserveInUse {
  $p = Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match 'observe-auto|observe-recon|recon\.ps1' } | Select-Object -First 1
  if ($p) { return "process $($p.Name) ($($p.ProcessId))" }
  $t = Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { ($_.TaskName -like 'camou-*' -and $_.TaskName -notlike 'camou-windows-ci-*') -or $_.TaskName -like '*observe*' } | Select-Object -First 1
  if ($t) { return "scheduled task $($t.TaskName)" }
  return $null
}

function Invoke-Step([string]$what, [scriptblock]$body) {
  & $body
  if ($LASTEXITCODE -ne 0) { throw "$what exit $LASTEXITCODE" }
}

function ConvertTo-Unix([string]$p) { '/' + $p.Substring(0, 1).ToLower() + ($p.Substring(2) -replace '\\', '/') }

# a run's verify output -> the record's per-script entries (lines of windows_verify_set.py)
function Read-Verify([string]$log, [string]$mode) {
  $ents = @()
  foreach ($l in (Get-Content $log -ErrorAction SilentlyContinue)) {
    if ($l -notmatch '^(OK  |BAD ) (\S+\.py): (.*)$') { continue }
    $ok = $Matches[1] -eq 'OK  '; $script = $Matches[2]; $why = $Matches[3]
    if ($mode -eq 'red') { $ents += [pscustomobject]@{ script = $script; rows = 0; red_seen = $ok }; continue }
    $e = [ordered]@{ script = $script; rows = 0; expected = 0; fails = 0; not_measured = 0; gpu_crashes = 0 }
    if ($why -match '^UNMEASURED') { $e.gpu_crashes = 1 }
    elseif ($why -match 'ALL_PASS') { $e.rows = [int]$ok; $e.expected = 1; $e.fails = [int](-not $ok) }
    elseif ($why -match '(\d+) PASS (\d+) FAIL') {
      $e.rows = [int]$Matches[1]; $e.fails = [int]$Matches[2]
      if ($why -match '(\d+) NOT MEASURED') { $e.not_measured = [int]$Matches[1] }
      $e.expected = if ($why -match 'want (\d+) PASS') { [int]$Matches[1] } else { $e.rows }
      if (-not $ok -and $e.fails -eq 0 -and $e.not_measured -eq 0) { $e.fails = 1 }
      # a may-skip row is allowed to print NOT MEASURED
      if ($ok) { $e.allowed_not_measured = $e.not_measured; $e.rows += $e.not_measured }
    } else { $e.fails = 1 }
    $ents += [pscustomobject]$e
  }
  , $ents
}

# ---- 1. PAUSE flag: no side effects ----
$runId = Get-RunId
if (Test-Path (Join-Path $OutRoot 'PAUSE')) {
  "SKIPPED paused by $(Join-Path $OutRoot 'PAUSE')"
  $rc = 0
  Write-Output "RESULT SKIPPED $runId"
  exit $rc
}

# ---- housekeeping: the newest 14 run directories stay ----
Get-ChildItem $OutRoot -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^\d{8}T\d{6}Z$' } |
  Sort-Object Name -Descending | Select-Object -Skip 14 | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
$run = Join-Path $OutRoot $runId
New-Item -ItemType Directory -Force $run | Out-Null

$rec = [ordered]@{
  commit = $Commit; tested_commit = 'none'; lock = 'not taken'
  preconditions = [ordered]@{ session_active = $true; commit_headroom_gb = 0; native_build_running = $false }
  build = [ordered]@{ steps = 0; seconds = 0; exit = 0; timed_out = $false }
  verify = [ordered]@{ red = @(); green = @() }
  stock_version = 'unknown'; started_utc = (Get-Stamp); ended_utc = ''
}
$lockTaken = $false
$thrown = $null

# ---- 2. preconditions ----
$rec.preconditions.session_active = Test-Session
$rec.preconditions.commit_headroom_gb = Get-Headroom
$rec.preconditions.native_build_running = [bool](Get-Process ninja, siso -ErrorAction SilentlyContinue)
$inUse = Get-ObserveInUse
if ($inUse) {
  $rec.observe_in_use = $inUse
  if ($Force) { "FORCED observe in use: $inUse (reason: $ForceReason)" }
}
if ($Force) { $rec.forced = $ForceReason; "FORCED: $ForceReason" }

# ---- 3. change set vs the last tested commit ----
$sha = (Invoke-Wsl "git -C $RepoClone rev-parse $Commit" | Select-Object -Last 1).Trim()
if ($sha -notmatch '^[0-9a-f]{40}$') { throw "cannot resolve $Commit in the runner clone: $sha" }
$rec.commit = $sha
$stamp = Join-Path $OutRoot 'tested.commit'
if (Test-Path $stamp) { $rec.tested_commit = (Get-Content $stamp -Raw).Trim() }
if ($rec.tested_commit -ne 'none' -and $rec.tested_commit -ne $sha) {
  Invoke-Wsl "git -C $RepoClone diff --quiet $($rec.tested_commit) $sha -- patches additions settings" | Out-Null
  if ($LASTEXITCODE -eq 0) { $rec.tested_commit = $sha }  # same change set: the module reads it as nothing changed
}

$pre = $rec.preconditions
$skip = ($inUse -and -not $Force) -or ($rec.commit -eq $rec.tested_commit -and -not $Force) -or
  -not $pre.session_active -or $pre.commit_headroom_gb -lt 8 -or $pre.native_build_running

# ---- 4. lock, then the work ----
if (-not $skip) {
  $got = Invoke-Lock 'acquire'
  if ($got.Rc -ne 0) {
    $rec.lock = 'held:' + ($got.Out -replace '^refused: (the build lock is held by )?', '')
    "SKIPPED lock: $($got.Out)"
  } else {
    $lockTaken = $true; $rec.lock = 'taken'; $got.Out
  }
}
if ($lockTaken) {
  try {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $buildLog = Join-Path $run 'build.log'
    if ($DryRun) {
      "stub build: $DryStubSteps steps" | Set-Content $buildLog
      $rec.build.steps = $DryStubSteps
      $v = Get-Content $DryVerifyJson -Raw | ConvertFrom-Json
      if ($v.stock_version) { $rec.stock_version = $v.stock_version }
      $rec.verify.red = @($v.red); $rec.verify.green = @($v.green)
    } else {
      # the proven re-point sequence: extract the target commit, pristine pin, apply.sh, gn gen, build
      Remove-Item $Tree -Recurse -Force -ErrorAction SilentlyContinue
      New-Item -ItemType Directory -Force $Tree | Out-Null
      $tar = Join-Path $run 'tree.tar'
      cmd /c "wsl -d Ubuntu-24.04 -u $WslUser -- git -C $RepoClone archive --format=tar $sha > `"$tar`""
      Invoke-Step 'archive' { }
      Invoke-Step 'untar' { tar -xf $tar -C $Tree }
      Remove-Item $tar -Force
      $pin = ((Get-Content (Join-Path $Tree 'upstream.env')) | Where-Object { $_ -match '^CHROMIUM_REV=' }) -replace '^CHROMIUM_REV=', ''
      Set-Location $Src
      Invoke-Step 'reset' { git reset --hard }
      Invoke-Step 'checkout pin' { git checkout -f --detach $pin }
      Invoke-Step 'clean' { git clean -fdq components/camoucfg }
      if ((git rev-parse HEAD).Trim() -ne $pin) { throw 'HEAD is not the pin' }
      if (@(git status --porcelain).Count -ne 0) { throw 'tree is not pristine' }
      Invoke-Step 'apply.sh' { & $GitBash -lc "cd '$(ConvertTo-Unix $Tree)' && bash scripts/apply.sh '$(ConvertTo-Unix $Src)'" }
      Invoke-Step 'gn gen' { gn gen $OutDir }
      $p = Start-Process cmd -ArgumentList "/c autoninja -j 8 -C $OutDir chrome > `"$buildLog`" 2>&1" -PassThru -NoNewWindow -WorkingDirectory $Src
      if (-not $p.WaitForExit(4 * 3600 * 1000)) {
        $rec.build.timed_out = $true
        taskkill /T /F /PID $p.Id | Out-Null
      }
      $rec.build.exit = if ($rec.build.timed_out) { 1 } else { $p.ExitCode }
      $last = Select-String -Path $buildLog -Pattern '\[(\d+)/\d+\]' | Select-Object -Last 1
      if ($last) { $rec.build.steps = [int]$last.Matches[0].Groups[1].Value }
      $rec.build.seconds = [int]$sw.Elapsed.TotalSeconds
      if ($rec.build.exit -eq 0) {
        $tests = Join-Path $Tree 'scripts'
        foreach ($mode in 'red', 'green') {
          $log = Join-Path $run "verify-$mode.log"
          $outEnv = if ($mode -eq 'green') { "`$env:CAMOU_OUT='$Src\$OutDir'; " } else { '' }
          $cmd = "Set-Location '$tests'; `$env:CAMOU_CLIENT='$Tree'; ${outEnv}python windows_verify_set.py $mode"
          $name = "windows-ci-$mode"
          powershell -NoProfile -ExecutionPolicy Bypass -File $Ri -Name $name -Log $log -Command $cmd | Out-Null
          $until = (Get-Date).ToUniversalTime().AddMinutes(90)
          while ((Get-Date).ToUniversalTime() -lt $until -and -not ((Test-Path $log) -and (Select-String -Path $log -Pattern '^EXIT=' -Quiet))) { Start-Sleep -Seconds 5 }
          if (-not (Select-String -Path $log -Pattern '^EXIT=' -Quiet -ErrorAction SilentlyContinue)) { Stop-ScheduledTask -TaskName "camou-$name" -ErrorAction SilentlyContinue; throw "verify $mode timed out" }
          powershell -NoProfile -ExecutionPolicy Bypass -File $Ri -Name $name -Remove | Out-Null
          $rec.verify[$mode] = Read-Verify $log $mode
          $sv = Select-String -Path $log -Pattern 'stock=(\S+)' | Select-Object -First 1
          if ($sv) { $rec.stock_version = $sv.Matches[0].Groups[1].Value }
          if ($mode -eq 'red' -and @($rec.verify.red | Where-Object { -not $_.red_seen }).Count) { break }
        }
      }
    }
    if (-not (Test-Session)) { $rec.session_lost = $true }
    if ((Get-Headroom) -lt 8) { $rec.headroom_lost = $true }
  } catch {
    $thrown = $_ | Out-String
    $rec.build.exit = 1
    "ERROR: $thrown"
  } finally {
    Get-ScheduledTask -TaskName 'camou-windows-ci-*' -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue
    $rel = Invoke-Lock 'release'
    if ($rel.Rc -eq 0) { "lock released: $($rel.Out)" } else { "lock NOT released: $($rel.Out)" }
  }
}

# ---- 5. record, summary, verdict ----
$rec.ended_utc = Get-Stamp
$prevFile = Join-Path $OutRoot 'stock.version'
if (Test-Path $prevFile) { $rec.previous_stock_version = (Get-Content $prevFile -Raw).Trim() }
if ($rec.stock_version -ne 'unknown') { $rec.stock_version | Set-Content $prevFile }
$recFile = Join-Path $run 'record.json'
$rec | ConvertTo-Json -Depth 8 | Set-Content $recFile -Encoding UTF8
$res = (python (Join-Path $PSScriptRoot 'windows_ci_summary.py') --record $recFile --out (Join-Path $run 'summary.md') | Select-Object -Last 1)
$rc = $LASTEXITCODE
$verdict = ($res -split ' ')[1]
if ($verdict -eq 'PASS' -or $verdict -eq 'FAIL') { $rec.commit | Set-Content $stamp }
Write-Output $res
exit $rc
