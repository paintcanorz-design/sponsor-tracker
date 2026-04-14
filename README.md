# Sponsor Tracker

Portable Windows app to **track combined sponsorship revenue** from **Patreon**, **pixiv Fanbox**, and **Fantia** (JPY-focused dashboard, Japan time JST).

**UI languages:** Traditional Chinese, English, Japanese (auto-detect or choose in Settings).

---

## 繁體中文（台灣）

### 這是什麼？

協助創作者把多平台的贊助／月費收入**合併觀察**：即時總額、走勢圖、每週與昨日對比、各平台卡片，並可排程自動更新、Discord Webhook（贊助增加或每日報表）、系統匣與迷你監控窗。

### 主要功能

- **多平台登入與抓取**：Patreon（Cookie）、Fanbox（Cookie）、Fantia（`_session_id`）；瀏覽器登入依賴 Playwright Chromium。
- **儀表板**：合計（日圓換算）、贊助人數、週對週、昨日金額變化、各平台明細、走勢（月／年）。
- **排程更新**：可選 15 分～4 小時間隔；偵測到增加可播通知音並可推播至 Discord。
- **國際化**：依系統語言或使用者在設定中選擇介面語言（繁中／英文／日文）。
- **Windows 免安裝**：PyInstaller 產生 `贊助額追蹤` 資料夾；**一鍵更新**會從 GitHub Release 下載你上傳的 `.zip` 覆寫程式（保留 `config.yaml` 與資料庫）。

### 環境與首次執行

1. 複製 `config.example.yaml` 為 `config.yaml`（若尚無）。
2. 依說明安裝 **Python 依賴** 與 **`playwright install chromium`**（打包版使用者執行同資料夾內的環境安裝批次檔）。
3. 執行 `贊助額追蹤.exe`（或開發模式 `python run_gui.py`）。

### 更新與版本

- 程式內建版本號見 **`src/version.py`** 的 `APP_VERSION`（目前版本為 `1.15.0`）。
- **GitHub**：推送 **`v*`** 標籤（例如 `v1.15.0`）會觸發 Actions 建置並上傳 **`SponsorTracker-Windows-v{version}.zip`**。一鍵更新需要 Release 上的**自訂 zip**（內含 `贊助額追蹤.exe` 與 `_internal`），請勿僅依賴「Source code」自動壓縮檔。
- 本機打包 zip：`.\scripts\build_windows_zip.ps1`（需已安裝 `requirements-build.txt`）。

### 設定倉庫

- `GITHUB_REPO` 於 `src/version.py` 設為 `owner/repo`，與 Release 來源一致時，程式可檢查更新並執行一鍵更新。

---

## English

### What is this?

A **portable Windows** tool for creators to monitor **combined sponsorship income** across **Patreon**, **Fanbox**, and **Fantia**, with totals converted toward **JPY**, schedules in **JST**, charts, Discord notifications, and a system-tray / mini dashboard.

### Features

- **Fetch & login**: Patreon cookies, Fanbox cookies, Fantia session; browser login uses **Playwright Chromium**.
- **Dashboard**: totals, patron counts, week-over-week, day-over-day, per-platform breakdown, trend (month/year).
- **Scheduled updates**: intervals from 15 minutes to 4 hours; optional sound + Discord webhook on increases and optional daily summary.
- **i18n**: **Traditional Chinese**, **English**, **Japanese** — system language or explicit choice in Settings.
- **Updates**: **One-click update** (portable exe only) downloads the **custom `.zip` asset** from the latest **GitHub Release** (not the auto-generated source archive). Your `config.yaml` and database are preserved.

### Setup

1. Copy `config.example.yaml` to `config.yaml` if needed.
2. Install dependencies and run **`playwright install chromium`** (see project batch files for the frozen exe workflow).
3. Run **`贊助額追蹤.exe`** (portable build) or `python run_gui.py` for development.

### Releases & versioning

- Bump **`APP_VERSION`** in `src/version.py` (current release line is **`1.15.0`**).
- Push a git tag like **`v1.15.0`**. The **Release** workflow builds PyInstaller output and uploads **`SponsorTracker-Windows-v1.15.0.zip`**.
- Local zip: `.\scripts\build_windows_zip.ps1` after `pip install -r requirements.txt -r requirements-build.txt`.

---

## 日本語

### 概要

**Patreon / pixiv Fanbox / Fantia** の支援・月額状況を **合算して把握** する **Windows 向けポータブル** アプリです。表示は **日本時間（JST）** を基準にし、金額は **円換算の合計** を中心に表示します。

### 機能

- **取得とログイン**：各プラットフォームの認証情報（Cookie / セッション）。ブラウザログインは **Playwright Chromium** が必要です。
- **ダッシュボード**：合計・支援者数・週次比・前日比・プラットフォーム別・推移グラフ（月／年）。
- **スケジュール更新**：15 分～4 時間隔。増加検知時の通知音、**Discord** への投稿、毎日定時のサマリーに対応。
- **表示言語**：**繁体字中国語 / 英語 / 日本語**（自動または設定で変更）。
- **更新**：**ポータブル exe** では GitHub の **最新 Release に添付された zip**（`贊助額追蹤.exe` と `_internal` を含む）から **ワンクリック更新** できます。`config.yaml` と DB は保持されます。

### セットアップ

1. `config.example.yaml` を `config.yaml` にコピー。
2. 依存関係と **`playwright install chromium`** を実行（同梱の bat 参照）。
3. **`贊助額追蹤.exe`** を実行（開発時は `python run_gui.py`）。

### リリース

- バージョンは **`src/version.py`** の `APP_VERSION`（現在は **`1.15.0`**）。
- **`v1.15.0`** のような **タグを push** すると GitHub Actions がビルドし、**`SponsorTracker-Windows-v1.15.0.zip`** を Release に添付します。
- 手元で zip：`.\scripts\build_windows_zip.ps1`

---

## Repository

Default GitHub repo for in-app update checks: **`src/version.py`** (`GITHUB_REPO`).
