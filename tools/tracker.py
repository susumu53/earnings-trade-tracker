#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
決算トレード・サイクル予測検証システム
決算後1週間結果トラッカー・検証エンジン (tracker.py)

決算発表後1週間の株価推移（寄り付き、高値、安値、終値）から
最大上昇率、実獲得リターン、目標達成可否、勝敗判定、成因分析を自動計算しDBに記録するモジュール
"""

from typing import Dict, Any, Optional
try:
    from tools.db import add_or_update_result, get_prediction_by_id
except ImportError:
    from db import add_or_update_result, get_prediction_by_id


def evaluate_and_record_result(
    prediction_id: int,
    earnings_actual_date: str,
    post_open_price: float,
    week_high_price: float,
    week_low_price: float,
    week_close_price: float,
    earnings_result_type: str,
    review_notes: str = ""
) -> Dict[str, Any]:
    """
    決算後1週間の結果を検証・集計してデータベースに保存
    """
    pred = get_prediction_by_id(prediction_id)
    if not pred:
        raise ValueError(f"Prediction ID {prediction_id} が見つかりません。")

    entry_price = float(pred["current_price"])
    target_price = float(pred["target_price"])
    stop_loss = float(pred["stop_loss"])

    # 1. パフォーマンス計算
    # 最大上昇率（エントリー株価から1週間の最高値まで）
    max_gain_pct = round(((week_high_price - entry_price) / entry_price) * 100, 2)
    # 実損益率（エントリー株価から1週間後終値まで）
    actual_return_pct = round(((week_close_price - entry_price) / entry_price) * 100, 2)
    # 寄り付きギャップ率
    gap_open_pct = round(((post_open_price - entry_price) / entry_price) * 100, 2)

    # 2. 達成判定
    target_hit = 1 if week_high_price >= target_price else 0
    stop_hit = 1 if week_low_price <= stop_loss else 0

    # 3. 勝敗判定ロジック
    # 目標達成または+5%以上の上昇で損切り未抵触ならWIN
    if target_hit == 1 or (actual_return_pct >= 5.0 and stop_hit == 0):
        win_loss = "WIN"
    elif stop_hit == 1 or actual_return_pct <= -4.0:
        win_loss = "LOSS"
    else:
        win_loss = "DRAW"

    # 目標株価に対する達成率（%）
    expected_diff = target_price - entry_price
    if expected_diff > 0:
        actual_diff = week_high_price - entry_price
        target_achievement_pct = round((actual_diff / expected_diff) * 100, 1)
    else:
        target_achievement_pct = 100.0 if target_hit else 0.0

    result_data = {
        "prediction_id": prediction_id,
        "earnings_actual_date": earnings_actual_date,
        "post_open_price": post_open_price,
        "week_high_price": week_high_price,
        "week_low_price": week_low_price,
        "week_close_price": week_close_price,
        "max_gain_pct": max_gain_pct,
        "actual_return_pct": actual_return_pct,
        "target_hit": target_hit,
        "stop_hit": stop_hit,
        "earnings_result_type": earnings_result_type,
        "win_loss": win_loss,
        "review_notes": review_notes
    }

    # DBに保存
    res_id = add_or_update_result(result_data)

    return {
        "result_id": res_id,
        "prediction_id": prediction_id,
        "ticker": pred["ticker"],
        "name": pred["name"],
        "entry_price": entry_price,
        "target_price": target_price,
        "gap_open_pct": gap_open_pct,
        "max_gain_pct": max_gain_pct,
        "actual_return_pct": actual_return_pct,
        "target_hit": bool(target_hit),
        "stop_hit": bool(stop_hit),
        "target_achievement_pct": target_achievement_pct,
        "win_loss": win_loss,
        "earnings_result_type": earnings_result_type,
        "review_notes": review_notes
    }


if __name__ == "__main__":
    print("Tracker module loaded successfully.")
