"""CSV parsing and sample CSV generation for Live Enrichment testing."""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from .schema import CATEGORY_GROUPS, category_group

# Flexible header aliases (Japanese & English)
HEADER_MAP = {
    "sku": {"sku", "id", "p_cd", "product_id", "item_id", "商品コード", "商品id", "品番", "jan"},
    "title": {"title", "name", "product_name", "商品名", "タイトル", "品名"},
    "brand": {"brand", "brands", "maker", "ブランド", "メーカー"},
    "category": {"category", "categories", "category_path", "カテゴリ", "カテゴリー", "分類"},
    "description": {"description", "desc", "body", "説明文", "商品説明", "商品の説明", "詳細説明"},
    "price": {"price", "sale_price", "価格", "販売価格", "税込価格"},
    "product_url": {"product_url", "uri", "url", "link", "商品url", "リンク"},
    "image_url": {"image_url", "image", "image_link", "thumbnail", "画像url", "商品画像"},
    "group": {"group", "category_group", "カテゴリグループ"},
    "raw_attributes_json": {"raw_attributes_json", "raw_attributes", "attributes_json"},
}

SAMPLE_PRODUCTS = [
    {
        "sku": "CSV-FOOD-001",
        "title": "Cymbal 国産若鶏 ささみ竜田揚げ（冷凍）",
        "brand": "Cymbal",
        "category": "冷凍食品・アイス > 冷凍 おかず > からあげ・竜田揚げ",
        "description": "国産若鶏のささみをしょうゆベースの下味に漬け込み、片栗粉の衣でカラッと揚げました。凍ったまま電子レンジで温めるだけ（600Wで約2分30秒）。"
                       "お弁当のおかずや夕食のもう一品に。内容量：300g（約12個） / 原料原産地：国産 / 保存方法：-18℃以下で保存 / "
                       "特定原材料：小麦・大豆・鶏肉 / 賞味期限：製造日より12ヶ月",
        "price": 498,
        "product_url": "https://example.com/cymbal/p/CSV-FOOD-001",
        "image_url": "",
    },
    {
        "sku": "CSV-FOOD-002",
        "title": "北海道産 秋鮭 切り身 甘塩 4切",
        "brand": "",
        "category": "お魚・水産加工品 > 鮭・サーモン > 塩鮭",
        "description": "脂ののった北海道産の秋鮭を甘塩に仕上げた切り身。焼くだけで朝食やお弁当に。旬：9月〜11月。4切（約320g）。要冷蔵（10℃以下）。",
        "price": 698,
        "product_url": "https://example.com/cymbal/p/CSV-FOOD-002",
        "image_url": "",
        "origin": "北海道産",
    },
    {
        "sku": "CSV-GM-003",
        "title": "Cymbal キッチン 軽量 IH対応 深型フライパン 26cm",
        "brand": "Cymbal キッチン",
        "category": "キッチン・調理器具 > フライパン・鍋 > フライパン",
        "description": "アルミ鋳物ボディにチタンコートのフッ素樹脂加工で、こびりつきにくく軽い深型フライパン。炒め物も煮込みもこれ1つ。"
                       "IH・ガス火対応（IH 200V可）。食洗機対応。サイズ：直径26×深さ7.5cm、重量約780g。",
        "price": 2980,
        "product_url": "https://example.com/cymbal/p/CSV-GM-003",
        "image_url": "",
        "material": "アルミニウム合金（鋳物）・フッ素樹脂加工",
        "color": "ブラウン",
    },
]

SAMPLE_CSV_COLUMNS = [
    "sku", "title", "brand", "category", "description", "price", "product_url", "image_url",
    "size", "origin", "storage_type", "allergens", "material", "color",
]


def sample_csv_text() -> str:
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.DictWriter(buf, fieldnames=SAMPLE_CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for p in SAMPLE_PRODUCTS:
        writer.writerow({k: p.get(k, "") for k in SAMPLE_CSV_COLUMNS})
    return buf.getvalue()


def decode_csv_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp932", "shift_jis"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _norm_header(h: str) -> str:
    return re.sub(r"[\s_\-]+", "_", (h or "").strip().lower())


def _parse_price(val: Any) -> float | None:
    if val is None:
        return None
    s = re.sub(r"[^\d.]", "", str(val))
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_csv_text(text: str) -> tuple[list[dict], list[str]]:
    """Parse CSV text into normalized product dicts ready for enrichment."""
    text = (text or "").lstrip("\ufeff").strip()
    if not text:
        raise ValueError("CSVデータが空です")

    reader = csv.DictReader(io.StringIO(text))
    headers = [h for h in (reader.fieldnames or []) if h]
    if not headers:
        raise ValueError("CSVヘッダー行が見つかりません")

    # Map each column to canonical field or raw_attribute
    col_map: dict[str, str] = {}
    for h in headers:
        nh = _norm_header(h)
        matched = None
        for canon, aliases in HEADER_MAP.items():
            if nh in aliases or h.strip() in aliases:
                matched = canon
                break
        if matched and matched not in col_map.values():
            col_map[h] = matched
        else:
            col_map[h] = f"raw:{h.strip()}"

    products: list[dict] = []
    for idx, row in enumerate(reader, start=1):
        if not row or not any((v or "").strip() for v in row.values()):
            continue
        p: dict[str, Any] = {
            "sku": "",
            "title": "",
            "brand": "",
            "category": "",
            "description": "",
            "price": None,
            "product_url": "",
            "image_url": "",
            "group": "",
            "raw_attributes": {},
        }
        for h, val in row.items():
            if not h:
                continue
            v = (val or "").strip()
            if not v:
                continue
            target = col_map.get(h, f"raw:{h}")
            if target == "price":
                p["price"] = _parse_price(v)
            elif target == "raw_attributes_json":
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        for kv in parsed:
                            if isinstance(kv, dict) and kv.get("k"):
                                p["raw_attributes"][str(kv["k"])] = str(kv.get("v", ""))
                    elif isinstance(parsed, dict):
                        for rk, rv in parsed.items():
                            p["raw_attributes"][str(rk)] = str(rv)
                except Exception:
                    p["raw_attributes"]["raw_attributes_json"] = v
            elif target.startswith("raw:"):
                rk = target[4:]
                p["raw_attributes"][rk] = v
            else:
                p[target] = v

        if not p["sku"]:
            p["sku"] = f"CSV-{idx:04d}"
        if not p["title"]:
            p["title"] = p["raw_attributes"].get("title") or f"商品 {p['sku']}"
        if p["group"] not in CATEGORY_GROUPS:
            p["group"] = category_group(f"{p['category']} {p['title']}")
        if not p["category"]:
            p["category"] = CATEGORY_GROUPS.get(p["group"], "その他")
        products.append(p)

    if not products:
        raise ValueError("有効な商品行が見つかりませんでした")
    return products, headers
