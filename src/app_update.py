# -*- coding: utf-8 -*-
"""一鍵更新：git pull 與／或查詢 GitHub Releases。"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import requests
from packaging.version import InvalidVersion, Version

from src.paths import project_root
from src.version import APP_VERSION, GITHUB_REPO

# 一鍵覆寫安裝時不覆蓋的使用者檔案
_LAZY_EXCLUDE_NAMES = frozenset({"config.yaml", "sponsorship_data.db"})
# 單次下載上限（防異常大檔）
_MAX_ZIP_BYTES = 500 * 1024 * 1024


def _norm_ver(v: str) -> str:
    s = (v or "").strip().lstrip("vV")
    return s or "0"


def version_newer_than(remote_tag: str, local: str) -> bool:
    try:
        return Version(_norm_ver(remote_tag)) > Version(_norm_ver(local))
    except InvalidVersion:
        return False


def project_has_git() -> bool:
    return (project_root() / ".git").is_dir()


def _subprocess_run_kw() -> dict:
    """Windows GUI \u61c9\u7528\u7a0b\u5f0f\u57f7\u884c git \u6642\u52a0\u6b64\u65d7\u6a19\uff0c\u907f\u514d\u9583\u73fe\u63a7\u5236\u53f0\u8996\u7a97\u3002"""
    if sys.platform != "win32":
        return {}
    # Python 3.7+：不\u958b\u65b0\u63a7\u5236\u53f0\u8996\u7a97\uff08\u8207 pythonw / PyInstaller \u4e00\u81f4\uff09
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def git_pull_project() -> tuple[bool, str]:
    root = project_root()
    if not (root / ".git").is_dir():
        return False, "此目錄沒有 .git（若不是用 git clone，無法以 git 更新）。"
    exe = shutil.which("git")
    if not exe:
        return False, "找不到 git 指令，請安裝 Git for Windows 後在 PATH 中提供 git.exe。"
    try:
        r = subprocess.run(
            [exe, "-C", str(root), "pull", "--ff-only"],
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
            **_subprocess_run_kw(),
        )
    except subprocess.TimeoutExpired:
        return False, "git pull 逾時。"
    except OSError as e:
        return False, str(e)
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    msg = "\n".join(x for x in (out, err) if x)
    if r.returncode != 0:
        return False, msg or f"git pull 失敗（結束碼 {r.returncode}）。"
    return True, msg or "已與遠端同步（無新提交或已最新）。"


def fetch_latest_release_json(repo: str) -> tuple[dict | None, str | None]:
    repo = (repo or "").strip().strip("/")
    if "/" not in repo:
        return None, None
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        r = requests.get(
            url,
            timeout=20,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "sponsor-tracker-update"},
        )
    except requests.RequestException as e:
        return None, str(e)
    if r.status_code == 404:
        return None, "找不到 releases（倉庫可能尚未建立 Release）。"
    if r.status_code != 200:
        return None, f"GitHub API 錯誤：HTTP {r.status_code}"
    data = r.json()
    return data if isinstance(data, dict) else None, None


def fetch_latest_release_tag(repo: str) -> tuple[str | None, str | None]:
    data, err = fetch_latest_release_json(repo)
    if data is None:
        return None, err
    tag = (data.get("tag_name") or data.get("name") or "").strip()
    return (tag or None), None


def pick_user_zip_asset(assets: list) -> dict | None:
    """選 Release 裡使用者上傳的 zip（略過 GitHub 自動產生的 Source code）。"""
    cands: list[dict] = []
    for a in assets:
        if not isinstance(a, dict):
            continue
        name = (a.get("name") or "").strip()
        if not name.lower().endswith(".zip"):
            continue
        if "source code" in name.lower():
            continue
        cands.append(a)
    if not cands:
        for a in assets:
            if not isinstance(a, dict):
                continue
            name = (a.get("name") or "").strip()
            if name.lower().endswith(".zip"):
                cands.append(a)
    if not cands:
        return None
    return max(cands, key=lambda x: int(x.get("size") or 0))


def lazy_update_supported() -> bool:
    """僅 Windows 打包 exe：可一鍵覆寫程式檔（設定檔另存）。"""
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def fetch_lazy_update_plan(repo: str) -> tuple[dict | None, str | None]:
    """
    回傳：
      {"kind": "uptodate", "latest": str}
      {"kind": "update", "latest": str, "url": str, "size": int, "name": str}
    或 (None, 錯誤訊息)
    """
    repo = (repo or "").strip()
    if "/" not in repo:
        return None, "未設定 GitHub 倉庫。"
    data, err = fetch_latest_release_json(repo)
    if data is None:
        return None, err or "無法取得 Release。"
    tag = (data.get("tag_name") or "").strip().lstrip("vV") or (data.get("name") or "").strip().lstrip("vV")
    if not tag:
        return None, "Release 無有效版本標籤。"
    local = current_app_version()
    if not version_newer_than(tag, local):
        return {"kind": "uptodate", "latest": tag}, None
    asset = pick_user_zip_asset(data.get("assets") or [])
    if not asset:
        return None, (
            "此 Release 沒有可用的 .zip 附件。\n"
            "請在 GitHub Release 上傳「免安裝資料夾」壓成的 zip，\n"
            "勿只依賴網頁上的 Source code（zip）。"
        )
    url = (asset.get("browser_download_url") or "").strip()
    if not url:
        return None, "下載網址無效。"
    size = int(asset.get("size") or 0)
    name = (asset.get("name") or "update.zip").strip()
    return {"kind": "update", "latest": tag, "url": url, "size": size, "name": name}, None


def _lazy_update_exe_names(preferred: str) -> tuple[str, ...]:
    """Prefer the running exe name; also try known aliases (English rename period)."""
    names: list[str] = []
    p = (preferred or "").strip()
    if p and p not in names:
        names.append(p)
    for n in ("贊助額追蹤.exe", "SponsorTracker.exe"):
        if n not in names:
            names.append(n)
    return tuple(names)


def _find_staging_dir_with_exe(root: Path, exe_name: str) -> Path | None:
    for p in root.rglob(exe_name):
        try:
            if p.is_file():
                return p.parent
        except OSError:
            continue
    return None


def download_zip_and_extract(
    url: str,
    exe_name: str,
    progress_cb: object | None = None,
) -> tuple[Path | None, Path | None, str | None]:
    """
    下載 zip 並解壓到暫存目錄。
    回傳 (staging_dir, work_root, None) 或 (None, None, error)。
    staging_dir 為內含 exe 與 _internal 的資料夾；work_root 供更新完成後刪除整包暫存。
    """
    work_root = Path(tempfile.mkdtemp(prefix="sponsor_lazy_up_"))
    zip_path = work_root / "update.zip"
    extract_root = work_root / "extracted"

    def _cleanup_wr() -> None:
        try:
            shutil.rmtree(work_root, ignore_errors=True)
        except OSError:
            pass

    try:
        extract_root.mkdir(parents=True, exist_ok=True)
        headers = {"Accept": "application/octet-stream", "User-Agent": "sponsor-tracker-update"}
        with requests.get(url, stream=True, timeout=120, headers=headers, allow_redirects=True) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0)
            if total > _MAX_ZIP_BYTES:
                _cleanup_wr()
                return None, None, f"檔案過大（{total // (1024 * 1024)} MB），已中止。"
            n = 0
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(65536):
                    if not chunk:
                        continue
                    f.write(chunk)
                    n += len(chunk)
                    if n > _MAX_ZIP_BYTES:
                        _cleanup_wr()
                        return None, None, "下載超過安全上限，已中止。"
                    if progress_cb is not None and callable(progress_cb):
                        progress_cb(n, total if total > 0 else n)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_root)
        except zipfile.BadZipFile:
            _cleanup_wr()
            return None, None, "不是有效的 zip 檔。"
        staging = None
        tried = _lazy_update_exe_names(exe_name)
        for en in tried:
            staging = _find_staging_dir_with_exe(extract_root, en)
            if staging is not None:
                break
        if staging is None:
            _cleanup_wr()
            return (
                None,
                None,
                "壓縮檔內找不到免安裝 exe（已嘗試："
                + "、".join(tried)
                + "）。請確認 zip 為免安裝資料夾內容。",
            )
        try:
            if zip_path.is_file():
                zip_path.unlink(missing_ok=True)
        except OSError:
            pass
        return staging, work_root, None
    except requests.RequestException as e:
        _cleanup_wr()
        return None, None, f"下載失敗：{e}"
    except OSError as e:
        _cleanup_wr()
        return None, None, str(e)


def find_launcher_bat_near_exe(install_dir: Path) -> Path | None:
    """往上尋找「【一鍵啟動】贊助額追蹤.bat」，有則更新後改由此腳本啟動（與手動雙擊相同）。"""
    name = "【一鍵啟動】贊助額追蹤.bat"
    d = install_dir.resolve()
    for _ in range(10):
        try:
            cand = d / name
            if cand.is_file():
                return cand
        except OSError:
            pass
        parent = d.parent
        if parent == d:
            break
        d = parent
    return None


def spawn_lazy_windows_updater(staging_dir: Path, work_root: Path) -> tuple[bool, str]:
    """寫入批次檔：等待程式結束後 robocopy 覆寫、啟動新版（優先跑一鍵啟動腳本）、刪暫存。"""
    if not lazy_update_supported():
        return False, "僅支援 Windows 免安裝 exe。"
    install_dir = Path(sys.executable).resolve().parent
    exe_name = Path(sys.executable).name
    staging_s = str(staging_dir.resolve())
    install_s = str(install_dir.resolve())
    work_s = str(work_root.resolve())
    bat = Path(os.environ.get("TEMP", ".")) / f"sponsor_lazy_up_{os.getpid()}.bat"
    xf = " ".join(f'"{n}"' for n in sorted(_LAZY_EXCLUDE_NAMES))
    launch_bat = find_launcher_bat_near_exe(install_dir)
    if launch_bat is not None:
        bat_parent = str(launch_bat.parent.resolve())
        bat_path = str(launch_bat.resolve())
        start_line = f'start "" /D "{bat_parent}" "{bat_path}"'
    else:
        start_line = f'start "" "{install_s}\\{exe_name}"'
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "ping 127.0.0.1 -n 6 >nul",
        f'robocopy "{staging_s}" "{install_s}" /E /XF {xf} /R:3 /W:1 /NFL /NDL /NJH /NJS /NP',
        start_line,
        f'if exist "{work_s}" rd /s /q "{work_s}"',
        "del \"%~f0\"",
    ]
    try:
        bat.write_text("\r\n".join(lines), encoding="utf-8")
    except OSError as e:
        return False, str(e)
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", str(bat)],
            close_fds=True,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except OSError as e:
        return False, str(e)
    return True, ""


def releases_latest_url(repo: str) -> str:
    repo = (repo or "").strip().strip("/")
    return f"https://github.com/{repo}/releases/latest"


def configured_github_repo() -> str:
    return (GITHUB_REPO or "").strip()


def current_app_version() -> str:
    return (APP_VERSION or "0").strip() or "0"
