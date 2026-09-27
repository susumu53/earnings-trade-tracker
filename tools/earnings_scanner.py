#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
決算トレード・サイクル予測検証システム
決算日ファースト高速スキャナー (earnings_scanner.py)

東証全銘柄から「決算日が当日から14日後（0〜14日後）」の銘柄を高速に抽出する。
第一優先: JPX公式の「決算発表予定会社一覧Excel」から公式スケジュールを数秒で完全取得
第二優先（フォールバック）: yfinanceによる軽量並列スキャン
"""

import os
import re
import json
import time
import urllib.request
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import yfinance as yf

try:
    from tools.universe import get_all_tse_tickers, get_all_tse_stocks
except ImportError:
    from universe import get_all_tse_tickers, get_all_tse_stocks

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
EARNINGS_CACHE_FILE = os.path.join(DATA_DIR, "earnings_dates_cache.json")
JPX_KESSAN_EXCEL_LOCAL = os.path.join(DATA_DIR, "jpx_kessan_latest.xlsx")

# 決算日キャッシュの有効期間（秒）: 12時間
EARNINGS_CACHE_TTL = 43200

# JPX決算発表スケジュールページ
JPX_SCHEDULE_PAGE_URL = "https://www.jpx.co.jp/listing/event-schedules/financial-announcement/index.html"


def _fetch_jpx_earnings_schedule_excel() -> Optional[str]:
    """
    JPX公式サイトから最新の決算発表予定会社一覧Excelをスクレイピングしてダウンロード
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        req = urllib.request.Request(JPX_SCHEDULE_PAGE_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        links = re.findall(r'href=["\']([^"\']+\.xls[x]?)["\']', html)
        if not links:
            print("[earnings_scanner] JPXスケジュールページにExcelリンクが見つかりません。")
            return None

        # 最新のファイル（通常リンク末尾または直近日付のもの）
        target_link = links[-1]
        full_url = urllib.parse.urljoin(JPX_SCHEDULE_PAGE_URL, target_link)

        print(f"[earnings_scanner] JPX決算発表予定Excelをダウンロード: {full_url}")
        req_dl = urllib.request.Request(full_url, headers=headers)
        with urllib.request.urlopen(req_dl, timeout=20) as resp_dl:
            data = resp_dl.read()
            with open(JPX_KESSAN_EXCEL_LOCAL, "wb") as f:
                f.write(data)

        print(f"[earnings_scanner] JPX決算発表予定Excel保存完了 ({len(data)} bytes)")
        return JPX_KESSAN_EXCEL_LOCAL
    except Exception as e:
        print(f"[earnings_scanner] JPX決算発表予定Excelダウンロード失敗: {e}")
        return None


def _parse_jpx_earnings_schedule(
    file_path: str,
    days_min: int = 0,
    days_max: int = 14
) -> List[Dict[str, Any]]:
    """
    JPX決算発表予定Excelをパースし、指定日数（days_min〜days_max日後）の銘柄を抽出
    """
    try:
        # ヘッダー行を特定（先頭10行の中から「決算発表予定日」「Scheduled Dates」「コード」「Code」を含む行を探す）
        preview_df = pd.read_excel(file_path, header=None, nrows=10)
        header_idx = None
        for idx, row in preview_df.iterrows():
            row_str = " ".join([str(v) for v in row.values])
            if ("Scheduled Dates" in row_str or "決算発表予定日" in row_str or "発表予定日" in row_str) and ("Code" in row_str or "コード" in row_str):
                header_idx = idx
                break

        if header_idx is None:
            # デフォルトで行4 (header=4) を試行
            header_idx = 4

        df = pd.read_excel(file_path, header=header_idx)

        # 列を特定
        date_col = None
        code_col = None
        name_col = None

        for col in df.columns:
            c_str = str(col).strip()
            if ("Scheduled" in c_str or "決算" in c_str or "発表" in c_str or "日付" in c_str) and date_col is None:
                date_col = col
            elif ("Code" in c_str or "コード" in c_str) and code_col is None:
                code_col = col
            elif ("Issue Name" in c_str or "会社名" in c_str or "銘柄名" in c_str or "社名" in c_str) and name_col is None:
                name_col = col

        if date_col is None or code_col is None:
            # インデックスによるフォールバック: 0列目が日付、1列目がコード、2列目が社名
            date_col = df.columns[0]
            code_col = df.columns[1]
            name_col = df.columns[2] if len(df.columns) > 2 else None

        today = date.today()
        results = []

        for _, row in df.iterrows():
            val = row[date_col]
            if pd.isna(val):
                continue

            ed = None
            if isinstance(val, (datetime, pd.Timestamp)):
                ed = val.date()
            elif isinstance(val, date):
                ed = val
            elif isinstance(val, str):
                try:
                    ed = datetime.strptime(val.strip().split()[0], "%Y-%m-%d").date()
                except Exception:
                    continue
            else:
                continue

            days_until = (ed - today).days
            if not (days_min <= days_until <= days_max):
                continue

            code_raw = str(row[code_col]).strip()
            if not code_raw.isdigit() or len(code_raw) != 4:
                continue

            name_raw = str(row[name_col]).strip() if name_col and not pd.isna(row[name_col]) else ""

            results.append({
                "code": code_raw,
                "name": name_raw,
                "earnings_date": ed.strftime("%Y-%m-%d"),
                "days_until": days_until,
                "source": "JPX_OFFICIAL"
            })

        return results
    except Exception as e:
        print(f"[earnings_scanner] JPX Excelパースエラー: {e}")
        return []


def _check_earnings_date_single(
    ticker_code: str,
    days_min: int = 0,
    days_max: int = 14
) -> Optional[Dict[str, Any]]:
    """
    1銘柄の決算予定日をyfinanceから軽量チェック（フォールバック用）
    """
    symbol = f"{ticker_code}.T"
    try:
        t = yf.Ticker(symbol)
        earnings_date_str = None
        try:
            cal = getattr(t, "calendar", None)
            if cal and "Earnings Date" in cal:
                e_dates = cal["Earnings Date"]
                if e_dates and len(e_dates) > 0:
                    ed = e_dates[0]
                    if isinstance(ed, (datetime, date)):
                        earnings_date_str = ed.strftime("%Y-%m-%d")
                    elif isinstance(ed, str):
                        earnings_date_str = ed.split("T")[0]
        except Exception:
            pass

        if not earnings_date_str:
            return None

        try:
            e_date = datetime.strptime(earnings_date_str, "%Y-%m-%d").date()
        except ValueError:
            return None

        days_until = (e_date - date.today()).days

        if not (days_min <= days_until <= days_max):
            return None

        return {
            "code": ticker_code,
            "earnings_date": earnings_date_str,
            "days_until": days_until,
            "source": "YFINANCE"
        }

    except Exception:
        return None


def _load_earnings_cache() -> Optional[Dict[str, Any]]:
    """決算日キャッシュを読み込み"""
    if not os.path.exists(EARNINGS_CACHE_FILE):
        return None
    try:
        with open(EARNINGS_CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        cached_at = datetime.fromisoformat(cache.get("cached_at", "2000-01-01"))
        if datetime.now() - cached_at > timedelta(seconds=EARNINGS_CACHE_TTL):
            return None
        return cache
    except Exception:
        return None


def _save_earnings_cache(results: List[Dict[str, Any]], scan_stats: Dict[str, Any]):
    """決算日キャッシュに保存"""
    os.makedirs(DATA_DIR, exist_ok=True)
    cache = {
        "cached_at": datetime.now().isoformat(),
        "scan_stats": scan_stats,
        "results": results
    }
    with open(EARNINGS_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def scan_earnings_dates_bulk(
    days_min: int = 0,
    days_max: int = 14,
    max_workers: int = 30,
    max_tickers: Optional[int] = None,
    force_refresh: bool = False,
    progress_callback=None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Phase 1: 東証全銘柄の決算予定日を高速チェック (当日から14日後: 0〜14日)

    第1優先: JPX公式決算発表予定会社一覧Excelによる一括抽出（約1秒で東証全銘柄を完全網羅）
    第2優先: yfinanceによる並列スキャン（フォールバック）

    Args:
        days_min: 最小日数（デフォルト0: 当日）
        days_max: 最大日数（デフォルト14: 2週間後）
        max_workers: フォールバック時の並列スレッド数
        max_tickers: チェックする最大銘柄数
        force_refresh: キャッシュを無視して再スキャン
        progress_callback: 進捗コールバック関数 f(scanned, total, found)

    Returns:
        (results, scan_stats)
    """
    # 1. キャッシュチェック
    if not force_refresh:
        cache = _load_earnings_cache()
        if cache and cache.get("results"):
            results = cache["results"]
            today = date.today()
            filtered = []
            for r in results:
                try:
                    e_date = datetime.strptime(r["earnings_date"], "%Y-%m-%d").date()
                    days = (e_date - today).days
                    if days_min <= days <= days_max:
                        r["days_until"] = days
                        filtered.append(r)
                except (ValueError, KeyError):
                    continue
            if filtered:
                stats = cache.get("scan_stats", {})
                stats["from_cache"] = True
                stats["matched"] = len(filtered)
                return filtered, stats

    start_time = time.time()

    # 2. 第1優先: JPX公式決算発表スケジュールExcelから抽出
    jpx_excel = None
    if os.path.exists(JPX_KESSAN_EXCEL_LOCAL):
        # 12時間以内のファイルなら再利用
        mod_time = datetime.fromtimestamp(os.path.getmtime(JPX_KESSAN_EXCEL_LOCAL))
        if datetime.now() - mod_time < timedelta(hours=12):
            jpx_excel = JPX_KESSAN_EXCEL_LOCAL
        else:
            jpx_excel = _fetch_jpx_earnings_schedule_excel() or JPX_KESSAN_EXCEL_LOCAL
    else:
        jpx_excel = _fetch_jpx_earnings_schedule_excel()

    if jpx_excel and os.path.exists(jpx_excel):
        print(f"[earnings_scanner] JPX公式決算発表スケジュールから抽出中 ({days_min}〜{days_max}日後)...")
        jpx_results = _parse_jpx_earnings_schedule(jpx_excel, days_min=days_min, days_max=days_max)
        if jpx_results:
            elapsed_sec = round(time.time() - start_time, 2)
            # 決算日が近い順にソート
            jpx_results.sort(key=lambda x: (x["days_until"], x["code"]))
            
            if max_tickers:
                jpx_results = jpx_results[:max_tickers]

            scan_stats = {
                "total_scanned": "JPX東証全銘柄 (公式発表一覧)",
                "matched": len(jpx_results),
                "elapsed_sec": elapsed_sec,
                "scan_date": date.today().isoformat(),
                "method": "JPX_OFFICIAL_EXCEL",
                "from_cache": False
            }
            print(f"[earnings_scanner] JPX公式スケジュール抽出完了: {len(jpx_results)}銘柄が決算{days_min}〜{days_max}日後 ({elapsed_sec}秒)")
            _save_earnings_cache(jpx_results, scan_stats)
            return jpx_results, scan_stats

    # 3. 第2優先: yfinance並列スキャン（フォールバック）
    print("[earnings_scanner] JPX公式Excelが利用できないため、yfinance並列スキャンを実行します...")
    all_tickers = get_all_tse_tickers()
    if max_tickers:
        all_tickers = all_tickers[:max_tickers]

    total = len(all_tickers)
    results = []
    scanned = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_code = {
            executor.submit(_check_earnings_date_single, code, days_min, days_max): code
            for code in all_tickers
        }

        for future in as_completed(future_to_code):
            scanned += 1
            try:
                res = future.result()
                if res:
                    results.append(res)
            except Exception:
                errors += 1

            if progress_callback and scanned % 100 == 0:
                progress_callback(scanned, total, len(results))

            if scanned % 500 == 0:
                elapsed = round(time.time() - start_time, 1)
                print(f"  [{scanned}/{total}] yfinanceスキャン済み... 該当: {len(results)}件 ({elapsed}秒)")

    elapsed_sec = round(time.time() - start_time, 2)
    results.sort(key=lambda x: (x["days_until"], x["code"]))

    scan_stats = {
        "total_scanned": total,
        "matched": len(results),
        "errors": errors,
        "elapsed_sec": elapsed_sec,
        "scan_date": date.today().isoformat(),
        "method": "YFINANCE_BULK",
        "from_cache": False
    }

    print(f"[earnings_scanner] yfinanceスキャン完了: {total}銘柄中 {len(results)}銘柄が決算{days_min}〜{days_max}日後 ({elapsed_sec}秒)")
    _save_earnings_cache(results, scan_stats)
    return results, scan_stats


def get_upcoming_earnings_tickers(
    days_min: int = 0,
    days_max: int = 14,
    force_refresh: bool = False
) -> List[str]:
    """決算日が当日から14日後の銘柄コード一覧を取得"""
    results, _ = scan_earnings_dates_bulk(
        days_min=days_min,
        days_max=days_max,
        force_refresh=force_refresh
    )
    return [r["code"] for r in results]


if __name__ == "__main__":
    print("決算日スキャナー実行テスト (0〜14日後)...")
    results, stats = scan_earnings_dates_bulk(days_min=0, days_max=14, force_refresh=True)
    print(f"\n--- スキャン統計 ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"\n--- 決算日が0〜14日後の銘柄 (全{len(results)}件中 先頭15件) ---")
    for r in results[:15]:
        name_info = f" ({r.get('name', '')})" if r.get('name') else ""
        print(f"  [{r['code']}] 決算日: {r['earnings_date']} (あと{r['days_until']}日){name_info}")
