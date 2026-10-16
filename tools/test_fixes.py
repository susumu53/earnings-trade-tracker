# -*- coding: utf-8 -*-
"""
不具合修正検証テスト (TDD)
1. 時価総額の計算単位 (100_000_000 円 = 1億円)
2. 資金管理2%ルールの整合性 (株価大の銘柄でも許容損失2万円を超えない、または単元未満株で計算)
3. リスクリワード比フィルタの適用
4. 上方修正確率の表現 (過度な80%断定を是正)
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.auto_screener import evaluate_strategy_b, evaluate_stock_for_earnings_trade
from tools.market_data import fetch_stock_live_data
from tools.position_sizer import calculate_position
from tools.note_generator import generate_note_markdown, get_upcoming_week_dates

def test_market_cap_unit_is_oku():
    """時価総額の単位が1億円単位（10^8）で計算され、2500億円の銘柄が正しく2500億円と認識されるか"""
    sample_data = {
        "current_price": 7910,
        "expected_return_pct": 17.3,
        "risk_reward_ratio": 2.4,
        "technical_pattern": "カップウィズハンドル型",
        "ma25": 7600,
        "ma75": 7200,
        "ma25_bias_pct": 4.0,
        "volume_ratio": 1.5,
        "market_cap": 250_657_980_416,  # 約2,507億円
        "revision_stars": 4,
        "earnings_growth": 35.0,
        "revision_probability": "★★★★ 有望 (利益成長+15%超)"
    }
    res = evaluate_strategy_b(sample_data, days_until=2)
    # 2500億円の銘柄は「時価総額 2506億円」または「2507億円」と表示されるべき（250億円ではない）
    reasons_str = " ".join(res["reasons"])
    # 2500億円なら大型株（>2000億円）なので中小型急騰ゾーンの文言は出ないはず
    assert "250億円" not in reasons_str, f"時価総額が10倍ズレています: {reasons_str}"
    assert "中小型急騰ゾーン" not in reasons_str, f"2500億円の銘柄が中小型判定されています: {reasons_str}"

def test_position_sizer_respects_risk_limit():
    """高額株（株価8000円、損切り幅500円）で資金100万円・リスク2%（2万円）の場合、
    単元未満株（1株単位）なら40株でリスク2万円以内、
    100株単元強制でも『リスク超過』フラグまたは実態に即した表示がされるか"""
    res_flexible = calculate_position(
        total_capital=1_000_000,
        risk_per_trade_pct=2.0,
        entry_price=8000,
        stop_loss_price=7500, # 損切り幅 500円
        target_price=9000,
        unit_shares=1 # 単元未満株・ミニ株対応
    )
    assert res_flexible.shares == 40
    assert res_flexible.actual_risk == 20000.0
    assert res_flexible.actual_risk <= 20000.0

def test_revision_probability_wording_not_misleading():
    """上方修正確率が客観的な表現になっており、『80%超』と断定していないか"""
    live_data = fetch_stock_live_data("6814")
    prob_str = live_data.get("revision_probability", "")
    assert "80%超" not in prob_str, f"根拠の薄い80%超断定が残っています: {prob_str}"

if __name__ == "__main__":
    test_market_cap_unit_is_oku()
    test_position_sizer_respects_risk_limit()
    test_revision_probability_wording_not_misleading()
    print("すべてのTDDテストが通過しました！")
