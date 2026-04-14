"""Discord Incoming Webhook：排程更新���助增加時通知。"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import requests

from src.i18n import get_language, translate

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


def post_discord_webhook(
    webhook_url: str, content: str, *, timeout: float = 12.0, lang: str | None = None
) -> tuple[bool, str | None]:
    if not is_discord_webhook_url(webhook_url):
        return False, translate(lang or get_language(), "post.invalid")
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


def post_discord_webhook_long(
    webhook_url: str, content: str, *, timeout: float = 12.0, lang: str | None = None
) -> tuple[bool, str | None]:
    """��容可超過 2000 字元時拆成�息送出（每��至多 2000）。"""
    if not is_discord_webhook_url(webhook_url):
        return False, translate(lang or get_language(), "post.invalid")
    raw = content or ""
    if len(raw) <= 2000:
        return post_discord_webhook(webhook_url, raw, timeout=timeout, lang=lang)
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
        ok, last_err = post_discord_webhook(webhook_url, part, timeout=timeout, lang=lang)
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
    lang: str | None = None,
) -> str:
    lg = lang or get_language()
    lines: list[str] = [
        translate(lg, "scheduled.increase.title"),
        translate(lg, "scheduled.increase.time", t=time_jst),
    ]
    if increase_jpy > 0:
        lines.append(
            translate(
                lg,
                "scheduled.increase.line_pos",
                inc=increase_jpy,
                total=new_total_jpy,
            )
        )
    else:
        lines.append(translate(lg, "scheduled.increase.line_mix", total=new_total_jpy))

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
                translate(
                    lg,
                    "scheduled.bump_usd",
                    label=label,
                    b=before_amt,
                    a=after_amt,
                    bj=b_j,
                    aj=a_j,
                )
            )
        else:
            bumped.append(
                translate(lg, "scheduled.bump_jpy", label=label, b=before_amt, a=after_amt)
            )

    if bumped:
        lines.append(translate(lg, "scheduled.increase.by_plat"))
        lines.extend(bumped)

    return "\n".join(lines)


def format_daily_dashboard_report(
    stats: dict[str, Any],
    period: dict[str, Any] | None,
    *,
    time_jst: str,
    lang: str | None = None,
) -> str:
    """�� GUI「��������」對��的文字報表（時間為日本標準時 JST）。"""
    lg = lang or get_language()
    lines: list[str] = [
        translate(lg, "daily.title"),
        translate(lg, "daily.time", t=time_jst),
        "———",
    ]
    total = float(stats.get("total_amount") or 0)
    lines.append(translate(lg, "daily.total", total=total))
    ch = stats.get("change_vs_yesterday")
    pct = stats.get("change_pct_vs_yesterday")
    if ch is not None and pct is not None:
        lines.append(translate(lg, "daily.vs_yday", ch=ch, pct=pct))
    elif ch is not None:
        lines.append(translate(lg, "daily.vs_yday_amt", ch=ch))

    patrons = int(stats.get("total_patron_count") or 0)
    pch = stats.get("patron_change")
    if pch is not None:
        lines.append(translate(lg, "daily.patrons", n=patrons, pch=pch))
    else:
        lines.append(translate(lg, "daily.patrons_only", n=patrons))

    inc = float(stats.get("increase_amount") or 0)
    dec = float(stats.get("decrease_amount") or 0)
    lines.append(translate(lg, "daily.delta", inc=inc, dec=dec))

    if period:
        d = int(period.get("days") or 7)
        c2 = period.get("change_amount")
        pct2 = period.get("change_percent")
        if c2 is not None:
            tail = translate(lg, "daily.plat_pct", p=pct2) if pct2 is not None else ""
            lines.append(translate(lg, "daily.week", d=d, c=c2, tail=tail))

    lines.append("———")
    lines.append(translate(lg, "daily.plat_head"))
    for p in stats.get("by_platform") or []:
        plat = p.get("platform") or "?"
        label = _PLAT_LABEL.get(plat, plat)
        amt = float(p.get("amount") or 0)
        cur = (p.get("currency") or "JPY").upper()
        pc = int(p.get("patron_count") or 0)
        people = translate(lg, "common.people")
        seg = translate(lg, "daily.plat_line", label=label, amt=amt, cur=cur, pc=pc)
        if people:
            seg = f"{seg} {people}"
        if p.get("change_amount") is not None:
            c3 = float(p["change_amount"])
            pp = p.get("change_percent")
            seg += translate(lg, "daily.plat_chg", c=c3)
            if pp is not None:
                seg += translate(lg, "daily.plat_pct", p=pp)
        lines.append(seg)

    return "\n".join(lines)
