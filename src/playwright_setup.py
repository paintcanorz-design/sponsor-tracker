# -*- coding: utf-8 -*-
"""Playwright + Chromium 偵測與一次性安裝（供瀏覽器登入）。"""
from __future__ import annotations

import importlib
import subprocess
import sys


def _no_window_kw() -> dict:
    if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _apply_frozen_env() -> None:
    try:
        from src.playwright_frozen_env import apply as _apply

        _apply()
    except Exception:
        pass


def import_sync_playwright():
    """成功則回傳 sync_playwright callable；否則 None。"""
    try:
        mod = importlib.import_module("playwright.sync_api")
        return mod.sync_playwright
    except Exception:
        return None


def probe_chromium_ok() -> bool:
    """能否在本機啟動 Chromium（已安裝驅動與瀏覽器）。"""
    _apply_frozen_env()
    sp = import_sync_playwright()
    if sp is None:
        return False
    try:
        with sp() as p:
            b = p.chromium.launch(headless=True)
            b.close()
        return True
    except Exception:
        return False


def needs_playwright_setup() -> bool:
    if import_sync_playwright() is None:
        return True
    return not probe_chromium_ok()


def _pip_install_playwright() -> tuple[bool, str]:
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "playwright"],
            capture_output=True,
            text=True,
            timeout=600,
            **_no_window_kw(),
        )
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or "").strip()
            return False, (tail[-800:] if tail else "pip install playwright failed")
        return True, ""
    except Exception as e:
        return False, str(e)[:800]


def _install_chromium_browsers() -> tuple[bool, str]:
    try:
        r = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=900,
            **_no_window_kw(),
        )
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or "").strip()
            return False, (tail[-800:] if tail else "playwright install chromium failed")
        return True, ""
    except Exception as e:
        return False, str(e)[:800]


def ensure_playwright_and_chromium() -> tuple[bool, str]:
    """
    非 frozen：必要時 pip install playwright，再 playwright install chromium。
    frozen：僅能 install chromium（模組必須已隨程式提供）。
    回傳 (成功, 錯誤訊息片段)。
    """
    _apply_frozen_env()
    frozen = bool(getattr(sys, "frozen", False))

    if frozen:
        if import_sync_playwright() is None:
            return False, "frozen_no_playwright_module"
        if probe_chromium_ok():
            return True, ""
        ok_b, err_b = _install_chromium_browsers()
        if not ok_b:
            return False, err_b
        if not probe_chromium_ok():
            return False, "chromium_launch_failed_after_install"
        return True, ""

    if import_sync_playwright() is None:
        ok_p, err_p = _pip_install_playwright()
        if not ok_p:
            return False, err_p
        importlib.invalidate_caches()
        if import_sync_playwright() is None:
            return False, "playwright_import_still_fails"

    if probe_chromium_ok():
        return True, ""

    ok_b, err_b = _install_chromium_browsers()
    if not ok_b:
        return False, err_b
    importlib.invalidate_caches()
    if not probe_chromium_ok():
        return False, "chromium_launch_failed_after_install"
    return True, ""
