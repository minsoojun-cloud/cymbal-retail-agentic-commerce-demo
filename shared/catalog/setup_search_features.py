"""Vertex AI Search for Commerce (Retail API v2alpha) のサービング機能を設定・検証するスクリプト。

ステップ（すべて冪等・import_pipeline.sh の後に実行）:
  facets   : servingConfig `default_search` の作成・dynamicFacetSpec.mode=ENABLED 設定
  complete : seed/catalog/products_retail.jsonl からオートコンプリート候補を生成し、
             seed/catalog/autocomplete_suggestions.jsonl と BigQuery へ保存後 CompletionService へインポート
  conv     : 会話型検索の retailerDisplayName 設定・生成質問の有効化試行
  probe    : 検索・会話型検索・オートコンプリートのライブ検証（結果は $CATALOG_SCRATCH/probe_*.json に出力）

使い方:
  source ../../install/config.env && python3 setup_search_features.py [--steps facets,complete,conv,probe]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DATASET = os.environ.get("BQ_DATASET", "cymbal")
REGION = os.environ.get("REGION", "asia-northeast1")
BRAND_NAME = os.environ.get("BRAND_NAME", "Cymbal Retail")
SCRATCH = os.environ.get("CATALOG_SCRATCH", "/tmp/cymbal_catalog_scratch")
CATALOG_JSONL = os.environ.get("CATALOG_JSONL", f"{REPO_ROOT}/seed/catalog/products_retail.jsonl")
AUTOCOMPLETE_JSONL = os.environ.get("AUTOCOMPLETE_JSONL", f"{REPO_ROOT}/seed/catalog/autocomplete_suggestions.jsonl")
API = "https://retail.googleapis.com/v2alpha"
SUGGEST_TABLE = "autocomplete_suggestions"

PROJECT = ""
PROJECT_NUMBER = ""
CATALOG = ""
SERVING = ""

DEMO_QUERIES = [
    ("お弁当 冷凍", 1.0), ("お弁当", 0.98), ("お弁当箱", 0.95), ("フライパン", 0.97), ("フライパン 26cm", 0.9),
    ("プレゼント", 0.96), ("プレゼント ギフト", 0.9), ("新米", 0.97), ("ドッグフード", 0.96), ("ドッグフード 小型犬", 0.9),
    ("キャットフード", 0.9), ("保湿 クリーム", 0.96), ("保湿クリーム 敏感肌", 0.88), ("ハンドクリーム", 0.9),
    ("中辛 カレー", 0.95), ("カレールー 中辛", 0.9), ("秋鮭", 0.9), ("鍋つゆ", 0.93), ("鍋 セット", 0.85),
    ("えび 不使用", 0.85), ("タオル ギフト", 0.88), ("加湿器", 0.86), ("水筒", 0.86), ("卵焼き器", 0.85),
    ("お買い得", 0.9), ("セール", 0.88), ("鮮度＋", 0.84), ("オーガニック", 0.84), ("冷凍食品", 0.9),
    ("かぜ薬", 0.95), ("かぜ薬 子ども用", 0.88), ("かぜ薬 錠剤", 0.86), ("かぜ 漢方", 0.82), ("解熱鎮痛薬", 0.92),
    ("頭痛薬", 0.88), ("目薬", 0.92), ("目薬 疲れ目", 0.86), ("湿布", 0.92), ("冷湿布", 0.86), ("温湿布", 0.85),
    ("のどスプレー", 0.9), ("トローチ", 0.86), ("せき止め", 0.86), ("鼻炎薬", 0.88), ("胃腸薬", 0.9),
    ("栄養ドリンク", 0.9), ("ビタミンC", 0.86), ("かゆみ止め", 0.85), ("口内炎", 0.84), ("医薬品", 0.85),
    ("焼きたてパン", 0.9), ("鯖寿司", 0.88), ("ばってら", 0.86), ("豚まん", 0.9), ("串カツ", 0.88), ("たこ焼き", 0.9),
    ("お好み焼き", 0.88), ("どて焼", 0.82), ("地元やさい", 0.86), ("仏花", 0.88), ("花束", 0.86), ("黒毛和牛 すき焼き", 0.86),
    ("わらび餅", 0.86), ("ちりめん山椒", 0.82), ("ぽん酢", 0.84), ("淡口しょうゆ", 0.82),
]

SIZE_TOKEN = re.compile(r"^[\[（(【]|[0-9０-９]|約|入$|個$|本$|枚$|袋$|パック|cm$|ml$|g$|kg$|L$")
BRAND_PREFIX = re.compile(r"^(Cymbal( ベーシック| セレクト| オーガニック| Home| Beauty| Pet| ヘルスケア| メディカル)?)\s+")


def _init_project(project_arg: str = "", project_number_arg: str = ""):
    global PROJECT, PROJECT_NUMBER, CATALOG, SERVING
    PROJECT = project_arg or os.environ.get("PROJECT_ID", "")
    if not PROJECT:
        sys.exit("--project または PROJECT_ID 環境変数を指定してください。")
    PROJECT_NUMBER = project_number_arg or os.environ.get("PROJECT_NUMBER", "")
    if not PROJECT_NUMBER:
        PROJECT_NUMBER = subprocess.run(
            ["gcloud", "projects", "describe", PROJECT, "--format=value(projectNumber)"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    CATALOG = f"projects/{PROJECT_NUMBER}/locations/global/catalogs/default_catalog"
    SERVING = f"{CATALOG}/servingConfigs/default_search"


def tok():
    return subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True,
                          check=True).stdout.strip()


TOKEN = None


def call(method, path, body=None, params=""):
    global TOKEN
    TOKEN = TOKEN or tok()
    url = f"{API}/{path}{('?' + params) if params else ''}"
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
                                          "X-Goog-User-Project": PROJECT})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        txt = e.read().decode()
        try:
            return e.code, json.loads(txt)
        except Exception:
            return e.code, {"raw": txt[:2000]}


def save(name, obj):
    os.makedirs(SCRATCH, exist_ok=True)
    with open(f"{SCRATCH}/probe_{name}.json", "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def step_facets():
    st, sc = call("GET", SERVING)
    if st == 404:
        st, sc = call("POST", f"{CATALOG}/servingConfigs", params="servingConfigId=default_search",
                      body={"displayName": "default_search", "solutionTypes": ["SOLUTION_TYPE_SEARCH"],
                            "dynamicFacetSpec": {"mode": "ENABLED"}})
        print("create servingConfig default_search:", st)
    st, sc = call("PATCH", SERVING, params="updateMask=dynamicFacetSpec",
                  body={"dynamicFacetSpec": {"mode": "ENABLED"}})
    print("servingConfig dynamicFacetSpec:", st, sc.get("dynamicFacetSpec"))


def short_title(title: str) -> str:
    t = BRAND_PREFIX.sub("", title.replace("[鮮度+]", "").replace("[鮮度＋]", "").strip())
    toks = t.split()
    while len(toks) > 1 and SIZE_TOKEN.search(toks[-1]):
        toks.pop()
    toks = [x for x in toks if not x.startswith(("[", "（", "("))]
    return " ".join(toks[:3]).strip()


def build_suggestions(path):
    cnt, cats, brands, otc = Counter(), Counter(), Counter(), Counter()
    for line in open(path, encoding="utf-8"):
        p = json.loads(line)
        s = short_title(p["title"])
        if 2 <= len(s) <= 30:
            base = next((a["value"]["text"][0] for a in p.get("attributes", []) if a["key"] == "base_id"), "")
            (otc if p.get("categories", [""])[0].startswith("医薬品・ヘルスケア") or base.startswith("k_kansai_")
             else cnt)[s] += 1
        for c in p.get("categories", []):
            for lvl in c.split(" > ")[1:]:
                cats[lvl.strip()] += 1
        for b in p.get("brands", []):
            brands[b] += 1
    rows = {}
    for s, sc in DEMO_QUERIES:
        rows[s] = sc
    for c, n in cats.items():
        rows.setdefault(c, round(min(0.8, 0.5 + n / 400), 3))
    for b, n in brands.items():
        rows.setdefault(b, round(min(0.75, 0.45 + n / 2000), 3))
    for s, n in cnt.most_common(4000):
        rows.setdefault(s, round(min(0.7, 0.2 + n / 20), 3))
    for s, n in otc.most_common():
        rows.setdefault(s, round(min(0.7, 0.2 + n / 20), 3))
    return [{"suggestion": s, "globalScore": float(v), "frequency": None, "languageCode": "ja"} for s, v in rows.items()]


def step_complete():
    rows = build_suggestions(CATALOG_JSONL)
    os.makedirs(os.path.dirname(os.path.abspath(AUTOCOMPLETE_JSONL)), exist_ok=True)
    with open(AUTOCOMPLETE_JSONL, "w", encoding="utf-8") as f:
        for r in sorted(rows, key=lambda r: -r["globalScore"]):
            f.write(json.dumps({"suggestion": r["suggestion"], "score": r["globalScore"]}, ensure_ascii=False) + "\n")
    tmp = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
    for r in rows:
        tmp.write(json.dumps({k: v for k, v in r.items() if v is not None}, ensure_ascii=False) + "\n")
    tmp.close()
    schema = "suggestion:STRING,globalScore:FLOAT,frequency:INTEGER,languageCode:STRING"
    subprocess.run(["bq", f"--project_id={PROJECT}", f"--location={REGION}", "load", "--replace",
                    "--source_format=NEWLINE_DELIMITED_JSON", f"{PROJECT}:{DATASET}.{SUGGEST_TABLE}", tmp.name, schema],
                   check=True, stdout=subprocess.DEVNULL)
    os.unlink(tmp.name)
    print(f"BQ {DATASET}.{SUGGEST_TABLE}: {len(rows)} suggestions (+ {AUTOCOMPLETE_JSONL})")
    g = subprocess.run(["bq", f"--project_id={PROJECT}", "add-iam-policy-binding",
                        "--member=serviceAccount:cloud-retail-customer-data-access@system.gserviceaccount.com",
                        "--role=roles/bigquery.dataViewer", f"{PROJECT}:{DATASET}.{SUGGEST_TABLE}"],
                       capture_output=True, text=True)
    print("grant dataViewer to cloud-retail-customer-data-access:", "OK" if g.returncode == 0 else
          ("WARN (ローカル JSONL にフォールバック) " + (g.stderr or g.stdout).strip().replace("\n", " ")[:300]))

    st, cc = call("PATCH", f"{CATALOG}/completionConfig",
                  params="updateMask=matchingOrder,maxSuggestions,minPrefixLength",
                  body={"matchingOrder": "out-of-order", "maxSuggestions": 10, "minPrefixLength": 1})
    print("completionConfig:", st, {k: cc.get(k) for k in ("matchingOrder", "maxSuggestions", "minPrefixLength")}
          if st == 200 else cc)

    st, op = call("POST", f"{CATALOG}/completionData:import", body={
        "inputConfig": {"bigQuerySource": {"projectId": PROJECT, "datasetId": DATASET, "tableId": SUGGEST_TABLE,
                                           "dataSchema": "suggestions"}}})
    if st != 200:
        print("completionData:import SKIPPED/FAILED", st, json.dumps(op, ensure_ascii=False)[:800]); return
    name = op["name"]
    print("completion import operation:", name)
    for _ in range(90):
        st, d = call("GET", name)
        if d.get("done"):
            m = d.get("metadata", {})
            print("  done", "error=" + json.dumps(d["error"], ensure_ascii=False) if "error" in d else "",
                  f"success={m.get('successCount')} failure={m.get('failureCount')}")
            return
        time.sleep(10)
    print("  still running (continues in background)")


def step_conv():
    st, r = call("PATCH", f"{CATALOG}/conversationalSearchCustomizationConfig", body={
        "catalog": CATALOG, "retailerDisplayName": BRAND_NAME})
    print("conversationalSearchCustomizationConfig:", st, r if st != 200 else r.get("retailerDisplayName"))
    st, r = call("PATCH", f"{CATALOG}/generativeQuestionFeature", params="updateMask=featureEnabled,minimumProducts",
                 body={"catalog": CATALOG, "featureEnabled": True, "minimumProducts": 2})
    print("generativeQuestionFeature enable:", st, r.get("error", {}).get("message", r))
    st, r = call("GET", f"{CATALOG}/generativeQuestions")
    print("generativeQuestions:", st, len(r.get("questions", [])), "questions")
    save("generative_questions", r)


SEARCH_BODY = {
    "query": "お弁当", "visitorId": "probe-visitor", "pageSize": 5, "languageCode": "ja",
    "facetSpecs": [
        {"facetKey": {"key": "categories"}, "limit": 10},
        {"facetKey": {"key": "brands"}, "limit": 10},
        {"facetKey": {"key": "attributes.top_category"}},
        {"facetKey": {"key": "attributes.on_sale"}},
        {"facetKey": {"key": "attributes.storage_type"}},
        {"facetKey": {"key": "price", "intervals": [{"maximum": 300}, {"minimum": 300, "maximum": 1000},
                                                     {"minimum": 1000, "maximum": 3000}, {"minimum": 3000}]}},
    ],
    "dynamicFacetSpec": {"mode": "ENABLED"},
    "conversationalSearchSpec": {"followupConversationRequested": True},
    "tileNavigationSpec": {"tileNavigationRequested": True},
    "spellCorrectionSpec": {"mode": "AUTO"},
    "queryExpansionSpec": {"condition": "AUTO", "pinUnexpandedResults": True},
}


def step_probe(queries):
    out = {}
    for q in queries:
        st, r = call("POST", f"{SERVING}:search", body={**SEARCH_BODY, "query": q})
        save(f"search_{q.replace(' ', '_')}", r)
        out[q] = {"status": st, "totalSize": r.get("totalSize"), "keys": sorted(r.keys()),
                  "facets": {f["key"]: len(f.get("values", [])) for f in r.get("facets", [])},
                  "tiles": len(r.get("tileNavigationResult", {}).get("tiles", [])),
                  "conversational": bool(r.get("conversationalSearchResult")),
                  "corrected": r.get("correctedQuery"),
                  "top": [x["id"] for x in r.get("results", [])[:3]],
                  "error": r.get("error", {}).get("message")}
    st, r = call("POST", f"{SERVING}:conversationalSearch", body={
        "query": "子どものお弁当に入れるおかずを探しています", "visitorId": "probe-visitor",
        "conversationalFilteringSpec": {"enableConversationalFiltering": True}})
    save("conversational_search", r)
    final = r[-1] if isinstance(r, list) and r else r
    out["conversationalSearch"] = {"status": st, "keys": sorted(final.keys()) if isinstance(final, dict) else None,
                                   "refinedSearch": [x.get("query") for x in ((final.get("refinedSearch") or [])
                                                     if isinstance(final, dict) else []) if x.get("query")][:6],
                                   "followup": (final.get("followupQuestion") or {}).get("followupQuestion"),
                                   "text": (final.get("conversationalTextResponse") or "")[:160]}
    for q in ["フラ", "お弁", "ドッグ", "保湿", "かぜ", "目薬", "しっぷ", "湿布"]:
        for ds in ("user-data", "cloud-retail"):
            st, r = call("GET", f"{CATALOG}:completeQuery",
                         params=urllib.parse.urlencode({"query": q, "visitorId": "probe-visitor", "languageCodes": "ja",
                                                        "dataset": ds, "maxSuggestions": 8}))
            out[f"completeQuery {q} [{ds}]"] = [x.get("suggestion") for x in r.get("completionResults", [])] \
                if st == 200 else f"{st} {r.get('error', {}).get('message')}"
    save("summary", out)
    print(json.dumps(out, ensure_ascii=False, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="")
    ap.add_argument("--project-number", default="")
    ap.add_argument("--steps", default="facets,complete,conv,probe")
    ap.add_argument("--queries", default="お弁当,フライパン,ドッグフード,保湿 クリーム,新米,プレゼント")
    a = ap.parse_args()
    _init_project(a.project, a.project_number)
    steps = a.steps.split(",")
    if "facets" in steps:
        step_facets()
    if "complete" in steps:
        step_complete()
    if "conv" in steps:
        step_conv()
    if "probe" in steps:
        step_probe(a.queries.split(","))


if __name__ == "__main__":
    main()
