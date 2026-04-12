"""測試 Fanbox 從 HTML 正確取出 支援額/支援者数/フォロワー数（取最大、排除 11 等小數字）"""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def parse_fanbox_html(content: str):
    amount_candidates = []
    for p in [
        r'支援額[^\d]*(\d[\d,]+)',
        r'"supportAmount"\s*:\s*(\d+(?:\.\d+)?)',
        r'"transferableAmount"\s*:\s*(\d+(?:\.\d+)?)',
    ]:
        for m in re.finditer(p, content):
            try:
                val = float(m.group(1).replace(",", ""))
                if 1000 <= val < 1e9:
                    amount_candidates.append(val)
            except ValueError:
                pass
    amount = max(amount_candidates) if amount_candidates else None

    patron_candidates = []
    for p in [r'支援者数[^\d]*(\d[\d,]*)', r'"supporterCount"\s*:\s*(\d+)', r'"supportingCount"\s*:\s*(\d+)']:
        for m in re.finditer(p, content):
            try:
                n = int(m.group(1).replace(",", ""))
                if n > 0:
                    patron_candidates.append(n)
            except ValueError:
                pass
    patron_count = max(patron_candidates) if patron_candidates else None

    follower_candidates = []
    for p in [r'フォロワー数[^\d]*(\d[\d,]*)', r'"followerCount"\s*:\s*(\d+)']:
        for m in re.finditer(p, content):
            try:
                n = int(m.group(1).replace(",", ""))
                if n > 0:
                    follower_candidates.append(n)
            except ValueError:
                pass
    follower_count = max(follower_candidates) if follower_candidates else None

    return {"amount": amount, "patron_count": patron_count, "follower_count": follower_count}


def test_takes_max_not_11():
    # 頁面同時有 11 與正確 KPI 時，應取 662 / 27641 / 490850
    html = """
    <span>支援者数</span><b>11</b>
    <span>支援者数</span><b>662</b>
    <span>フォロワー数</span><b>11</b>
    <span>フォロワー数</span><b>27,641</b>
    <span>支援額</span><b>490,850</b>
    """
    out = parse_fanbox_html(html)
    assert out["amount"] == 490850, "amount 應為 490850，實際 %s" % out["amount"]
    assert out["patron_count"] == 662, "支援者数 應為 662，實際 %s" % out["patron_count"]
    assert out["follower_count"] == 27641, "フォロワー数 應為 27641，實際 %s" % out["follower_count"]


def test_662_is_patron_not_amount():
    """662 是支援者数，絕不能當成支援額（金額）"""
    html_bad = """<span>支援額</span><b>662</b><span>支援者数</span><b>662</b>"""
    out = parse_fanbox_html(html_bad)
    # 662 不應進入 amount（我們要求 amount >= 1000）
    assert out["amount"] is None, "662 不得當成金額"
    assert out["patron_count"] == 662


def test_rejects_zero_amount():
    from src.fetchers.fanbox_fetcher import FanboxFetcher
    f = FanboxFetcher("x=y")
    out = f._extract_amount_from_json({"supportAmount": 0, "supporterCount": 11, "followerCount": 11})
    assert out is None, "amount=0 的 JSON 不應被當成有效總覽"


if __name__ == "__main__":
    test_takes_max_not_11()
    test_rejects_zero_amount()
    print("OK: Fanbox 解析測試通過")
