#!/usr/bin/env bash
# ADK AIコンシェルジュ (${ADK_AGENT_SERVICE}) を Cloud Run（内部公開）へデプロイする。
#   - セッション保持（InMemorySessionService）のため min 1 / max 1 インスタンスで稼働
#   - オンラインストア BFF が RUNTIME_SA の ID トークンでプロキシ呼び出し
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
GEMINI_LOCATION="${GEMINI_LOCATION:-global}"
SERVICE_PREFIX="${SERVICE_PREFIX:-cymbal}"
SERVICE="${ADK_AGENT_SERVICE:-${ADK_SERVICE:-${SERVICE_PREFIX}-adk-agent}}"
MCP_SERVICE="${MCP_SERVICE:-${SERVICE_PREFIX}-commerce-mcp}"
RUNTIME_SA_NAME="${RUNTIME_SA_NAME:-${SERVICE_PREFIX}-runtime}"
RUNTIME_SA="${RUNTIME_SA:-${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com}"
AGENT_THINKING_BUDGET="${AGENT_THINKING_BUDGET:-0}"
BRAND_NAME="${BRAND_NAME:-Cymbal Retail}"
CATALOG_JSONL="${CATALOG_JSONL:-$REPO_ROOT/seed/catalog/products_retail.jsonl}"

# AGENT_MODEL の決定（未指定時は最新候補からプロジェクトで利用可能なモデルをプローブしてフォールバック）
if [[ -z "${AGENT_MODEL:-}" ]]; then
  if [[ -n "${GEMINI_MODEL:-}" ]]; then
    AGENT_MODEL="${GEMINI_MODEL}"
  else
    AGENT_MODEL="$(python3 - "$PROJECT_ID" "$GEMINI_LOCATION" <<'PY'
import json, subprocess, sys, urllib.request
project, loc = sys.argv[1], sys.argv[2]
candidates = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
]
try:
    tok = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
except Exception:
    print("gemini-3.8-flash")
    sys.exit(0)
host = "aiplatform.googleapis.com" if loc == "global" else f"{loc}-aiplatform.googleapis.com"
for m in candidates:
    url = f"https://{host}/v1/projects/{project}/locations/{loc}/publishers/google/models/{m}:generateContent"
    body = json.dumps({"contents": [{"role": "user", "parts": [{"text": "ping"}]}],
                       "generationConfig": {"maxOutputTokens": 4}}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status == 200:
                print(m)
                sys.exit(0)
    except Exception:
        continue
print("gemini-3.8-flash")
PY
)"
  fi
fi
echo "AGENT_MODEL=${AGENT_MODEL}"

# MCP_URL の解決（環境変数 -> shared/mcp_server/DEPLOYMENT.env -> Cloud Run describe）
if [[ -z "${MCP_URL:-}" && -f "$REPO_ROOT/shared/mcp_server/DEPLOYMENT.env" ]]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/shared/mcp_server/DEPLOYMENT.env"
fi
if [[ -z "${MCP_URL:-}" ]]; then
  MCP_URL="$(gcloud run services describe "${MCP_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
fi
echo "MCP_URL=${MCP_URL}"

# カート金額計算用の軽量カタログをビルド用ディレクトリにステージングし、終了時にクリーンアップ
cleanup() {
  rm -rf "${HERE}/data"
}
trap cleanup EXIT

mkdir -p "${HERE}/data"
python3 - "${CATALOG_JSONL}" "${HERE}/data/products_retail.jsonl" <<'PY'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
n = 0
with open(src, encoding="utf-8") as f, open(dst, "w", encoding="utf-8") as o:
    for line in f:
        if not line.strip():
            continue
        d = json.loads(line)
        o.write(json.dumps({"id": d["id"], "title": d.get("title", ""),
                            "priceInfo": {"price": (d.get("priceInfo") or {}).get("price", 0)},
                            "availability": d.get("availability", "IN_STOCK")}, ensure_ascii=False) + "\n")
        n += 1
print(f"compact catalog: {n} products -> {dst}")
PY

# ADK エージェントのランタイム SA に MCP サーバー呼び出し権限を付与
gcloud run services add-iam-policy-binding "${MCP_SERVICE}" --quiet \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --member "serviceAccount:${RUNTIME_SA}" --role roles/run.invoker >/dev/null || true

gcloud run deploy "${SERVICE}" --quiet \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --source "${HERE}" \
  --service-account "${RUNTIME_SA}" \
  --no-allow-unauthenticated \
  --cpu 2 --memory 2Gi --cpu-boost --no-cpu-throttling \
  --min-instances "${ADK_MIN_INSTANCES:-1}" --max-instances 1 \
  --concurrency 40 --timeout 300 \
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${GEMINI_LOCATION},AGENT_MODEL=${AGENT_MODEL},AGENT_THINKING_BUDGET=${AGENT_THINKING_BUDGET},MCP_URL=${MCP_URL},BRAND_NAME=${BRAND_NAME},WARMUP_CUSTOMER_ID=CR-0001"

# オンラインストア BFF がランタイム SA でプロキシ呼び出しできるよう invoker を付与
gcloud run services add-iam-policy-binding "${SERVICE}" --quiet \
  --project "${PROJECT_ID}" --region "${REGION}" \
  --member "serviceAccount:${RUNTIME_SA}" --role roles/run.invoker >/dev/null || true

URL="$(gcloud run services describe "${SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
cat > "${HERE}/DEPLOYMENT.env" <<EOF
ADK_AGENT_SERVICE=${SERVICE}
ADK_AGENT_URL=${URL}
ADK_AGENT_MODEL=${AGENT_MODEL}
PROJECT_ID=${PROJECT_ID}
REGION=${REGION}
EOF
echo "ADK エージェント: ${URL}"
echo "ヘルスチェック  : curl -H \"Authorization: Bearer \$(gcloud auth print-identity-token)\" ${URL}/api/health"
echo "ライブテスト    : python3 ${HERE}/test_live.py"
