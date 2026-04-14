# -*- coding: utf-8 -*-
"""Regenerate README.md (UTF-8) with ZH / EN / JA sections."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = """# Sponsor Tracker

Portable Windows app to **track combined sponsorship revenue** from **Patreon**, **pixiv Fanbox**, and **Fantia** (JPY-focused dashboard, Japan time JST).

**UI languages:** Traditional Chinese, English, Japanese (auto-detect or choose in Settings).

---

## \u7e41\u9ad4\u4e2d\u6587\uff08\u53f0\u7063\uff09

### \u9019\u662f\u4ec0\u9ebc\uff1f

\u5354\u52a9\u5275\u4f5c\u8005\u628a\u591a\u5e73\u53f0\u7684\u8d0a\u52a9\uff0f\u6708\u8cbb\u6536\u5165**\u5408\u4f75\u89c0\u5bdf**\uff1a\u5373\u6642\u7e3d\u984d\u3001\u8d70\u52e2\u5716\u3001\u6bcf\u9031\u8207\u6628\u65e5\u5c0d\u6bd4\u3001\u5404\u5e73\u53f0\u5361\u7247\uff0c\u4e26\u53ef\u6392\u7a0b\u81ea\u52d5\u66f4\u65b0\u3001Discord Webhook\uff08\u8d0a\u52a9\u589e\u52a0\u6216\u6bcf\u65e5\u5831\u8868\uff09\u3001\u7cfb\u7d71\u5323\u8207\u8ff7\u4f60\u76e3\u63a7\u7a97\u3002

### \u4e3b\u8981\u529f\u80fd

- **\u591a\u5e73\u53f0\u767b\u5165\u8207\u6293\u53d6**\uff1aPatreon\uff08Cookie\uff09\u3001Fanbox\uff08Cookie\uff09\u3001Fantia\uff08`_session_id`\uff09\uff1b\u700f\u89bd\u5668\u767b\u5165\u4f9d\u8cf4 Playwright Chromium\u3002
- **\u5100\u8868\u677f**\uff1a\u5408\u8a08\uff08\u65e5\u5713\u63db\u7b97\uff09\u3001\u8d0a\u52a9\u4eba\u6578\u3001\u9031\u5c0d\u9031\u3001\u6628\u65e5\u91d1\u984d\u8b8a\u5316\u3001\u5404\u5e73\u53f0\u660e\u7d30\u3001\u8d70\u52e2\uff08\u6708\uff0f\u5e74\uff09\u3002
- **\u6392\u7a0b\u66f4\u65b0**\uff1a\u53ef\u9078 15 \u5206\uff5e4 \u5c0f\u6642\u9593\u9694\uff1b\u5075\u6e2c\u5230\u589e\u52a0\u53ef\u64ad\u901a\u77e5\u97f3\u4e26\u53ef\u63a8\u64ad\u81f3 Discord\u3002
- **\u570b\u969b\u5316**\uff1a\u4f9d\u7cfb\u7d71\u8a9e\u8a00\u6216\u4f7f\u7528\u8005\u5728\u8a2d\u5b9a\u4e2d\u9078\u64c7\u4ecb\u9762\u8a9e\u8a00\uff08\u7e41\u4e2d\uff0f\u82f1\u6587\uff0f\u65e5\u6587\uff09\u3002
- **Windows \u514d\u5b89\u88dd**\uff1aPyInstaller \u7522\u751f `\u8d0a\u52a9\u984d\u8ffd\u8e64` \u8cc7\u6599\u593e\uff1b**\u4e00\u9375\u66f4\u65b0**\u6703\u5f9e GitHub Release \u4e0b\u8f09\u4f60\u4e0a\u50b3\u7684 `.zip` \u8986\u5beb\u7a0b\u5f0f\uff08\u4fdd\u7559 `config.yaml` \u8207\u8cc7\u6599\u5eab\uff09\u3002

### \u74b0\u5883\u8207\u9996\u6b21\u57f7\u884c

