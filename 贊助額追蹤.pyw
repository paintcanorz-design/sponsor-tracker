#!/usr/bin/env pythonw
"""
Windows 雙擊啟動用（無主控台）。
若啟動失敗，會顯示錯誤視窗並寫入 startup_error.log。
"""
from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import traceback


def _show_error(title: str, msg: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, msg)
        try:
            root.destroy()
        except Exception:
            pass
    except Exception:
        # 任何情況下都不要再噴錯
        pass


def _relaunch_with_preferred_pythonw(project_root: Path) -> bool:
    """
    若目前執行的 Python 環境缺套件，嘗試改用偏好的 pythonw.exe 重新啟動本程式。
    回傳 True 表示已成功觸發重啟（此程序應直接 return/exit）。
    """
    if os.environ.get("SPONSORSHIP_TRACKER_RELAUNCHED") == "1":
        return False

    candidates = [
        Path(r"D:\Miniconda3\pythonw.exe"),
        Path(r"D:\Miniconda3\python.exe"),  # fallback（會閃一下 console，但至少能跑）
    ]
    for exe in candidates:
        if exe.exists():
            try:
                env = os.environ.copy()
                env["SPONSORSHIP_TRACKER_RELAUNCHED"] = "1"
                subprocess.Popen(
                    [str(exe), str(project_root / "贊助額追蹤.pyw")],
                    cwd=str(project_root),
                    env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                return True
            except Exception:
                continue
    return False


def main() -> None:
    # 確保可 import 專案
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))

    import launch_bootstrap

    launch_bootstrap.maybe_relaunch_with_py311(Path(__file__), root)

    try:
        # 檢查關鍵依賴（常見：雙擊用錯 Python 環境）
        import yaml  # noqa: F401
        import PySide6  # noqa: F401

        import run_gui

        run_gui.main()
    except Exception:
        # 若是用錯 Python 環境造成的缺套件，先嘗試自動改用偏好的 pythonw.exe 重新啟動
        if _relaunch_with_preferred_pythonw(root):
            return
        err = traceback.format_exc()
        log_path = root / "startup_error.log"
        try:
            log_path.write_text(err, encoding="utf-8")
        except Exception:
            pass
        _show_error(
            "贊助額追蹤 - 啟動失敗",
            "程式啟動失敗。\n\n"
            f"請查看：{log_path}\n\n"
            "常見原因：缺少套件 / Python 環境不對 / 權限問題。\n\n"
            "完整錯誤：\n" + err[-1200:],
        )


if __name__ == "__main__":
    main()

