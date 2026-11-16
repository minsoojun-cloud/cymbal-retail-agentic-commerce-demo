#!/usr/bin/env python3
"""ペルソナ CR-0001（さくら）向けに実商品IDを用いた約12か月分の週次購買履歴（架空データ）を生成するスクリプト。

使い方:
  python3 generate_history.py [--products ../catalog/products_retail.jsonl] [--out purchase_history.jsonl] \
      [--end 2026-10-03] [--weeks 53] [--seed 20251001]

- 週1回（土曜日の週末まとめ買い）、1注文あたり 8〜15 点。
- ペルソナ設定（和食・魚好き、中辛カレー、子育て家庭）と季節ルールに基づき商品を選択。
- 前年10月（例: 2025-10）には 秋鮭、さんま、さつまいも、しめじ/まいたけ、梨、中辛カレールー、
  豚こま、鍋つゆ を優先的に含める（カタログに該当商品がない場合はスキップしてログ出力）。
- えび関連商品は除外（長女のアレルギー対応）。シード固定により決定論的に出力。
出力スキーマ (JSONL): order_id, customer_id, order_date (YYYY-MM-DD), product_id, product_title, category,
  quantity, unit_price_tax_included, amount
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import random
import sys

DEFAULT_CATALOG = os.environ.get(
    "CATALOG_JSONL",
    str(Path(__file__).resolve().parent.parent / "catalog" / "products_retail.jsonl"),
)

CUSTOMER_ID = "CR-0001"
EXCLUDE = ("えび", "エビ", "海老", "シュリンプ", "桜えび", "甘えび")
EXCLUDE_TOP = ("酒", "ワイン", "ビール", "ペット", "ベビー", "医薬", "たばこ")
EXCLUDE_SOFT = ("激辛", "麻辣", "業務用")
PROCESSED = ("焼き", "蒸し", "パクっと", "スープカレー", "フレーク", "チップス", "菓子", "冷凍", "ふりかけ", "干し", "切り干し")

MUST_OCT = [
    ("秋鮭", [["秋鮭"], ["生鮭"], ["鮭", "切身"], ["鮭"], ["さけ"], ["サーモン"]]),
    ("さんま", [["さんま"], ["秋刀魚"], ["サンマ"]]),
    ("さつまいも", [["さつまいも"], ["紅はるか"], ["シルクスイート"], ["安納"]]),
    ("しめじ", [["しめじ"]]),
    ("まいたけ", [["まいたけ"], ["舞茸"]]),
    ("梨", [["梨"], ["幸水"], ["豊水"], ["新高"]]),
    ("中辛カレールー", [["カレー", "中辛"], ["カレールー"], ["カレー", "ルウ"], ["カレー", "ルー"]]),
    ("豚こま", [["豚", "こま"], ["豚", "小間"], ["豚", "切り落とし"], ["豚", "切落し"]]),
    ("鍋つゆ", [["鍋つゆ"], ["鍋スープ"], ["鍋", "つゆ"], ["鍋", "スープ"], ["鍋の素"]]),
]

STAPLES = [
    ("牛乳", [["牛乳"]], 0.95), ("卵", [["卵"], ["たまご"]], 0.9), ("食パン", [["食パン"]], 0.7),
    ("納豆", [["納豆"]], 0.8), ("豆腐", [["豆腐"]], 0.75), ("ヨーグルト", [["ヨーグルト"]], 0.6),
    ("バナナ", [["バナナ"]], 0.7), ("にんじん", [["にんじん"]], 0.6), ("たまねぎ", [["たまねぎ"], ["玉ねぎ"]], 0.65),
    ("じゃがいも", [["じゃがいも"]], 0.45), ("キャベツ", [["キャベツ"]], 0.5), ("鶏もも", [["鶏", "もも"]], 0.5),
    ("豚こま", [["豚", "こま"], ["豚", "切り落とし"]], 0.5), ("鮭", [["鮭"]], 0.45), ("さば", [["さば"], ["鯖"]], 0.35),
    ("味噌", [["みそ"], ["味噌"]], 0.12), ("ねぎ", [["ねぎ"]], 0.4), ("もやし", [["もやし"]], 0.4),
    ("カット野菜", [["カット野菜"], ["千切り"], ["細切り"]], 0.35), ("ごぼう", [["ごぼう"]], 0.15),
    ("だいこん", [["大根"], ["だいこん"]], 0.3),
]

SEASONAL = {
    1: [("白菜", [["白菜"]]), ("ぶり", [["ぶり"]]), ("みかん", [["みかん"]]), ("鍋つゆ", [["鍋つゆ"], ["鍋スープ"]])],
    2: [("白菜", [["白菜"]]), ("いちご", [["いちご"]]), ("ぶり", [["ぶり"]]), ("鍋つゆ", [["鍋つゆ"], ["鍋スープ"]])],
    3: [("菜の花", [["菜の花"]]), ("いちご", [["いちご"]]), ("新たまねぎ", [["新たまねぎ"], ["新玉ねぎ"]])],
    4: [("たけのこ", [["たけのこ"]]), ("春キャベツ", [["春キャベツ"]]), ("新じゃが", [["新じゃが"]]), ("いちご", [["いちご"]])],
    5: [("アスパラ", [["アスパラ"]]), ("新たまねぎ", [["淡路島"], ["新たまねぎ"]]), ("かつお", [["かつお"]])],
    6: [("トマト", [["トマト"]]), ("きゅうり", [["きゅうり"]]), ("さくらんぼ", [["さくらんぼ"]])],
    7: [("とうもろこし", [["とうもろこし"]]), ("枝豆", [["枝豆"]]), ("すいか", [["すいか"]]), ("そうめん", [["そうめん"]])],
    8: [("なす", [["なす"]]), ("ピーマン", [["ピーマン"]]), ("桃", [["桃"]]), ("そうめん", [["そうめん"]])],
    9: [("ぶどう", [["ぶどう"]]), ("梨", [["梨"]]), ("さんま", [["さんま"]]), ("さつまいも", [["さつまいも"]])],
    10: [("きのこ", [["しめじ"], ["まいたけ"], ["えのき"]]), ("柿", [["柿"]]), ("栗", [["栗"]]), ("さつまいも", [["さつまいも"]]),
         ("秋鮭", [["秋鮭"], ["鮭"]]), ("れんこん", [["れんこん"]])],
    11: [("白菜", [["白菜"]]), ("りんご", [["りんご"]]), ("鍋つゆ", [["鍋つゆ"], ["鍋スープ"]]), ("里芋", [["さといも"], ["里芋"]])],
    12: [("白菜", [["白菜"]]), ("みかん", [["みかん"]]), ("ぶり", [["ぶり"]]), ("おでん", [["おでん"], ["大根"]])],
}

FILL_TOPS = ("野菜", "果物", "肉", "魚", "卵", "乳", "豆腐", "納豆", "パン", "米", "調味料", "冷凍", "惣菜")


def log(msg):
    print(msg, file=sys.stderr)


def load_products(path):
    prods = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            title = d.get("title") or ""
            cats = d.get("categories") or []
            attrs = {a["key"]: a.get("value", {}) for a in d.get("attributes", [])} if isinstance(d.get("attributes"), list) \
                else (d.get("attributes") or {})
            allergens = " ".join((attrs.get("allergens") or {}).get("text", []) if isinstance(attrs.get("allergens"), dict) else [])
            hay = " ".join([title, " ".join(cats), d.get("description") or "", allergens])
            if any(x in hay for x in EXCLUDE):
                continue
            top = cats[0].split(" > ")[0] if cats else ""
            if any(x in top for x in EXCLUDE_TOP):
                continue
            price = int(round(float((d.get("priceInfo") or {}).get("price") or 0)))
            if price <= 0:
                continue
            prods.append({
                "id": d["id"], "title": title, "cats": cats, "top": top, "price": price,
                "in_stock": d.get("availability", "IN_STOCK") == "IN_STOCK",
                "soft_bad": any(x in title for x in EXCLUDE_SOFT),
            })
    prods.sort(key=lambda p: p["id"])
    return prods


def candidates(prods, alternatives):
    """最初に一致した AND 条件グループの候補商品リストを返す（タイトル一致を優先）。"""
    for group in alternatives:
        hits = [p for p in prods if all(k in p["title"] for k in group)]
        if not hits:
            hits = [p for p in prods if all(k in p["title"] or any(k in c for c in p["cats"]) for k in group)]
        if hits:
            def processed(p):
                return any(w in p["title"] and not any(w in k for k in group) for w in PROCESSED)
            hits.sort(key=lambda p: (p["soft_bad"], processed(p), not p["in_stock"], len(p["title"]), p["id"]))
            return hits
    return []


def pick(rng, prods, alternatives, top_n=3):
    c = candidates(prods, alternatives)
    return rng.choice(c[:top_n]) if c else None


def qty_for(p, rng):
    t = p["title"]
    if any(k in t for k in ("牛乳", "納豆", "豆腐", "ヨーグルト")):
        return rng.choice([1, 2, 2])
    return 1 if p["price"] >= 500 else rng.choice([1, 1, 2])


def main():
    ap = argparse.ArgumentParser(description="ペルソナ CR-0001 用の週次購買履歴 JSONL を生成します。")
    ap.add_argument("--products", default=DEFAULT_CATALOG, help="商品カタログ JSONL のパス（既定: 環境変数 CATALOG_JSONL または ../catalog/products_retail.jsonl）")
    ap.add_argument("--out", default="purchase_history.jsonl", help="出力先 JSONL ファイルパス")
    ap.add_argument("--end", default=None, help="最終注文日 YYYY-MM-DD（既定: 今日より前の直近土曜日）")
    ap.add_argument("--weeks", type=int, default=53, help="生成する週数（既定: 53）")
    ap.add_argument("--seed", type=int, default=20251001, help="乱数シード（既定: 20251001）")
    a = ap.parse_args()

    rng = random.Random(a.seed)
    prods = load_products(a.products)
    if not prods:
        log("対象となる商品が見つかりませんでした")
        return 1
    log(f"対象商品数: {len(prods)}")

    if a.end:
        end = dt.date.fromisoformat(a.end)
    else:
        today = dt.date.today()
        end = today - dt.timedelta(days=(today.weekday() - 5) % 7 or 7)
    last_year = end.year - 1 if end.month >= 10 else end.year - 2
    dates = [end - dt.timedelta(weeks=i) for i in range(a.weeks)][::-1]
    oct_dates = [d for d in dates if d.year == last_year and d.month == 10]
    if not oct_dates:
        start = dt.date(last_year, 10, 4)
        start += dt.timedelta(days=(5 - start.weekday()) % 7)
        dates = sorted(set(dates) | {start + dt.timedelta(weeks=i) for i in range(4)})
        oct_dates = [d for d in dates if d.year == last_year and d.month == 10]

    must = []
    for label, alts in MUST_OCT:
        c = candidates(prods, alts)
        if c:
            must.append((label, c[:3]))
            log(f"[必須 {last_year}-10] {label:<8} -> {c[0]['id']} {c[0]['title']}")
        else:
            log(f"[必須 {last_year}-10] {label:<8} -> スキップ（該当商品なし）")

    fill_pool = [p for p in prods if any(t in p["top"] for t in FILL_TOPS) and not p["soft_bad"]] or prods
    rows = []
    for d in dates:
        order_id = f"CR-{d.strftime('%Y%m%d')}-0001"
        items = {}

        def add(p):
            if p and p["id"] not in items:
                items[p["id"]] = p

        target = rng.randint(8, 15)
        if d in oct_dates:
            idx = oct_dates.index(d)
            for j, (label, c) in enumerate(must):
                if idx == 0 or (idx + j) % 2 == 0:
                    add(rng.choice(c))
        for label, alts in SEASONAL.get(d.month, []):
            if rng.random() < 0.55:
                add(pick(rng, prods, alts))
        for label, alts, prob in STAPLES:
            if len(items) >= target:
                break
            if rng.random() < prob:
                add(pick(rng, prods, alts))
        guard = 0
        while len(items) < target and guard < 200:
            add(rng.choice(fill_pool))
            guard += 1

        for p in items.values():
            q = qty_for(p, rng)
            rows.append({
                "order_id": order_id, "customer_id": CUSTOMER_ID, "order_date": d.isoformat(),
                "product_id": p["id"], "product_title": p["title"], "category": p["cats"][0] if p["cats"] else "",
                "quantity": q, "unit_price_tax_included": p["price"], "amount": q * p["price"],
            })

    with open(a.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    n_orders = len({r["order_id"] for r in rows})
    log(f"出力完了: {len(rows)} 行 / {n_orders} 注文 ({dates[0]}..{dates[-1]}) -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
