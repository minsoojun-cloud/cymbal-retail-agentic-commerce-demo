#!/usr/bin/env bash
# ==============================================================================
# 30_retail.sh — Vertex AI Search for Commerce (Retail API) 規約同意・検索有効化・Serving Config 設定
# ==============================================================================
set -euo pipefail
STEP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${STEP_DIR}/../lib/common.sh"
load_config

log_info "Vertex AI Search for Commerce (Retail API v2alpha) の規約同意・Search ソリューション登録・Serving Config 設定を実行しています..."

python3 - "${PROJECT_ID}" "${BRAND_NAME}" <<'PY'
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

project_id = sys.argv[1]
brand_name = sys.argv[2]
token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
api_base = "https://retail.googleapis.com/v2alpha"


def call(method: str, path: str, body=None, params: str = "") -> tuple[int, dict]:
    url = f"{api_base}/{path}" + (f"?{params}" if params else "")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        method=method,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": project_id,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw[:400]}


# 1. 利用規約への同意 (acceptTerms)
st, resp = call("POST", f"projects/{project_id}/retailProject:acceptTerms", {})
if st in (200, 409):
    print(f"  [OK] Retail API 利用規約同意 (HTTP {st})")
else:
    print(f"  [警告] acceptTerms 応答 HTTP {st}: {json.dumps(resp, ensure_ascii=False)[:300]}")

# 2. SOLUTION_TYPE_SEARCH の有効化 (enrollSolution)
st, resp = call("POST", f"projects/{project_id}:enrollSolution", {"solution": "SOLUTION_TYPE_SEARCH"})
if st == 200:
    # LRO の場合は完了まで軽くポーリング
    op_name = resp.get("name", "")
    if op_name and not resp.get("done", True):
        for _ in range(12):
            time.sleep(3)
            _, op_st = call("GET", op_name)
            if op_st.get("done"):
                break
    print("  [OK] SOLUTION_TYPE_SEARCH を有効化しました。")
elif st == 409 or "ALREADY_EXISTS" in json.dumps(resp):
    print("  [OK] SOLUTION_TYPE_SEARCH は既に有効化されています。")
else:
    print(f"  [警告] enrollSolution 応答 HTTP {st}: {json.dumps(resp, ensure_ascii=False)[:300]}")

# 3. default_search Serving Config の確認・作成と動的ファセット有効化
catalog_path = f"projects/{project_id}/locations/global/catalogs/default_catalog"
serving_path = f"{catalog_path}/servingConfigs/default_search"

st, sc = call("GET", serving_path)
if st == 404:
    st, sc = call(
        "POST",
        f"{catalog_path}/servingConfigs",
        body={
            "displayName": "default_search",
            "solutionTypes": ["SOLUTION_TYPE_SEARCH"],
            "dynamicFacetSpec": {"mode": "ENABLED"},
        },
        params="servingConfigId=default_search",
    )
    if st not in (200, 409):
        print(f"エラー: default_search Serving Config の作成に失敗しました (HTTP {st}): {sc}", file=sys.stderr)
        sys.exit(1)
    print("  [作成] Serving Config 'default_search' を新規作成しました。")

st, sc = call(
    "PATCH",
    serving_path,
    body={"dynamicFacetSpec": {"mode": "ENABLED"}},
    params="updateMask=dynamicFacetSpec",
)
if st == 200:
    print(f"  [OK] default_search 動的ファセット有効化: {sc.get('dynamicFacetSpec')}")
else:
    print(f"  [警告] dynamicFacetSpec 更新応答 HTTP {st}: {json.dumps(sc, ensure_ascii=False)[:300]}")

# 4. オートコンプリート設定 (completionConfig)
st, cc = call(
    "PATCH",
    f"{catalog_path}/completionConfig",
    body={"matchingOrder": "out-of-order", "maxSuggestions": 10, "minPrefixLength": 1},
    params="updateMask=matchingOrder,maxSuggestions,minPrefixLength",
)
if st == 200:
    print("  [OK] completionConfig 設定完了 (matchingOrder=out-of-order, maxSuggestions=10, minPrefixLength=1)")
else:
    print(f"  [警告] completionConfig 更新応答 HTTP {st}: {json.dumps(cc, ensure_ascii=False)[:300]}")

# 5. 会話型検索の表示名設定（ベストエフォート）
st, _ = call(
    "PATCH",
    f"{catalog_path}/conversationalSearchCustomizationConfig",
    body={"catalog": catalog_path, "retailerDisplayName": brand_name},
)
if st == 200:
    print(f"  [OK] 会話型検索のストア表示名を '{brand_name}' に設定しました。")
PY

log_ok "Vertex AI Search for Commerce の初期設定が完了しました。"