1. \u8907\u88fd `config.example.yaml` \u70ba `config.yaml`\uff08\u82e5\u5c1a\u7121\uff09\u3002
2. \u4f9d\u8aaa\u660e\u5b89\u88dd **Python \u4f9d\u8cf4** \u8207 **`playwright install chromium`**\uff08\u6253\u5305\u7248\u4f7f\u7528\u8005\u57f7\u884c\u540c\u8cc7\u6599\u593e\u5167\u7684\u74b0\u5883\u5b89\u88dd\u6279\u6b21\u6a94\uff09\u3002
3. \u57f7\u884c `\u8d0a\u52a9\u984d\u8ffd\u8e64.exe`\uff08\u6216\u958b\u767c\u6a21\u5f0f `python run_gui.py`\uff09\u3002

### \u66f4\u65b0\u8207\u7248\u672c

- \u7a0b\u5f0f\u5167\u5efa\u7248\u672c\u865f\u898b **`src/version.py`** \u7684 `APP_VERSION`\uff08\u76ee\u524d\u8207 **1.1** \u5c0d\u61c9\u70ba `1.1.1`\uff09\u3002
- **GitHub**\uff1a\u63a8\u9001 **`v*`** \u6a19\u7c64\uff08\u4f8b\u5982 `v1.1.1`\uff09\u6703\u89f8\u767c Actions \u5efa\u7f6e\u4e26\u4e0a\u50b3 **`SponsorTracker-Windows-v{version}.zip`**\u3002\u4e00\u9375\u66f4\u65b0\u9700\u8981 Release \u4e0a\u7684**\u81ea\u8a02 zip**\uff08\u5167\u542b `\u8d0a\u52a9\u984d\u8ffd\u8e64.exe` \u8207 `_internal`\uff09\uff0c\u8acb\u52ff\u50c5\u4f9d\u8cf4\u300cSource code\u300d\u81ea\u52d5\u58d3\u7e2e\u6a94\u3002
- \u672c\u6a5f\u6253\u5305 zip\uff1a`.\u005cscripts\u005cbuild_windows_zip.ps1`\uff08\u9700\u5df2\u5b89\u88dd `requirements-build.txt`\uff09\u3002

### \u8a2d\u5b9a\u5009\u5eab

- `GITHUB_REPO` \u65bc `src/version.py` \u8a2d\u70ba `owner/repo`\uff0c\u8207 Release \u4f86\u6e90\u4e00\u81f4\u6642\uff0c\u7a0b\u5f0f\u53ef\u6aa2\u67e5\u66f4\u65b0\u4e26\u57f7\u884c\u4e00\u9375\u66f4\u65b0\u3002

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
3. Run **`\u8d0a\u52a9\u984d\u8ffd\u8e64.exe`** (portable build) or `python run_gui.py` for development.

### Releases & versioning

- Bump **`APP_VERSION`** in `src/version.py` (current line with **1.1** is **`1.1.1`** for semver).
- Push a git tag like **`v1.1.1`**. The **Release** workflow builds PyInstaller output and uploads **`SponsorTracker-Windows-v1.1.1.zip`**.
- Local zip: `.\u005cscripts\u005cbuild_windows_zip.ps1` after `pip install -r requirements.txt -r requirements-build.txt`.

---

## \u65e5\u672c\u8a9e

### \u6982\u8981

**Patreon / pixiv Fanbox / Fantia** \u306e\u652f\u63f4\u30fb\u6708\u984d\u72b6\u6cc1\u3092 **\u5408\u7b97\u3057\u3066\u628a\u63e1** \u3059\u308b **Windows \u5411\u3051\u30dd\u30fc\u30bf\u30d6\u30eb** \u30a2\u30d7\u30ea\u3067\u3059\u3002\u8868\u793a\u306f **\u65e5\u672c\u6642\u9593\uff08JST\uff09** \u3092\u57fa\u6e96\u306b\u3057\u3001\u91d1\u984d\u306f **\u5186\u63db\u7b97\u306e\u5408\u8a08** \u3092\u4e2d\u5fc3\u306b\u8868\u793a\u3057\u307e\u3059\u3002

### \u6a5f\u80fd

