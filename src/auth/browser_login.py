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
    """等待使用者按「已完成」；若 cancel 先置位�回�� False。"""
    step = 0.5
    deadline = time.monotonic() + total_timeout
    while time.monotonic() < deadline:
        if cancel.is_set():
            return False
        if done.wait(timeout=step):
            return True
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
            page.goto("https://www.fanbox.cc/")
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
    """Fantia 登入��行��。可重複按「已完成登入」直到抓到有效 session。"""
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
            while True:
                if cancel.is_set():
                    break
                if not _wait_done_or_cancel(event, cancel, 600):
                    break
                if cancel.is_set():
                    break
                cookies = context.cookies()
                session_id = ""
                for c in cookies:
                    if c["name"] == "_session_id":
                        session_id = c["value"]
                        break
                callback(session_id)
                if session_id:
                    break
                event.clear()
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
    """Patreon 登入�器��使用者登入，完成後抓取 cookies。"""
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
            while True:
                if cancel.is_set():
                    break
                if not _wait_done_or_cancel(event, cancel, 600):
                    break
                if cancel.is_set():
                    break
                cookies = context.cookies()
                cookie_parts = []
                for c in cookies:
                    if "patreon" in c.get("domain", ""):
                        cookie_parts.append(f"{c['name']}={c['value']}")
                cookie_str = "; ".join(cookie_parts)
                callback(cookie_str)
                if cookie_str:
                    break
                event.clear()
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
