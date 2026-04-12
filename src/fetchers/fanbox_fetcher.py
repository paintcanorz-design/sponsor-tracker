"""Fanbox 贊助額取得 - 創作者後台為 SPA，需用 Playwright 載入後攔截 API 或讀取畫面"""
import re
import json
import requests
from typing import Optional

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class FanboxFetcher:
    """Fanbox 創作者後台：以 Playwright 取得收益數據（後台為 SPA，requests 拿不到）"""

    BASE_URL = "https://www.fanbox.cc"
    API_BASE = "https://api.fanbox.cc"

    def __init__(self, cookies: str):
        self.cookies = self._parse_cookies(cookies)

    def _parse_cookies(self, cookie_str: str) -> dict:
        result = {}
        for part in (cookie_str or "").strip().split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                result[k.strip()] = v.strip()
        return result

    def _try_api_with_cookie(self) -> Optional[dict]:
        """嘗試直接呼叫 api.fanbox.cc（部分端點需創作者登入）"""
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": self.BASE_URL,
            "Referer": f"{self.BASE_URL}/",
        })
        for k, v in self.cookies.items():
            session.cookies.set(k, v, domain=".fanbox.cc")
        # 創作者後台可能用的內部 API（名稱為推測）
        for path in ["/creator.get", "/creator.getPayoutSummary", "/payment.getTransferableAmount"]:
            try:
                r = session.get(self.API_BASE + path, timeout=10)
                if r.status_code != 200:
                    continue
                data = r.json()
                body = data.get("body") if isinstance(data, dict) else data
                if not body:
                    continue
                amount = None
                if isinstance(body, dict):
                    amount = body.get("transferableAmount") or body.get("monthlyAmount") or body.get("amount")
                    patron_count = body.get("supportingCount") or body.get("supporterCount") or body.get("patronCount")
                if amount is not None and float(amount) >= 1000:
                    return {"amount": float(amount), "currency": "JPY", "patron_count": int(patron_count) if patron_count is not None else None}
            except Exception:
                continue
        return None

    def _fetch_with_playwright(self) -> Optional[dict]:
        """用 Playwright 開創作者後台，攔截 API 回應或從畫面讀取數字"""
        if not PLAYWRIGHT_AVAILABLE:
            return None

        cookie_list = []
        for k, v in self.cookies.items():
            cookie_list.append({"name": k, "value": v, "domain": ".fanbox.cc", "path": "/"})
            cookie_list.append({"name": k, "value": v, "domain": ".pixiv.net", "path": "/"})
        if not self.cookies:
            return None

        captured = []  # 收集 api 回應 body

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            context.add_cookies(cookie_list)
            page = context.new_page()

            def on_response(response):
                url = response.url
                if "api.fanbox.cc" not in url and "fanbox.cc" not in url:
                    return
                try:
                    body = response.json()
                    captured.append(body)
                except Exception:
                    pass

            page.on("response", on_response)

            try:
                page.goto("https://www.fanbox.cc/manage/dashboard", wait_until="domcontentloaded", timeout=18000)
            except Exception:
                try:
                    page.goto("https://www.fanbox.cc/manage/payouts", wait_until="domcontentloaded", timeout=18000)
                except Exception:
                    try:
                        page.goto("https://www.fanbox.cc/manage", wait_until="domcontentloaded", timeout=15000)
                    except Exception:
                        browser.close()
                        return None

            # 若被導向登入頁表示 Cookie 無效
            if "/login" in page.url or "signin" in page.url.lower():
                browser.close()
                return None

            page.wait_for_timeout(3000)  # 等 SPA 打 API 載入數據

            # 從攔截到的 JSON 找 支援額 / 支援者数 / フォロワー数（只接受像總覽的數據，排除 0 元或小數字）
            for body in captured:
                out = self._extract_amount_from_json(body)
                if out is not None and (out.get("amount") or 0) >= 1000:
                    browser.close()
                    return out

            # 從頁面 HTML / 可見文字找（SPA 可能晚渲染）；不解析追隨數以加快更新
            amount, patron_count = None, None
            try:
                content = page.content()
                try:
                    visible = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
                    content = content + "\n" + visible
                except Exception:
                    pass
                # 支援額＝金額（日圓），必須 >= 1000，避免把「支援者数 662」誤當成金額
                amount_candidates = []
                for p in [
                    r'支援額[^\d]*(\d[\d,]+)',
                    r'"supportAmount"\s*:\s*(\d+(?:\.\d+)?)',
                    r'"transferableAmount"\s*:\s*(\d+(?:\.\d+)?)',
                    r'"monthlyAmount"\s*:\s*(\d+(?:\.\d+)?)',
                    r'振込可能[^\d]*(\d[\d,]+)\s*円',
                    r'(\d{1,3}(?:,\d{3})+)\s*円',  # 490,850 円 這種格式
                ]:
                    for m in re.finditer(p, content):
                        try:
                            val = float(m.group(1).replace(",", ""))
                            if 1000 <= val < 1e9:
                                amount_candidates.append(val)
                        except ValueError:
                            pass
                if amount_candidates:
                    amount = max(amount_candidates)
                # 支援者数（頁面可能有多個數字，取「最大」的才是總覽 KPI，避免誤取 11 等小數字）
                patron_candidates = []
                for p in [r'支援者数[^\d]*(\d[\d,]*)', r'"supporterCount"\s*:\s*(\d+)', r'"supportingCount"\s*:\s*(\d+)']:
                    for m in re.finditer(p, content):
                        try:
                            n = int(m.group(1).replace(",", ""))
                            if n > 0:
                                patron_candidates.append(n)
                        except ValueError:
                            pass
                if patron_candidates:
                    patron_count = max(patron_candidates)
                if amount is not None and amount >= 1000:
                    browser.close()
                    return {"amount": amount, "currency": "JPY", "patron_count": patron_count}
                # 備援：僅數字+円
                for m in re.finditer(r"(\d[\d,]+)\s*円", content):
                    val = float(m.group(1).replace(",", ""))
                    if 1000 <= val < 1e8:
                        browser.close()
                        return {"amount": val, "currency": "JPY", "patron_count": patron_count}
            except Exception:
                pass

            # 沒抓到金額時再等 3 秒讓 SPA 載入，重試解析一次
            if amount is None:
                try:
                    page.wait_for_timeout(3000)
                    content2 = page.content()
                    try:
                        content2 += "\n" + (page.evaluate("() => document.body ? document.body.innerText : ''") or "")
                    except Exception:
                        pass
                    ac, pc = [], []
                    for p in [r'支援額[^\d]*(\d[\d,]+)', r'"supportAmount"\s*:\s*(\d+(?:\.\d+)?)', r'振込可能[^\d]*(\d[\d,]+)\s*円', r'(\d{1,3}(?:,\d{3})+)\s*円', r'(\d[\d,]+)\s*円']:
                        for m in re.finditer(p, content2):
                            try:
                                val = float(m.group(1).replace(",", ""))
                                if 1000 <= val < 1e9:
                                    ac.append(val)
                            except ValueError:
                                pass
                    for p in [r'支援者数[^\d]*(\d[\d,]*)', r'"supporterCount"\s*:\s*(\d+)']:
                        for m in re.finditer(p, content2):
                            try:
                                n = int(m.group(1).replace(",", ""))
                                if n > 0:
                                    pc.append(n)
                            except ValueError:
                                pass
                    amount = max(ac) if ac else None
                    if patron_count is None and pc:
                        patron_count = max(pc)
                    if amount is not None and amount >= 1000:
                        browser.close()
                        return {"amount": amount, "currency": "JPY", "patron_count": patron_count}
                    if patron_count is not None:
                        for m in re.finditer(r"(\d[\d,]+)\s*円", content2):
                            val = float(m.group(1).replace(",", ""))
                            if 1000 <= val < 1e8:
                                browser.close()
                                return {"amount": val, "currency": "JPY", "patron_count": patron_count}
                except Exception:
                    pass

            # 用 selector 找畫面數字（僅接受 >= 1000 円，絕不把 662 人當金額）
            try:
                for selector in [
                    '[class*="Transferable"]', '[class*="transferable"]',
                    '[class*="Amount"]', '[class*="amount"]',
                    'text=/\\d+\\s*円/',
                ]:
                    el = page.query_selector(selector)
                    if el:
                        text = el.evaluate("el => el.textContent").strip()
                        nums = re.findall(r"[\d,]+", text)
                        if nums:
                            val = float(nums[0].replace(",", ""))
                            if 1000 <= val < 1e8:
                                browser.close()
                                return {"amount": val, "currency": "JPY", "patron_count": None}
            except Exception:
                pass

            browser.close()
        return None

    def _extract_amount_from_json(self, obj) -> Optional[dict]:
        """從 API 回應 JSON 遞迴找 支援額・支援者数（不取追隨数以加快更新）"""
        if isinstance(obj, dict):
            amount = None
            for key in ("supportAmount", "transferableAmount", "monthlyAmount", "amount", "totalAmount"):
                if key in obj and obj[key] is not None:
                    try:
                        amount = float(obj[key])
                        break
                    except (TypeError, ValueError):
                        pass
            patron = obj.get("supporterCount") or obj.get("supportingCount") or obj.get("patronCount")
            if amount is not None and amount >= 1000:
                return {
                    "amount": amount,
                    "currency": "JPY",
                    "patron_count": int(patron) if patron is not None else None,
                }
            for v in obj.values():
                out = self._extract_amount_from_json(v)
                if out:
                    return out
        elif isinstance(obj, list):
            for item in obj:
                out = self._extract_amount_from_json(item)
                if out:
                    return out
        return None

    def fetch_sponsorship(self) -> Optional[dict]:
        """
        取得 Fanbox 贊助數據。
        創作者後台為 SPA，優先以 Playwright 開頁並攔截 API／讀取畫面。
        """
        # 1. 先試直接 API（若官方有開放創作者端點）
        result = self._try_api_with_cookie()
        if result:
            return result
        # 2. 用 Playwright 開後台並攔截／爬取
        result = self._fetch_with_playwright()
        if result:
            return result
        return None
