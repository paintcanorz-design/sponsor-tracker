"""Facebook / X (Twitter) 粉絲數取得 — 多層備援策略"""
import re
import requests
from typing import Optional
from urllib.parse import urlparse

HEADERS_DESKTOP = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

HEADERS_MOBILE = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
                  "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT = True
except ImportError:
    _PLAYWRIGHT = False


# ---------------------------------------------------------------------------
#  URL helpers
# ---------------------------------------------------------------------------

def _extract_x_username(url: str) -> Optional[str]:
    """Extract Twitter/X username from a profile URL."""
    if not url:
        return None
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.hostname or "").lower()
    if "x.com" not in host and "twitter.com" not in host:
        return None
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if not parts:
        return None
    name = parts[0]
    if name.lower() in ("home", "explore", "search", "settings", "i", "intent"):
        return None
    return name


def _extract_fb_page(url: str) -> Optional[str]:
    """Extract Facebook page name/ID from a page URL."""
    if not url:
        return None
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.hostname or "").lower()
    if "facebook.com" not in host:
        return None
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if not parts:
        return None
    name = parts[0]
    if name.lower() in ("pages", "groups", "events", "marketplace", "watch", "gaming", "profile.php"):
        return parts[1] if len(parts) > 1 else None
    return name


# ---------------------------------------------------------------------------
#  Number parsing (handles "1,234", "354.8K", "3万", "175M" etc.)
# ---------------------------------------------------------------------------

_SUFFIX_MAP = {
    "k": 1_000, "m": 1_000_000, "b": 1_000_000_000,
    "万": 10_000, "萬": 10_000, "億": 100_000_000,
}


def _parse_abbr_number(raw: str) -> Optional[int]:
    """Parse a possibly-abbreviated number string like '354.8K' or '3万' into int."""
    raw = raw.strip().replace(",", "").replace(" ", "").replace("\u00a0", "")
    m = re.match(r'^([\d.]+)\s*([KkMmBb万萬億])?$', raw)
    if not m:
        return None
    try:
        base = float(m.group(1))
    except ValueError:
        return None
    suffix = (m.group(2) or "").lower()
    if suffix in ("万", "萬", "億"):
        suffix = m.group(2)
    mult = _SUFFIX_MAP.get(suffix, 1)
    return int(base * mult)


# ---------------------------------------------------------------------------
#  X (Twitter) — syndication endpoint → Playwright fallback
# ---------------------------------------------------------------------------

_X_TEXT_PATTERNS = [
    r'"followers_count"\s*:\s*(\d+)',
    r'"followersCount"\s*:\s*"?(\d[\d,]*)"?',
    r'content="([\d,.]+[KkMm]?)\s*Followers?"',
    r'([\d,.]+[KkMm]?)\s*Follower',
    r'([\d,.]+[KkMm]?)\s*追蹤者',
    r'フォロワー([\d,.]+[KkMm万萬]?)人?',
    r'followers["\s:]+(\d[\d,]*)',
]


def _parse_x_text(text: str) -> Optional[int]:
    for pat in _X_TEXT_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            n = _parse_abbr_number(m.group(1))
            if n is not None and n > 0:
                return n
    return None


def _x_via_syndication(username: str) -> Optional[int]:
    """Twitter widget syndication endpoint — returns JSON with followers_count."""
    url = f"https://cdn.syndication.twimg.com/widgets/followbutton/info.json?screen_names={username}"
    try:
        r = requests.get(url, headers=HEADERS_DESKTOP, timeout=10)
        if r.status_code == 200 and r.text.strip():
            data = r.json()
            if data and isinstance(data, list) and len(data) > 0:
                count = data[0].get("followers_count")
                if count is not None:
                    return int(count)
    except Exception as e:
        print(f"[social] X syndication failed: {e}")
    return None


def _pw_click_if_visible(page, selectors: list[str], label: str) -> bool:
    """Try clicking the first visible element matching any selector."""
    for sel in selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(2000)
                return True
        except Exception:
            pass
    return False


def _x_via_playwright(url: str) -> Optional[int]:
    """Load X profile in Playwright, handle cookie consent + sensitive warning."""
    if not _PLAYWRIGHT:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=HEADERS_DESKTOP["User-Agent"],
                viewport={"width": 1280, "height": 900},
            )
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=25_000)
            page.wait_for_timeout(3000)

            _pw_click_if_visible(page, [
                'button:has-text("Accept all cookies")',
                'button:has-text("Accept")',
                'button:has-text("允許所有 Cookie")',
                'button:has-text("接受所有")',
            ], "cookie consent")

            _pw_click_if_visible(page, [
                'button:has-text("Yes, view profile")',
                'a:has-text("Yes, view profile")',
                'button:has-text("是，檢視個人檔案")',
                'button:has-text("はい、プロフィールを見ます")',
            ], "sensitive content")

            page.wait_for_timeout(4000)
            inner = page.evaluate("() => document.body?.innerText || ''") or ""
            html = page.content()
            browser.close()
            return _parse_x_text(inner + "\n" + html)
    except Exception as e:
        print(f"[social] X Playwright failed: {e}")
    return None


