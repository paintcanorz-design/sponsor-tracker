#!/usr/bin/env python3
"""
贊助額追蹤 - 主程式

支援：Patreon、Fanbox、Fantia
- 每小時自動更新贊助額
- 記錄每日漲跌
"""
import sys
from pathlib import Path

# 將 src 加入 path
sys.path.insert(0, str(Path(__file__).parent))

import yaml
import schedule
import time
from src.jst import now_jst, today_jst_str
from src.database import init_db, save_record, update_daily_summary
from src.fetchers.patreon_fetcher import PatreonFetcher
from src.fetchers.fanbox_fetcher import FanboxFetcher
from src.fetchers.fantia_fetcher import FantiaFetcher


def load_config():
    """載入設定"""
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        config_path = Path(__file__).parent / "config.example.yaml"
        print(f"請複製 config.example.yaml 為 config.yaml 並填入憑證")
        print(f"找不到 config.yaml，使用範例設定（無法實際取得數據）")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_update(config: dict):
    """執行一次贊助額更新"""
    print(f"\n[{now_jst().strftime('%Y-%m-%d %H:%M')} JST] 開始更新...")

    results = {}

    # Patreon（網頁爬取，需瀏覽器登入取得 cookies）
    patreon_cfg = config.get("patreon", {})
    cookies = (patreon_cfg.get("cookies") or "").strip()
    if cookies and "xxx" not in cookies:
        try:
            page_url = patreon_cfg.get("creator_page") or "https://www.patreon.com/c/paintcan"
            fetcher = PatreonFetcher(cookies, page_url)
            data = fetcher.fetch_sponsorship()
            if data:
                results["patreon"] = data
                save_record("patreon", data["amount"], data.get("currency", "USD"), data.get("patron_count"))
                print(f"  Patreon: {data['amount']:.2f} {data.get('currency', 'USD')} ({data.get('patron_count', '?')} 贊助者)")
        except Exception as e:
            print(f"  Patreon 錯誤: {e}")

    # Fanbox（需為實際 cookie，非 placeholder）
    fanbox_cfg = config.get("fanbox", {})
    cookies = (fanbox_cfg.get("cookies") or "").strip()
    if cookies and "xxx" not in cookies:
        try:
            fetcher = FanboxFetcher(cookies)
            data = fetcher.fetch_sponsorship()
            if data:
                results["fanbox"] = data
                save_record("fanbox", data["amount"], data.get("currency", "JPY"), data.get("patron_count"))
                print(f"  Fanbox: {data['amount']:.0f} {data.get('currency', 'JPY')} ({data.get('patron_count', '?')} 支援者)")
        except Exception as e:
            print(f"  Fanbox 錯誤: {e}")

    # Fantia（需為實際 session_id，非 placeholder）
    fantia_cfg = config.get("fantia", {})
    sid = (fantia_cfg.get("session_id") or "").strip()
    if sid and "你的" not in sid:
        try:
            fetcher = FantiaFetcher(sid)
            data = fetcher.fetch_sponsorship()
            if data:
                results["fantia"] = data
                save_record("fantia", data["amount"], data.get("currency", "JPY"), data.get("patron_count"))
                print(f"  Fantia: {data['amount']:.0f} {data.get('currency', 'JPY')} ({data.get('patron_count', '?')} 会員)")
        except Exception as e:
            print(f"  Fantia 錯誤: {e}")

    # 更新每日摘要
    today = today_jst_str()
    for platform, data in results.items():
        update_daily_summary(platform, today, data["amount"], data.get("patron_count"))

    if not results:
        print("  無可用數據（請檢查 config.yaml 憑證）")
    else:
        print("  更新完成")


def main():
    config = load_config()
    init_db()

    # 立即執行一次
    run_update(config)

    # 排程：每 N 小時更新
    interval = config.get("schedule", {}).get("update_interval_hours", 1)
    schedule.every(interval).hours.do(run_update, config)

    print(f"\n排程已啟動：每 {interval} 小時更新一次")
    print("按 Ctrl+C 結束\n")

    while True:
        schedule.run_pending()
        time.sleep(60)  # 每分鐘檢查


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="只執行一次更新，不啟動排程")
    args = parser.parse_args()

    if args.once:
        config = load_config()
        init_db()
        run_update(config)
    else:
        main()
