#!/usr/bin/env bash
# ==============================================================================
# 70_apps.sh — ユーザー向け 4 アプリケーションの Cloud Run デプロイと相互リンク URL 同期
#   1. online-store-adk (cymbal-site-adk)
#   2. store-navi customer (cymbal-store-app)
#   3. store-navi staff    (cymbal-store-staff)
#   4. data-enrichment     (cymbal-data-enrichment)
# ==============================================================================
set -euo pipefail
STEP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${STEP_DIR}/../lib/common.sh"
load_config

# URL 書き換え済みカタログが存在しない場合は生成し、各アプリのステージングに渡す
REWRITTEN_CATALOG="${STATE_DIR}/products_retail.rewritten.jsonl"
if [[ ! -s "${REWRITTEN_CATALOG}" && -s "${REPO_ROOT}/seed/catalog/products_retail.jsonl" ]]; then
  log_info "アプリ同梱用に URL 書き換え済みカタログを生成しています..."
  python3 "${INSTALL_DIR}/lib/rewrite_urls.py" \
    --src "${REPO_ROOT}/seed/catalog/products_retail.jsonl" \
    --dst "${REWRITTEN_CATALOG}" \
    --online-store-url "${ONLINE_STORE_URL}"
fi
if [[ -s "${REWRITTEN_CATALOG}" ]]; then
  export CATALOG_JSONL="${REWRITTEN_CATALOG}"
fi

# バックエンドサービスがデプロイ済みであれば実測 URL を取得して確実に連携する
MCP_LIVE="$(gcloud run services describe "${MCP_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)' 2>/dev/null || true)"
ADK_LIVE="$(gcloud run services describe "${ADK_AGENT_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)' 2>/dev/null || true)"
[[ -n "${MCP_LIVE}" ]] && export MCP_URL="${MCP_LIVE}"
[[ -n "${ADK_LIVE}" ]] && export ADK_AGENT_URL="${ADK_LIVE}"

PRED_ONLINE_URL="${ONLINE_STORE_URL}"
PRED_CUSTOMER_URL="${CUSTOMER_URL}"
PRED_STAFF_URL="${STAFF_URL}"
PRED_ENRICH_URL="${ENRICH_URL}"
PRED_FLYER_URL="${FLYER_STUDIO_URL}"
PRED_SPEC_BANNER_URL="${SPEC_BANNER_URL}"

log_info "ユーザー向け Cloud Run サービス (6 件) をデプロイします..."
printf "  - ADK オンラインストア : %-28s (予定 URL: %s)\n" "${ONLINE_STORE_SERVICE}" "${PRED_ONLINE_URL}"
printf "  - 店舗ナビ (お客様用)  : %-28s (予定 URL: %s)\n" "${STORE_APP_SERVICE}" "${PRED_CUSTOMER_URL}"
printf "  - 店舗ナビ (スタッフ用): %-28s (予定 URL: %s)\n" "${STORE_STAFF_SERVICE}" "${PRED_STAFF_URL}"
printf "  - エンリッチメント     : %-28s (予定 URL: %s)\n" "${ENRICH_SERVICE}" "${PRED_ENRICH_URL}"
printf "  - チラシ作成スタジオ   : %-28s (予定 URL: %s)\n" "${FLYER_STUDIO_SERVICE}" "${PRED_FLYER_URL}"
printf "  - 機能表・POPスタジオ  : %-28s (予定 URL: %s)\n" "${SPEC_BANNER_SERVICE}" "${PRED_SPEC_BANNER_URL}"
printf "  - 使用 Gemini モデル   : GEMINI=%s / AGENT=%s / ENRICH=%s / IMAGE=%s\n" \
  "${GEMINI_MODEL}" "${AGENT_MODEL}" "${ENRICH_GEMINI_MODEL}" "${IMAGE_MODEL}"

# 単一サービスのデプロイラッパー（allUsers が組織ポリシーで拒否された場合もサービス本体の Ready を確認して継続）
deploy_one() {
  local label="$1"
  local svc="$2"
  local log_file="${STATE_DIR}/logs/deploy_${svc}.log"
  shift 2

  log_info "[開始] ${label} (${svc}) のビルド・デプロイを開始します (ログ: ${log_file})"
  set +e
  "$@" >"${log_file}" 2>&1
  local rc=$?
  set -e

  local url=""
  local ready=""
  url="$(gcloud run services describe "${svc}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)' 2>/dev/null || true)"
  ready="$(gcloud run services describe "${svc}" --project "${PROJECT_ID}" --region "${REGION}" \
    --format="value(status.conditions.filter(type:Ready).status)" 2>/dev/null || true)"

  if [[ "${rc}" -eq 0 && -n "${url}" ]]; then
    log_ok "[完了] ${label} (${svc}) -> ${url}"
    return 0
  fi

  # allUsers 付与のみが組織ポリシーで失敗し、リビジョン自体は Ready になっているケースを救済
  if [[ -n "${url}" && "${ready}" == "True" ]] && grep -Eiq "allUsers|allowedPolicyMemberDomains|Organization Policy|FAILED_PRECONDITION" "${log_file}"; then
    log_warn "[注意] ${label} (${svc}) はデプロイ完了しましたが、組織ポリシーにより公開設定 (allUsers) のみスキップされました -> ${url}"
    return 0
  fi

  log_err "[失敗] ${label} (${svc}) のデプロイに失敗しました (rc=${rc})。ログ末尾を表示します:"
  tail -n 60 "${log_file}" >&2 || true
  return 1
}

