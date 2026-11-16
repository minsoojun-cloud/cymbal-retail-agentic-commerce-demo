#!/usr/bin/env bash
# ペルソナおよび購買履歴データを BigQuery (${PROJECT_ID}:${BQ_DATASET}) にロードするスクリプト。
# 使い方:
#   ./load_to_bq.sh [--products <catalog.jsonl> | --regenerate]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../.." && pwd)"

if [ -d "${HOME}/google-cloud-sdk/bin" ]; then
  export PATH="${HOME}/google-cloud-sdk/bin:${PATH}"
fi

if [ -z "${PROJECT_ID:-}" ] && [ -f "${REPO_ROOT}/install/config.env" ]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/install/config.env"
fi

PROJECT_ID="${PROJECT_ID:?環境変数 PROJECT_ID を設定するか install/config.env を作成してください}"
BQ_DATASET="${BQ_DATASET:-cymbal}"
LOC="${REGION:-asia-northeast1}"
CATALOG_JSONL="${CATALOG_JSONL:-${REPO_ROOT}/seed/catalog/products_retail.jsonl}"
DS="${PROJECT_ID}:${BQ_DATASET}"

if [ "${1:-}" = "--products" ]; then
  CATALOG_JSONL="${2:?--products にはカタログ JSONL のパスを指定してください}"
  python3 "${HERE}/generate_history.py" --products "${CATALOG_JSONL}" --out "${HERE}/purchase_history.jsonl"
elif [ "${1:-}" = "--regenerate" ]; then
  python3 "${HERE}/generate_history.py" --products "${CATALOG_JSONL}" --out "${HERE}/purchase_history.jsonl"
fi

if [ ! -f "${HERE}/purchase_history.jsonl" ]; then
  echo "エラー: purchase_history.jsonl が見つかりません（--regenerate または --products <catalog.jsonl> を指定して実行してください）" >&2
  exit 1
fi

bq --project_id="${PROJECT_ID}" --location="${LOC}" show "${DS}" >/dev/null 2>&1 || \
  bq --project_id="${PROJECT_ID}" --location="${LOC}" mk --dataset "${DS}"

# customers: personas.json (JSON 配列) -> NDJSON 変換（完全な構造を保持するため profile_json 列も付与）
TMP_FULL="$(mktemp "${TMPDIR:-/tmp}/cr_customers_XXXXXX.jsonl")"
TMP_SLIM="$(mktemp "${TMPDIR:-/tmp}/cr_customers_slim_XXXXXX.jsonl")"
trap 'rm -f "${TMP_FULL}" "${TMP_SLIM}"' EXIT

python3 - "${HERE}/personas.json" "${TMP_FULL}" "${TMP_SLIM}" <<'PY'
import json, sys
personas = json.load(open(sys.argv[1], encoding="utf-8"))
with open(sys.argv[2], "w", encoding="utf-8") as full, open(sys.argv[3], "w", encoding="utf-8") as slim:
    for p in personas:
        pj = json.dumps(p, ensure_ascii=False)
        full.write(json.dumps({**p, "profile_json": pj}, ensure_ascii=False) + "\n")
        slim.write(json.dumps({"customer_id": p["customer_id"], "name": p.get("name", ""),
                               "household_size": p.get("household_size"), "profile_json": pj}, ensure_ascii=False) + "\n")
PY

if ! bq --project_id="${PROJECT_ID}" --location="${LOC}" load --replace --autodetect --source_format=NEWLINE_DELIMITED_JSON \
  "${DS}.customers" "${TMP_FULL}"; then
  echo "自動スキーマ検出でのロードに失敗したため、最小スキーマで再ロードします" >&2
  bq --project_id="${PROJECT_ID}" --location="${LOC}" load --replace --source_format=NEWLINE_DELIMITED_JSON \
    "${DS}.customers" "${TMP_SLIM}" \
    customer_id:STRING,name:STRING,household_size:INT64,profile_json:STRING
fi

bq --project_id="${PROJECT_ID}" --location="${LOC}" load --replace --source_format=NEWLINE_DELIMITED_JSON \
  "${DS}.purchase_history" "${HERE}/purchase_history.jsonl" \
  order_id:STRING,customer_id:STRING,order_date:DATE,product_id:STRING,product_title:STRING,category:STRING,quantity:INT64,unit_price_tax_included:INT64,amount:INT64

# MCP サーバーのローカルフォールバック用コピー（ディレクトリが存在する場合のみ更新）
MCP_DATA_DIR="${MCP_DATA_DIR:-${REPO_ROOT}/shared/mcp_server/data}"
if [ -d "$(dirname "${MCP_DATA_DIR}")" ]; then
  mkdir -p "${MCP_DATA_DIR}"
  cp "${HERE}/personas.json" "${HERE}/purchase_history.jsonl" "${MCP_DATA_DIR}/"
fi

bq --project_id="${PROJECT_ID}" --location="${LOC}" query --use_legacy_sql=false --format=pretty \
  "SELECT FORMAT_DATE('%Y-%m', order_date) ym, COUNT(DISTINCT order_id) orders, COUNT(*) rows_, SUM(amount) amount
   FROM \`${PROJECT_ID}.${BQ_DATASET}.purchase_history\` GROUP BY ym ORDER BY ym"
