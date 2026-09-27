#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
決算トレード・サイクル予測検証システム
GitHub Pages用 静的ダッシュボードデータ出力スクリプト (export_dashboard.py)

GitHub Actionsまたはローカルで実行され、最新の市場データ・スクリーニング結果・
チャートデータを静的JSONファイル (web/data/dashboard_data.json) として生成します。
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from tools.db import init_db, get_all_records
from tools.auto_screener import auto_screen_upcoming_opportunities
from tools.earnings_scanner import scan_earnings_dates_bulk
from tools.analyzer import generate_season_analysis, generate_markdown_report
from tools.market_data import fetch_stock_chart_data
from tools.predictor import TECHNICAL_PATTERNS


def export_dashboard_data(output_path: str = None) -> str:
    print("=" * 60)
    print("  📊 決算トレード 静的ダッシュボードデータ エクスポート開始")
    print("=" * 60)

    # 1. DB初期化
    init_db()

    # 2. 日本時間 (JST) の取得
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst).strftime("%Y-%m-%d %H:%M:%S (JST)")

    # 3. 3大戦略スクリーニング実行 (当日から14日以内)
    print("🔍 決算直前銘柄スクリーニング中...")
    try:
        opportunities = auto_screen_upcoming_opportunities(force_refresh=True)
        print(f"  -> 抽出銘柄数: {len(opportunities)} 件")
    except Exception as e:
        print(f"  [警告] スクリーニング中にエラー: {e}")
        opportunities = []

    # 4. 決算スキャン統計
    print("📅 決算スケジュール統計取得中...")
    try:
        _, scan_stats = scan_earnings_dates_bulk(days_min=0, days_max=14)
    except Exception as e:
        print(f"  [警告] スキャン統計取得エラー: {e}")
        scan_stats = {"total_scheduled": 0, "target_window": 0}

    # 5. 登録済みレコード・分析レポート取得
    records = get_all_records()
    analysis = generate_season_analysis()
    markdown_report = generate_markdown_report()

    # 6. チャートデータの事前キャッシュ (上位銘柄)
    chart_cache = {}
    print("📈 上位銘柄のチャートデータを事前取得中...")
    top_tickers = set()
    for opp in opportunities[:40]:  # 上位40銘柄
        t = opp.get("ticker")
        if t:
            top_tickers.add(t)

    for ticker in top_tickers:
        try:
            c_data = fetch_stock_chart_data(ticker, period="6mo")
            if c_data.get("candles"):
                chart_cache[ticker] = c_data
                print(f"  - {ticker}: {len(c_data['candles'])} 日分キャッシュ完了")
        except Exception as e:
            print(f"  - {ticker}: チャート取得スキップ ({e})")

    # 7. 全体データ構造の構築
    export_payload = {
        "status": "success",
        "updated_at": now_jst,
        "is_static": True,
        "scan_stats": scan_stats,
        "opportunities": opportunities,
        "records": records,
        "analysis": analysis,
        "markdown_report": markdown_report,
        "technical_patterns": TECHNICAL_PATTERNS,
        "charts": chart_cache,
    }

    if output_path is None:
        web_data_dir = os.path.join(BASE_DIR, "web", "data")
        os.makedirs(web_data_dir, exist_ok=True)
        output_path = os.path.join(web_data_dir, "dashboard_data.json")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export_payload, f, ensure_ascii=False, indent=2)

    print(f"\n✅ エクスポート完了: {output_path}")
    print(f"   データサイズ: {os.path.getsize(output_path) / 1024:.1f} KB")
    print("=" * 60)
    return output_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else None
    export_dashboard_data(out)
