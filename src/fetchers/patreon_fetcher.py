"""Patreon 贊助額取得 - 使用網頁爬取（需瀏覽器登入取得 cookies）"""
from typing import Optional


class PatreonFetcher:
    """Patreon 創作者後台爬取（與 Fanbox/Fantia 相同，登入後抓取）"""

    def __init__(self, cookies: str, creator_page: str = None):
        """
        cookies: 瀏覽器登入後取得的 cookie 字串
        creator_page: 創作者頁面 URL，例如 https://www.patreon.com/c/paintcan
        """
        self.cookies = (cookies or "").strip()
        self.creator_page = (creator_page or "").strip() or None

    def fetch_sponsorship(self) -> Optional[dict]:
        """
        取得 Patreon 贊助總額
        回傳: {"amount": float, "currency": str, "patron_count": int} 或 None
        """
        if not self.cookies:
            return None
        try:
            from .playwright_fallback import patreon_fetch_with_playwright
            return patreon_fetch_with_playwright(self.cookies, self.creator_page)
        except Exception:
            return None
