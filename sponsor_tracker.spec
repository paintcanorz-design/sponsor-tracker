# -*- mode: python ; coding: utf-8 -*-
"""Onedir portable EXE (folder + _internal). Do not bundle config.yaml or .db."""
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

_spec_file = Path(SPECPATH).resolve()
_spec_dir = _spec_file.parent
if not (_spec_dir / "run_gui.py").is_file():
    _spec_dir = Path(os.getcwd()).resolve()

_APP = "贊助額追蹤"

# PySide6
datas, binaries, hiddenimports = collect_all("PySide6")

# Pillow
_d2, _b2, _h2 = collect_all("PIL")
datas += _d2
binaries += _b2
hiddenimports += _h2

# Playwright driver only (Chromium: use machine cache from "playwright install chromium" when building/testing)
_pw_d, _pw_b, _pw_h = collect_all("playwright")
datas += _pw_d
binaries += _pw_b
hiddenimports += _pw_h

_alert = _spec_dir / "alert.wav.wav"
if _alert.is_file():
    datas = list(datas) + [(str(_alert), ".")]

_icon = _spec_dir / "app_icon.ico"
if _icon.is_file():
    datas = list(datas) + [(str(_icon), ".")]

block_cipher = None

a = Analysis(
    ["run_gui.py"],
    pathex=[str(_spec_dir)],
    binaries=binaries,
    datas=list(datas),
    hiddenimports=hiddenimports
    + [
        "yaml",
        "schedule",
        "app_gui",
        "launch_bootstrap",
        "certifi",
        "src.paths",
        "src.database",
        "src.jst",
        "src.exchange",
        "src.currency_ui",
        "src.qt_app",
        "src.qt_app.application",
        "src.qt_app.shared",
        "src.i18n",
        "src.i18n_table",
        "PySide6.QtCharts",
        "PySide6.QtSvg",
        "src.qt_app.ui_assets",
        "src.auth.browser_login",
        "src.playwright_frozen_env",
        "src.fetchers",
        "src.fetchers.patreon_fetcher",
        "src.fetchers.fanbox_fetcher",
        "src.fetchers.fantia_fetcher",
        "src.fetchers.playwright_fallback",
        "src.fetchers.social_fetcher",
        "playwright",
        "playwright.sync_api",
        "playwright._impl",
        "greenlet",
        "pyee",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

_exe_kw = dict(
    exclude_binaries=True,
    name=_APP,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
if _icon.is_file():
    _exe_kw["icon"] = str(_icon)
exe = EXE(pyz, a.scripts, [], **_exe_kw)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=_APP,
)
