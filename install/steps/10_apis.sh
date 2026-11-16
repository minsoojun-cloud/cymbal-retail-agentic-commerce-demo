#!/usr/bin/env bash
# ==============================================================================
# 10_apis.sh — 必要な Google Cloud API の有効化
# ==============================================================================
set -euo pipefail
STEP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${STEP_DIR}/../lib/common.sh"
load_config

APIS=(
  retail.googleapis.com
  aiplatform.googleapis.com
  run.googleapis.com
  cloudbuild.googleapis.com
  artifactregistry.googleapis.com
  bigquery.googleapis.com
  storage.googleapis.com
  speech.googleapis.com
  texttospeech.googleapis.com
  iam.googleapis.com
)

log_info "プロジェクト '${PROJECT_ID}' で必要な Google Cloud API (${#APIS[@]} 件) を有効化しています..."
for api in "${APIS[@]}"; do
  printf "  - %s\n" "${api}"
done

gcloud services enable "${APIS[@]}" --project "${PROJECT_ID}" --quiet

# 新規有効化直後の API 伝播待ち（後続の Vertex AI モデルプローブ・IAM 付与の安定化）
log_info "API 有効化の反映を確認しています..."
sleep 5
log_ok "すべての必須 API が有効化されました。"
