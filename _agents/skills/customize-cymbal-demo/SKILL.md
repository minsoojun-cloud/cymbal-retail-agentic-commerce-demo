---
name: customize-cymbal-demo
description: インストール済みの Cymbal Retail デモを顧客要件に合わせてカスタマイズ（ブランド名・配色・ロゴ変更、商品追加と著作権フリー画像生成、ペルソナ・購買履歴変更、店舗マップ・棚割変更、AIエージェント指示文・モデル変更）し、必要なステップのみ高速に再デプロイする手順。
---

# Cymbal Retail デモ カスタマイズスキル (`customize-cymbal-demo`)

提案先のお客様（小売・スーパー・ドラッグストア・EC 事業者など）に合わせてデモを改装する際は、変更対象に応じたレシピを実行し、`./install/install.sh --steps ...` で必要な部分だけを再デプロイしてください。

---

## カスタマイズ早見表（変更箇所 → 再実行ステップ）

| 変更したい内容 | 主な編集対象ファイル | 反映に必要なコマンド |
|---|---|---|
| 1. ブランド名・ロゴ・テーマカラー | `install/config.env` (`BRAND_NAME`), 各アプリの `logo.svg` / CSS トークン | `./install/install.sh --steps 70_apps,90_verify` |
| 2. 商品の追加・価格変更 + AI 商品画像生成 | `shared/catalog/blueprint/*.json` → `generate_catalog.py` → `gen_vertex.py` | `./install/install.sh --steps 40_data,50_catalog_import,60_backend,70_apps,90_verify` |
| 3. 顧客ペルソナ・家族構成・アレルギー・購買履歴 | `seed/personas/personas.json`, `generate_history.py`, `load_to_bq.sh` | `./install/install.sh --steps 60_backend,70_apps,90_verify` |
| 4. 店舗情報・フロアマップ・棚番・在庫 | `store-navi/scripts/store_layout_defs.py`, `build_store_data.py` | `store-navi` データ再構築後 `./install/install.sh --steps 70_apps,90_verify` |
| 5. AIコンシェルジュの接客方針・プロンプト | `shared/adk_agent/cymbal_agent/agent.py`, `store-navi/app/agent/` | `./install/install.sh --steps 60_backend,70_apps,90_verify` |
| 6. 使用する Gemini モデル・音声機能の切替 | `install/config.env` (`GEMINI_MODEL`, `AGENT_MODEL`, `VOICE_ENABLED` 等) | `./install/install.sh --steps 60_backend,70_apps,90_verify` |

---

## レシピ 1: お客様ブランド（ロゴ・カラー・表示名）への変更

1. **設定ファイルの更新**: `install/config.env` の `BRAND_NAME="〇〇マート"` を更新します。
2. **オンラインストア (`online-store-adk`)**:
   - ロゴ画像: `online-store-adk/static/img/logo.svg` および `favicon.svg` を差し替えます。
   - 配色・CSS 変数: `online-store-adk/static/css/theme.css` 先頭の `:root` カラー変数（プライマリカラー等）と `online-store-adk/static/index.html` のタイトル・ヘッダー表記を編集します。
3. **店舗ナビ (`store-navi`)**:
   - 共通デザイントークン: `store-navi/static/shared/css/` 内の CSS 変数と `store-navi/static/shared/img/` のロゴを編集します。
4. **商品情報エンリッチメント (`data-enrichment`)**:
   - `data-enrichment/static/index.html` および `data-enrichment/static/css/` のヘッダータイトル・アクセントカラーを編集します。
5. **Retail 会話型検索表示名とアプリの再デプロイ**:
   ```bash
   ./install/install.sh --steps 30_retail,70_apps,90_verify
   ```

---

## レシピ 2: 商品の追加・差し替えと Gemini 著作権セーフ画像生成

実在メーカーのロゴや著作物を含まない安全な商品パックショット画像を Gemini 画像生成モデルで自動作成し、カタログに組み込みます。

1. **ブループリントの編集・追加**:
   `shared/catalog/blueprint/` に新しい JSON（例: `custom_client_items.json`）を追加するか既存ファイルを編集します。
   - 既存商品のセール・評価乱数を維持したい場合は、ソート順が後ろになるファイル名にするか既存ファイル末尾にアイテムを追加します。
   - 各アイテムには `base_id`、`category_path`、`images`（例: `["custom_item_01_p.jpg"]`）、`image_brief`（英語または日本語の撮影指示）、`variants`（商品名・税抜価格・サイズ）を定義します。
