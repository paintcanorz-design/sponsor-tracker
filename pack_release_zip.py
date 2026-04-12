# -*- coding: utf-8 -*-
"""將「【請由此執行】贊助額追蹤」打成 zip，供 GitHub Release 一鍵更新下載。"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.version import APP_VERSION  # noqa: E402


def main() -> int:
    src = _ROOT / "【請由此執行】贊助額追蹤"
    exe = src / "贊助額追蹤.exe"
    if not exe.is_file():
        print("找不到「【請由此執行】贊助額追蹤\\贊助額追蹤.exe」，請先執行【一鍵打包】EXE.bat。", file=sys.stderr)
        return 1
    out_dir = _ROOT / "release"
    out_dir.mkdir(exist_ok=True)
    ver = (APP_VERSION or "0").strip().replace("/", "-")
    # 檔名僅用 ASCII，避免 gh release upload 等工具誤判參數
    zip_path = out_dir / f"sponsor-tracker-v{ver}-Win64.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in src.rglob("*"):
            try:
                if p.is_file():
                    zf.write(p, p.relative_to(src))
            except OSError as e:
                print(f"略過：{p}（{e}）", file=sys.stderr)
    print(f"[完成] {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
