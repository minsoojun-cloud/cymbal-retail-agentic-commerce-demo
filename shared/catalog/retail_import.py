"""BigQuery から Vertex AI Search for Commerce (Retail API) への products:import を実行し完了までポーリングする。"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request


def token():
    return subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True,
                          check=True).stdout.strip()


def call(method, url, project, body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json",
                                          "X-Goog-User-Project": project})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode() or "{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=os.environ.get("PROJECT_ID", ""))
    ap.add_argument("--dataset", default=os.environ.get("BQ_DATASET", "cymbal"))
    ap.add_argument("--table", default=os.environ.get("BQ_TABLE", "products"))
    ap.add_argument("--bucket", default=os.environ.get("CATALOG_BUCKET") or os.environ.get("GCS_BUCKET") or "")
    a = ap.parse_args()
    if not a.project:
        sys.exit("--project または PROJECT_ID 環境変数を指定してください。")
    bucket = a.bucket or f"{a.project}-catalog"
    base = f"https://retail.googleapis.com/v2alpha/projects/{a.project}/locations/global/catalogs/default_catalog"
    body = {"inputConfig": {"bigQuerySource": {"projectId": a.project, "datasetId": a.dataset,
                                               "tableId": a.table, "dataSchema": "product"}},
            "reconciliationMode": "FULL",
            "skipDefaultBranchProtection": True,
            "errorsConfig": {"gcsPrefix": f"gs://{bucket}/import_errors/"}}
    try:
        op = call("POST", f"{base}/branches/0/products:import", a.project, body)
    except urllib.error.HTTPError as e:
        print(e.code, e.read().decode()[:2000]); sys.exit(1)
    name = op["name"]
    print("operation:", name)
    for _ in range(180):
        d = call("GET", f"https://retail.googleapis.com/v2alpha/{name}", a.project)
        m = d.get("metadata", {})
        print(f"  done={d.get('done', False)} success={m.get('successCount', 0)} failure={m.get('failureCount', 0)}")
        if d.get("done"):
            if "error" in d:
                print("ERROR:", d["error"]); sys.exit(1)
            return
        time.sleep(10)
    print("timeout while polling (operation continues in background)")


if __name__ == "__main__":
    main()
