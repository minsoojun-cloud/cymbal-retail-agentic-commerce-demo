#!/usr/bin/env bash
# ==============================================================================
# 40_data.sh — GCS バケット・BigQuery データセット作成と全シードデータの投入
# ==============================================================================
set -euo pipefail
STEP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${STEP_DIR}/../lib/common.sh"
load_config

log_info "Cloud Storage バケット・BigQuery データセットを作成し、シードデータ一式をロードしています..."
python3 "${INSTALL_DIR}/lib/load_seed.py" \
  --project "${PROJECT_ID}" \
  --region "${REGION}"

# バケット単位でも RUNTIME_SA に明示権限を付与（均一バケットレベルアクセス）
log_info "各 Cloud Storage バケットに対する ${RUNTIME_SA} のアクセス権限を確認しています..."
for bkt in "${CATALOG_BUCKET}" "${STORE_NAVI_BUCKET}" "${ENRICH_IMAGE_BUCKET}"; do
  gcloud storage buckets add-iam-policy-binding "gs://${bkt}" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/storage.objectAdmin" \
    --project="${PROJECT_ID}" \
    --quiet >/dev/null
done

log_ok "全シードデータ（GCS アセット・BigQuery テーブル）の投入が完了しました。"
