#!/usr/bin/env bash
# ==============================================================================
# 50_catalog_import.sh — Retail API への商品カタログ FULL インポート・属性設定・オートコンプリート設定
# ==============================================================================
set -euo pipefail
STEP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${STEP_DIR}/../lib/common.sh"
load_config

REWRITTEN_CATALOG="${STATE_DIR}/products_retail.rewritten.jsonl"
if [[ ! -s "${REWRITTEN_CATALOG}" ]]; then
  log_info "URL 書き換え済みカタログを生成しています..."
  python3 "${INSTALL_DIR}/lib/rewrite_urls.py" \
    --src "${REPO_ROOT}/seed/catalog/products_retail.jsonl" \
    --dst "${REWRITTEN_CATALOG}" \
    --online-store-url "${ONLINE_STORE_URL}"
fi

# 1. GCS カタログバケットへアップロード
gcloud storage buckets describe "gs://${CATALOG_BUCKET}" --project "${PROJECT_ID}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${CATALOG_BUCKET}" --project "${PROJECT_ID}" --location "${REGION}" --uniform-bucket-level-access

STAMP="$(date +%Y%m%d-%H%M%S)"
log_info "書き換え済みカタログを gs://${CATALOG_BUCKET}/catalog/ にアップロードしています..."
gcloud storage cp "${REWRITTEN_CATALOG}" "gs://${CATALOG_BUCKET}/catalog/products_retail_${STAMP}.jsonl" --project "${PROJECT_ID}" --quiet
gcloud storage cp "${REWRITTEN_CATALOG}" "gs://${CATALOG_BUCKET}/catalog/products_retail_latest.jsonl" --project "${PROJECT_ID}" --quiet

# 2. Retail API ブランチ 0 へ FULL リコンシリエーション インポートを実行し完了までポーリング
log_info "Vertex AI Search for Commerce (branch 0) へ商品カタログを FULL インポートしています（完了まで数分かかります）..."
python3 - "${PROJECT_ID}" "${BQ_DATASET}" "${CATALOG_BUCKET}" <<'PY'
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

project_id, bq_dataset, catalog_bucket = sys.argv[1], sys.argv[2], sys.argv[3]


def get_token() -> str:
    return subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()


def call(method: str, url: str, body=None) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={
            "Authorization": f"Bearer {get_token()}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": project_id,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw[:600]}


base_url = f"https://retail.googleapis.com/v2alpha/projects/{project_id}/locations/global/catalogs/default_catalog"
import_url = f"{base_url}/branches/0/products:import"

# BigQuery テーブルが存在する場合は bigQuerySource、未ロードの場合は gcsSource を使用
bq_chk = subprocess.run(
    ["bq", f"--project_id={project_id}", "show", f"{project_id}:{bq_dataset}.products"],
    capture_output=True,
    text=True,
)
if bq_chk.returncode == 0:
    input_cfg = {
        "bigQuerySource": {
            "projectId": project_id,
            "datasetId": bq_dataset,
            "tableId": "products",
            "dataSchema": "product",
        }
    }
    src_desc = f"BigQuery ({project_id}:{bq_dataset}.products)"
else:
    input_cfg = {
        "gcsSource": {
            "inputUris": [f"gs://{catalog_bucket}/catalog/products_retail_latest.jsonl"],
            "dataSchema": "product",
        }
    }
    src_desc = f"GCS (gs://{catalog_bucket}/catalog/products_retail_latest.jsonl)"

print(f"  [インポート開始] 入力元: {src_desc}")
body = {
    "inputConfig": input_cfg,
    "reconciliationMode": "FULL",
    "skipDefaultBranchProtection": True,
    "errorsConfig": {"gcsPrefix": f"gs://{catalog_bucket}/import_errors/"},
}

st, op = call("POST", import_url, body)
if st != 200 and "bigQuerySource" in input_cfg:
    print(f"  [情報] BigQuery 経由のインポート要求が HTTP {st} を返したため、GCS ソースへ切り替えて再試行します...")
    body["inputConfig"] = {
        "gcsSource": {
            "inputUris": [f"gs://{catalog_bucket}/catalog/products_retail_latest.jsonl"],
            "dataSchema": "product",
        }
    }
    st, op = call("POST", import_url, body)

if st != 200:
    print(f"エラー: products:import の開始に失敗しました (HTTP {st}): {json.dumps(op, ensure_ascii=False)[:800]}", file=sys.stderr)
    sys.exit(1)

op_name = op["name"]
print(f"  [LRO] オペレーション: {op_name}")

