#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
決算トレード・サイクル予測検証システム
次期シーズン分析・学習・スコアリングエンジン (analyzer.py)

過去の予測データと決算後1週間の結果を横断分析し、
テクニカルパターン別勝率、進捗率別リターン、プロフィットファクター、失敗傾向を抽出し、
次期決算シーズンでの予測精度向上にフィードバックするエンジン
"""

import json
from typing import Dict, Any, List, Optional
try:
    from tools.db import get_all_records, get_connection
except ImportError:
    from db import get_all_records, get_connection


def generate_season_analysis(season_id: Optional[str] = None) -> Dict[str, Any]:
    """
    指定シーズン（または全期間）の決算トレード結果を分析し、
    次期決算シーズンに向けた実践的インサイトを生成する
    """
    records = get_all_records(season_id)
    # 結果が記録されているレコードのみ抽出
    completed = [r for r in records if r["status"] == "completed" and r["win_loss"]]

    if not completed:
        return {
            "total_trades": len(records),
            "completed_trades": 0,
            "win_rate": 0.0,
            "message": "完了したトレード結果がまだありません。決算後1週間の結果を記録してください。"
        }

    total_completed = len(completed)
    wins = [r for r in completed if r["win_loss"] == "WIN"]
    losses = [r for r in completed if r["win_loss"] == "LOSS"]
    draws = [r for r in completed if r["win_loss"] == "DRAW"]

    win_rate = round((len(wins) / total_completed) * 100, 1)

    # リターン計算
    actual_returns = [r["actual_return_pct"] for r in completed]
    max_gains = [r["max_gain_pct"] for r in completed]

    avg_actual_return = round(sum(actual_returns) / total_completed, 2)
    avg_max_gain = round(sum(max_gains) / total_completed, 2)

    # 総利益と総損失からプロフィットファクター計算
    gross_profit = sum(r["actual_return_pct"] for r in wins if r["actual_return_pct"] > 0)
    gross_loss = abs(sum(r["actual_return_pct"] for r in losses if r["actual_return_pct"] < 0))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.9 if gross_profit > 0 else 1.0)

    # 目標株価達成率
    target_hits = sum(1 for r in completed if r["target_hit"] == 1)
    target_hit_rate = round((target_hits / total_completed) * 100, 1)

    # 1. テクニカルパターン別集計
    pattern_stats = {}
    for r in completed:
        pat = r["technical_pattern"]
        if pat not in pattern_stats:
            pattern_stats[pat] = {"total": 0, "wins": 0, "max_gains": [], "returns": []}
        pattern_stats[pat]["total"] += 1
        if r["win_loss"] == "WIN":
            pattern_stats[pat]["wins"] += 1
        pattern_stats[pat]["max_gains"].append(r["max_gain_pct"])
        pattern_stats[pat]["returns"].append(r["actual_return_pct"])

    pattern_ranking = []
    for pat, data in pattern_stats.items():
        p_win_rate = round((data["wins"] / data["total"]) * 100, 1)
        p_avg_gain = round(sum(data["max_gains"]) / data["total"], 2)
        p_avg_return = round(sum(data["returns"]) / data["total"], 2)
        pattern_ranking.append({
            "pattern": pat,
            "sample_count": data["total"],
            "wins": data["wins"],
            "win_rate": p_win_rate,
            "avg_max_gain": p_avg_gain,
            "avg_return": p_avg_return
        })
    # 勝率順にソート
    pattern_ranking.sort(key=lambda x: (x["win_rate"], x["avg_return"]), reverse=True)

    # 2. 業績進捗率別集計（進捗率 >= 80% vs 50-80% vs <50%）
    progress_buckets = {
        "80%以上 (超高進捗)": {"total": 0, "wins": 0, "returns": []},
        "50%〜79% (標準進捗)": {"total": 0, "wins": 0, "returns": []},
        "50%未満 (低進捗)": {"total": 0, "wins": 0, "returns": []}
    }
    for r in completed:
        p_rate = r["progress_rate"] or 0.0
        if p_rate >= 80.0:
            b_key = "80%以上 (超高進捗)"
        elif p_rate >= 50.0:
            b_key = "50%〜79% (標準進捗)"
        else:
            b_key = "50%未満 (低進捗)"
        progress_buckets[b_key]["total"] += 1
        if r["win_loss"] == "WIN":
            progress_buckets[b_key]["wins"] += 1
        progress_buckets[b_key]["returns"].append(r["actual_return_pct"])

    progress_summary = []
    for b_key, b_data in progress_buckets.items():
        if b_data["total"] > 0:
            b_win_rate = round((b_data["wins"] / b_data["total"]) * 100, 1)
            b_avg_return = round(sum(b_data["returns"]) / b_data["total"], 2)
            progress_summary.append({
                "bucket": b_key,
                "count": b_data["total"],
                "win_rate": b_win_rate,
                "avg_return": b_avg_return
            })

    # 3. 次期シーズン向け具体的インサイト生成
    actionable_insights = []
    if pattern_ranking:
        best_pat = pattern_ranking[0]
        actionable_insights.append(
            f"【最優秀テクニカル】『{best_pat['pattern']}』は勝率 {best_pat['win_rate']}%（平均最大上昇 +{best_pat['avg_max_gain']}%）と極めて高いパフォーマンスを記録。次期シーズンでは最優先ピックアップ対象として推奨。"
        )
    if len(pattern_ranking) > 1:
        worst_pat = pattern_ranking[-1]
        if worst_pat["win_rate"] < 50.0:
            actionable_insights.append(
                f"【要注意パターン】『{worst_pat['pattern']}』は勝率 {worst_pat['win_rate']}% に留まりました。決算前の出尽くしや騙しブレイクが疑われるため、次期シーズンは参入基準（出来高確認等）を厳格化してください。"
            )

    high_prog = next((b for b in progress_summary if "80%以上" in b["bucket"]), None)
    if high_prog and high_prog["win_rate"] >= 65.0:
        actionable_insights.append(
            f"【業績の優位性】進捗率80%超の銘柄は勝率 {high_prog['win_rate']}%（平均リターン +{high_prog['avg_return']}%）と上方修正期待が素直に株価上昇に結びついています。"
        )

    # 失敗トレードの反省メモ集約
    loss_reviews = [
        {"ticker": r["ticker"], "name": r["name"], "notes": r["review_notes"]}
        for r in losses if r.get("review_notes")
    ]

    return {
        "season_id": season_id or "全期間",
        "total_predictions": len(records),
        "completed_trades": total_completed,
        "wins": len(wins),
        "losses": len(losses),
        "draws": len(draws),
        "win_rate": win_rate,
        "avg_actual_return": avg_actual_return,
        "avg_max_gain": avg_max_gain,
        "profit_factor": profit_factor,
        "target_hit_rate": target_hit_rate,
        "pattern_ranking": pattern_ranking,
        "progress_summary": progress_summary,
        "actionable_insights": actionable_insights,
        "loss_reviews": loss_reviews
    }


def generate_markdown_report(season_id: Optional[str] = None) -> str:
    """次期決算シーズン向け学習レポート（Markdown形式）の生成"""
    analysis = generate_season_analysis(season_id)
    if "message" in analysis:
        return f"# 決算トレード シーズン分析レポート\n\n{analysis['message']}"

    md = f"""# 📊 決算トレード シーズン分析・次期予測指針レポート
