#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
決算トレード・サイクル予測検証システム
決算トレード特化 自動スクリーニングエンジン (auto_screener.py)

東証全銘柄から「決算日が近い銘柄」を抽出し、
プロトレーダーの3大戦略（戦略A: 決算前モメンタム / 戦略B: 決算またぎ上方修正 / 戦略C: 決算後PEAD）
に特化した精密スコアリングで、値上がり期待銘柄を自動分類・ピックアップする。

【3大戦略の定義】
  ⚡ 戦略A: 決算前モメンタム型（Pre-Earnings Drift）
     - 決算7〜14日前に仕込み、決算発表直前に利確して手仕舞う。持ち越しリスクゼロ。
  🎯 戦略B: 決算またぎ上方修正型（Surprise & S高狙い）
     - 決算直前（0〜3日前）に仕込み、サプライズ上方修正による翌日のS高や大ギャップアップを狙う。
  🚀 戦略C: 決算後PEAD型（Post-Earnings Announcement Drift）
     - 決算発表直後（0〜3日以内）の大商い・ブレイクアウト銘柄に乗り、数週間のドリフトを抜く。
"""

import math
import time
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from tools.market_data import fetch_stock_live_data, normalize_ticker
    from tools.predictor import query_historical_pattern_stats
    from tools.earnings_scanner import scan_earnings_dates_bulk
except ImportError:
    from market_data import fetch_stock_live_data, normalize_ticker
    from predictor import query_historical_pattern_stats
    from earnings_scanner import scan_earnings_dates_bulk


def evaluate_strategy_a(data: Dict[str, Any], days_until: int) -> Dict[str, Any]:
    """
    戦略A: 決算前モメンタム型（持ち越さない・先回り）の適性スコアリング（100点満点）
    - 狙い: 決算発表の7〜14日前に仕込み、前日引けまでに利確して手仕舞う
    """
    current_price = data["current_price"]
    exp_return = data["expected_return_pct"]
    rr_ratio = data["risk_reward_ratio"]
    pattern = data["technical_pattern"]
    ma25 = data["ma25"]
    ma75 = data["ma75"]
    bias25 = data["ma25_bias_pct"]
    volume_ratio = data.get("volume_ratio", 1.0)
    market_cap = data.get("market_cap", 0)
    cap_billion = market_cap / 1_000_000_000

    score = 0.0
    breakdown = {}

    # ① タイミング評価 (最大25点) - 7〜14日前が最良
    if 7 <= days_until <= 14:
        timing_score = 25.0
    elif 5 <= days_until <= 6:
        timing_score = 18.0
    elif 3 <= days_until <= 4:
        timing_score = 12.0
    elif 1 <= days_until <= 2:
        timing_score = 5.0  # 手仕舞い期に近いため低評価
    elif days_until == 0:
        timing_score = 0.0  # 当日は戦略Aの仕込み対象外
    else:
        timing_score = 8.0
    score += timing_score
    breakdown["timing"] = timing_score

    # ② 押し目・過熱感評価 (最大25点) - 25MA直上が最良（まだ上がりきっていない）
    if 0.0 <= bias25 <= 4.0:
        bias_score = 25.0  # 絶好の仕込み水準
    elif 4.0 < bias25 <= 8.0:
        bias_score = 18.0
    elif -3.0 <= bias25 < 0.0:
        bias_score = 15.0  # 25日線押し目
    elif 8.0 < bias25 <= 12.0:
        bias_score = 8.0   # やや上昇ピッチ速い
    elif bias25 > 12.0:
        bias_score = -10.0 # 先食い過熱（急反落リスク大）
    else:
        bias_score = -5.0  # 下降トレンド
    score += bias_score
    breakdown["ma_bias"] = bias_score

    # ③ 出来高先行性 (最大20点) - 大口の緩やかな先回り買い（1.2〜2.0倍）
    if 1.3 <= volume_ratio <= 2.2:
        vol_score = 20.0  # 先回り買いの絶好サイン
    elif volume_ratio > 2.2:
        vol_score = 14.0  # すでに出来高過熱気味
    elif 1.0 <= volume_ratio < 1.3:
        vol_score = 12.0
    elif 0.7 <= volume_ratio < 1.0:
        vol_score = 5.0
    else:
        vol_score = -5.0  # 閑散
    score += vol_score
    breakdown["volume"] = vol_score

    # ④ チャート形状 (最大15点)
    if pattern in ["25日線押し目反発型", "カップウィズハンドル型"]:
        tech_score = 15.0
    elif pattern == "直近高値ブレイク型":
        tech_score = 12.0
    elif pattern == "ボリンジャースクイーズ型":
        tech_score = 10.0
    else:
        tech_score = 5.0
    if current_price >= ma25 >= ma75:
        tech_score = min(15.0, tech_score + 3.0)
    score += tech_score
    breakdown["technical"] = tech_score

    # ⑤ リスクリワード (最大15点)
    rr_score = 0.0
    if rr_ratio >= 2.5:
        rr_score += 10.0
    elif rr_ratio >= 1.5:
        rr_score += 6.0
    if 8.0 <= exp_return <= 20.0:
        rr_score += 5.0  # 手堅い上昇余地
    elif exp_return > 20.0:
        rr_score += 3.0
    score += rr_score
    breakdown["risk_reward"] = rr_score

    score = max(10.0, min(98.0, round(score, 1)))

    reasons = [
        f"決算{days_until}日前（先回り仕込み好機）",
        f"25MA乖離率 {bias25:+.1f}%（過熱前の健全水準）",
        f"出来高比率 {volume_ratio:.1f}倍（先回り買い検出）"
    ]
    if pattern in ["25日線押し目反発型", "カップウィズハンドル型"]:
        reasons.append(f"反発支持形状（{pattern}）")

    return {
        "score": score,
        "strategy_id": "A",
        "strategy_name": "戦略A: 決算前モメンタム",
        "badge": "決算前モメンタム",
        "action_plan": f"⚡ 決算前日までに利確！決算発表（あと{days_until}日）は持ち越さない",
        "reasons": reasons,
        "breakdown": breakdown
    }


def evaluate_strategy_b(data: Dict[str, Any], days_until: int) -> Dict[str, Any]:
    """
    戦略B: 決算またぎ上方修正型（ストップ高・サプライズ狙い）の適性スコアリング（100点満点）
    - 狙い: 決算直前（0〜3日前）に仕込み、好決算・上方修正で翌日のストップ高を狙う
    """
    current_price = data["current_price"]
    exp_return = data["expected_return_pct"]
    rr_ratio = data["risk_reward_ratio"]
    pattern = data["technical_pattern"]
    ma25 = data["ma25"]
    ma75 = data["ma75"]
    bias25 = data["ma25_bias_pct"]
    volume_ratio = data.get("volume_ratio", 1.0)
    market_cap = data.get("market_cap", 0)
    cap_billion = market_cap / 1_000_000_000

    score = 0.0
    breakdown = {}

    # ① タイミング評価 (最大25点) - 0〜3日前の直前が最良
    if 0 <= days_until <= 2:
        timing_score = 25.0  # 直前仕込み局面
    elif 3 <= days_until <= 5:
        timing_score = 18.0
    elif 6 <= days_until <= 9:
        timing_score = 10.0
    else:
        timing_score = 5.0   # 10日以上前はまだ早い
    score += timing_score
    breakdown["timing"] = timing_score

    # ② チャート強度 & パーフェクトオーダー (最大25点) - 強い上放れ形状
    tech_score = 0.0
    if pattern == "直近高値ブレイク型":
        tech_score = 20.0
    elif pattern == "カップウィズハンドル型":
        tech_score = 18.0
    elif pattern == "ボリンジャースクイーズ型":
        tech_score = 15.0
    else:
        tech_score = 8.0
    if current_price >= ma25 >= ma75:
        tech_score = min(25.0, tech_score + 5.0)  # トレンドの完全一致
    score += tech_score
    breakdown["technical"] = tech_score

    # ③ 爆発力・時価総額フィルター (最大20点) - 100億〜1500億円の中小型株がストップ高しやすい
    if 100 <= cap_billion <= 800:
        cap_score = 20.0   # S高本命ゾーン（中小型・値動き軽い）
    elif 800 < cap_billion <= 2000:
        cap_score = 14.0   # 中型株
    elif 30 <= cap_billion < 100:
        cap_score = 12.0   # 小型株
    elif 2000 < cap_billion <= 5000:
        cap_score = 6.0    # 大型株（S高しにくい）
    elif cap_billion > 5000:
        cap_score = 0.0    # 超大型株
    else:
        cap_score = 5.0    # 不明/超小型
    score += cap_score
    breakdown["market_cap"] = cap_score

    # ④ 出来高の強さ (最大15点) - 大口の本格買い
    if volume_ratio >= 1.8:
        vol_score = 15.0
    elif volume_ratio >= 1.3:
        vol_score = 11.0
    elif volume_ratio >= 0.9:
        vol_score = 6.0
    else:
        vol_score = -3.0
    score += vol_score
    breakdown["volume"] = vol_score

    # ⑤ 一撃リターン期待値 (最大15点) - +15%以上の大相場余地
    rr_score = 0.0
    if exp_return >= 20.0:
        rr_score += 10.0
    elif exp_return >= 12.0:
        rr_score += 6.0
    if rr_ratio >= 2.5:
        rr_score += 5.0
    elif rr_ratio >= 1.5:
        rr_score += 3.0
    score += rr_score
    breakdown["risk_reward"] = rr_score

    # ⑥ 業績成長率 & 上方修正確率（progress_calculator連動）
    rev_stars = data.get("revision_stars", 3)
    e_growth = data.get("earnings_growth")
    fundamental_score = 0.0
    if rev_stars == 5:
        fundamental_score = 15.0  # 上方修正確率80%超（決算またぎ超本命）
    elif rev_stars == 4:
        fundamental_score = 10.0  # 上方修正確率50-70%
    elif rev_stars == 3:
        fundamental_score = 4.0
    elif rev_stars == 2:
        fundamental_score = 0.0
    elif rev_stars <= 1:
        fundamental_score = -15.0 # 減益下方修正リスク（決算またぎ厳禁ペナルティ）
    score += fundamental_score
    breakdown["fundamentals"] = fundamental_score

    score = max(10.0, min(99.0, round(score, 1)))

    reasons = [
        f"決算まであと{days_until}日（決算またぎ直前局面）",
        f"形状: {pattern}（強い上昇モメンタム）",
    ]
    if current_price >= ma25 >= ma75:
        reasons.append("25MA・75MAパーフェクトオーダー（上値追いの順風）")
    if 100 <= cap_billion <= 800:
        reasons.append(f"時価総額 {int(cap_billion)}億円（S高が出やすい中小型急騰ゾーン）")
    if rev_stars >= 4:
        reasons.append(f"上方修正確率 {data.get('revision_probability', '')}")
    if e_growth is not None:
        reasons.append(f"純利益成長率 {e_growth:+.1f}%")

    return {
        "score": score,
        "strategy_id": "B",
        "strategy_name": "戦略B: 決算またぎ上方修正",
        "badge": "決算またぎ本命",
        "action_plan": f"🎯 上方修正ストップ高狙い！決算発表（あと{days_until}日）をまたいで勝負",
        "reasons": reasons,
        "breakdown": breakdown
    }


def evaluate_strategy_c(data: Dict[str, Any], days_until: int) -> Dict[str, Any]:
    """
    戦略C: 決算後PEAD型（発表後ドリフト・安全追随）の適性スコアリング（100点満点）
    - 狙い: 決算発表直後（0〜3日以内）に好決算＋大出来高で急騰した銘柄の初押しや追随を狙う
    """
    current_price = data["current_price"]
    exp_return = data["expected_return_pct"]
    rr_ratio = data["risk_reward_ratio"]
    pattern = data["technical_pattern"]
    ma25 = data["ma25"]
    bias25 = data["ma25_bias_pct"]
    volume_ratio = data.get("volume_ratio", 1.0)
    market_cap = data.get("market_cap", 0)
    cap_billion = market_cap / 1_000_000_000

    score = 0.0
    breakdown = {}

    # ① タイミング評価 (最大30点) - 本日〜2日後が最良
    if days_until == 0:
        timing_score = 30.0  # 本日決算発表！即座にリアクション追随
    elif 1 <= days_until <= 2:
        timing_score = 22.0  # 発表直前〜直後の転換
    elif 3 <= days_until <= 5:
        timing_score = 14.0
    else:
        timing_score = 5.0
    score += timing_score
    breakdown["timing"] = timing_score

    # ② 出来高急増 (最大25点) - 発表前後の大商い（機関参入の証拠）
    if volume_ratio >= 2.5:
        vol_score = 25.0  # 機関投資家の猛烈な買い増し
    elif volume_ratio >= 1.8:
        vol_score = 20.0
    elif volume_ratio >= 1.3:
        vol_score = 12.0
    else:
        vol_score = 0.0
    score += vol_score
    breakdown["volume"] = vol_score

    # ③ 高値ブレイクアウト (最大25点)
    tech_score = 0.0
    if pattern == "直近高値ブレイク型":
        tech_score = 25.0
    elif pattern == "カップウィズハンドル型":
        tech_score = 20.0
    elif pattern == "ボリンジャースクイーズ型":
        tech_score = 15.0
    else:
        tech_score = 8.0
    score += tech_score
    breakdown["technical"] = tech_score

    # ④ 押し目水準 (最大20点) - 乖離が大きすぎない押し目
    if 2.0 <= bias25 <= 8.0:
        bias_score = 20.0
    elif 8.0 < bias25 <= 15.0:
        bias_score = 12.0
    elif bias25 > 15.0:
        bias_score = 2.0  # やや過熱
    else:
        bias_score = 10.0
    score += bias_score
    breakdown["ma_bias"] = bias_score

    score = max(10.0, min(98.0, round(score, 1)))

    reasons = [
        f"決算発表タイミング（あと{days_until}日）での急変動注目",
        f"出来高比率 {volume_ratio:.1f}倍（機関投資家の大商い）",
        f"ブレイク形状: {pattern}"
    ]

    return {
        "score": score,
        "strategy_id": "C",
        "strategy_name": "戦略C: 決算後PEAD",
        "badge": "決算後PEAD",
        "action_plan": f"🚀 決算後ドリフト（PEAD）！発表内容確認後の初押しエントリー",
        "reasons": reasons,
        "breakdown": breakdown
    }


def evaluate_stock_for_earnings_trade(ticker: str, days_until_earnings: int) -> Optional[Dict[str, Any]]:
    """
    1銘柄の決算トレード適性を3大戦略（戦略A / 戦略B / 戦略C）で総合評価
    """
    try:
        data = fetch_stock_live_data(ticker)
    except Exception:
        return None

    current_price = data["current_price"]
    target_price = data["target_price"]
    stop_loss = data["stop_loss"]
    exp_return = data["expected_return_pct"]
    rr_ratio = data["risk_reward_ratio"]
    pattern = data["technical_pattern"]
    ma25 = data["ma25"]
    ma75 = data["ma75"]
    bias25 = data["ma25_bias_pct"]
    market_cap = data.get("market_cap", 0)
    volume_ratio = data.get("volume_ratio", 1.0)

    e_str = data.get("earnings_date")
    if not e_str:
        return None

    # 基本足切り
    if exp_return < 4.0 or rr_ratio < 0.9:
        return None

    # 3大戦略それぞれのスコアを算出
    eval_a = evaluate_strategy_a(data, days_until_earnings)
    eval_b = evaluate_strategy_b(data, days_until_earnings)
    eval_c = evaluate_strategy_c(data, days_until_earnings)

    # 過去実績勝率のボーナス加点
    hist_stats = query_historical_pattern_stats(pattern)
    win_rate = hist_stats.get("win_rate", 60.0)
    hist_bonus = 0.0
    if win_rate >= 75.0:
        hist_bonus = 5.0
    elif win_rate >= 65.0:
        hist_bonus = 3.0
    elif win_rate < 45.0:
        hist_bonus = -5.0

    eval_a["score"] = max(10.0, min(99.0, round(eval_a["score"] + hist_bonus, 1)))
    eval_b["score"] = max(10.0, min(99.0, round(eval_b["score"] + hist_bonus, 1)))
    eval_c["score"] = max(10.0, min(99.0, round(eval_c["score"] + hist_bonus, 1)))

    # 最適戦略（プライマリ戦略）を決定
    # 日数に基づく自然な優先度付け（7〜14日後はA優先、0〜2日後はBまたはC優先）
    scores = [
        (eval_a["score"], eval_a),
        (eval_b["score"], eval_b),
        (eval_c["score"], eval_c)
    ]
    scores.sort(key=lambda x: -x[0])
    best_eval = scores[0][1]

    # ランク判定
    best_score = best_eval["score"]
    if best_score >= 78:
        rank = "S (最有力・急騰期待)"
    elif best_score >= 65:
        rank = "A (有力・上昇トレンド)"
    elif best_score >= 50:
        rank = "B (押し目狙い)"
    else:
        rank = "C (中立)"

    return {
        "ticker": data["ticker"],
        "name": data["name"],
        "sector": data["sector"],
        "current_price": current_price,
        "earnings_date": e_str,
        "days_until_earnings": days_until_earnings,
        "technical_pattern": pattern,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "expected_return_pct": exp_return,
        "risk_reward_ratio": rr_ratio,
        "score": best_score,
        "rank": rank,
        # 戦略情報
        "strategy": best_eval["strategy_id"],
        "strategy_name": best_eval["strategy_name"],
        "strategy_badge": best_eval["badge"],
        "trade_action": best_eval["action_plan"],
        "reasons": best_eval["reasons"],
        "strategy_scores": {
            "A": eval_a["score"],
            "B": eval_b["score"],
            "C": eval_c["score"]
        },
        "score_breakdown": best_eval["breakdown"],
        "wave_targets": data["wave_targets"],
        "ma25": ma25,
        "ma25_bias_pct": bias25,
        "hist_win_rate": win_rate,
        "market_cap": market_cap,
        "volume_ratio": volume_ratio,
        "revision_probability": data.get("revision_probability", "★★★ 標準"),
        "earnings_growth": data.get("earnings_growth"),
        "revenue_growth": data.get("revenue_growth"),
        "operating_margins": data.get("operating_margins")
    }


def auto_screen_upcoming_opportunities(
    max_results: int = 30,
    max_universe: Optional[int] = None,
    force_refresh: bool = False,
    strategy_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    東証全銘柄から決算日が当日から14日後の銘柄を抽出し、
    3大決算戦略スコアリングで値上がり期待銘柄をピックアップする。

    Args:
        max_results: 返却する最大銘柄数
        max_universe: テスト用：チェックする最大銘柄数
        force_refresh: キャッシュを無視して再スキャン
        strategy_filter: 'A', 'B', 'C'（Noneなら全戦略）
    """
    print("[screener] Phase 1: 東証全銘柄の決算日スキャン (当日から14日後)...")
    earnings_hits, scan_stats = scan_earnings_dates_bulk(
        days_min=0,
        days_max=14,
        max_tickers=max_universe,
        force_refresh=force_refresh
    )

    if not earnings_hits:
        print("[screener] 決算日が当日から14日後の銘柄が見つかりませんでした。")
        return []

    print(f"[screener] Phase 1 完了: {len(earnings_hits)}銘柄が決算当日から14日後")
    print(f"[screener] Phase 2: {len(earnings_hits)}銘柄の3大戦略詳細分析開始...")
    opportunities = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_hit = {
            executor.submit(
                evaluate_stock_for_earnings_trade,
                hit["code"],
                hit["days_until"]
            ): hit
            for hit in earnings_hits
        }
        completed = 0
        for future in as_completed(future_to_hit):
            completed += 1
            try:
                res = future.result()
                if res and res["score"] >= 50.0:
                    if not strategy_filter or res["strategy"] == strategy_filter.upper():
                        opportunities.append(res)
            except Exception:
                continue

            if completed % 20 == 0:
                print(f"  [{completed}/{len(earnings_hits)}] 分析済み... 候補: {len(opportunities)}件")

    # スコア順にソート
    opportunities.sort(key=lambda x: (-x["score"], x["days_until_earnings"], -x["expected_return_pct"]))

    print(f"[screener] Phase 2 完了: {len(opportunities)}銘柄がスコア50点以上（上位{max_results}件を返却）")
    return opportunities[:max_results]


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    start_t = time.time()
    print("3大決算戦略スクリーナーを実行中...\n")
    results = auto_screen_upcoming_opportunities(max_results=10)
    elapsed = round(time.time() - start_t, 2)
    print(f"\n{'='*70}")
    print(f"抽出結果: {len(results)} 銘柄 ({elapsed}秒)")
    print(f"{'='*70}")
    for r in results:
        print(f"[{r['strategy_badge']}] [{r['rank']}] [{r['ticker']}] {r['name']} (スコア: {r['score']})")
        print(f"   アクション: {r['trade_action']}")
        print(f"   現値: {r['current_price']}円 -> 目標: {r['target_price']}円 (+{r['expected_return_pct']}%) | 損切り: {r['stop_loss']}円 (RR: {r['risk_reward_ratio']})")
        print(f"   決算予定: {r['earnings_date']} (あと{r['days_until_earnings']}日) | 形状: {r['technical_pattern']}")
        print(f"   戦略別スコア: A(前モメンタム):{r['strategy_scores']['A']} | B(またぎ):{r['strategy_scores']['B']} | C(後PEAD):{r['strategy_scores']['C']}")
        print(f"   根拠: {' / '.join(r['reasons'])}")
        print("-" * 70)
