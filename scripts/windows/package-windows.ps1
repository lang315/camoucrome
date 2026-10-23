# Package the native Windows build (out\Release) into a release zip.
# Run from the tree extract; the commit is the change-set commit it was archived from.
param([string]$Tree = 'D:\camou-win\tree', [string]$Dist = 'D:\camou-win\dist', [string]$Commit)
if (-not $Commit) { $Commit = (Get-Content D:\camou-win\tree.commit -Raw).Trim() }
$env:DEPOT_TOOLS_WIN_TOOLCHAIN = '0'
$env:PATH = 'D:\camou-win\depot_tools;' + $env:PATH
Set-Location D:\camou-win\chromium\src
& D:\camou-win\python312\tools\python.exe "$Tree\scripts\package.py" D:\camou-win\chromium\src `
  --out out\Release --platform windows-x64 --dist $Dist --changeset-commit $Commit --no-fonts
"EXIT $LASTEXITCODE"
