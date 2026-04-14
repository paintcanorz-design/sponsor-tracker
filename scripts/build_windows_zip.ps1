# Build PyInstaller onedir and zip for manual upload to GitHub Release.
# Usage: .\scripts\build_windows_zip.ps1
# Requires: pip install -r requirements.txt -r requirements-build.txt
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$verLine = Select-String -Path (Join-Path $root "src\version.py") -Pattern 'APP_VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
$ver = if ($verLine) { $verLine.Matches.Groups[1].Value } else { "0.0.0" }
Write-Host "APP_VERSION from src/version.py: $ver"

python -m PyInstaller sponsor_tracker.spec
$exe = Join-Path $root "dist\SponsorTracker\SponsorTracker.exe"
if (-not (Test-Path $exe)) {
    throw "Missing $exe"
}
$zipName = "SponsorTracker-Windows-v$ver.zip"
$zipPath = Join-Path $root "dist\$zipName"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path (Join-Path $root "dist\SponsorTracker") -DestinationPath $zipPath
Write-Host "Created: $zipPath"
Get-Item $zipPath | Format-List FullName, Length
