#Requires -Version 5.1
<#
.SYNOPSIS
  你只需先登入 GitHub CLI，其餘由腳本完成（建立公開倉庫、推送、寫入 GITHUB_REPO）。

.DESCRIPTION
  1. 安裝 GitHub CLI：https://cli.github.com/
  2. 在終端機執行：gh auth login（瀏覽器或權杖登入皆可）
  3. 在本專案根目錄右鍵「使用 PowerShell 執行」本腳本，或：
     powershell -ExecutionPolicy Bypass -File ".\推送到GitHub.ps1"

.PARAMETER RepoName
  GitHub 上的倉庫名稱（僅英數與連字號較保險），預設 sponsor-tracker
#>
param(
    [string]$RepoName = "sponsor-tracker"
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Write-Info($msg) { Write-Host $msg -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host $msg -ForegroundColor Green }

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Error "找不到 gh。請安裝 GitHub CLI：https://cli.github.com/"
    exit 1
}

gh auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "請先登入 GitHub，在終端機執行：" -ForegroundColor Yellow
    Write-Host "  gh auth login" -ForegroundColor White
    Write-Host ""
    Write-Host "登入成功後，再執行本腳本一次即可。" -ForegroundColor Yellow
    exit 1
}

$login = (gh api user --jq .login 2>$null).Trim()
if (-not $login) {
    Write-Error "無法取得 GitHub 帳號，請確認 gh auth login 已完成。"
    exit 1
}

Write-Info "GitHub 帳號：$login"
Write-Info "倉庫名稱：$RepoName（公開）"

# 確保主分支為 main
git branch -M main 2>$null | Out-Null

$slug = "$login/$RepoName"
$originUrl = $null
try { $originUrl = git remote get-url origin 2>$null } catch { }

if ($originUrl) {
    Write-Info "已有 remote origin，直接推送…"
    git push -u origin main
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    gh repo create $RepoName --public --source=. --remote=origin --push
    if ($LASTEXITCODE -ne 0) {
        Write-Info "自動建立失敗（可能倉庫已存在），改為手動綁定 origin 並推送…"
        $url = "https://github.com/$slug.git"
        git remote remove origin 2>$null | Out-Null
        git remote add origin $url
        git push -u origin main
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}

# 寫入 src/version.py 的 GITHUB_REPO（僅在仍為空字串時）
$vf = Join-Path $PSScriptRoot "src\version.py"
$raw = [System.IO.File]::ReadAllText($vf, [System.Text.UTF8Encoding]::new($false))
if ($raw -match 'GITHUB_REPO:\s*str\s*=\s*""') {
    $raw2 = $raw -replace 'GITHUB_REPO:\s*str\s*=\s*""', "GITHUB_REPO: str = `"$slug`""
    [System.IO.File]::WriteAllText($vf, $raw2, [System.Text.UTF8Encoding]::new($false))
    git add "src/version.py"
    git commit -m "chore: set GITHUB_REPO for in-app update"
    git push
    Write-Ok "已設定 GITHUB_REPO = $slug"
} else {
    Write-Info "src/version.py 已有 GITHUB_REPO，略過寫入。"
}

Write-Ok ""
Write-Ok "完成。倉庫：https://github.com/$slug"
Write-Ok "之後改版請記得：更新 src/version.py 的 APP_VERSION，並在 GitHub 發佈 Release（標籤建議與版號一致）。"
