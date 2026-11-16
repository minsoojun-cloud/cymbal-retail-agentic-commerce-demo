# Cymbal Retail VMD 機能表・POP自動生成スタジオ (`cymbal-spec-banner`)

Cymbal Retail の店舗展示用ディスプレイバナー（**機能表 / VMD POP**）を商品マスタおよびメーカー入力用 Excel シート（`*機能表入力シート.xlsx`）からリアルタイム生成・編集・高解像度 JPEG / 印刷用 PDF 出力・メール添付配信するフルスタック Web アプリケーションです。

## 主な機能

1. **6 大家電カテゴリ対応の精密バナーテンプレート**
   - **テレビ (`tv`)**: 画面サイズ、パネル方式、リフレッシュレート、倍速機能、ネット動画サービス対応一覧、省エネ性能ラベル、JAN バーコード
   - **パソコン (`pc`)**: ネイビーヘッダー (`#1F4E78`)、CPU バッジ、Copilot+ PC 準拠 & NPU TOPS、SSD / メモリ / Office / バッテリー駆動時間、`Cymbal オリジナルポイント` パネル
   - **ワインセラー (`wine_cellar`)**: 収容本数・冷却方式・温度帯・外形寸法・扉開き方向図
   - **冷温庫 (`cooler_warmer`)**: 保冷・保温温度目安、AC/DC 2電源対応、内容量、外形寸法
   - **冷凍庫 (`freezer`)**: 1ドア / 2ドアレイアウト、3D ドア図、統一省エネラベル、Cymbal オリジナルポイント
   - **冷蔵庫 (`refrigerator`)**: 3D ドアレイアウト図（12パターン）、各室容量、Cymbal 長期保証・Cymbal カード特典、統一省エネラベル
2. **テンプレート・項目配置デザイナー（AI Vision レイアウト解析）**
   - 既存バナー画像やレイアウト画像を Gemini Vision で解析し、枠組み・座標・項目マッピングを自動抽出してカスタムテンプレートを編集可能
3. **Excel 一括取込 & Gemini AI スペック補完**
   - `*機能表入力シート.xlsx` のアップロードによる一括取込
   - Vertex AI Gemini によるメーカー公式仕様の自動補完
4. **高解像度 JPEG / 印刷用 A4 PDF 出力 & GCS / BigQuery 保存**
   - `Cymbal_機能表_<型番>.jpg`（300 DPI）・`Cymbal_機能表_<型番>.pdf` を生成し、Cloud Storage (`gs://${GCS_BUCKET}/banners/`) および BigQuery (`${PROJECT_ID}.${BQ_DATASET}.kinohyo_banners`) に保存

## ローカル実行・テスト

```bash
# バックエンドテスト
uv run --no-project --with fastapi --with uvicorn --with sqlalchemy --with pydantic --with httpx --with pytest --with pillow --with reportlab --with openpyxl --with google-genai --with google-cloud-storage --with psycopg \
  pytest -q

# フロントエンドビルド
cd web
npm install
npm run build
```

## Cloud Run デプロイ

リポジトリルートの `install/config.env` を設定した状態で実行します（SQLite 内蔵シードデータでスタンドアロン動作します）。

```bash
cd spec-banner
chmod +x deploy.sh
./deploy.sh
```
