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
