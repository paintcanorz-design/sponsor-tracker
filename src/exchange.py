"""USD → JPY 現價匯率（每天更新一次，供儀表板與總額換算）"""
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

JST = ZoneInfo("Asia/Tokyo")

_CACHE = {"rate": None, "date_jst": None}


def get_usd_jpy_rate() -> float:
    """取得 USD/JPY 匯率，失敗時回傳 150 作為 fallback"""
    today_jst = datetime.now(JST).date().isoformat()
    if _CACHE["rate"] is not None and _CACHE.get("date_jst") == today_jst:
        return _CACHE["rate"]
    try:
        r = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=10)
        if r.status_code == 200:
            data = r.json()
            rate = float(data.get("rates", {}).get("JPY", 150))
            if rate > 0:
                _CACHE["rate"] = rate
                _CACHE["date_jst"] = today_jst
                return rate
    except Exception:
        pass
    return _CACHE["rate"] or 150.0
