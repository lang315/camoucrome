<# Runs a command in the owner's interactive session through a temporary
scheduled task (S4, 2026-10-12: in session 0, where sshd/sshgate put a
shell, the GPU process crashes once per launch). The owner must be logged
on (RDP connected or disconnected); headed windows show on that desktop.

  powershell -NoProfile -ExecutionPolicy Bypass -File run-interactive.ps1 -Name step2b -Log D:\x.log -Command '<PowerShell>'
  powershell -NoProfile -ExecutionPolicy Bypass -File run-interactive.ps1 -Name step2b -Remove

The command runs after set-env.ps1; the log gets SESSION=<id> first and
EXIT=<rc> last. Poll the log, then -Remove. #>
param(
  [Parameter(Mandatory = $true)][string]$Name,
  [string]$Command,
  [string]$Log,
  [string]$EnvScript = 'D:\camou-win\set-env.ps1',
  [switch]$Remove
)
$task = "camou-$Name"
if ($Remove) {
  Unregister-ScheduledTask -TaskName $task -Confirm:$false
  "removed $task"
  return
}
if (-not $Command -or -not $Log) { throw '-Command and -Log are required' }
$dir = Join-Path $env:TEMP $task
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$body = Join-Path $dir 'run.ps1'
$text = @(
  '& {',
  "Invoke-Expression (Get-Content -Raw '$EnvScript')",
  '"SESSION=" + (Get-Process -Id $PID).SessionId',
  $Command,
  '"EXIT=" + $LASTEXITCODE',
  "} *> '$Log'"
) -join "`n"
[IO.File]::WriteAllText($body, $text, (New-Object Text.UTF8Encoding $true))
$a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File $body"
$p = New-ScheduledTaskPrincipal -UserId (whoami) -LogonType Interactive
$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 6)
Register-ScheduledTask -TaskName $task -Action $a -Principal $p -Settings $s -Force | Out-Null
Start-ScheduledTask -TaskName $task
"started $task log=$Log"
