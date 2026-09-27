#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
決算トレード・サイクル予測検証システム
データベース層 (db.py)

SQLiteを用いた予測レコードおよび決算後1週間結果の永続化・集計インターフェース
"""

import os
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "earnings_trade.db")


def get_connection():
    """SQLiteデータベース接続を取得（フォルダが無ければ自動作成）"""
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """テーブルの初期化"""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. 予測テーブル
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        season_id TEXT NOT NULL,
        ticker TEXT NOT NULL,
        name TEXT NOT NULL,
        sector TEXT DEFAULT '',
        pick_date TEXT NOT NULL,
        earnings_date TEXT NOT NULL,
        current_price REAL NOT NULL,
        target_price REAL NOT NULL,
        stop_loss REAL NOT NULL,
        expected_return_pct REAL NOT NULL,
        risk_reward_ratio REAL NOT NULL,
        technical_pattern TEXT NOT NULL,
        progress_rate REAL DEFAULT 0.0,
        consensus_status TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        status TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL
    );
    """)

    # 2. 結果テーブル
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prediction_id INTEGER UNIQUE NOT NULL,
        earnings_actual_date TEXT NOT NULL,
        post_open_price REAL NOT NULL,
        week_high_price REAL NOT NULL,
        week_low_price REAL NOT NULL,
        week_close_price REAL NOT NULL,
        max_gain_pct REAL NOT NULL,
        actual_return_pct REAL NOT NULL,
        target_hit INTEGER NOT NULL DEFAULT 0,
        stop_hit INTEGER NOT NULL DEFAULT 0,
        earnings_result_type TEXT DEFAULT '',
        win_loss TEXT NOT NULL,
        review_notes TEXT DEFAULT '',
        recorded_at TEXT NOT NULL,
        FOREIGN KEY (prediction_id) REFERENCES predictions(id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    conn.close()


def add_prediction(data: Dict[str, Any]) -> int:
    """新規の決算前ピックアップ・予測を登録"""
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    INSERT INTO predictions (
        season_id, ticker, name, sector, pick_date, earnings_date,
        current_price, target_price, stop_loss, expected_return_pct,
        risk_reward_ratio, technical_pattern, progress_rate,
        consensus_status, notes, status, created_at
    ) VALUES (
        :season_id, :ticker, :name, :sector, :pick_date, :earnings_date,
        :current_price, :target_price, :stop_loss, :expected_return_pct,
        :risk_reward_ratio, :technical_pattern, :progress_rate,
        :consensus_status, :notes, :status, :created_at
    )
    """, {
        "season_id": data.get("season_id", "2026Q1"),
        "ticker": data["ticker"],
        "name": data.get("name", ""),
        "sector": data.get("sector", ""),
        "pick_date": data.get("pick_date", datetime.now().strftime("%Y-%m-%d")),
        "earnings_date": data["earnings_date"],
        "current_price": float(data["current_price"]),
        "target_price": float(data["target_price"]),
        "stop_loss": float(data["stop_loss"]),
        "expected_return_pct": float(data.get("expected_return_pct", 0.0)),
        "risk_reward_ratio": float(data.get("risk_reward_ratio", 0.0)),
        "technical_pattern": data.get("technical_pattern", "ブレイクアウト型"),
        "progress_rate": float(data.get("progress_rate", 0.0)),
        "consensus_status": data.get("consensus_status", "中立"),
        "notes": data.get("notes", ""),
        "status": data.get("status", "pending"),
        "created_at": now_str
    })
    pred_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return pred_id


def add_predictions_batch(items: List[Dict[str, Any]]) -> List[int]:
    """複数の予測銘柄を一括してトランザクションで登録"""
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    inserted_ids = []

    for data in items:
        cursor.execute("""
        INSERT INTO predictions (
            season_id, ticker, name, sector, pick_date, earnings_date,
            current_price, target_price, stop_loss, expected_return_pct,
            risk_reward_ratio, technical_pattern, progress_rate,
            consensus_status, notes, status, created_at
        ) VALUES (
            :season_id, :ticker, :name, :sector, :pick_date, :earnings_date,
            :current_price, :target_price, :stop_loss, :expected_return_pct,
            :risk_reward_ratio, :technical_pattern, :progress_rate,
            :consensus_status, :notes, :status, :created_at
        )
        """, {
            "season_id": data.get("season_id", "2026Q3"),
            "ticker": data["ticker"],
            "name": data.get("name", ""),
            "sector": data.get("sector", ""),
            "pick_date": data.get("pick_date", datetime.now().strftime("%Y-%m-%d")),
            "earnings_date": data["earnings_date"],
            "current_price": float(data["current_price"]),
            "target_price": float(data["target_price"]),
            "stop_loss": float(data["stop_loss"]),
            "expected_return_pct": float(data.get("expected_return_pct", 0.0)),
            "risk_reward_ratio": float(data.get("risk_reward_ratio", 0.0)),
            "technical_pattern": data.get("technical_pattern", "ブレイクアウト型"),
            "progress_rate": float(data.get("progress_rate", 0.0)),
            "consensus_status": data.get("consensus_status", "中立"),
            "notes": data.get("notes", ""),
            "status": data.get("status", "pending"),
            "created_at": now_str
        })
        inserted_ids.append(cursor.lastrowid)

    conn.commit()
    conn.close()
    return inserted_ids



def add_or_update_result(data: Dict[str, Any]) -> int:
    """決算後1週間の結果を登録・更新し、予測レコードのステータスをcompletedにする"""
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    INSERT INTO results (
        prediction_id, earnings_actual_date, post_open_price,
        week_high_price, week_low_price, week_close_price,
        max_gain_pct, actual_return_pct, target_hit, stop_hit,
        earnings_result_type, win_loss, review_notes, recorded_at
    ) VALUES (
        :prediction_id, :earnings_actual_date, :post_open_price,
        :week_high_price, :week_low_price, :week_close_price,
        :max_gain_pct, :actual_return_pct, :target_hit, :stop_hit,
        :earnings_result_type, :win_loss, :review_notes, :recorded_at
    )
    ON CONFLICT(prediction_id) DO UPDATE SET
        earnings_actual_date=excluded.earnings_actual_date,
        post_open_price=excluded.post_open_price,
        week_high_price=excluded.week_high_price,
        week_low_price=excluded.week_low_price,
        week_close_price=excluded.week_close_price,
        max_gain_pct=excluded.max_gain_pct,
        actual_return_pct=excluded.actual_return_pct,
        target_hit=excluded.target_hit,
        stop_hit=excluded.stop_hit,
        earnings_result_type=excluded.earnings_result_type,
        win_loss=excluded.win_loss,
        review_notes=excluded.review_notes,
        recorded_at=excluded.recorded_at
    """, {
        "prediction_id": data["prediction_id"],
        "earnings_actual_date": data["earnings_actual_date"],
        "post_open_price": float(data["post_open_price"]),
        "week_high_price": float(data["week_high_price"]),
        "week_low_price": float(data["week_low_price"]),
        "week_close_price": float(data["week_close_price"]),
        "max_gain_pct": float(data["max_gain_pct"]),
        "actual_return_pct": float(data["actual_return_pct"]),
        "target_hit": 1 if data.get("target_hit") else 0,
        "stop_hit": 1 if data.get("stop_hit") else 0,
        "earnings_result_type": data.get("earnings_result_type", ""),
        "win_loss": data.get("win_loss", "WIN"),
        "review_notes": data.get("review_notes", ""),
        "recorded_at": now_str
    })
    res_id = cursor.lastrowid

    # 予測ステータスを完了に更新
    cursor.execute("""
    UPDATE predictions SET status = 'completed' WHERE id = ?
    """, (data["prediction_id"],))

    conn.commit()
    conn.close()
    return res_id


