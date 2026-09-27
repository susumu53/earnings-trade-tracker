#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
決算トレード・サイクル予測検証システム
テクニカル分析・上昇予測エンジン (predictor.py)

決算2週間前の銘柄情報、テクニカル指標、波動計算（N/V/E値）から
目標株価・上昇余地(%)・リスクリワード・過去実績照合スコアを自動算出するモジュール
"""

import math
from typing import Dict, Any, Optional
try:
    from tools.db import get_connection
except ImportError:
    from db import get_connection

# 代表的なテクニカルパターン定義
TECHNICAL_PATTERNS = {
    "直近高値ブレイク型": {
        "description": "年初来高値またはレンジ上限をブレイクし上値抵抗線が薄い状態",
        "default_target_method": "V計算値",
        "base_win_rate": 0.65,
        "typical_gain": 18.0
    },
    "25日線押し目反発型": {
        "description": "上昇トレンド中の25日移動平均線付近での下げ止まり・陽線出現",
        "default_target_method": "N計算値",
        "base_win_rate": 0.62,
        "typical_gain": 14.0
    },
    "カップウィズハンドル型": {
        "description": "お椀型の底練りから取手（ハンドル）を形成し、上値ブレイク直前",
        "default_target_method": "E計算値",
        "base_win_rate": 0.68,
        "typical_gain": 22.0
    },
    "ボリンジャースクイーズ型": {
        "description": "ボリンジャーバンドが収束（スクイーズ）し、バンド+2σブレイク目前",
        "default_target_method": "ATR倍率",
        "base_win_rate": 0.60,
        "typical_gain": 16.0
    },
    "ダブルボトム反転型": {
        "description": "直近2点底を付け、ネックラインを突破する底打ち反転形状",
        "default_target_method": "V計算値",
        "base_win_rate": 0.58,
        "typical_gain": 15.0
    }
}


def calculate_wave_targets(current_price: float, low_a: float, high_b: float, pull_c: float) -> Dict[str, float]:
    """
    チャート波動（一目均衡表の基本計算値）による目標株価の計算
    - A: 第1波動安値
    - B: 第1波動高値
    - C: 押し目安値
    """
    targets = {}
    if high_b > low_a and pull_c <= high_b:
        # N計算値: C + (B - A)
        targets["N_target"] = round(pull_c + (high_b - low_a), 1)
        # V計算値: B + (B - C)
        targets["V_target"] = round(high_b + (high_b - pull_c), 1)
        # E計算値: B + (B - A)
        targets["E_target"] = round(high_b + (high_b - low_a), 1)
    else:
        # デフォルトの概算値（高値基準）
        targets["N_target"] = round(current_price * 1.15, 1)
        targets["V_target"] = round(current_price * 1.20, 1)
        targets["E_target"] = round(current_price * 1.25, 1)
    return targets


def calculate_risk_reward(current_price: float, target_price: float, stop_loss: float) -> Dict[str, float]:
    """リスクリワード比および想定リターン・リスク率を算出"""
    if current_price <= 0:
        return {"expected_return_pct": 0.0, "risk_pct": 0.0, "risk_reward_ratio": 0.0}

    reward = target_price - current_price
    risk = current_price - stop_loss

    expected_return_pct = round((reward / current_price) * 100, 2)
    risk_pct = round((risk / current_price) * 100, 2) if risk > 0 else 0.0

    if risk > 0:
        rr_ratio = round(reward / risk, 2)
    else:
        rr_ratio = 99.9  # 損切り幅ゼロ設定時のフォールバック

    return {
        "expected_return_pct": expected_return_pct,
        "risk_pct": risk_pct,
        "risk_reward_ratio": rr_ratio
    }


def query_historical_pattern_stats(technical_pattern: str, min_progress_rate: float = 0.0) -> Dict[str, Any]:
    """
    過去データベースから同一テクニカルパターンおよび業績帯の実績勝率・平均リターンを検索。
    次の決算シーズン予測に過去の蓄積データをフィードバックする。
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # 過去の該当テクニカルパターン実績
        cursor.execute("""
            SELECT 
                COUNT(*) as total_count,
                SUM(CASE WHEN r.win_loss = 'WIN' THEN 1 ELSE 0 END) as win_count,
                AVG(r.max_gain_pct) as avg_max_gain,
                AVG(r.actual_return_pct) as avg_actual_return
            FROM predictions p
            JOIN results r ON p.id = r.prediction_id
            WHERE p.technical_pattern = ?
        """, (technical_pattern,))
        row = cursor.fetchone()
        conn.close()

        if row and row["total_count"] > 0:
            win_rate = round((row["win_count"] / row["total_count"]) * 100, 1)
            avg_gain = round(row["avg_max_gain"] or 0.0, 1)
            return {
                "sample_count": row["total_count"],
                "win_rate": win_rate,
                "avg_gain": avg_gain,
                "data_source": "historical_db"
            }
    except Exception as e:
        pass

    # 過去データがまだ蓄積されていない場合の基準モデル値（デフォルト）
    pattern_info = TECHNICAL_PATTERNS.get(technical_pattern, {
        "base_win_rate": 0.60,
        "typical_gain": 15.0
    })
    return {
        "sample_count": 0,
        "win_rate": round(pattern_info["base_win_rate"] * 100, 1),
        "avg_gain": pattern_info["typical_gain"],
        "data_source": "default_prior"
    }


