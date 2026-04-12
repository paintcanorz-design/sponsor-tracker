"""Discord Incoming Webhook：排程更新偵測到贊助增加時通知。"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import requests

_DISCORD_HOSTS = frozenset(
    {
        "discord.com",
        "canary.discord.com",
        "ptb.discord.com",
        "discordapp.com",
    }
)


def is_discord_webhook_url(url: str) -> bool:
    s = (url or "").strip()
    if not s:
        return False
    try:
        p = urlparse(s)
    except Exception:
        return False
    if p.scheme != "https":
        return False
    if (p.hostname or "").lower() not in _DISCORD_HOSTS:
        return False
    return "/api/webhooks/" in (p.path or "")


def post_discord_webhook(webhook_url: str, content: str, *, timeout: float = 12.0) -> tuple[bool, str | None]:
    if not is_discord_webhook_url(webhook_url):
        return False, "非有效的 Discord Webhook 網址"
    payload = {"content": (content or "")[:2000]}
    try:
        r = requests.post(
            webhook_url,
            json=payload,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        if r.status_code in (200, 204):
            return True, None
        tail = (r.text or "")[:200]
        return False, f"HTTP {r.status_code}" + (f" {tail}" if tail else "")
    except Exception as e:
        return False, str(e)


def post_discord_webhook_long(webhook_url: str, content: str, *, timeout: float = 12.0) -> tuple[bool, str | None]:
    """內容可超過 2000 字元時拆成多則訊息送出（每則至多 2000）。"""
    if not is_discord_webhook_url(webhook_url):
        return False, "非有效的 Discord Webhook 網址"
    raw = content or ""
    if len(raw) <= 2000:
        return post_discord_webhook(webhook_url, raw, timeout=timeout)
    chunks: list[str] = []
    rest = raw[:32000]
    while rest:
        if len(rest) <= 2000:
            chunks.append(rest)
            break
        cut = rest.rfind("\n", 0, 2000)
        if cut < 800:
            cut = 2000
        chunks.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    last_err = None
    for part in chunks:
        ok, last_err = post_discord_webhook(webhook_url, part, timeout=timeout)
        if not ok:
            return False, last_err
    return True, None


_PLAT_LABEL = {"patreon": "Patreon", "fanbox": "Fanbox", "fantia": "Fantia"}


def format_scheduled_increase_message(
    *,
    time_jst: str,
    new_total_jpy: float,
    prev_total_jpy: float,
    increase_jpy: float,
    platform_before: dict[str, float],
    by_platform: list[dict[str, Any]],
    fx_usd_jpy: float | None,
) -> str:
    lines: list[str] = [
        "【贊助額追蹤】排程更新：偵測到贊助增加",
        f"時間：{time_jst}",
    ]
    if increase_jpy > 0:
        lines.append(f"折合日圓總額：較更新前 +¥{increase_jpy:,.0f}（目前約 ¥{new_total_jpy:,.0f}）")
    else:
        lines.append(f"折合日圓總額：約 ¥{new_total_jpy:,.0f}（總額換算變化受匯率等影響，但以下平台金額有上升）")

    bumped: list[str] = []
    for p in by_platform or []:
        plat = p.get("platform")
        if not plat:
            continue
        try:
            after_amt = float(p.get("amount") or 0)
        except (TypeError, ValueError):
            after_amt = 0.0
        try:
            before_amt = float(platform_before.get(plat) or 0)
        except (TypeError, ValueError):
            before_amt = 0.0
        if after_amt <= before_amt:
            continue
        cur = (p.get("currency") or "JPY").upper()
        label = _PLAT_LABEL.get(plat, plat)
        if cur == "USD" and fx_usd_jpy:
            b_j = before_amt * fx_usd_jpy
            a_j = after_amt * fx_usd_jpy
            bumped.append(
                f"- {label}：US${before_amt:,.2f} → US${after_amt:,.2f}（約 ¥{b_j:,.0f} → ¥{a_j:,.0f}）"
            )
        else:
            bumped.append(f"- {label}：¥{before_amt:,.0f} → ¥{after_amt:,.0f}")

    if bumped:
        lines.append("分平台：")
        lines.extend(bumped)

    return "\n".join(lines)


def format_daily_dashboard_report(
    stats: dict[str, Any],
    period: dict[str, Any] | None,
    *,
    time_jst: str,
) -> str:
    """與 GUI「經營總覽」對應的文字報表（時間為日本標準時 JST）。"""
    lines: list[str] = [
        "【贊助額追蹤】每日總覽報表",
        f"時間：{time_jst}",
        "———",
    ]
    total = float(stats.get("total_amount") or 0)
    lines.append(f"總收益（折合日圓）：¥{total:,.0f}")
    ch = stats.get("change_vs_yesterday")
    pct = stats.get("change_pct_vs_yesterday")
    if ch is not None and pct is not None:
        lines.append(f"較昨日：{ch:+,.0f}（{pct:+.1f}%）")
    elif ch is not None:
        lines.append(f"較昨日：{ch:+,.0f}")

    patrons = int(stats.get("total_patron_count") or 0)
    pch = stats.get("patron_change")
    if pch is not None:
        lines.append(f"贊助人數：{patrons:,} 人（較昨日 {pch:+d} 人）")
    else:
        lines.append(f"贊助人數：{patrons:,} 人")

    inc = float(stats.get("increase_amount") or 0)
    dec = float(stats.get("decrease_amount") or 0)
    lines.append(f"昨日區間變動｜增加 +¥{inc:,.0f}　減少 {dec:,.0f}")

    if period:
        d = int(period.get("days") or 7)
        c2 = period.get("change_amount")
        pct2 = period.get("change_percent")
        if c2 is not None:
            tail = f"（{pct2:+.1f}%）" if pct2 is not None else ""
            lines.append(f"本週較上週（近 {d} 天合計 vs 前 {d} 天）：{c2:+,.0f}{tail}")

    lines.append("———")
    lines.append("各平台：")
    for p in stats.get("by_platform") or []:
        plat = p.get("platform") or "?"
        label = _PLAT_LABEL.get(plat, plat)
        amt = float(p.get("amount") or 0)
        cur = (p.get("currency") or "JPY").upper()
        pc = int(p.get("patron_count") or 0)
        seg = f"- {label}：{amt:,.2f} {cur}　{pc:,} 人"
        if p.get("change_amount") is not None:
            c3 = float(p["change_amount"])
            pp = p.get("change_percent")
            seg += f"　日變 {c3:+,.0f}"
            if pp is not None:
                seg += f"（{pp:+.1f}%）"
        lines.append(seg)

    return "\n".join(lines)
