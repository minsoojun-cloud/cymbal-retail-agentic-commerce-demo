#!/usr/bin/env bash
# ==============================================================================
# 80_public.sh — 公開アクセス (allUsers) 状態の確認と組織ポリシー制限時のコンソール手順案内
# ※重要: 組織ポリシーの上書きや --no-invoker-iam-check 等の回避策は一切実行しません。
# ==============================================================================
set -euo pipefail
STEP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${STEP_DIR}/../lib/common.sh"
load_config

PUBLIC_SERVICES=(
  "${ONLINE_STORE_SERVICE}|${ONLINE_STORE_URL}"
  "${STORE_APP_SERVICE}|${CUSTOMER_URL}"
  "${STORE_STAFF_SERVICE}|${STAFF_URL}"
  "${ENRICH_SERVICE}|${ENRICH_URL}"
  "${FLYER_STUDIO_SERVICE}|${FLYER_STUDIO_URL}"
  "${SPEC_BANNER_SERVICE}|${SPEC_BANNER_URL}"
)

check_anon_status() {
  local url="$1"
  local code
  code="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 "${url}/api/health" 2>/dev/null || echo "000")"
  if [[ "${code}" == "404" ]]; then
    code="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 "${url}/" 2>/dev/null || echo "000")"
  fi
  echo "${code}"
}

blocked_services=()
log_info "ユーザー向け 6 サービスの匿名 HTTP アクセス状態を確認しています..."

for entry in "${PUBLIC_SERVICES[@]}"; do
  svc="${entry%%|*}"
  url="${entry#*|}"
  code="$(check_anon_status "${url}")"

  if [[ "${code}" == "200" ]]; then
    log_ok "${svc}: 公開アクセス有効 (HTTP 200)"
    continue
  fi

  # 未設定の場合は標準の add-iam-policy-binding (allUsers) を 1 回のみ試行（回避策は一切行わない）
  if [[ "${code}" == "401" || "${code}" == "403" ]]; then
    if gcloud run services add-iam-policy-binding "${svc}" \
        --project "${PROJECT_ID}" \
        --region "${REGION}" \
        --member="allUsers" \
        --role="roles/run.invoker" \
        --quiet >/dev/null 2>&1; then
      sleep 2
      code="$(check_anon_status "${url}")"
    fi
  fi

  if [[ "${code}" == "200" ]]; then
    log_ok "${svc}: 公開アクセス有効化完了 (HTTP 200)"
  elif [[ "${code}" == "401" || "${code}" == "403" ]]; then
    log_warn "${svc}: 組織ポリシーにより未認証アクセス (allUsers) が制限されています (HTTP ${code})。"
    blocked_services+=("${svc}|${url}")
  else
    log_warn "${svc}: 応答ステータス HTTP ${code} (${url}/api/health)"
  fi
done

if [[ "${#blocked_services[@]}" -gt 0 ]]; then
  printf "\n"
  printf "╔══════════════════════════════════════════════════════════════════════════════╗\n"
  printf "║ 【重要案内】Cloud Run 公開アクセスの手動有効化手順（組織ポリシー制限環境）   ║\n"
  printf "╠══════════════════════════════════════════════════════════════════════════════╣\n"
  printf "║ 組織ポリシー (iam.allowedPolicyMemberDomains 等) により CLI からの allUsers  ║\n"
  printf "║ 付与がブロックされました。本インストーラーはポリシー回避を行いません。       ║\n"
  printf "║                                                                              ║\n"
  printf "║ ■ ブラウザから一般公開アクセスを許可する場合（Cloud Console 手順）:          ║\n"
  printf "║   1. Google Cloud Console の「Cloud Run」画面を開く                          ║\n"
  printf "║   2. 下記の対象サービスを 1 つずつ選択し、「セキュリティ」タブを開く         ║\n"
  printf "║   3. 認証設定で「パブリック アクセスを許可（未認証の呼び出しを許可）」を選択 ║\n"
  printf "║   4.「保存」をクリック                                                       ║\n"
  printf "╚══════════════════════════════════════════════════════════════════════════════╝\n"
  printf "\n対象サービス（全 %d 件）:\n" "${#blocked_services[@]}"
  for entry in "${blocked_services[@]}"; do
    svc="${entry%%|*}"
    url="${entry#*|}"
    printf "  - %-26s : %s\n" "${svc}" "${url}"
    printf "    コンソール設定画面         : https://console.cloud.google.com/run/detail/%s/%s/security?project=%s\n" \
      "${REGION}" "${svc}" "${PROJECT_ID}"
  done
  printf "\n■ 公開設定を行わずに今すぐ動作確認する方法:\n"
  printf "  1) 自動スモークテスト（ID トークン認証に自動対応）:\n"
  printf "     python3 tests/smoke_install.py --config install/config.env --id-token\n\n"
  printf "  2) ローカルブラウザから安全にアクセス（Cloud Run プロキシ）:\n"
  printf "     gcloud run services proxy %s --project=%s --region=%s --port=8080\n" \
    "${ONLINE_STORE_SERVICE}" "${PROJECT_ID}" "${REGION}"
  printf "     → ブラウザで http://localhost:8080 を開く\n\n"
  printf "  3) curl での API 疎通確認:\n"
  printf "     curl -H \"Authorization: Bearer \$(gcloud auth print-identity-token)\" %s/api/health\n\n" \
    "${ONLINE_STORE_URL}"
else
  log_ok "すべてのユーザー向け Cloud Run サービスで公開アクセスが確認されました。"
fi
