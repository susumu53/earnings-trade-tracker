#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
決算トレード・サイクル予測検証システム
市場データAPI連携モジュール (market_data.py)

yfinanceおよび公開市場データソースから日本株（TSE）の
リアルタイム株価、決算予定日、テクニカル指標、波動計算、決算後1週間値動きを自動取得
"""

import math
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional, List, Tuple
import pandas as pd
import yfinance as yf

try:
    from tools.universe import get_stock_info
except ImportError:
    try:
        from universe import get_stock_info
    except ImportError:
        get_stock_info = None


def normalize_ticker(ticker: str) -> str:
    """銘柄コードを日本株シンボル (XXXX.T) に正規化"""
    ticker_clean = str(ticker).strip().upper()
    if ticker_clean.isdigit():
        return f"{ticker_clean}.T"
    if not ticker_clean.endswith(".T") and ticker_clean[:-1].isdigit():
        # 例: 6501A などの対応
        return f"{ticker_clean}.T"
    return ticker_clean


def fetch_stock_live_data(ticker_input: str) -> Dict[str, Any]:
    """
    銘柄コードから市場の実データを自動取得し、テクニカル分析・波動計算・目標値を自動生成
    """
    symbol = normalize_ticker(ticker_input)
    ticker_code = ticker_input.strip().upper().replace(".T", "")
    t = yf.Ticker(symbol)

    # 1. 銘柄基本情報
    info = {}
    try:
        info = t.info or {}
    except Exception:
        pass

    # 日本語会社名・業種名を優先取得
    stock_meta = get_stock_info(ticker_code) if get_stock_info else None
    if stock_meta and stock_meta.get("name"):
        name = stock_meta["name"]
    else:
        name = info.get("longName") or info.get("shortName") or ticker_input

    if stock_meta and stock_meta.get("sector"):
        sector = stock_meta["sector"]
    else:
        sector = info.get("sector") or info.get("industry") or "一般"

    # 2. 直近株価と日足データ (過去6ヶ月)
    hist = t.history(period="6mo")
    if hist.empty:
        raise ValueError(f"銘柄コード {symbol} の株価データを取得できませんでした。コードを確認してください。")

    # 現在株価
    current_price = round(float(hist["Close"].iloc[-1]), 1)

    # 3. テクニカル指標計算 (25MA, 75MA, ボリンジャーバンド, 直近高値・安値)
    close_series = hist["Close"]
    high_series = hist["High"]
    low_series = hist["Low"]
    volume_series = hist["Volume"]

    ma25 = round(float(close_series.rolling(window=25).mean().iloc[-1]), 1) if len(close_series) >= 25 else current_price
    ma75 = round(float(close_series.rolling(window=75).mean().iloc[-1]), 1) if len(close_series) >= 75 else ma25
    ma25_bias = round(((current_price - ma25) / ma25) * 100, 2)

    # ボリンジャーバンド (25日, ±2σ)
    std25 = float(close_series.rolling(window=25).std().iloc[-1]) if len(close_series) >= 25 else 0
    bb_upper = round(ma25 + (std25 * 2), 1)
    bb_lower = round(ma25 - (std25 * 2), 1)

    # 過去20日間の最高値・最安値
    high_20d = round(float(high_series.tail(20).max()), 1)
    low_20d = round(float(low_series.tail(20).min()), 1)

    # 4. チャート波動（安値A、高値B、押し目C）のスイング自動検出
    # 直近30日の極値から自動推計
    low_a = round(float(low_series.tail(30).min()), 1)
    # A以降の最高値B
    sub_df = hist.tail(30)
    idx_a = sub_df["Low"].idxmin()
    after_a = sub_df.loc[idx_a:]
    high_b = round(float(after_a["High"].max()), 1) if not after_a.empty else high_20d
    # B以降の安値C（現在株価に近い押し目）
    idx_b = after_a["High"].idxmax() if not after_a.empty else idx_a
    after_b = sub_df.loc[idx_b:]
    pull_c = round(float(after_b["Low"].min()), 1) if len(after_b) > 1 else current_price

    # 波動計算ターゲット (N, V, E)
    if high_b > low_a and pull_c <= high_b:
        wave_n = round(pull_c + (high_b - low_a), 1)
        wave_v = round(high_b + (high_b - pull_c), 1)
        wave_e = round(high_b + (high_b - low_a), 1)
    else:
        wave_n = round(current_price * 1.15, 1)
        wave_v = round(current_price * 1.20, 1)
        wave_e = round(current_price * 1.25, 1)

    # 5. テクニカル形状パターンの自動判定
    technical_pattern = "直近高値ブレイク型"
    if current_price >= high_20d * 0.98:
        technical_pattern = "直近高値ブレイク型"
    elif abs(current_price - ma25) / ma25 <= 0.025 and current_price >= ma25:
        technical_pattern = "25日線押し目反発型"
    elif (bb_upper - bb_lower) / ma25 < 0.08:
        technical_pattern = "ボリンジャースクイーズ型"
    elif current_price > ma25 and ma25 > ma75:
        technical_pattern = "カップウィズハンドル型"
    else:
        technical_pattern = "ダブルボトム反転型"

    # 目標株価と損切りラインの自動推奨
    # パターンに応じてN/V/Eから選定
    if technical_pattern == "直近高値ブレイク型":
        recommended_target = wave_v
    elif technical_pattern == "カップウィズハンドル型":
        recommended_target = wave_e
    else:
        recommended_target = wave_n

    # 損切りライン: 25日線下-2%、または直近押し目Cの直下
    recommended_stop = round(min(pull_c * 0.97, ma25 * 0.97), 1)
    if recommended_stop >= current_price:
        recommended_stop = round(current_price * 0.94, 1)

    # 6. 次回決算予定日の取得
    earnings_date_str = ""
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

    # 決算日が取得できない場合はフォールバックせず空文字のまま返す
    # （決算トレード特化ツールでは、決算日不明の銘柄は対象外とする）

    # 7. 業績・コンセンサス情報
    trailing_pe = round(float(info.get("trailingPE", 0.0)), 1) if info.get("trailingPE") else 0.0
    forward_pe = round(float(info.get("forwardPE", 0.0)), 1) if info.get("forwardPE") else 0.0
    target_mean_price = round(float(info.get("targetMeanPrice", 0.0)), 1) if info.get("targetMeanPrice") else 0.0

    # 8. 時価総額（円）
    market_cap = int(info.get("marketCap", 0)) if info.get("marketCap") else 0

    # 9. 出来高比率（直近5日平均 / 25日平均）
    if len(volume_series) >= 25:
        vol_5d_avg = float(volume_series.tail(5).mean())
        vol_25d_avg = float(volume_series.tail(25).mean())
        volume_ratio = round(vol_5d_avg / vol_25d_avg, 2) if vol_25d_avg > 0 else 1.0
    else:
        volume_ratio = 1.0

    consensus_status = "中立"
    if target_mean_price > current_price * 1.1:
        consensus_status = "上振れ期待"
    elif target_mean_price > 0 and target_mean_price < current_price:
        consensus_status = "下振れ懸念"

    # 10. 業績成長率 & 上方修正確率（progress_calculator連動）
    earnings_growth = round(float(info.get("earningsGrowth", 0.0)) * 100, 1) if info.get("earningsGrowth") is not None else None
    revenue_growth = round(float(info.get("revenueGrowth", 0.0)) * 100, 1) if info.get("revenueGrowth") is not None else None
    operating_margins = round(float(info.get("operatingMargins", 0.0)) * 100, 1) if info.get("operatingMargins") is not None else None

    # 上方修正確率の推計判定（★〜★★★★★）
    if earnings_growth is not None:
        if earnings_growth >= 30.0 or (revenue_growth and revenue_growth >= 20.0):
            revision_prob = "★★★★★ 非常に高い (80%超)"
            revision_stars = 5
        elif earnings_growth >= 15.0 or (revenue_growth and revenue_growth >= 10.0):
            revision_prob = "★★★★ 高い (50-70%)"
            revision_stars = 4
        elif earnings_growth >= 5.0:
            revision_prob = "★★★ やや高い (30-50%)"
            revision_stars = 3
        elif earnings_growth >= 0.0:
            revision_prob = "★★ 普通 (10-30%)"
            revision_stars = 2
        else:
            revision_prob = "★ 低い (下方リスク注意)"
            revision_stars = 1
    else:
        # データなしの場合はコンセンサスから推計
        if consensus_status == "上振れ期待":
            revision_prob = "★★★★ 高い (目標株価上振れ)"
            revision_stars = 4
        elif consensus_status == "下振れ懸念":
            revision_prob = "★ 低い (目標株価下振れ)"
            revision_stars = 1
        else:
            revision_prob = "★★★ 標準 (データ巡航)"
            revision_stars = 3

    # 想定リターン & リスクリワード
    reward = recommended_target - current_price
    risk = current_price - recommended_stop
    exp_return_pct = round((reward / current_price) * 100, 2)
    rr_ratio = round(reward / risk, 2) if risk > 0 else 99.9

    return {
        "ticker": ticker_input.strip().upper().replace(".T", ""),
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "current_price": current_price,
        "earnings_date": earnings_date_str,
        "technical_pattern": technical_pattern,
        "ma25": ma25,
        "ma75": ma75,
        "ma25_bias_pct": ma25_bias,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "wave_a": low_a,
        "wave_b": high_b,
        "wave_c": pull_c,
        "wave_targets": {
            "N_target": wave_n,
            "V_target": wave_v,
            "E_target": wave_e
        },
        "target_price": recommended_target,
        "stop_loss": recommended_stop,
        "expected_return_pct": exp_return_pct,
        "risk_reward_ratio": rr_ratio,
        "trailing_pe": trailing_pe,
        "forward_pe": forward_pe,
        "consensus_status": consensus_status,
        "market_cap": market_cap,
        "volume_ratio": volume_ratio,
        "earnings_growth": earnings_growth,
        "revenue_growth": revenue_growth,
        "operating_margins": operating_margins,
        "revision_probability": revision_prob,
        "revision_stars": revision_stars
    }


def fetch_stock_chart_data(ticker_input: str, period: str = "6mo") -> Dict[str, Any]:
    """
    チャート描画用の詳細日足ローソク足、移動平均線、ボリンジャーバンド、出来高、RSIを生成
    """
    symbol = normalize_ticker(ticker_input)
    t = yf.Ticker(symbol)

    hist = t.history(period=period)
    if hist.empty:
        raise ValueError(f"{symbol} の日足データを取得できませんでした。")

    # 基本情報の取得
    live_meta = fetch_stock_live_data(ticker_input)

    # タイムゾーンを統一して文字列化
    hist.index = hist.index.tz_localize(None)

    # 1. 移動平均線の計算
    hist["MA25"] = hist["Close"].rolling(window=25).mean()
    hist["MA75"] = hist["Close"].rolling(window=75).mean()

    # 2. ボリンジャーバンド (25日, ±2σ)
    std25 = hist["Close"].rolling(window=25).std()
    hist["BB_Upper"] = hist["MA25"] + (std25 * 2)
    hist["BB_Lower"] = hist["MA25"] - (std25 * 2)

    # 3. RSI (14日)
    delta = hist["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    hist["RSI14"] = 100 - (100 / (1 + rs))

    # 出来高移動平均 (25日)
    hist["VolMA25"] = hist["Volume"].rolling(window=25).mean()

    candles = []
    for dt, row in hist.iterrows():
        date_str = dt.strftime("%Y-%m-%d")
        c = float(row["Close"])
        o = float(row["Open"])
        h = float(row["High"])
        l = float(row["Low"])
        v = int(row["Volume"])

        ma25_val = round(float(row["MA25"]), 1) if pd.notna(row["MA25"]) else None
        ma75_val = round(float(row["MA75"]), 1) if pd.notna(row["MA75"]) else None
        bbu_val = round(float(row["BB_Upper"]), 1) if pd.notna(row["BB_Upper"]) else None
        bbl_val = round(float(row["BB_Lower"]), 1) if pd.notna(row["BB_Lower"]) else None
        rsi_val = round(float(row["RSI14"]), 1) if pd.notna(row["RSI14"]) else None
        vol_ma = int(row["VolMA25"]) if pd.notna(row["VolMA25"]) else None

        candles.append({
            "date": date_str,
            "open": round(o, 1),
            "high": round(h, 1),
            "low": round(l, 1),
            "close": round(c, 1),
            "volume": v,
            "ma25": ma25_val,
            "ma75": ma75_val,
            "bb_upper": bbu_val,
            "bb_lower": bbl_val,
            "rsi": rsi_val,
            "vol_ma25": vol_ma
        })

    # 最新値におけるテクニカル根拠の診断
    latest_candle = candles[-1]
    cur_rsi = latest_candle["rsi"] or 50.0
    cur_vol = latest_candle["volume"]
    cur_vol_ma = latest_candle["vol_ma25"] or 1
    vol_ratio = round((cur_vol / cur_vol_ma), 2) if cur_vol_ma > 0 else 1.0

    technical_diagnosis = []
    # トレンド判定
    if live_meta["current_price"] >= live_meta["ma25"]:
        if live_meta["ma25"] >= live_meta["ma75"]:
            technical_diagnosis.append("【上昇トレンド】株価 ≧ 25MA ≧ 75MA（パーフェクトオーダー形成中）")
        else:
            technical_diagnosis.append("【底打ち反転】25日移動平均線を上抜け、上昇軌道へ転換中")
    else:
        technical_diagnosis.append("【調整局面】25日線下での自律反発・底値固めを監視")

    # 乖離率
    bias = live_meta["ma25_bias_pct"]
    if 0 <= bias <= 5.0:
        technical_diagnosis.append(f"【押し目妙味】25日線乖離率 {bias}%（過熱感が全くなく最も買いやすい水準）")
    elif bias > 10.0:
        technical_diagnosis.append(f"【過熱警戒】25日線乖離率 {bias}%（上昇ピッチ急、押し目を待つのが無難）")

    # ボリンジャーバンド
    if latest_candle["bb_upper"] and live_meta["current_price"] >= latest_candle["bb_upper"] * 0.98:
        technical_diagnosis.append("【バンドウォーク】ボリンジャー+2σに沿った力強い上昇トレンド突入")

    # RSI
    if cur_rsi >= 70:
        technical_diagnosis.append(f"【モメンタム強】RSI(14)は {cur_rsi}（買い圧力優勢）")
    elif cur_rsi <= 35:
        technical_diagnosis.append(f"【売られすぎ反転】RSI(14)は {cur_rsi}（リバウンド圏）")
    else:
        technical_diagnosis.append(f"【中立ゾーン】RSI(14)は {cur_rsi}（上値余地十分）")

    # 出来高
    if vol_ratio >= 1.5:
        technical_diagnosis.append(f"【出来高急増】直近出来高は25日平均の {vol_ratio}倍（大口資金・思惑買い流入）")

    return {
        "ticker": live_meta["ticker"],
        "name": live_meta["name"],
        "current_price": live_meta["current_price"],
        "target_price": live_meta["target_price"],
        "stop_loss": live_meta["stop_loss"],
        "earnings_date": live_meta["earnings_date"],
        "technical_pattern": live_meta["technical_pattern"],
        "expected_return_pct": live_meta["expected_return_pct"],
        "risk_reward_ratio": live_meta["risk_reward_ratio"],
        "wave_targets": live_meta["wave_targets"],
        "wave_points": {
            "a": live_meta["wave_a"],
            "b": live_meta["wave_b"],
            "c": live_meta["wave_c"]
        },
        "technical_diagnosis": technical_diagnosis,
        "candles": candles
    }



def fetch_post_earnings_result(ticker_input: str, earnings_date_str: str) -> Dict[str, Any]:
    """
    決算発表日以降の実績日足データを自動取得し、
    翌日寄付値、1週間高値、安値、終値、最大上昇率、確定損益を実データから自動計算
    """
    symbol = normalize_ticker(ticker_input)
    t = yf.Ticker(symbol)

    try:
        e_date = datetime.strptime(earnings_date_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError("決算日フォーマットは YYYY-MM-DD である必要があります。")

    # 決算日の前営業日〜決算後2週間分の日足を取得
    start_date = (e_date - timedelta(days=5)).strftime("%Y-%m-%d")
    end_date = (e_date + timedelta(days=20)).strftime("%Y-%m-%d")

    hist = t.history(start=start_date, end=end_date)
    if hist.empty:
        raise ValueError(f"{symbol} の期間データが取得できませんでした。")

    # タイムゾーンを除去して日付ベースでフィルタ
    hist.index = hist.index.tz_localize(None)
    e_date_ts = pd.Timestamp(e_date)

    # 決算日以降の営業日
    post_df = hist[hist.index >= e_date_ts]
    if post_df.empty or len(post_df) < 2:
        # 決算当日のみ、または未発表の場合
        raise ValueError(f"決算日 {earnings_date_str} 以降の取引データがまだ十分蓄積されていません（決算翌日以降に実行してください）。")

    # 決算発表が取引時間後と仮定し、翌営業日をpost_day_1とする
    # もし決算日のデータがpost_dfの第1行にあれば、第2行が翌日寄付き
    if post_df.index[0].date() == e_date.date():
        post_window = post_df.iloc[1:6]  # 翌日から5営業日（約1週間）
        if post_window.empty:
            raise ValueError("決算翌日の取引データがまだありません。")
        post_open_price = round(float(post_window["Open"].iloc[0]), 1)
    else:
        post_window = post_df.iloc[:5]
        post_open_price = round(float(post_window["Open"].iloc[0]), 1)

    week_high_price = round(float(post_window["High"].max()), 1)
    week_low_price = round(float(post_window["Low"].min()), 1)
    week_close_price = round(float(post_window["Close"].iloc[-1]), 1)

    return {
        "ticker": ticker_input.strip().upper().replace(".T", ""),
        "earnings_actual_date": earnings_date_str,
        "post_open_price": post_open_price,
        "week_high_price": week_high_price,
        "week_low_price": week_low_price,
        "week_close_price": week_close_price,
        "trading_days_counted": len(post_window)
    }



def scan_upcoming_earnings(days_ahead_min: int = 7, days_ahead_max: int = 25) -> List[Dict[str, Any]]:
    """
    決算予定日が近い銘柄を自動スクリーニング
    （earnings_scanner.py への委譲ラッパー。後方互換性のために維持）
    """
    try:
        from tools.earnings_scanner import scan_earnings_dates_bulk
    except ImportError:
        from earnings_scanner import scan_earnings_dates_bulk

    earnings_results, _ = scan_earnings_dates_bulk(
        days_min=days_ahead_min,
        days_max=days_ahead_max
    )

    matched_stocks = []
    for er in earnings_results:
        try:
            data = fetch_stock_live_data(er["code"])
            data["days_until_earnings"] = er["days_until"]
            matched_stocks.append(data)
        except Exception:
            continue

    matched_stocks.sort(key=lambda x: x.get("days_until_earnings", 999))
    return matched_stocks


if __name__ == "__main__":
    print("Testing live market data fetch for 6501 (Hitachi)...")
    res = fetch_stock_live_data("6501")
    for k, v in res.items():
        print(f"  {k}: {v}")
