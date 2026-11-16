#!/usr/bin/env bash
# Cymbal Retail オンラインストア（ADK 版）を Cloud Run へデプロイする。
# ビルドコンテキスト（一時ディレクトリ）に app/, static/（商品画像 4,131 枚含む）,
# seed/catalog/products_retail.jsonl, seed/personas/ をステージングしてデプロイする。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${HERE}/.." && pwd)"

# 呼び出し元の環境変数を優先退避
CALLER_SERVICE="${ONLINE_STORE_SERVICE:-${SERVICE_NAME:-}}"
CALLER_ADK_URL="${ADK_AGENT_URL-__unset__}"
CALLER_ENRICH_URL="${ENRICH_URL-__unset__}"
CALLER_STORE_APP_URL="${STORE_APP_URL-__unset__}"
CALLER_VOICE="${VOICE_ENABLED-__unset__}"
CALLER_BRAND="${BRAND_NAME-__unset__}"
CALLER_BACKEND="${AGENT_BACKEND-__unset__}"

if [[ -z "${PROJECT_ID:-}" && -f "${REPO_ROOT}/install/config.env" ]]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/install/config.env"
fi

if [[ -f "${REPO_ROOT}/shared/adk_agent/DEPLOYMENT.env" ]]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/shared/adk_agent/DEPLOYMENT.env"
fi

[[ -n "${CALLER_SERVICE}" ]] && ONLINE_STORE_SERVICE="${CALLER_SERVICE}"
[[ "${CALLER_ADK_URL}" != "__unset__" ]] && ADK_AGENT_URL="${CALLER_ADK_URL}"
[[ "${CALLER_ENRICH_URL}" != "__unset__" ]] && ENRICH_URL="${CALLER_ENRICH_URL}"
[[ "${CALLER_STORE_APP_URL}" != "__unset__" ]] && STORE_APP_URL="${CALLER_STORE_APP_URL}"
[[ "${CALLER_VOICE}" != "__unset__" ]] && VOICE_ENABLED="${CALLER_VOICE}"
[[ "${CALLER_BRAND}" != "__unset__" ]] && BRAND_NAME="${CALLER_BRAND}"
[[ "${CALLER_BACKEND}" != "__unset__" ]] && AGENT_BACKEND="${CALLER_BACKEND}"

PROJECT_ID="${PROJECT_ID:?PROJECT_ID を設定してください（例: install/config.env）}"
PROJECT_NUMBER="${PROJECT_NUMBER:-$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')}"
REGION="${REGION:-asia-northeast1}"
SERVICE_PREFIX="${SERVICE_PREFIX:-cymbal}"
SERVICE="${ONLINE_STORE_SERVICE:-${SERVICE_PREFIX}-site-adk}"
RUNTIME_SA_NAME="${RUNTIME_SA_NAME:-${SERVICE_PREFIX}-runtime}"
RUNTIME_SA="${RUNTIME_SA:-${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com}"

AGENT_BACKEND="${AGENT_BACKEND:-adk}"
VOICE_ENABLED="${VOICE_ENABLED:-1}"
[[ "${VOICE_ENABLED}" == "0" ]] && VOICE_ENABLED=""
BRAND_NAME="${BRAND_NAME:-Cymbal Retail}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.8-flash}"
GEMINI_LOCATION="${GEMINI_LOCATION:-global}"
DELIVERY_SPEED_SEC="${DELIVERY_SPEED_SEC:-8}"
ADK_AGENT_URL="${ADK_AGENT_URL:-}"
ENRICH_URL="${ENRICH_URL:-}"
STORE_APP_URL="${STORE_APP_URL:-${CUSTOMER_URL:-}}"

case "${AGENT_BACKEND}" in
  ces|adk) ;;
  *) echo "AGENT_BACKEND は adk または ces を指定してください (指定値: '${AGENT_BACKEND}')" >&2; exit 1 ;;
esac

if [[ "${AGENT_BACKEND}" == "adk" ]]; then
  export CES_APP_NAME="" CES_DEPLOYMENT_NAME="" CES_TOOL_ID_MAP="{}" CES_MODEL=""
fi

export PROJECT_ID PROJECT_NUMBER REGION GEMINI_MODEL GEMINI_LOCATION
export ADK_AGENT_URL AGENT_BACKEND DELIVERY_SPEED_SEC ENRICH_URL STORE_APP_URL VOICE_ENABLED BRAND_NAME

echo "SERVICE=${SERVICE} AGENT_BACKEND=${AGENT_BACKEND} ADK_AGENT_URL=${ADK_AGENT_URL:-<unset>}" \
     "ENRICH_URL=${ENRICH_URL:-<unset>} STORE_APP_URL=${STORE_APP_URL:-<unset>} VOICE_ENABLED=${VOICE_ENABLED:-0} BRAND_NAME=${BRAND_NAME}"