run_online_store() {
  SERVICE_NAME="${ONLINE_STORE_SERVICE}" \
  AGENT_BACKEND="adk" \
  ADK_AGENT_URL="${ADK_AGENT_URL}" \
  ENRICH_URL="${PRED_ENRICH_URL}" \
  STORE_APP_URL="${PRED_CUSTOMER_URL}" \
  VOICE_ENABLED="${VOICE_ENABLED}" \
  BRAND_NAME="${BRAND_NAME}" \
  bash "${REPO_ROOT}/online-store-adk/deploy.sh"
}

run_store_customer() {
  SERVICE_NAME="${STORE_APP_SERVICE}" \
  APP_MODE="customer" \
  ONLINE_STORE_URL="${PRED_ONLINE_URL}" \
  ENRICH_URL="${PRED_ENRICH_URL}" \
  STAFF_URL="${PRED_STAFF_URL}" \
  CUSTOMER_URL="${PRED_CUSTOMER_URL}" \
  MCP_URL="${MCP_URL}" \
  PHOTO_BUCKET="${STORE_NAVI_BUCKET}" \
  BRAND_NAME="${BRAND_NAME}" \
  bash "${REPO_ROOT}/store-navi/deploy.sh"
}

run_store_staff() {
  SERVICE_NAME="${STORE_STAFF_SERVICE}" \
  APP_MODE="staff" \
  ONLINE_STORE_URL="${PRED_ONLINE_URL}" \
  ENRICH_URL="${PRED_ENRICH_URL}" \
  STAFF_URL="${PRED_STAFF_URL}" \
  CUSTOMER_URL="${PRED_CUSTOMER_URL}" \
  MCP_URL="${MCP_URL}" \
  PHOTO_BUCKET="${STORE_NAVI_BUCKET}" \
  BRAND_NAME="${BRAND_NAME}" \
  bash "${REPO_ROOT}/store-navi/deploy.sh"
}

run_enrichment() {
  ENRICH_SERVICE="${ENRICH_SERVICE}" \
  SERVICE_NAME="${ENRICH_SERVICE}" \
  PUBLIC_BASE_URL="${PRED_ENRICH_URL}" \
  STORE_URL="${PRED_ONLINE_URL}" \
  FLYER_URL="${PRED_FLYER_URL}" \
  IMAGE_BUCKET="${ENRICH_IMAGE_BUCKET}" \
  BQ_SOURCE_TABLE="${PROJECT_ID}.${BQ_DATASET}.products" \
  BRAND_NAME="${BRAND_NAME}" \
  bash "${REPO_ROOT}/data-enrichment/deploy.sh"
}

run_flyer_studio() {
  SERVICE_NAME="${FLYER_STUDIO_SERVICE}" \
  FLYERS_BUCKET="${FLYERS_BUCKET}" \
  STORE_URL="${PRED_ONLINE_URL}" \
  ENRICH_URL="${PRED_ENRICH_URL}" \
  GEMINI_MODEL="${GEMINI_MODEL}" \
  GEMINI_LOCATION="${GEMINI_LOCATION}" \
  bash "${REPO_ROOT}/flyer-studio/deploy.sh"
}

run_spec_banner() {
  SERVICE_NAME="${SPEC_BANNER_SERVICE}" \
  GCS_BUCKET="${SPEC_BANNER_BUCKET}" \
  BQ_DATASET="${ENRICH_BQ_DATASET}" \
  STORE_URL="${PRED_ONLINE_URL}" \
  AI_LOCATION="${GEMINI_LOCATION}" \
  bash "${REPO_ROOT}/spec-banner/deploy.sh"
}

if [[ "${PARALLEL_DEPLOY:-1}" == "1" ]]; then
  log_info "6 サービスを並列でビルド・デプロイしています（所要時間目安: 約 4〜7 分）..."
  pids=()
  deploy_one "ADK オンラインストア" "${ONLINE_STORE_SERVICE}" run_online_store & pids+=($!)
  deploy_one "店舗ナビ (お客様向け)" "${STORE_APP_SERVICE}" run_store_customer & pids+=($!)
  deploy_one "店舗ナビ (スタッフ向け)" "${STORE_STAFF_SERVICE}" run_store_staff & pids+=($!)
  deploy_one "商品情報エンリッチメント" "${ENRICH_SERVICE}" run_enrichment & pids+=($!)
  deploy_one "チラシ作成スタジオ" "${FLYER_STUDIO_SERVICE}" run_flyer_studio & pids+=($!)
  deploy_one "機能表・POPスタジオ" "${SPEC_BANNER_SERVICE}" run_spec_banner & pids+=($!)

  fail_cnt=0
  for pid in "${pids[@]}"; do
    if ! wait "${pid}"; then
      fail_cnt=$((fail_cnt + 1))
    fi
  done
  if [[ "${fail_cnt}" -gt 0 ]]; then
    log_err "${fail_cnt} 件のアプリデプロイが失敗しました。${STATE_DIR}/logs/ 内のログを確認してください。"
    exit 1
  fi
