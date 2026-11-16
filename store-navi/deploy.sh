#!/usr/bin/env bash
# Store Navi（お客様向けアプリ / スタッフ向けアプリ）を Cloud Run へデプロイする。
# 1 種類のコンテナイメージから APP_MODE に応じて 2 つのサービスをデプロイできる:
#   SERVICE_NAME=${STORE_APP_SERVICE}   ./deploy.sh    # お客様アプリ  (APP_MODE=customer)
#   SERVICE_NAME=${STORE_STAFF_SERVICE} ./deploy.sh    # スタッフアプリ (APP_MODE=staff)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${HERE}/.." && pwd)"

CALLER_SERVICE="${SERVICE_NAME:-}"
CALLER_APP_MODE="${APP_MODE:-}"
CALLER_STAFF_URL="${STAFF_URL-__unset__}"
CALLER_CUSTOMER_URL="${CUSTOMER_URL-__unset__}"
CALLER_ONLINE_URL="${ONLINE_STORE_URL-__unset__}"
CALLER_ENRICH_URL="${ENRICH_URL-__unset__}"
CALLER_MCP_URL="${MCP_URL-__unset__}"
CALLER_MODEL="${AGENT_MODEL-__unset__}"

if [[ -z "${PROJECT_ID:-}" && -f "${REPO_ROOT}/install/config.env" ]]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/install/config.env"
fi

if [[ -f "${REPO_ROOT}/shared/mcp_server/DEPLOYMENT.env" ]]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/shared/mcp_server/DEPLOYMENT.env"
fi

[[ "${CALLER_STAFF_URL}" != "__unset__" ]] && STAFF_URL="${CALLER_STAFF_URL}"
[[ "${CALLER_CUSTOMER_URL}" != "__unset__" ]] && CUSTOMER_URL="${CALLER_CUSTOMER_URL}"
[[ "${CALLER_ONLINE_URL}" != "__unset__" ]] && ONLINE_STORE_URL="${CALLER_ONLINE_URL}"
[[ "${CALLER_ENRICH_URL}" != "__unset__" ]] && ENRICH_URL="${CALLER_ENRICH_URL}"
[[ "${CALLER_MCP_URL}" != "__unset__" ]] && MCP_URL="${CALLER_MCP_URL}"
[[ "${CALLER_MODEL}" != "__unset__" ]] && AGENT_MODEL="${CALLER_MODEL}"

PROJECT_ID="${PROJECT_ID:?PROJECT_ID を設定してください（例: install/config.env）}"
PROJECT_NUMBER="${PROJECT_NUMBER:-$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')}"
REGION="${REGION:-asia-northeast1}"
SERVICE_PREFIX="${SERVICE_PREFIX:-cymbal}"

STORE_APP_SERVICE="${STORE_APP_SERVICE:-${SERVICE_PREFIX}-store-app}"
STORE_STAFF_SERVICE="${STORE_STAFF_SERVICE:-${SERVICE_PREFIX}-store-staff}"
ONLINE_STORE_SERVICE="${ONLINE_STORE_SERVICE:-${SERVICE_PREFIX}-site-adk}"
MCP_SERVICE="${MCP_SERVICE:-${SERVICE_PREFIX}-commerce-mcp}"
RUNTIME_SA_NAME="${RUNTIME_SA_NAME:-${SERVICE_PREFIX}-runtime}"
RUNTIME_SA="${RUNTIME_SA:-${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com}"

SERVICE="${CALLER_SERVICE}"
if [[ -z "${SERVICE}" ]]; then
  case "${CALLER_APP_MODE:-customer}" in
    customer) SERVICE="${STORE_APP_SERVICE}" ;;
    staff)    SERVICE="${STORE_STAFF_SERVICE}" ;;
    *) echo "APP_MODE は customer または staff を指定してください (指定値: '${CALLER_APP_MODE}')" >&2; exit 1 ;;
  esac
fi

if [[ "${SERVICE}" == "${STORE_APP_SERVICE}" ]]; then
  APP_MODE="customer"
elif [[ "${SERVICE}" == "${STORE_STAFF_SERVICE}" ]]; then
  APP_MODE="staff"
else
  echo "エラー: SERVICE_NAME は ${STORE_APP_SERVICE} または ${STORE_STAFF_SERVICE} である必要があります (指定値: '${SERVICE}')" >&2
  exit 1
fi

if [[ -n "${APP_MODE_OVERRIDE:-}" && "${APP_MODE_OVERRIDE}" != "${APP_MODE}" ]]; then
  echo "エラー: ${SERVICE} は APP_MODE=${APP_MODE} で実行する必要があります" >&2
  exit 1
