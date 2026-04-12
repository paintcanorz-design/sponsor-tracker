# -*- coding: utf-8 -*-
"""Qt GUI shared: config, palette, sound (no CustomTkinter)."""
import io
import struct
import sys
import wave
from pathlib import Path

import yaml

from src.paths import project_root

CONFIG_PATH = project_root() / "config.yaml"

_INCREASE_SOUND_LABEL_TO_KEY = {
    "\u7121": "none",
    "\u661f\u865f\uff08\u9810\u8a2d\uff09": "asterisk",
    "\u932f\u8aa4": "hand",
    "\u63d0\u793a\u97f3": "alert_bundle",
}
_INCREASE_SOUND_KEY_TO_LABEL = {v: k for k, v in _INCREASE_SOUND_LABEL_TO_KEY.items()}
INCREASE_SOUND_PRESET_LABELS = list(_INCREASE_SOUND_LABEL_TO_KEY.keys())

_REMOVED_INCREASE_SOUND_PRESETS = frozenset({"exclamation", "question", "ok"})


def normalize_increase_sound_key(raw: str | None) -> str:
    k = (raw or "asterisk").strip().lower()
    if k in _REMOVED_INCREASE_SOUND_PRESETS:
        return "asterisk"
    return k

_PALETTE_LIGHT: dict[str, str] = {
    "bg": "#ebedf0",
    "bg_grouped": "#ebedf0",
    "bg_sidebar": "#fbfbfc",
    "bg_card": "#ffffff",
    "bg_card_hover": "#f5f6f8",
    "bg_elevated": "#f6f7f9",
    "border": "#c7c7cc",
    "border_light": "#d1d1d6",
    "hairline": "#c6c6c8",
    "text": "#1c1c1e",
    "text_secondary": "#636366",
    "text_tertiary": "#8e8e93",
    "accent": "#0a84ff",
    "accent_hover": "#0071e3",
    "accent_soft": "#e8f1ff",
    "dash_hero_top": "#e3eefc",
    "dash_hero_bottom": "#ffffff",
    "segment_bg": "#d8d8dc",
    "segment_hover": "#f2f2f7",
    "success": "#34c759",
    "warning": "#ff9500",
    "error": "#ff3b30",
    "patreon": "#ff375f",
    "fanbox": "#0a84ff",
    "fantia": "#bf5af2",
}

_PALETTE_DARK: dict[str, str] = {
    "bg": "#161618",
    "bg_grouped": "#161618",
    "bg_sidebar": "#1e1e20",
    "bg_card": "#232326",
    "bg_card_hover": "#2e2e32",
    "bg_elevated": "#2a2a2e",
    "border": "#4a4a50",
    "border_light": "#3a3a3e",
    "hairline": "#2e2e32",
    "text": "#f5f5f7",
    "text_secondary": "#a1a1a6",
    "text_tertiary": "#7c7c82",
    "accent": "#0a84ff",
    "accent_hover": "#409cff",
    "accent_soft": "#0a84ff18",
    "dash_hero_top": "#1a2a3d",
    "dash_hero_bottom": "#232326",
    "segment_bg": "#2a2a2e",
    "segment_hover": "#363639",
    "success": "#30d158",
    "warning": "#ff9f0a",
    "error": "#ff453a",
    "patreon": "#ff375f",
    "fanbox": "#0a84ff",
    "fantia": "#bf5af2",
}

PALETTE: dict[str, str] = {}

def qt_theme_mode() -> str:
    """App is dark-only; kept for call sites that branch on chart theme."""
    return "dark"


def palette_apply(_mode: str | None = None) -> None:
    """Always use the dark palette (light theme removed)."""
    PALETTE.clear()
    PALETTE.update(_PALETTE_DARK)


palette_apply()

if sys.platform == "win32":
    FONT_FALLBACKS = ["Segoe UI Variable Text", "Segoe UI", "Microsoft JhengHei UI"]
elif sys.platform == "darwin":
    FONT_FALLBACKS = ["PingFang TC", "Helvetica Neue", "Heiti TC"]
else:
    FONT_FALLBACKS = ["Noto Sans CJK TC", "Noto Sans"]

FONT_FAMILY = FONT_FALLBACKS[0]