else
  deploy_one "ADK オンラインストア" "${ONLINE_STORE_SERVICE}" run_online_store
  deploy_one "店舗ナビ (お客様向け)" "${STORE_APP_SERVICE}" run_store_customer
  deploy_one "店舗ナビ (スタッフ向け)" "${STORE_STAFF_SERVICE}" run_store_staff
  deploy_one "商品情報エンリッチメント" "${ENRICH_SERVICE}" run_enrichment
  deploy_one "チラシ作成スタジオ" "${FLYER_STUDIO_SERVICE}" run_flyer_studio
  deploy_one "機能表・POPスタジオ" "${SPEC_BANNER_SERVICE}" run_spec_banner
fi

# 実測 Cloud Run URL を取得し、予測 URL と差異がある場合は相互リンク環境変数を自動更新
ACTUAL_ONLINE="$(gcloud run services describe "${ONLINE_STORE_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
ACTUAL_CUSTOMER="$(gcloud run services describe "${STORE_APP_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
ACTUAL_STAFF="$(gcloud run services describe "${STORE_STAFF_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
ACTUAL_ENRICH="$(gcloud run services describe "${ENRICH_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
ACTUAL_FLYER="$(gcloud run services describe "${FLYER_STUDIO_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
ACTUAL_SPEC_BANNER="$(gcloud run services describe "${SPEC_BANNER_SERVICE}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"

export ONLINE_STORE_URL="${ACTUAL_ONLINE}"
export STORE_URL="${ACTUAL_ONLINE}"
export CUSTOMER_URL="${ACTUAL_CUSTOMER}"
export STAFF_URL="${ACTUAL_STAFF}"
export ENRICH_URL="${ACTUAL_ENRICH}"
export FLYER_STUDIO_URL="${ACTUAL_FLYER}"
export FLYER_URL="${ACTUAL_FLYER}"
export SPEC_BANNER_URL="${ACTUAL_SPEC_BANNER}"

if [[ "${ACTUAL_ONLINE}" != "${PRED_ONLINE_URL}" || \
      "${ACTUAL_CUSTOMER}" != "${PRED_CUSTOMER_URL}" || \
      "${ACTUAL_STAFF}" != "${PRED_STAFF_URL}" || \
      "${ACTUAL_ENRICH}" != "${PRED_ENRICH_URL}" || \
      "${ACTUAL_FLYER}" != "${PRED_FLYER_URL}" || \
      "${ACTUAL_SPEC_BANNER}" != "${PRED_SPEC_BANNER_URL}" ]]; then
  log_info "実測された Cloud Run URL が予測 URL と異なるため、サービス間の相互リンク環境変数を同期しています..."
  gcloud run services update "${ONLINE_STORE_SERVICE}" \
    --project "${PROJECT_ID}" --region "${REGION}" --quiet \
    --update-env-vars "ENRICH_URL=${ACTUAL_ENRICH},STORE_APP_URL=${ACTUAL_CUSTOMER},FLYER_URL=${ACTUAL_FLYER}" >/dev/null
  gcloud run services update "${STORE_APP_SERVICE}" \
    --project "${PROJECT_ID}" --region "${REGION}" --quiet \
    --update-env-vars "ONLINE_STORE_URL=${ACTUAL_ONLINE},ENRICH_URL=${ACTUAL_ENRICH},STAFF_URL=${ACTUAL_STAFF}" >/dev/null
  gcloud run services update "${STORE_STAFF_SERVICE}" \
    --project "${PROJECT_ID}" --region "${REGION}" --quiet \
    --update-env-vars "ONLINE_STORE_URL=${ACTUAL_ONLINE},ENRICH_URL=${ACTUAL_ENRICH},CUSTOMER_URL=${ACTUAL_CUSTOMER}" >/dev/null
  gcloud run services update "${ENRICH_SERVICE}" \
    --project "${PROJECT_ID}" --region "${REGION}" --quiet \
    --update-env-vars "PUBLIC_BASE_URL=${ACTUAL_ENRICH},STORE_URL=${ACTUAL_ONLINE},FLYER_URL=${ACTUAL_FLYER}" >/dev/null
  gcloud run services update "${FLYER_STUDIO_SERVICE}" \
    --project "${PROJECT_ID}" --region "${REGION}" --quiet \
    --update-env-vars "STORE_URL=${ACTUAL_ONLINE},ENRICH_URL=${ACTUAL_ENRICH}" >/dev/null
  gcloud run services update "${SPEC_BANNER_SERVICE}" \
    --project "${PROJECT_ID}" --region "${REGION}" --quiet \
    --update-env-vars "STORE_URL=${ACTUAL_ONLINE}" >/dev/null
  log_ok "相互リンク URL の同期が完了しました。"
fi

save_urls_env
log_ok "全 6 アプリケーションのデプロイが完了しました。"
