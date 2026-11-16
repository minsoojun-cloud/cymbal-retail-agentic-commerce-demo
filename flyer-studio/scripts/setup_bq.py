"""Create and populate BigQuery extension tables for Cymbal Flyer Studio (`flyer-studio`).

Tables created in `${PROJECT_ID}.${BQ_DATASET}` (default dataset `cymbal`):
  - `flyer_product_ext`     : per-product flyer metadata (flyer_name, unit_label, price_per_100g, pack_type, origin_label)
  - `flyer_offers`          : flyer-only special price records entered by staff/managers
  - `flyers`                : flyer index for drafts, pending review, and manager-approved archives
  - `flyer_price_reference` : reference price bands observed in the 93-flyer Japanese supermarket survey
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from google.cloud import bigquery

REPO_DIR = Path(__file__).resolve().parent.parent.parent
DATA_FILE = Path(os.environ.get("CATALOG_JSONL") or str(REPO_DIR / "seed" / "catalog" / "products_retail.jsonl"))
PROJECT_ID = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
BQ_DATASET = os.environ.get("BQ_DATASET", "cymbal")
BQ_LOCATION = os.environ.get("BQ_LOCATION", os.environ.get("REGION", "asia-northeast1"))

BRAND_PREFIXES = (
    "Cymbal ベーシック ",
    "Cymbal セレクト ",
    "Cymbal オーガニック ",
    "Cymbal Home ",
    "Cymbal Beauty ",
    "Cymbal Pet ",
    "Cymbal ",
)


def _attr_map(raw: list | dict | None) -> dict[str, dict]:
    if isinstance(raw, dict):
        return raw
    out: dict[str, dict] = {}
    for a in raw or []:
        if isinstance(a, dict) and "key" in a:
            out[a["key"]] = a.get("value") or {}
    return out


def _attr_text(attrs: dict, key: str) -> str:
    v = attrs.get(key) or {}
    t = v.get("text") or []
    return str(t[0]) if t else ""


def _attr_num(attrs: dict, key: str) -> float | None:
    v = attrs.get(key) or {}
    n = v.get("numbers") or []
    try:
        return float(n[0]) if n else None
    except (TypeError, ValueError):
        return None


def make_flyer_name(title: str) -> str:
    s = (title or "").strip()
    for p in BRAND_PREFIXES:
        if s.startswith(p):
            s = s[len(p):].strip()
            break
    return s or title


def derive_unit_and_per100g(title: str, size: str, category: str, price_ex: float) -> tuple[str, int | None, str]:
    size_s = (size or "").strip()
    is_meat_fish = any(k in category for k in ("お肉", "お魚"))
    price_per_100g: int | None = None

    m_g = re.fullmatch(r"(\d+(?:\.\d+)?)\s*g", size_s, flags=re.I)
    if m_g and is_meat_fish:
        grams = float(m_g.group(1))
        if 50 <= grams <= 2000 and price_ex > 0:
            price_per_100g = max(1, int(round(price_ex * 100.0 / grams)))

    if price_per_100g is not None:
        unit_label = f"1パック({size_s})・100g当り本体{price_per_100g}円"
    elif size_s:
        unit_label = size_s
    else:
        unit_label = "1点"

    combined = f"{title} {size_s}"
    if any(k in combined for k in ("大パック", "徳用", "お徳用", "大容量", "ファミリー", "ジャンボ")) or (
        m_g and float(m_g.group(1)) >= 400
    ):
        pack_type = "大パック"
    elif any(k in combined for k in ("1人前", "小分け", "ハーフ", "少量", "食べきり", "1個", "半身")):
        pack_type = "少量・1人前"
    else:
        pack_type = "標準"

    return unit_label, price_per_100g, pack_type


REFERENCE_PRICES = [
    {"category": "野菜・果物", "item_type": "キャベツ", "unit": "1玉", "observed_price": 198, "source_record": "survey_seg1_summit"},
    {"category": "野菜・果物", "item_type": "ブロッコリー", "unit": "1株", "observed_price": 158, "source_record": "survey_seg1_summit"},
    {"category": "野菜・果物", "item_type": "小松菜・ほうれん草", "unit": "1袋", "observed_price": 99, "source_record": "survey_seg1_summit"},
    {"category": "野菜・果物", "item_type": "ぶなしめじ・きのこ", "unit": "1袋", "observed_price": 99, "source_record": "survey_seg1_summit"},
    {"category": "野菜・果物", "item_type": "みかん・りんご・キウイ", "unit": "1個", "observed_price": 99, "source_record": "survey_seg1_summit"},
    {"category": "お肉・お肉加工品", "item_type": "国産若どりもも肉", "unit": "100g当り", "observed_price": 99, "source_record": "survey_seg1_summit"},
    {"category": "お肉・お肉加工品", "item_type": "豚こま切れ肉", "unit": "100g当り", "observed_price": 99, "source_record": "survey_seg1_summit"},
    {"category": "お肉・お肉加工品", "item_type": "国産牛カルビ・黒毛和牛", "unit": "100g当り", "observed_price": 598, "source_record": "survey_seg2_regional"},
    {"category": "お魚・水産加工品", "item_type": "刺身用まぐろ", "unit": "100g当り", "observed_price": 258, "source_record": "survey_seg1_summit"},
    {"category": "お魚・水産加工品", "item_type": "生秋鮭・塩銀鮭切身", "unit": "1切/100g当り", "observed_price": 198, "source_record": "survey_seg2_regional"},
    {"category": "卵・乳製品・豆乳・デザート", "item_type": "鶏卵 L/M 10個入", "unit": "1パック", "observed_price": 238, "source_record": "survey_seg2_regional"},
    {"category": "卵・乳製品・豆乳・デザート", "item_type": "牛乳 1000ml", "unit": "1本", "observed_price": 198, "source_record": "survey_seg2_regional"},
    {"category": "豆腐・納豆・練り物", "item_type": "豆腐・厚揚げ・ちくわ", "unit": "1パック", "observed_price": 99, "source_record": "survey_seg1_summit"},
    {"category": "冷凍食品・アイス", "item_type": "冷凍ギョーザ 12個入", "unit": "1袋", "observed_price": 168, "source_record": "survey_seg1_summit"},
    {"category": "お米・麺・インスタント", "item_type": "新潟県産こしひかり 新米", "unit": "5kg", "observed_price": 2980, "source_record": "survey_seg1_summit"},
    {"category": "お米・麺・インスタント", "item_type": "袋ラーメン・玉うどん", "unit": "1袋", "observed_price": 99, "source_record": "survey_seg1_summit"},
    {"category": "調味料", "item_type": "マヨネーズ 450g", "unit": "1本", "observed_price": 250, "source_record": "survey_seg1_summit"},
    {"category": "調味料", "item_type": "食酢・ぽん酢 500ml", "unit": "1本", "observed_price": 238, "source_record": "survey_seg1_summit"},
    {"category": "お惣菜・ミールキット", "item_type": "若どり唐揚げ・コロッケ", "unit": "100g/1パック", "observed_price": 198, "source_record": "survey_seg4_coop"},
    {"category": "日用品・キッチン消耗品", "item_type": "トイレットペーパー 8〜12ロール", "unit": "1パック", "observed_price": 368, "source_record": "survey_seg1_summit"},
]


def main() -> None:
    client = bigquery.Client(project=PROJECT_ID, location=BQ_LOCATION)
    ds = f"{PROJECT_ID}.{BQ_DATASET}"

    ddl_statements = [
        f"""
        CREATE TABLE IF NOT EXISTS `{ds}.flyer_product_ext` (
          product_id STRING NOT NULL,
          flyer_name STRING,
          unit_label STRING,
          price_per_100g INT64,
          pack_type STRING,
          origin_label STRING
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS `{ds}.flyer_offers` (
          offer_id STRING NOT NULL,
          flyer_id STRING NOT NULL,
          slot_id STRING NOT NULL,
          product_id STRING NOT NULL,
          offer_price_tax_excluded INT64 NOT NULL,
          offer_price_tax_included INT64 NOT NULL,
          regular_price_tax_excluded INT64,
          regular_price_tax_included INT64,
          valid_from STRING,
          valid_to STRING,
          limit_text STRING,
          entered_by STRING,
          entered_at TIMESTAMP
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS `{ds}.flyers` (
          flyer_id STRING NOT NULL,
          title STRING,
          theme STRING,
          target STRING,
          template_id STRING,
          period_from STRING,
          period_to STRING,
          item_count INT64,
          status STRING,
          created_by STRING,
          created_at TIMESTAMP,
          approved_by STRING,
          approved_at TIMESTAMP,
          gcs_prefix STRING
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS `{ds}.flyer_price_reference` (
          category STRING,
          item_type STRING,
          unit STRING,
          observed_price INT64,
          source_record STRING
        )
        """,
    ]
    for ddl in ddl_statements:
        client.query(ddl).result()
    print("BigQuery tables ensured in", ds)

    # Populate flyer_price_reference
    ref_table = f"{ds}.flyer_price_reference"
    job_cfg = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    client.load_table_from_json(REFERENCE_PRICES, ref_table, job_config=job_cfg).result()
    print(f"Loaded {len(REFERENCE_PRICES)} rows into {ref_table}")

    # Build and load flyer_product_ext for all catalog products
    ext_rows = []
    with open(DATA_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            p = json.loads(line)
            if p.get("type", "PRIMARY") not in ("PRIMARY", ""):
                continue
            attrs = _attr_map(p.get("attributes"))
            title = p.get("title") or ""
            cats = p.get("categories") or [""]
            top_cat = _attr_text(attrs, "top_category") or cats[0].split(">")[0].strip()
            size = _attr_text(attrs, "size")
            origin = _attr_text(attrs, "origin")
            price_info = p.get("priceInfo") or {}
            price_inc = float(price_info.get("price") or 0)
            price_ex = _attr_num(attrs, "price_tax_excluded") or round(price_inc / 1.08)

            flyer_name = make_flyer_name(title)
            unit_label, per100g, pack_type = derive_unit_and_per100g(flyer_name, size, top_cat, float(price_ex))
            ext_rows.append({
                "product_id": str(p["id"]),
                "flyer_name": flyer_name,
                "unit_label": unit_label,
                "price_per_100g": per100g,
                "pack_type": pack_type,
                "origin_label": origin,
            })

    ext_table = f"{ds}.flyer_product_ext"
    ext_job_cfg = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        schema=[
            bigquery.SchemaField("product_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("flyer_name", "STRING"),
            bigquery.SchemaField("unit_label", "STRING"),
            bigquery.SchemaField("price_per_100g", "INT64"),
            bigquery.SchemaField("pack_type", "STRING"),
            bigquery.SchemaField("origin_label", "STRING"),
        ],
    )
    client.load_table_from_json(ext_rows, ext_table, job_config=ext_job_cfg).result()
    print(f"Loaded {len(ext_rows)} rows into {ext_table}")

    # Also write a local cache copy for offline/local-mode tests
    local_ext = Path(__file__).resolve().parent.parent / "data" / "flyer_product_ext.json"
    local_ext.parent.mkdir(parents=True, exist_ok=True)
    local_ext.write_text(json.dumps({r["product_id"]: r for r in ext_rows}, ensure_ascii=False), encoding="utf-8")
    print("Wrote local cache:", local_ext)


if __name__ == "__main__":
    main()
