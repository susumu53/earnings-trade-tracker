# -*- coding: utf-8 -*-
"""
P1改善 検証テスト (TDD)
1. 戦略Aの根拠ラベルが数値に応じて条件分岐する（固定文言「先回り買い検出」の廃止）
2. 戦略Aに業績ペナルティ（★1=-15点 / ★2=-5点）が入る
3. 業績星評価と純利益成長率の矛盾解消（増収だけで「利益成長+15%超」と表示しない）
4. ポートフォリオ全体の資金枠（合計代金≦元本 / 合計リスク≦6%）チェック
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.auto_screener import evaluate_strategy_a
from tools.market_data import classify_revision
from tools.note_generator import compute_position_plan, summarize_portfolio


def _base_a(**over):
    d = {
        "current_price": 2000.0,
        "expected_return_pct": 10.0,
        "risk_reward_ratio": 2.5,
        "technical_pattern": "25日線押し目反発型",
        "ma25": 1980.0,
        "ma75": 1900.0,
        "ma25_bias_pct": 1.0,
        "volume_ratio": 1.5,
        "market_cap": 300_000_000_000,
        "revision_stars": 3,
        "revision_probability": "★★★ 標準 (巡航増益ペース)",
    }
    d.update(over)
    return d


# ---------- 1. 条件付きラベル ----------
def test_low_volume_not_labeled_as_accumulation():
    res = evaluate_strategy_a(_base_a(volume_ratio=0.9), days_until=8)
    text = " ".join(res["reasons"])
    assert "先回り買い検出" not in text, text
    assert "閑散" in text, text


def test_high_volume_labeled_as_accumulation():
    res = evaluate_strategy_a(_base_a(volume_ratio=1.5), days_until=8)
    assert "先回り買い検出" in " ".join(res["reasons"])


def test_negative_bias_not_labeled_healthy_overheat():
    res = evaluate_strategy_a(_base_a(ma25_bias_pct=-0.6), days_until=8)
    text = " ".join(res["reasons"])
    assert "過熱前の健全水準" not in text, text
    assert "押し目" in text, text


def test_label_matches_displayed_rounded_value():
    # 0.97倍は「1.0倍」と表示されるため「閑散」と書いてはならない
    res = evaluate_strategy_a(_base_a(volume_ratio=0.97), days_until=8)
    text = " ".join(res["reasons"])
    assert "1.0倍（平常水準）" in text, text


# ---------- 2. 戦略Aの業績ペナルティ ----------
def test_strategy_a_penalizes_declining_earnings():
    # 出来高1.1倍（12点）にして素点を92点に抑え、上限98点への張り付きを避ける
    good = evaluate_strategy_a(_base_a(revision_stars=4, volume_ratio=1.1), days_until=8)
    bad = evaluate_strategy_a(_base_a(revision_stars=1, volume_ratio=1.1,
                                      revision_probability="★ 警戒 (減益・下方修正リスク)"),
                              days_until=8)
    assert good["score"] - bad["score"] >= 15.0, (good["score"], bad["score"])
    assert "警戒" in " ".join(bad["reasons"])


# ---------- 3. 星評価の整合性 ----------
def test_revenue_only_growth_does_not_claim_profit_growth():
    label, stars = classify_revision(earnings_growth=0.2, revenue_growth=12.0, consensus_status="中立")
    assert stars <= 3, (label, stars)
    assert "利益成長+15%超" not in label, label


def test_real_profit_growth_still_rated_high():
    label, stars = classify_revision(earnings_growth=35.0, revenue_growth=5.0, consensus_status="中立")
    assert stars == 5, (label, stars)


# ---------- 4. ポートフォリオ資金枠 ----------
def _opp(ticker, price, stop, target, score):
    return {"ticker": ticker, "name": ticker, "current_price": price,
            "stop_loss": stop, "target_price": target, "score": score}


def test_portfolio_detects_capital_overflow_and_selects_within_limit():
    # 10/10記事の3銘柄（竹内・サイゼリヤ・高島屋）
    opps = [
        _opp("6432", 7280, 6906, 7810, 55.0),
        _opp("7581", 6730, 6363, 7170, 57.0),
        _opp("8233", 2141, 2058, 2276, 69.0),
    ]
    plans = [compute_position_plan(o) for o in opps]
    summary = summarize_portfolio(opps, plans, capital=1_000_000, max_total_risk_pct=6.0)

    assert summary["total_cost"] == 385_840 + 363_420 + 428_200
    assert summary["over_capital"] is True
    sel_cost = sum(p["cost"] for o, p in zip(opps, plans) if o["ticker"] in summary["selected"])
    sel_risk = sum(p["risk"] for o, p in zip(opps, plans) if o["ticker"] in summary["selected"])
    assert sel_cost <= 1_000_000
    assert sel_risk <= 60_000
    # スコア上位から採用される
    assert summary["selected"][0] == "8233"


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
