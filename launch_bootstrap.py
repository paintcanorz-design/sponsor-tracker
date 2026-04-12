"""Windows: 若目前解譯器缺 PyYAML 且非 3.11，改以 pyw/py -3.11 重啟（與啟動圖形介面.bat 一致）。"""
import os
import shutil
import subprocess
import sys
from pathlib import Path


def maybe_relaunch_with_py311(script_path: Path, root: Path) -> None:
    if getattr(sys, "frozen", False):
        return
    if sys.platform != "win32":
        return
    if sys.version_info[:2] == (3, 11):
        return
    try:
        import yaml  # noqa: F401

        return
    except ImportError:
        pass

    script_path = script_path.resolve()
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")

    pyw_exe = shutil.which("pyw")
    if pyw_exe:
        subprocess.Popen([pyw_exe, "-3.11", os.fspath(script_path)], cwd=root, env=env)
        raise SystemExit(0)

    py_exe = shutil.which("py")
    if py_exe:
        kwargs: dict = {"cwd": root, "env": env}
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.Popen([py_exe, "-3.11", os.fspath(script_path)], **kwargs)
        raise SystemExit(0)
