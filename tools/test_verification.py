#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""統合検証スクリプト"""
import sys
import os

sys.path.insert(0, ".")

from tools.universe import get_all_tse_stocks
from tools.earnings_scanner import scan_earnings_dates_bulk
from tools.auto_screener import auto_screen_upcoming_opportunities

def test_universe():
    stocks = get_all_tse_stocks()
    print(f"[TEST 1] Universe stocks count: {len(stocks)}")
    assert len(stocks) >= 3000, f"Expected >= 3000 stocks, got {len(stocks)}"
    print("  -> PASSED: 東証全銘柄が正常に取得されています。")

def test_earnings_scanner():
    hits, stats = scan_earnings_dates_bulk(days_min=0, days_max=14, force_refresh=True)
    print(f"[TEST 2] Earnings hits count: {len(hits)}")
    print(f"  Scan stats: {stats}")
    assert len(hits) > 0, "No earnings hits found!"
    # 全件の日数が 0〜14 日後であることを確認
    for h in hits:
        days = h["days_until"]
        assert 0 <= days <= 14, f"Invalid days_until: {days} for {h['code']}"
    print(f"  -> PASSED: すべての銘柄が決算当日〜14日後 (0〜14日) の範囲内です。")

def test_auto_screener():
    opps = auto_screen_upcoming_opportunities(max_results=10)
    print(f"[TEST 3] Auto screen opportunities count: {len(opps)}")
    assert len(opps) > 0, "No opportunities found!"
    for o in opps:
        assert 0 <= o["days_until_earnings"] <= 14
        print(f"  - [{o['ticker']}] {o['name']} | 決算日: {o['earnings_date']} (あと{o['days_until_earnings']}日) | スコア: {o['score']}pt ({o['rank']})")
    print("  -> PASSED: スクリーナーが正常にピックアップ完了。")

if __name__ == "__main__":
    print("=== 全体検証テスト開始 ===")
    test_universe()
    test_earnings_scanner()
    test_auto_screener()
    print("=== 全検証テスト合格 ===")
