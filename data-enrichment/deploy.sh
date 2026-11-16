#!/usr/bin/env bash
# Cymbal Retail 商品情報エンリッチメント スタジオを Cloud Run へデプロイする。
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
PROJECT_NUMBER="${PROJECT_NUMBER:-$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')}"
REGION="${REGION:-asia-northeast1}"
GEMINI_LOCATION="${GEMINI_LOCATION:-global}"
SERVICE_PREFIX="${SERVICE_PREFIX:-cymbal}"
SERVICE_NAME="${ENRICH_SERVICE:-${SERVICE_PREFIX}-data-enrichment}"
ONLINE_STORE_SERVICE="${ONLINE_STORE_SERVICE:-${SERVICE_PREFIX}-site-adk}"
RUNTIME_SA_NAME="${RUNTIME_SA_NAME:-${SERVICE_PREFIX}-runtime}"
RUNTIME_SA="${RUNTIME_SA:-${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com}"

BQ_DATASET="${BQ_DATASET:-cymbal}"
ENRICH_BQ_DATASET="${ENRICH_BQ_DATASET:-cymbal_enrichment}"
BQ_SOURCE_TABLE="${BQ_SOURCE_TABLE:-${PROJECT_ID}.${BQ_DATASET}.products}"
ENRICH_GEMINI_MODEL="${ENRICH_GEMINI_MODEL:-${GEMINI_MODEL:-gemini-3.8-flash}}"
GEMINI_FALLBACK_MODEL="${GEMINI_FALLBACK_MODEL:-gemini-3.5-flash}"
IMAGE_BUCKET="${ENRICH_IMAGE_BUCKET:-${IMAGE_BUCKET:-products_images_${PROJECT_ID}}}"
IMAGE_MODEL="${IMAGE_MODEL:-gemini-3.1-flash-image}"
IMAGE_MODEL_PRO="${IMAGE_MODEL_PRO:-gemini-3-pro-image}"
IMAGE_MODEL_FALLBACK="${IMAGE_MODEL_FALLBACK:-gemini-2.5-flash-image}"
BRAND_NAME="${BRAND_NAME:-Cymbal Retail}"

PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://${SERVICE_NAME}-${PROJECT_NUMBER}.${REGION}.run.app}"
STORE_URL="${STORE_URL:-${ONLINE_STORE_URL:-https://${ONLINE_STORE_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app}}"
FLYER_URL="${FLYER_URL:-}"

echo "Deploying ${SERVICE_NAME} to ${PROJECT_ID}/${REGION} (model: ${ENRICH_GEMINI_MODEL}, dataset: ${ENRICH_BQ_DATASET})"

# max-instances=1: BigQuery 永続化＋インメモリキャッシュの一貫性を保つため単一インスタンス構成
gcloud run deploy "${SERVICE_NAME}" --quiet \
  --source . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --service-account "${RUNTIME_SA}" \
  --no-allow-unauthenticated \
  --min-instances "${ENRICH_MIN_INSTANCES:-0}" --max-instances 1 \
  --memory 2Gi --cpu 2 --timeout 900 \
  --set-env-vars "^@^PROJECT_ID=${PROJECT_ID}@ENRICH_BQ_DATASET=${ENRICH_BQ_DATASET}@BQ_DATASET=${BQ_DATASET}@BQ_LOCATION=${REGION}@BQ_SOURCE_TABLE=${BQ_SOURCE_TABLE}@ENRICH_GEMINI_MODEL=${ENRICH_GEMINI_MODEL}@GEMINI_FALLBACK_MODEL=${GEMINI_FALLBACK_MODEL}@VERTEX_LOCATION=${GEMINI_LOCATION}@ENRICH_BATCH_MODEL=${ENRICH_GEMINI_MODEL}@BATCH_LOCATION=${GEMINI_LOCATION}@ENRICH_IMAGE_BUCKET=${IMAGE_BUCKET}@IMAGE_BUCKET=${IMAGE_BUCKET}@IMAGE_MODEL=${IMAGE_MODEL}@IMAGE_MODEL_PRO=${IMAGE_MODEL_PRO}@IMAGE_MODEL_FALLBACK=${IMAGE_MODEL_FALLBACK}@PUBLIC_BASE_URL=${PUBLIC_BASE_URL}@STORE_URL=${STORE_URL}@ONLINE_STORE_URL=${STORE_URL}@FLYER_URL=${FLYER_URL}@BRAND_NAME=${BRAND_NAME}"

if ! gcloud run services add-iam-policy-binding "${SERVICE_NAME}" --quiet \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --member="allUsers" --role="roles/run.invoker" >/dev/null 2>&1; then
  echo "WARN: 組織ポリシーにより ${SERVICE_NAME} への公開アクセス（allUsers）付与はスキップされました。Cloud Console から許可するか ID トークン認証をご利用ください。" >&2
fi

URL="$(gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
echo "${URL}"
