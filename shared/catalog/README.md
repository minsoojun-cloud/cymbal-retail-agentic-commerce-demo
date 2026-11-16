# カタログ生成・Retail API インポート (`shared/catalog`)

カテゴリ別ブループリント（`blueprint/*.json`）から約 21,130 件の Retail API スキーマ商品カタログを生成し、Google Cloud Storage・BigQuery・Vertex AI Search for Commerce（Retail API）へ投入するためのツール群です。

## ディレクトリ構成

| ファイル / ディレクトリ | 役割 |
|---|---|
| `blueprint/*.json` | カテゴリ別の商品定義ブループリント（価格・属性・バリエーション・対応料理など） |
| `generate_catalog.py` | ブループリントを展開し `seed/catalog/products_retail.jsonl` を決定論的に生成（`BRAND_NAME` によるブランド名置換に対応） |
| `gen_vertex.py` | Vertex AI 画像生成モデル（`$IMAGE_MODEL`）と Gemini QA モデル（`$GEMINI_MODEL`）による商品パックショット自動生成 |
| `apply_packshots.py` | 生成画像の背景白抜き・600x600 JPEG 化と `online-store-adk/static/img/products/` への配置 |
| `validate_jsonl.py` | 生成された JSONL のスキーマ・必須フィールド検証 |
| `bq_schema.json` | BigQuery `${BQ_DATASET}.products` テーブルスキーマ（Retail API `product` スキーマ準拠） |
| `retail_import.py` | BigQuery から Retail API `default_catalog`（branch 0）への FULL インポート実行と完了ポーリング |
| `set_attributes_config.py` | カスタム属性（`on_sale`, `dishes`, `allergens`, `drug_class` など）のインデックス・検索・ファセット設定 |
| `setup_search_features.py` | `default_search` サービング設定、オートコンプリート候補生成、会話型検索設定、動作プローブ |
| `import_pipeline.sh` | 生成 → 検証 → GCS アップロード → BigQuery ロード → Retail インポート → 属性設定の一括実行スクリプト |
| `SEARCH_FEATURES.md` | Vertex AI Search for Commerce の API 仕様・ファセット・フィルタ構文メモ |

## 主な環境変数

`install/config.env` で一元管理される以下の環境変数を参照します。

| 変数名 | 既定値 | 説明 |
|---|---|---|
| `PROJECT_ID` | （必須） | デプロイ先 Google Cloud プロジェクト ID |
| `PROJECT_NUMBER` | 自動取得 | Google Cloud プロジェクト番号 |
| `REGION` | `asia-northeast1` | BigQuery / Cloud Run リージョン |
| `BQ_DATASET` | `cymbal` | 商品マスタを格納する BigQuery データセット |
| `CATALOG_BUCKET` | `${PROJECT_ID}-catalog` | カタログ JSONL およひインポートエラーログ用 GCS バケット |
| `ONLINE_STORE_URL` | `https://${ONLINE_STORE_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app` | 商品 URI・画像 URI のベース URL |
| `BRAND_NAME` | `Cymbal Retail` | 自社ブランド表示名（変更時は `Cymbal` プレフィックスも連動して置換） |
| `IMAGE_MODEL` | `gemini-3.1-flash-image` | 新規パックショット生成時の画像モデル |
| `GEMINI_MODEL` | `gemini-3.8-flash` | 画像 QA 等に使用するテキスト生成モデル |

## 使い方

### 1. カタログ JSONL の再生成とインポート一括実行

ブループリントや `BRAND_NAME` を変更した後、以下でカタログの再生成から Retail API への反映までを一括実行できます。

```bash
source install/config.env
./shared/catalog/import_pipeline.sh
```

### 2. 新規商品のパックショット画像生成

ブループリントに新しいアイテムを追加した場合、Vertex AI で白背景パックショットを生成して配置できます。

```bash
source install/config.env
cd shared/catalog
GOOGLE_CLOUD_QUOTA_PROJECT="$PROJECT_ID" uv run --no-project --with google-genai --with pillow \
  python gen_vertex.py --blueprints blueprint/z_kitchen.json --workers 6
uv run --no-project --with pillow python apply_packshots.py --glob "z_kitchen.json"
```

### 3. サービング設定とオートコンプリート更新

```bash
source install/config.env
python3 shared/catalog/setup_search_features.py --steps facets,complete,conv
```
