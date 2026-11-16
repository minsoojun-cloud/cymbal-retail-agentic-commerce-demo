#!/usr/bin/env bash
# ==============================================================================
# 20_iam.sh — ランタイム サービス アカウント作成と最小権限ロール付与
# ==============================================================================
set -euo pipefail
STEP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${STEP_DIR}/../lib/common.sh"
load_config

SA_CREATED=0
if gcloud iam service-accounts describe "${RUNTIME_SA}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  log_info "ランタイム サービス アカウントは既に存在します: ${RUNTIME_SA}"
else
  log_info "ランタイム サービス アカウントを作成しています: ${RUNTIME_SA}"
  gcloud iam service-accounts create "${RUNTIME_SA_NAME}" \
    --project "${PROJECT_ID}" \
    --display-name "Cymbal Retail デモ ランタイム (${SERVICE_PREFIX})"
  SA_CREATED=1
  # 作成直後の IAM 伝播待ち
  sleep 5
fi

RUNTIME_ROLES=(
  roles/retail.editor
  roles/aiplatform.user
  roles/bigquery.dataEditor
  roles/bigquery.jobUser
  roles/storage.objectAdmin
  roles/speech.client
  roles/logging.logWriter
)

log_info "${RUNTIME_SA} に必要な IAM ロールを付与しています..."
for role in "${RUNTIME_ROLES[@]}"; do
  printf "  - %s\n" "${role}"
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member "serviceAccount:${RUNTIME_SA}" \
    --role "${role}" \
    --condition=None \
    --quiet >/dev/null
done

# Cloud Run のソースデプロイ (--source) で使用されるデフォルト Compute サービス アカウントに run.builder を付与
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
log_info "Cloud Run ソースビルド用にデフォルト Compute SA (${COMPUTE_SA}) へ roles/run.builder を確認・付与しています..."
if gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member "serviceAccount:${COMPUTE_SA}" \
    --role "roles/run.builder" \
    --condition=None \
    --quiet >/dev/null 2>&1; then
  log_ok "${COMPUTE_SA} に roles/run.builder を付与しました。"
else
  log_warn "${COMPUTE_SA} への roles/run.builder 付与をスキップしました（Compute Engine デフォルト SA 未作成または別ビルド SA 構成のプロジェクト）。"
fi

if [[ "${SA_CREATED}" -eq 1 ]]; then
  log_info "IAM ポリシーの伝播を待機しています (10 秒)..."
  sleep 10
fi

log_ok "サービス アカウントと IAM ロールの設定が完了しました。"
