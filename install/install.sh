#!/usr/bin/env bash
# ==============================================================================
# install/install.sh — Cymbal Retail エージェンティック・コマース デモ 統合インストーラー
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/common.sh"

ALL_STEPS=(
  "00_preflight"
  "10_apis"
  "15_models"
  "20_iam"
  "30_retail"
  "40_data"
  "50_catalog_import"
  "60_backend"
  "70_apps"
  "80_public"
  "90_verify"
)

step_title() {
  case "$1" in
    00_preflight)      echo "事前チェック（CLI・認証・プロジェクト・課金確認）" ;;
    10_apis)           echo "Google Cloud API の有効化" ;;
    15_models)         echo "利用可能な最新 Gemini モデルの自動検出" ;;
    20_iam)            echo "ランタイム サービス アカウントと IAM ロール設定" ;;
    30_retail)         echo "Vertex AI Search for Commerce 初期設定" ;;
    40_data)           echo "GCS バケット・BigQuery シードデータの投入" ;;
    50_catalog_import) echo "Retail API 商品カタログ FULL インポート・属性設定" ;;
    60_backend)        echo "内部バックエンド (MCP / ADK エージェント) のデプロイ" ;;
    70_apps)           echo "ユーザー向け 4 アプリケーションのデプロイ" ;;
    80_public)         echo "公開アクセス確認と組織ポリシー案内" ;;
    90_verify)         echo "スモークテスト検証と URL サマリー出力" ;;
    *)                 echo "$1" ;;
  esac
}

usage() {
  cat <<'EOF'
使い方: ./install/install.sh [オプション]

Cymbal Retail エージェンティック・コマース デモ一式（バックエンド 2 サービス +
ユーザー向け 4 アプリケーション + 商品カタログ・BigQuery・GCS シードデータ）を
指定された Google Cloud プロジェクトにインストールします。

オプション:
  --project <PROJECT_ID>   デプロイ先の Google Cloud プロジェクト ID（config.env より優先）
  --region <REGION>        デプロイ先リージョン（既定値: asia-northeast1）
  --config <FILE>          読み込む設定ファイルパス（既定値: install/config.env）
  --steps <s1,s2,...>      指定したステップのみ実行（カンマ区切り、例: 70_apps,90_verify）
  --from <STEP>            指定したステップから最後まで順番に実行（例: 50_catalog_import）
  --resume                 完了済みステップ (install/.state/<step>.done) をスキップして再開
  --sequential             70_apps の 4 アプリデプロイを直列で実行（既定は並列デプロイ）
  --dry-run                設定解決と実行予定ステップの確認のみ行い、変更を加えない
  -h, --help               このヘルプを表示

利用可能なステップ一覧:
  00_preflight       事前環境・認証・課金・設定内容の検証
  10_apis            必須 Google Cloud API の有効化
  15_models          Vertex AI で利用可能な最新 Gemini モデルの自動検出
  20_iam             ランタイム サービス アカウント作成と IAM ロール付与
  30_retail          Vertex AI Search for Commerce 規約同意・Serving Config 設定
  40_data            GCS バケット・BigQuery シードデータ一式の投入
  50_catalog_import  Retail API 商品カタログ FULL インポート・属性・候補設定
  60_backend         内部バックエンド (commerce-mcp / adk-agent) のデプロイ
  70_apps            ユーザー向け 4 アプリ (ストア / 店舗ナビ×2 / エンリッチメント) のデプロイ
  80_public          公開アクセス確認と組織ポリシー制限時の Cloud Console 手順案内
  90_verify          エンドツーエンド スモークテスト実行
EOF
}

CONFIG_ARG=""
CLI_PROJECT_ID=""
CLI_REGION=""
SELECTED_STEPS=""
FROM_STEP=""
RESUME_MODE=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      [[ $# -ge 2 ]] || { log_err "--project にはプロジェクト ID を指定してください。"; exit 1; }
      CLI_PROJECT_ID="$2"; shift 2 ;;
    --project=*)
      CLI_PROJECT_ID="${1#*=}"; shift ;;
    --region)
      [[ $# -ge 2 ]] || { log_err "--region にはリージョン名を指定してください。"; exit 1; }
      CLI_REGION="$2"; shift 2 ;;
    --region=*)
      CLI_REGION="${1#*=}"; shift ;;
    --config)
      [[ $# -ge 2 ]] || { log_err "--config にはファイルパスを指定してください。"; exit 1; }
      CONFIG_ARG="$2"; shift 2 ;;
    --config=*)
      CONFIG_ARG="${1#*=}"; shift ;;
    --steps)
      [[ $# -ge 2 ]] || { log_err "--steps にはステップ名をカンマ区切りで指定してください。"; exit 1; }
      SELECTED_STEPS="$2"; shift 2 ;;
    --steps=*)
      SELECTED_STEPS="${1#*=}"; shift ;;
    --from)
      [[ $# -ge 2 ]] || { log_err "--from には開始ステップ名を指定してください。"; exit 1; }
      FROM_STEP="$2"; shift 2 ;;
    --from=*)
      FROM_STEP="${1#*=}"; shift ;;
    --resume)
      RESUME_MODE=1; shift ;;
    --sequential)
      export PARALLEL_DEPLOY=0; shift ;;
    --dry-run)
      DRY_RUN=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      log_err "不明なオプションです: $1"
      usage >&2
      exit 1 ;;
  esac
