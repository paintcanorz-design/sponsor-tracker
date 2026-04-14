# -*- coding: utf-8 -*-
"""Runtime i18n: load string table, resolve language, format helpers."""
from __future__ import annotations

import locale
import re
import sys
from typing import Any

from src.i18n_table import MESSAGES

LANG_ZH_TW = "zh_TW"
LANG_EN = "en"
LANG_JA = "ja"
SUPPORTED_LANGS = (LANG_ZH_TW, LANG_EN, LANG_JA)

SCHEDULE_INTERVAL_MINUTES: dict[str, int] = {
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
}

_LEGACY_SCHEDULE_INTERVAL: dict[str, str] = {
    "15 \u5206\u9418": "15m",
    "30 \u5206\u9418": "30m",
    "1 \u5c0f\u6642": "1h",
    "2 \u5c0f\u6642": "2h",
    "4 \u5c0f\u6642": "4h",
}

INCREASE_SOUND_KEYS: tuple[str, ...] = ("none", "asterisk", "hand", "alert_bundle")

_current: str = LANG_ZH_TW


def get_language() -> str:
    return _current


def set_language(code: str) -> None:
    global _current
    c = (code or LANG_ZH_TW).strip()
    if c not in SUPPORTED_LANGS:
        c = LANG_ZH_TW
    _current = c


def translate(lang: str, key: str, **kwargs: Any) -> str:
    lang = lang if lang in SUPPORTED_LANGS else LANG_ZH_TW
    bag = MESSAGES.get(lang) or {}
    s = bag.get(key)
    if s is None:
        s = MESSAGES.get(LANG_EN, {}).get(key) or MESSAGES.get(LANG_ZH_TW, {}).get(key) or key
    if kwargs:
        try:
            return s.format(**kwargs)
        except (KeyError, ValueError):
            return s
    return s


def tr(key: str, **kwargs: Any) -> str:
    return translate(get_language(), key, **kwargs)


def _qlocale_system_name() -> str:
    try:
        from PySide6.QtCore import QLocale

        return (QLocale.system().name() or "").lower().replace("-", "_")
    except Exception:
        return ""


def system_language_guess() -> str:
    qn = _qlocale_system_name()
    if qn.startswith("ja"):
        return LANG_JA
    if qn.startswith("en"):
        return LANG_EN
    if qn.startswith("zh"):
        return LANG_ZH_TW
    try:
        loc = locale.getdefaultlocale()[0]
        if loc:
            low = loc.lower()
            if low.startswith("ja"):
                return LANG_JA
            if low.startswith("en"):
                return LANG_EN
            if low.startswith("zh"):
                return LANG_ZH_TW
    except Exception:
        pass
    return LANG_ZH_TW


def normalize_ui_language_raw(raw: str | None) -> str:
    s = (raw or "auto").strip().lower().replace("-", "_")
    if s in ("", "auto", "system"):
        return "auto"
    if s in ("zh_tw", "zh_hant", "cht", "zh_cn_traditional"):
        return LANG_ZH_TW
    if s in ("en", "en_us", "en_gb"):
        return LANG_EN
    if s in ("ja", "ja_jp"):
        return LANG_JA
    return "auto"


def effective_ui_language(config: dict | None) -> str:
    gui = (config or {}).get("gui") or {}
    raw = gui.get("ui_language", gui.get("language", "auto"))
    norm = normalize_ui_language_raw(str(raw))
    if norm == "auto":
        return system_language_guess()
    return norm


def normalize_schedule_interval_id(raw: str | None) -> str:
    s = (raw or "1h").strip()
    if s in SCHEDULE_INTERVAL_MINUTES:
        return s
    if s in _LEGACY_SCHEDULE_INTERVAL:
        return _LEGACY_SCHEDULE_INTERVAL[s]
    m = re.match(r"^(\d+)\s*m$", s, re.I)
    if m and f"{m.group(1)}m" in SCHEDULE_INTERVAL_MINUTES:
        return f"{m.group(1)}m"
    return "1h"


def schedule_interval_label(interval_id: str) -> str:
    iid = normalize_schedule_interval_id(interval_id)
    return tr(f"sched.{iid}")


def increase_sound_label(key: str) -> str:
    k = (key or "asterisk").strip().lower()
    if k not in INCREASE_SOUND_KEYS:
        k = "asterisk"
    return tr(f"sound.{k}")


def migrate_config_schedule_interval(config: dict) -> bool:
    """Normalize gui.schedule_interval to id keys (15m, 1h, ...). Returns True if changed."""
    gui = config.setdefault("gui", {})
    raw = gui.get("schedule_interval")
    nid = normalize_schedule_interval_id(str(raw) if raw is not None else "1h")
    if raw != nid:
        gui["schedule_interval"] = nid
        return True
    return False