def get_all_records(season_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """予測と結果を結合した一覧を取得"""
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT 
        p.id AS pred_id, p.season_id, p.ticker, p.name, p.sector,
        p.pick_date, p.earnings_date, p.current_price, p.target_price,
        p.stop_loss, p.expected_return_pct, p.risk_reward_ratio,
        p.technical_pattern, p.progress_rate, p.consensus_status,
        p.notes AS pred_notes, p.status, p.created_at,
        r.id AS res_id, r.earnings_actual_date, r.post_open_price,
        r.week_high_price, r.week_low_price, r.week_close_price,
        r.max_gain_pct, r.actual_return_pct, r.target_hit, r.stop_hit,
        r.earnings_result_type, r.win_loss, r.review_notes, r.recorded_at
    FROM predictions p
    LEFT JOIN results r ON p.id = r.prediction_id
    """
    params = []
    if season_id:
        query += " WHERE p.season_id = ?"
        params.append(season_id)
    query += " ORDER BY p.earnings_date ASC, p.id DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    results = [dict(row) for row in rows]
    conn.close()
    return results


def get_prediction_by_id(pred_id: int) -> Optional[Dict[str, Any]]:
    """特定の予測レコードを取得"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM predictions WHERE id = ?", (pred_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_prediction(pred_id: int) -> bool:
    """予測（および紐づく結果）を削除"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM results WHERE prediction_id = ?", (pred_id,))
    cursor.execute("DELETE FROM predictions WHERE id = ?", (pred_id,))
    conn.commit()
    conn.close()
    return True


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", DB_PATH)
