#!/usr/bin/env bash
# ==============================================================================
# 00_preflight.sh — 事前環境・認証・課金・設定内容の検証
# ==============================================================================
set -euo pipefail
STEP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${STEP_DIR}/../lib/common.sh"
load_config

log_info "必須コマンドの存在を確認しています..."
missing=0
for cmd in gcloud bq python3; do
  if command -v "${cmd}" >/dev/null 2>&1; then
    log_ok "${cmd}: $(command -v "${cmd}")"
  else
    log_err "必須コマンド '${cmd}' が見つかりません。"
    missing=1
  fi
done

if command -v uv >/dev/null 2>&1; then
  log_ok "uv: $(command -v uv)"
else
  log_warn "推奨ツール 'uv' が見つかりません（インストーラー本体は標準 python3 で動作しますが、ローカル開発・カタログ生成時には便利です）。"
  log_info "uv のインストール方法: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

if [[ "${missing}" -ne 0 ]]; then
  log_err "Google Cloud SDK (gcloud / bq) および python3 をインストールしてから再実行してください。"
  exit 1
fi

log_info "Google Cloud の認証状態を確認しています..."
ACTIVE_ACCOUNT="$(gcloud auth list --filter='status:ACTIVE' --format='value(account)' 2>/dev/null | head -n 1 || true)"
if [[ -z "${ACTIVE_ACCOUNT}" ]]; then
  log_err "アクティブな gcloud アカウントがありません。'gcloud auth login' を実行してください。"
  exit 1
fi
if ! gcloud auth print-access-token >/dev/null 2>&1; then
  log_err "アクセストークンを取得できませんでした。'gcloud auth login' で再認証してください。"
  exit 1
fi
log_ok "認証アカウント: ${ACTIVE_ACCOUNT}"

log_info "対象プロジェクト '${PROJECT_ID}' の存在と課金設定を確認しています..."
PROJ_STATE="$(gcloud projects describe "${PROJECT_ID}" --format='value(lifecycleState)' 2>/dev/null || true)"
if [[ "${PROJ_STATE}" != "ACTIVE" ]]; then
  log_err "プロジェクト '${PROJECT_ID}' が存在しないか、ACTIVE 状態ではありません (状態: ${PROJ_STATE:-不明})。"
  exit 1
fi

BILLING_ENABLED="$(gcloud billing projects describe "${PROJECT_ID}" --format='value(billingEnabled)' 2>/dev/null || echo 'UNKNOWN')"
if [[ "${BILLING_ENABLED}" == "True" || "${BILLING_ENABLED}" == "true" ]]; then
  log_ok "課金設定: 有効 (billingEnabled=True)"
elif [[ "${BILLING_ENABLED}" == "False" || "${BILLING_ENABLED}" == "false" ]]; then
  log_err "プロジェクト '${PROJECT_ID}' で課金 (Billing) が無効になっています。Cloud Console で請求先アカウントをリンクしてから再実行してください。"
  exit 1
else
  log_warn "課金状態の参照権限がないため確認をスキップしました (応答: ${BILLING_ENABLED})。課金が有効であることを確認してください。"
fi

printf "\n"
printf "┌──────────────────────────────────────────────────────────────────────────────┐\n"
printf "│ Cymbal Retail デモ インストール設定一覧                                      │\n"
printf "├────────────────────────────┬─────────────────────────────────────────────────┤\n"
printf "│ 項目                       │ 設定値                                          │\n"
printf "├────────────────────────────┼─────────────────────────────────────────────────┤\n"
printf "│ PROJECT_ID                 │ %-47s │\n" "${PROJECT_ID}"
printf "│ PROJECT_NUMBER             │ %-47s │\n" "${PROJECT_NUMBER}"
printf "│ REGION                     │ %-47s │\n" "${REGION}"
printf "│ GEMINI_LOCATION            │ %-47s │\n" "${GEMINI_LOCATION}"
printf "│ RUNTIME_SA                 │ %-47s │\n" "${RUNTIME_SA}"
printf "│ BigQuery データセット      │ %-47s │\n" "${BQ_DATASET}, ${ENRICH_BQ_DATASET}"
printf "│ カタログ GCS バケット      │ %-47s │\n" "gs://${CATALOG_BUCKET}"
printf "│ 店舗ナビ GCS バケット      │ %-47s │\n" "gs://${STORE_NAVI_BUCKET}"
printf "│ 生成画像 GCS バケット      │ %-47s │\n" "gs://${ENRICH_IMAGE_BUCKET}"
printf "│ 音声対話 (VOICE_ENABLED)   │ %-47s │\n" "${VOICE_ENABLED}"
printf "│ ブランド名 (BRAND_NAME)    │ %-47s │\n" "${BRAND_NAME}"
printf "├────────────────────────────┴─────────────────────────────────────────────────┤\n"
printf "│ デプロイ対象 Cloud Run サービス（予定 URL）                                  │\n"
printf "│   [非公開] %-24s %s\n" "${MCP_SERVICE}" "${MCP_URL}"
printf "│   [非公開] %-24s %s\n" "${ADK_AGENT_SERVICE}" "${ADK_AGENT_URL}"
printf "│   [公開]   %-24s %s\n" "${ONLINE_STORE_SERVICE}" "${ONLINE_STORE_URL}"
printf "│   [公開]   %-24s %s\n" "${STORE_APP_SERVICE}" "${CUSTOMER_URL}"
printf "│   [公開]   %-24s %s\n" "${STORE_STAFF_SERVICE}" "${STAFF_URL}"
printf "│   [公開]   %-24s %s\n" "${ENRICH_SERVICE}" "${ENRICH_URL}"
printf "└──────────────────────────────────────────────────────────────────────────────┘\n"

log_ok "事前チェックが完了しました。"
