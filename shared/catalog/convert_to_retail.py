"""Convert crawled Green Beans data into AI Commerce Search (Retail API) product JSONL.

Input : data/products_list.json (listing entities) + data/products_detail.jsonl (detail pages)
Output: data/products_retail.jsonl  (BigQuery `product` schema, one product per line)

Prices: priceInfo.price = 税込 current price, originalPrice = 税込 regular price.
        Tax-excluded prices are kept in attributes (price_tax_excluded / original_price_tax_excluded).
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
from datetime import datetime, timezone

IMG_SIZE = "500x500"


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def amount(d, *path):
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return num(d)


def text_attr(key, values):
    vals = [v for v in (values if isinstance(values, list) else [values]) if v not in (None, "")]
    return {"key": key, "value": {"text": [str(v)[:256] for v in vals][:400]}} if vals else None


def num_attr(key, value):
    return {"key": key, "value": {"numbers": [float(value)]}} if value is not None else None


FIELD_KEYS = {  # bopData.fields[].title -> attribute key
    "regionalInformation": "origin", "countryOfOrigin": "origin", "allergens": "allergens",
    "storage": "storage", "ingredients": "ingredients", "nutritionalData": "nutrition",
    "manufacturer": "manufacturer",
}


def convert(sku: str, lst: dict, det: dict | None, now_iso: str) -> dict:
    e = lst["listing"]
    bop = (det or {}).get("bop") or {}
    bp = bop.get("product") or {}
    bd = bop.get("bopData") or {}
    ld = (det or {}).get("ld") or {}

    title = bp.get("name") or e.get("name") or ld.get("name")
    brand = bp.get("brand") or e.get("brand")

    # ---- prices (税抜 / 税込) ----
    regular_ex = amount(bp, "price", "amount") or amount(e, "price", "original", "amount") \
        or amount(e, "price", "current", "amount")
    current_ex = amount(bp, "promoPrice", "amount") or amount(e, "price", "current", "amount") or regular_ex
    current_in = amount(bp, "grossPrice", "amount") or amount(e, "price", "gross", "amount")
    rate = (current_in / current_ex) if (current_in and current_ex) else (1.10 if e.get("alcohol") else 1.08)
    if current_in is None and current_ex is not None:
        current_in = math.floor(current_ex * rate)
    regular_in = math.floor(regular_ex * rate + 1e-6) if regular_ex else current_in
    if regular_in is None or regular_in < current_in:
        regular_in = current_in
    on_sale = bool(regular_ex and current_ex and current_ex < regular_ex)
    discount = round((1 - current_in / regular_in) * 100, 1) if on_sale and regular_in else 0.0

    # ---- categories (primary path + every listing breadcrumb the item appeared in) ----
    cats = []
    if e.get("categoryPath"):
        cats.append(" > ".join(e["categoryPath"]))
    for c in lst.get("seen_in", []):
        if c not in cats:
            cats.append(c)
    top = e.get("categoryPath", [None])[0] if e.get("categoryPath") else (cats[0].split(" > ")[0] if cats else None)

    # ---- images: ALL images ----
    imgs = []
    for p in bp.get("imagePaths") or []:
        imgs.append(f"{p}/{IMG_SIZE}.jpg")
    if not imgs:
        imgs = [i["src"] for i in e.get("images", []) if i.get("src")]
    if not imgs and ld.get("image"):
        imgs = ld["image"] if isinstance(ld["image"], list) else [ld["image"]]
    seen = set()
    images = [{"uri": u, "width": 500, "height": 500} for u in imgs if not (u in seen or seen.add(u))]

    # ---- promotions / tags ----
    promos = [o.get("description") for o in e.get("offers", []) if o.get("description")]
    promos += [p.get("description") for p in bop.get("bopPromotions") or [] if p.get("description")]
    promos = list(dict.fromkeys(strip_html(p) for p in promos if p))
    labels = [a.get("label") for a in (e.get("attributes") or bp.get("iconAttributes") or []) if a.get("label")]
    tags = list(dict.fromkeys(labels + (["お買い得"] if on_sale or promos else [])
                               + [c.split(" > ")[-1] for c in cats if any(k in c for k in ("旬", "季節", "鍋"))]))

    storage_type = next((l for l in labels if l in ("冷蔵食品", "冷凍食品", "常温食品")), None)

    attrs = [
        text_attr("top_category", top),
        num_attr("price_tax_excluded", current_ex),
        num_attr("original_price_tax_excluded", regular_ex),
        text_attr("on_sale", "true" if on_sale else "false"),
        num_attr("discount_rate", discount),
        text_attr("promo_text", promos[:5]),
        text_attr("size", (e.get("size") or {}).get("value") or bp.get("packSizeDescription")),
        text_attr("storage_type", storage_type),
        text_attr("labels", labels),
        text_attr("unit_price", _unit_price(e)),
    ]
    if e.get("guaranteedProductLife"):
        g = e["guaranteedProductLife"]
        attrs.append(text_attr("freshness_guarantee", f"{g.get('quantity')}{'日' if g.get('unit') == 'DAY' else g.get('unit')}"))
    for f in bd.get("fields") or []:
        key = FIELD_KEYS.get(f.get("title"))
        if key:
            attrs.append(text_attr(key, strip_html(f.get("content")).split("\n")[0][:256]))

    desc = strip_html(bd.get("detailedDescription") or ld.get("description"))

    rec = {
        "id": sku,
        "type": "PRIMARY",
        "title": title[:1000],
        "brands": [brand] if brand else [],
        "categories": cats or ["その他"],
        "description": desc[:5000],
        "languageCode": "ja",
        "attributes": [a for a in attrs if a],
        "tags": tags[:250],
        "priceInfo": {"currencyCode": "JPY", "price": float(current_in or 0), "originalPrice": float(regular_in or 0)},
        "availability": "IN_STOCK" if (bp.get("available", e.get("available", True))) else "OUT_OF_STOCK",
        "availableTime": now_iso,
        "uri": f"https://greenbeans.com/products/{sku}/details",
        "images": images,
        "conditions": ["NEW"],
    }
    rs = bp.get("ratingSummary") or e.get("ratingSummary") or {}
    avg, cnt = num(rs.get("overallRating")), int(rs.get("count") or 0)
    if avg and cnt and 1 <= avg <= 5:
        rec["rating"] = {"averageRating": avg, "ratingCount": cnt}
    return rec


def _unit_price(e):
    u = (e.get("price") or {}).get("unit") or {}
    a = amount(u, "current", "amount")
    suf = u.get("pricePerSuffix") or ""
    if a is None:
        return None
    if not suf and "100gram" in (u.get("label") or ""):
        suf = "/100g"
    return f"¥{int(a)}{suf}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    lst = json.load(open(os.path.join(args.data, "products_list.json"), encoding="utf-8"))
    det = {}
    dp = os.path.join(args.data, "products_detail.jsonl")
    if os.path.exists(dp):
        for line in open(dp, encoding="utf-8"):
            r = json.loads(line)
            det[r["sku"]] = r
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = args.out or os.path.join(args.data, "products_retail.jsonl")
    n = 0
    with open(out, "w", encoding="utf-8") as f:
        for sku, l in lst.items():
            rec = convert(sku, l, det.get(sku), now_iso)
            if not rec["title"] or not rec["images"]:
                continue
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"wrote {n} products ({len(det)} with detail) -> {out}")


if __name__ == "__main__":
    main()
