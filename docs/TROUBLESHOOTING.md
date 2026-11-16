# トラブルシューティング (`docs/TROUBLESHOOTING.md`)

インストール中またはデプロイ後の動作確認で問題が発生した場合は、以下の症状別ガイドを確認してください。修正後は `./install/install.sh --resume` または `./install/install.sh --from <ステップ名>` で途中から安全に再開できます。

---

## 1. 組織ポリシー・認証・公開アクセスに関する問題

### Q1. Cloud Run デプロイ時またはブラウザアクセス時に `403 Forbidden` が出る / `allUsers` 付与が失敗する

- **原因**: Argolis や企業の Google Cloud 組織で、組織ポリシー `constraints/iam.allowedPolicyMemberDomains` により未認証ユーザー (`allUsers`) への `roles/run.invoker` 付与が制限されています。
- **重要方針**: **組織ポリシーの無効化・上書きや `--no-invoker-iam-check` などの回避策は絶対に行わないでください。**
- **対処方法**:
  1. **Cloud Console から正規手順で公開を許可する場合**:
     - Google Cloud Console → **Cloud Run** を開きます。
     - 以下の 4 サービスをそれぞれ選択し、**「セキュリティ」**タブ → 認証で **「パブリック アクセスを許可（未認証の呼び出しを許可）」** を選択して「保存」をクリックします:
       - `cymbal-site-adk`
       - `cymbal-store-app`
       - `cymbal-store-staff`
       - `cymbal-data-enrichment`
     - ※ `cymbal-commerce-mcp` と `cymbal-adk-agent` は内部専用サービスのため、「認証が必要」のままで正常です。
  2. **公開設定を行わずに手元で今すぐデモ・検証を行う場合**:
     - スモークテスト（自動で ID トークン認証を使用）:
       ```bash
       python3 tests/smoke_install.py --config install/config.env --id-token
       ```
     - ローカルブラウザでの閲覧（`gcloud run services proxy` が自動で認証トークンを付与）:
       ```bash
       gcloud run services proxy cymbal-site-adk --project="<PROJECT_ID>" --region="asia-northeast1" --port=8080
       ```
       その後ブラウザで `http://localhost:8080` を開きます（別ポート `8081`, `8082`, `8083` で他 3 アプリも同様に同時起動可能）。

### Q2. `50_catalog_import` で `cloud-retail-customer-data-access@system.gserviceaccount.com` への権限付与が警告になる

- **原因**: Retail API のオートコンプリートインポート (`completionData:import`) は `@system.gserviceaccount.com` ドメインの Google 管理サービスアカウントから BigQuery テーブルを読み取りますが、組織ポリシー `iam.allowedPolicyMemberDomains` が有効な環境ではこのドメインへの IAM 付与が拒否されます。
- **影響と対処**: **対応不要です（機能低下なし）。** オンラインストアと店舗ナビは両方とも、Retail Completion API が未設定の場合に同梱の `seed/catalog/autocomplete_suggestions.jsonl`（7,280 件）を使った高速なインメモリ候補検索へ自動で切り替わります。

---

## 2. Vertex AI / Gemini モデルに関する問題

### Q3. 特定の Gemini モデル（例: `gemini-2.5-flash` や `gemini-3.8-flash`）が `404 NOT_FOUND` になる

- **原因**: Google Cloud プロジェクトの種類や作成時期・許可リストによって、利用可能な Gemini モデル ID が異なります。
- **対処方法**:
  1. `install/config.env` の `GEMINI_MODEL` / `AGENT_MODEL` / `ENRICH_GEMINI_MODEL` / `IMAGE_MODEL` を空欄（`""`）にし、自動検出ステップを再実行してください:
     ```bash
     ./install/install.sh --steps 15_models,60_backend,70_apps
     ```
  2. 検出結果は `cat install/.state/models.env` で確認できます。
  3. リージョンエンドポイントではなく **`GEMINI_LOCATION="global"`** を使用していることを確認してください（最新プレビュー / 3.x モデルは `global` で提供されます）。

### Q4. モデル呼び出し時に `429 RESOURCE_EXHAUSTED` が発生する

