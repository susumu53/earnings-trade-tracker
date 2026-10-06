#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
決算トレード・サイクル予測検証システム
note記事自動生成エンジン (note_generator.py)

毎週土曜日にローカルで実行され、来週（決算約1週間前）に決算発表を迎える
注目銘柄のテクニカル分析・業績進捗・100万円資金管理シナリオをまとめた
note投稿用Markdown記事を出力します。
"""

import os
import sys
import subprocess
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from tools.db import init_db
from tools.auto_screener import auto_screen_upcoming_opportunities
from tools.earnings_scanner import scan_earnings_dates_bulk
try:
    from tools.universe import get_stock_info
except ImportError:
    get_stock_info = None

# 英語業種の日本語フォールバック変換辞書
SECTOR_JA_MAP = {
    "Consumer Cyclical": "一般消費財・小売",
    "Consumer Defensive": "生活必需品・小売",
    "Technology": "情報通信・IT",
    "Communication Services": "サービス・通信",
    "Healthcare": "医薬品・ヘルスケア",
    "Industrials": "機械・製造・産業",
    "Financial Services": "金融・保険",
    "Basic Materials": "素材・化学",
    "Real Estate": "不動産",
    "Energy": "エネルギー・資源",
    "Utilities": "電力・ガス"
}


def get_upcoming_week_dates() -> Dict[str, Any]:
    """直近の土曜日基準、または今日基準で来週月曜〜金曜の日付範囲を計算"""
    today = date.today()
    # 次の月曜日（または今日の週の月曜日）
    days_ahead = (0 - today.weekday()) % 7
    if days_ahead == 0 and today.weekday() != 0:
        days_ahead = 7
    next_monday = today + timedelta(days=days_ahead)
    next_friday = next_monday + timedelta(days=4)

    # 決算日ターゲット: 今日から見て2日〜10日後 (来週月曜〜金曜＋前後数日)
    return {
        "today": today,
        "monday": next_monday,
        "friday": next_friday,
        "title_week": f"{next_monday.year}年{next_monday.month}月{next_monday.day}日週",
    }


def format_currency(val: float) -> str:
    if val is None or val == 0:
        return "---"
    return f"{int(round(val)):,} 円"


def generate_note_markdown(opportunities: List[Dict[str, Any]], week_info: Dict[str, Any]) -> str:
    """note記事用の洗練されたMarkdownテキストを生成"""
    today_str = week_info["today"].strftime("%Y/%m/%d")
    week_str = week_info["title_week"]

    # 銘柄名と業種名を日本語に統一・補正
    for o in opportunities:
        t_code = str(o.get("ticker", "")).strip().upper().replace(".T", "")
        if get_stock_info:
            meta = get_stock_info(t_code)
            if meta:
                if meta.get("name"):
                    o["name"] = meta["name"]
                if meta.get("sector"):
                    o["sector"] = meta["sector"]
        # sectorが英語の場合は日本語に翻訳
        cur_sec = o.get("sector", "")
        if cur_sec in SECTOR_JA_MAP:
            o["sector"] = SECTOR_JA_MAP[cur_sec]

    # 決算日順、かつスコア順にソート
    sorted_opps = sorted(
        opportunities,
        key=lambda x: (x.get("days_until_earnings", 99), -x.get("score", 0))
    )

    lines = []
    # 記事タイトル
    lines.append(f"【週刊・決算トレード分析】来週（{week_str}）決算発表！注目の決算プレトレード候補銘柄＆テクニカル戦略まとめ")
    lines.append("")
    lines.append(f"執筆日: {today_str}（東証全銘柄データ解析）")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 📌 はじめに：来週の決算トレード注目ポイント")
    lines.append("")
    lines.append("決算発表前後の株価は、思惑や好業績サプライズ、テクニカルな節目が重なり、大きな値動き（ボラティリティ）が発生します。")
    lines.append("本記事では、東証全上場銘柄の中から **「来週（決算約1週間前）に決算を控える銘柄」** を独自スクリーニング。")
    lines.append("")
    lines.append("以下の3大プロ戦略に基づき、**業績進捗率・テクニカルチャート形状・リスクリワード（1:2以上）・資金管理**の基準をクリアした注目銘柄を厳選分析してお届けします。")
    lines.append("")
    lines.append("- ⚡ **戦略A（決算前モメンタム型）**: 決算発表の4〜10日前に仕込み、発表直前に利確して手仕舞う（持ち越しリスクなし）。")
    lines.append("- 🎯 **戦略B（決算またぎ上方修正型）**: 高進捗・上方修正期待銘柄に絞り、決算サプライズ大陽線を狙う。")
    lines.append("- 🚀 **戦略C（決算後好決算飛び乗り）**: 発表直後のギャップアップ初動に乗る。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"## 📊 来週の厳選注目銘柄一覧（計 {len(sorted_opps)} 銘柄）")
    lines.append("")

    if not sorted_opps:
        lines.append("※現在、来週決算で一定のスコア基準を満たす銘柄はありません。無理なエントリーは控え、次週の候補を待ちましょう。")
        lines.append("")
    else:
        # サマリー表
        lines.append("| コード | 銘柄名 | 決算日 | 現在株価 | 戦略 | 想定リターン | RR比 | スコア |")
        lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
        for o in sorted_opps:
            ret_str = f"+{o.get('expected_return_pct', 0)}%"
            lines.append(
                f"| **{o['ticker']}** | {o['name']} | {o.get('earnings_date', '--')} ({o.get('days_until_earnings', '?')}日後) | "
                f"{format_currency(o['current_price'])} | {o.get('strategy_name', '戦略')} | "
                f"{ret_str} | 1:{o.get('risk_reward_ratio', 2.0)} | **{o.get('score', 0)}pt** |"
            )
        lines.append("")
        lines.append("---")
        lines.append("")

        # 各銘柄の詳細分析
        lines.append("## 🔍 各銘柄の徹底テクニカル＆資金管理分析")
        lines.append("")

        for idx, o in enumerate(sorted_opps, 1):
            t = o["ticker"]
            name = o["name"]
            sector = o.get("sector", "その他")
            strat = o.get("strategy_name", "決算トレード")
            cur_price = o.get("current_price", 0)
            target = o.get("target_price", 0)
            stop = o.get("stop_loss", 0)
            exp_ret = o.get("expected_return_pct", 0)
            rr = o.get("risk_reward_ratio", 2.0)
            score = o.get("score", 0)
            rank = o.get("rank", "B")
            pattern = o.get("technical_pattern", "ブレイクアウト")
            edate = o.get("earnings_date", "--")
            days = o.get("days_until_earnings", 0)
            trade_action = o.get("trade_action", "")
            reasons = o.get("reasons", [])

            lines.append(f"### {idx}. 【{strat}】[{t}] {name}（{sector}）")
            lines.append("")
            lines.append(f"- **総合スコア**: **{score} 点** / 判定ランク: **{rank}**")
            lines.append(f"- **決算発表予定日**: **{edate}**（あと **{days} 日**）")
            lines.append(f"- **現在株価**: {format_currency(cur_price)}")
            lines.append(f"- **推奨売買アクション**: **{trade_action}**")
            lines.append("")

            # 業績進捗・上方修正確率
            rev_prob = o.get("revision_probability", "中")
            prog_rate = o.get("progress_rate", 0)
            lines.append("#### 📈 業績進捗 ＆ 上方修正確率")
            if prog_rate > 0:
                lines.append(f"- **経常利益進捗率**: **{prog_rate}%**")
            lines.append(f"- **上方修正確度判定**: **{rev_prob}**")
            lines.append("")

            # テクニカル分析
            lines.append("#### 📊 テクニカルチャート診断")
            lines.append(f"- **検出パターン**: **{pattern}**")
            ma25_bias = o.get("ma25_bias_pct")
            if ma25_bias is not None:
                lines.append(f"- **25日移動平均線乖離率**: {ma25_bias:+.1f}%")

            # 波動目標値
            wt = o.get("wave_targets", {})
            if wt:
                n_t = wt.get("N_target")
                v_t = wt.get("V_target")
                e_t = wt.get("E_target")
                if n_t and v_t and e_t:
                    lines.append(f"- **一目均衡表・波動目標値**: N計算値: {n_t:,}円 / V計算値: {v_t:,}円 / E計算値: {e_t:,}円")

            lines.append("- **抽出根拠**:")
            for r in reasons:
                lines.append(f"  - {r}")
            lines.append("")

            # 資金管理・ポジションサイジング（100万円元本）
            ps = o.get("position_sizing", {})
            lines.append("#### 🛡 100万円元本ベース 資金管理設計（2%損失ルール）")
            lines.append(f"- **目標利確株価**: **{format_currency(target)}**（想定リターン: **+{exp_ret}%**）")
            lines.append(f"- **損切りライン**: **{format_currency(stop)}**（許容損失率: -{abs(round((cur_price - stop) / cur_price * 100, 1))}%）")
            lines.append(f"- **リスクリワード比**: **1 : {rr}**（※プロ基準 1:2.0以上）")

            if ps:
                shares = ps.get("recommended_shares", 100)
                inv_amt = ps.get("total_investment", cur_price * shares)
                max_loss = ps.get("total_risk_amount", abs(cur_price - stop) * shares)
                lines.append(f"- **推奨買付株数**: **{shares:,} 株**（約 {int(inv_amt):,} 円 / ポートフォリオ比率: {ps.get('capital_weight_pct', 0)}%）")
                lines.append(f"- **最大許容リスク額**: {int(max_loss):,} 円（元本100万円の2.0%以内）")
            else:
                # 簡易算出
                risk_per_share = max(1.0, cur_price - stop)
                shares = max(100, int((20000 / risk_per_share) // 100) * 100)
                lines.append(f"- **推奨買付株数**: **{shares:,} 株**（約 {int(cur_price * shares):,} 円）")
                lines.append(f"- **最大許容リスク額**: {int(risk_per_share * shares):,} 円（最大許容損失2万円以内）")

            lines.append("")
            lines.append("---")
            lines.append("")

    # おわりに & 免責事項
    lines.append("## 💡 トレード実践における重要ルール")
    lines.append("1. **事前シナリオの徹底**: エントリー前に必ず「目標利確値」と「逆指値（ロスカット）」をセットしてください。")
    lines.append("2. **持ち越しルールの遵守**: 戦略A（決算前プレ）は決算前日引けまでに必ず手仕舞い、またぎリスクを避けてください。")
    lines.append("3. **地合いの確認**: 日経平均・TOPIXが大幅安の日は、個別銘柄も連れ安しやすいためロットを落とすか見送りが賢明です。")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("### ⚠️ 免責事項 (Disclaimer)")
    lines.append("本記事は、株式投資に関する情報提供およびテクニカル・決算分析の学習検証を目的として作成されたものであり、特定の銘柄の売買推奨や投資勧誘を目的としたものではありません。株式投資には元本割れを含む市場価格の変動リスクがあります。実際の投資判断および売買は、必ずご自身の責任とご判断において行っていただきますようお願い申し上げます。")
    lines.append("")

    return "\n".join(lines)


def copy_to_clipboard(text: str):
    """Windowsクリップボードにテキストをコピー"""
    if sys.platform == "win32":
        try:
            p = subprocess.Popen(["clip.exe"], stdin=subprocess.PIPE, close_fds=True)
            p.communicate(input=text.encode("cp932", errors="ignore"))
            print("📋 note用記事テキストをクリップボードに自動コピーしました！（そのままnoteに貼り付け可能）")
        except Exception as e:
            print(f"[クリップボードコピー失敗] {e}")


def run_weekly_note_generation(target_days_min: int = 2, target_days_max: int = 10, open_file: bool = True) -> str:
    print("=" * 65)
    print("  📝 週刊note記事 自動生成エンジン 起動中...")
    print(f"  決算対象範囲: {target_days_min}日後 〜 {target_days_max}日後（来週発表予定企業）")
    print("=" * 65)

    init_db()
    week_info = get_upcoming_week_dates()

    # 1. 銘柄スキャン＆スクリーニング (force_refresh=True, 候補プールを広めに取得)
    print("🔍 東証全銘柄から来週決算の注目企業をスクリーニング中...")
    all_opps = auto_screen_upcoming_opportunities(max_results=60, force_refresh=True)

    # 2. 決算1週間前（target_days_min <= days <= target_days_max）にフィルタリング
    target_opps = [
        o for o in all_opps
        if target_days_min <= o.get("days_until_earnings", 999) <= target_days_max
    ]

    # もし1週間前ピンポイントで少ない場合は、直近上位銘柄（0〜14日後）をフォールバックとして採用
    if len(target_opps) < 3 and all_opps:
        print(f"  ※対象日数範囲({target_days_min}〜{target_days_max}日)の該当が少ないため、直近の上位注目銘柄を採用します。")
        target_opps = all_opps[:8]
    else:
        # note記事として読みやすい厳選8〜10銘柄に調整
        target_opps = target_opps[:10]

    print(f"✅ 抽出完了: {len(target_opps)} 銘柄をnote記事にまとめます。")

    # 3. Markdownテキスト生成
    md_content = generate_note_markdown(target_opps, week_info)

    # 4. ローカル reports/note/ フォルダに出力
    reports_dir = os.path.join(BASE_DIR, "reports", "note")
    os.makedirs(reports_dir, exist_ok=True)

    today_str = week_info["today"].strftime("%Y%m%d")
    output_filename = f"note_決算注目銘柄_{today_str}.md"
    output_path = os.path.join(reports_dir, output_filename)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"\n📄 note記事ファイルを保存しました:")
    print(f"   -> {output_path}")

    # 5. クリップボードにコピー
    copy_to_clipboard(md_content)

    # 6. テキストエディタ（メモ帳）で自動オープン
    if open_file and sys.platform == "win32":
        try:
            os.startfile(output_path)
            print("📝 メモ帳で記事ファイルを開きました。")
        except Exception:
            pass

    print("=" * 65)
    print("🎉 note記事の作成が完了しました！そのままnoteに投稿できます。")
    print("=" * 65)
    return output_path


if __name__ == "__main__":
    min_d = 2
    max_d = 10
    if len(sys.argv) > 1:
        min_d = int(sys.argv[1])
    if len(sys.argv) > 2:
        max_d = int(sys.argv[2])
    run_weekly_note_generation(min_d, max_d)
