# -*- coding: utf-8 -*-
"""Display amounts in JPY / TWD / USD using daily FX cached in config (gui.fx_daily)."""
from __future__ import annotations


def fx_dict_from_config(config: dict) -> dict:
    gui = config.get("gui") or {}
    fd = gui.get("fx_daily") or {}
    uj = float(fd.get("usd_jpy") or 150)
    ut = float(fd.get("usd_twd") or 31)
    if uj <= 0:
        uj = 150.0
    if ut <= 0:
        ut = 31.0
    return {"usd_jpy": uj, "usd_twd": ut, "twd_jpy": uj / ut}


def display_currency_code(config: dict) -> str:
    raw = (config.get("gui") or {}).get("display_currency")
    s = str(raw if raw is not None else "jpy").strip().lower()
    return s if s in ("jpy", "twd", "usd") else "jpy"


def jpy_to_display_amount(jpy: float, code: str, fx: dict) -> float:
    c = (code or "jpy").lower()
    j = float(jpy)
    if c == "jpy":
        return j
    uj = float(fx.get("usd_jpy") or 150)
    tj = float(fx.get("twd_jpy") or 0)
    if tj <= 0:
        ut = float(fx.get("usd_twd") or 31)
        tj = uj / ut if ut else j
    if c == "usd":
        return j / uj
    if c == "twd":
        return j / tj
    return j


def format_money_jpy_as_display(
    jpy: float,
    config: dict,
    *,
    signed: bool = False,
    decimals: int | None = None,
) -> str:
    code = display_currency_code(config)
    fx = fx_dict_from_config(config)
    v = jpy_to_display_amount(jpy, code, fx)
    if decimals is None:
        decimals = 2 if code == "usd" else 0
    if signed:
        if code == "jpy":
            return f"\u00a5{v:+,.{decimals}f}"
        if code == "twd":
            return f"NT${v:+,.{decimals}f}"
        return f"${v:+,.{decimals}f}"
    if code == "jpy":
        return f"\u00a5{v:,.{decimals}f}"
    if code == "twd":
        return f"NT${v:,.{decimals}f}"
    return f"${v:,.{decimals}f}"


def platform_native_to_jpy(
    amount: float, platform: str, currency: str, usd_jpy: float
) -> float:
    amt = float(amount or 0)
    cur = (currency or "JPY").strip().upper()
    if platform == "patreon" and cur == "USD":
        return amt * float(usd_jpy or 150)
    return amt
