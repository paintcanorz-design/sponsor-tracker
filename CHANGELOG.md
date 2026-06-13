# Changelog

## 1.16.1

- **Release zip**: GitHub Actions now uses `pack_release_zip.py` (same as local build). Includes `開啟exe前請開啟此檔案安裝所需環境.bat` and `使用說明.txt` beside the exe.

## 1.16

- **Patreon**: Fix monthly earnings when displayed as compact K (e.g. `$1.06K` → 1060 USD). Values under 10 without a K suffix are scaled ×1000.

## 1.12

- Mini dashboard UI refresh: right-aligned people count, compact top-right controls (pin + open main), and subtle inset frame style for clearer window separation.
- Mini dashboard behavior tuning: improved per-screen DPI resize stability when moving across monitors with different scaling.

## 1.1.1

- Windows portable **exe / onedir name** restored to **贊助額追蹤** (matches existing launcher batch files and one-click update expectations).
- One-click update: when validating the downloaded zip, the app tries **贊助額追蹤.exe** and **SponsorTracker.exe** so older 1.1.0 zips remain applicable if needed.

## 1.1.0

- UI: Traditional Chinese, English, and Japanese; system language or Settings (`gui.ui_language`).
- Windows portable build folder / exe name: **SponsorTracker**; GitHub Actions release workflow uploads `SponsorTracker-Windows-v*.zip` for one-click updates.
- Documentation: trilingual README; local zip script `scripts/build_windows_zip.ps1`.

## Earlier releases

See git history and previous tags (e.g. 1.0.x).
