---
name: install-cymbal-demo
description: Cymbal Retail エージェンティック・コマース デモ一式（バックエンド2サービス・フロント4アプリ・BigQuery/GCS/Retail API データ）をユーザー指定の Google Cloud プロジェクトに安全にインストールし、スモークテストで検証する手順。
---

# Cymbal Retail デモ インストールスキル (`install-cymbal-demo`)

ユーザーが「このリポジトリを自分のプロジェクトにデプロイしたい」「デモ環境をインストールして」と依頼した際は、以下の手順を順番に実行してください。

---

## ステップ 1: デプロイ先パラメータの確認

実行前に以下の項目を確認します（未指定の場合は必ずユーザーに質問してください）:

1. **`PROJECT_ID`（必須）**: デプロイ先の Google Cloud プロジェクト ID（課金が有効であること）
2. **`REGION`（任意）**: 既定は `asia-northeast1`（東京）
3. **`SERVICE_PREFIX`（任意）**: 既定は `cymbal`（同一プロジェクトに別名で共存させたい場合のみ変更）

---

## ステップ 2: `install/config.env` の作成と事前チェック (`00_preflight`)

1. `install/config.example.env` をもとに `install/config.env` を作成し、`PROJECT_ID` と `REGION` を設定します。
   ```bash
   cp install/config.example.env install/config.env
   ```
   `install/config.env` の `PROJECT_ID="<ユーザー指定のID>"` を編集します（モデル欄は空欄のままにすると最新モデルが自動選択されます）。

2. 事前チェックとドライランを実行し、CLI (`gcloud`, `bq`, `python3`)・認証状態・課金有効化 (`billingEnabled=True`)・予定 URL を確認します。
   ```bash
   ./install/install.sh --dry-run
   ./install/install.sh --steps 00_preflight
   ```
   - 認証切れの場合はユーザーに `gcloud auth login` の実行を案内してください。
   - 課金が無効な場合は Cloud Console で請求先アカウントをリンクするよう案内し、中断してください。

---

## ステップ 3: 基盤構築・データ投入・アプリケーションデプロイの実行

`install/install.sh` を実行します（全体所要時間: 初回 約 12〜20 分）。途中で失敗した場合でも `--resume` または `--from <step>` で安全に再開できます。

```bash
./install/install.sh --resume
```

内部では以下のステップが順番に実行されます:

| 順序 | ステップ名 | 内容 |
|---|---|---|
| 1 | `00_preflight` | CLI・認証・プロジェクト・課金状態の確認 |
| 2 | `10_apis` | Retail / Vertex AI / Cloud Run / Cloud Build / BigQuery / GCS / Speech / TTS / IAM API の有効化 |
| 3 | `15_models` | `probe_models.py` による最新利用可能 Gemini モデルの自動検出 (`install/.state/models.env`) |
| 4 | `20_iam` | `${SERVICE_PREFIX}-runtime` サービスアカウント作成と最小権限 IAM ロール付与 |
| 5 | `30_retail` | Retail API 利用規約同意・Search 有効化・`default_search` 動的ファセット・候補設定 |
| 6 | `40_data` | GCS 3 バケット・BigQuery 2 データセット作成、URL/バケット置換付きシードデータ一括ロード |
| 7 | `50_catalog_import` | 商品カタログ 21,534 件の Retail API FULL インポート + カスタム属性設定 + 検索候補登録 |
| 8 | `60_backend` | `cymbal-commerce-mcp` → `cymbal-adk-agent` の非公開デプロイと内部 `run.invoker` 付与 |
| 9 | `70_apps` | 6 つのフロントエンドアプリを並列デプロイし、実測 URL に基づき相互リンク環境変数を同期 |
| 10 | `80_public` | 匿名公開アクセスの確認と、組織ポリシー制限時の Cloud Console 手順案内 |
| 11 | `90_verify` | `tests/smoke_install.py` による全サービス・検索・推薦・ADK 会話・相互リンクの自動検証 |

---

## ステップ 4: 組織ポリシーによる公開制限時の対応（重要ガードレール）

Argolis や企業組織配下の GCP プロジェクトでは、組織ポリシー `iam.allowedPolicyMemberDomains` により CLI からの `allUsers` 付与が拒否される場合があります。

- **絶対に行わないこと**: 組織ポリシーの変更・無効化、`--no-invoker-iam-check` の使用、認証バイパス。
- **正しい対応**:
  1. `80_public` および `90_verify` は公開設定がブロックされていてもエラー終了せず、自動で ID トークン認証に切り替えて動作確認を完了させます。
  2. ユーザーに対して、ブラウザから認証なしで開きたい場合は **Google Cloud Console → Cloud Run → 対象サービス（下記6件） → 「セキュリティ」タブ → 「パブリック アクセスを許可（未認証の呼び出しを許可）」** を選択して保存するよう案内してください:
     - `${SERVICE_PREFIX}-site-adk`（ADK オンラインストア）
     - `${SERVICE_PREFIX}-store-app`（店舗ナビ お客様向け）
     - `${SERVICE_PREFIX}-store-staff`（店舗ナビ スタッフ向け）
     - `${SERVICE_PREFIX}-data-enrichment`（商品情報エンリッチメント スタジオ）
     - `${SERVICE_PREFIX}-flyer-studio`（チラシ作成スタジオ）
     - `${SERVICE_PREFIX}-spec-banner`（機能表・POP自動生成スタジオ）
  3. コンソール設定前でも手元のブラウザで今すぐ確認したい場合は、`gcloud run services proxy <サービス名> --project=<PROJECT_ID> --region=<REGION> --port=8080` を案内してください。

---

## ステップ 5: 完了検証とユーザーへの最終レポート

1. スモークテスト単体を再実行する場合は以下のコマンドを使用します:
   ```bash
   python3 tests/smoke_install.py --config install/config.env
   ```
2. 全チェック項目が `PASS` であることを確認し、以下の情報を日本語の表形式でユーザーに報告してください:
   - デプロイされた 6 つのフロントエンド URL と 2 つの内部バックエンド URL
   - 自動選択された Gemini モデル（`GEMINI_MODEL`, `AGENT_MODEL`, `ENRICH_GEMINI_MODEL`, `IMAGE_MODEL`）
   - 公開アクセス状態（公開済み / Cloud Console での「パブリック アクセスを許可」案内）
