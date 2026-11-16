#!/usr/bin/env bash
# Cymbal Retail VMD 機能表・POP自動生成スタジオを Cloud Run へデプロイする。
# 使い方: ./deploy.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${HERE}/.." && pwd)"
cd "${HERE}"

if [[ -z "${PROJECT_ID:-}" && -f "${REPO_ROOT}/install/config.env" ]]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/install/config.env"
fi
if [[ -f "${HERE}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${HERE}/.env"
  set +a
fi

PROJECT_ID="${PROJECT_ID:?PROJECT_ID を設定してください（例: install/config.env）}"
REGION="${REGION:-asia-northeast1}"
GEMINI_LOCATION="${GEMINI_LOCATION:-global}"
SERVICE_PREFIX="${SERVICE_PREFIX:-cymbal}"
SERVICE_NAME="${SPEC_BANNER_SERVICE:-${SERVICE_PREFIX}-spec-banner}"
RUNTIME_SA_NAME="${RUNTIME_SA_NAME:-${SERVICE_PREFIX}-runtime}"
RUNTIME_SA="${RUNTIME_SA:-${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com}"

GCS_BUCKET="${SPEC_BANNER_BUCKET:-${PROJECT_ID}-spec-banner}"
BQ_DATASET="${ENRICH_BQ_DATASET:-cymbal_enrichment}"
AI_MODEL="${SPEC_BANNER_AI_MODEL:-${ENRICH_GEMINI_MODEL:-${GEMINI_MODEL:-gemini-2.5-flash}}}"
if [[ -z "${AI_MODEL}" ]]; then
  AI_MODEL="gemini-2.5-flash"
fi

if ! gcloud storage buckets describe "gs://${GCS_BUCKET}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "Creating GCS bucket gs://${GCS_BUCKET} in ${REGION}..."
  gcloud storage buckets create "gs://${GCS_BUCKET}" \
    --project="${PROJECT_ID}" \
    --location="${REGION}" \
    --uniform-bucket-level-access
fi

echo "Deploying ${SERVICE_NAME} to ${PROJECT_ID}/${REGION} (bucket: ${GCS_BUCKET}, dataset: ${BQ_DATASET})..."

gcloud run deploy "${SERVICE_NAME}" --quiet \
  --source . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --service-account "${RUNTIME_SA}" \
  --no-allow-unauthenticated \
  --min-instances "${SPEC_BANNER_MIN_INSTANCES:-0}" \
  --max-instances "${SPEC_BANNER_MAX_INSTANCES:-3}" \
  --memory 2Gi --cpu 2 --timeout 600 \
  --set-env-vars "^@^PROJECT_ID=${PROJECT_ID}@GOOGLE_CLOUD_PROJECT=${PROJECT_ID}@AI_PROJECT=${PROJECT_ID}@AI_LOCATION=${GEMINI_LOCATION}@AI_MODEL=${AI_MODEL}@GCS_BUCKET=${GCS_BUCKET}@ENABLE_GCS_UPLOAD=true@BQ_DATASET=${BQ_DATASET}@PRODUCT_REG_URL=${PRODUCT_REG_URL:-}"

if ! gcloud run services add-iam-policy-binding "${SERVICE_NAME}" --quiet \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --member="allUsers" --role="roles/run.invoker" >/dev/null 2>&1; then
  echo "WARN: 組織ポリシーにより ${SERVICE_NAME} への公開アクセス（allUsers）付与はスキップされました。Cloud Console から許可するか ID トークン認証をご利用ください。" >&2
fi

URL="$(gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
echo "${URL}"
