"""日本標準時 Asia/Tokyo：業務「今日」、顯示時間、報表日期範圍。"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


def now_jst() -> datetime:
    return datetime.now(JST)


def today_jst_str() -> str:
    return now_jst().strftime("%Y-%m-%d")


def yesterday_jst_str() -> str:
    return (now_jst().date() - timedelta(days=1)).isoformat()


def date_days_ago_jst(days: int) -> str:
    """今天往前推 N 天（日曆日，日本）。"""
    return (now_jst().date() - timedelta(days=max(0, int(days)))).strftime("%Y-%m-%d")


def month_start_jst_str() -> str:
    """目前月份一號 YYYY-MM-DD（JST）。"""
    d = now_jst().date()
    return d.replace(day=1).isoformat()


def year_start_jst_str() -> str:
    """目前 JST 年份一月一日 YYYY-MM-DD。"""
    d = now_jst().date()
    return d.replace(month=1, day=1).isoformat()
