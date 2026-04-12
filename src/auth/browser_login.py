"""Fanbox / Fantia ����器登入 - 開��視窗��使用者登入，����完成後自動抓取 Cookie"""
import threading
import time
from typing import Callable

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


def _wait_done_or_cancel(
    done: threading.Event, cancel: threading.Event, total_timeout: float = 600.0
) -> bool:
    """等待使用者按「已完成」；若 cancel 先置位則回傳 False。

    使用 is_set 輪詢而非 Event.wait 迴圈，避免與 Qt／Playwright 執行緒互動時偶發無法喚醒。
    """
    step = 0.05
    deadline = time.monotonic() + total_timeout
    while time.monotonic() < deadline:
        if cancel.is_set():
            return False
        if done.is_set():
            return True
        time.sleep(step)
    return False


def _run_fanbox(
    event: threading.Event, cancel: threading.Event, callback: Callable[[str], None]
):
    """Fanbox�行��"""
    if not PLAYWRIGHT_AVAILABLE:
        callback("")
        return
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://www.fanbox.cc/", wait_until="domcontentloaded", timeout=60000)
            if cancel.is_set():
                browser.close()
                callback("")
                return
            if not _wait_done_or_cancel(event, cancel, 600):
                browser.close()
                callback("")
                return
            cookies = context.cookies()
            # Fanbox 登入有時會��由 pixiv，一����上 pixiv �� fanbox 的 cookie
            cookie_str = "; ".join(
                f"{c['name']}={c['value']}" for c in cookies
                if "fanbox" in c.get("domain", "") or "pixiv" in c.get("domain", "")
            )
            browser.close()
            callback(cookie_str)
    except Exception:
        callback("")


def _run_fantia(
    event: threading.Event, cancel: threading.Event, callback: Callable[[str], None]
):
    """Fantia：登入後按一次「已完成」即抓取 _session_id。未取得則回傳空字串。"""
    if not PLAYWRIGHT_AVAILABLE:
        callback("")
        return
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://fantia.jp/sessions/signin", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
            if cancel.is_set():
                browser.close()
                callback("")
                return
            if not _wait_done_or_cancel(event, cancel, 600):
                browser.close()
                callback("")
                return
            if cancel.is_set():
                browser.close()
                callback("")
                return
            cookies = context.cookies()
            session_id = ""
            for c in cookies:
                if c["name"] == "_session_id":
                    session_id = c["value"]
                    break
            callback(session_id)
            browser.close()
    except Exception:
        callback("")


def fanbox_login(
    done_event: threading.Event,
    callback: Callable[[str], None],
    cancel_event: threading.Event,
):
    """
    開�� Fanbox 登入視窗
    使用者登入後����「已完成登入」時，請呼叫 done_event.set()
    callback(cookie_string) 在抓取完成時被呼叫
    """
    threading.Thread(
        target=_run_fanbox, args=(done_event, cancel_event, callback), daemon=True
    ).start()


def fantia_login(
    done_event: threading.Event,
    callback: Callable[[str], None],
    cancel_event: threading.Event,
):
    """
    開�� Fantia 登入視窗
    使用者登入後����「已完成登入」時，請呼叫 done_event.set()
    callback(session_id) 在抓取完成時被呼叫
    """
    threading.Thread(
        target=_run_fantia, args=(done_event, cancel_event, callback), daemon=True
    ).start()


def _run_patreon(
    event: threading.Event, cancel: threading.Event, callback: Callable[[str], None]
):
    """Patreon：開瀏覽器登入，使用者按一次「已完成」即抓取 cookies 並結束。

    先前若 cookie 為空會 clear(event) 並再次等待，但 UI 已停用「已完成」按鈕，導致永遠卡住。
    """
    if not PLAYWRIGHT_AVAILABLE:
        callback("")
        return
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://www.patreon.com/login", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
            if cancel.is_set():
                browser.close()
                callback("")
                return
            if not _wait_done_or_cancel(event, cancel, 600):
                browser.close()
                callback("")
                return
            if cancel.is_set():
                browser.close()
                callback("")
                return
            cookies = context.cookies()
            cookie_parts = []
            for c in cookies:
                if "patreon" in c.get("domain", ""):
                    cookie_parts.append(f"{c['name']}={c['value']}")
            cookie_str = "; ".join(cookie_parts)
            callback(cookie_str)
            browser.close()
    except Exception:
        callback("")


def patreon_login(
    done_event: threading.Event,
    callback: Callable[[str], None],
    cancel_event: threading.Event,
):
    """
    開�� Patreon 登入視窗
    使用者登入後����「已完成登入」時，請呼叫 done_event.set()
    callback(cookie_string) 在抓取完成時被呼叫
    """
    threading.Thread(
        target=_run_patreon, args=(done_event, cancel_event, callback), daemon=True
    ).start()