fi

URL_SUFFIX="${PROJECT_NUMBER}.${REGION}.run.app"
STAFF_URL="${STAFF_URL:-https://${STORE_STAFF_SERVICE}-${URL_SUFFIX}}"
CUSTOMER_URL="${CUSTOMER_URL:-https://${STORE_APP_SERVICE}-${URL_SUFFIX}}"
ONLINE_STORE_URL="${ONLINE_STORE_URL:-${STORE_URL:-https://${ONLINE_STORE_SERVICE}-${URL_SUFFIX}}}"
ENRICH_URL="${ENRICH_URL:-}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.8-flash}"
GEMINI_LOCATION="${GEMINI_LOCATION:-global}"
AGENT_MODEL="${AGENT_MODEL:-${GEMINI_MODEL}}"
AGENT_MODE="${AGENT_MODE:-live}"
BRAND_NAME="${BRAND_NAME:-Cymbal Retail}"
STORE_NAVI_BUCKET="${STORE_NAVI_BUCKET:-${PHOTO_BUCKET:-${PROJECT_ID}-store-navi}}"
PHOTO_BUCKET="${STORE_NAVI_BUCKET}"

DATA_JSONL="${CATALOG_JSONL:-${REPO_ROOT}/seed/catalog/products_retail.jsonl}"
SUGG_JSONL="${AUTOCOMPLETE_JSONL:-${REPO_ROOT}/seed/catalog/autocomplete_suggestions.jsonl}"
IMG_DIR="${PRODUCT_IMAGES_DIR:-${REPO_ROOT}/online-store-adk/static/img/products}"
SITE_APP="${REPO_ROOT}/online-store-adk/app"

[[ -s "${DATA_JSONL}" ]] || { echo "カタログファイルが見つかりません: ${DATA_JSONL}" >&2; exit 1; }
[[ -s "${HERE}/data/stores.json" ]] || { echo "店舗データが見つかりません: ${HERE}/data/stores.json" >&2; exit 1; }
for f in catalog.py search.py ai.py; do
  [[ -s "${SITE_APP}/${f}" ]] || { echo "共通モジュールが見つかりません: ${SITE_APP}/${f}" >&2; exit 1; }
done

