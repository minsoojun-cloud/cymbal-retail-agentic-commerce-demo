#!/usr/bin/env bash
# カタログパイプライン:
#   shared/catalog/blueprint/*.json -> seed/catalog/products_retail.jsonl -> GCS -> BigQuery (${BQ_DATASET}.products)
#   -> Vertex AI Search for Commerce (Retail API) FULL インポート -> カスタム属性設定
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
cd "$HERE"

if [[ -z "${PROJECT_ID:-}" && -f "$REPO_ROOT/install/config.env" ]]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/install/config.env"
fi

PROJECT_ID="${PROJECT_ID:?PROJECT_ID を設定してください（例: install/config.env）}"
REGION="${REGION:-asia-northeast1}"
BQ_DATASET="${BQ_DATASET:-cymbal}"
BQ_TABLE="${BQ_TABLE:-products}"
BUCKET="${CATALOG_BUCKET:-${GCS_BUCKET:-${PROJECT_ID}-catalog}}"
CATALOG_JSONL="${CATALOG_JSONL:-$REPO_ROOT/seed/catalog/products_retail.jsonl}"
SCHEMA="$HERE/bq_schema.json"

if [[ -z "${ONLINE_STORE_URL:-}" && -z "${SITE_BASE_URL:-}" ]]; then
  PROJECT_NUMBER="${PROJECT_NUMBER:-$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')}"
  SERVICE_PREFIX="${SERVICE_PREFIX:-cymbal}"
  ONLINE_STORE_SERVICE="${ONLINE_STORE_SERVICE:-${SERVICE_PREFIX}-site-adk}"
  BASE_URL="https://${ONLINE_STORE_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
else
  BASE_URL="${ONLINE_STORE_URL:-${SITE_BASE_URL}}"
fi

python3 generate_catalog.py --out "$CATALOG_JSONL" --base-url "$BASE_URL" --brand-name "${BRAND_NAME:-Cymbal Retail}"
python3 validate_jsonl.py "$CATALOG_JSONL"

STAMP=$(date +%Y%m%d-%H%M%S)
gcloud storage cp "$CATALOG_JSONL" "gs://${BUCKET}/catalog/products_retail_${STAMP}.jsonl" --project "$PROJECT_ID"
gcloud storage cp "$CATALOG_JSONL" "gs://${BUCKET}/catalog/products_retail_latest.jsonl" --project "$PROJECT_ID"

bq --project_id "$PROJECT_ID" --location "$REGION" load --replace \
   --source_format=NEWLINE_DELIMITED_JSON \
   "${PROJECT_ID}:${BQ_DATASET}.${BQ_TABLE}" \
   "gs://${BUCKET}/catalog/products_retail_latest.jsonl" "$SCHEMA"
bq --project_id "$PROJECT_ID" query --nouse_legacy_sql \
   "SELECT a.value.text[SAFE_OFFSET(0)] top_category, COUNT(*) n
    FROM \`${PROJECT_ID}.${BQ_DATASET}.${BQ_TABLE}\` p, UNNEST(p.attributes) a
    WHERE a.key='top_category' GROUP BY 1 ORDER BY 2 DESC"

python3 retail_import.py --project "$PROJECT_ID" --dataset "$BQ_DATASET" --table "$BQ_TABLE" --bucket "$BUCKET"
python3 set_attributes_config.py --project "$PROJECT_ID"
