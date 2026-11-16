#!/usr/bin/env bash
# ==============================================================================
# 60_backend.sh — 内部バックエンド (commerce-mcp / adk-agent) のデプロイと IAM 設定
# ==============================================================================
set -euo pipefail
STEP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${STEP_DIR}/../lib/common.sh"
load_config

# URL 書き換え済みカタログが存在しない場合は生成し、ビルドコンテキストに渡す
REWRITTEN_CATALOG="${STATE_DIR}/products_retail.rewritten.jsonl"
if [[ ! -s "${REWRITTEN_CATALOG}" && -s "${REPO_ROOT}/seed/catalog/products_retail.jsonl" ]]; then
  log_info "バックエンド同梱用に URL 書き換え済みカタログを生成しています..."
  python3 "${INSTALL_DIR}/lib/rewrite_urls.py" \
    --src "${REPO_ROOT}/seed/catalog/products_retail.jsonl" \
    --dst "${REWRITTEN_CATALOG}" \
    --online-store-url "${ONLINE_STORE_URL}"
fi
if [[ -s "${REWRITTEN_CATALOG}" ]]; then
  export CATALOG_JSONL="${REWRITTEN_CATALOG}"
fi

# 1. MCP サーバー (commerce-mcp) のデプロイ
log_info "[1/2] MCP サーバー (${MCP_SERVICE}) を Cloud Run へ非公開デプロイしています..."
bash "${REPO_ROOT}/shared/mcp_server/deploy.sh"

ACTUAL_MCP_URL="$(gcloud run services describe "${MCP_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
if [[ -z "${ACTUAL_MCP_URL}" ]]; then
  log_err "MCP サーバー (${MCP_SERVICE}) の URL を取得できませんでした。"
  exit 1
fi
export MCP_URL="${ACTUAL_MCP_URL}"
log_ok "MCP サーバー デプロイ完了: ${MCP_URL}"

log_info "${RUNTIME_SA} に ${MCP_SERVICE} の呼び出し権限 (roles/run.invoker) を付与しています..."
gcloud run services add-iam-policy-binding "${MCP_SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --member "serviceAccount:${RUNTIME_SA}" \
  --role "roles/run.invoker" \
  --quiet >/dev/null

# 2. ADK エージェント (adk-agent) のデプロイ
log_info "[2/2] ADK AIコンシェルジュ (${ADK_AGENT_SERVICE}, モデル: ${AGENT_MODEL}) を Cloud Run へ非公開デプロイしています..."
ADK_SERVICE="${ADK_AGENT_SERVICE}" ADK_AGENT_SERVICE="${ADK_AGENT_SERVICE}" MCP_URL="${MCP_URL}" \
  bash "${REPO_ROOT}/shared/adk_agent/deploy.sh"

ACTUAL_ADK_URL="$(gcloud run services describe "${ADK_AGENT_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
if [[ -z "${ACTUAL_ADK_URL}" ]]; then
  log_err "ADK エージェント (${ADK_AGENT_SERVICE}) の URL を取得できませんでした。"
  exit 1
fi
export ADK_AGENT_URL="${ACTUAL_ADK_URL}"
log_ok "ADK エージェント デプロイ完了: ${ADK_AGENT_URL}"

log_info "${RUNTIME_SA} に ${ADK_AGENT_SERVICE} の呼び出し権限 (roles/run.invoker) を付与しています..."
gcloud run services add-iam-policy-binding "${ADK_AGENT_SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --member "serviceAccount:${RUNTIME_SA}" \
  --role "roles/run.invoker" \
  --quiet >/dev/null

save_urls_env
log_ok "内部バックエンド 2 サービスのデプロイとサービス間 IAM 設定が完了しました。"
