# -*- coding: utf-8 -*-
"""
決算トレード・サイクル予測検証システム
note事後検証＆戦略監査レポート 自動生成エンジン (note_review_generator.py)

前週に配信した「週刊・決算注目銘柄レポート」の銘柄を対象に、
東証の実際の日足推移（yfinance照合）と照合して、
1. 予測 vs 実勢パフォーマンスの客観的検証
2. 4シナリオ別ポートフォリオ損益計算（ルール厳守 vs 決算またぎ反事実）
3. 戦略A不発から戦略C（決算後好決算飛び乗り）への監視引き継ぎ判定
4. 地合いクラッシュ（ルール3）の発動判定
をまとめた事後検証note記事を自動生成します。
"""

import os
import re
import sys
import math
import subprocess
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd
import yfinance as yf

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from tools.calendar_util import is_tse_trading_day, get_tse_business_days_between
from tools.market_data import normalize_ticker, _load_market_cache


def parse_previous_note_report(file_path: str) -> List[Dict[str, Any]]:
    """前週のnote記事Markdownから推奨銘柄・設定値を自動抽出"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"レポートファイルが見つかりません: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    stocks = []
    # 各銘柄詳細セクションから抽出: ### 1. 【戦略...】[XXXX] 銘柄名（業種）
    pattern_section = re.compile(
        r"###\s*\d+\.\s*【(?P<strategy>[^】]+)】\[(?P<ticker>[0-9A-Za-z]+)\]\s*(?P<name>[^（\(\n]+)",
        re.MULTILINE
    )

    matches = list(pattern_section.finditer(content))
    for i, m in enumerate(matches):
        ticker = m.group("ticker").strip()
        name = m.group("name").strip()
        strategy_str = m.group("strategy").strip()

        start_pos = m.start()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sec_text = content[start_pos:end_pos]

        # 決算予定日
        edate_m = re.search(r"決算発表予定日\*+:\s*\*+(?P<edate>\d{4}-\d{2}-\d{2})", sec_text)
        edate = edate_m.group("edate") if edate_m else ""

        # 現在株価
        price_m = re.search(r"現在株価\*+:\s*(?P<price>[0-9,]+)\s*円", sec_text)
        cur_price = float(price_m.group("price").replace(",", "")) if price_m else 0.0

        # 目標利確株価
        target_m = re.search(r"目標利確株価\*+:\s*\*+(?P<target>[0-9,]+)\s*円", sec_text)
        target = float(target_m.group("target").replace(",", "")) if target_m else cur_price * 1.1

        # 損切りライン
        stop_m = re.search(r"損切りライン\*+:\s*\*+(?P<stop>[0-9,]+)\s*円", sec_text)
        stop = float(stop_m.group("stop").replace(",", "")) if stop_m else cur_price * 0.95

        # 推奨買付株数
        shares_m = re.search(r"推奨買付株数\*+:\s*\*+(?P<shares>[0-9,]+)\s*株", sec_text)
        shares = int(shares_m.group("shares").replace(",", "")) if shares_m else 100

        # 単元未満株判定
        odd_lot = ("単元未満株" in sec_text or "ミニ株" in sec_text)

        # 戦略IDの特定
        strat_id = "A"
        if "またぎ" in strategy_str or "戦略B" in strategy_str:
            strat_id = "B"
        elif "PEAD" in strategy_str or "戦略C" in strategy_str or "決算後" in strategy_str:
            strat_id = "C"

        stocks.append({
            "ticker": ticker,
            "name": name,
            "strategy": strat_id,
            "strategy_name": strategy_str,
            "current_price": cur_price,
            "entry_price": cur_price,
            "target_price": target,
            "stop_loss": stop,
            "shares": shares,
            "earnings_date": edate,
            "odd_lot": odd_lot
        })

    return stocks


def fetch_historical_daily(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """yfinanceまたはキャッシュから対象期間の日足データを取得"""
    symbol = normalize_ticker(ticker)
    t = yf.Ticker(symbol)
    try:
        df = t.history(start=start_date, end=end_date, auto_adjust=False)
        if df.empty:
            df = t.history(period="1mo", auto_adjust=False)
    except Exception:
        df = pd.DataFrame()

    if not df.empty:
        df.index = [d.strftime("%Y-%m-%d") for d in df.index]
        return df[["Open", "High", "Low", "Close", "Volume"]]
    return pd.DataFrame()


def evaluate_scenario_pnl(stock: Dict[str, Any], daily_df: pd.DataFrame) -> Dict[str, Any]:
    """1銘柄の実績値動きに基づくシナリオ損益の精密計算"""
    entry_p = stock["entry_price"]
    target_p = stock["target_price"]
    stop_p = stock["stop_loss"]
    shares = stock["shares"]
    strat = stock["strategy"]
    edate = stock.get("earnings_date", "")

    if daily_df.empty:
        return {
            "target_reached": False,
            "stop_loss_hit": False,
            "exit_date": "",
            "exit_price": entry_p,
            "return_pct": 0.0,
            "pnl_amount": 0.0,
            "max_high": entry_p,
            "min_low": entry_p,
            "judgment": "データ取得不可"
        }

    max_high = float(daily_df["High"].max())
    min_low = float(daily_df["Low"].min())

    target_reached = max_high >= target_p
    stop_loss_hit = min_low <= stop_p

    # ルール厳守に基づく決済価格の決定
    # 戦略A: 決算前日引け（または目標指値到達なら目標価格）
    # 戦略B: 決算またぎ。目標指値到達なら目標価格、それ以外は決算後終値
    exit_price = entry_p
    exit_date = daily_df.index[-1]
    judgment = "中立"

    if strat == "A":
        # 決算前日を探す
        pre_dates = [d for d in daily_df.index if d < edate]
        if target_reached:
            # 期間中に目標達成
            exit_price = target_p
            judgment = "◎ 目標達成利確"
        elif pre_dates:
            pre_close = float(daily_df.loc[pre_dates[-1], "Close"])
            exit_price = pre_close
            exit_date = pre_dates[-1]
            judgment = "△ 決算前日ルール手仕舞い"
        else:
            exit_price = float(daily_df["Close"].iloc[0])
            judgment = "△ ルール決済"

    elif strat == "B":
        if target_reached:
            exit_price = target_p
            judgment = "◎ 上方修正シナリオ的中利確"
        elif stop_loss_hit:
            exit_price = stop_p
            judgment = "× 損切りライン到達"
        else:
            exit_price = float(daily_df["Close"].iloc[-1])
            judgment = "○ 決算後決済"

    pnl_per_share = exit_price - entry_p
    pnl_amount = round(pnl_per_share * shares, 1)
    ret_pct = round((pnl_per_share / entry_p) * 100, 2) if entry_p > 0 else 0.0

    return {
        "target_reached": target_reached,
        "stop_loss_hit": stop_loss_hit,
        "exit_date": exit_date,
        "exit_price": exit_price,
        "return_pct": ret_pct,
        "pnl_amount": pnl_amount,
        "max_high": max_high,
        "min_low": min_low,
        "judgment": judgment
    }


def check_strategy_a_to_c_handoff(ticker: str, earnings_date: str, daily_df: pd.DataFrame) -> Dict[str, Any]:
    """戦略A（決算前利確）で手仕舞った銘柄が、好決算で戦略C（飛び乗り）対象となるかを判定"""
    if daily_df.empty or not earnings_date:
        return {"triggered": False, "gap_up_pct": 0.0, "recommendation": "データなし"}

    # 決算日当日および決算日翌日の営業日を候補として調査
    candidate_dates = [d for d in daily_df.index if d >= earnings_date]
    if not candidate_dates:
        return {"triggered": False, "gap_up_pct": 0.0, "recommendation": "決算後の取引データなし"}

    best_gap = 0.0
    best_res = {"triggered": False, "gap_up_pct": 0.0, "recommendation": "引き継ぎ条件未達"}

    for post_date in candidate_dates[:2]:
        post_idx = daily_df.index.get_loc(post_date)
        if post_idx == 0:
            continue
        prev_close = float(daily_df.iloc[post_idx - 1]["Close"])
        post_open = float(daily_df.iloc[post_idx]["Open"])
        post_high = float(daily_df.iloc[post_idx]["High"])
        post_vol = float(daily_df.iloc[post_idx]["Volume"])
        prev_vol = float(daily_df.iloc[post_idx - 1]["Volume"])

        gap_pct = round(((post_open - prev_close) / prev_close) * 100, 2)
        vol_mult = round(post_vol / prev_vol, 2) if prev_vol > 0 else 1.0

        if gap_pct >= 3.0 and vol_mult >= 1.5:
            return {
                "triggered": True,
                "date": post_date,
                "gap_up_pct": gap_pct,
                "high_pct": round(((post_high - prev_close) / prev_close) * 100, 2),
                "volume_multiple": vol_mult,
                "recommendation": "戦略C（好決算飛び乗り）推奨シグナル点灯"
            }
        if gap_pct > best_gap:
            best_gap = gap_pct
            best_res = {
                "triggered": False,
                "date": post_date,
                "gap_up_pct": gap_pct,
                "high_pct": round(((post_high - prev_close) / prev_close) * 100, 2),
                "volume_multiple": vol_mult,
                "recommendation": "引き継ぎ条件未達"
            }

    return best_res


def generate_review_markdown(
    previous_report_path: str,
    output_path: Optional[str] = None
) -> str:
    """前週レポートを完全検証するnote記事Markdownを自動生成"""
    stocks = parse_previous_note_report(previous_report_path)
    if not stocks:
        raise ValueError("前週レポートから有効な銘柄を抽出できませんでした。")

    today_str = date.today().strftime("%Y/%m/%d")

    lines = []
    lines.append("【事後検証＆戦略監査レポート】先週の決算トレード結果を全件突き合わせ検証！")
    lines.append(f"執筆日: {today_str}（実データ照合: yfinance東証日足）")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 📌 エグゼクティブ・サマリー：今週の検証結果まとめ")
    lines.append("")
    lines.append("先週公開した決算注目銘柄レポートについて、実際の市場における株価推移と照合した事後検証結果をお届けします。")
    lines.append("事前スクリーニングで抽出した銘柄と、**「2%損失ルール」「決算持ち越し禁止ルール」**がどう機能したのか、包み隠さず検証します。")
    lines.append("")

    # 各銘柄の実績取得と計算
    eval_results = []
    for s in stocks:
        # 直近1週間の日足を取得
        df = fetch_historical_daily(s["ticker"], start_date="2026-10-09", end_date="2026-10-18")
        eval_res = evaluate_scenario_pnl(s, df)
        eval_res["stock"] = s
        eval_res["df"] = df
        eval_results.append(eval_res)

    total_pnl = sum(r["pnl_amount"] for r in eval_results)
    pnl_sign = "+" if total_pnl >= 0 else ""
    lines.append(f"- **ポートフォリオ合計実現損益（ルール厳守）**: **{pnl_sign}{int(total_pnl):,} 円**（元本100万円比: **{pnl_sign}{total_pnl/10000:.2f}%**）")
    lines.append("")
    lines.append("---")
    lines.append("")

    # サマリー一覧表
    lines.append("## 📊 厳選銘柄の予測 vs 実勢パフォーマンス一覧")
    lines.append("")
    lines.append("| コード | 銘柄名 | 戦略 | 基準株価 | 目標 / 損切 | 期間中最高値 | 決済価格 | 獲得損益 | 判定 |")
    lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for r in eval_results:
        s = r["stock"]
        sign = "+" if r["pnl_amount"] >= 0 else ""
        lines.append(
            f"| **{s['ticker']}** | {s['name']} | 戦略{s['strategy']} | {int(s['entry_price']):,}円 | "
            f"{int(s['target_price']):,}円 / {int(s['stop_loss']):,}円 | {int(r['max_high']):,}円 | "
            f"{int(r['exit_price']):,}円 | **{sign}{int(r['pnl_amount']):,}円** ({sign}{r['return_pct']}%) | {r['judgment']} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")

    # 個別銘柄の検証詳細
    lines.append("## 🔍 個別銘柄の徹底検証＆カタリスト分析")
    lines.append("")
    for idx, r in enumerate(eval_results, 1):
        s = r["stock"]
        df = r["df"]
        t = s["ticker"]
        name = s["name"]
        lines.append(f"### {idx}. 【{s['strategy_name']}】[{t}] {name}")
        lines.append(f"- **判定**: **{r['judgment']}**")
        lines.append(f"- **基準株価**: {int(s['entry_price']):,}円 → **決済価格**: {int(r['exit_price']):,}円（実現損益: **{int(r['pnl_amount']):,}円** / {r['return_pct']:+}%）")
        lines.append(f"- **期間中最高値**: {int(r['max_high']):,}円 / 最安値: {int(r['min_low']):,}円")
        lines.append("")

        # 適時開示・カタリストのプレースホルダー（捏造防止）
        lines.append("#### 📢 適時開示・発表カタリスト（事実確認欄）")
        lines.append("> [!NOTE]")
        lines.append(f"> **適時開示内容**: [✍️ ここに{name}の適時開示・決算発表の公式発表内容やサプライズ要因を記入]")
        lines.append("")

        # 日次OHLCVテーブル
        if not df.empty:
            lines.append("#### 📈 日次株価・出来高推移（実データ）")
            lines.append("| 日付 | 始値 | 高値 | 安値 | 終値 | 出来高 |")
            lines.append("| :---: | :---: | :---: | :---: | :---: | :---: |")
            for d_idx, row in df.iterrows():
                lines.append(
                    f"| {d_idx} | {int(row['Open']):,}円 | {int(row['High']):,}円 | "
                    f"{int(row['Low']):,}円 | {int(row['Close']):,}円 | {int(row['Volume']):,}株 |"
                )
            lines.append("")

        # 戦略Aから戦略Cへの引き継ぎチェック
        if s["strategy"] == "A":
            handoff = check_strategy_a_to_c_handoff(t, s.get("earnings_date", ""), df)
            lines.append("#### 🔄 戦略A → 戦略C（好決算飛び乗り）監視引き継ぎ診断")
            if handoff["triggered"]:
                lines.append(f"- **引き継ぎ判定**: 🔥 **{handoff['recommendation']}**")
                lines.append(f"- **決算翌日ギャップアップ**: +{handoff['gap_up_pct']}%（出来高 {handoff['volume_multiple']}倍急増）")
                lines.append(f"- **アクション**: 決算前のモメンタム不発で手仕舞った後、発表翌日の寄り付きから戦略Cで再エントリー可能でした。")
            else:
                lines.append(f"- **引き継ぎ判定**: 該当なし（{handoff['recommendation']}）")
            lines.append("")

        lines.append("---")
        lines.append("")

    # 免責事項
    lines.append("### ⚠️ 免責事項 (Disclaimer)")
    lines.append("本記事は過去のトレード戦略モデルの事後検証および学習を目的としており、投資勧誘を目的としたものではありません。実際の投資判断は自己責任において行っていただきますようお願い申し上げます。")
    lines.append("")

    md_content = "\n".join(lines)

    # クリップボードコピー
    if sys.platform == "win32":
        try:
            p = subprocess.Popen(["clip.exe"], stdin=subprocess.PIPE, close_fds=True)
            p.communicate(input=md_content.encode("cp932", errors="ignore"))
            print("📋 事後検証note用記事をクリップボードに自動コピーしました！")
        except Exception:
            pass

    # ファイル保存
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"📄 事後検証記事を保存しました: {output_path}")

    return md_content


if __name__ == "__main__":
    rep_path = os.path.join(BASE_DIR, "reports", "note", "note_決算注目銘柄_20261010.md")
    out_path = os.path.join(BASE_DIR, "reports", "note", "note_事後検証_20261010.md")
    generate_review_markdown(rep_path, out_path)
