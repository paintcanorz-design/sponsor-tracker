# -*- coding: utf-8 -*-
"""一鍵更新：git pull 與／或查詢 GitHub Releases。"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import requests
from packaging.version import InvalidVersion, Version

from src.paths import project_root
from src.version import APP_VERSION, GITHUB_REPO


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


def git_pull_project() -> tuple[bool, str]:
    root = project_root()
    if not (root / ".git").is_dir():
        return False, "此目錄沒有 .git（若不是用 git clone，無法以 git 更新）。"
    exe = shutil.which("git")
    if not exe:
        return False, "找不到 git 指令，請安裝 Git for Windows 後再試。"
    try:
        r = subprocess.run(
            [exe, "-C", str(root), "pull", "--ff-only"],
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
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


def fetch_latest_release_tag(repo: str) -> tuple[str | None, str | None]:
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
    tag = (data.get("tag_name") or data.get("name") or "").strip()
    return (tag or None), None


def releases_latest_url(repo: str) -> str:
    repo = (repo or "").strip().strip("/")
    return f"https://github.com/{repo}/releases/latest"


def configured_github_repo() -> str:
    return (GITHUB_REPO or "").strip()


def current_app_version() -> str:
    return (APP_VERSION or "0").strip() or "0"
