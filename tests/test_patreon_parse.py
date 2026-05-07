"""Patreon 頁面文字含 $1k / $1.1k 時應還原為 1000 / 1100 USD"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.fetchers.playwright_fallback import _parse_patreon_page


def test_compact_k_monthly():
    html = '會籍 $1k／月\n192 收費'
    out = _parse_patreon_page(html)
    assert out is not None
    assert out["amount"] == 1000.0
    assert out["currency"] == "USD"


def test_compact_decimal_k_monthly():
    html = '會籍 $1.1k ／月'
    out = _parse_patreon_page(html)
    assert out is not None
    assert out["amount"] == 1100.0


def test_plain_dollars_unchanged():
    html = '會籍 $925 ／月'
    out = _parse_patreon_page(html)
    assert out is not None
    assert out["amount"] == 925.0


def test_monthly_earnings_json_no_k():
    html = '"monthlyEarnings": 1234\n"patronCount": 50'
    out = _parse_patreon_page(html)
    assert out is not None
    assert out["amount"] == 1234.0


if __name__ == "__main__":
    test_compact_k_monthly()
    test_compact_decimal_k_monthly()
    test_plain_dollars_unchanged()
    test_monthly_earnings_json_no_k()
    print("ok")
