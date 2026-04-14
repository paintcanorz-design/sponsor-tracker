"""Fantia 贊助額取得 - 使用 Session Cookie 爬取創作者後台

注意：Fantia 無官方 API，需從瀏覽器取得 _session_id。
取得方式：登入 fantia.jp -> F12 -> Application -> Cookies -> 複製 _session_id
"""
import re
import requests
from typing import Optional


class FantiaFetcher:
    """Fantia 創作者後台爬取"""

    BASE_URL = "https://fantia.jp"

    def __init__(self, session_id: str):
        """session_id: 瀏覽器的 _session_id cookie 值"""
        self.session_id = session_id

    def _headers(self):
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/",
        }

    def _get_session(self) -> requests.Session:
        """建立帶 cookie 的 session（同時設 fantia.jp 與 .fantia.jp）"""
        s = requests.Session()
        s.cookies.set("_session_id", self.session_id, domain="fantia.jp")
        s.cookies.set("_session_id", self.session_id, domain=".fantia.jp")
        s.headers.update(self._headers())
        return s

    DASHBOARD_URL = "https://fantia.jp/mypage/fanclubs/creator_dashboard"

    def _try_scrape_dashboard(self) -> Optional[dict]:
        """
        爬取創作者儀表板 https://fantia.jp/mypage/fanclubs/creator_dashboard
        提取：全体売上 (總銷售額)、プラン加入総数 (方案加入總數)
        """
        session = self._get_session()
        try:
            resp = session.get(self.DASHBOARD_URL, timeout=18, allow_redirects=True)
            if resp.status_code != 200:
                return None
            # 若被導向登入頁則 session 無效
            if "/sessions/signin" in resp.url or "ログイン" in resp.text[:2000]:
                return None
            text = resp.text
            amount = None
            patron_count = None
            # 全体売上：¥36,880、前月比較 等
            for p in [
                r'全体売上[^¥\d]*¥?\s*([\d,]+)',
                r'全体売上.*?([\d,]+)\s*円',
                r'([\d,]+)\s*円\s*※前月',
                r'"total_sales"\s*:\s*(\d+(?:\.\d+)?)',
                r'¥\s*([\d,]+)',
            ]:
                m = re.search(p, text, re.DOTALL)
                if m:
                    try:
                        v = float(m.group(1).replace(",", ""))
                        if 100 <= v < 1e10:
                            amount = v
                            break
                    except ValueError:
                        pass
            # プラン加入総数／会員数／加入数（儀表板用語可能變動，多種 pattern）
            for p in [
                r'プラン加入総数[^\d]*(\d+)',
                r'プラン加入.*?(\d+)\s*※',
                r'"plan_subscriptions"\s*:\s*(\d+)',
                r'加入総数[^\d]*(\d+)',
                r'会員数[^\d]*(\d+)',
                r'加入数[^\d]*(\d+)',
                r'ファンクラブ.*?(\d+)\s*人',
                r'メンバー[^\d]*(\d+)',
                r'"member_count"\s*:\s*(\d+)',
                r'"subscribers"\s*:\s*(\d+)',
                r'(\d+)\s*人\s*[（(]プラン',
                r'プラン.*?(\d+)\s*人',
                r'(\d+)\s*名',  # 75名
            ]:
                m = re.search(p, text, re.DOTALL if ".*?" in p else 0)
                if m:
                    try:
                        patron_count = int(m.group(1).replace(",", ""))
                        if patron_count >= 0:
                            break
                    except ValueError:
                        pass
            if amount is not None or patron_count is not None:
                creator_name = None
                for p in (
                    r'<meta\s+property="og:title"\s+content="([^"]+)"',
                    r"<title>([^<|]+)",
                ):
                    m = re.search(p, text, re.I)
                    if m:
                        creator_name = (m.group(1) or "").strip()
                        if creator_name:
                            break
                out = {
                    "amount": amount if amount is not None else 0,
                    "patron_count": patron_count,
                    "currency": "JPY",
                }
                if creator_name:
                    out["creator_name"] = creator_name
                return out
        except Exception:
            pass
        return None

    def fetch_sponsorship(self) -> Optional[dict]:
        """
        取得 Fantia 贊助數據。儀表板為 SPA，先試 Playwright 再試 requests。
        回傳: {"amount": float, "currency": str, "patron_count": int} 或 None
        """
        try:
            from .playwright_fallback import fantia_fetch_with_playwright
            result = fantia_fetch_with_playwright(self.session_id)
            if result:
                return result
        except Exception:
            pass
        result = self._try_scrape_dashboard()
        if result:
            return result
        return None
