# Vertex AI Search for Commerce 機能リファレンス

対象エンドポイント:
- ベース URL: `https://retail.googleapis.com/v2alpha/projects/${PROJECT_NUMBER}/locations/global/catalogs/default_catalog`
- ヘッダー: `Authorization: Bearer $(gcloud auth print-access-token)`, `X-Goog-User-Project: ${PROJECT_ID}`
- ランタイム SA `${RUNTIME_SA}` には `roles/retail.editor`（または検索用途で `roles/retail.viewer`）を付与します。

機能検証の再実行:
```bash
source install/config.env
python3 shared/catalog/setup_search_features.py --steps probe
```

## 機能別の動作状況

| 機能 | 状態 | 備考 |
|---|---|---|
| 商品検索 `servingConfigs/default_search:search` | 利用可能 | 約 21,130 商品をインポート直後から検索可能 |
| 静的ファセット (`facetSpecs`) | 利用可能 | `categories`, `brands`, `price` 区間、`attributes.top_category` / `on_sale` / `storage_type` / `labels` / `brand_line` / `material` / `color` / `origin` 等に対応 |
| 動的ファセット (`dynamicFacetSpec`) | 設定有効 | `dynamicFacetSpec.mode=ENABLED` を設定済み。検索トラフィック蓄積前は静的 `facetSpecs` を併用 |
| フィルタ (`filter`) | 利用可能 | 例: `attributes.top_category: ANY("キッチン・調理器具") AND price: IN(1000.0, 5000.0)` |
| 会話型検索 RPC (`:conversationalSearch`) | 利用可能 | 日本語でのマルチターン検索クエリ精緻化 (`refinedSearch[].query`) が動作 |
| タイルナビゲーション (`tileNavigationSpec`) | クライアント側補完 | レスポンスが空の場合は `categories` ファセット値からクライアント側でタイルを生成 |
| オートコンプリート (`:completeQuery`) | ローカルフォールバック併用 | 組織ポリシー (`iam.allowedPolicyMemberDomains`) によりシステム SA への BQ 権限付与が制限される環境では `seed/catalog/autocomplete_suggestions.jsonl` に自動フォールバック |

## 検索リクエスト例

`POST {base}/servingConfigs/default_search:search`
```json
{
  "query": "お弁当",
  "visitorId": "v-7f3a9c21",
  "userInfo": {"userId": "CR-0001"},
  "pageSize": 24,
  "offset": 0,
  "languageCode": "ja",
  "filter": "attributes.on_sale: ANY(\"true\")",
  "facetSpecs": [
    {"facetKey": {"key": "categories"}, "limit": 10},
    {"facetKey": {"key": "brands"}, "limit": 10},
    {"facetKey": {"key": "attributes.top_category"}},
    {"facetKey": {"key": "attributes.on_sale"}},
    {"facetKey": {"key": "attributes.storage_type"}},
    {"facetKey": {"key": "price", "intervals": [
      {"maximum": 300},
      {"minimum": 300, "maximum": 1000},
      {"minimum": 1000, "maximum": 3000},
      {"minimum": 3000}
    ]}}
  ],
  "dynamicFacetSpec": {"mode": "ENABLED"},
  "spellCorrectionSpec": {"mode": "AUTO"},
  "queryExpansionSpec": {"condition": "AUTO", "pinUnexpandedResults": true}
}
```

> [!IMPORTANT]
> `:search` の `results[]` には `id` のみが返却されるため、商品名・価格・画像などは `seed/catalog/products_retail.jsonl` または BigQuery `${BQ_DATASET}.products` から `id` キーでハイドレートします。
