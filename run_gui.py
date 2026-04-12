#!/usr/bin/env python3
"""啟動器：切換到正確目錄後執行 GUI，錯誤時彈出視窗顯示"""
import os
import sys
import traceback
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

try:
    from src.playwright_frozen_env import apply as _apply_playwright_frozen_env

    _apply_playwright_frozen_env()
except Exception:
    pass


def _install_playwright_browsers_cli() -> int:
    """下載 Playwright 用 Chromium（設定內瀏覽器登入）。由「開啟exe前請開啟此檔案安裝所需環境.bat」呼叫。"""
    print("正在安裝 Playwright 瀏覽器（Chromium），供「瀏覽器登入」使用。")
    print("約數百 MB，需網路；若失敗可改用手動貼 Cookie。\n")
    old = sys.argv[:]
    try:
        sys.argv = ["playwright", "install", "chromium"]
        from playwright.__main__ import main as pw_main

        pw_main()
        return 0
    except SystemExit as e:
        c = e.code
        if c is None:
            return 0
        return int(c) if isinstance(c, int) else 1
    except Exception as e:
        print(f"安裝失敗：{e}")
        return 1
    finally:
        sys.argv = old


if __name__ == "__main__" and "--install-playwright-browsers" in sys.argv:
    sys.argv = [x for x in sys.argv if x != "--install-playwright-browsers"]
    raise SystemExit(_install_playwright_browsers_cli())

import launch_bootstrap

launch_bootstrap.maybe_relaunch_with_py311(Path(__file__).resolve(), ROOT)


def main():
    try:
        import app_gui

        app_gui.main()
    except Exception as e:
        err = traceback.format_exc()
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("程式啟動失敗", f"{e}\n\n詳情:\n{err}")
            root.destroy()
        except Exception:
            print("程式啟動失敗：")
            print(err)
            input("按 Enter 關閉...")
        sys.exit(1)

if __name__ == "__main__":
    main()