- **原因**: `global` エンドポイントの一時的な共有クォータ混雑、または短時間の連続リクエスト集中によるレート制限です。
- **対処方法**:
  - 各アプリ（ADK エージェント、エンリッチメントスタジオ、画像生成ツール）には指数バックオフによる自動リトライが組み込まれています。数秒〜数十秒待ってから再試行してください。
  - エンリッチメントスタジオでは、画面右上のモデルセレクターから別ティアのモデル（例: `gemini-3.5-flash` や `gemini-3.5-flash-lite`）へリクエスト単位で即座に切り替えることができます。

---

## 3. Vertex AI Search for Commerce (Retail API) に関する問題

### Q5. インストール直後にオンラインストアで検索するとヒット件数が 0 件になる

- **原因**: 初回の `50_catalog_import`（21,534 件の FULL インポート）の LRO が `done=true` になった直後でも、Retail API 内部の検索インデックス構築が完了するまで **3〜10 分程度**かかる場合があります。
- **対処方法**:
  1. 5 分ほど待ってから再度検索（例: `お弁当`、`フライパン`、`カレー`）をお試しください。
  2. Serving Config とインポート状態を手動で確認するには以下を実行します:
     ```bash
     python3 tests/smoke_install.py --config install/config.env
     ```
  3. もし `30_retail` を実行する前にインポートしていた場合は、`./install/install.sh --steps 30_retail,50_catalog_import` を再実行してください。

---

## 4. Cloud Build / Cloud Run デプロイに関する問題

### Q6. `60_backend` または `70_apps` の Cloud Run `--source` ビルドが権限エラーで失敗する

- **原因**: 新規作成したばかりのプロジェクトで、Cloud Build またはデフォルト Compute サービスアカウント（`<PROJECT_NUMBER>-compute@developer.gserviceaccount.com`）への `roles/run.builder` / `roles/storage.objectAdmin` 伝播が完了していないケースがあります。
- **対処方法**:
  1. 詳細ログを確認します:
     ```bash
     ls -la install/.state/logs/
     tail -n 80 install/.state/logs/deploy_cymbal-site-adk.log
     ```
  2. IAM ステップを再実行し、1 分待ってからアプリデプロイを再実行します（並列ビルドで Cloud Build 同時実行数上限に達する場合は `--sequential` を付与します）:
     ```bash
     ./install/install.sh --steps 20_iam
     ./install/install.sh --sequential --steps 60_backend,70_apps,90_verify
     ```

### Q7. オンラインストアのチャットで「AIコンシェルジュに接続できません (`502` / `503`)」と表示される

- **原因**:
  1. `cymbal-adk-agent` または `cymbal-commerce-mcp` が未デプロイ、あるいはランタイム SA (`cymbal-runtime@...`) に `roles/run.invoker` が付与されていない。
  2. `cymbal-site-adk` の環境変数 `ADK_AGENT_URL` が空または古い URL を指している。
- **対処方法**:
  ```bash
  ./install/install.sh --steps 60_backend,70_apps,90_verify
  ```
  個別に Cloud Run ログを確認する場合:
  ```bash
  source install/lib/common.sh && load_config
  gcloud run services logs read "${ADK_AGENT_SERVICE}" --project="${PROJECT_ID}" --region="${REGION}" --limit=50
  gcloud run services logs read "${MCP_SERVICE}" --project="${PROJECT_ID}" --region="${REGION}" --limit=50
  ```

---

## 5. 音声機能（マイク入力 / 自動読み上げ）に関する問題

### Q8. オンラインストアでマイクボタンが表示されない、または音声認識/合成がエラーになる

- **確認ポイント**:
  1. `install/config.env` で `VOICE_ENABLED="1"` になっているか（`/config.js` に `"voiceEnabled": true` が含まれているか）。
  2. `speech.googleapis.com`（Cloud Speech-to-Text API）と `texttospeech.googleapis.com`（Cloud Text-to-Speech API）が有効か（`./install/install.sh --steps 10_apis,20_iam`）。
  3. ブラウザでマイク権限が許可されているか（`https://*.run.app` または `http://localhost:*` でのみ Web Audio / MediaRecorder が動作します）。
