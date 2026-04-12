"""專案根目錄：與雙擊 贊助額追蹤.pyw 相同（該檔所在資料夾即為資料根）。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# 打包後強制指定資料目錄（最高優先）
_ENV_ROOT = "SPONSORSHIP_PROJECT_ROOT"
_DEBUG_ENV = "SPONSORSHIP_DEBUG_PATHS"

# 與你專案內啟動檔相同檔名，用來鎖定「跟 .pyw 同一套設定」
_ANCHOR_LAUNCHERS = ("贊助額追蹤.pyw",)

_PERSIST_NAME = "project_root.txt"
_PERSIST_DIRNAME = "贊助額追蹤"

_cached_root: Path | None = None


def _frozen_exe_dir() -> Path:
    return Path(sys.executable).resolve().parent


def _persist_dir() -> Path:
    base = (os.environ.get("LOCALAPPDATA") or os.environ.get("USERPROFILE") or ".").strip()
    return Path(base) / _PERSIST_DIRNAME


def _persist_file() -> Path:
    return _persist_dir() / _PERSIST_NAME


def _debug_log(lines: list[str]) -> None:
    if not (os.environ.get(_DEBUG_ENV) or "").strip():
        return
    try:
        p = _persist_dir() / "paths_debug.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime

        hdr = f"[{datetime.now().isoformat(timespec='seconds')}]"
        p.write_text(hdr + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass


def _parse_persisted_text(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None
    if text.startswith("v2"):
        parts = text.splitlines()
        if len(parts) >= 2:
            return parts[1].strip() or None
        return None
    return text


def _load_persisted_path_string() -> str | None:
    try:
        p = _persist_file()
        if not p.is_file():
            return None
        return _parse_persisted_text(p.read_text(encoding="utf-8"))
    except OSError:
        return None


def _dir_is_plausible_root(d: Path) -> bool:
    if not d.is_dir():
        return False
    if (d / "config.yaml").is_file():
        return True
    for name in _ANCHOR_LAUNCHERS:
        if (d / name).is_file():
            return True
    return False


def _load_persisted_root_candidate() -> Path | None:
    line = _load_persisted_path_string()
    if not line:
        return None
    try:
        r = Path(line).expanduser().resolve()
        if _dir_is_plausible_root(r):
            return r
    except OSError:
        pass
    try:
        _persist_file().unlink()
    except OSError:
        pass
    return None


def _save_persisted_root(r: Path) -> None:
    try:
        rp = r.resolve()
        if not rp.is_dir():
            return
        f = _persist_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("v2\n" + str(rp) + "\n", encoding="utf-8")
    except OSError:
        pass


def _find_anchor_root(start: Path) -> Path | None:
    """往上找「與 .pyw 同一層」的專案根：任一啟動 .pyw 所在目錄。"""
    d = start.resolve()
    for _ in range(16):
        try:
            for name in _ANCHOR_LAUNCHERS:
                if (d / name).is_file():
                    return d
        except OSError:
            pass
        parent = d.parent
        if parent == d:
            break
        d = parent
    return None


def _maybe_copy_missing_sidecars(exe_dir: Path, anchor: Path) -> list[str]:
    """
    若專案根尚無設定檔，但 exe 目錄有（先前誤寫入的），只補拷「目標不存在」的檔案，不覆蓋你的登入設定。
    """
    copied: list[str] = []
    for name in ("config.yaml", "sponsorship_data.db"):
        src = exe_dir / name
        dst = anchor / name
        try:
            if src.is_file() and not dst.exists():
                shutil.copy2(src, dst)
                copied.append(name)
        except OSError:
            pass
    return copied


def _resolve_best_config_root(start: Path) -> Path | None:
    """僅作備援：多個 config.yaml 時取路徑層數最少者。"""
    candidates: list[Path] = []
    d = start.resolve()
    for _ in range(16):
        try:
            if (d / "config.yaml").is_file():
                candidates.append(d)
        except OSError:
            pass
        parent = d.parent
        if parent == d:
            break
        d = parent
    if not candidates:
        return None
    return min(candidates, key=lambda p: (len(p.parts), str(p)))


def _frozen_pick_root() -> Path:
    exe_dir = _frozen_exe_dir()
    cwd = Path.cwd().resolve()

    log_lines = [
        f"frozen=1 executable={sys.executable}",
        f"exe_dir={exe_dir}",
        f"cwd={cwd}",
    ]

    anchor = _find_anchor_root(exe_dir) or _find_anchor_root(cwd)
    log_lines.append(f"anchor_pyw_root={anchor}")

    if anchor is not None:
        copied = _maybe_copy_missing_sidecars(exe_dir, anchor)
        if copied:
            log_lines.append(f"migrated_from_exe_dir={copied}")
        _save_persisted_root(anchor)
        log_lines.append(f"final={anchor} (anchor launcher)")
        _debug_log(log_lines)
        return anchor

    persisted = _load_persisted_root_candidate()
    from_exe = _resolve_best_config_root(exe_dir)
    from_cwd = _resolve_best_config_root(cwd)

    opts: list[Path] = []
    for p in (persisted, from_exe, from_cwd):
        if p is None:
            continue
        try:
            if p.is_dir() and (p / "config.yaml").is_file():
                opts.append(p.resolve())
        except OSError:
            continue

    log_lines += [
        f"persisted={persisted}",
        f"from_exe={from_exe}",
        f"from_cwd={from_cwd}",
        f"opts={[str(x) for x in opts]}",
    ]

    if not opts:
        log_lines.append(f"final={exe_dir} (fallback, no anchor / no config chain)")
        _debug_log(log_lines)
        return exe_dir

    final = min(set(opts), key=lambda p: (len(p.parts), str(p)))
    _save_persisted_root(final)
    log_lines.append(f"final={final} (fallback min-depth)")
    _debug_log(log_lines)
    return final


def project_root() -> Path:
    global _cached_root
    if _cached_root is not None:
        return _cached_root

    if getattr(sys, "frozen", False):
        raw = (os.environ.get(_ENV_ROOT) or "").strip()
        if raw:
            p = Path(raw).expanduser().resolve()
            if p.is_dir():
                _cached_root = p
                return p
        r = _frozen_pick_root()
        _cached_root = r
        return r

    r = Path(__file__).resolve().parent.parent
    _cached_root = r
    return r
