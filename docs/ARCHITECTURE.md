# アーキテクチャ設計書 (`docs/ARCHITECTURE.md`)

本書では、Cymbal Retail エージェンティック・コマース デモの全体構成、Cloud Run サービス間の認証境界、データフロー、および環境変数仕様について解説します。

---

## 1. サービス構成とセキュリティ境界

本デモは単一の Google Cloud プロジェクト上に **8 つの Cloud Run サービス**（公開 Web 6 サービス + IAM 保護された内部 API 2 サービス）を展開します。すべてのサービスは最小権限の専用サービスアカウント（既定: `cymbal-runtime@<PROJECT_ID>.iam.gserviceaccount.com`）で稼働します。

```mermaid
flowchart TB
  subgraph Browser["クライアント（ブラウザ）"]
    B1["EC サイト利用者"]
    B2["来店客スマホ"]
    B3["店舗スタッフ端末"]
    B4["商品管理・MD 担当"]
  end

  subgraph PublicRun["Cloud Run — ユーザー向け Web / BFF 層"]
    OS["cymbal-site-adk<br/>(FastAPI + SPA)<br/>min=1, max=5"]
    CA["cymbal-store-app<br/>(APP_MODE=customer)<br/>min=1, max=3, session-affinity"]
    SA["cymbal-store-staff<br/>(APP_MODE=staff)<br/>min=1, max=3, session-affinity"]
    EN["cymbal-data-enrichment<br/>(FastAPI + SPA)<br/>min=0, max=1"]
  end

  subgraph PrivateRun["Cloud Run — 内部エージェント・ツール層 (--no-allow-unauthenticated)"]
    AG["cymbal-adk-agent<br/>(Google ADK LlmAgent)<br/>min=1, max=1"]
    MCP["cymbal-commerce-mcp<br/>(FastMCP Streamable HTTP)<br/>min=1, max=5"]
  end

  subgraph Managed["Google Cloud マネージドサービス"]
    RET["Vertex AI Search for Commerce<br/>(default_catalog / default_search)"]
    GEM["Vertex AI Gemini API<br/>(location=global)"]
    BQ1[("BigQuery: cymbal<br/>商品・顧客・購買履歴・店舗・棚割")]
    BQ2[("BigQuery: cymbal_enrichment<br/>属性抽出・品質ゲート・GMC・コスト")]
    GCS1[("GCS: <PROJECT_ID>-store-navi<br/>スタッフ登録棚写真")]
    GCS2[("GCS: products_images_<PROJECT_ID><br/>AI生成シーン画像・帳票原本")]
    SPEECH["Cloud Speech-to-Text v2<br/>& Cloud Text-to-Speech"]
  end

  B1 --> OS
  B2 --> CA
  B3 --> SA
  B4 --> EN

  OS -->|"OIDC ID トークン<br/>POST /api/chat/stream (SSE)"| AG
  AG -->|"OIDC ID トークン<br/>POST /mcp"| MCP
  CA -->|"組み込み ADK → OIDC ID トークン<br/>POST /mcp"| MCP

  OS & CA & SA & MCP --> RET
  OS & CA & SA & EN & AG --> GEM
  MCP & CA & SA --> BQ1
  EN --> BQ1 & BQ2
  SA & CA --> GCS1
  EN --> GCS2
  OS --> SPEECH
```

---

## 2. 主要ユースケースのシーケンス

### 2.1 オンラインストア：AIコンシェルジュによる夕食セット提案〜注文確定

オンラインストア (`cymbal-site-adk`) のチャット欄は、ブラウザと BFF 間で Server-Sent Events (SSE) ストリームを維持し、ツール実行による UI 操作アクション（`show_products_on_page`, `add_to_cart`, `start_checkout`, `select_delivery_slot`, `place_order`）をリアルタイムに画面へ反映します。

