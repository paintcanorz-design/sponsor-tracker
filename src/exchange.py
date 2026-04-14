# -*- coding: utf-8 -*-
"""USD-based FX: Patreon JPY conversion and UI rates (daily cache in config gui.fx_daily)."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

from src.jst import today_jst_str

JST = ZoneInfo("Asia/Tokyo")

_CACHE: dict[str, Any] = {"rate": None, "date_jst": None}


def _fetch_usd_jpy_twd() -> tuple[float, float] | None:
    try:
        r = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        rates = data.get("rates") or {}
        jpy = float(rates.get("JPY") or 0)
        twd = float(rates.get("TWD") or 0)
        if jpy > 0 and twd > 0:
            return jpy, twd
    except Exception:
        pass
    return None


def _sync_process_cache_from_gui(gui: dict) -> None:
    fd = gui.get("fx_daily") or {}
    if fd.get("date_jst") and float(fd.get("usd_jpy") or 0) > 0:
        _CACHE["rate"] = float(fd["usd_jpy"])
        _CACHE["date_jst"] = str(fd["date_jst"])


def get_usd_jpy_rate() -> float:
    """USD/JPY: use in-memory cache for the JST day, else one API fetch (legacy path)."""
    today_jst = datetime.now(JST).date().isoformat()
    if _CACHE["rate"] is not None and _CACHE.get("date_jst") == today_jst:
        return float(_CACHE["rate"])
    pair = _fetch_usd_jpy_twd()
    if pair:
        uj, _ut = pair
        _CACHE["rate"] = uj
        _CACHE["date_jst"] = today_jst
        return uj
    return float(_CACHE["rate"] or 150.0)


def sync_fx_cache_from_config(config: dict) -> None:
    """After load_config: align process USD/JPY cache with gui.fx_daily if present."""
    _sync_process_cache_from_gui(config.setdefault("gui", {}))


def ensure_fx_daily(config: dict) -> None:
    """
    At most once per JST calendar day: refresh gui.fx_daily when the first data update runs.
    If the API fails, keep the previous fx_daily (may be from the prior day).
    """
    today = today_jst_str()
    gui = config.setdefault("gui", {})
    fd = gui.get("fx_daily") or {}
    uj0 = float(fd.get("usd_jpy") or 0)
    ut0 = float(fd.get("usd_twd") or 0)
    if fd.get("date_jst") == today and uj0 > 0 and ut0 > 0:
        _sync_process_cache_from_gui(gui)
        return
    pair = _fetch_usd_jpy_twd()
    if pair:
        uj, ut = pair
        gui["fx_daily"] = {"date_jst": today, "usd_jpy": uj, "usd_twd": ut}
        _CACHE["rate"] = uj
        _CACHE["date_jst"] = today
    else:
        _sync_process_cache_from_gui(gui)