def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def save_config(config: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def parse_jst_hhmm(raw: str) -> tuple[int, int] | None:
    s = (raw or "").strip().replace("：", ":")
    if not s:
        return None
    parts = s.split(":")
    if len(parts) != 2:
        return None
    try:
        h = int(parts[0].strip())
        m = int(parts[1].strip())
    except ValueError:
        return None
    if h < 0 or h > 23 or m < 0 or m > 59:
        return None
    return h, m


def bundled_alert_wav_path() -> Path:
    return project_root() / "alert.wav.wav"


def bundled_alert_wav_candidates() -> list[Path]:
    """Search project root, config directory, then frozen exe dir for alert.wav.wav."""
    roots: list[Path] = []
    for r in (project_root(), CONFIG_PATH.parent):
        try:
            roots.append(r.resolve())
        except OSError:
            roots.append(r)
    if getattr(sys, "frozen", False):
        try:
            roots.append(Path(sys.executable).resolve().parent)
        except OSError:
            pass
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            try:
                roots.append(Path(meipass))
            except OSError:
                pass
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        key = str(r)
        if key in seen:
            continue
        seen.add(key)
        p = r / "alert.wav.wav"
        try:
            if p.is_file():
                out.append(p.resolve())
        except OSError:
            continue
    return out


def _resolve_increase_sound_wav_path(raw: str) -> Path | None:
    s = (raw or "").strip()
    if not s:
        return None
    p = Path(s)
    if not p.is_absolute():
        p = CONFIG_PATH.parent / p
    return p if p.is_file() and p.suffix.lower() == ".wav" else None


def _gui_increase_sound_volume_01(gui: dict) -> float:
    raw = (gui or {}).get("increase_sound_volume", 100)
    try:
        x = float(raw)
    except (TypeError, ValueError):
        x = 100.0
    return max(0.0, min(1.0, x / 100.0))


def _wav_scaled_to_memory(wav_path: Path, volume_01: float) -> bytes | None:
    v = max(0.0, min(1.0, volume_01))
    try:
        with wave.open(str(wav_path), "rb") as rd:
            if rd.getcomptype() != "NONE":
                return None
            nch = rd.getnchannels()
            sw = rd.getsampwidth()
            fr = rd.getframerate()
            raw = rd.readframes(rd.getnframes())
    except Exception:
        return None
    if nch < 1 or sw not in (1, 2):
        return None
    if sw == 1:
        out = bytes(max(0, min(255, int(round(b * v)))) for b in raw)
    else:
        n = len(raw) // 2
        fmt = "<" + "h" * n
        samples = struct.unpack(fmt, raw)
        out = struct.pack(fmt, *[max(-32768, min(32767, int(round(s * v)))) for s in samples])
    buf = io.BytesIO()
    try:
        with wave.open(buf, "wb") as wr:
            wr.setnchannels(nch)
            wr.setsampwidth(sw)
            wr.setframerate(fr)
            wr.setcomptype("NONE", "not compressed")
            wr.writeframes(out)
        return buf.getvalue()
    except Exception:
        return None


def _winsound_play_wav_file(wav_path: Path, vol01: float) -> bool:
    """Windows: if in-memory PlaySound fails, fall back to playing the file path."""
    try:
        import winsound

        wav_path = wav_path.resolve()
    except Exception:
        return False
    if vol01 < 0.999:
        blob = _wav_scaled_to_memory(wav_path, vol01)
        if blob:
            try:
                winsound.PlaySound(blob, winsound.SND_MEMORY | winsound.SND_ASYNC)
                return True
            except Exception:
                pass
    try:
        winsound.PlaySound(str(wav_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    except Exception:
        return False


def _qt_play_wav_file(wav_path: Path, vol01: float) -> bool:
    """Qt Multimedia fallback when winsound cannot play the WAV."""
    try:
        from PySide6.QtCore import QTimer, QUrl
        from PySide6.QtMultimedia import QSoundEffect
        from PySide6.QtWidgets import QApplication
    except Exception:
        return False
    app = QApplication.instance()
    if app is None:
        return False
    try:
        try:
            wav_path = wav_path.resolve(strict=False)
        except TypeError:
            wav_path = wav_path.resolve()
    except Exception:
        pass
    if not wav_path.is_file():
        return False
    try:
        eff = QSoundEffect(app)
        eff.setSource(QUrl.fromLocalFile(str(wav_path)))
        if eff.status() == QSoundEffect.Status.Error:
            eff.deleteLater()
            return False
        eff.setVolume(max(0.0, min(1.0, float(vol01))))
        started = False

        def _try_play() -> None:
            nonlocal started
            if started or not eff.isLoaded():
                return
            started = True
            eff.play()

        eff.loadedChanged.connect(_try_play)
        _try_play()
        QTimer.singleShot(400, _try_play)

        QTimer.singleShot(5000, eff.deleteLater)
        return True
    except Exception:
        return False


def play_increase_sound(config: dict | None = None):
    cfg = config or {}
    gui = cfg.get("gui") or {}
    vol01 = _gui_increase_sound_volume_01(gui)
    if vol01 <= 0:
        return

    wav_path = _resolve_increase_sound_wav_path(gui.get("increase_sound_wav") or "")
    preset = normalize_increase_sound_key(gui.get("increase_sound"))
    if wav_path is None and preset == "alert_bundle":
        cands = bundled_alert_wav_candidates()
        if cands:
            wav_path = cands[0]

    if wav_path is not None:
        if _qt_play_wav_file(wav_path, vol01):
            return
        if sys.platform == "win32" and _winsound_play_wav_file(wav_path, vol01):
            return

    if preset in ("none", "off", "0", "false"):
        return
    if preset == "alert_bundle":
        return

    try:
        if sys.platform == "win32":
            import winsound

            _map = {
                "asterisk": winsound.MB_ICONASTERISK,
                "exclamation": winsound.MB_ICONEXCLAMATION,
                "hand": winsound.MB_ICONHAND,
                "error": winsound.MB_ICONHAND,
                "question": winsound.MB_ICONQUESTION,
                "ok": winsound.MB_OK,
                "default": winsound.MB_OK,
            }
            winsound.MessageBeep(_map.get(preset, winsound.MB_ICONASTERISK))
        else:
            print("\a", end="", flush=True)
    except Exception:
        pass


def detach_windows_console_if_present() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        if kernel32.GetConsoleWindow():
            kernel32.FreeConsole()
    except Exception:
        pass
