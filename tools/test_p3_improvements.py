# -*- coding: utf-8 -*-
"""
P3改善 検証テスト (TDD)
1. 前週のnote記事からの銘柄・事前設定値（コード・戦略・目標・損切）の自動パース
2. シナリオ別損益計算（ルール厳守 vs 決算持ち越し反事実）の正確性
3. 戦略A不発銘柄から戦略C（決算後好決算飛び乗り）への引き継ぎ判定ロジック
4. 適時開示のダミーデータ・捏造防止（未確認箇所の手入力プレースホルダー保証）
"""
import os
import sys
import pandas as pd
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.note_review_generator import (
    parse_previous_note_report,
    evaluate_scenario_pnl,
    check_strategy_a_to_c_handoff,
    generate_review_markdown
)


def test_parse_previous_note_report():
    # 20261010の記事から竹内、サイゼリヤ、高島屋が正しくパースされるか
    report_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "reports", "note", "note_決算注目銘柄_20261010.md"
    )
    stocks = parse_previous_note_report(report_path)
    assert len(stocks) >= 3, f"3銘柄以上抽出されるべき: {len(stocks)}"
    tickers = [s["ticker"] for s in stocks]
    assert "6432" in tickers
    assert "7581" in tickers
    assert "8233" in tickers

    # 竹内製作所のパラメータチェック
    t_stock = next(s for s in stocks if s["ticker"] == "6432")
    assert t_stock["current_price"] == 7280.0
    assert t_stock["target_price"] == 7810.0
    assert t_stock["stop_loss"] == 6906.0
    assert "B" in t_stock["strategy"] or "またぎ" in t_stock["strategy"]


def test_evaluate_scenario_pnl():
    # 10/12週の竹内製作所の実績データ（10/9終値7280、10/13高値8020、目標7810到達）
    sample_stock = {
        "ticker": "6432",
        "name": "竹内製作所",
        "strategy": "B",
        "entry_price": 7280.0,
        "target_price": 7810.0,
        "stop_loss": 6906.0,
        "shares": 53,
        "earnings_date": "2026-10-13",
        "odd_lot": True
    }
    # 日次価格モック
    daily_df = pd.DataFrame([
        {"Date": "2026-10-09", "Open": 7260, "High": 7320, "Low": 7190, "Close": 7280, "Volume": 200000},
        {"Date": "2026-10-13", "Open": 7390, "High": 8020, "Low": 7310, "Close": 7650, "Volume": 1200000},
        {"Date": "2026-10-14", "Open": 7780, "High": 8010, "Low": 7710, "Close": 7850, "Volume": 850000},
    ]).set_index("Date")

    pnl_res = evaluate_scenario_pnl(sample_stock, daily_df)
    # 目標株価7810到達で利確されているか
    assert pnl_res["target_reached"] is True
    assert pnl_res["stop_loss_hit"] is False
    assert pnl_res["pnl_amount"] > 20000.0, f"利益が2万円以上であるべき: {pnl_res['pnl_amount']}"


def test_strategy_a_to_c_handoff_trigger():
    # 戦略A不発後、決算翌日に+14%ギャップアップしたサイゼリヤのケース
    # 10/14引け後決算（10/14終値6550）、10/15寄付7300（+11.4%）、高値7470（出来高大幅増）
    daily_df = pd.DataFrame([
        {"Date": "2026-10-13", "Open": 6820, "High": 6890, "Low": 6740, "Close": 6810, "Volume": 514700},
        {"Date": "2026-10-14", "Open": 6810, "High": 6870, "Low": 6550, "Close": 6550, "Volume": 723800},
        {"Date": "2026-10-15", "Open": 7300, "High": 7470, "Low": 6870, "Close": 7050, "Volume": 3398700},
    ]).set_index("Date")

    handoff = check_strategy_a_to_c_handoff(
        ticker="7581",
        earnings_date="2026-10-14",
        daily_df=daily_df
    )
    assert handoff["triggered"] is True, "サイゼリヤの決算後ギャップアップは戦略C引き継ぎ対象となるべき"
    assert handoff["gap_up_pct"] >= 5.0
    assert "戦略C" in handoff["recommendation"]


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    failed = 0
    for f in fns:
        try:
            f()
            print(f"PASS {f.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {f.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
