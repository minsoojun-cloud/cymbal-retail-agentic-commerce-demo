#!/usr/bin/env bash
# ==============================================================================
# Cymbal Retail インストーラー共通ライブラリ (common.sh)
# 設定ファイルの読み込み・環境変数の解決・ログ出力・ステップ状態管理を提供します。
# ==============================================================================

if [[ -n "${_CYMBAL_COMMON_LOADED:-}" ]]; then
  return 0 2>/dev/null || true
fi
_CYMBAL_COMMON_LOADED=1

# Google Cloud SDK / uv の標準インストールパスを補完
if [[ -d "${HOME}/google-cloud-sdk/bin" && ":${PATH}:" != *":${HOME}/google-cloud-sdk/bin:"* ]]; then
  export PATH="${HOME}/google-cloud-sdk/bin:${PATH}"
fi
if [[ -d "${HOME}/.local/bin" && ":${PATH}:" != *":${HOME}/.local/bin:"* ]]; then
  export PATH="${HOME}/.local/bin:${PATH}"
fi
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

# リポジトリ・インストーラーのパス解決
INSTALL_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(cd "${INSTALL_LIB_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${INSTALL_DIR}/.." && pwd)"
STATE_DIR="${INSTALL_DIR}/.state"
mkdir -p "${STATE_DIR}" "${STATE_DIR}/logs"
export REPO_ROOT INSTALL_DIR STATE_DIR

# カラー定義（端末出力時のみ有効）
if [[ -t 1 ]]; then
  C_RESET='\033[0m'
  C_BOLD='\033[1m'
  C_BLUE='\033[1;34m'
  C_GREEN='\033[1;32m'
  C_YELLOW='\033[1;33m'
  C_RED='\033[1;31m'
  C_CYAN='\033[0;36m'
else
  C_RESET='' C_BOLD='' C_BLUE='' C_GREEN='' C_YELLOW='' C_RED='' C_CYAN=''
fi

# ログ出力ヘルパー（すべて日本語）
log_info() { printf "${C_CYAN}[情報]${C_RESET} %s\n" "$*"; }
log_ok()   { printf "${C_GREEN}[完了]${C_RESET} %s\n" "$*"; }
log_warn() { printf "${C_YELLOW}[警告]${C_RESET} %s\n" "$*" >&2; }
log_err()  { printf "${C_RED}[エラー]${C_RESET} %s\n" "$*" >&2; }
log_step() {
  printf "\n${C_BLUE}==============================================================================${C_RESET}\n"
  printf "${C_BOLD}▶ ステップ: %s${C_RESET}\n" "$*"
  printf "${C_BLUE}==============================================================================${C_RESET}\n"
}

# ステップ完了状態の管理 (install/.state/<step>.done)
step_is_done() {
  local step="$1"
  [[ -f "${STATE_DIR}/${step}.done" ]]
}

mark_step_done() {
  local step="$1"
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "${STATE_DIR}/${step}.done"
}

clear_step_done() {
  local step="$1"
  rm -f "${STATE_DIR}/${step}.done"
}

# プロジェクト番号の解決（キャッシュ対応）
resolve_project_number() {
  if [[ -n "${PROJECT_NUMBER:-}" ]]; then
    return 0
  fi
  local cache_file="${STATE_DIR}/project_number.${PROJECT_ID}"
  if [[ -s "${cache_file}" ]]; then
    PROJECT_NUMBER="$(cat "${cache_file}")"
    export PROJECT_NUMBER
    return 0
  fi
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    # ドライラン時は gcloud 呼び出しに失敗しても仮番号で継続可能にする
    PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)' 2>/dev/null || echo '000000000000')"
    export PROJECT_NUMBER
    return 0
  fi
  if ! PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)' 2>/dev/null)" || [[ -z "${PROJECT_NUMBER}" ]]; then
    log_err "プロジェクト '${PROJECT_ID}' のプロジェクト番号を取得できませんでした。プロジェクト ID と閲覧権限を確認してください。"
    return 1
  fi
  printf '%s' "${PROJECT_NUMBER}" > "${cache_file}"
  export PROJECT_NUMBER
}

