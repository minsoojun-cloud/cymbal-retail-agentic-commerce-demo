"""カテゴリブループリント (shared/catalog/blueprint/*.json) から Retail API スキーマの商品カタログ JSONL を生成する。

決定論的（シード固定）に展開し、以下を出力する:
  seed/catalog/products_retail.jsonl                      -> GCS -> BigQuery -> Vertex AI Search for Commerce
  online-store-adk/static/img/products/credits.json       (credits.jsonl が存在する場合のみ)
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import random
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BP_DIR = os.environ.get("BLUEPRINT_DIR", f"{HERE}/blueprint")
IMG_DIR = os.environ.get("PRODUCT_IMAGES_DIR", f"{REPO_ROOT}/online-store-adk/static/img/products")


def _default_base_url() -> str:
    for k in ("ONLINE_STORE_URL", "SITE_BASE_URL", "STORE_URL"):
        if os.environ.get(k):
            return os.environ[k].rstrip("/")
    pn = os.environ.get("PROJECT_NUMBER")
    if pn:
        prefix = os.environ.get("SERVICE_PREFIX", "cymbal")
        svc = os.environ.get("ONLINE_STORE_SERVICE", f"{prefix}-site-adk")
        reg = os.environ.get("REGION", "asia-northeast1")
        return f"https://{svc}-{pn}.{reg}.run.app"
    return "https://cymbal-store.example.com"


DEFAULT_BASE_URL = _default_base_url()
TAX = 1.08
CURRENT_MONTH = 11
PROMOS = ["今週のおトクな！おすすめ品", "週末限定 お買い得", "秋の味覚フェア 特価", "まとめ買いでおトク", "タイムセール"]
PROMOS_GM = ["今週のおトクな！おすすめ品", "週末限定 お買い得", "暮らしの応援セール", "まとめ買いでおトク", "タイムセール"]
LOYALTY_TEMPLATES = ["{brand_prefix}ポイント 10ポイント進呈", "{brand_prefix}ポイント 20ポイント進呈"]
# リブランディングマップ（長い文字列から順に置換）
REBRAND = [
    ("トップバリュ グリーンアイ オーガニック", "Cymbal オーガニック"),
    ("トップバリュ ベストプライス", "Cymbal ベーシック"),
    ("トップバリュ セレクト", "Cymbal セレクト"),
    ("トップバリュ", "Cymbal"),
    ("WAONポイント", "Cymbalポイント"),
    ("グリーンビーンズ", "Cymbal Retail"),
    ("Green Beans", "Cymbal Retail"),
    ("イオン", "Cymbal Retail"),
]

NONFOOD_TOPS = {"日用品・キッチン消耗品", "キッチン・調理器具", "ビューティー・パーソナルケア", "ペット用品", "生活雑貨・インテリア"}
HOT_KEYWORDS = ["秋鮭", "さんま", "さつまいも", "しめじ", "まいたけ", "梨", "中辛", "豚こま", "鍋つゆ", "鍋スープ", "柿", "栗", "新米"]


def _brand_prefix(brand_name: str) -> str:
    brand_name = (brand_name or "Cymbal Retail").strip()
    if os.environ.get("BRAND_PREFIX"):
        return os.environ["BRAND_PREFIX"].strip()
    if brand_name.endswith(" Retail") and len(brand_name) > 7:
        return brand_name[:-7].strip()
    return brand_name


def rebrand(s: str | None, brand_name: str = "Cymbal Retail") -> str | None:
    if not s:
        return s
    for a, b in REBRAND:
        s = s.replace(a, b)
    brand_name = (brand_name or "Cymbal Retail").strip()
    if brand_name != "Cymbal Retail":
        prefix = _brand_prefix(brand_name)
        s = s.replace("Cymbal Retail", brand_name)
        s = s.replace("Cymbal", prefix)
    return s


def jan(seed: str) -> str:
    """Deterministic 13-digit JAN-like code with a valid EAN-13 check digit (prefix 49)."""
    h = int(hashlib.sha1(seed.encode()).hexdigest(), 16)
    body = "49" + str(h % 10**10).zfill(10)
    s = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body))
    return body + str((10 - s % 10) % 10)


def sale_price(ex: int, rate: float) -> int:
    p = int(ex * (1 - rate))
    p = (p // 10) * 10 + 8 if p >= 100 else max(p, 1)
    return min(p, ex - 1)


def t(key, vals):
    vals = [str(v) for v in (vals if isinstance(vals, list) else [vals]) if v not in (None, "", [])]
    return {"key": key, "value": {"text": vals}} if vals else None


def n(key, val):
    return {"key": key, "value": {"numbers": [float(val)]}} if val is not None else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.environ.get("CATALOG_JSONL", f"{REPO_ROOT}/seed/catalog/products_retail.jsonl"))
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--brand-name", default=os.environ.get("BRAND_NAME", "Cymbal Retail"))
    ap.add_argument("--blueprint-dir", default=BP_DIR)
    ap.add_argument("--images-dir", default=IMG_DIR)
    ap.add_argument("--seed", type=int, default=20261111)
    ap.add_argument("--available-time", default=None,
                    help="fixed availableTime (ISO) so re-generation keeps existing rows byte-identical (default: now)")
    ap.add_argument("--pending-image-prefix", default=None,
                    help="emit items whose base_id starts with this prefix even if their declared image is not "
                         "generated yet")
    a = ap.parse_args()
    base_url = a.base_url.rstrip("/")
    brand_name = (a.brand_name or "Cymbal Retail").strip()
    brand_prefix = _brand_prefix(brand_name)
    loyalty = [tmpl.format(brand_prefix=brand_prefix) for tmpl in LOYALTY_TEMPLATES]
    rnd = random.Random(a.seed)
    now_iso = a.available_time or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    existing = set(os.listdir(a.images_dir)) if os.path.isdir(a.images_dir) else set()

    products, used_imgs, seen_titles, problems = [], set(), set(), []

    def bp_order(p):
        b = os.path.basename(p)
        return (3 if b.startswith("k_kansai_") else 2 if b.startswith("v_otc_") else 1 if b.startswith("w_") else 0, p)

    for path in sorted(glob.glob(f"{a.blueprint_dir}/*.json"), key=bp_order):
        bp = json.load(open(path, encoding="utf-8"))
        for it in bp.get("items", []):
            imgs = [f for f in it.get("images", []) if f in existing]
            if not imgs and a.pending_image_prefix and it.get("base_id", "").startswith(a.pending_image_prefix):
                imgs = list(it.get("images", []))[:1]
                problems.append(f"pending image: {it.get('base_id')}")
            if not imgs:
                problems.append(f"no image: {it.get('base_id')}")
                continue
            path_ = it["category_path"]
            top = path_[0]
            seasonal = CURRENT_MONTH in (it.get("season_months") or [])
            food = top not in NONFOOD_TOPS and bool(it.get("storage_type"))
            for v in it.get("variants", []):
                raw_title = rebrand(v["title"].strip(), "Cymbal Retail")
                title = rebrand(v["title"].strip(), brand_name)
                if title in seen_titles:
                    problems.append(f"dup title: {title}"); continue
                seen_titles.add(title)
                # Keep JAN deterministic against canonical Cymbal title so SKUs do not change on brand rename
                pid = jan(f"{it['base_id']}|{raw_title}")
                reg_ex = int(v["price_tax_excluded"])
                hot = any(k in title for k in HOT_KEYWORDS)
                on_sale = rnd.random() < (0.45 if hot else 0.18)
                cur_ex = sale_price(reg_ex, rnd.choice([0.1, 0.15, 0.2, 0.25, 0.3])) if on_sale else reg_ex
                tax = 1 + (float(it.get("tax_rate") or 8) / 100)
                cur_in, reg_in = math.floor(cur_ex * tax), math.floor(reg_ex * tax)
                discount = round((1 - cur_in / reg_in) * 100, 1) if on_sale else 0.0
                promos = [rnd.choice(PROMOS if food else PROMOS_GM)] if on_sale else []
                if rnd.random() < 0.08:
                    promos.append(rnd.choice(loyalty))
                labels = ([it["storage_type"]] if food else []) + list(it.get("labels") or []) + (["鮮度＋"] if "鮮度+" in title or "鮮度＋" in title else []) \
                    + (["旬"] if seasonal else [])
                attr_src = {**(it.get("attributes") or {}), **(v.get("attributes") or {})}
                drug_class, age_min = attr_src.get("drug_class"), attr_src.get("age_min")
                symptoms = list(attr_src.get("symptoms") or [])
                abuse_control = attr_src.get("abuse_control")
                tags = list(dict.fromkeys(labels + (["お買い得"] if on_sale else []) + [path_[-1]] + symptoms))
                allergens = (it.get("allergens") or []) if food else []
                desc = rebrand(it.get("description", "").strip(), brand_name)
                material, color, capacity = attr_src.get("material"), attr_src.get("color"), attr_src.get("capacity")
                if capacity and v.get("size") and "capacity" not in (v.get("attributes") or {}):
                    capacity = None
                if food:
                    extra = " / ".join(x for x in [f"内容量：{v.get('size')}" if v.get("size") else "",
                                                    f"産地：{v.get('origin')}" if v.get("origin") else "",
                                                    f"保存方法：{it['storage_type'].replace('食品', '')}",
                                                    f"特定原材料：{'・'.join(allergens)}" if allergens else ""] if x)
                else:
                    extra = " / ".join(x for x in [f"区分：{drug_class}" if drug_class else "",
                                                    f"対象年齢：{age_min:g}歳以上" if age_min else "",
                                                    f"サイズ・容量：{v.get('size')}" if v.get("size") else "",
                                                    f"素材：{material}" if material else "",
                                                    f"カラー：{color}" if color else "",
                                                    f"容量：{capacity}" if capacity else "",
                                                    f"生産国：{v.get('origin')}" if v.get("origin") else ""] if x)
                attrs = [
                    t("top_category", top), n("price_tax_excluded", cur_ex), n("original_price_tax_excluded", reg_ex),
                    t("on_sale", "true" if on_sale else "false"), n("discount_rate", discount), t("promo_text", promos),
                    t("size", v.get("size")), t("storage_type", it.get("storage_type") if food else None), t("labels", labels),
                    t("origin", v.get("origin")), t("allergens", allergens or ["なし"]) if food else None,
                    t("material", material), t("color", color), t("capacity", capacity),
                    t("brand_line", rebrand(v.get("brand"), brand_name)),
                    t("is_seasonal", "true" if seasonal else "false"),
                    {"key": "season_months", "value": {"numbers": [float(m) for m in it.get("season_months") or []]}}
                    if it.get("season_months") else None,
                    t("base_id", it["base_id"]),
                    t("dishes", it.get("dishes") or []),
                    t("is_food", "true" if food else "false"),
                    t("drug_class", drug_class), t("symptoms", symptoms),
                    n("age_min", age_min), t("abuse_control", abuse_control),
                ]
                rec = {
                    "id": pid, "type": "PRIMARY", "title": title,
                    "brands": [rebrand(v["brand"], brand_name)] if v.get("brand") else [],
                    "categories": [" > ".join(path_)],
                    "description": (desc + ("\n" + extra if extra else ""))[:5000],
                    "languageCode": "ja",
                    "attributes": [x for x in attrs if x],
                    "tags": tags,
                    "priceInfo": {"currencyCode": "JPY", "price": float(cur_in), "originalPrice": float(reg_in)},
                    "availability": "IN_STOCK" if rnd.random() > 0.03 else "OUT_OF_STOCK",
                    "availableTime": now_iso,
                    "uri": f"{base_url}/?product={pid}",
                    "images": [{"uri": f"{base_url}/img/products/{f}", "width": 600, "height": 600} for f in imgs],
                    "conditions": ["NEW"],
                    "rating": {"averageRating": round(rnd.uniform(3.6, 4.8), 1), "ratingCount": rnd.randint(3, 320)},
                }
                products.append(rec)
                used_imgs.update(imgs)

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        for r in products:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    credits, seen = [], set()
    cpath = f"{a.blueprint_dir}/credits.jsonl"
    if os.path.exists(cpath):
        for line in open(cpath, encoding="utf-8"):
            c = json.loads(line)
            if c["file"] in used_imgs and c["file"] not in seen:
                seen.add(c["file"]); credits.append(c)
        os.makedirs(a.images_dir, exist_ok=True)
        json.dump(credits, open(f"{a.images_dir}/credits.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    missing_credit = sorted(used_imgs - seen) if os.path.exists(cpath) else []

    print(json.dumps({"products": len(products), "images_used": len(used_imgs), "credits": len(credits),
                      "missing_credit": missing_credit[:20], "problems": problems[:30],
                      "on_sale": sum(1 for p in products if p["priceInfo"]["price"] < p["priceInfo"]["originalPrice"])},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