2. **Gemini による商品パックショット生成 + 自動品質検査 (QA)**:
   ```bash
   source install/lib/common.sh && load_config
   # 未生成の商品画像を Gemini (IMAGE_MODEL) で白背景・文字なし生成し、Gemini 視覚 QA で自動検品
   GEN_MODEL="${IMAGE_MODEL}" QA_MODEL="${GEMINI_MODEL}" \
     uv run --no-project --with google-genai --with pillow \
     python3 shared/catalog/gen_vertex.py --blueprints shared/catalog/blueprint/custom_client_items.json
   # 600x600 JPEG として online-store-adk/static/img/products/ に反映
   uv run --no-project --with pillow python3 shared/catalog/apply_packshots.py
   ```
   > **ポイント**: `gen_vertex.py` は「純白背景・文字やブランドロゴ一切なし・人物なし」をプロンプトと視覚 QA の二重チェックで保証するため、デモで安心して使用できます。
3. **カタログ JSONL の再生成と検証**:
   ```bash
   python3 shared/catalog/generate_catalog.py \
     --out seed/catalog/products_retail.jsonl \
     --base-url "${ONLINE_STORE_URL}"
   python3 shared/catalog/validate_jsonl.py seed/catalog/products_retail.jsonl
   ```
4. **BigQuery・Retail API・全アプリへの反映**:
   ```bash
   ./install/install.sh --steps 40_data,50_catalog_import,60_backend,70_apps,90_verify
   ```

---

## レシピ 3: ペルソナ（家族構成・アレルギー・嗜好）・購買履歴の変更

1. **オンラインストアのペルソナ編集**:
   `seed/personas/personas.json` を編集します（例: `CR-0001` の家族構成 `household`、アレルギー除外語 `exclude_keywords`、好物 `family_preferences`）。
2. **購買履歴の再生成と BigQuery 反映**:
   ```bash
   source install/lib/common.sh && load_config
   python3 seed/personas/generate_history.py \
     --products seed/catalog/products_retail.jsonl \
     --out seed/personas/purchase_history.jsonl
   bash seed/personas/load_to_bq.sh
   ```
3. **店舗ナビ側の来店ペルソナ (`CR-0002`, `CR-0003`) を変更する場合**:
   `store-navi/data/store_personas.json` および `store_purchase_history.jsonl` を編集し、`python3 store-navi/scripts/setup_bq.py --skip-iam` で BigQuery に反映します。
4. **MCP サーバー・オンラインストアの再デプロイ**:
   ```bash
   ./install/install.sh --steps 60_backend,70_apps,90_verify
   ```

---

## レシピ 4: 店舗レイアウト・棚割・店内在庫のカスタマイズ

1. **店舗定義・フロアマップの編集**:
   - 店舗基本情報（住所・緯度経度・営業時間・調剤窓口）: `store-navi/data/stores.json`
   - ゴンドラ配置・通路・棚スロット定義: `store-navi/scripts/store_layout_defs.py` および `store-navi/scripts/build_store_data.py`
2. **店舗データ JSONL の再ビルドと BigQuery 反映**:
   ```bash
   source install/lib/common.sh && load_config
   python3 store-navi/scripts/build_store_data.py
   python3 store-navi/scripts/setup_bq.py --skip-iam --reset-shelf
   ```
   ※ デプロイ済みのスタッフアプリ画面（`/admin` の「棚番管理」画面）から GUI でリアルタイムにゴンドラ・棚番を編集して公開することも可能です。
3. **店舗ナビの再デプロイ**:
   ```bash
   ./install/install.sh --steps 70_apps,90_verify
   ```

---

## レシピ 5: AI エージェントのシステム指示文・使用モデルの変更

1. **システムプロンプト（接客トーン・提案ルール）の変更**:
   - オンラインストア AIコンシェルジュ: `shared/adk_agent/cymbal_agent/agent.py` の `BASE_INSTRUCTION`（`<role>`, `<allergy>`, `<dinner_set>`, `<search>`, `<checkout>` セクション）を編集します。
   - 店舗ナビ 店内コンシェルジュ: `store-navi/app/agent/` 配下の指示文・ツール定義を編集します。
2. **Gemini モデルの変更**:
   `install/config.env` で `GEMINI_MODEL`、`AGENT_MODEL`、`ENRICH_GEMINI_MODEL`、`IMAGE_MODEL` を指定します（空欄に戻して `./install/install.sh --steps 15_models` を実行すると、再びプロジェクトで利用可能な最新モデルを自動検出します）。
3. **バックエンド・フロントエンドの再デプロイ**:
   ```bash
   ./install/install.sh --steps 60_backend,70_apps,90_verify
   ```
