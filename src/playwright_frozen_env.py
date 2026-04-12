# -*- coding: utf-8 -*-
"""PyInstaller onedir：修正 frozen 時 Playwright 的 driver 與瀏覽器路徑。

1) node.exe：PLAYWRIGHT_NODEJS_PATH 指向 _internal 內 driver。
2) Chromium：Playwright 在 sys.frozen 時會把 PLAYWRIGHT_BROWSERS_PATH 預設為 \"0\"（預期瀏覽器跟 exe 捆在一起）；
   本專案未捆瀏覽器，改為使用與 `playwright install chromium` 相同的使用者目錄 %LOCALAPPDATA%\\ms-playwright。
   需在連線 Playwright 前寫入 os.environ，否則 _transport 內的 setdefault 會沿用 \"0\" 而找不到 Chromium。"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def _default_browsers_dir() -> Path:
    local = (os.environ.get("LOCALAPPDATA") or "").strip()
    if local:
        return Path(local) / "ms-playwright"
    return Path.home() / "AppData" / "Local" / "ms-playwright"


def apply() -> None:
    if not getattr(sys, "frozen", False):
        return
    _bp = (os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "").strip()
    if not _bp or _bp == "0":
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_default_browsers_dir())
    if (os.environ.get("PLAYWRIGHT_NODEJS_PATH") or "").strip():
        return
    bases: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bases.append(Path(meipass))
    try:
        exe_dir = Path(sys.executable).resolve().parent
        bases.append(exe_dir / "_internal")
        bases.append(exe_dir)
    except OSError:
        pass
    for base in bases:
        node = base / "playwright" / "driver" / "node.exe"
        if node.is_file():
            os.environ["PLAYWRIGHT_NODEJS_PATH"] = str(node.resolve())
            return
    try:
        spec = importlib.util.find_spec("playwright")
        if spec and spec.origin:
            alt = Path(spec.origin).resolve().parent / "driver" / "node.exe"
            if alt.is_file():
                os.environ["PLAYWRIGHT_NODEJS_PATH"] = str(alt)
    except Exception:
        pass