for attempt in range(1, 181):
    st, d = call("GET", f"https://retail.googleapis.com/v2alpha/{op_name}")
    meta = d.get("metadata") or {}
    succ = int(meta.get("successCount") or 0)
    fail = int(meta.get("failureCount") or 0)
    done = bool(d.get("done", False))
    if attempt == 1 or done or attempt % 3 == 0:
        print(f"  [進捗] 完了={done} / 成功={succ:,} 件 / 失敗={fail:,} 件")
    if done:
        if "error" in d:
            print(f"エラー: カタログインポート LRO が失敗しました: {json.dumps(d['error'], ensure_ascii=False)}", file=sys.stderr)
            sys.exit(1)
        if succ < 20000:
            print(
                f"エラー: インポート成功件数が想定未満です (成功={succ:,} 件 < 20,000 件, 失敗={fail:,} 件)。"
                f" gs://{catalog_bucket}/import_errors/ を確認してください。",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"  [OK] カタログインポート完了: 成功 {succ:,} 件 / 失敗 {fail:,} 件")
        sys.exit(0)
    time.sleep(10)

print("エラー: カタログインポートの待機がタイムアウトしました（バックグラウンドで継続中）。", file=sys.stderr)
sys.exit(1)
PY

# 3. カスタム属性の検索・インデックス・ファセット設定
log_info "カスタム属性のインデックス・検索・ファセット設定 (set_attributes_config.py) を適用しています..."
if [[ -f "${REPO_ROOT}/shared/catalog/set_attributes_config.py" ]]; then
  python3 "${REPO_ROOT}/shared/catalog/set_attributes_config.py" --project "${PROJECT_ID}"
else
  log_warn "shared/catalog/set_attributes_config.py が見つかりません。"
fi

# 4. オートコンプリート候補インポート（組織ポリシーで外部システム SA への付与が拒否された場合はローカル JSONL に自動フォールバック）
log_info "オートコンプリート候補データの Retail API インポートを試行しています..."
if bq --project_id="${PROJECT_ID}" show "${PROJECT_ID}:${BQ_DATASET}.autocomplete_suggestions" >/dev/null 2>&1; then
  set +e
  IAM_OUT="$(bq --project_id="${PROJECT_ID}" add-iam-policy-binding \
    --member="serviceAccount:cloud-retail-customer-data-access@system.gserviceaccount.com" \
    --role="roles/bigquery.dataViewer" \
    "${PROJECT_ID}:${BQ_DATASET}.autocomplete_suggestions" 2>&1)"
  IAM_RC=$?
  set -e

  if [[ "${IAM_RC}" -ne 0 ]]; then
    log_warn "組織ポリシー (iam.allowedPolicyMemberDomains 等) により cloud-retail-customer-data-access@system.gserviceaccount.com への権限付与がブロックされました。"
    log_info "ポリシーの回避は行いません。オンラインストアおよび店舗ナビは同梱のローカル候補ファイル (seed/catalog/autocomplete_suggestions.jsonl: 約 6,800 件) に自動でフォールバックし、同等のオートコンプリートを提供します。"
  else
    python3 - "${PROJECT_ID}" "${BQ_DATASET}" <<'PY'
import json, subprocess, sys, time, urllib.error, urllib.request

project_id, dataset_id = sys.argv[1], sys.argv[2]
tok = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
url = f"https://retail.googleapis.com/v2alpha/projects/{project_id}/locations/global/catalogs/default_catalog/completionData:import"
body = {
    "inputConfig": {
        "bigQuerySource": {
            "projectId": project_id,
            "datasetId": dataset_id,
            "tableId": "autocomplete_suggestions",
            "dataSchema": "suggestions",
        }
    }
}
req = urllib.request.Request(
    url,
    method="POST",
    data=json.dumps(body).encode("utf-8"),
    headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json", "X-Goog-User-Project": project_id},
)
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        op = json.loads(r.read().decode("utf-8") or "{}")
    name = op.get("name", "")
    print(f"  [OK] completionData:import を開始しました ({name})。")
    for _ in range(30):
        if not name:
            break
        time.sleep(5)
        chk = urllib.request.Request(
            f"https://retail.googleapis.com/v2alpha/{name}",
            headers={"Authorization": f"Bearer {tok}", "X-Goog-User-Project": project_id},
        )
        with urllib.request.urlopen(chk, timeout=60) as cr:
            st = json.loads(cr.read().decode("utf-8") or "{}")
        if st.get("done"):
            meta = st.get("metadata") or {}
            print(f"  [OK] オートコンプリートインポート完了: 成功={meta.get('successCount', 0)}")
            break
except Exception as exc:  # noqa: BLE001
    print(f"  [警告] completionData:import をスキップしました（ローカル候補ファイルへ自動フォールバック）: {exc}")
PY
  fi
else
  log_warn "${PROJECT_ID}:${BQ_DATASET}.autocomplete_suggestions テーブルが未作成のため、ローカルの autocomplete_suggestions.jsonl を使用します。"
fi

log_info "注意: 初回の Retail API カタログインポート直後は、検索インデックス反映まで数分かかる場合があります。"
log_ok "商品カタログのインポートと属性設定が完了しました。"
