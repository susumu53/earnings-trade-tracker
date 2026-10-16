# -*- coding: utf-8 -*-
"""
P2改善 検証テスト (TDD)
1. 東証営業日（土日・祝日・年末年始除外）の正確な日数計算
2. 戦略Aにおける実営業日フィルター（決算前日までの実営業日<3日のペナルティ）
3. ミニ株（単元未満株）執行・約定注記の自動追記
4. 戦略Aで業績★1（減益警戒）銘柄の推奨枠除外（または足切り）
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.calendar_util import is_tse_trading_day, get_tse_business_days_between
from tools.auto_screener import evaluate_strategy_a
from tools.note_generator import compute_position_plan, summarize_portfolio, generate_note_markdown, get_upcoming_week_dates


def test_tse_calendar_trading_days():
    # 2026年10月12日（月）はスポーツの日（祝日）
    assert not is_tse_trading_day(date(2026, 10, 12)), "10/12（スポーツの日）は休場日であるべき"
    # 2026年10月13日（火）は平日営業日
    assert is_tse_trading_day(date(2026, 10, 13)), "10/13は東証営業日であるべき"
    # 土日は休場
    assert not is_tse_trading_day(date(2026, 10, 17)), "10/17（土）は休場日であるべき"
    assert not is_tse_trading_day(date(2026, 10, 18)), "10/18（日）は休場日であるべき"
    # 年末年始
    assert not is_tse_trading_day(date(2026, 12, 31)), "12/31は大納会翌日休場であるべき"
    assert not is_tse_trading_day(date(2027, 1, 1)), "1/1は休場日であるべき"
    assert not is_tse_trading_day(date(2027, 1, 2)), "1/2は休場日であるべき"
    assert not is_tse_trading_day(date(2027, 1, 3)), "1/3は休場日であるべき"


def test_count_business_days():
    # 2026年10月9日（金）から10月14日（水・サイゼリヤ決算日）まで
    # 10/10(土), 10/11(日), 10/12(月・祝) は休場。
    # 営業日は 10/13(火), 10/14(水) の2営業日
    b_days = get_tse_business_days_between(date(2026, 10, 9), date(2026, 10, 14))
    assert b_days == 2, f"10/9〜10/14の東証営業日は2日のはずが {b_days}日"


def test_strategy_a_trading_days_filter():
    # 決算前日までの営業日が1日しかない場合（先回り期間不足）は大幅減点されるか
    sample_data = {
        "current_price": 2000.0,
        "expected_return_pct": 10.0,
        "risk_reward_ratio": 2.5,
        "technical_pattern": "25日線押し目反発型",
        "ma25": 1980.0,
        "ma75": 1900.0,
        "ma25_bias_pct": 1.0,
        "volume_ratio": 1.5,
        "market_cap": 300_000_000_000,
        "revision_stars": 4,
        "revision_probability": "★★★★ 有望 (利益成長+15%超)",
    }
    # 暦日4日でも営業日1日の場合
    res_short = evaluate_strategy_a(sample_data, days_until=4, business_days_until=2)
    # 通常の営業日4日の場合
    res_normal = evaluate_strategy_a(sample_data, days_until=6, business_days_until=4)
    assert res_normal["score"] > res_short["score"], "営業日不足の銘柄はスコアが下がるべき"
    assert "営業日" in " ".join(res_short["reasons"]), "理由欄に営業日数への言及があるべき"


def test_mini_stock_execution_notes_included_in_note():
    # 単元未満株推奨銘柄が含まれる場合、成行約定・終値判定ルールの注記がMarkdownに含まれるか
    opps = [{
        "ticker": "6146",
        "name": "ディスコ",
        "sector": "機械",
        "strategy_name": "戦略B: 決算またぎ上方修正",
        "current_price": 50000.0,
        "target_price": 60000.0,
        "stop_loss": 48000.0,
        "expected_return_pct": 20.0,
        "risk_reward_ratio": 5.0,
        "score": 80.0,
        "rank": "S",
        "technical_pattern": "ダブルボトム反転型",
        "earnings_date": "2026-10-22",
        "days_until_earnings": 5,
        "business_days_until": 4,
        "trade_action": "テストアクション",
        "reasons": ["テスト理由"]
    }]
    week_info = get_upcoming_week_dates()
    md = generate_note_markdown(opps, week_info)
    assert "成行約定" in md or "指値不可" in md or "単元未満株（ミニ株）" in md
    assert "終値" in md or "寄り" in md


def test_strategy_a_declining_earnings_excluded_from_recommended_portfolio():
    # 戦略Aで業績★1（減益警戒）の銘柄は、テクニカルスコアが高くても同時保有枠（selected）から除外されること
    opps = [
        {"ticker": "7970", "name": "信越ポリマー", "current_price": 2377, "stop_loss": 2261, "target_price": 2767,
         "score": 85.0, "strategy": "A", "revision_stars": 1},
        {"ticker": "4063", "name": "信越化学工業", "current_price": 5978, "stop_loss": 5745, "target_price": 6667,
         "score": 85.0, "strategy": "A", "revision_stars": 3},
        {"ticker": "8697", "name": "日本取引所G", "current_price": 2219, "stop_loss": 2096, "target_price": 2394,
         "score": 65.0, "strategy": "A", "revision_stars": 4},
    ]
    plans = [compute_position_plan(o) for o in opps]
    summary = summarize_portfolio(opps, plans, capital=1_000_000, max_total_risk_pct=6.0)
    assert "7970" not in summary["selected"], "減益警戒（★1）の戦略A銘柄は同時保有推奨枠から除外されるべき"
    assert "4063" in summary["selected"], "健全銘柄（★3）は採用されるべき"


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