**対象シーズン: {analysis['season_id']}**

---

## 1. 総合パフォーマンス
- **検証済みトレード数**: {analysis['completed_trades']} 件 （総予測数: {analysis['total_predictions']} 件）
- **勝敗**: {analysis['wins']} 勝 {analysis['losses']} 敗 {analysis['draws']} 分
- **勝率**: **{analysis['win_rate']}%**
- **平均最大上昇率 (1週間以内)**: **+{analysis['avg_max_gain']}%**
- **平均確定リターン (1週間後終値)**: **+{analysis['avg_actual_return']}%**
- **プロフィットファクター (PF)**: **{analysis['profit_factor']}**
- **目標株価的中率**: **{analysis['target_hit_rate']}%**

---

## 2. テクニカルパターン別 実績ランキング
次期決算シーズンにおける銘柄選定の重み付け基準となります。

| 順位 | テクニカルパターン | サンプル数 | 勝率 | 平均最大上昇率 | 平均確定損益 |
|:---:|:---|:---:|:---:|:---:|:---:|
"""
    for i, p in enumerate(analysis["pattern_ranking"], 1):
        md += f"| {i} | {p['pattern']} | {p['sample_count']} | **{p['win_rate']}%** | +{p['avg_max_gain']}% | {p['avg_return']:+.2f}% |\n"

    md += """
---

## 3. 業績進捗率帯別のパフォーマンス比較
| 進捗率帯 | サンプル数 | 勝率 | 平均確定損益 |
|:---|:---:|:---:|:---:|
"""
    for prog in analysis["progress_summary"]:
        md += f"| {prog['bucket']} | {prog['count']} | **{prog['win_rate']}%** | {prog['avg_return']:+.2f}% |\n"

    md += """
---

## 4. 💡 次期決算シーズンへの学習フィードバック・アクションプラン
"""
    for insight in analysis["actionable_insights"]:
        md += f"- {insight}\n"

    if analysis["loss_reviews"]:
        md += "\n### ⚠️ 敗戦事例からの教訓・メモ\n"
        for lr in analysis["loss_reviews"]:
            md += f"- **[{lr['ticker']}] {lr['name']}**: {lr['notes']}\n"

    return md


if __name__ == "__main__":
    import sys
    report = generate_markdown_report()
    try:
        print("Analyzer Test:")
        print(report)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(report.encode("utf-8"))

