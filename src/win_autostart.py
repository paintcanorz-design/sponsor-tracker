# -*- coding: utf-8 -*-
"""Windows 開機自動啟動：寫入 HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run。"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REG_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "SponsorTrackerSponsorAmount"


def is_windows() -> bool:
    return sys.platform == "win32"


def build_launch_command() -> str | None:
    """回傳可寫入 Run 的指令字串；無法建立時回傳 None。"""
    if not is_windows():
        return None
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        return f'"{exe}"'
    from src.paths import project_root

    pyw = project_root() / "贊助額追蹤.pyw"
    pythonw = shutil.which("pythonw")
    if not pythonw or not pyw.is_file():
        return None
    return f'"{Path(pythonw).resolve()}" "{pyw.resolve()}"'


def apply_start_with_windows(enabled: bool) -> tuple[bool, str]:
    """啟用或移除開機自動啟動。非 Windows 一律視為成功且不做任何事。"""
    if not is_windows():
        return True, ""
    import winreg

    cmd = build_launch_command()
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_SUBKEY,
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_READ,
        )
    except OSError as e:
        return False, f"無法開啟登錄檔：{e}"
    try:
        if enabled:
            if not cmd:
                return False, "找不到 pythonw 或「贊助額追蹤.pyw」，無法設定自動啟動。"
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)
    return True, ""