MCP_URL="${MCP_URL:-}"
if [[ -z "${MCP_URL}" && "${DRY_RUN:-0}" != "1" ]]; then
  MCP_URL="$(gcloud run services describe "${MCP_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
fi
echo "SERVICE=${SERVICE} APP_MODE=${APP_MODE} MCP_URL=${MCP_URL:-<unset>} AGENT_MODEL=${AGENT_MODEL} AGENT_MODE=${AGENT_MODE}"

STAGE="$(mktemp -d -t cymbal-store-navi-XXXXXX)"
ENV_FILE="$(mktemp -t cymbal-store-navi-env-XXXXXX.yaml)"
trap 'rm -rf "${STAGE}" "${ENV_FILE}"' EXIT

cp -r "${HERE}/app" "${HERE}/static" "${HERE}/Dockerfile" "${HERE}/requirements.txt" "${STAGE}/"
if [[ "${APP_MODE}" == "staff" && ! -s "${STAGE}/app/staff.py" ]]; then
  echo "エラー: APP_MODE=staff ですが app/staff.py が存在しません" >&2
  exit 1
fi
mkdir -p "${STAGE}/site_lib" "${STAGE}/data" "${STAGE}/product_images"
cp "${SITE_APP}/catalog.py" "${SITE_APP}/search.py" "${SITE_APP}/ai.py" "${STAGE}/site_lib/"
printf '"""Copies of online-store-adk/app/{catalog,search,ai}.py (staged by store-navi/deploy.sh; do not edit)."""\n' > "${STAGE}/site_lib/__init__.py"
cp -r "${HERE}/data/." "${STAGE}/data/"
cp "${DATA_JSONL}" "${STAGE}/data/products_retail.jsonl"
[[ -s "${SUGG_JSONL}" ]] && cp "${SUGG_JSONL}" "${STAGE}/data/autocomplete_suggestions.jsonl"
cp -r "${IMG_DIR}/." "${STAGE}/product_images/"
find "${STAGE}" -name '__pycache__' -prune -exec rm -rf {} +
rm -rf "${STAGE}/data/products_extra.jsonl"
printf '__pycache__\n*.pyc\n' > "${STAGE}/.gcloudignore"
echo "ステージング完了: $(wc -l < "${STAGE}/data/products_retail.jsonl") 商品, $(ls "${STAGE}/product_images" | wc -l) 画像"

export PROJECT_ID PROJECT_NUMBER GEMINI_MODEL GEMINI_LOCATION BRAND_NAME
export APP_MODE STAFF_URL CUSTOMER_URL ONLINE_STORE_URL ENRICH_URL AGENT_MODEL AGENT_MODE MCP_URL PHOTO_BUCKET STORE_NAVI_BUCKET

python3 - "${ENV_FILE}" <<'PY'
import json, os, sys
env = {
  "APP_MODE": os.environ["APP_MODE"],
  "DATA_MODE": "bq",
  "PROJECT_ID": os.environ["PROJECT_ID"],
  "PROJECT_NUMBER": os.environ["PROJECT_NUMBER"],
  "BQ_DATASET": os.environ.get("BQ_DATASET", "cymbal"),
  "CATALOG": os.environ.get("CATALOG", "default_catalog"),
  "BRANCH": os.environ.get("RETAIL_BRANCH", "0"),
  "SERVING_CONFIG": os.environ.get("SERVING_CONFIG", "default_search"),
  "GEMINI_MODEL": os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
  "GEMINI_LOCATION": os.environ.get("GEMINI_LOCATION", "global"),
  "ONLINE_STORE_URL": os.environ["ONLINE_STORE_URL"],
  "BRAND_NAME": os.environ.get("BRAND_NAME", "Cymbal Retail"),
  "MCP_URL": os.environ.get("MCP_URL", ""),
  "AGENT_MODEL": os.environ["AGENT_MODEL"],
  "AGENT_MODE": os.environ["AGENT_MODE"],
  "AGENT_LOCATION": os.environ.get("GEMINI_LOCATION", "global"),
  "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
  "GOOGLE_CLOUD_PROJECT": os.environ["PROJECT_ID"],
  "GOOGLE_CLOUD_LOCATION": os.environ.get("GEMINI_LOCATION", "global"),
  "STORE_NAVI_BUCKET": os.environ["STORE_NAVI_BUCKET"],
  "PHOTO_BUCKET": os.environ["PHOTO_BUCKET"],
  "STORE_DATA_REFRESH_SEC": os.environ.get("STORE_DATA_REFRESH_SEC", "20"),
}
if os.environ.get("ENRICH_URL"):
    env["ENRICH_URL"] = os.environ["ENRICH_URL"]
if env["APP_MODE"] == "customer":
    env["STAFF_URL"] = os.environ["STAFF_URL"]
else:
    env["CUSTOMER_URL"] = os.environ["CUSTOMER_URL"]
    if os.environ.get("STAFF_PREWARM"):
        env["STAFF_PREWARM"] = os.environ["STAFF_PREWARM"]
with open(sys.argv[1], "w", encoding="utf-8") as f:
    for k, v in env.items():
        f.write(f"{k}: {json.dumps(str(v), ensure_ascii=False)}\n")
print("env:", {k: (v[:60] + "…" if len(v) > 60 else v) for k, v in env.items()})
PY

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo "DRY_RUN=1: ${STAGE} にステージングしました（デプロイ未実行）"; ls -la "${STAGE}"; trap - EXIT; exit 0
fi

# 内蔵 ADK エージェントが内部公開 MCP サーバーを呼び出せるよう invoker 権限を確認・付与
gcloud run services add-iam-policy-binding "${MCP_SERVICE}" --quiet \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --member "serviceAccount:${RUNTIME_SA}" --role roles/run.invoker >/dev/null || true

gcloud run deploy "${SERVICE}" --quiet \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --source "${STAGE}" \
  --service-account "${RUNTIME_SA}" \
  --no-allow-unauthenticated \
  --cpu 2 --memory 2Gi --cpu-boost \
  --min-instances "${STORE_MIN_INSTANCES:-1}" --max-instances 3 --session-affinity \
  --concurrency 40 --timeout 300 \
  --env-vars-file "${ENV_FILE}"

if ! gcloud run services add-iam-policy-binding "${SERVICE}" --quiet \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --member="allUsers" --role="roles/run.invoker" >/dev/null 2>&1; then
  echo "WARN: 組織ポリシーにより ${SERVICE} への公開アクセス（allUsers）付与はスキップされました。Cloud Console から許可するか ID トークン認証をご利用ください。" >&2
fi

URL="$(gcloud run services describe "${SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
echo "${SERVICE}: ${URL}"
echo "ヘルスチェック: curl -s ${URL}/api/health"