CATALOG_JSONL="${CATALOG_JSONL:-${REPO_ROOT}/seed/catalog/products_retail.jsonl}"
AUTOCOMPLETE_JSONL="${AUTOCOMPLETE_JSONL:-${REPO_ROOT}/seed/catalog/autocomplete_suggestions.jsonl}"
PERSONAS_DIR="${PERSONAS_DIR:-${REPO_ROOT}/seed/personas}"
[[ -s "${CATALOG_JSONL}" ]] || { echo "カタログファイルが見つかりません: ${CATALOG_JSONL}" >&2; exit 1; }

STAGE="$(mktemp -d -t cymbal-site-XXXXXX)"
ENV_FILE="$(mktemp -t cymbal-site-env-XXXXXX.yaml)"
trap 'rm -rf "${STAGE}" "${ENV_FILE}"' EXIT

cp -r "${HERE}/app" "${HERE}/static" "${HERE}/Dockerfile" "${HERE}/requirements.txt" "${STAGE}/"
find "${STAGE}" -name '__pycache__' -prune -exec rm -rf {} +
mkdir -p "${STAGE}/data"
cp "${CATALOG_JSONL}" "${STAGE}/data/products_retail.jsonl"
[[ -s "${AUTOCOMPLETE_JSONL}" ]] && cp "${AUTOCOMPLETE_JSONL}" "${STAGE}/data/autocomplete_suggestions.jsonl"
mkdir -p "${STAGE}/data/personas"
if [[ -f "${PERSONAS_DIR}/personas.json" ]]; then
  cp "${PERSONAS_DIR}/personas.json" "${STAGE}/data/personas/"
  [[ -f "${PERSONAS_DIR}/purchase_history.jsonl" ]] && cp "${PERSONAS_DIR}/purchase_history.jsonl" "${STAGE}/data/personas/"
elif [[ -f "${REPO_ROOT}/shared/mcp_server/data/personas.json" ]]; then
  cp "${REPO_ROOT}/shared/mcp_server/data/personas.json" "${STAGE}/data/personas/"
  [[ -f "${REPO_ROOT}/shared/mcp_server/data/purchase_history.jsonl" ]] && cp "${REPO_ROOT}/shared/mcp_server/data/purchase_history.jsonl" "${STAGE}/data/personas/"
fi
echo "ステージング完了: $(wc -l < "${STAGE}/data/products_retail.jsonl") 商品, $(ls "${STAGE}/static/img/products" | wc -l) 画像ファイル"
printf '__pycache__\n*.pyc\n' > "${STAGE}/.gcloudignore"

python3 - "${ENV_FILE}" <<'PY'
import json, os, sys
env = {
  "PROJECT_ID": os.environ["PROJECT_ID"],
  "PROJECT_NUMBER": os.environ["PROJECT_NUMBER"],
  "CATALOG": os.environ.get("CATALOG", "default_catalog"),
  "BRANCH": os.environ.get("RETAIL_BRANCH", "0"),
  "SERVING_CONFIG": os.environ.get("SERVING_CONFIG", "default_search"),
  "GEMINI_MODEL": os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
  "GEMINI_LOCATION": os.environ.get("GEMINI_LOCATION", "global"),
  "ADK_AGENT_URL": os.environ.get("ADK_AGENT_URL", ""),
  "AGENT_BACKEND": os.environ.get("AGENT_BACKEND", "adk"),
  "BRAND_NAME": os.environ.get("BRAND_NAME", "Cymbal Retail"),
  "DELIVERY_SPEED_SEC": os.environ.get("DELIVERY_SPEED_SEC", "8"),
}
for k in ("ENRICH_URL", "STORE_APP_URL", "FLYER_URL"):
    if os.environ.get(k):
        env[k] = os.environ[k]
if os.environ.get("VOICE_ENABLED"):
    env["VOICE_ENABLED"] = "1"
with open(sys.argv[1], "w", encoding="utf-8") as f:
    for k, v in env.items():
        f.write(f"{k}: {json.dumps(str(v), ensure_ascii=False)}\n")
print("env:", {k: (v[:60] + "…" if len(v) > 60 else v) for k, v in env.items()})
PY

gcloud run deploy "${SERVICE}" --quiet \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --source "${STAGE}" \
  --service-account "${RUNTIME_SA}" \
  --no-allow-unauthenticated \
  --cpu 1 --memory 1Gi --min-instances "${SITE_MIN_INSTANCES:-1}" --max-instances 5 --concurrency 40 --timeout 300 \
  --env-vars-file "${ENV_FILE}"

if ! gcloud run services add-iam-policy-binding "${SERVICE}" --quiet \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --member="allUsers" --role="roles/run.invoker" >/dev/null 2>&1; then
  echo "WARN: 組織ポリシーにより ${SERVICE} への公開アクセス（allUsers）付与はスキップされました。Cloud Console から許可するか ID トークン認証をご利用ください。" >&2
fi

URL="$(gcloud run services describe "${SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
echo "${URL}"