def evaluate_prediction(
    ticker: str,
    name: str,
    current_price: float,
    target_price: float,
    stop_loss: float,
    technical_pattern: str,
    progress_rate: float = 0.0,
    consensus_status: str = "中立"
) -> Dict[str, Any]:
    """
    ピックアップ銘柄の総合事前評価（予測スコア、推奨度）
    """
    rr = calculate_risk_reward(current_price, target_price, stop_loss)
    hist_stats = query_historical_pattern_stats(technical_pattern, progress_rate)

    # スコアリング（100点満点）
    score = 50.0

    # 1. リスクリワード評価 (最大 +25点)
    rr_ratio = rr["risk_reward_ratio"]
    if rr_ratio >= 3.0:
        score += 25
    elif rr_ratio >= 2.0:
        score += 15
    elif rr_ratio >= 1.5:
        score += 5
    else:
        score -= 15

    # 2. 業績進捗率・コンセンサス評価 (最大 +20点)
    if progress_rate >= 80.0:
        score += 15
    elif progress_rate >= 50.0:
        score += 8

    if consensus_status == "上振れ期待":
        score += 10
    elif consensus_status == "下振れ懸念":
        score -= 20

    # 3. 過去勝率反映 (最大 +15点)
    if hist_stats["win_rate"] >= 70.0:
        score += 15
    elif hist_stats["win_rate"] >= 60.0:
        score += 10
    elif hist_stats["win_rate"] < 50.0:
        score -= 10

    score = max(10.0, min(100.0, score))

    if score >= 80:
        rating = "S (極めて有望)"
    elif score >= 70:
        rating = "A (積極参入)"
    elif score >= 55:
        rating = "B (中立・監視)"
    else:
        rating = "C (見送り推奨)"

    return {
        "ticker": ticker,
        "name": name,
        "current_price": current_price,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "expected_return_pct": rr["expected_return_pct"],
        "risk_pct": rr["risk_pct"],
        "risk_reward_ratio": rr["risk_reward_ratio"],
        "technical_pattern": technical_pattern,
        "progress_rate": progress_rate,
        "consensus_status": consensus_status,
        "score": round(score, 1),
        "rating": rating,
        "historical_stats": hist_stats
    }


if __name__ == "__main__":
    # サンプル計算テスト
    res = evaluate_prediction(
        ticker="6501",
        name="日立製作所",
        current_price=3500.0,
        target_price=4200.0,
        stop_loss=3300.0,
        technical_pattern="直近高値ブレイク型",
        progress_rate=82.5,
        consensus_status="上振れ期待"
    )
    print("Prediction Evaluation Test:")
    for k, v in res.items():
        print(f"  {k}: {v}")
