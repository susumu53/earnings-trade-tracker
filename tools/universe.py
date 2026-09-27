#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
決算トレード・サイクル予測検証システム
東証全銘柄ユニバース管理モジュール (universe.py)

JPX（日本取引所グループ）公式の上場銘柄一覧Excelから
東証の全普通株式銘柄コードを取得・管理する。
ETF/REIT/新株予約権等は除外し、普通株式のみを対象とする。
"""

import os
import time
import json
import urllib.request
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_FILE = os.path.join(DATA_DIR, "tse_universe_cache.json")
JPX_EXCEL_LOCAL = os.path.join(DATA_DIR, "data_j.xlsx")

# JPX公式の上場銘柄一覧ダウンロードURL (現在はxlsx形式)
JPX_LISTED_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xlsx"

# キャッシュ有効期間（秒）: 24時間
CACHE_TTL_SECONDS = 86400


def _download_jpx_excel() -> Optional[str]:
    """JPX公式サイトから上場銘柄一覧Excel (.xlsx) をダウンロード"""
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        req = urllib.request.Request(JPX_LISTED_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read()
            with open(JPX_EXCEL_LOCAL, "wb") as f:
                f.write(data)
        print(f"[universe] JPX Excelダウンロード成功: {len(data)} bytes")
        return JPX_EXCEL_LOCAL
    except Exception as e:
        print(f"[universe] JPX Excelダウンロード失敗: {e}")
        return None


def _parse_jpx_excel(file_path: str) -> List[Dict[str, str]]:
    """
    JPX上場銘柄一覧Excelをパースし、普通株式のみを抽出

    Excelの列構成（想定）:
    - 日付
    - コード (銘柄コード)
    - 銘柄名
    - 市場・商品区分
    - 33業種コード
    - 33業種区分
    - 17業種コード
    - 17業種区分
    - 規模コード
    - 規模区分
    """
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        print(f"[universe] Excelパース失敗: {e}")
        return []

    # 列名を正規化（JPXのExcelは日本語列名）
    columns = list(df.columns)

    # コード列と銘柄名列を特定
    code_col = None
    name_col = None
    market_col = None
    sector_col = None

    for col in columns:
        col_str = str(col).strip()
        if "コード" in col_str and code_col is None:
            code_col = col
        elif "銘柄名" in col_str and name_col is None:
            name_col = col
        elif ("市場" in col_str or "商品" in col_str) and market_col is None:
            market_col = col
        elif "33業種" in col_str and "区分" in col_str and sector_col is None:
            sector_col = col

    if code_col is None:
        # フォールバック: 2番目の列をコード、3番目を銘柄名と推定
        if len(columns) >= 3:
            code_col = columns[1]
            name_col = columns[2]
            market_col = columns[3] if len(columns) > 3 else None
            sector_col = columns[5] if len(columns) > 5 else None
        else:
            print("[universe] Excel列構造を特定できません。")
            return []

    stocks = []
    for _, row in df.iterrows():
        code_raw = str(row.get(code_col, "")).strip()

        # 4桁の数字のみを普通株式と判定（ETF等は5桁以上やアルファベット含み）
        if not code_raw.isdigit():
            continue
        if len(code_raw) != 4:
            continue

        name = str(row.get(name_col, "")).strip() if name_col else ""
        market = str(row.get(market_col, "")).strip() if market_col else ""
        sector = str(row.get(sector_col, "")).strip() if sector_col else ""

        # 市場区分でフィルタ: 「内国株式」「プライム」「スタンダード」「グロース」を含む行のみ
        # ETF/ETN/REIT/新株予約権等を除外
        market_lower = market.lower()
        exclude_keywords = ["etf", "etn", "reit", "出資証券", "新株予約権", "優先株", "受益証券"]
        if any(kw in market_lower or kw in market for kw in exclude_keywords):
            continue

        stocks.append({
            "code": code_raw,
            "name": name,
            "market": market,
            "sector": sector
        })

    return stocks


def _load_cache() -> Optional[Dict[str, Any]]:
    """キャッシュファイルを読み込み"""
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        # TTLチェック
        cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
        if datetime.now() - cached_at > timedelta(seconds=CACHE_TTL_SECONDS):
            return None
        return cache
    except Exception:
        return None


def _save_cache(stocks: List[Dict[str, str]]):
    """キャッシュファイルに保存"""
    os.makedirs(DATA_DIR, exist_ok=True)
    cache = {
        "cached_at": datetime.now().isoformat(),
        "count": len(stocks),
        "stocks": stocks
    }
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def get_all_tse_stocks(force_refresh: bool = False) -> List[Dict[str, str]]:
    """
    東証全銘柄（普通株式のみ）のリストを取得

    Returns:
        list of dict: [{"code": "6501", "name": "日立製作所", "market": "プライム", "sector": "電気機器"}, ...]
    """
    # 1. キャッシュチェック
    if not force_refresh:
        cache = _load_cache()
        if cache and cache.get("stocks"):
            return cache["stocks"]

    # 2. JPX Excelの取得（ローカルにあればそれを使う、なければダウンロード）
    excel_path = None
    if os.path.exists(JPX_EXCEL_LOCAL):
        # ローカルファイルの鮮度チェック（7日以内なら再ダウンロードしない）
        mod_time = datetime.fromtimestamp(os.path.getmtime(JPX_EXCEL_LOCAL))
        if datetime.now() - mod_time < timedelta(days=7):
            excel_path = JPX_EXCEL_LOCAL
        else:
            excel_path = _download_jpx_excel() or JPX_EXCEL_LOCAL
    else:
        excel_path = _download_jpx_excel()

    if not excel_path or not os.path.exists(excel_path):
        print("[universe] JPX Excelが取得できません。フォールバック銘柄リストを使用します。")
        return _get_fallback_tickers()

    # 3. パース
    stocks = _parse_jpx_excel(excel_path)
    if not stocks:
        print("[universe] Excelのパースに失敗しました。フォールバック銘柄リストを使用します。")
        return _get_fallback_tickers()

    # 4. キャッシュ保存
    _save_cache(stocks)
    print(f"[universe] 東証普通株式 {len(stocks)} 銘柄を取得しました。")
    return stocks


def get_all_tse_tickers(force_refresh: bool = False) -> List[str]:
    """東証全銘柄コード（4桁文字列）のリストを取得"""
    stocks = get_all_tse_stocks(force_refresh)
    return [s["code"] for s in stocks]


def get_stock_info(code: str) -> Optional[Dict[str, str]]:
    """銘柄コードから銘柄情報を検索"""
    stocks = get_all_tse_stocks()
    for s in stocks:
        if s["code"] == code:
            return s
    return None


def _get_fallback_tickers() -> List[Dict[str, str]]:
    """
    JPX Excelが取得できない場合のフォールバック銘柄リスト
    主要銘柄のみ（約120銘柄）
    """
    # 既存のPOPULAR_TICKERSベースの最小限リスト
    codes = [
        "6501", "6758", "6857", "6920", "8035", "6702", "6723", "6762", "7735", "6861", "6981", "6971", "6645",
        "7011", "7012", "7013", "6301", "6367", "6326", "6273", "6103",
        "7203", "7267", "7201", "7269", "7270", "6902", "5108",
        "9984", "9432", "9433", "9434", "4689", "4755", "3659", "2413", "4385", "4443", "4478",
        "8001", "8058", "8031", "8002", "8015", "2768",
        "8306", "8316", "8411", "8604", "8766", "8725", "8591",
        "4063", "4188", "4502", "4503", "4519", "4568", "4523", "4543", "3407", "3405",
        "9983", "3382", "8267", "2670", "3048", "9843", "7453", "3086", "3099", "8227",
        "7581", "9861", "2782", "7616", "2685", "3050", "7545", "7649", "9842",
        "7974", "6098", "9101", "9104", "9107", "9020", "9022", "9201",
        "6506", "6323", "6594", "7751", "6752", "6963", "6954"
    ]
    return [{"code": c, "name": "", "market": "", "sector": ""} for c in codes]


if __name__ == "__main__":
    print("東証全銘柄ユニバース取得テスト...")
    stocks = get_all_tse_stocks(force_refresh=True)
    print(f"取得銘柄数: {len(stocks)}")
    if stocks:
        print("先頭5件:")
        for s in stocks[:5]:
            print(f"  [{s['code']}] {s['name']} ({s['market']} / {s['sector']})")
        print(f"末尾5件:")
        for s in stocks[-5:]:
            print(f"  [{s['code']}] {s['name']} ({s['market']} / {s['sector']})")