- **\u53d6\u5f97\u3068\u30ed\u30b0\u30a4\u30f3**\uff1a\u5404\u30d7\u30e9\u30c3\u30c8\u30d5\u30a9\u30fc\u30e0\u306e\u8a8d\u8a3c\u60c5\u5831\uff08Cookie / \u30bb\u30c3\u30b7\u30e7\u30f3\uff09\u3002\u30d6\u30e9\u30a6\u30b6\u30ed\u30b0\u30a4\u30f3\u306f **Playwright Chromium** \u304c\u5fc5\u8981\u3067\u3059\u3002
- **\u30c0\u30c3\u30b7\u30e5\u30dc\u30fc\u30c9**\uff1a\u5408\u8a08\u30fb\u652f\u63f4\u8005\u6570\u30fb\u9031\u6b21\u6bd4\u30fb\u524d\u65e5\u6bd4\u30fb\u30d7\u30e9\u30c3\u30c8\u30d5\u30a9\u30fc\u30e0\u5225\u30fb\u63a8\u79fb\u30b0\u30e9\u30d5\uff08\u6708\uff0f\u5e74\uff09\u3002
- **\u30b9\u30b1\u30b8\u30e5\u30fc\u30eb\u66f4\u65b0**\uff1a15 \u5206\uff5e4 \u6642\u9593\u9694\u3002\u5897\u52a0\u691c\u77e5\u6642\u306e\u901a\u77e5\u97f3\u3001**Discord** \u3078\u306e\u6295\u7a3f\u3001\u6bce\u65e5\u5b9a\u6642\u306e\u30b5\u30de\u30ea\u30fc\u306b\u5bfe\u5fdc\u3002
- **\u8868\u793a\u8a00\u8a9e**\uff1a**\u7e41\u4f53\u5b57\u4e2d\u56fd\u8a9e / \u82f1\u8a9e / \u65e5\u672c\u8a9e**\uff08\u81ea\u52d5\u307e\u305f\u306f\u8a2d\u5b9a\u3067\u5909\u66f4\uff09\u3002
- **\u66f4\u65b0**\uff1a**\u30dd\u30fc\u30bf\u30d6\u30eb exe** \u3067\u306f GitHub \u306e **\u6700\u65b0 Release \u306b\u6dfb\u4ed8\u3055\u308c\u305f zip**\uff08`\u8d0a\u52a9\u984d\u8ffd\u8e64.exe` \u3068 `_internal` \u3092\u542b\u3080\uff09\u304b\u3089 **\u30ef\u30f3\u30af\u30ea\u30c3\u30af\u66f4\u65b0** \u3067\u304d\u307e\u3059\u3002`config.yaml` \u3068 DB \u306f\u4fdd\u6301\u3055\u308c\u307e\u3059\u3002

### \u30bb\u30c3\u30c8\u30a2\u30c3\u30d7

1. `config.example.yaml` \u3092 `config.yaml` \u306b\u30b3\u30d4\u30fc\u3002
2. \u4f9d\u5b58\u95a2\u4fc2\u3068 **`playwright install chromium`** \u3092\u5b9f\u884c\uff08\u540c\u68b1\u306e bat \u53c2\u7167\uff09\u3002
3. **`\u8d0a\u52a9\u984d\u8ffd\u8e64.exe`** \u3092\u5b9f\u884c\uff08\u958b\u767a\u6642\u306f `python run_gui.py`\uff09\u3002

### \u30ea\u30ea\u30fc\u30b9

- \u30d0\u30fc\u30b8\u30e7\u30f3\u306f **`src/version.py`** \u306e `APP_VERSION`\uff08**1.1** \u5bfe\u5fdc\u306f **`1.1.1`**\uff09\u3002
- **`v1.1.1`** \u306e\u3088\u3046\u306a **\u30bf\u30b0\u3092 push** \u3059\u308b\u3068 GitHub Actions \u304c\u30d3\u30eb\u30c9\u3057\u3001**`SponsorTracker-Windows-v1.1.1.zip`** \u3092 Release \u306b\u6dfb\u4ed8\u3057\u307e\u3059\u3002
- \u624b\u5143\u3067 zip\uff1a`.\u005cscripts\u005cbuild_windows_zip.ps1`

---

## Repository

Default GitHub repo for in-app update checks: **`src/version.py`** (`GITHUB_REPO`).
"""
ROOT.joinpath("README.md").write_text(text, encoding="utf-8")
print("wrote README.md")
