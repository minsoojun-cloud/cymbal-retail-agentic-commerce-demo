#!/usr/bin/env bash
# ==============================================================================
# install/uninstall.sh — デプロイ済みリソースの削除（アンインストール）スクリプト
# 既定では 6 つの Cloud Run サービスのみ削除します。
# --purge-data を指定した場合のみ、確認の上で BigQuery データセットと GCS バケットも削除します。
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/common.sh"

usage() {
  cat <<'EOF'
使い方: ./install/uninstall.sh [オプション]

対象プロジェクトにデプロイした Cymbal Retail デモの Cloud Run サービス（6 件）を削除します。

オプション:
  --project <PROJECT_ID>   対象の Google Cloud プロジェクト ID
  --region <REGION>        対象リージョン（既定値: asia-northeast1）
  --config <FILE>          設定ファイルパス（既定値: install/config.env）
  --purge-data             BigQuery データセット（2 件）と Cloud Storage バケット（3 件）も完全削除
  --delete-sa              ランタイム サービス アカウントも削除
  --yes                    確認プロンプトを省略して実行
  -h, --help               このヘルプを表示
EOF
}

CONFIG_ARG=""
CLI_PROJECT_ID=""
CLI_REGION=""
PURGE_DATA=0
DELETE_SA=0
ASSUME_YES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)     CLI_PROJECT_ID="${2:?}"; shift 2 ;;
    --project=*)   CLI_PROJECT_ID="${1#*=}"; shift ;;
    --region)      CLI_REGION="${2:?}"; shift 2 ;;
    --region=*)    CLI_REGION="${1#*=}"; shift ;;
    --config)      CONFIG_ARG="${2:?}"; shift 2 ;;
    --config=*)    CONFIG_ARG="${1#*=}"; shift ;;
    --purge-data)  PURGE_DATA=1; shift ;;
    --delete-sa)   DELETE_SA=1; shift ;;
    --yes|-y)      ASSUME_YES=1; shift ;;
    -h|--help)     usage; exit 0 ;;
    *)             log_err "不明なオプションです: $1"; usage >&2; exit 1 ;;
  esac
done

export CLI_PROJECT_ID CLI_REGION
[[ -n "${CONFIG_ARG}" ]] && export CONFIG_FILE="${CONFIG_ARG}"
load_config "${CONFIG_FILE:-${INSTALL_DIR}/config.env}"

SERVICES=(
  "${ONLINE_STORE_SERVICE}"
  "${STORE_APP_SERVICE}"
  "${STORE_STAFF_SERVICE}"
  "${ENRICH_SERVICE}"
  "${ADK_AGENT_SERVICE}"
  "${MCP_SERVICE}"
)

printf "\n${C_YELLOW}==============================================================================${C_RESET}\n"
printf "${C_BOLD}⚠️  Cymbal Retail デモ アンインストール確認${C_RESET}\n"
printf "${C_YELLOW}==============================================================================${C_RESET}\n"
printf "対象プロジェクト : %s\n" "${PROJECT_ID}"
printf "対象リージョン   : %s\n" "${REGION}"
printf "削除される Cloud Run サービス:\n"
for svc in "${SERVICES[@]}"; do
  printf "  - %s\n" "${svc}"
done

if [[ "${PURGE_DATA}" -eq 1 ]]; then
  printf "\n${C_RED}[--purge-data 指定あり] 以下のデータセットおよびバケットも完全に削除されます:${C_RESET}\n"
  printf "  - BigQuery データセット : %s:%s\n" "${PROJECT_ID}" "${BQ_DATASET}"
  printf "  - BigQuery データセット : %s:%s\n" "${PROJECT_ID}" "${ENRICH_BQ_DATASET}"
  printf "  - GCS バケット          : gs://%s\n" "${CATALOG_BUCKET}"
  printf "  - GCS バケット          : gs://%s\n" "${STORE_NAVI_BUCKET}"
  printf "  - GCS バケット          : gs://%s\n" "${ENRICH_IMAGE_BUCKET}"
fi

if [[ "${DELETE_SA}" -eq 1 ]]; then
  printf "\n[--delete-sa 指定あり] ランタイム サービス アカウントも削除されます:\n"
  printf "  - %s\n" "${RUNTIME_SA}"
fi
printf "${C_YELLOW}==============================================================================${C_RESET}\n"

if [[ "${ASSUME_YES}" -ne 1 ]]; then
  read -r -p "本当に削除を実行しますか？ 続行するにはプロジェクト ID (${PROJECT_ID}) を入力してください: " confirm_proj
  if [[ "${confirm_proj}" != "${PROJECT_ID}" ]]; then
    log_info "入力が一致しなかったため、アンインストールを中止しました。"
    exit 0
  fi
fi

# 1. Cloud Run サービス 6 件の削除
log_info "Cloud Run サービスを削除しています..."
for svc in "${SERVICES[@]}"; do
  if gcloud run services describe "${svc}" --project "${PROJECT_ID}" --region "${REGION}" >/dev/null 2>&1; then
    gcloud run services delete "${svc}" --project "${PROJECT_ID}" --region "${REGION}" --quiet
    log_ok "Cloud Run サービス削除完了: ${svc}"
  else
    log_info "存在しないためスキップ: ${svc}"
  fi
done

# 2. データ完全削除 (--purge-data 指定時のみ)
if [[ "${PURGE_DATA}" -eq 1 ]]; then
  log_info "BigQuery データセットを削除しています..."
  for ds in "${BQ_DATASET}" "${ENRICH_BQ_DATASET}"; do
    if bq --project_id="${PROJECT_ID}" show "${PROJECT_ID}:${ds}" >/dev/null 2>&1; then
      bq --project_id="${PROJECT_ID}" rm -r -f -d "${PROJECT_ID}:${ds}"
      log_ok "BigQuery データセット削除完了: ${PROJECT_ID}:${ds}"
    else
      log_info "存在しないためスキップ: ${PROJECT_ID}:${ds}"
    fi
  done

  log_info "Cloud Storage バケットを削除しています..."
  for bkt in "${CATALOG_BUCKET}" "${STORE_NAVI_BUCKET}" "${ENRICH_IMAGE_BUCKET}"; do
    if gcloud storage buckets describe "gs://${bkt}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
      gcloud storage rm --recursive "gs://${bkt}" --project "${PROJECT_ID}" --quiet
      log_ok "GCS バケット削除完了: gs://${bkt}"
    else
      log_info "存在しないためスキップ: gs://${bkt}"
    fi
  done
fi

# 3. ランタイム SA の削除 (--delete-sa 指定時のみ)
if [[ "${DELETE_SA}" -eq 1 ]]; then
  if gcloud iam service-accounts describe "${RUNTIME_SA}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
    gcloud iam service-accounts delete "${RUNTIME_SA}" --project "${PROJECT_ID}" --quiet
    log_ok "サービス アカウント削除完了: ${RUNTIME_SA}"
  fi
fi

# ステップ完了状態のクリア
rm -rf "${STATE_DIR}"
log_ok "アンインストール処理が完了しました。"
