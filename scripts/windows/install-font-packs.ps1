<# Installs the Windows font packs (Features on Demand) that the profile
generator draws from (settings/fonts.json families.Windows.supplemental),
once per machine; every profile on the machine shares them. A pack that is
already installed is left alone, so the script can run again at any time.

  powershell -NoProfile -ExecutionPolicy Bypass -File install-font-packs.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File install-font-packs.ps1 -IncludeJapaneseKorean
  powershell -NoProfile -ExecutionPolicy Bypass -File install-font-packs.ps1 -Source E:\LanguagesAndOptionalFeatures

Run it from an elevated PowerShell. Without -Source the packs come from
Windows Update, which must be reachable. -Source installs offline from the
"Languages and Optional Features" ISO of the same Windows build, which saves
a download per machine.

The Japanese and Korean packs wait for -IncludeJapaneseKorean: install them
only once every Camoucrome build on the machine is -13 or later. An earlier
build renders a hidden Japanese or Korean family through the lang=ja and
lang=ko default fonts (PR #233), so a profile that hides the pack would still
show it.

Prints one line per pack. Exit 0 when every requested pack is installed,
1 when one failed, 2 when not elevated. #>
param(
  [string]$Source,
  [switch]$IncludeJapaneseKorean
)
$ErrorActionPreference = 'Stop'

$admin = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $admin.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  'not elevated: run this from an administrator PowerShell'
  exit 2
}

$packs = @(
  'Language.Fonts.Arab~~~und-ARAB~0.0.1.0',
  'Language.Fonts.Beng~~~und-BENG~0.0.1.0',
  'Language.Fonts.Hans~~~und-HANS~0.0.1.0',
  'Language.Fonts.Hant~~~und-HANT~0.0.1.0',
  'Language.Fonts.Hebr~~~und-HEBR~0.0.1.0',
  'Language.Fonts.Thai~~~und-THAI~0.0.1.0'
)
$gated = @('Language.Fonts.Jpan~~~und-JPAN~0.0.1.0', 'Language.Fonts.Kore~~~und-KORE~0.0.1.0')
if ($IncludeJapaneseKorean) {
  $packs += $gated
} else {
  foreach ($n in $gated) { "$n skipped: needs -IncludeJapaneseKorean (Camoucrome -13 or later)" }
}

$failed = 0
foreach ($n in $packs) {
  try {
    if ((Get-WindowsCapability -Online -Name $n).State -eq 'Installed') { "$n already installed"; continue }
    $add = @{ Online = $true; Name = $n }
    if ($Source) { $add.Source = $Source; $add.LimitAccess = $true }
    $r = Add-WindowsCapability @add
    if ($r.RestartNeeded) { "$n installed (restart needed)" } else { "$n installed" }
  } catch {
    "$n FAILED: $($_.Exception.Message)"
    $failed++
  }
}
if ($failed) {
  "$failed pack(s) failed. Check that Windows Update is reachable, or pass -Source with the matching ISO."
  exit 1
}
exit 0
