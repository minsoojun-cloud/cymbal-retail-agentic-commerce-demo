#!/usr/bin/env bash
# ==============================================================================
# 15_models.sh — Vertex AI で利用可能な最新 Gemini モデルの自動検出
# ==============================================================================
set -euo pipefail
STEP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${STEP_DIR}/../lib/common.sh"
load_config

log_info "Vertex AI (${GEMINI_LOCATION}) に対して最新の利用可能 Gemini モデルを検出しています..."
python3 "${INSTALL_DIR}/lib/probe_models.py" \
  --project "${PROJECT_ID}" \
  --location "${GEMINI_LOCATION}" \
  --out "${STATE_DIR}/models.env"

reload_models_env

log_info "有効なモデル設定（install/config.env の明示指定がある場合はそちらを優先）:"
printf "  - GEMINI_MODEL        : %s\n" "${GEMINI_MODEL}"
printf "  - AGENT_MODEL         : %s\n" "${AGENT_MODEL}"
printf "  - ENRICH_GEMINI_MODEL : %s\n" "${ENRICH_GEMINI_MODEL}"
printf "  - IMAGE_MODEL         : %s\n" "${IMAGE_MODEL}"
log_ok "Gemini モデルの自動検出が完了しました。"
