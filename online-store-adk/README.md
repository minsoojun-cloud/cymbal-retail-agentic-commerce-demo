# Cymbal Retail オンラインストア ADK 版 (`online-store-adk`)

Vertex AI Search for Commerce（Retail API）、Gemini「AI による概要」、および ADK AI コンシェルジュ（テキスト＋音声会話対応）を統合した総合オンラインスーパーのデモストアフロント（FastAPI BFF + 静的 SPA + 商品画像 4,131 枚）です。

## 主な機能

- **パーソナライズドホーム**: 顧客ペルソナ（`CR-0001` さくらさん）と購買履歴に基づき、「おすすめ」「よく購入する商品」「今週の特価」「旬のおすすめ」「新登場雑貨」「人気ランキング」を表示（アレルギー食材・業務用サイズを自動除外）
- **AI Commerce Search 連携**: ファセット絞り込み、タイルナビゲーション、会話型検索（`:conversationalSearch`）、オートコンプリート（ローカルフォールバック対応）
- **Gemini「AI による概要」**: 検索結果上位の商品特徴・価格帯・おすすめ理由・絞り込み質問をリアルタイム生成（`POST /api/ai-summary`）
- **AI コンシェルジュ（ADK）**: スライドオーバー型チャットから夕食セット提案、比較表表示、カート追加、配送枠選択、注文確定、配送状況トラッキングまでを一貫操作（`POST /api/agent/stream` → `adk-agent`）
- **音声対話（STT / TTS）**: `VOICE_ENABLED=1`（既定）で Cloud Speech-to-Text v2（Chirp 2/3 + Gemini フォールバック）と Cloud Text-to-Speech（`ja-JP-Chirp3-HD-Aoede`）によるマイク入力・ハンズフリー注文・音声読み上げを提供
- **クロスリンクとブランドカスタマイズ**: `ENRICH_URL` や `STORE_APP_URL` 設定時にヘッダーアイコンを表示。`BRAND_NAME` 設定時は `/config.js` 経由でタイトル・ヘッダーロゴ・フッター表記に自動反映

## ディレクトリ構成

| パス | 役割 |
|---|---|
| `app/main.py` | FastAPI エントリポイント、`/config.js`、検索・推薦・音声・エージェントプロキシ API |
| `app/search.py` | Retail API v2alpha 検索クライアント＋オフライン `LocalSearch` エンジン |
| `app/catalog.py` | カタログ正規化・インメモリキャッシュ・かな変換・オートコンプリート候補検索 |
| `app/recommend.py` | ペルソナ＋購買履歴ベースのホーム推薦エンジン |
| `app/ai.py` | Gemini による「AI による概要」生成・英語フォローアップ質問の日本語翻訳 |
| `app/agent_proxy.py` | 内部公開 Cloud Run `adk-agent` への Google ID トークン付き SSE プロキシ |
| `app/voice.py` | Cloud Speech-to-Text v2 / Gemini STT および Cloud TTS 音声合成 |
| `static/` | SPA フロントエンド（HTML / CSS / JS）および商品画像 `static/img/products/`（4,131 枚） |
| `tests/` | バックエンド単体テスト（`test_*.py`）および Playwright E2E スクリプト（`e2e_*.py`） |
| `deploy.sh` | カタログ・ペルソナをステージングして Cloud Run へデプロイするスクリプト |

## 環境変数

| 変数名 | 既定値 | 説明 |
|---|---|---|
| `PROJECT_ID` | （必須） | Google Cloud プロジェクト ID |
| `PROJECT_NUMBER` | 自動取得 | Google Cloud プロジェクト番号 |
| `REGION` | `asia-northeast1` | Cloud Run デプロイ先リージョン |
| `ONLINE_STORE_SERVICE` | `${SERVICE_PREFIX}-site-adk` | Cloud Run サービス名 |
| `AGENT_BACKEND` | `adk` | エージェントバックエンド（既定 `adk`） |
| `ADK_AGENT_URL` | `shared/adk_agent/DEPLOYMENT.env` から解決 | ADK エージェントの URL |
| `ENRICH_URL` | 空（設定時にヘッダーリンク表示） | 商品データエンリッチメント・スタジオの URL |
| `STORE_APP_URL` | 空（設定時にヘッダーリンク表示） | 店舗ナビ（お客様アプリ）の URL |
| `GEMINI_MODEL` | `gemini-3.8-flash` | 「AI による概要」等で使用する Gemini モデル |
| `VOICE_ENABLED` | `1` | チャット音声入出力の有効化（`0` で無効） |
| `BRAND_NAME` | `Cymbal Retail` | ストアブランド表示名 |

## デプロイとローカル開発

### Cloud Run へのデプロイ

```bash
source install/config.env
./online-store-adk/deploy.sh
```

> [!NOTE]
> デプロイ完了時に `allUsers`（公開アクセス）付与を試みますが、組織ポリシーで制限されている環境でもエラー終了せず警告を表示して正常完了します。

### ローカル起動（オフライン検索モード）

```bash
cd online-store-adk
DATA_FILE=../seed/catalog/products_retail.jsonl AI_MOCK=1 VOICE_ENABLED=1 \
  uv run --no-project --with-requirements requirements.txt uvicorn app.main:app --port 8080
```

### テスト実行

```bash
# 単体テスト（ネットワーク不要）
cd online-store-adk
uv run --no-project --with-requirements requirements.txt --with-requirements requirements-dev.txt \
  pytest -q tests/test_*.py

# デプロイ済み環境に対する Playwright E2E テスト
python3 tests/e2e_site_adk.py --base-url "$ONLINE_STORE_URL" --enrich-url "$ENRICH_URL" --id-token
```