```mermaid
sequenceDiagram
  autonumber
  actor User as お客様 (CR-0001)
  participant Site as cymbal-site-adk (BFF)
  participant Agent as cymbal-adk-agent (ADK)
  participant MCP as cymbal-commerce-mcp
  participant BQ as BigQuery (cymbal)
  participant Retail as Vertex AI Search for Commerce
  participant Gemini as Vertex AI Gemini

  User->>Site: 「今夜の夕食をお勧めしてね」(POST /api/agent/stream)
  Site->>Agent: OIDC ID トークン付き中継 (POST /api/chat/stream + page_state)
  Note over Agent,MCP: セッション初回時に顧客プロフィール (えびアレルギー・4人家族) をウォームアップ取得
  Agent->>Gemini: システム指示 + 顧客コンテキスト + ツール定義
  Gemini-->>Agent: functionCall: recommend_dinner_set(request="今夜の夕食...")
  Agent->>MCP: MCP ツール呼び出し: recommend_dinner_set
  MCP->>BQ: 顧客プロフィール・購買履歴参照
  MCP->>Retail: 主菜・副菜・汁物候補を検索（アレルギー原材料「えび」を自動除外）
  MCP-->>Agent: 夕食献立セット案（主菜・副菜・合計税込金額・提案理由）
  Agent-->>Site: SSE event: action (show_products_on_page)
  Site-->>User: 画面上に夕食セットカードを即時描画
  Agent->>Gemini: ツール結果を渡して接客応答文を生成
  Gemini-->>Agent: ストリーミング応答テキスト
  Agent-->>Site: SSE event: text / chips / done
  Site-->>User: チャット応答表示 & 音声読み上げ（任意）
```

### 2.2 店舗ナビ：スタッフによる売場写真登録とお客様マップへの即時反映

`store-navi` は 1 つのコンテナイメージから環境変数 `APP_MODE`（`staff` / `customer`）によって 2 つの専用サービスとして稼働し、BigQuery `cymbal` データセットと GCS バケットを介してリアルタイムに連携します。

```mermaid
sequenceDiagram
  autonumber
  actor Staff as 店舗スタッフ
  participant StaffApp as cymbal-store-staff
  participant Gemini as Gemini Vision (@ global)
  participant GCS as GCS (store-navi)
  participant BQ as BigQuery (cymbal)
  participant CustApp as cymbal-store-app
  actor Cust as 来店客

  Staff->>StaffApp: 売場・値札プレート写真を送信 (POST /api/staff/analyze-photo)
  StaffApp->>Gemini: 画像から棚番号(A01-203等)・段・JAN/商品名を構造化抽出
  Gemini-->>StaffApp: ゴンドラ候補・段・商品候補リスト・信頼度
  Staff->>StaffApp: 確認して棚位置を登録 (POST /api/staff/shelf-locations)
  StaffApp->>GCS: 棚写真を gs://<STORE_NAVI_BUCKET>/shelf_photos/ に保存
  StaffApp->>BQ: shelf_locations テーブルへ追記 (source='staff')
  Cust->>CustApp: 商品を検索してルート案内を実行 (/api/search, /api/route)
  CustApp->>BQ: 最新の shelf_locations / store_layouts を参照
  CustApp-->>Cust: フロアマップ上の正確な棚ピンと最短ルートを表示
```

### 2.3 商品情報エンリッチメント スタジオ：3 段階パイプラインと品質ゲート

1. **ステージ 1（属性抽出・単位正規化）**: 商品タイトル・レガシー説明文・アップロードされた仕様書 PDF / 価格表 Excel / パッケージ画像から、カテゴリ別スキーマに沿った構造化属性と根拠箇所 (`evidence`) を Gemini で抽出。
2. **品質ゲート判定（Gate 1 / Gate 2）**:
   - **Gate 1（ルール検証）**: 必須単位正規化・28 品目アレルゲン整合性・禁止表現チェック。
   - **Gate 2（複合信頼度スコア）**: 根拠一致度 (`evidence_match`) × 自己評価 (`self_conf`) × トークン確信度 (`token_conf`) からスコアを算出し、閾値以上を `auto_approved`（自動承認）、中間を `needs_review`（人間レビュー待ち）、不整合を `rejected`（却下）に自動振り分け。
3. **ステージ 3 & GMC 生成**: 承認属性から検索キーワード・AI 要約（ゴールデンレコード）および Google Merchant Center 会話型コマース用フィード（Q&A・ハイライト・バリアント）を生成。

---

