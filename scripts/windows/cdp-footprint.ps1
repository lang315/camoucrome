# Host entry for the CDP-footprint harness: checks the proxy setting, runs the orchestrator, prints RC=<n> last.
# Run it through run-interactive.ps1 (owner session). Exit 0 PASS, 1 FAIL, 3 UNMEASURED (orchestrator codes pass through).
# -ProxyEnableOverride is a test switch: when given, it is used instead of the registry value.
param(
  [Parameter(Mandatory = $true)][string]$Out,
  [string]$Groups = 'L,D,F',
  [string]$Arms = '',
  [int]$ProxyEnableOverride = -1
)
# Continue, not Stop: PS 5.1 turns native stderr into a terminating error under Stop
$ErrorActionPreference = 'Continue'
$Py = 'D:\camou-win\observe\venv\Scripts\python.exe'
$Dir = 'D:\camou-win\cdpfp'
$Exe = 'D:\camou-win\chromium157\src\out\Observe\chrome.exe'

if ($ProxyEnableOverride -ge 0) {
  $proxy = $ProxyEnableOverride
} else {
  $proxy = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyEnable -ErrorAction SilentlyContinue).ProxyEnable
  if ($null -eq $proxy) { $proxy = 0 }
}
if ($proxy -ne 0) {
  'UNMEASURED proxy enabled'
  'RC=3'
  exit 3
}

if (-not (Test-Path $Py)) {
  'UNMEASURED python missing'
  'RC=3'
  exit 3
}

$argv = @((Join-Path $Dir 'measure_cdp_footprint.py'), '--exe', $Exe, '--drivers', $Dir, '--out', $Out, '--groups', $Groups)
if ($Arms) { $argv += @('--arms', $Arms) }
& $Py @argv
$rc = $LASTEXITCODE
# a python that never launched leaves $LASTEXITCODE null: that measured nothing
if ($null -eq $rc) { $rc = 3 }
"RC=$rc"
exit $rc
