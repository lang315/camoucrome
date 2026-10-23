# Package the native Windows build (out\Release) into a release zip.
# Launch with: powershell.exe -NoProfile -ExecutionPolicy Bypass -File package-windows.ps1
# Run from the tree extract; the commit is the change-set commit it was archived from
# (tree.commit sits beside the tree directory).
param([string]$Tree = 'D:\camou-win\tree', [string]$Dist = 'D:\camou-win\dist', [string]$Commit)
if (-not $Commit) { $Commit = (Get-Content (Join-Path (Split-Path $Tree -Parent) 'tree.commit') -Raw).Trim() }
$env:DEPOT_TOOLS_WIN_TOOLCHAIN = '0'
$env:PATH = 'D:\camou-win\depot_tools;' + $env:PATH
Set-Location D:\camou-win\chromium\src
& D:\camou-win\python312\tools\python.exe "$Tree\scripts\package.py" D:\camou-win\chromium\src `
  --out out\Release --platform windows-x64 --dist $Dist --changeset-commit $Commit --no-fonts
"EXIT $LASTEXITCODE"
exit $LASTEXITCODE