## 3. 決定論的 URL 設計と相互リンク注入

Cloud Run v2 では、各サービスに `https://<SERVICE_NAME>-<PROJECT_NUMBER>.<REGION>.run.app` 形式の決定論的 URL が割り当てられます。インストーラー（`install/lib/common.sh` および `install/steps/70_apps.sh`）は以下の仕組みで循環依存なしに相互リンクを解決します。

1. デプロイ前に `gcloud projects describe` で `PROJECT_NUMBER` を取得し、全 6 サービスの URL を算出。
2. カタログ JSONL 内の商品 URL・画像 URL を `ONLINE_STORE_URL` に書き換えてから BigQuery / Retail API / 各コンテナに配布。
3. 各フロントエンドに相互遷移用環境変数を注入:
   - `cymbal-site-adk`: `ENRICH_URL`（ヘッダーからエンリッチメントスタジオへ遷移）、`ADK_AGENT_URL`
   - `cymbal-store-app`: `ONLINE_STORE_URL`（EC で購入リンク）、`STAFF_URL`（スタッフ画面切替リンク）、`MCP_URL`
   - `cymbal-store-staff`: `ONLINE_STORE_URL`、`CUSTOMER_URL`（お客様画面切替リンク）、`MCP_URL`
   - `cymbal-data-enrichment`: `STORE_URL`（オンラインストアへ戻るリンク）、`PUBLIC_BASE_URL`
4. `70_apps.sh` 完了時に `gcloud run services describe --format='value(status.url)'` で実測 URL を検証し、万一予測 URL と異なる形式が返された場合は `gcloud run services update --update-env-vars` で自動補正します。

---

## 4. 正規環境変数一覧 (`install/config.env` / `common.sh`)

| 環境変数名 | 既定値 / 算出規則 | 用途 |
|---|---|---|
| `PROJECT_ID` | （必須） | デプロイ先 Google Cloud プロジェクト ID |
| `PROJECT_NUMBER` | 自動取得 | 決定論的 Cloud Run URL および Retail リソース名の構築 |
| `REGION` | `asia-northeast1` | Cloud Run / BigQuery / Cloud Storage のリージョン |
| `GEMINI_LOCATION` | `global` | Vertex AI Gemini API のエンドポイントロケーション |
| `SERVICE_PREFIX` | `cymbal` | 全 Cloud Run サービス名・ランタイム SA の接頭辞 |
| `RUNTIME_SA` | `${SERVICE_PREFIX}-runtime@${PROJECT_ID}.iam.gserviceaccount.com` | 全 6 サービス共通の実行サービスアカウント |
| `BQ_DATASET` | `cymbal` | カタログ・顧客・購買履歴・店舗ナビ用 BigQuery データセット |
| `ENRICH_BQ_DATASET` | `cymbal_enrichment` | エンリッチメントスタジオ用 BigQuery データセット |
| `CATALOG_BUCKET` | `${PROJECT_ID}-catalog` | Retail インポート用カタログ JSONL・エラーログ保管バケット |
| `STORE_NAVI_BUCKET` | `${PROJECT_ID}-store-navi` | 店舗ナビの売場棚写真保管バケット |
| `ENRICH_IMAGE_BUCKET` | `products_images_${PROJECT_ID}` | エンリッチメントスタジオの生成画像・帳票サンプル保管バケット |
| `GEMINI_MODEL` | `probe_models.py` で自動検出 | サイト AI 概要・店舗ビジョン等の高速テキストモデル |
| `AGENT_MODEL` | `probe_models.py` で自動検出 | ADK エージェント用の Function Calling 対応最新モデル |
| `ENRICH_GEMINI_MODEL` | `probe_models.py` で自動検出 | エンリッチメント抽出・GMC 生成用 Gemini 3.x モデル |
| `IMAGE_MODEL` | `probe_models.py` で自動検出 | 商品パックショット・季節シーン生成用画像モデル |
| `VOICE_ENABLED` | `1` | オンラインストアの音声入力 (STT) / 音声読み上げ (TTS) 有効化 |
| `BRAND_NAME` | `Cymbal Retail` | ストア・Retail 会話型検索のブランド表示名 |
