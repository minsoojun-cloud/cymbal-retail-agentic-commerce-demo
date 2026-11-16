#!/usr/bin/env bash
# Cymbal Retail チラシ作成スタジオ (cymbal-flyer-studio) を Cloud Run へデプロイする。
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
SERVICE_NAME="${FLYER_SERVICE:-${SERVICE_PREFIX}-flyer-studio}"
RUNTIME_SA_NAME="${RUNTIME_SA_NAME:-${SERVICE_PREFIX}-runtime}"
RUNTIME_SA="${RUNTIME_SA:-${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com}"

BQ_DATASET="${BQ_DATASET:-cymbal}"
FLYERS_BUCKET="${FLYERS_BUCKET:-${PROJECT_ID}-flyers}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.8-flash}"
ONLINE_STORE_SERVICE="${ONLINE_STORE_SERVICE:-${SERVICE_PREFIX}-site-adk}"
ENRICH_SERVICE="${ENRICH_SERVICE:-${SERVICE_PREFIX}-data-enrichment}"
STORE_URL="${STORE_URL:-${ONLINE_STORE_URL:-https://${ONLINE_STORE_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app}}"
ENRICH_URL="${ENRICH_URL:-https://${ENRICH_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app}"

CATALOG_JSONL="${CATALOG_JSONL:-${REPO_ROOT}/seed/catalog/products_retail.jsonl}"
PRODUCT_IMAGES_DIR="${PRODUCT_IMAGES_DIR:-${REPO_ROOT}/online-store-adk/static/img/products}"
[[ -s "${CATALOG_JSONL}" ]] || { echo "カタログファイルが見つかりません: ${CATALOG_JSONL}" >&2; exit 1; }
[[ -d "${PRODUCT_IMAGES_DIR}" ]] || { echo "商品画像ディレクトリが見つかりません: ${PRODUCT_IMAGES_DIR}" >&2; exit 1; }

STAGE="$(mktemp -d -t cymbal-flyer-XXXXXX)"
trap 'rm -rf "${STAGE}"' EXIT

cp -r "${HERE}/app" "${HERE}/static" "${HERE}/Dockerfile" "${HERE}/requirements.txt" "${STAGE}/"
find "${STAGE}" -name '__pycache__' -prune -exec rm -rf {} +
mkdir -p "${STAGE}/data" "${STAGE}/static/img/products"
if [[ -f "${HERE}/data/flyer_product_ext.json" ]]; then
  cp "${HERE}/data/flyer_product_ext.json" "${STAGE}/data/flyer_product_ext.json"
fi
cp -f "${CATALOG_JSONL}" "${STAGE}/data/products_retail.jsonl"
cp -r "${PRODUCT_IMAGES_DIR}/." "${STAGE}/static/img/products/"
printf '__pycache__\n*.pyc\n.pytest_cache\n' > "${STAGE}/.gcloudignore"

echo "Deploying ${SERVICE_NAME} to ${PROJECT_ID}/${REGION} (model: ${GEMINI_MODEL}, bucket: ${FLYERS_BUCKET})..."
gcloud run deploy "${SERVICE_NAME}" --quiet \
  --source "${STAGE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --service-account "${RUNTIME_SA}" \
  --no-allow-unauthenticated \
  --min-instances "${FLYER_MIN_INSTANCES:-0}" --max-instances 2 \
  --memory 4Gi --cpu 4 --timeout 300 \
  --set-env-vars "^@^PROJECT_ID=${PROJECT_ID}@BQ_DATASET=${BQ_DATASET}@BQ_LOCATION=${REGION}@FLYERS_BUCKET=${FLYERS_BUCKET}@GEMINI_MODEL=${GEMINI_MODEL}@GEMINI_LOCATION=${GEMINI_LOCATION}@STORE_URL=${STORE_URL}@ONLINE_STORE_URL=${STORE_URL}@ENRICH_URL=${ENRICH_URL}"

if ! gcloud run services add-iam-policy-binding "${SERVICE_NAME}" --quiet \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --member="allUsers" --role="roles/run.invoker" >/dev/null 2>&1; then
  echo "WARN: 組織ポリシーにより ${SERVICE_NAME} への公開アクセス（allUsers）付与はスキップされました。Cloud Console から許可するか ID トークン認証をご利用ください。" >&2
fi

URL="$(gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
echo "${URL}"