def get_x_followers(url: str) -> Optional[int]:
    """取得 X (Twitter) 追蹤數 — syndication → Playwright"""
    if not url or ("x.com" not in url and "twitter.com" not in url):
        return None
    username = _extract_x_username(url)
    if username:
        n = _x_via_syndication(username)
        if n is not None:
            print(f"[social] X @{username} followers={n} (syndication)")
            return n
    n = _x_via_playwright(url)
    if n is not None:
        print(f"[social] X followers={n:,} (playwright)")
    else:
        print(f"[social] X: all methods failed for {url}")
    return n


# ---------------------------------------------------------------------------
#  Facebook — requests → Graph API → Playwright
# ---------------------------------------------------------------------------

_FB_TEXT_PATTERNS = [
    r'"fan_count"\s*:\s*(\d+)',
    r'"followers_count"\s*:\s*(\d+)',
    r'"global_likers_count"\s*:\s*(\d+)',
    r'"page_likers"\s*:\s*(\d+)',
    r'content="([\d,.]+[KkMm万萬億]?)\s*(?:likes?|followers?)"',
    r'([\d,.]+[KkMm万萬億]?)\s*位用戶說這專頁',
    r'([\d,.]+[KkMm万萬億]?)\s*people like this',
    r'([\d,.]+[KkMm万萬億]?)\s*(?:人在追蹤|人追蹤)',
    r'([\d,.]+[KkMm万萬億]?)\s*人在追蹤此專頁',
    r'([\d,.]+[KkMm万萬億]?)\s*(?:個)?(?:追蹤者|follower)',
    r'([\d,.]+[KkMm万萬億]?)\s*(?:個)?讚',
    r'フォロワー([\d,.]+[KkMm万萬億]?)人',
    r'(?:粉絲|粉丝)\s*([\d,.]+[KkMm万萬億]?)人?',
    r'see_fan_count[\s\S]*?(\d[\d,]+)',
]


def _parse_facebook_text(text: str) -> Optional[int]:
    for pat in _FB_TEXT_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            n = _parse_abbr_number(m.group(1))
            if n is not None and n > 0:
                return n
    return None


def _fb_via_requests(url: str) -> Optional[int]:
    """Try fetching with mobile UA (m.facebook.com returns simpler HTML)."""
    mobile_url = url.replace("www.facebook.com", "m.facebook.com")
    for target, headers in [(mobile_url, HEADERS_MOBILE), (url, HEADERS_DESKTOP)]:
        try:
            r = requests.get(target, headers=headers, timeout=15, allow_redirects=True)
            if r.status_code == 200 and "login" not in r.url:
                n = _parse_facebook_text(r.text)
                if n is not None:
                    return n
        except Exception as e:
            print(f"[social] FB requests failed ({target}): {e}")
    return None


def _fb_via_graph_api(page_name: str) -> Optional[int]:
    """Public Graph API — sometimes works for public pages without a token."""
    url = f"https://graph.facebook.com/{page_name}?fields=fan_count,followers_count"
    try:
        r = requests.get(url, headers=HEADERS_DESKTOP, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for key in ("followers_count", "fan_count"):
                v = data.get(key)
                if v is not None:
                    return int(v)
    except Exception as e:
        print(f"[social] FB Graph API failed: {e}")
    return None


def _fb_via_playwright(url: str) -> Optional[int]:
    """Load Facebook page in Playwright and parse innerText for follower count."""
    if not _PLAYWRIGHT:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=HEADERS_DESKTOP["User-Agent"],
                viewport={"width": 1280, "height": 900},
            )
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=25_000)
            page.wait_for_timeout(6000)

            _pw_click_if_visible(page, [
                'button:has-text("Accept")',
                'button:has-text("Allow")',
                'button:has-text("允許")',
            ], "cookie consent")

            inner = page.evaluate("() => document.body?.innerText || ''") or ""
            html = page.content()
            browser.close()
            return _parse_facebook_text(inner + "\n" + html)
    except Exception as e:
        print(f"[social] FB Playwright failed: {e}")
    return None


def get_facebook_followers(url: str) -> Optional[int]:
    """取得 Facebook 專頁追蹤/按讚數 — requests(mobile) → Graph API → Playwright"""
    if not url or "facebook.com" not in url:
        return None
    n = _fb_via_requests(url)
    if n is not None:
        print(f"[social] FB followers={n:,} (requests)")
        return n
    page_name = _extract_fb_page(url)
    if page_name:
        n = _fb_via_graph_api(page_name)
        if n is not None:
            print(f"[social] FB followers={n:,} (graph api)")
            return n
    n = _fb_via_playwright(url)
    if n is not None:
        print(f"[social] FB followers={n:,} (playwright)")
    else:
        print(f"[social] FB: all methods failed for {url}")
    return n
