#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
決算トレード・サイクル予測検証システム
検証用サンプルデータ生成 (seed_data.py)

/* DUMMY DATA */
初期動作確認およびシーズン学習エンジンの統計検証を行うための
過去シーズン（2025Q3, 2025Q4）および今期（2026Q1）のサンプルデータ投入モジュール
"""

from datetime import datetime, timedelta
try:
    from tools.db import init_db, add_prediction, add_or_update_result, get_connection
except ImportError:
    from db import init_db, add_prediction, add_or_update_result, get_connection


# /* DUMMY DATA */
# 過去の決算トレード検証用シミュレーションデータ
SAMPLE_RECORDS = [
    {
        "pred": {
            "season_id": "2025Q3",
            "ticker": "6857",
            "name": "アドバンテスト",
            "sector": "半導体製造装置",
            "pick_date": "2025-07-15",
            "earnings_date": "2025-07-30",
            "current_price": 5400.0,
            "target_price": 6500.0,
            "stop_loss": 5050.0,
            "expected_return_pct": 20.37,
            "risk_reward_ratio": 3.14,
            "technical_pattern": "直近高値ブレイク型",
            "progress_rate": 84.2,
            "consensus_status": "上振れ期待",
            "notes": "直近高値を陽線でブレイク、出来高急増。コンセンサスも大幅切り上げ観測あり。",
            "status": "completed"
        },
        "res": {
            "earnings_actual_date": "2025-07-30",
            "post_open_price": 5950.0,
            "week_high_price": 6620.0,
            "week_low_price": 5850.0,
            "week_close_price": 6480.0,
            "max_gain_pct": 22.59,
            "actual_return_pct": 20.0,
            "target_hit": 1,
            "stop_hit": 0,
            "earnings_result_type": "大幅上方修正+増配",
            "win_loss": "WIN",
            "review_notes": "好決算に素直に反応しギャップアップ。目標株価を4営業日目に完全達成。"
        }
    },
    {
        "pred": {
            "season_id": "2025Q3",
            "ticker": "6501",
            "name": "日立製作所",
            "sector": "電気機器",
            "pick_date": "2025-07-14",
            "earnings_date": "2025-07-28",
            "current_price": 3400.0,
            "target_price": 3950.0,
            "stop_loss": 3220.0,
            "expected_return_pct": 16.18,
            "risk_reward_ratio": 3.06,
            "technical_pattern": "25日線押し目反発型",
            "progress_rate": 78.5,
            "consensus_status": "上振れ期待",
            "notes": "25日線で反発の十字線形成。Lumada事業好調継続の観測。",
            "status": "completed"
        },
        "res": {
            "earnings_actual_date": "2025-07-28",
            "post_open_price": 3600.0,
            "week_high_price": 3980.0,
            "week_low_price": 3520.0,
            "week_close_price": 3890.0,
            "max_gain_pct": 17.06,
            "actual_return_pct": 14.41,
            "target_hit": 1,
            "stop_hit": 0,
            "earnings_result_type": "通期上方修正",
            "win_loss": "WIN",
            "review_notes": "押し目からのN波動ターゲット(3950円)を綺麗に達成。"
        }
    },
    {
        "pred": {
            "season_id": "2025Q3",
            "ticker": "9984",
            "name": "ソフトバンクグループ",
            "sector": "情報・通信",
            "pick_date": "2025-07-25",
            "earnings_date": "2025-08-07",
            "current_price": 8200.0,
            "target_price": 9600.0,
            "stop_loss": 7700.0,
            "expected_return_pct": 17.07,
            "risk_reward_ratio": 2.8,
            "technical_pattern": "カップウィズハンドル型",
            "progress_rate": 62.0,
            "consensus_status": "一致見込み",
            "notes": "取手部分を出来高減で形成。AI投資の含み益拡大期待。",
            "status": "completed"
        },
        "res": {
            "earnings_actual_date": "2025-08-07",
            "post_open_price": 8100.0,
            "week_high_price": 8350.0,
            "week_low_price": 7600.0,
            "week_close_price": 7650.0,
            "max_gain_pct": 1.83,
            "actual_return_pct": -6.71,
            "target_hit": 0,
            "stop_hit": 1,
            "earnings_result_type": "自社株買い見送り/失望",
            "win_loss": "LOSS",
            "review_notes": "期待された自社株買いの発表がなく失望売り。損切りライン7700円到達で機械的撤退。"
        }
    },
    {
        "pred": {
            "season_id": "2025Q4",
            "ticker": "6920",
            "name": "レーザーテック",
            "sector": "精密機器",
            "pick_date": "2025-10-16",
            "earnings_date": "2025-10-31",
            "current_price": 22000.0,
            "target_price": 26500.0,
            "stop_loss": 20800.0,
            "expected_return_pct": 20.45,
            "risk_reward_ratio": 3.75,
            "technical_pattern": "直近高値ブレイク型",
            "progress_rate": 88.0,
            "consensus_status": "上振れ期待",
            "notes": "高値保ち合いからの上放れ。受注残高の高水準維持が濃厚。",
            "status": "completed"
        },
        "res": {
            "earnings_actual_date": "2025-10-31",
            "post_open_price": 24200.0,
            "week_high_price": 27100.0,
            "week_low_price": 23500.0,
            "week_close_price": 26300.0,
            "max_gain_pct": 23.18,
            "actual_return_pct": 19.55,
            "target_hit": 1,
            "stop_hit": 0,
            "earnings_result_type": "最高益更新+上方修正",
            "win_loss": "WIN",
            "review_notes": "受注残高の強さからショートカバーを巻き込み大幅上昇。"
        }
    },
    {
        "pred": {
            "season_id": "2025Q4",
            "ticker": "8035",
            "name": "東京エレクトロン",
            "sector": "電気機器",
            "pick_date": "2025-10-24",
            "earnings_date": "2025-11-08",
            "current_price": 26000.0,
            "target_price": 30000.0,
            "stop_loss": 24500.0,
            "expected_return_pct": 15.38,
            "risk_reward_ratio": 2.67,
            "technical_pattern": "カップウィズハンドル型",
            "progress_rate": 81.3,
            "consensus_status": "上振れ期待",
            "notes": "綺麗なカップウィズハンドル形成完了。WSTS世界半導体予測の引き上げも追い風。",
            "status": "completed"
        },
        "res": {
            "earnings_actual_date": "2025-11-08",
            "post_open_price": 28500.0,
            "week_high_price": 30800.0,
            "week_low_price": 27800.0,
            "week_close_price": 30200.0,
            "max_gain_pct": 18.46,
            "actual_return_pct": 16.15,
            "target_hit": 1,
            "stop_hit": 0,
            "earnings_result_type": "上方修正+自社株買い",
            "win_loss": "WIN",
            "review_notes": "自社株買い発表も重なりカップブレイクの目標30000円を完全突破。"
        }
    },
    {
        "pred": {
            "season_id": "2026Q1",
            "ticker": "7011",
            "name": "三菱重工業",
            "sector": "機械",
            "pick_date": "2026-01-20",
            "earnings_date": "2026-02-05",
            "current_price": 2100.0,
            "target_price": 2550.0,
            "stop_loss": 1960.0,
            "expected_return_pct": 21.43,
            "risk_reward_ratio": 3.21,
            "technical_pattern": "直近高値ブレイク型",
            "progress_rate": 85.0,
            "consensus_status": "上振れ期待",
            "notes": "防衛・ガスタービン好調。高値圏三角保ち合い上放れ。",
            "status": "pending"
        }
    }
]


def seed_sample_data() -> int:
    """初期検証用サンプルデータを投入"""
    init_db()
    count = 0
    for item in SAMPLE_RECORDS:
        pred_data = item["pred"]
        pred_id = add_prediction(pred_data)
        count += 1
        if "res" in item:
            res_data = item["res"]
            res_data["prediction_id"] = pred_id
            add_or_update_result(res_data)
    return count


if __name__ == "__main__":
    inserted = seed_sample_data()
    print(f"/* DUMMY DATA */ {inserted} 件のサンプルデータをDBに投入しました。")
