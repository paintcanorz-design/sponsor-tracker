# Build PyInstaller onedir and zip for manual upload to GitHub Release.
# Usage: .\scripts\build_windows_zip.ps1
# Requires: pip install -r requirements.txt -r requirements-build.txt
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$verLine = Select-String -Path (Join-Path $root "src\version.py") -Pattern 'APP_VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
$ver = if ($verLine) { $verLine.Matches.Groups[1].Value } else { "0.0.0" }
Write-Host "APP_VERSION from src/version.py: $ver"

$distDir = Join-Path $root "dist\贊助額追蹤"
python -m PyInstaller sponsor_tracker.spec
if (-not (Test-Path -LiteralPath (Join-Path $distDir "贊助額追蹤.exe"))) {
    throw "Missing $distDir\贊助額追蹤.exe"
}
python pack_release_zip.py
$zipPath = Join-Path $root "release\SponsorTracker-Windows-v$ver.zip"
if (-not (Test-Path -LiteralPath $zipPath)) {
    throw "Missing $zipPath"
}
Write-Host "Created: $zipPath"
Get-Item -LiteralPath $zipPath | Format-List FullName, Length
