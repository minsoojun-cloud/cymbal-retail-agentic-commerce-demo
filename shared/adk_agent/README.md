# AI コンシェルジュ ADK エージェント (`shared/adk_agent`)

Google Agent Development Kit（ADK）の単一 `LlmAgent` と FastAPI（SSE ストリーミング）で構築されたオンラインストア向け AI コンシェルジュサービスです。`online-store-adk` の BFF プロキシから内部呼び出しされ、商品検索・夕食セット提案・比較表作成・カート追加・配送枠選択・注文確定・配送状況確認までを一貫して処理します。

## ファイル構成

| ファイル | 役割 |
|---|---|
| `cymbal_agent/agent.py` | ADK `LlmAgent` 定義、システムプロンプト、音声モード時の短文化制御、`BRAND_NAME` 反映 |
| `cymbal_agent/tools.py` | MCP バックエンドツール呼び出しおよびページ操作アクション（`show_products_on_page`, `add_to_cart`, `place_order` 等） |
| `cymbal_agent/shop.py` | カート計算・送料（税込 3,000 円以上で無料）・配送枠・注文番号生成の決定論的ロジック |
| `cymbal_agent/mcp_client.py` | Cloud Run 上の `commerce-mcp` を Google ID トークン付きで呼び出す非同期クライアント |
| `server.py` | FastAPI アプリケーション（`POST /api/chat/stream`, `POST /api/chat`, `GET /api/health`） |
| `deploy.sh` | 軽量カタログのステージング、モデルプローブ、Cloud Run 内部公開デプロイ、`DEPLOYMENT.env` 出力 |
| `test_live.py` | 夕食セット提案から注文確定・商品比較まで 7 シナリオのライブ E2E 検証スクリプト |
| `tests/test_shop.py` | カート・送料・配送枠・注文管理ロジックのユニットテスト |

## 環境変数

| 変数名 | 既定値 | 説明 |
|---|---|---|
| `PROJECT_ID` | （必須） | Google Cloud プロジェクト ID |
| `REGION` | `asia-northeast1` | Cloud Run デプロイ先リージョン |
| `GEMINI_LOCATION` | `global` | Vertex AI Gemini エンドポイントロケーション |
| `ADK_AGENT_SERVICE` | `${SERVICE_PREFIX}-adk-agent` | Cloud Run サービス名 |
| `AGENT_MODEL` | `gemini-3.8-flash`（自動フォールバック付） | エージェントが使用する Gemini モデル |
| `MCP_URL` | `shared/mcp_server/DEPLOYMENT.env` から自動解決 | `commerce-mcp` のベース URL |
| `BRAND_NAME` | `Cymbal Retail` | ストアブランド名（システムプロンプトへ反映） |
| `CATALOG_JSONL` | `../../seed/catalog/products_retail.jsonl` | デプロイ時に軽量化して同梱するカタログ JSONL |

## デプロイ・テスト手順

### Cloud Run へのデプロイ

先に `shared/mcp_server/deploy.sh` を実行してからデプロイします。

```bash
source install/config.env
./shared/adk_agent/deploy.sh
```

デプロイ完了後、`shared/adk_agent/DEPLOYMENT.env` に `ADK_AGENT_URL` と `ADK_AGENT_MODEL` が書き出されます。

### ローカル起動

```bash
source install/config.env
cd shared/adk_agent
GOOGLE_GENAI_USE_VERTEXAI=TRUE \
GOOGLE_CLOUD_PROJECT="$PROJECT_ID" \
GOOGLE_CLOUD_LOCATION="${GEMINI_LOCATION:-global}" \
MCP_URL="$MCP_URL" \
CATALOG_FILE="../../seed/catalog/products_retail.jsonl" \
python3 server.py
```

### テスト実行

```bash
# ユニットテスト（ネットワーク不要）
cd shared/adk_agent
uv run --no-project --with pytest pytest -q tests/

# デプロイ済みエージェントに対するライブシナリオ検証
uv run --no-project --with httpx python test_live.py
```
