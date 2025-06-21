# 競馬分析システム (Keiba Analysis System)

netkeiba.comから競馬データを収集し、PostgreSQLに保存して、YAML設定による柔軟な分析を実行する包括的な競馬データ分析システムです。

## 📋 目次

- [機能概要](#機能概要)
- [技術スタック](#技術スタック)
- [プロジェクト構成](#プロジェクト構成)
- [環境構築](#環境構築)
- [使用方法](#使用方法)
- [設定ファイル](#設定ファイル)
- [データベース設計](#データベース設計)
- [開発ログ](#開発ログ)

## 🎯 機能概要

### 1. データ収集機能
- netkeiba.comからの競馬データ自動収集
- 指定期間のレース情報とレース結果の一括取得
- レースメタデータ（距離、コース種別、天候、馬場状態）の自動抽出
- 重複データ検出と排除

### 2. データ管理機能
- PostgreSQL データベースへの構造化データ保存
- SQLAlchemy ORM を使用した型安全なデータ操作
- 自動的なデータベーステーブル作成
- トランザクション管理による安全なデータ更新

### 3. 分析エンジン機能
- YAML設定ファイルによる柔軟な分析条件指定
- 複数条件による動的データ抽出
- 競馬統計量の自動計算（勝率、複勝率、回収率など）
- 分析結果のCSV出力

### 4. 統計計算機能
- 総レース数・総出走頭数の集計
- 勝率（1着率）・複勝率（3着内率）の計算
- 単勝・複勝回収率の精密計算
- 分析結果の日本語フォーマット表示

## 🛠 技術スタック

### バックエンド
- **Python 3.x**: メインプログラミング言語
- **SQLAlchemy**: ORM（Object-Relational Mapping）
- **PostgreSQL 14**: データベース管理システム
- **Docker**: コンテナ化環境

### データ処理
- **pandas**: データ分析・処理
- **requests**: HTTP通信
- **BeautifulSoup4**: HTMLパースィング
- **lxml**: XML/HTML解析

### 設定・ユーティリティ
- **PyYAML**: YAML設定ファイル処理
- **python-dotenv**: 環境変数管理
- **tqdm**: プログレスバー表示

## 📁 プロジェクト構成

```
keiba_resource/
├── README.md                    # このファイル
├── CLAUDE.md                    # 開発ログ・指示書
├── docker-compose.yml          # PostgreSQL環境構築
├── requirements.txt             # Python依存関係
├── .env                        # 環境変数設定（要作成）
├── src/                        # メインソースコード
│   ├── models.py               # データベースモデル定義
│   ├── db_utils.py             # データベースユーティリティ
│   ├── build_database.py       # データ収集スクレイピングツール
│   └── run_analysis.py         # 分析エンジン
├── analysis_definitions/        # 分析設定ファイル
│   └── sample_analysis.yml     # 分析設定サンプル  
└── results/                    # 分析結果出力先（自動作成）
    └── *.csv                   # 分析結果CSVファイル
```

## 🚀 環境構築

### 1. 前提条件
- Python 3.8 以上
- Docker & Docker Compose
- Git

### 2. プロジェクトのクローン
```bash
git clone https://github.com/Be114/keiba_resource.git
cd keiba_resource
```

### 3. Python環境の構築
```bash
# 仮想環境の作成（推奨）
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 依存関係のインストール
pip install -r requirements.txt
```

### 4. 環境変数設定
`.env`ファイルを作成し、データベース接続情報を設定：

```env
# データベース接続設定
DB_USER=user
DB_PASSWORD=password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=keiba_data
```

### 5. PostgreSQL環境の起動
```bash
docker-compose up -d
```

データベースの動作確認：
```bash
docker-compose ps
```

## 📊 使用方法

### 1. データ収集（スクレイピング）

指定期間の競馬データを netkeiba.com から収集：

```bash
# 2023年のデータを収集
python -m src.build_database --start-year 2023 --end-year 2023

# 複数年のデータを収集
python -m src.build_database --start-year 2022 --end-year 2023
```

**注意**: データ収集には時間がかかります。サイトへの負荷を考慮し、リクエスト間隔を設けています。

### 2. データ分析

YAML設定ファイルを使用した分析実行：

```bash
# サンプル設定での分析
python -m src.run_analysis analysis_definitions/sample_analysis.yml

# カスタム設定での分析
python -m src.run_analysis path/to/your_analysis.yml
```

### 3. 分析結果の確認

分析結果は以下の形式で出力されます：

**コンソール出力例**:
```
============================================================
競馬分析結果
============================================================
分析名: サンプル競馬分析 - 距離別勝率分析
総レース数: 1,234 レース
総出走頭数: 18,510 頭
勝率: 8.33%
複勝率（3着内率）: 25.00%
単勝回収率: 78.45%
複勝回収率: 82.17%
分析実行日時: 2025-06-21 10:30:45
============================================================
```

**CSV出力**: `results/` ディレクトリに分析結果が保存されます。

## ⚙️ 設定ファイル

### YAML設定ファイルの構造

```yaml
# 分析名（必須）
analysis_name: "競馬分析 - 距離別勝率分析"

# 分析条件（必須）
conditions:
  # 対象期間
  date_range:
    start: "2023-01-01"
    end: "2023-12-31"
  
  # 対象競馬場
  race_tracks:
    - "東京"
    - "中山"
    - "京都"
    - "阪神"
  
  # 距離範囲
  distance_range:
    min: 1200
    max: 3200
  
  # コース種別
  course_types:
    - "芝"
    - "ダート"
  
  # 天候条件
  weather_conditions:
    - "晴"
    - "曇"
    - "雨"
  
  # 馬場状態
  track_conditions:
    - "良"
    - "稍重"
    - "重"
    - "不良"

# 出力設定（必須）
output:
  # 結果の保存先
  save_path: "results/analysis_results.csv"
  
  # 出力形式
  format: "csv"
  
  # 詳細ログ出力
  verbose: true
```

### 設定可能な条件

| 条件 | 説明 | 例 |
|------|------|-----|
| `date_range` | 分析対象期間 | `start: "2023-01-01"`, `end: "2023-12-31"` |
| `race_tracks` | 対象競馬場 | `["東京", "中山", "京都", "阪神"]` |
| `distance_range` | 距離範囲 | `min: 1200`, `max: 3200` |
| `course_types` | コース種別 | `["芝", "ダート", "障害"]` |
| `weather_conditions` | 天候条件 | `["晴", "曇", "雨"]` |
| `track_conditions` | 馬場状態 | `["良", "稍重", "重", "不良"]` |

## 🗄️ データベース設計

### Raceテーブル（レース情報）
| カラム | 型 | 説明 |
|--------|-----|------|
| `id` | String(12) | レースID（主キー） |
| `date` | Date | 開催日 |
| `course` | String(50) | コース名 |
| `race_number` | Integer | レース番号 |
| `distance` | Integer | 距離（メートル） |
| `track_type` | String(20) | コース種別 |
| `weather` | String(20) | 天候 |
| `track_condition` | String(20) | 馬場状態 |

### Resultテーブル（レース結果）
| カラム | 型 | 説明 |
|--------|-----|------|
| `id` | Integer | 結果ID（主キー） |
| `race_id` | String(12) | レースID（外部キー） |
| `horse_name` | String(100) | 馬名 |
| `rank` | Integer | 着順 |
| `pre_race_rank` | Integer | 予想順位 |
| `jockey_name` | String(50) | 騎手名 |
| `odds` | Float | オッズ（単勝） |
| `weight` | Float | 負担重量 |

### リレーションシップ
- Race : Result = 1 : 多（1つのレースに複数の結果）
- 外部キー制約による整合性確保
- カスケード削除対応

## 🔧 開発・メンテナンス

### データベース操作

```bash
# データベース接続テスト
python -c "from src.db_utils import get_db_manager; print(get_db_manager().test_connection())"

# テーブル作成
python -c "from src.db_utils import init_database; init_database()"
```

### ログ確認

```bash
# PostgreSQLログ確認
docker-compose logs db

# コンテナ状態確認
docker-compose ps
```

### トラブルシューティング

**データベース接続エラー**:
1. `.env`ファイルの設定確認
2. PostgreSQLコンテナの起動確認
3. ポート競合の確認

**スクレイピングエラー**:
1. ネットワーク接続確認
2. リクエスト間隔の調整
3. netkeiba.comのサイト構造変更の確認

## 📈 開発ログ

プロジェクトの詳細な開発経緯は [`CLAUDE.md`](CLAUDE.md) を参照してください。

- **Session 1-2**: プロジェクト基盤とデータベースモデル構築
- **Session 3-4**: データ収集ツールとスクレイピング機能実装
- **Session 5**: メタデータ取得機能の強化
- **Session 6-7**: 分析エンジンとYAMLクエリ機能実装
- **Session 8**: 統計計算とCSV出力機能実装
- **Session 9**: 最終動作確認とプロジェクト完了

## 📝 ライセンス

本プロジェクトは教育・研究目的で開発されています。
netkeiba.comのデータ使用については、同サイトの利用規約を遵守してください。

## 🤝 貢献

バグ報告や機能要望は、GitHubのIssuesでお知らせください。

---

**開発者**: Be114  
**最終更新**: 2025-06-21  
**バージョン**: 1.0.0