done

export CLI_PROJECT_ID CLI_REGION DRY_RUN
if [[ -n "${CONFIG_ARG}" ]]; then
  export CONFIG_FILE="${CONFIG_ARG}"
fi

if [[ -n "${SELECTED_STEPS}" && -n "${FROM_STEP}" ]]; then
  log_err "--steps と --from は同時に指定できません。"
  exit 1
fi

is_valid_step() {
  local target="$1"
  local s
  for s in "${ALL_STEPS[@]}"; do
    [[ "${s}" == "${target}" ]] && return 0
  done
  return 1
}

# 実行対象ステップリストの構築
STEPS_TO_RUN=()
if [[ -n "${SELECTED_STEPS}" ]]; then
  IFS=',' read -r -a raw_steps <<< "${SELECTED_STEPS}"
  for rs in "${raw_steps[@]}"; do
    rs="$(echo "${rs}" | tr -d '[:space:]')"
    [[ -z "${rs}" ]] && continue
    # .sh 拡張子付きで指定された場合も許容
    rs="${rs%.sh}"
    if ! is_valid_step "${rs}"; then
      log_err "存在しないステップ名です: '${rs}'"
      exit 1
    fi
    STEPS_TO_RUN+=("${rs}")
  done
elif [[ -n "${FROM_STEP}" ]]; then
  FROM_STEP="${FROM_STEP%.sh}"
  if ! is_valid_step "${FROM_STEP}"; then
    log_err "存在しない開始ステップ名です: '${FROM_STEP}'"
    exit 1
  fi
  started=0
  for s in "${ALL_STEPS[@]}"; do
    [[ "${s}" == "${FROM_STEP}" ]] && started=1
    [[ "${started}" -eq 1 ]] && STEPS_TO_RUN+=("${s}")
  done
else
  STEPS_TO_RUN=("${ALL_STEPS[@]}")
fi

load_config "${CONFIG_FILE:-${INSTALL_DIR}/config.env}"

printf "\n${C_BOLD}Cymbal Retail エージェンティック・コマース デモ インストーラー${C_RESET}\n"
log_info "対象プロジェクト: ${PROJECT_ID} (#${PROJECT_NUMBER}) / リージョン: ${REGION}"
log_info "実行予定ステップ (${#STEPS_TO_RUN[@]} 件): ${STEPS_TO_RUN[*]}"

if [[ "${DRY_RUN}" -eq 1 ]]; then
  log_info "[ドライラン] 設定内容と実行ステップ一覧を確認しました（クラウドリソースへの変更は行っていません）:"
  for s in "${STEPS_TO_RUN[@]}"; do
    status_note="実行予定"
    if [[ "${RESUME_MODE}" -eq 1 ]] && step_is_done "${s}"; then
      status_note="完了済みのためスキップ (--resume)"
    fi
    printf "  - %-20s : %s [%s]\n" "${s}" "$(step_title "${s}")" "${status_note}"
  done
  exit 0
fi

START_TS="$(date +%s)"
for step in "${STEPS_TO_RUN[@]}"; do
  if [[ "${RESUME_MODE}" -eq 1 ]] && step_is_done "${step}"; then
    log_info "ステップ '${step}' は完了済みのためスキップします (${STATE_DIR}/${step}.done)。"
    continue
  fi

  log_step "${step} — $(step_title "${step}")"
  step_script="${INSTALL_DIR}/steps/${step}.sh"
  if [[ ! -f "${step_script}" ]]; then
    log_err "ステップスクリプトが見つかりません: ${step_script}"
    exit 1
  fi

  if bash "${step_script}"; then
    mark_step_done "${step}"
    # 15_models / 60_backend / 70_apps で更新されたモデルや実測 URL を親プロセスにも再読み込み
    load_config "${CONFIG_FILE:-${INSTALL_DIR}/config.env}"
  else
    rc=$?
    log_err "ステップ '${step}' でエラーが発生しました (終了コード: ${rc})。"
    log_info "問題を解消した後、以下のコマンドで途中から再開できます:"
    log_info "  ./install/install.sh --project ${PROJECT_ID} --from ${step}"
    exit "${rc}"
  fi
done

ELAPSED=$(( $(date +%s) - START_TS ))
printf "\n${C_GREEN}==============================================================================${C_RESET}\n"
printf "${C_BOLD}🎉 インストール処理が正常に完了しました！（所要時間: %d 分 %d 秒）${C_RESET}\n" $((ELAPSED / 60)) $((ELAPSED % 60))
printf "${C_GREEN}==============================================================================${C_RESET}\n"
printf "  ADK オンラインストア           : %s\n" "${ONLINE_STORE_URL}"
printf "  店舗ナビ（お客様向けアプリ）   : %s\n" "${CUSTOMER_URL}"
printf "  店舗ナビ（スタッフ向けアプリ） : %s\n" "${STAFF_URL}"
printf "  商品情報エンリッチメント       : %s\n" "${ENRICH_URL}"
printf "  ADK AIコンシェルジュ (内部)    : %s\n" "${ADK_AGENT_URL}"
printf "  Commerce MCP サーバー (内部)   : %s\n" "${MCP_URL}"
printf "${C_GREEN}==============================================================================${C_RESET}\n"
