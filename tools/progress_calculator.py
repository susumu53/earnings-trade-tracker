#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
進捗率計算・分析ツール

決算データから進捗率を計算し、過去の平均進捗率と比較して
上方修正の可能性が高い銘柄を特定するためのツール。

使い方:
  python progress_calculator.py --interactive   # 対話モード
  python progress_calculator.py --demo          # デモデータで実行
"""

import argparse
import csv
import json
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class QuarterlyData:
    """四半期決算データ"""
    year: int
    quarter: int  # 1=1Q, 2=2Q, 3=3Q, 4=4Q(通期)
    revenue: float  # 売上高（累計）
    operating_profit: float  # 営業利益（累計）
    ordinary_profit: float  # 経常利益（累計）
    net_income: float  # 純利益（累計）
    full_year_forecast_op: float  # 通期会社予想（営業利益）
    full_year_forecast_revenue: float  # 通期会社予想（売上高）
    eps: Optional[float] = None  # EPS
    dividend: Optional[float] = None  # 配当
    consensus_op: Optional[float] = None  # コンセンサス予想（営業利益）


@dataclass
class StockAnalysis:
    """銘柄分析結果"""
    code: str
    name: str
    sector: str
    current_data: QuarterlyData
    historical_progress: list = field(default_factory=list)  # 過去の同四半期の進捗率リスト

    @property
    def current_progress_revenue(self) -> float:
        """売上高進捗率"""
        if self.current_data.full_year_forecast_revenue == 0:
            return 0.0
        return (self.current_data.revenue / self.current_data.full_year_forecast_revenue) * 100

    @property
    def current_progress_op(self) -> float:
        """営業利益進捗率"""
        if self.current_data.full_year_forecast_op == 0:
            return 0.0
        return (self.current_data.operating_profit / self.current_data.full_year_forecast_op) * 100

    @property
    def avg_historical_progress(self) -> float:
        """過去5年平均進捗率"""
        if not self.historical_progress:
            return self._standard_progress()
        return sum(self.historical_progress) / len(self.historical_progress)

    @property
    def progress_deviation(self) -> float:
        """進捗率の乖離（現在 - 過去平均）"""
        return self.current_progress_op - self.avg_historical_progress

    @property
    def surprise_vs_consensus(self) -> Optional[float]:
        """コンセンサスとの乖離率"""
        if self.current_data.consensus_op is None or self.current_data.consensus_op == 0:
            return None
        return ((self.current_data.operating_profit - self.current_data.consensus_op)
                / abs(self.current_data.consensus_op)) * 100

    @property
    def revision_probability(self) -> str:
        """上方修正の可能性判定"""
        dev = self.progress_deviation
        if dev >= 10:
            return "★★★★★ 非常に高い（80%以上）"
        elif dev >= 5:
            return "★★★★ 高い（50-70%）"
        elif dev >= 2:
            return "★★★ やや高い（30-50%）"
        elif dev >= 0:
            return "★★ 普通（10-30%）"
        else:
            return "★ 低い（下方修正リスクあり）"

    def _standard_progress(self) -> float:
        """標準進捗率（過去データがない場合のデフォルト）"""
        q = self.current_data.quarter
        return {1: 25.0, 2: 50.0, 3: 75.0, 4: 100.0}.get(q, 25.0)


def calculate_position_size(total_capital: float, risk_pct: float, stop_loss_pct: float) -> dict:
    """
    ポジションサイズを計算する

    Args:
        total_capital: 総資金（円）
        risk_pct: 1トレードあたりの最大リスク（%）
        stop_loss_pct: 損切り幅（%）

    Returns:
        dict: ポジションサイズ情報
    """
    max_loss = total_capital * (risk_pct / 100)
    position_size = max_loss / (stop_loss_pct / 100)

    return {
        "total_capital": total_capital,
        "risk_pct": risk_pct,
        "stop_loss_pct": stop_loss_pct,
        "max_loss_per_trade": max_loss,
        "max_position_size": position_size,
        "position_ratio": (position_size / total_capital) * 100
    }


def analyze_stock(analysis: StockAnalysis) -> dict:
    """銘柄の総合分析を実施"""
    quarter_names = {1: "1Q", 2: "2Q（中間）", 3: "3Q", 4: "本決算"}
    standard_progress = {1: 25.0, 2: 50.0, 3: 75.0, 4: 100.0}

    result = {
        "銘柄コード": analysis.code,
        "銘柄名": analysis.name,
        "セクター": analysis.sector,
        "決算区分": quarter_names.get(analysis.current_data.quarter, "不明"),
        "売上高進捗率": f"{analysis.current_progress_revenue:.1f}%",
        "営業利益進捗率": f"{analysis.current_progress_op:.1f}%",
        "標準進捗率": f"{standard_progress.get(analysis.current_data.quarter, 25.0):.1f}%",
        "過去5年平均進捗率": f"{analysis.avg_historical_progress:.1f}%",
        "進捗率乖離": f"{analysis.progress_deviation:+.1f}pt",
        "上方修正可能性": analysis.revision_probability,
    }

    # コンセンサスとの乖離
    surprise = analysis.surprise_vs_consensus
    if surprise is not None:
        result["コンセンサス乖離率"] = f"{surprise:+.1f}%"
        if surprise >= 30:
            result["サプライズ判定"] = "⚡ 超ポジティブサプライズ"
        elif surprise >= 15:
            result["サプライズ判定"] = "✅ ポジティブサプライズ"
        elif surprise >= 5:
            result["サプライズ判定"] = "📊 やや上振れ"
        elif surprise >= -5:
            result["サプライズ判定"] = "➡️ ほぼ予想通り"
        elif surprise >= -15:
            result["サプライズ判定"] = "⚠️ やや下振れ"
        else:
            result["サプライズ判定"] = "🔴 ネガティブサプライズ"

    # 戦略判定
    strategies = []
    dev = analysis.progress_deviation

    if dev >= 5 and analysis.current_progress_op > standard_progress.get(analysis.current_data.quarter, 25.0):
        strategies.append("戦略A: 決算前モメンタム ✅")

    if dev >= 10 and (surprise is None or surprise >= 0):
        strategies.append("戦略B: 決算またぎ候補 ✅（要追加条件確認）")

    if surprise is not None and surprise >= 15:
        strategies.append("戦略C: PEAD候補 ✅")

    result["適用可能戦略"] = strategies if strategies else ["該当なし"]

    return result


def print_analysis(result: dict):
    """分析結果を見やすく表示"""
    print("\n" + "=" * 60)
    print(f"📊 銘柄分析レポート")
    print("=" * 60)

    for key, value in result.items():
        if key == "適用可能戦略":
            print(f"\n🎯 {key}:")
            if isinstance(value, list):
                for strategy in value:
                    print(f"    • {strategy}")
            else:
                print(f"    • {value}")
        else:
            print(f"  {key}: {value}")

    print("=" * 60)


def run_demo():
    """デモデータで実行"""
    print("\n🎮 デモモード: サンプルデータで分析を実行します\n")

    # デモデータ: 3銘柄
    demo_stocks = [
        StockAnalysis(
            code="6758",
            name="ソニーグループ（仮想データ）",
            sector="電気機器",
            current_data=QuarterlyData(
                year=2026, quarter=2,
                revenue=5800000, operating_profit=680000,
                ordinary_profit=720000, net_income=550000,
                full_year_forecast_op=1100000,
                full_year_forecast_revenue=11000000,
                consensus_op=620000
            ),
            historical_progress=[48.5, 51.2, 49.8, 50.5, 47.3]
        ),
        StockAnalysis(
            code="4755",
            name="楽天グループ（仮想データ）",
            sector="サービス",
            current_data=QuarterlyData(
                year=2026, quarter=1,
                revenue=500000, operating_profit=35000,
                ordinary_profit=30000, net_income=20000,
                full_year_forecast_op=100000,
                full_year_forecast_revenue=2000000,
                consensus_op=25000
            ),
            historical_progress=[22.0, 18.5, 20.3, 24.1, 19.8]
        ),
        StockAnalysis(
            code="9999",
            name="高進捗サンプル社（仮想データ）",
            sector="情報通信",
            current_data=QuarterlyData(
                year=2026, quarter=3,
                revenue=8500000, operating_profit=920000,
                ordinary_profit=950000, net_income=680000,
                full_year_forecast_op=1000000,
                full_year_forecast_revenue=10000000,
                consensus_op=800000
            ),
            historical_progress=[72.5, 74.0, 71.8, 73.5, 75.2]
        ),
    ]

    for stock in demo_stocks:
        result = analyze_stock(stock)
        print_analysis(result)

    # ポジションサイズ計算のデモ
    print("\n" + "=" * 60)
    print("💰 ポジションサイズ計算（デモ）")
    print("=" * 60)

    capital = 1000000  # 100万円
    scenarios = [
        {"risk_pct": 2.0, "stop_loss_pct": 5.0, "label": "戦略A（損切り5%）"},
        {"risk_pct": 2.0, "stop_loss_pct": 7.0, "label": "戦略C（損切り7%）"},
        {"risk_pct": 2.0, "stop_loss_pct": 10.0, "label": "戦略B（ギャップダウン想定10%）"},
    ]

    for scenario in scenarios:
        pos = calculate_position_size(capital, scenario["risk_pct"], scenario["stop_loss_pct"])
        print(f"\n  📋 {scenario['label']}")
        print(f"    総資金: {pos['total_capital']:,.0f}円")
        print(f"    最大リスク: {pos['risk_pct']}%（{pos['max_loss_per_trade']:,.0f}円）")
        print(f"    損切り幅: {pos['stop_loss_pct']}%")
        print(f"    最大ポジションサイズ: {pos['max_position_size']:,.0f}円")
        print(f"    資金比率: {pos['position_ratio']:.1f}%")

    print("\n" + "=" * 60)


def run_interactive():
    """対話モードで銘柄分析を実行"""
    print("\n📊 進捗率計算・分析ツール（対話モード）")
    print("=" * 60)

    while True:
        print("\n--- 新規銘柄分析 ---")
        try:
            code = input("銘柄コード（終了: q）: ").strip()
            if code.lower() == 'q':
                break

            name = input("銘柄名: ").strip()
            sector = input("セクター: ").strip()
            quarter = int(input("四半期（1=1Q, 2=2Q, 3=3Q, 4=通期）: "))

            print("\n--- 累計実績 ---")
            revenue = float(input("売上高（百万円）: "))
            op = float(input("営業利益（百万円）: "))
            ordinary = float(input("経常利益（百万円）: "))
            net = float(input("純利益（百万円）: "))

            print("\n--- 通期会社予想 ---")
            forecast_op = float(input("通期営業利益予想（百万円）: "))
            forecast_rev = float(input("通期売上高予想（百万円）: "))

            consensus_input = input("コンセンサス営業利益予想（百万円、なければEnter）: ").strip()
            consensus_op = float(consensus_input) if consensus_input else None

            print("\n--- 過去の同四半期進捗率 ---")
            print("過去5年分の同四半期の営業利益進捗率をカンマ区切りで入力")
            print("（例: 48.5,51.2,49.8,50.5,47.3）")
            hist_input = input("過去進捗率（なければEnter）: ").strip()

            if hist_input:
                historical = [float(x.strip()) for x in hist_input.split(",")]
            else:
                historical = []

            # データ構築と分析
            data = QuarterlyData(
                year=2026, quarter=quarter,
                revenue=revenue, operating_profit=op,
                ordinary_profit=ordinary, net_income=net,
                full_year_forecast_op=forecast_op,
                full_year_forecast_revenue=forecast_rev,
                consensus_op=consensus_op
            )

            stock = StockAnalysis(
                code=code, name=name, sector=sector,
                current_data=data,
                historical_progress=historical
            )

            result = analyze_stock(stock)
            print_analysis(result)

        except ValueError as e:
            print(f"⚠️ 入力エラー: {e}")
            continue
        except KeyboardInterrupt:
            print("\n\n終了します。")
            break

    print("\n📊 分析終了。お疲れ様でした！")


def export_analysis_csv(analyses: list, output_path: str):
    """分析結果をCSVにエクスポート"""
    if not analyses:
        print("エクスポートするデータがありません。")
        return

    fieldnames = list(analyses[0].keys())

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in analyses:
            # リスト型の値を文字列に変換
            row_copy = {}
            for k, v in row.items():
                if isinstance(v, list):
                    row_copy[k] = " / ".join(str(item) for item in v)
                else:
                    row_copy[k] = v
            writer.writerow(row_copy)

    print(f"✅ CSVにエクスポートしました: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="決算トレード用 進捗率計算・分析ツール"
    )
    parser.add_argument(
        "--interactive", "-i", action="store_true",
        help="対話モードで実行"
    )
    parser.add_argument(
        "--demo", "-d", action="store_true",
        help="デモデータで実行"
    )
    args = parser.parse_args()

    if args.demo:
        run_demo()
    elif args.interactive:
        run_interactive()
    else:
        # デフォルトはデモモード
        print("オプションを指定してください:")
        print("  --demo (-d)        : デモデータで実行")
        print("  --interactive (-i) : 対話モードで実行")
        print("\nデモモードで実行します...\n")
        run_demo()


if __name__ == "__main__":
    main()
