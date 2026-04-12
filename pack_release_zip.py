# -*- coding: utf-8 -*-
"""將「【請由此執行】贊助額追蹤」打成 zip，供 GitHub Release 一鍵更新下載。"""
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.version import APP_VERSION  # noqa: E402

# 絕不可打入公開 zip（使用者本機設定／資料庫／日誌）
_EXCLUDE_NAMES = frozenset(
    {
        "config.yaml",
        "sponsorship_data.db",
        "startup_error.log",
        "project_root.txt",
    }
)


def _must_skip_file(path: Path) -> bool:
    name = path.name.lower()
    if name in {n.lower() for n in _EXCLUDE_NAMES}:
        return True
    if name.endswith(".db"):
        return True
    return False


# 與 exe 同層一併發佈（由專案根複製，確保 zip 內一定有）
_BAT_SIDECAR = ("開啟exe前請開啟此檔案安裝所需環境.bat",)


def _copy_bat_scripts_into(src: Path) -> None:
    for name in _BAT_SIDECAR:
        root_f = _ROOT / name
        if not root_f.is_file():
            print(f"[警告] 專案根目錄缺少「{name}」，zip 將不含此腳本。", file=sys.stderr)
            continue
        try:
            shutil.copy2(root_f, src / name)
        except OSError as e:
            print(f"[警告] 無法複製「{name}」：{e}", file=sys.stderr)


def _pick_source_dir() -> Path | None:
    """優先使用 dist（僅 PyInstaller 產物）；否則用【請由此執行】並仍套用排除名單。"""
    for d in (_ROOT / "dist" / "贊助額追蹤", _ROOT / "【請由此執行】贊助額追蹤"):
        if (d / "贊助額追蹤.exe").is_file():
            return d
    return None


def main() -> int:
    src = _pick_source_dir()
    if src is None:
        print("找不到 dist\\贊助額追蹤 或「【請由此執行】贊助額追蹤」內的 exe，請先執行【一鍵打包】EXE.bat。", file=sys.stderr)
        return 1
    _copy_bat_scripts_into(src)
    out_dir = _ROOT / "release"
    out_dir.mkdir(exist_ok=True)
    ver = (APP_VERSION or "0").strip().replace("/", "-")
    # 檔名僅用 ASCII，避免 gh release upload 等工具誤判參數
    zip_path = out_dir / f"sponsor-tracker-v{ver}-Win64.zip"
    skipped = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in src.rglob("*"):
            try:
                if p.is_file():
                    if _must_skip_file(p):
                        skipped += 1
                        continue
                    zf.write(p, p.relative_to(src))
            except OSError as e:
                print(f"略過：{p}（{e}）", file=sys.stderr)
    if skipped:
        print(f"[提示] 已排除 {skipped} 個本機／敏感檔，未打入 zip。", file=sys.stderr)
    print(f"[完成] {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
