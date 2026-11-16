# Cymbal Retail チラシ作成スタジオ (`flyer-studio`)

日本の地域密着型スーパーマーケット「Cymbal Retail」向けの AI 折込・デジタルチラシ作成スタジオです。BigQuery の商品カタログとチラシ拡張メタデータ（`flyer_product_ext` / `flyer_offers` / `flyer_price_reference` / `flyers`）および Cloud Storage バケット（`${PROJECT_ID}-flyers`）と連携し、テンプレート選択、Gemini によるキャッチコピー・献立提案・背景画像生成、承認ワークフロー、高解像度 PDF / JPEG 書き出しを提供します。

## 主な機能

- **テンプレート & レイアウト編集**: 基本テンプレート（T1〜T4）およびカスタムテンプレート保存、ゾーン背景・スロット単位の形状／価格表示カスタマイズ。
- **AI 自動構成 & 代替提案**: Gemini によるテーマ・ターゲット層に合わせた商品ピックアップ、キャッチコピー生成、献立提案。
- **チラシ特別価格（`flyer_offers`）**: チラシ期間・枠ごとの特売価格設定と税込参考価格の自動計算。
- **承認・アーカイブ**: 販促担当による確認依頼、店舗責任者による承認・差し戻し、承認済みチラシの凍結スナップショット保管。
- **印刷・デジタル書き出し**: Headless Chromium / Poppler / ImageMagick による PDF・JPEG（150 / 300 dpi）出力。

## ディレクトリ構成

- `app/`: FastAPI アプリケーション本体（`main.py`, `composer.py`, `bg_gen.py`, `render.py`, `repository.py`, `archive.py`, `picker.py`, `cutout.py`, `qa_validator.py`, `templates.py`）
- `static/`: 日本語 SPA フロントエンド（HTML / CSS / JS）および背景プリセット画像
- `data/`: ローカルフォールバック用拡張メタデータ（`flyer_product_ext.json`）
- `scripts/setup_bq.py`: BigQuery チラシ拡張テーブル作成・初期データ投入スクリプト
- `tests/`: Pytest テストスイート
- `deploy.sh`: Cloud Run（`cymbal-flyer-studio`）デプロイスクリプト

## ローカルテスト

```bash
cd flyer-studio
pytest -q
```

`tests/test_flyer_studio.py` は `FLYER_DATA_MODE=local` / `FLYER_AI_MODE=fallback` で動作し、`seed/catalog/products_retail.jsonl` を参照してオフラインで全 API・HTML/PDF レンダリングを検証します。

## Cloud Run デプロイ

`install/config.env`（または環境変数 `PROJECT_ID` 等）を参照し、カタログ JSONL と商品画像をステージングしてデプロイします。

```bash
cd flyer-studio
./deploy.sh
```

主な環境変数:

- `PROJECT_ID`: デプロイ先 Google Cloud プロジェクト ID
- `REGION`: Cloud Run / BigQuery リージョン（既定値: `asia-northeast1`）
- `BQ_DATASET`: BigQuery データセット名（既定値: `cymbal`）
- `FLYERS_BUCKET`: チラシ背景・アーカイブ保存用 GCS バケット名（既定値: `${PROJECT_ID}-flyers`）
- `GEMINI_MODEL`: チラシ構成生成用 Gemini モデル（既定値: `gemini-3.8-flash`）
- `GEMINI_LOCATION`: Vertex AI ロケーション（既定値: `global`）
- `STORE_URL` / `ONLINE_STORE_URL`: オンラインストア（`cymbal-site-adk`）の URL（QR コード・クロスリンク用）
- `ENRICH_URL`: 商品情報エンリッチメント スタジオ（`cymbal-data-enrichment`）の URL
