# 📈 決算トレード予測・検証サイクルシステム (EarningsTrade-Tracker)

東証全上場銘柄の決算スケジュール・リアルタイム株価・業績進捗率を自動解析し、**3大決算トレード戦略（決算前プレ・決算またぎ・決算後モメンタム）** に基づく銘柄抽出、エントリー判断、資金管理、およびトレード結果の自己学習検証を行う統合ダッシュボードシステムです。

---

## 🌟 主な機能

### 1. 東証全銘柄 決算カレンダー自動スキャン
- 日本取引所グループ（JPX）の最新決算発表スケジュールおよび東証全銘柄一覧を自動連携。
- 当日から直近14日以内に決算発表を控える銘柄を高速一括スキャン。

### 2. 3大決算戦略 スクリーニング＆自動スコアリング
- **戦略A（決算前プレトレード / 期待買い狙い）**
  - 決算4〜14日前、業績期待やチャート形状（カップウィズハンドル、ブレイクアウト等）から発表前の期待上げを狙うスイング戦略。
- **戦略B（決算またぎ / サプライズ狙い）**
  - 決算0〜3日前、高進捗率（80%以上）かつ直近上昇・出来高急増銘柄に絞り、決算サプライズ好決算を狙う戦略。
- **戦略C（決算後モメンタム / 好決算飛び乗り）**
  - 決算発表直後、好決算ギャップアップやゴールデンクロス等初動の上昇トレンドに乗る戦略。

### 3. 業績成長・進捗率 ＆ 上方修正確率エンジン (`progress_calculator.py`)
- 四半期ごとの経常利益・営業利益進捗率を自動判定（超高進捗・標準・低進捗）。
- 過去の業績傾向から「上方修正確率（高 / 中 / 低）」および「適正戦略」を自動判定。

### 4. 100万円資金管理ポジションサイザー (`position_sizer.py`)
- ポートフォリオ元本（100万円等）に対するリスク許容度（2%ルール：最大許容損失2万円/銘柄）に基づく最適買付株数を自動計算。
- 損切りライン、利確ターゲット（リスクリワード比 1:2 以上）、期待値（損益比）を自動提示。

### 5. 決算後実績トラッカー ＆ 自己学習分析エンジン
- 決算通過後の株価変動（高値、安値、終値騰落率）を自動追跡し、勝敗を自動判定。
- テクニカル指標・進捗率ごとの勝率・平均リターンを集計し、次回トレードに向けた検証レポートを出力。

### 6. フルレスポンシブ Webダッシュボード
- 外部フレームワーク（ReactやVue等）に依存せず、軽量なHTML5/CSS3/Vanilla JSで構築。
- モバイル・デスクトップ両対応のプレミアムダークモードUI。
- インタラクティブな株価チャート（移動平均線、ボリンジャーバンド、出来高）を搭載。

---

## 🛠 システムアーキテクチャ

```mermaid
flowchart TD
    JPX[JPX 決算スケジュール / 東証一覧] --> Scanner[earnings_scanner.py]
    YF[Yahoo! Finance 市場データ] --> Market[market_data.py]
    
    Scanner --> Screener[auto_screener.py]
    Market --> Screener
    
    subgraph 分析・計算エンジン
        Prog[progress_calculator.py<br>進捗率・上方修正確率] --> Screener
        Pred[predictor.py<br>テクニカルパターン予測] --> Screener
        Sizer[position_sizer.py<br>100万円資金管理・サイジング] --> Screener
    end
    
    Screener --> WebServer[tools/app.py<br>REST API Server]
    DB[(SQLite: earnings_trade.db)] <--> WebServer
    Analyzer[analyzer.py<br>トレード検証・学習] <--> DB
    
    WebServer <--> UI[Webダッシュボード<br>Vanilla HTML / CSS / JS]
```

---

## 🚀 クイックスタート

### 動作要件
- OS: Windows, macOS, Linux
- Python: 3.9 以上
- ブラウザ: Google Chrome, Microsoft Edge, Firefox, Safari 等

### 1. リポジトリのクローン
```bash
git clone https://github.com/susumu53/earnings-trade-tracker.git
cd earnings-trade-tracker
```

### 2. 依存パッケージのインストール
```bash
pip install -r requirements.txt
```

### 3. アプリケーションの起動

#### Windowsの場合（ワンクリック起動）:
`起動_決算トレードダッシュボード.bat` をダブルクリックするだけで、自動的にサーバーが起動しブラウザが開きます。

#### コマンドラインから起動する場合:
```bash
python main.py
```
起動後、ブラウザで [http://localhost:8080](http://localhost:8080) にアクセスしてください。

---

## ☁️ クラウド公開 (Render無料デプロイ)

本リポジトリは [Render](https://render.com) の無料プランに対応しています。GitHubと連携するだけで、インターネット上にWebアプリとして公開できます。

### デプロイ手順（3ステップ）:
1. **[Render](https://dashboard.render.com/) にサインアップ / ログイン**（GitHubアカウントでログイン推奨）
2. **「New +」→「Web Service」をクリック**
   - 連携済みリポジトリ一覧から `earnings-trade-tracker` を選択
3. **設定を入力して「Deploy Web Service」をクリック**
   - **Name**: `earnings-trade-tracker` (任意)
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Instance Type**: `Free` (無料)
4. 数分でビルドが完了し、`https://earnings-trade-tracker-xxxx.onrender.com` の公開URLが発行されます！

---


## 📂 ディレクトリ構成

```
earnings-trade-tracker/
├── main.py                          # 統合メインエントリーポイント
├── requirements.txt                 # 必要Pythonパッケージ定義
├── 起動_決算トレードダッシュボード.bat    # Windows向けワンクリック起動スクリプト
├── tools/
│   ├── app.py                       # 軽量HTTPサーバー & REST API
│   ├── auto_screener.py             # 3大戦略自動スクリーニングエンジン
│   ├── market_data.py               # yfinance連携・テクニカル計算
│   ├── earnings_scanner.py          # JPX決算発表スケジュールスキャナー
│   ├── progress_calculator.py       # 業績進捗率・上方修正確率判定
│   ├── position_sizer.py            # 資金管理・最適ポジションサイズ計算
│   ├── predictor.py                 # 上昇予測・目標株価計算
│   ├── tracker.py                   # 決算後値動き自動追跡・勝敗判定
│   ├── analyzer.py                  # パターン別勝率分析・自己学習レポート
│   ├── db.py                        # SQLiteデータベース管理層
│   └── universe.py                  # 東証全銘柄コード一覧キャッシュ管理
├── web/
│   ├── index.html                   # ダッシュボードUI画面
│   ├── style.css                    # プレミアムダークテーマCSS
│   └── app.js                       # UI制御 & API非同期通信
├── docs/
│   ├── SYSTEM_GUIDE.md              # システム設計・アーキテクチャ詳細解説
│   └── 決算トレード完全マニュアル.md    # 決算トレード実践ガイド
└── data/                            # 実行時生成キャッシュ・DB格納ディレクトリ
```

---

## ⚠️ 免責事項 (Disclaimer)

- 本ソフトウェアは、株式投資に関する情報収集およびトレード検証を支援するためのツールであり、特定の銘柄の売買推奨や投資助言を行うものではありません。
- 株式投資には元本割れを含む市場変動リスクが伴います。最終的な投資決定は、必ずご自身の判断と責任において行ってください。
- 本プログラムの利用によって生じたいかなる損害・損失についても、開発者は一切の責任を負いません。

---

## 📄 ライセンス

本プロジェクトは [MIT License](LICENSE) のもとで公開されています。
