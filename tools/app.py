#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
決算トレード・サイクル予測検証システム
統合Webダッシュボード サーバー (app.py)

本物の市場データ（リアルタイム株価、決算日、テクニカル自動計算、決算後実績株価）
を自動フェッチする実運用対応サーバー
"""

import os
import sys
import json
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from typing import Dict, Any

# パス設定
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, "web")
sys.path.append(BASE_DIR)

from tools.db import (
    init_db, get_all_records, add_prediction, add_predictions_batch,
    delete_prediction, get_prediction_by_id, get_connection
)


from tools.predictor import (
    evaluate_prediction, calculate_wave_targets,
    TECHNICAL_PATTERNS
)
from tools.tracker import evaluate_and_record_result
from tools.analyzer import generate_season_analysis, generate_markdown_report
from tools.market_data import (
    fetch_stock_live_data,
    fetch_stock_chart_data,
    fetch_post_earnings_result,
    scan_upcoming_earnings
)


class EarningsTradeHandler(SimpleHTTPRequestHandler):
    """APIリクエストおよび静的ファイル配信ハンドラー"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 0. 詳細チャート時系列データの取得
        if path == "/api/stock/chart":
            ticker = query.get("ticker", [""])[0]
            period = query.get("period", ["6mo"])[0]
            if not ticker:
                self._send_json({"success": False, "error": "銘柄コードを指定してください。"}, status=400)
                return
            try:
                chart_data = fetch_stock_chart_data(ticker, period=period)
                self._send_json({"success": True, "data": chart_data})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        # 1. 銘柄実データのリアルタイム取得
        elif path == "/api/stock/fetch":
            ticker = query.get("ticker", [""])[0]

            if not ticker:
                self._send_json({"success": False, "error": "銘柄コードを指定してください。"}, status=400)
                return
            try:
                data = fetch_stock_live_data(ticker)
                self._send_json({"success": True, "data": data})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        # 2. 決算直前 注目銘柄の自動スクリーニング・ピックアップ (当日から14日後)
        elif path == "/api/stock/auto-screen":
            try:
                from tools.auto_screener import auto_screen_upcoming_opportunities
                from tools.earnings_scanner import scan_earnings_dates_bulk
                force_refresh = query.get("refresh", ["false"])[0].lower() == "true"
                strategy_filter = query.get("strategy", [None])[0]
                opportunities = auto_screen_upcoming_opportunities(
                    force_refresh=force_refresh,
                    strategy_filter=strategy_filter
                )
                # スキャン統計を取得（キャッシュから）
                _, scan_stats = scan_earnings_dates_bulk(days_min=0, days_max=14)
                self._send_json({
                    "success": True,
                    "opportunities": opportunities,
                    "scan_stats": scan_stats
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        # 3. 決算直前銘柄の自動スキャン
        elif path == "/api/stock/scan-upcoming":

            try:
                min_days = int(query.get("min_days", [7])[0])
                max_days = int(query.get("max_days", [25])[0])
                matched = scan_upcoming_earnings(min_days, max_days)
                self._send_json({"success": True, "stocks": matched})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        # 3. 決算後1週間の実績株価自動取得
        elif path == "/api/stock/post-earnings":
            ticker = query.get("ticker", [""])[0]
            date_str = query.get("date", [""])[0]
            if not ticker or not date_str:
                self._send_json({"success": False, "error": "銘柄コードと決算日を指定してください。"}, status=400)
                return
            try:
                res_data = fetch_post_earnings_result(ticker, date_str)
                self._send_json({"success": True, "data": res_data})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        # 4. 全レコード取得
        elif path == "/api/records":
            season_id = query.get("season_id", [None])[0]
            records = get_all_records(season_id)
            self._send_json(records)
            return

        # 5. シーズン分析
        elif path == "/api/analysis":
            season_id = query.get("season_id", [None])[0]
            analysis = generate_season_analysis(season_id)
            self._send_json(analysis)
            return

        # 6. Markdownレポート
        elif path == "/api/report/markdown":
            season_id = query.get("season_id", [None])[0]
            md = generate_markdown_report(season_id)
            self._send_text(md, content_type="text/markdown; charset=utf-8")
            return

        # 7. テクニカルパターン一覧
        elif path == "/api/technical-patterns":
            self._send_json(TECHNICAL_PATTERNS)
            return

        # 静的ファイル配信
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()

        # 評価計算プレビュー
        if path == "/api/predict/evaluate":
            cur = float(body.get("current_price", 1000.0))
            low_a = float(body.get("low_a", cur * 0.9))
            high_b = float(body.get("high_b", cur * 1.05))
            pull_c = float(body.get("pull_c", cur * 0.98))
            waves = calculate_wave_targets(cur, low_a, high_b, pull_c)

            pat = body.get("technical_pattern", "直近高値ブレイク型")
            target = float(body.get("target_price", waves.get("V_target", cur * 1.15)))
            stop = float(body.get("stop_loss", round(cur * 0.95, 1)))

            eval_res = evaluate_prediction(
                ticker=body.get("ticker", ""),
                name=body.get("name", ""),
                current_price=cur,
                target_price=target,
                stop_loss=stop,
                technical_pattern=pat,
                progress_rate=float(body.get("progress_rate", 0.0)),
                consensus_status=body.get("consensus_status", "中立")
            )
            eval_res["wave_targets"] = waves
            self._send_json(eval_res)
            return

        # ポジションサイズ計算（資金管理）
        elif path == "/api/position/calculate":
            try:
                from tools.position_sizer import calculate_position
                capital = float(body.get("total_capital", 1_000_000))
                risk_pct = float(body.get("risk_per_trade_pct", 2.0))
                entry = float(body.get("entry_price", 1000.0))
                stop = float(body.get("stop_loss_price", round(entry * 0.95, 1)))
                target = float(body.get("target_price", round(entry * 1.15, 1)))
                lev = float(body.get("leverage", 1.0))

                pos_res = calculate_position(
                    total_capital=capital,
                    risk_per_trade_pct=risk_pct,
                    entry_price=entry,
                    stop_loss_price=stop,
                    target_price=target,
                    leverage=lev
                )

                required_margin = round(pos_res.position_size / lev, 0) if lev > 0 else pos_res.position_size
                target_profit = round(pos_res.shares * (target - entry), 0)
                gain_pct = round(((target - entry) / entry) * 100, 2)
                loss_pct = round(((stop - entry) / entry) * 100, 2)
                cap_ratio = round((required_margin / capital) * 100, 1)

                self._send_json({
                    "success": True,
                    "shares": pos_res.shares,
                    "position_size": pos_res.position_size,
                    "required_margin": required_margin,
                    "max_loss_amount": pos_res.max_loss_amount,
                    "actual_risk": pos_res.actual_risk,
                    "target_profit": target_profit,
                    "gain_pct": gain_pct,
                    "loss_pct": loss_pct,
                    "risk_reward_ratio": round(pos_res.risk_reward_ratio, 2),
                    "capital_ratio": cap_ratio,
                    "leverage": lev
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=500)
            return

        # 新規予測登録（単一）
        elif path == "/api/predictions":
            pred_id = add_prediction(body)
            self._send_json({"success": True, "prediction_id": pred_id})
            return

        # 複数予測の一括登録（バッチ）
        elif path == "/api/predictions/batch":
            items = body.get("items", [])
            if not items:
                self._send_json({"success": False, "error": "登録データが空です。"}, status=400)
                return
            ids = add_predictions_batch(items)
            self._send_json({"success": True, "inserted_count": len(ids), "inserted_ids": ids})
            return


        # 決算後1週間結果登録
        elif path == "/api/results":
            res = evaluate_and_record_result(
                prediction_id=int(body["prediction_id"]),
                earnings_actual_date=body["earnings_actual_date"],
                post_open_price=float(body["post_open_price"]),
                week_high_price=float(body["week_high_price"]),
                week_low_price=float(body["week_low_price"]),
                week_close_price=float(body["week_close_price"]),
                earnings_result_type=body.get("earnings_result_type", ""),
                review_notes=body.get("review_notes", "")
            )
            self._send_json({"success": True, "result": res})
            return

        # DBクリア（本番用リセット）
        elif path == "/api/db/clear":
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM results")
            cursor.execute("DELETE FROM predictions")
            conn.commit()
            conn.close()
            self._send_json({"success": True, "message": "全データをクリアしました。"})
            return

        self.send_error(404, "Not Found")

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/predictions/"):
            try:
                pred_id = int(path.split("/")[-1])
                delete_prediction(pred_id)
                self._send_json({"success": True, "deleted_id": pred_id})
                return
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, status=400)
                return
        self.send_error(404, "Not Found")

    def _read_json_body(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            post_data = self.rfile.read(content_length).decode("utf-8")
            return json.loads(post_data)
        return {}

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, content_type: str = "text/plain", status: int = 200):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(port: int = None):
    init_db()
    if port is None:
        port = int(os.environ.get("PORT", 8080))
    server_address = ("0.0.0.0", port)
    try:
        httpd = ThreadingHTTPServer(server_address, EarningsTradeHandler)
        print(f"=====================================================")
        print(f"  決算トレード実運用ダッシュボード稼働中 (マルチスレッド)")
        print(f"  市場API: yfinance (東証リアルタイムデータ連携)")
        print(f"  URL: http://localhost:{port}/ (バインド: 0.0.0.0)")
        print(f"=====================================================")
        httpd.serve_forever()
    except OSError:
        port = port + 1
        httpd = ThreadingHTTPServer(("0.0.0.0", port), EarningsTradeHandler)
        print(f"Port busy. Starting on http://localhost:{port}/")
        httpd.serve_forever()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    run_server(port)
