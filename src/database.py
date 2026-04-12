"""資料庫模組 - 儲存贊助額與每日漲跌記錄"""
import os
import sqlite3
from pathlib import Path

from src.jst import date_days_ago_jst, now_jst, today_jst_str, yesterday_jst_str
from src.paths import project_root

def _usd_jpy_rate():
    try:
        from src.exchange import get_usd_jpy_rate
        return get_usd_jpy_rate()
    except Exception:
        return 150.0


_PROJECT_ROOT = project_root()
_resolved_db_path: Path | None = None


def _paths_from_config() -> tuple[Path | None, Path | None]:
    """從 config.yaml 讀取 (database 檔案路徑, data_dir 目錄)。database 優先。"""
    cfg_path = _PROJECT_ROOT / "config.yaml"
    if not cfg_path.exists():
        return None, None
    try:
        import yaml
        with open(cfg_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        paths = data.get("paths") or {}
        db_s = (paths.get("database") or "").strip()
        dir_s = (paths.get("data_dir") or "").strip()
        db_p = Path(db_s).expanduser() if db_s else None
        if db_p is not None and not db_p.is_absolute():
            db_p = (_PROJECT_ROOT / db_p).resolve()
        elif db_p is not None:
            db_p = db_p.resolve()
        dir_p = Path(dir_s).expanduser() if dir_s else None
        if dir_p is not None and not dir_p.is_absolute():
            dir_p = (_PROJECT_ROOT / dir_p).resolve()
        elif dir_p is not None:
            dir_p = dir_p.resolve()
        return db_p, dir_p
    except Exception:
        return None, None


def resolve_db_path() -> Path:
    """
    SQLite 檔案路徑。優先順序：
    環境變數 SPONSORSHIP_DB_PATH（完整 .db 路徑）
    → SPONSORSHIP_DATA_DIR（目錄，檔名固定 sponsorship_data.db）
    → config.yaml paths.database
    → config.yaml paths.data_dir
    → 專案根目錄 / sponsorship_data.db
    """
    global _resolved_db_path
    if _resolved_db_path is not None:
        return _resolved_db_path

    root = _PROJECT_ROOT

    env_db = (os.environ.get("SPONSORSHIP_DB_PATH") or "").strip()
    if env_db:
        p = Path(env_db).expanduser()
        p = (root / p).resolve() if not p.is_absolute() else p.resolve()
        _resolved_db_path = p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    env_dir = (os.environ.get("SPONSORSHIP_DATA_DIR") or "").strip()
    if env_dir:
        d = Path(env_dir).expanduser()
        d = (root / d).resolve() if not d.is_absolute() else d.resolve()
        p = d / "sponsorship_data.db"
        _resolved_db_path = p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    cfg_db, cfg_dir = _paths_from_config()
    if cfg_db is not None:
        p = cfg_db
    elif cfg_dir is not None:
        p = cfg_dir / "sponsorship_data.db"
    else:
        p = root / "sponsorship_data.db"

    _resolved_db_path = p.resolve()
    _resolved_db_path.parent.mkdir(parents=True, exist_ok=True)
    return _resolved_db_path


def get_connection():
    """取得資料庫連線"""
    conn = sqlite3.connect(resolve_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def clear_sponsorship_data():
    conn = get_connection()
    try:
        conn.execute("DELETE FROM sponsorship_records")
        conn.execute("DELETE FROM daily_summary")
        conn.commit()
    finally:
        conn.close()


def init_db():
    """初始化資料庫表"""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sponsorship_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT DEFAULT 'JPY',
                patron_count INTEGER,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS daily_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                date DATE NOT NULL,
                total_amount REAL NOT NULL,
                patron_count INTEGER,
                change_amount REAL,
                change_percent REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(platform, date)
            );

            CREATE INDEX IF NOT EXISTS idx_records_platform_time 
                ON sponsorship_records(platform, recorded_at);
            CREATE INDEX IF NOT EXISTS idx_daily_platform_date 
                ON daily_summary(platform, date);
        """)
        conn.commit()
    finally:
        conn.close()


def save_record(platform: str, amount: float, currency: str = "JPY", patron_count: int = None):
    """儲存單筆贊助額記錄"""
    conn = get_connection()
    try:
        ts = now_jst().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO sponsorship_records (platform, amount, currency, patron_count, recorded_at) VALUES (?, ?, ?, ?, ?)",
            (platform, amount, currency, patron_count, ts),
        )
        conn.commit()
    finally:
        conn.close()


def update_daily_summary(platform: str, date_str: str, total_amount: float, patron_count: int = None):
    """更新每日摘要（計算漲跌）"""
    conn = get_connection()
    try:
        # 取得前一天的總額
        prev = conn.execute(
            """SELECT total_amount FROM daily_summary 
               WHERE platform = ? AND date < ? 
               ORDER BY date DESC LIMIT 1""",
            (platform, date_str),
        ).fetchone()

        prev_amount = prev["total_amount"] if prev else None
        change_amount = (total_amount - prev_amount) if prev_amount is not None else None
        change_percent = (
            ((total_amount - prev_amount) / prev_amount * 100) if prev_amount and prev_amount > 0 else None
        )

        conn.execute(
            """INSERT INTO daily_summary (platform, date, total_amount, patron_count, change_amount, change_percent)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(platform, date) DO UPDATE SET
                   total_amount = excluded.total_amount,
                   patron_count = excluded.patron_count,
                   change_amount = excluded.change_amount,
                   change_percent = excluded.change_percent""",
            (platform, date_str, total_amount, patron_count, change_amount, change_percent),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_records(platform: str = None, limit: int = 100):
    """取得最近記錄"""
    conn = get_connection()
    try:
        if platform:
            return conn.execute(
                "SELECT * FROM sponsorship_records WHERE platform = ? ORDER BY recorded_at DESC LIMIT ?",
                (platform, limit),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM sponsorship_records ORDER BY recorded_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()


def get_daily_summary(platform: str = None, days: int = 30):
    """取得每日摘要"""
    conn = get_connection()
    try:
        if platform:
            return conn.execute(
                """SELECT * FROM daily_summary 
                   WHERE platform = ? 
                   ORDER BY date DESC LIMIT ?""",
                (platform, days),
            ).fetchall()
        return conn.execute(
            """SELECT * FROM daily_summary 
               ORDER BY date DESC LIMIT ?""",
            (days * 3,),  # 三個平台
        ).fetchall()
    finally:
        conn.close()


def get_chart_data(days: int = 30):
    """取得趨勢圖數據，回傳 {platform: [(date_str, amount), ...]} 按日期升序"""
    conn = get_connection()
    try:
        start = date_days_ago_jst(days)
        rows = conn.execute(
            """SELECT platform, date, total_amount, patron_count FROM daily_summary 
               WHERE date >= ?
               ORDER BY date ASC""",
            (start,),
        ).fetchall()
        result = {}
        for r in rows:
            platform = r["platform"]
            if platform not in result:
                result[platform] = []
            result[platform].append((r["date"], r["total_amount"], r["patron_count"]))
        return result
    finally:
        conn.close()


def get_chart_combined_daily_between(start_str: str, end_str: str) -> list[tuple[str, float, int]]:
    """
    每日三平台加總（與總覽邏輯一致：Patreon USD→日幣，其餘原幣當日幣加總）。
    回傳 [(date_str, total_amount_jpy, total_patron_count), ...] 日期升序。
    """
    conn = get_connection()
    try:
        rate = _usd_jpy_rate()
        cur_rows = conn.execute(
            """SELECT platform, currency FROM sponsorship_records r
               WHERE (platform, recorded_at) IN (
                 SELECT platform, MAX(recorded_at) FROM sponsorship_records GROUP BY platform
               )"""
        ).fetchall()
        currency_map = {r["platform"]: r["currency"] for r in cur_rows}
        rows = conn.execute(
            """SELECT date, platform, total_amount, patron_count FROM daily_summary
               WHERE date >= ? AND date <= ?
               ORDER BY date ASC, platform""",
            (start_str, end_str),
        ).fetchall()
        by_date: dict[str, list] = {}
        for r in rows:
            d = r["date"]
            plat = r["platform"]
            amt = float(r["total_amount"] or 0)
            if currency_map.get(plat) == "USD":
                amt *= rate
            pc = int(r["patron_count"] or 0)
            if d not in by_date:
                by_date[d] = [0.0, 0]
            by_date[d][0] += amt
            by_date[d][1] += pc
        return [(d, by_date[d][0], by_date[d][1]) for d in sorted(by_date.keys())]
    finally:
        conn.close()


def get_chart_combined_daily(days: int = 30):
    """Rolling window: combined daily JPY totals from (today - N days) through today; N capped at 366."""
    days = max(1, min(int(days), 366))
    return get_chart_combined_daily_between(date_days_ago_jst(days), today_jst_str())


def get_dashboard_stats():
    """
    經營儀表板用：總額、增減、贊助人數、分平台明細。
    回傳 dict:
      total_amount, total_patron_count,
      change_vs_yesterday (金額), change_pct_vs_yesterday,
      increase_amount (本日/最近正變動), decrease_amount (本日/最近負變動),
      patron_change (人數變化),
      by_platform: [{ platform, amount, patron_count, change_amount, change_percent, currency }]
    """
    conn = get_connection()
    try:
        # 各平台最新一筆每日摘要（當天或最近一天）
        latest = conn.execute(
            """SELECT platform, date, total_amount, patron_count, change_amount, change_percent
               FROM daily_summary d1
               WHERE (platform, date) IN (
                 SELECT platform, MAX(date) FROM daily_summary GROUP BY platform
               )
               ORDER BY platform"""
        ).fetchall()

        # 幣別（先取，供 USD→JPY 換算總額）
        cur_rows = conn.execute(
            """SELECT platform, currency, recorded_at FROM sponsorship_records r
               WHERE (platform, recorded_at) IN (
                 SELECT platform, MAX(recorded_at) FROM sponsorship_records GROUP BY platform
               )"""
        ).fetchall()
        currency_map = {r["platform"]: r["currency"] for r in cur_rows}
        last_updated_map = {r["platform"]: r["recorded_at"] for r in cur_rows}

        rate = _usd_jpy_rate()
        yday = yesterday_jst_str()
        yesterday = conn.execute(
            """SELECT platform, total_amount, patron_count FROM daily_summary
               WHERE date = ?""",
            (yday,),
        ).fetchall()
        yesterday_amount = 0
        yesterday_patrons = 0
        for r in yesterday:
            yesterday_amount += (r["total_amount"] * rate if currency_map.get(r["platform"]) == "USD" else r["total_amount"])
            yesterday_patrons += r["patron_count"] or 0
        has_yesterday = len(yesterday) > 0

        total_amount = 0
        for r in latest:
            total_amount += (r["total_amount"] * rate if currency_map.get(r["platform"]) == "USD" else r["total_amount"])
        total_patrons = sum(r["patron_count"] or 0 for r in latest)
        increase_amount = 0
        decrease_amount = 0
        for r in latest:
            ch = r["change_amount"] or 0
            mult = rate if currency_map.get(r["platform"]) == "USD" else 1
            if ch > 0:
                increase_amount += ch * mult
            else:
                decrease_amount += ch * mult
        patron_change = (total_patrons - yesterday_patrons) if has_yesterday else None
        change_vs_yesterday = (total_amount - yesterday_amount) if has_yesterday else None
        change_pct = (
            (total_amount - yesterday_amount) / yesterday_amount * 100
            if has_yesterday and yesterday_amount and yesterday_amount > 0 else None
        )

        by_platform = [
            {
                "platform": r["platform"],
                "amount": r["total_amount"],
                "patron_count": r["patron_count"] or 0,
                "change_amount": r["change_amount"],
                "change_percent": r["change_percent"],
                "currency": currency_map.get(r["platform"], "JPY"),
                "last_updated": last_updated_map.get(r["platform"]),
            }
            for r in latest
        ]

        return {
            "total_amount": total_amount,
            "total_patron_count": total_patrons,
            "change_vs_yesterday": change_vs_yesterday,
            "change_pct_vs_yesterday": change_pct,
            "increase_amount": increase_amount,
            "decrease_amount": decrease_amount,
            "patron_change": patron_change,
            "yesterday_amount": yesterday_amount,
            "by_platform": by_platform,
            "fx_usd_jpy": rate,
        }
    finally:
        conn.close()


def get_period_comparison(days: int = 7):
    """
    週期比較：最近 N 天總額 vs 前 N 天總額（總額以日圓計，USD 會換算）。
    回傳 { total_recent, total_previous, change_amount, change_percent }
    """
    conn = get_connection()
    try:
        cur_rows = conn.execute(
            """SELECT platform, currency FROM sponsorship_records r
               WHERE (platform, recorded_at) IN (
                 SELECT platform, MAX(recorded_at) FROM sponsorship_records GROUP BY platform
               )"""
        ).fetchall()
        currency_map = {r["platform"]: r["currency"] for r in cur_rows}
        rate = _usd_jpy_rate()
        start = date_days_ago_jst(days * 2)
        rows = conn.execute(
            """SELECT platform, date, total_amount FROM daily_summary
               WHERE date >= ?
               ORDER BY date ASC""",
            (start,),
        ).fetchall()
        if not rows:
            return None
        from collections import defaultdict
        by_date = defaultdict(float)
        for r in rows:
            amt = r["total_amount"] * rate if currency_map.get(r["platform"]) == "USD" else r["total_amount"]
            by_date[r["date"]] += amt
        dates = sorted(by_date.keys())
        if len(dates) < 2:
            return None
        mid = len(dates) // 2
        recent_dates = dates[mid:]
        prev_dates = dates[:mid]
        total_recent = sum(by_date[d] for d in recent_dates)
        total_previous = sum(by_date[d] for d in prev_dates)
        change = total_recent - total_previous
        pct = (change / total_previous * 100) if total_previous else None
        return {
            "total_recent": total_recent,
            "total_previous": total_previous,
            "change_amount": change,
            "change_percent": pct,
            "days": days,
        }
    finally:
        conn.close()
