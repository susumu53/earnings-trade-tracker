#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ポジションサイジング計算機

100万円→500万円を目指す決算トレードにおいて、
リスク管理に基づいた最適なポジションサイズを算出するツール。

使い方:
  python position_sizer.py --demo          # デモ実行
  python position_sizer.py --interactive   # 対話モード
  python position_sizer.py --simulate      # シーズンシミュレーション
"""

import argparse
import random
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TradeSetup:
    """トレードセットアップ"""
    stock_code: str
    stock_name: str
    strategy: str  # A, B, C
    entry_price: float
    stop_loss_price: float
    target_price_1: float
    target_price_2: Optional[float] = None
    leverage: float = 1.0


@dataclass
class PositionResult:
    """ポジション計算結果"""
    max_loss_amount: float
    position_size: float
    shares: int
    actual_risk: float
    risk_reward_ratio: float
    leverage_position: float


def calculate_position(
    total_capital: float,
    risk_per_trade_pct: float,
    entry_price: float,
    stop_loss_price: float,
    target_price: float,
    leverage: float = 1.0,
    unit_shares: int = 100
) -> PositionResult:
    """
    ポジションサイズを計算する

    Args:
        total_capital: 総資金（円）
        risk_per_trade_pct: 1トレードあたりの最大リスク（%）
        entry_price: エントリー価格
        stop_loss_price: 損切り価格
        target_price: 利確目標価格
        leverage: レバレッジ倍率
        unit_shares: 単元株数（通常100株）

    Returns:
        PositionResult: 計算結果
    """
    # 1. 最大損失額
    max_loss = total_capital * (risk_per_trade_pct / 100)

    # 2. 損切り幅（1株あたり）
    stop_loss_width = abs(entry_price - stop_loss_price)
    if stop_loss_width == 0:
        stop_loss_width = entry_price * 0.05  # デフォルト5%

    # 3. 最大株数
    max_shares = max_loss / stop_loss_width
    # 単元株に丸める
    max_shares_rounded = int(max_shares // unit_shares) * unit_shares
    if max_shares_rounded == 0:
        max_shares_rounded = unit_shares

    # 4. ポジションサイズ
    position_size = max_shares_rounded * entry_price

    # 5. レバレッジ適用時の実質ポジション
    leverage_position = position_size  # レバレッジは必要証拠金を下げるが、リスクは同じ

    # 6. 実際のリスク
    actual_risk = max_shares_rounded * stop_loss_width

    # 7. リスクリワード比
    target_width = abs(target_price - entry_price)
    risk_reward = target_width / stop_loss_width if stop_loss_width > 0 else 0

    return PositionResult(
        max_loss_amount=max_loss,
        position_size=position_size,
        shares=max_shares_rounded,
        actual_risk=actual_risk,
        risk_reward_ratio=risk_reward,
        leverage_position=leverage_position
    )


def print_position_result(
    setup: TradeSetup,
    result: PositionResult,
    total_capital: float,
    risk_pct: float
):
    """ポジション計算結果を表示"""
    stop_loss_pct = abs(setup.entry_price - setup.stop_loss_price) / setup.entry_price * 100
    target_pct = abs(setup.target_price_1 - setup.entry_price) / setup.entry_price * 100

    strategy_names = {
        "A": "決算前モメンタム",
        "B": "決算またぎ",
        "C": "決算後ドリフト（PEAD）"
    }

    print(f"\n{'='*60}")
    print(f"📊 ポジションサイズ計算結果")
    print(f"{'='*60}")
    print(f"  銘柄: {setup.stock_code} {setup.stock_name}")
    print(f"  戦略: {setup.strategy} ({strategy_names.get(setup.strategy, '不明')})")
    print(f"  レバレッジ: {setup.leverage}倍")
    print(f"{'─'*60}")
    print(f"  【資金情報】")
    print(f"    総資金:         {total_capital:>12,.0f}円")
    print(f"    最大リスク:     {risk_pct}%（{result.max_loss_amount:,.0f}円）")
    print(f"{'─'*60}")
    print(f"  【価格設定】")
    print(f"    エントリー価格: {setup.entry_price:>12,.0f}円")
    print(f"    損切り価格:     {setup.stop_loss_price:>12,.0f}円（{stop_loss_pct:-.1f}%）")
    print(f"    利確目標1:      {setup.target_price_1:>12,.0f}円（+{target_pct:.1f}%）")
    if setup.target_price_2:
        target_pct_2 = abs(setup.target_price_2 - setup.entry_price) / setup.entry_price * 100
        print(f"    利確目標2:      {setup.target_price_2:>12,.0f}円（+{target_pct_2:.1f}%）")
    print(f"{'─'*60}")
    print(f"  【計算結果】")
    print(f"    購入株数:       {result.shares:>12,}株")
    print(f"    ポジションサイズ: {result.position_size:>10,.0f}円")
    print(f"    資金比率:       {result.position_size/total_capital*100:>11.1f}%")
    print(f"    実際のリスク額:  {result.actual_risk:>11,.0f}円")
    print(f"    リスクリワード比: {result.risk_reward_ratio:>10.2f}")
    print(f"{'─'*60}")

    # リスクリワード評価
    rr = result.risk_reward_ratio
    if rr >= 3.0:
        print(f"  📈 評価: ★★★★★ 非常に良い（RR={rr:.2f}）")
    elif rr >= 2.0:
        print(f"  📈 評価: ★★★★ 良い（RR={rr:.2f}）")
    elif rr >= 1.5:
        print(f"  📈 評価: ★★★ 普通（RR={rr:.2f}）")
    elif rr >= 1.0:
        print(f"  ⚠️ 評価: ★★ やや低い（RR={rr:.2f}）")
    else:
        print(f"  🔴 評価: ★ リスクが高い（RR={rr:.2f}）→ 見送り推奨")

    # ポジション比率の警告
    ratio = result.position_size / total_capital * 100
    if ratio > 30:
        print(f"  ⚠️ 警告: ポジション比率が{ratio:.1f}%で30%を超えています")
    if result.actual_risk > total_capital * 0.03:
        print(f"  ⚠️ 警告: 実際のリスク額が総資金の3%を超えています")

    print(f"{'='*60}")


def simulate_season(
    initial_capital: float,
    strategy_mix: str = "balanced",
    num_simulations: int = 1000
):
    """
    決算シーズンのシミュレーションを実行

    Args:
        initial_capital: 初期資金
        strategy_mix: 戦略ミックス（balanced/aggressive/conservative）
        num_simulations: シミュレーション回数
    """
    print(f"\n{'='*60}")
    print(f"🎲 決算シーズン・シミュレーション")
    print(f"{'='*60}")
    print(f"  初期資金: {initial_capital:,.0f}円")
    print(f"  戦略ミックス: {strategy_mix}")
    print(f"  シミュレーション回数: {num_simulations:,}")
    print(f"{'─'*60}")

    # 戦略パラメータ
    strategies = {
        "A": {
            "name": "決算前モメンタム",
            "win_rate": 0.55,
            "avg_win": 0.15,
            "avg_loss": -0.05,
            "trades_per_season": 5,
            "leverage": 2.0,
        },
        "B": {
            "name": "決算またぎ",
            "win_rate": 0.40,
            "avg_win": 0.25,
            "avg_loss": -0.10,
            "trades_per_season": 3,
            "leverage": 2.0,
        },
        "C": {
            "name": "PEAD",
            "win_rate": 0.55,
            "avg_win": 0.20,
            "avg_loss": -0.07,
            "trades_per_season": 4,
            "leverage": 2.0,
        },
    }

    # 戦略ミックス設定
    if strategy_mix == "aggressive":
        weight = {"A": 0.30, "B": 0.40, "C": 0.30}
    elif strategy_mix == "conservative":
        weight = {"A": 0.40, "B": 0.10, "C": 0.50}
    else:  # balanced
        weight = {"A": 0.35, "B": 0.25, "C": 0.40}

    final_capitals = []
    ruin_count = 0  # 元本の50%以上を失ったケース

    for _ in range(num_simulations):
        capital = initial_capital

        for strategy_key, w in weight.items():
            s = strategies[strategy_key]
            allocated = capital * w
            trades = s["trades_per_season"]

            for _ in range(trades):
                if capital <= initial_capital * 0.5:  # ドローダウンリミット
                    break

                # 1トレードあたりの配分
                trade_size = allocated / trades
                # リスク管理: 1トレードの最大リスクは総資金の2%
                max_risk = capital * 0.02

                # 勝敗判定
                if random.random() < s["win_rate"]:
                    # 勝ち
                    pnl = trade_size * s["avg_win"] * s["leverage"]
                else:
                    # 負け
                    pnl = trade_size * s["avg_loss"] * s["leverage"]
                    # 損切りで最大リスクを制限
                    pnl = max(pnl, -max_risk)

                capital += pnl

        if capital <= initial_capital * 0.5:
            ruin_count += 1

        final_capitals.append(capital)

    # 結果の統計
    final_capitals.sort()
    avg_capital = sum(final_capitals) / len(final_capitals)
    median_capital = final_capitals[len(final_capitals) // 2]
    min_capital = final_capitals[0]
    max_capital = final_capitals[-1]
    pct_10 = final_capitals[int(len(final_capitals) * 0.10)]
    pct_25 = final_capitals[int(len(final_capitals) * 0.25)]
    pct_75 = final_capitals[int(len(final_capitals) * 0.75)]
    pct_90 = final_capitals[int(len(final_capitals) * 0.90)]

    target = initial_capital * 5  # 5倍
    reach_target = sum(1 for c in final_capitals if c >= target)
    double_count = sum(1 for c in final_capitals if c >= initial_capital * 2)
    profit_count = sum(1 for c in final_capitals if c > initial_capital)

    print(f"\n  📊 シミュレーション結果（{num_simulations:,}回）")
    print(f"{'─'*60}")
    print(f"  平均最終資金:     {avg_capital:>12,.0f}円（{(avg_capital/initial_capital-1)*100:+.1f}%）")
    print(f"  中央値:           {median_capital:>12,.0f}円（{(median_capital/initial_capital-1)*100:+.1f}%）")
    print(f"  最小:             {min_capital:>12,.0f}円")
    print(f"  最大:             {max_capital:>12,.0f}円")
    print(f"{'─'*60}")
    print(f"  10パーセンタイル: {pct_10:>12,.0f}円")
    print(f"  25パーセンタイル: {pct_25:>12,.0f}円")
    print(f"  75パーセンタイル: {pct_75:>12,.0f}円")
    print(f"  90パーセンタイル: {pct_90:>12,.0f}円")
    print(f"{'─'*60}")
    print(f"  利益が出る確率:    {profit_count/num_simulations*100:>10.1f}%")
    print(f"  2倍達成率:         {double_count/num_simulations*100:>10.1f}%")
    print(f"  5倍達成率:         {reach_target/num_simulations*100:>10.1f}%")
    print(f"  破産リスク（-50%超）: {ruin_count/num_simulations*100:>7.1f}%")
    print(f"{'='*60}")

    # 複数シーズンのシミュレーション
    print(f"\n  📈 複数シーズン累積シミュレーション")
    print(f"{'─'*60}")

    for seasons in [2, 3, 4]:
        multi_finals = []
        for _ in range(num_simulations):
            capital = initial_capital
            for _ in range(seasons):
                if capital <= initial_capital * 0.3:
                    break
                season_return = random.choice(final_capitals) / initial_capital
                capital = capital * season_return
            multi_finals.append(capital)

        multi_reach = sum(1 for c in multi_finals if c >= target)
        multi_avg = sum(multi_finals) / len(multi_finals)
        multi_median = sorted(multi_finals)[len(multi_finals) // 2]

        print(f"  {seasons}シーズン後:")
        print(f"    平均: {multi_avg:,.0f}円 / 中央値: {multi_median:,.0f}円")
        print(f"    5倍達成率: {multi_reach/num_simulations*100:.1f}%")

    print(f"{'='*60}")


def run_demo():
    """デモ実行"""
    print("\n🎮 デモモード: サンプルデータでポジション計算\n")

    capital = 1_000_000  # 100万円
    risk_pct = 2.0  # 2%ルール

    setups = [
        TradeSetup("1234", "テスト銘柄A", "A", 1500, 1425, 1725, 1800, 2.0),
        TradeSetup("5678", "テスト銘柄B", "B", 3200, 2880, 4000, 4200, 2.0),
        TradeSetup("9012", "テスト銘柄C", "C", 800, 744, 960, 1040, 2.0),
    ]

    for setup in setups:
        result = calculate_position(
            total_capital=capital,
            risk_per_trade_pct=risk_pct,
            entry_price=setup.entry_price,
            stop_loss_price=setup.stop_loss_price,
            target_price=setup.target_price_1,
            leverage=setup.leverage
        )
        print_position_result(setup, result, capital, risk_pct)

    # シーズンシミュレーション
    print("\n\n" + "🎲" * 30)
    simulate_season(capital, "balanced", 10000)
    simulate_season(capital, "aggressive", 10000)
    simulate_season(capital, "conservative", 10000)


def run_interactive():
    """対話モード"""
    print("\n💰 ポジションサイジング計算機（対話モード）")
    print("=" * 60)

    try:
        capital = float(input("総資金（円）: "))
        risk_pct = float(input("1トレードあたりの最大リスク（%、推奨2%）: ") or "2")
    except ValueError:
        print("入力エラー")
        return

    while True:
        print(f"\n--- 新規トレード計算 ---")
        try:
            code = input("銘柄コード（終了: q）: ").strip()
            if code.lower() == 'q':
                break

            name = input("銘柄名: ").strip()
            strategy = input("戦略（A/B/C）: ").strip().upper()
            entry = float(input("エントリー価格: "))
            stop = float(input("損切り価格: "))
            target1 = float(input("利確目標1: "))
            target2_input = input("利確目標2（なければEnter）: ").strip()
            target2 = float(target2_input) if target2_input else None
            leverage = float(input("レバレッジ（1〜3.3）: ") or "1")

            setup = TradeSetup(code, name, strategy, entry, stop, target1, target2, leverage)
            result = calculate_position(capital, risk_pct, entry, stop, target1, leverage)
            print_position_result(setup, result, capital, risk_pct)

        except ValueError as e:
            print(f"⚠️ 入力エラー: {e}")
            continue
        except KeyboardInterrupt:
            break

    print("\n💰 計算終了。お疲れ様でした！")


def main():
    parser = argparse.ArgumentParser(
        description="決算トレード用 ポジションサイジング計算機"
    )
    parser.add_argument("--demo", "-d", action="store_true", help="デモ実行")
    parser.add_argument("--interactive", "-i", action="store_true", help="対話モード")
    parser.add_argument("--simulate", "-s", action="store_true", help="シーズンシミュレーション")
    parser.add_argument("--capital", type=float, default=1_000_000, help="初期資金（デフォルト100万円）")
    parser.add_argument("--mix", choices=["balanced", "aggressive", "conservative"],
                        default="balanced", help="戦略ミックス")
    args = parser.parse_args()

    if args.demo:
        run_demo()
    elif args.interactive:
        run_interactive()
    elif args.simulate:
        simulate_season(args.capital, args.mix, 10000)
    else:
        print("オプションを指定してください:")
        print("  --demo (-d)        : デモ実行")
        print("  --interactive (-i) : 対話モード")
        print("  --simulate (-s)    : シーズンシミュレーション")
        print("\nデモモードで実行します...\n")
        run_demo()


if __name__ == "__main__":
    main()