# 設定ファイル・自動検出モデル・URL の読み込みと正規環境変数のエクスポート
load_config() {
  local cfg_file="${1:-${CONFIG_FILE:-${INSTALL_DIR}/config.env}}"
  local cli_project="${CLI_PROJECT_ID:-}"
  local cli_region="${CLI_REGION:-}"

  # 呼び出し元環境で明示指定されたモデル・URL があれば退避
  local env_gemini="${GEMINI_MODEL:-}"
  local env_agent="${AGENT_MODEL:-}"
  local env_enrich_model="${ENRICH_GEMINI_MODEL:-}"
  local env_image="${IMAGE_MODEL:-}"

  if [[ -f "${cfg_file}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${cfg_file}"
    set +a
    CONFIG_FILE="${cfg_file}"
    export CONFIG_FILE
  elif [[ "${cfg_file}" != "${INSTALL_DIR}/config.env" ]]; then
    log_err "指定された設定ファイルが見つかりません: ${cfg_file}"
    return 1
  fi

  # CLI 引数による上書きを最優先
  [[ -n "${cli_project}" ]] && PROJECT_ID="${cli_project}"
  [[ -n "${cli_region}" ]] && REGION="${cli_region}"

  if [[ -z "${PROJECT_ID:-}" ]]; then
    log_err "PROJECT_ID が設定されていません。install/config.env に設定するか、--project <PROJECT_ID> を指定してください。"
    log_info "例: cp install/config.example.env install/config.env && vi install/config.env"
    return 1
  fi

  # PROJECT_ID 形式の簡易検証
  if [[ ! "${PROJECT_ID}" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]]; then
    log_err "PROJECT_ID の形式が不正です: '${PROJECT_ID}'"
    return 1
  fi

  # config.env で明示指定されたモデル設定を保持
  local cfg_gemini="${env_gemini:-${GEMINI_MODEL:-}}"
  local cfg_agent="${env_agent:-${AGENT_MODEL:-}}"
  local cfg_enrich_model="${env_enrich_model:-${ENRICH_GEMINI_MODEL:-}}"
  local cfg_image="${env_image:-${IMAGE_MODEL:-}}"

  # 自動検出済みモデル (install/.state/models.env) があれば読み込み
  if [[ -f "${STATE_DIR}/models.env" ]]; then
    # shellcheck disable=SC1091
    source "${STATE_DIR}/models.env"
  fi

  # 明示指定があれば自動検出値より優先
  [[ -n "${cfg_gemini}" ]] && GEMINI_MODEL="${cfg_gemini}"
  [[ -n "${cfg_agent}" ]] && AGENT_MODEL="${cfg_agent}"
  [[ -n "${cfg_enrich_model}" ]] && ENRICH_GEMINI_MODEL="${cfg_enrich_model}"
  [[ -n "${cfg_image}" ]] && IMAGE_MODEL="${cfg_image}"

  # モデル未検出時の安全なフォールバック値
  GEMINI_MODEL="${GEMINI_MODEL:-gemini-3-flash-preview}"
  AGENT_MODEL="${AGENT_MODEL:-${GEMINI_MODEL}}"
  ENRICH_GEMINI_MODEL="${ENRICH_GEMINI_MODEL:-${GEMINI_MODEL}}"
  IMAGE_MODEL="${IMAGE_MODEL:-gemini-2.5-flash-image}"

  # 基本設定の既定値
  REGION="${REGION:-asia-northeast1}"
  GEMINI_LOCATION="${GEMINI_LOCATION:-global}"
  SERVICE_PREFIX="${SERVICE_PREFIX:-cymbal}"
  RUNTIME_SA_NAME="${RUNTIME_SA_NAME:-${SERVICE_PREFIX}-runtime}"
  RUNTIME_SA="${RUNTIME_SA:-${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com}"

  # BigQuery データセット
  BQ_DATASET="${BQ_DATASET:-cymbal}"
  ENRICH_BQ_DATASET="${ENRICH_BQ_DATASET:-cymbal_enrichment}"

  # Cloud Storage バケット（空文字の場合も既定値を設定）
  CATALOG_BUCKET="${CATALOG_BUCKET:-${PROJECT_ID}-catalog}"
  STORE_NAVI_BUCKET="${STORE_NAVI_BUCKET:-${PROJECT_ID}-store-navi}"
  ENRICH_IMAGE_BUCKET="${ENRICH_IMAGE_BUCKET:-products_images_${PROJECT_ID}}"
  FLYERS_BUCKET="${FLYERS_BUCKET:-${PROJECT_ID}-flyers}"
  SPEC_BANNER_BUCKET="${SPEC_BANNER_BUCKET:-${PROJECT_ID}-spec-banner}"
  # 各アプリの deploy.sh との互換エイリアス
  GCS_BUCKET="${GCS_BUCKET:-${CATALOG_BUCKET}}"
  PHOTO_BUCKET="${PHOTO_BUCKET:-${STORE_NAVI_BUCKET}}"
  IMAGE_BUCKET="${IMAGE_BUCKET:-${ENRICH_IMAGE_BUCKET}}"

  # Cloud Run サービス名
  MCP_SERVICE="${MCP_SERVICE:-${SERVICE_PREFIX}-commerce-mcp}"
  ADK_AGENT_SERVICE="${ADK_AGENT_SERVICE:-${SERVICE_PREFIX}-adk-agent}"
  ADK_SERVICE="${ADK_SERVICE:-${ADK_AGENT_SERVICE}}"
  ONLINE_STORE_SERVICE="${ONLINE_STORE_SERVICE:-${SERVICE_PREFIX}-site-adk}"
  STORE_APP_SERVICE="${STORE_APP_SERVICE:-${SERVICE_PREFIX}-store-app}"
  STORE_STAFF_SERVICE="${STORE_STAFF_SERVICE:-${SERVICE_PREFIX}-store-staff}"
  ENRICH_SERVICE="${ENRICH_SERVICE:-${SERVICE_PREFIX}-data-enrichment}"
  SPEC_BANNER_SERVICE="${SPEC_BANNER_SERVICE:-${SERVICE_PREFIX}-spec-banner}"
  FLYER_STUDIO_SERVICE="${FLYER_STUDIO_SERVICE:-${SERVICE_PREFIX}-flyer-studio}"

  # プロジェクト番号の解決
  resolve_project_number || return 1

  # Cloud Run の決定論的 URL 算出 (https://<service>-${PROJECT_NUMBER}.${REGION}.run.app)
  local url_suffix="${PROJECT_NUMBER}.${REGION}.run.app"
  local cfg_mcp_url="${MCP_URL:-}"
  local cfg_adk_url="${ADK_AGENT_URL:-}"
  local cfg_online_url="${ONLINE_STORE_URL:-}"
  local cfg_store_url="${STORE_URL:-}"
  local cfg_staff_url="${STAFF_URL:-}"
  local cfg_customer_url="${CUSTOMER_URL:-}"
  local cfg_enrich_url="${ENRICH_URL:-}"
  local cfg_spec_banner_url="${SPEC_BANNER_URL:-}"
  local cfg_flyer_url="${FLYER_STUDIO_URL:-${FLYER_URL:-}}"

  # デプロイ後に実測 URL が保存されていれば反映（同一プロジェクト・リージョンの場合のみ）
  if [[ -f "${STATE_DIR}/urls.env" ]]; then
    # shellcheck disable=SC1091
    source "${STATE_DIR}/urls.env"
    if [[ "${URLS_PROJECT_ID:-}" != "${PROJECT_ID}" || "${URLS_REGION:-}" != "${REGION}" ]]; then
      unset MCP_URL ADK_AGENT_URL ONLINE_STORE_URL STORE_URL STAFF_URL CUSTOMER_URL ENRICH_URL SPEC_BANNER_URL FLYER_STUDIO_URL FLYER_URL
    fi
  fi

  [[ -n "${cfg_mcp_url}" ]] && MCP_URL="${cfg_mcp_url}"
  [[ -n "${cfg_adk_url}" ]] && ADK_AGENT_URL="${cfg_adk_url}"
  [[ -n "${cfg_online_url}" ]] && ONLINE_STORE_URL="${cfg_online_url}"
  [[ -n "${cfg_store_url}" ]] && STORE_URL="${cfg_store_url}"
  [[ -n "${cfg_staff_url}" ]] && STAFF_URL="${cfg_staff_url}"
  [[ -n "${cfg_customer_url}" ]] && CUSTOMER_URL="${cfg_customer_url}"
  [[ -n "${cfg_enrich_url}" ]] && ENRICH_URL="${cfg_enrich_url}"
  [[ -n "${cfg_spec_banner_url}" ]] && SPEC_BANNER_URL="${cfg_spec_banner_url}"
  [[ -n "${cfg_flyer_url}" ]] && FLYER_STUDIO_URL="${cfg_flyer_url}"

  MCP_URL="${MCP_URL:-https://${MCP_SERVICE}-${url_suffix}}"
  ADK_AGENT_URL="${ADK_AGENT_URL:-https://${ADK_AGENT_SERVICE}-${url_suffix}}"
  ONLINE_STORE_URL="${ONLINE_STORE_URL:-https://${ONLINE_STORE_SERVICE}-${url_suffix}}"
  STORE_URL="${STORE_URL:-${ONLINE_STORE_URL}}"
  STAFF_URL="${STAFF_URL:-https://${STORE_STAFF_SERVICE}-${url_suffix}}"
  CUSTOMER_URL="${CUSTOMER_URL:-https://${STORE_APP_SERVICE}-${url_suffix}}"
  ENRICH_URL="${ENRICH_URL:-https://${ENRICH_SERVICE}-${url_suffix}}"
  SPEC_BANNER_URL="${SPEC_BANNER_URL:-https://${SPEC_BANNER_SERVICE}-${url_suffix}}"
  FLYER_STUDIO_URL="${FLYER_STUDIO_URL:-https://${FLYER_STUDIO_SERVICE}-${url_suffix}}"
  FLYER_URL="${FLYER_URL:-${FLYER_STUDIO_URL}}"

  # 機能フラグ・ブランド設定
  VOICE_ENABLED="${VOICE_ENABLED:-1}"
  BRAND_NAME="${BRAND_NAME:-Cymbal Retail}"

  # シード・アセットの標準パス解決（URL 書き換え済みカタログが存在する場合はそちらを優先）
  if [[ -z "${CATALOG_JSONL:-}" ]]; then
    if [[ -s "${STATE_DIR}/products_retail.rewritten.jsonl" ]]; then
      CATALOG_JSONL="${STATE_DIR}/products_retail.rewritten.jsonl"
    else
      CATALOG_JSONL="${REPO_ROOT}/seed/catalog/products_retail.jsonl"
    fi
  fi
  AUTOCOMPLETE_JSONL="${AUTOCOMPLETE_JSONL:-${REPO_ROOT}/seed/catalog/autocomplete_suggestions.jsonl}"
  PERSONAS_DIR="${PERSONAS_DIR:-${REPO_ROOT}/seed/personas}"
  PRODUCT_IMAGES_DIR="${PRODUCT_IMAGES_DIR:-${REPO_ROOT}/online-store-adk/static/img/products}"

  export PROJECT_ID PROJECT_NUMBER REGION GEMINI_LOCATION SERVICE_PREFIX
  export RUNTIME_SA_NAME RUNTIME_SA
  export BQ_DATASET ENRICH_BQ_DATASET
  export CATALOG_BUCKET STORE_NAVI_BUCKET ENRICH_IMAGE_BUCKET FLYERS_BUCKET SPEC_BANNER_BUCKET GCS_BUCKET PHOTO_BUCKET IMAGE_BUCKET
  export MCP_SERVICE ADK_AGENT_SERVICE ADK_SERVICE ONLINE_STORE_SERVICE STORE_APP_SERVICE STORE_STAFF_SERVICE ENRICH_SERVICE SPEC_BANNER_SERVICE FLYER_STUDIO_SERVICE
  export MCP_URL ADK_AGENT_URL ONLINE_STORE_URL STORE_URL STAFF_URL CUSTOMER_URL ENRICH_URL SPEC_BANNER_URL FLYER_STUDIO_URL FLYER_URL
  export GEMINI_MODEL AGENT_MODEL ENRICH_GEMINI_MODEL IMAGE_MODEL
  export VOICE_ENABLED BRAND_NAME
  export CATALOG_JSONL AUTOCOMPLETE_JSONL PERSONAS_DIR PRODUCT_IMAGES_DIR
}

# 自動検出済みモデル設定の再読み込み（15_models 実行直後用）
reload_models_env() {
  if [[ -f "${STATE_DIR}/models.env" ]]; then
    local explicit_gemini="" explicit_agent="" explicit_enrich="" explicit_image=""
    if [[ -n "${CONFIG_FILE:-}" && -f "${CONFIG_FILE}" ]]; then
      explicit_gemini="$(bash -c "source '${CONFIG_FILE}' >/dev/null 2>&1; printf '%s' \"\${GEMINI_MODEL:-}\"")"
      explicit_agent="$(bash -c "source '${CONFIG_FILE}' >/dev/null 2>&1; printf '%s' \"\${AGENT_MODEL:-}\"")"
      explicit_enrich="$(bash -c "source '${CONFIG_FILE}' >/dev/null 2>&1; printf '%s' \"\${ENRICH_GEMINI_MODEL:-}\"")"
      explicit_image="$(bash -c "source '${CONFIG_FILE}' >/dev/null 2>&1; printf '%s' \"\${IMAGE_MODEL:-}\"")"
    fi
    # shellcheck disable=SC1091
    source "${STATE_DIR}/models.env"
    [[ -n "${explicit_gemini}" ]] && GEMINI_MODEL="${explicit_gemini}"
    [[ -n "${explicit_agent}" ]] && AGENT_MODEL="${explicit_agent}"
    [[ -n "${explicit_enrich}" ]] && ENRICH_GEMINI_MODEL="${explicit_enrich}"
    [[ -n "${explicit_image}" ]] && IMAGE_MODEL="${explicit_image}"
    export GEMINI_MODEL AGENT_MODEL ENRICH_GEMINI_MODEL IMAGE_MODEL
  fi
}

# Cloud Run 実測 URL の保存
save_urls_env() {
  cat > "${STATE_DIR}/urls.env" <<EOF
# デプロイ済み Cloud Run サービスの実測 URL（自動生成）
URLS_PROJECT_ID="${PROJECT_ID}"
URLS_REGION="${REGION}"
MCP_URL="${MCP_URL}"
ADK_AGENT_URL="${ADK_AGENT_URL}"
ONLINE_STORE_URL="${ONLINE_STORE_URL}"
STORE_URL="${STORE_URL}"
STAFF_URL="${STAFF_URL}"
CUSTOMER_URL="${CUSTOMER_URL}"
ENRICH_URL="${ENRICH_URL}"
SPEC_BANNER_URL="${SPEC_BANNER_URL}"
FLYER_STUDIO_URL="${FLYER_STUDIO_URL}"
FLYER_URL="${FLYER_URL}"
EOF
}
