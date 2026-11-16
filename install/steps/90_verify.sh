#!/usr/bin/env bash
# ==============================================================================
# 90_verify.sh — エンドツーエンド スモークテスト (smoke_install.py) の実行と URL 一覧出力
# ==============================================================================
set -euo pipefail
STEP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${STEP_DIR}/../lib/common.sh"
load_config

log_info "デプロイ済み環境の総合スモークテスト (tests/smoke_install.py) を実行しています..."
CMD=(python3 "${REPO_ROOT}/tests/smoke_install.py")
if [[ -n "${CONFIG_FILE:-}" && -f "${CONFIG_FILE}" ]]; then
  CMD+=(--config "${CONFIG_FILE}")
fi
CMD+=(--project "${PROJECT_ID}" --region "${REGION}")

"${CMD[@]}"
log_ok "すべてのスモークテスト検証が完了しました。"
