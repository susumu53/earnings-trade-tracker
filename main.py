#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
決算トレード・サイクル予測検証システム (EarningsTrade-Tracker)
メイン統合エントリーポイント (main.py)
"""

import sys
import os
import webbrowser
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

from tools.db import init_db, get_all_records
from tools.app import run_server
from tools.analyzer import generate_markdown_report


def print_header():
    print("=" * 65)
    print("  📈 決算プレトレード予測・検証サイクルシステム (EarningsTrade-Tracker)")
    print("  - 決算2週間前ピックアップ & テクニカル上昇予測")
    print("  - 決算後1週間値動き結果記録 & 勝敗検証")
    print("  - 次期決算シーズン向け自己学習 & パターン分析")
    print("=" * 65)


def open_browser_delayed(url, delay=1.2):
    time.sleep(delay)
    webbrowser.open(url)


def main():
    init_db()
    print_header()

    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd in ["report", "analysis"]:
            print(generate_markdown_report())
            return
        elif cmd in ["server", "web"]:
            port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
            run_server(port)
            return

    # 選択肢を挟まず、直ちにWebダッシュボードを起動＆ブラウザを自動オープン
    port = 8080
    url = f"http://localhost:{port}/"
    print(f"\n🚀 Webダッシュボードを自動起動しています...")
    print(f"🌐 ブラウザを開きます: {url}")
    print("（ダッシュボードを終了するにはこのウィンドウを閉じるか Ctrl+C を押してください）\n")
    threading.Thread(target=open_browser_delayed, args=(url,), daemon=True).start()
    run_server(port)


if __name__ == "__main__":
    main()
