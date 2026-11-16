#!/usr/bin/env python3
"""Migrate store layouts to v11 schema:
- Stable fixture UIDs (`<store_id>-F<index:04d>`)
- `tier_slots` (default empty dict)
- `disabled_slots` (default empty list)
- Zone `auto_rect: true`
- Ensure BigQuery `cymbal.store_layout_changes` exists
- Re-seed BigQuery `store_layouts` with baseline version 2
"""
import json
import os
import sys
from pathlib import Path
from google.cloud import bigquery

PROJECT_ID = os.environ.get("PROJECT_ID", "")
DATASET_ID = os.environ.get("BQ_DATASET", "cymbal")
HERE = Path(__file__).resolve().parent
REPO_DIR = HERE.parent
DATA_DIR = REPO_DIR / "data"
LAYOUTS_DIR = DATA_DIR / "layouts"


def migrate_local_layouts():
    print("Migrating local layout files in", LAYOUTS_DIR)
    migrated_layouts = {}
    for sid in ["S01", "S02", "S03"]:
        p = LAYOUTS_DIR / f"{sid}.json"
        if not p.exists():
            print(f"Warning: {p} does not exist")
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        fixtures = data.get("fixtures", [])
        for idx, f in enumerate(fixtures):
            if "uid" not in f:
                f["uid"] = f"{sid}-F{idx+1:04d}"
            if "tier_slots" not in f:
                f["tier_slots"] = {}
            if "disabled_slots" not in f:
                f["disabled_slots"] = []
        
        zones = data.get("zones", [])
        for z in zones:
            z["auto_rect"] = True
            
        # Ensure version is 2
        data["version"] = 2
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {sid}: {len(fixtures)} fixtures, {len(zones)} zones migrated.")
        migrated_layouts[sid] = data
    return migrated_layouts


def ensure_bq_tables(client: bigquery.Client, layouts: dict):
    # 1. Create store_layout_changes table if not exists
    table_id = f"{PROJECT_ID}.{DATASET_ID}.store_layout_changes"
    schema = [
        bigquery.SchemaField("store_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("version", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("base_version", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("action", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("published_by", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("published_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("summary", "STRING", mode="NULLABLE"),
    ]
    try:
        client.get_table(table_id)
        print(f"Table {table_id} already exists.")
    except Exception:
        table = bigquery.Table(table_id, schema=schema)
        client.create_table(table)
        print(f"Created table {table_id}.")

    # 2. Re-seed store_layouts baseline v2
    layouts_table_id = f"{PROJECT_ID}.{DATASET_ID}.store_layouts"
    rows = []
    for sid, lay in layouts.items():
        rows.append({
            "store_id": sid,
            "version": 2,
            "layout": json.dumps(lay, ensure_ascii=False)
        })
    
    job_config = bigquery.LoadJobConfig(
        schema=[
            bigquery.SchemaField("store_id", "STRING"),
            bigquery.SchemaField("version", "INTEGER"),
            bigquery.SchemaField("layout", "STRING"),
        ],
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    job = client.load_table_from_json(rows, layouts_table_id, job_config=job_config)
    job.result()
    print(f"Re-seeded {layouts_table_id} with baseline version 2 ({len(rows)} stores).")


def main():
    if not PROJECT_ID:
        sys.exit("PROJECT_ID 環境変数を指定してください。")
    layouts = migrate_local_layouts()
    client = bigquery.Client(project=PROJECT_ID)
    ensure_bq_tables(client, layouts)
    print("Migration complete!")


if __name__ == "__main__":
    main()
