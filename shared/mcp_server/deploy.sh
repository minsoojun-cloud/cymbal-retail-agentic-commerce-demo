#!/usr/bin/env bash
# Cymbal Commerce MCP サーバーを Cloud Run（内部公開: ID トークン認証）へデプロイする。
# 使い方: ./deploy.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

if [[ -z "${PROJECT_ID:-}" && -f "$REPO_ROOT/install/config.env" ]]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/install/config.env"
fi

PROJECT_ID="${PROJECT_ID:?PROJECT_ID を設定してください（例: install/config.env）}"
REGION="${REGION:-asia-northeast1}"
SERVICE_PREFIX="${SERVICE_PREFIX:-cymbal}"
SERVICE="${MCP_SERVICE:-${SERVICE_PREFIX}-commerce-mcp}"
RUNTIME_SA_NAME="${RUNTIME_SA_NAME:-${SERVICE_PREFIX}-runtime}"
RUNTIME_SA="${RUNTIME_SA:-${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com}"
BQ_DATASET="${BQ_DATASET:-cymbal}"

# BigQuery 未接続時のフォールバック用ペルソナデータをバンドル
PERSONAS_DIR="${PERSONAS_DIR:-$REPO_ROOT/seed/personas}" python3 "${HERE}/prepare_data.py"

gcloud run deploy "${SERVICE}" --quiet \
  --project "${PROJECT_ID}" \
  --source "${HERE}" \
  --region "${REGION}" \
  --service-account "${RUNTIME_SA}" \
  --no-allow-unauthenticated \
  --cpu 1 --memory 1Gi --concurrency 40 --timeout 60 \
  --min-instances "${MCP_MIN_INSTANCES:-1}" --max-instances 5 \
  --set-env-vars "PROJECT_ID=${PROJECT_ID},REGION=${REGION},LOCATION=global,CATALOG=default_catalog,BRANCH=0,SERVING_CONFIG=default_search,BQ_DATASET=${BQ_DATASET},BQ_LOCATION=${REGION},COMPACT_RESULTS=true,DINNER_WARM=true"

URL=$(gcloud run services describe "${SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')
cat > "${HERE}/DEPLOYMENT.env" <<EOF
MCP_SERVICE=${SERVICE}
MCP_URL=${URL}
PROJECT_ID=${PROJECT_ID}
REGION=${REGION}
EOF
echo "MCP エンドポイント: ${URL}/mcp"
echo "スモークテスト    : python3 ${HERE}/testing.py --url ${URL} --auth"
