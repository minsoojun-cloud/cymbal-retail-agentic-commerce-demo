# Cymbal Commerce MCP サーバー (`shared/mcp_server`)

Vertex AI Search for Commerce（Retail API）および BigQuery（顧客プロフィール・購買履歴・商品マスタ）をバックエンドに持つ FastMCP（Streamable HTTP / JSON-RPC）サーバーです。`adk-agent` および `store-navi` から ID トークン認証経由で呼び出されます。

## 提供ツール (`/mcp`)

| ツール名 | 概要 |
|---|---|
| `search_products` | Retail API `servingConfigs/default_search` による商品検索（在庫あり限定・最大 100 件・「N円以下」フィルタ自動変換） |
| `get_product_details` | 商品 ID 指定での詳細情報取得（説明文・属性・画像・評価スコア） |
| `compare_products` | 複数商品の属性比較テーブル生成（価格・内容量・ラベル・産地/素材など） |
| `get_customer_profile` | BigQuery `${BQ_DATASET}.customers` から顧客プロフィールを取得（未接続時は `data/personas.json` にフォールバック） |
| `get_purchase_history` | BigQuery `${BQ_DATASET}.purchase_history` から購買履歴・頻出商品を集計（未接続時は `data/purchase_history.jsonl` にフォールバック） |
| `recommend_dinner_set` | 家族構成・好み・アレルギー除外・購買頻度・セール・旬情報をもとに夕食セット（主菜・副菜・汁物・主食・デザート）を最大 3 案構成 |

## 環境変数

| 変数名 | 既定値 | 説明 |
|---|---|---|
| `PROJECT_ID` | （必須） | Google Cloud プロジェクト ID |
| `REGION` | `asia-northeast1` | Cloud Run / BigQuery リージョン |
| `BQ_DATASET` | `cymbal` | BigQuery データセット名 |
| `MCP_SERVICE` | `${SERVICE_PREFIX}-commerce-mcp` | Cloud Run サービス名 |
| `RUNTIME_SA` | `${SERVICE_PREFIX}-runtime@${PROJECT_ID}.iam.gserviceaccount.com` | 実行サービスアカウント |
| `PERSONAS_DIR` | `../../seed/personas` | デプロイ時にバンドルするペルソナデータの参照元 |

## デプロイ・動作確認

### Cloud Run へのデプロイ

```bash
source install/config.env
./shared/mcp_server/deploy.sh
```

デプロイ完了後、`shared/mcp_server/DEPLOYMENT.env` に `MCP_URL` が出力されます。

### スモークテスト（リモート）

```bash
source shared/mcp_server/DEPLOYMENT.env
python3 shared/mcp_server/testing.py --url "$MCP_URL" --auth
```

### ユニットテスト（ローカル・ネットワーク不要）

```bash
cd shared/mcp_server
uv run --no-project --with-requirements requirements.txt --with pytest --with httpx pytest -q tests
```
