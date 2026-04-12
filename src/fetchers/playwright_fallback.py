"""
Playwright 備援 - 當 requests 無法取得 SPA 頁面時使用

使用前需執行: playwright install chromium
"""
import re
from typing import Optional

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


def fanbox_fetch_with_playwright(cookies: str) -> Optional[dict]:
    """
    使用 Playwright 取得 Fanbox 創作者後台數據
    cookies: "name1=value1; name2=value2"
    """
    if not PLAYWRIGHT_AVAILABLE:
        return None

    cookie_dict = {}
    for part in cookies.strip().split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookie_dict[k.strip()] = v.strip()

    cookie_list = [{"name": k, "value": v, "domain": ".fanbox.cc", "path": "/"} for k, v in cookie_dict.items()]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(cookie_list)
        page = context.new_page()
        try:
            page.goto("https://www.fanbox.cc/manage/payouts", wait_until="networkidle", timeout=30000)
            content = page.content()
            # 嘗試從頁面提取
            for pattern in [
                r'"transferableAmount"\s*:\s*(\d+(?:\.\d+)?)',
                r'"monthlyAmount"\s*:\s*(\d+(?:\.\d+)?)',
                r'(\d[\d,]+)\s*円',
            ]:
                m = re.search(pattern, content)
                if m:
                    amount = float(m.group(1).replace(",", ""))
                    return {"amount": amount, "currency": "JPY", "patron_count": None}
        except Exception:
            pass
        finally:
            browser.close()
    return None


def fantia_fetch_with_playwright(session_id: str) -> Optional[dict]:
    """使用 Playwright 取得 Fantia 創作者後台數據（等儀表板內容出現後解析）"""
    if not PLAYWRIGHT_AVAILABLE:
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        for domain in ["fantia.jp", ".fantia.jp"]:
            context.add_cookies([{"name": "_session_id", "value": session_id, "domain": domain, "path": "/"}])
        page = context.new_page()
        try:
            page.goto("https://fantia.jp/mypage/fanclubs/creator_dashboard", wait_until="domcontentloaded", timeout=18000)
            try:
                page.get_by_text("全体売上").first.wait_for(state="visible", timeout=10000)
            except Exception:
                page.wait_for_timeout(5000)
            if "/sessions/signin" in page.url:
                return None
            content = page.content()
            try:
                visible = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
                content = content + "\n" + visible
            except Exception:
                pass
            amount, patron_count = None, None
            for pat in [r'全体売上[^¥\d]*¥?\s*([\d,]+)', r'全体売上.*?([\d,]+)\s*円', r'([\d,]+)\s*円\s*※前月', r'¥\s*([\d,]+)']:
                m = re.search(pat, content, re.DOTALL if ".*?" in pat else 0)
                if m:
                    try:
                        v = float(m.group(1).replace(",", ""))
                        if 100 <= v < 1e10:
                            amount = v
                            break
                    except ValueError:
                        pass
            if amount is None:
                for m in re.finditer(r'(\d[\d,]+)\s*円', content):
                    try:
                        v = float(m.group(1).replace(",", ""))
                        if 10000 <= v < 1e10:
                            amount = v
                            break
                    except ValueError:
                        pass
            for pat in [
                r'プラン加入総数[^\d]*(\d+)',
                r'プラン加入.*?(\d+)\s*※',
                r'加入総数[^\d]*(\d+)',
                r'会員数[^\d]*(\d+)',
                r'加入数[^\d]*(\d+)',
                r'ファンクラブ.*?(\d+)\s*人',
                r'"plan_subscriptions"\s*:\s*(\d+)',
                r'"member_count"\s*:\s*(\d+)',
                r'(\d+)\s*人\s*[（(]プラン',
                r'プラン.*?(\d+)\s*人',
                r'(\d+)\s*名',
            ]:
                m = re.search(pat, content, re.DOTALL if ".*?" in pat else 0)
                if m:
                    try:
                        patron_count = int(m.group(1).replace(",", ""))
                        if patron_count >= 0:
                            break
                    except ValueError:
                        pass
            if amount is not None or patron_count is not None:
                return {"amount": amount or 0, "currency": "JPY", "patron_count": patron_count}
        except Exception:
            pass
        finally:
            browser.close()
    return None


def _parse_patreon_page(content: str) -> Optional[dict]:
    """
    從頁面內容解析收益與贊助人數
    目標：會籍 $925／月、192 收費（來自 https://www.patreon.com/c/paintcan）
    """
    amount, patron_count = None, None
    # 允許換行與空白
    flags = re.DOTALL | re.IGNORECASE

    # 金額：會籍 $925 ／月（數字與／月可能分開）
    for pat in [
        r'\$\s*([\d,]+(?:\.\d+)?)\s*[/／]\s*月',
        r'會籍\s*\$\s*([\d,]+(?:\.\d+)?)',
        r'\$\s*([\d,]+(?:\.\d+)?)\s+／?\s*月',
        r'"monthlyEarnings"\s*:\s*(\d+(?:\.\d+)?)',
        r'\$\s*([\d,]+(?:\.\d+)?)',
    ]:
        m = re.search(pat, content, flags)
        if m:
            try:
                v = float(m.group(1).replace(",", ""))
                if 1 <= v < 1e10:
                    amount = v
                    break
            except ValueError:
                pass

    # 付費人數：192 收費（數字與收費可能分開）
    for pat in [
        r'([\d,]+)\s+收費',
        r'([\d,]+)\s*收費',
        r'收費\s*([\d,]+)',
        r'"patronCount"\s*:\s*(\d+)',
        r'(\d+)\s*patrons',
    ]:
        m = re.search(pat, content, flags)
        if m:
            try:
                patron_count = int(m.group(1).replace(",", ""))
                if patron_count >= 0:
                    break
            except ValueError:
                pass

    if amount is not None or patron_count is not None:
        return {"amount": amount if amount is not None else 0, "currency": "USD", "patron_count": patron_count}
    return None


def patreon_fetch_with_playwright(cookies: str, creator_page: str = None) -> Optional[dict]:
    """使用 Playwright 取得 Patreon 創作者後台數據（收益與贊助人數）"""
    if not PLAYWRIGHT_AVAILABLE:
        return None

    # 處理 YAML 多行：合併成單行再解析
    cookies_str = " ".join((cookies or "").strip().split())
    cookie_dict = {}
    for part in cookies_str.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookie_dict[k.strip()] = v.strip()

    if not cookie_dict:
        return None

    cookie_list = [
        {"name": k, "value": v, "domain": ".patreon.com", "path": "/"}
        for k, v in cookie_dict.items()
    ]

    url = creator_page or "https://www.patreon.com/c/paintcan"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        context.add_cookies(cookie_list)
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=12000)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            page.wait_for_timeout(1500)
            if "/login" in page.url or "login" in page.url:
                return None
            content = page.content()
            try:
                visible = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
                content = content + "\n" + visible
            except Exception:
                pass
            return _parse_patreon_page(content)
        except Exception:
            pass
        finally:
            browser.close()
    return None
