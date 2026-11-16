"""Dinner-set composer for recommend_dinner_set (CONTRACT.md v2).

Builds 「今夜の夕食」 product sets (主菜・副菜・汁物・主食・デザート/果物) from:
  - persona: household size, family_preferences (per-member like_keywords), allergies / exclude_keywords, dislikes,
    cooking style (時短)
  - purchase-history frequency (product level + leaf-category level)
  - current sale items (attributes.on_sale) and seasonal items (attributes.is_seasonal / season_months)

Pure functions only (no I/O) so that it is fully unit-testable; server.py supplies the catalog pool, the profile and
the history rows. Deterministic for (customer, date, request) but varies by day through a small hash jitter.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
import re
from dataclasses import dataclass, field

JST = dt.timezone(dt.timedelta(hours=9))

ROLE_MAIN, ROLE_SIDE, ROLE_SOUP, ROLE_STAPLE, ROLE_DESSERT = "主菜", "副菜", "汁物", "主食", "デザート・果物"
ROLE_ORDER = [ROLE_MAIN, ROLE_SIDE, ROLE_SOUP, ROLE_STAPLE, ROLE_DESSERT]
TAG_FREQ, TAG_FAMILY, TAG_SALE, TAG_SEASON, TAG_QUICK = "よく購入", "家族の好み", "特価", "旬", "時短"
TAG_ORDER = [TAG_FREQ, TAG_FAMILY, TAG_SALE, TAG_SEASON, TAG_QUICK]

# Always excluded from dinner sets (persona dislike 「大容量すぎる業務用サイズ」 + non-dinner items).
BULK_WORDS = ["業務用", "大容量", "徳用", "お徳用", "まとめ買い", "ケース", "箱買い", "ギフト", "贈答", "訳あり"]
NON_DINNER_WORDS = ["弁当", "おにぎり", "サンドイッチ", "おせち", "オードブル", "パーティー", "離乳", "1歳頃", "ベビー",
                    "あら", "刺身", "お刺身", "寿司", "ふりかけ", "お茶漬け"]
# Allergen spelling variants (persona exclude_keywords are merged on top).
ALLERGEN_VARIANTS = {
    "えび": ["えび", "エビ", "海老", "シュリンプ", "ｴﾋﾞ", "shrimp", "桜えび", "甘えび", "えびせん"],
    "かに": ["かに", "カニ", "蟹"],
    "卵": ["卵", "玉子", "たまご", "エッグ"],
    "乳": ["乳", "ミルク", "チーズ", "バター"],
    "小麦": ["小麦"],
    "そば": ["そば", "蕎麦"],
    "落花生": ["落花生", "ピーナッツ"],
}
DISLIKE_HINTS = {"激辛": ["激辛", "麻辣", "旨辛", "辛口", "ハバネロ"], "麻辣": ["麻辣", "花椒"]}
QUICK_WORDS = ["ミールキット", "焼くだけ", "揚げるだけ", "温めるだけ", "下味", "味付", "カット野菜", "カット済", "レンジ", "骨取り",
               "店内調理", "フリーズドライ", "生みそタイプ", "即席", "そのまま", "惣菜", "パウチ", "自然解凍"]
SEASON_NOUNS = ["秋鮭", "さんま", "戻りがつお", "ぶり", "さば", "たら", "牡蠣", "さつまいも", "栗", "かぼちゃ", "れんこん",
                "ごぼう", "里芋", "しめじ", "まいたけ", "しいたけ", "えのき", "きのこ", "白菜", "大根", "長ねぎ", "春菊",
                "ほうれん草", "小松菜", "ブロッコリー", "柿", "りんご", "ぶどう", "シャインマスカット", "梨", "ラ・フランス",
                "みかん", "キウイ", "鶏つくね", "鍋つゆ"]
MAIN_NOUNS = ["秋鮭", "銀鮭", "紅鮭", "鮭", "塩さば", "さば", "ぶり", "さんま", "あじ", "ほっけ", "たら", "さわら", "かれい",
              "唐揚げ", "からあげ", "ハンバーグ", "生姜焼", "とんかつ", "豚こま", "豚ロース", "豚バラ", "鶏もも", "鶏むね",
              "手羽", "牛こま", "焼き鳥", "餃子", "鶏つくね", "つくね", "寄せ鍋", "キムチ鍋", "豆乳鍋", "水炊き", "すき焼き",
              "しゃぶしゃぶ", "ちゃんちゃん焼き", "回鍋肉", "麻婆", "カレー"]
NUM = str.maketrans("０１２３４５６７８９，", "0123456789,")


# ── product normalisation ────────────────────────────────────────────────────


def _attr_map(attributes) -> dict:
    """Retail-schema attributes (list of {key, value:{text, numbers}} or dict) → {key: [values]}."""
    out = {}
    if isinstance(attributes, dict):
        for k, v in attributes.items():
            if isinstance(v, dict):
                out[k] = list(v.get("text") or v.get("numbers") or [])
            elif isinstance(v, (list, tuple)):
                out[k] = list(v)
            else:
                out[k] = [v]
        return out
    for a in attributes or []:
        v = a.get("value") or {}
        out[a.get("key")] = list(v.get("text") or v.get("numbers") or [])
    return out


def _first(v, default=None):
    if isinstance(v, (list, tuple)):
        return v[0] if v else default
    return default if v is None else v


def _truthy(v) -> bool:
    return str(_first(v, "")).lower() == "true"


def normalize_product(row: dict) -> dict | None:
    """BigQuery cymbal.products / data/products_retail.jsonl row (Retail schema) → compact dict."""
    pid = row.get("id")
    if not pid:
        return None
    a = _attr_map(row.get("attributes"))
    cats = list(row.get("categories") or [])
    cat = cats[0] if cats else ""
    parts = [p.strip() for p in cat.split(">")]
    pi = row.get("priceInfo") or {}
    price = int(round(float(pi.get("price") or 0)))
    original = int(round(float(pi.get("originalPrice") or price or 0)))
    if original < price:
        original = price
    imgs = row.get("images") or []
    rating = row.get("rating") or {}
    months = []
    for m in a.get("season_months") or []:
        try:
            months.append(int(float(m)))
        except (TypeError, ValueError):
            pass
    return {
        "id": str(pid),
        "title": row.get("title") or "",
        "category": cat,
        "top": parts[0] if parts else "",
        "mid": parts[1] if len(parts) > 1 else "",
        "leaf": parts[-1] if parts else "",
        "price": price,
        "original_price": original,
        "on_sale": _truthy(a.get("on_sale")) or (0 < price < original),
        "discount_rate": float(_first(a.get("discount_rate"), 0) or 0),
        "seasonal": _truthy(a.get("is_seasonal")),
        "season_months": months,
        "size": str(_first(a.get("size"), "") or ""),
        "allergens": [str(x) for x in a.get("allergens") or []],
        "dishes": [str(x) for x in a.get("dishes") or []],
        "is_food": _truthy(a.get("is_food")) if a.get("is_food") else True,
        "image": (imgs[0].get("uri") if imgs and isinstance(imgs[0], dict) else "") or "",
        "rating": float(rating.get("averageRating") or 0),
        "rating_count": int(rating.get("ratingCount") or 0),
        "availability": row.get("availability") or "IN_STOCK",
        "description": row.get("description") or "",
    }


def normalize_summary(s: dict) -> dict:
    """search_products summary item (server.summarize_product) → compact dict (Retail-search fallback pool)."""
    cat = (s.get("topCategory") or "") + (" > " + s["subtitle"] if s.get("subtitle") else "")
    parts = [p.strip() for p in cat.split(">")]
    return {
        "id": s.get("productId"), "title": s.get("title") or "", "category": cat, "top": parts[0], "mid": parts[-1],
        "leaf": parts[-1], "price": int(s.get("price") or 0), "original_price": int(s.get("originalPrice") or s.get("price") or 0),
        "on_sale": bool(s.get("onSale")), "discount_rate": float(s.get("discountRate") or 0), "seasonal": False,
        "season_months": [], "size": s.get("size") or "",
        "allergens": [x.strip() for x in str(s.get("allergens") or "").split("/") if x.strip()], "dishes": [],
        "is_food": True, "image": (s.get("imageUris") or [""])[0], "rating": float((s.get("rating") or {}).get("average") or 0),
        "rating_count": int((s.get("rating") or {}).get("count") or 0), "availability": "IN_STOCK", "description": "",
    }


# ── persona helpers ─────────────────────────────────────────────────────────


def exclusion_words(profile: dict) -> list:
    words = set()
    for w in profile.get("exclude_keywords") or []:
        words.add(str(w))
    allergens = [str(a.get("allergen")) for a in profile.get("allergies") or [] if isinstance(a, dict) and a.get("allergen")]
    for fp in profile.get("family_preferences") or []:
        allergens += [str(x) for x in fp.get("allergies") or []]
    for al in allergens:
        words.add(al)
        for k, vs in ALLERGEN_VARIANTS.items():
            if k in al or al in vs:
                words.update(vs)
    return sorted(w for w in words if w)


def dislike_words(profile: dict) -> list:
    out = set()
    for d in profile.get("dislikes") or []:
        for k, vs in DISLIKE_HINTS.items():
            if k in str(d):
                out.update(vs)
    return sorted(out)


def allergy_note(profile: dict) -> str:
    notes = []
    names = {fp.get("relation"): fp.get("call_name") or fp.get("name") for fp in profile.get("family_preferences") or []}
    for a in profile.get("allergies") or []:
        if isinstance(a, dict) and a.get("allergen"):
            who = names.get(a.get("member")) or a.get("member") or ""
            notes.append(f"{a['allergen']}（登録済みのアレルギー情報）")
    return "・".join(notes)


def family_rules(profile: dict) -> list:
    """→ [(call_name, relation, label, keyword)] from family_preferences[].like_keywords (falls back to likes)."""
    rules = []
    for fp in profile.get("family_preferences") or []:
        call = fp.get("call_name") or (fp.get("name", "") + "さん")
        lk = fp.get("like_keywords") or []
        if lk:
            for g in lk:
                for kw in g.get("keywords") or []:
                    rules.append((call, fp.get("relation", ""), g.get("label") or kw, kw))
        else:
            for like in fp.get("likes") or []:
                rules.append((call, fp.get("relation", ""), like, like))
    return rules


def is_kid(relation: str) -> bool:
    return relation in ("長男", "長女", "次男", "次女", "三男", "三女", "子ども", "息子", "娘")


# ── history ─────────────────────────────────────────────────────────────────


def short_name(title: str) -> str:
    """「カナダ産 豚こま切れ 300g」→「豚こま切れ」, 「[鮮度+] 北海道産 生秋鮭 切り身 2切（約160g）」→「生秋鮭 切り身」."""
    t = re.sub(r"\[[^\]]*\]|【[^】]*】|（[^）]*）|\([^)]*\)", " ", title or "")
    t = re.sub(r"\bCymbal\s*(ベーシック|セレクト|オーガニック)?\s*", " ", t)
    toks = [x for x in t.split() if x]
    toks = [x for x in toks if not re.search(r"(産|県|国内|国産)$", x)]
    toks = [x for x in toks if not re.search(r"[0-9０-９]", x) and x not in ("約", "生", "徳用")]
    return " ".join(toks[:2]) or (title or "")[:12]


def history_signals(rows: list) -> dict:
    """Aggregate purchase rows → {by_product:{id: times}, by_leaf:{leaf: (times, short)}, top:[{...}]}."""
    by_product, info, by_leaf = {}, {}, {}
    for r in rows or []:
        pid = str(r.get("product_id") or "")
        if not pid:
            continue
        times = int(r.get("times") or 1)
        by_product[pid] = by_product.get(pid, 0) + times
        info.setdefault(pid, (r.get("product_title") or "", r.get("category") or ""))
    for pid, n in by_product.items():
        title, cat = info[pid]
        leaf = cat.split(">")[-1].strip() if cat else ""
        if not leaf:
            continue
        t, best, best_n = by_leaf.get(leaf, (0, "", 0))
        if n > best_n:
            best, best_n = short_name(title), n
        by_leaf[leaf] = (t + n, best, best_n)
    top = sorted(by_product.items(), key=lambda kv: -kv[1])
    return {
        "by_product": by_product,
        "by_leaf": {k: (v[0], v[1]) for k, v in by_leaf.items()},
        "top": [{"product_id": pid, "title": info[pid][0], "short": short_name(info[pid][0]), "times": n}
                for pid, n in top[:30]],
    }


# ── request parsing ─────────────────────────────────────────────────────────

BUDGET_RE = re.compile(r"([0-9０-９,，]{3,7})\s*円")


def parse_request(text: str) -> dict:
    t = (text or "").translate(NUM)
    req = {"meat": False, "fish": False, "nabe": False, "curry": False, "quick": False, "light": False,
           "kids": False, "staple": False, "budget": 0, "servings": 0, "text": text or ""}
    if re.search(r"肉|唐揚|からあげ|ハンバーグ|生姜焼|とんかつ|ステーキ|焼肉|ガッツリ|がっつり", t):
        req["meat"] = True
    if re.search(r"魚|鮭|さば|ぶり|さんま|あじ|たら|海鮮", t):
        req["fish"] = True
    if re.search(r"鍋|なべ|あったか|温ま", t):
        req["nabe"] = True
    if re.search(r"カレー", t):
        req["curry"] = True
    if re.search(r"時短|簡単|手軽|すぐ|忙し|楽|ラク|疲れ|手抜き|5分|10分|15分|20分", t):
        req["quick"] = True
    if re.search(r"ヘルシー|さっぱり|軽め|野菜たっぷり|野菜多め", t):
        req["light"] = True
    if re.search(r"子ども|子供|キッズ|こども", t):
        req["kids"] = True
    if re.search(r"ご飯も|ごはんも|主食|お米|白米", t):
        req["staple"] = True
    m = BUDGET_RE.search(t)
    if m and re.search(r"予算|以内|以下|まで|円で|円くらい|円程度", t):
        try:
            req["budget"] = int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    m = re.search(r"([0-9]{1,2})\s*人(?:分|前|で)", t)
    if m:
        req["servings"] = int(m.group(1))
    return req


# ── classification ──────────────────────────────────────────────────────────

FISH_MIDS = {"鮮魚", "鮭・サーモン", "鮮魚・切り身", "塩さば・塩鮭", "さば・あじ", "ぶり・はまち", "さんま・いわし", "漬け魚",
             "骨取り魚", "味付け魚", "たら・白身魚", "焼魚・煮魚", "さわら・かじき", "フライ・揚げ物", "干物", "塩干・干物"}
MEAT_MIDS = {"豚肉", "鶏肉", "牛肉", "味付け肉", "ひき肉・ハンバーグ", "ひき肉加工品", "ひき肉"}
DELI_MAIN_MIDS = {"揚げ物", "焼き物", "ミールキット", "揚げるだけ", "中華惣菜", "餃子・焼売"}
FROZEN_MAIN_MIDS = {"冷凍 からあげ・揚げ物", "冷凍 お肉おかず", "冷凍 中華惣菜", "冷凍 餃子・焼売", "冷凍 和風おかず", "冷凍 肉・肉加工品"}
VEG_MIDS = {"野菜", "葉物野菜", "きのこ", "カット野菜", "カット野菜・水煮", "果菜・花菜", "洋野菜", "もやし・スプラウト",
            "有機・特別栽培野菜", "香味野菜", "根菜"}
DELI_SIDE_MIDS = {"サラダ", "和惣菜", "和え物・小鉢", "卵料理", "お惣菜"}
SOUP_MIDS = {"インスタントスープ・みそ汁", "インスタント", "スープ", "汁物・スープ", "インスタントスープ"}
DESSERT_MIDS = {"デザート", "ゼリー", "和スイーツ"}


def _text(p: dict) -> str:
    return p["title"] + " " + p["category"]


def size_grams(p: dict):
    s = (p.get("size") or "") + " " + p["title"]
    s = s.translate(NUM)
    m = re.search(r"([0-9.]+)\s*kg", s, re.I)
    if m:
        return float(m.group(1)) * 1000
    m = re.search(r"([0-9]+)\s*g(?![a-z])", s)
    if m:
        return float(m.group(1))
    return None


def pieces(p: dict):
    """「4切」「3〜4人前」「8個」「2尾」→ number of portions (None if unknown)."""
    s = ((p.get("size") or "") + " " + p["title"]).translate(NUM)
    m = re.search(r"([0-9]+)\s*[〜~～-]\s*([0-9]+)\s*人前", s)
    if m:
        return int(m.group(2))
    m = re.search(r"([0-9]+)\s*(人前|人分|切|尾|枚|個|本|食|皿分)", s)
    if m:
        return int(m.group(1))
    return None


def blocked(p: dict, excl: list, dislikes: list) -> bool:
    if p.get("availability", "IN_STOCK") != "IN_STOCK" or not p.get("is_food", True) or p["price"] <= 0:
        return True
    hay = " ".join([p["title"], p["category"], " ".join(p["allergens"]), " ".join(p["dishes"]), p.get("description", "")])
    if any(w in hay for w in excl):
        return True
    title_cat = _text(p)
    if any(w in title_cat for w in dislikes):
        return True
    if any(w in p["title"] for w in BULK_WORDS):
        return True
    if any(w in title_cat for w in NON_DINNER_WORDS):
        return True
    g = size_grams(p)
    if g and g > 1200:
        return True
    return False


def classify(p: dict) -> set:
    """→ set of (role, kind) the product can fill."""
    t, top, mid, title = _text(p), p["top"], p["mid"], p["title"]
    out = set()
    if top == "お魚・水産加工品" and (mid in FISH_MIDS or re.search(r"鮭|さば|ぶり|さんま|あじ|たら|ほっけ|切り身", title)):
        if not re.search(r"缶|ほぐし|フレーク|ちりめん|しらす|明太|たらこ|いくら|筋子|うに", title):
            out.add((ROLE_MAIN, "fish"))
    if top == "お肉・お肉加工品" and mid in MEAT_MIDS and not re.search(r"ハム|ソーセージ|ベーコン|サラダチキン|レバー|ホルモン|砂肝|ラード", title):
        out.add((ROLE_MAIN, "nabe_protein" if "鍋" in t else "meat"))
    if top == "お惣菜・ミールキット" and (mid in DELI_MAIN_MIDS or re.search(r"ハンバーグ|唐揚|とんかつ|生姜焼|焼き鳥", title)):
        kind = "fish" if re.search(r"鮭|さば|ぶり|魚|さんま|たら", title) else "meat"
        out.add((ROLE_MAIN, kind))
    if top == "冷凍食品・アイス" and (mid in FROZEN_MAIN_MIDS or re.search(r"ハンバーグ|唐揚|からあげ", title)):
        out.add((ROLE_MAIN, "meat"))
    if top == "お惣菜・ミールキット" and mid == "鍋セット":
        out.add((ROLE_MAIN, "nabe_set"))
    if "鍋つゆ" in t or "鍋の素" in t:
        out.add((ROLE_SOUP, "nabe_soup"))
    if "カレールー" in t:
        out.add((ROLE_MAIN, "curry_roux"))
    if "カレー用" in title and top == "お肉・お肉加工品":
        out.add((ROLE_MAIN, "curry_meat"))
    if top == "お魚・水産加工品" and "鍋" in title:
        out.add((ROLE_MAIN, "nabe_protein"))
    if top == "お肉・お肉加工品" and re.search(r"しゃぶしゃぶ|つくね|鍋用", title):
        out.add((ROLE_MAIN, "nabe_protein"))
    if top == "お魚・水産加工品" and re.search(r"たら|鱈", title) and re.search(r"切り身|鍋", title):
        out.add((ROLE_MAIN, "nabe_protein"))
    # sides
    if top == "野菜・果物" and mid in VEG_MIDS:
        if not re.search(r"味噌汁用|みそ汁用|汁物|豚汁用|煮込み用|カレー用|鍋用", title):
            out.add((ROLE_SIDE, "veg"))
        if re.search(r"白菜|ねぎ|春菊|水菜|しめじ|えのき|しいたけ|まいたけ|きのこ|鍋", title):
            out.add((ROLE_SIDE, "nabe_veg"))
    if top == "お惣菜・ミールキット" and mid in DELI_SIDE_MIDS and not re.search(r"唐揚|とんかつ|ハンバーグ|コロッケ|弁当", title):
        out.add((ROLE_SIDE, "deli"))
    if re.search(r"玉子焼|卵焼|だし巻", title) and not re.search(r"明太|たらこ|辛|わさび", title) and top in ("冷凍食品・アイス", "お惣菜・ミールキット", "卵・乳製品・豆乳・デザート"):
        out.add((ROLE_SIDE, "kids"))
    if "コーン" in title and (top in ("缶詰・粉類・乾物", "冷凍食品・アイス", "野菜・果物")) and not re.search(r"フレーク|スープ|油|クリーム", title):
        out.add((ROLE_SIDE, "kids"))
    if top == "冷凍食品・アイス" and mid in ("冷凍 野菜", "冷凍野菜") and re.search(r"ほうれん草|ブロッコリー|いんげん|枝豆|かぼちゃ|コーン|ミックス", title):
        out.add((ROLE_SIDE, "veg"))
    if top == "豆腐・納豆・練り物" and mid == "豆腐":
        out.add((ROLE_SIDE, "tofu"))
        if re.search(r"絹|木綿", title):
            out.add((ROLE_SOUP, "tofu"))
            out.add((ROLE_SIDE, "nabe_tofu"))
    # soup
    if top == "お米・麺・インスタント" and (mid in SOUP_MIDS or "みそ汁" in title) and re.search(r"みそ汁|味噌汁|スープ|すまし|豚汁|お吸い物", title):
        if not re.search(r"カップ麺|ラーメン|春雨|はるさめ|ポタージュ.*箱|業務", title):
            out.add((ROLE_SOUP, "instant"))
    if top == "お惣菜・ミールキット" and mid == "汁物・スープ":
        out.add((ROLE_SOUP, "deli"))
    if "味噌汁用" in title or "汁物" in p["leaf"]:
        out.add((ROLE_SOUP, "ingredient"))
    # staple
    if top == "お米・麺・インスタント" and re.search(r"パックご飯|レンジご飯", p["mid"] + p["leaf"]) and not re.search(
            r"炊き込み|きのこ|五目|赤飯|チャーハン|ピラフ|おこわ|ドリア|雑炊|粥|リゾット|ビビンバ|釜めし|わかめ|ちらし", title):
        out.add((ROLE_STAPLE, "rice"))
    if top in ("お米・麺・インスタント", "冷凍食品・アイス") and "うどん" in title and not re.search(r"カップ|スープ|お好み|焼うどん|焼きうどん|皿うどん|即席|カレー|天ぷら|きつね", title):
        out.add((ROLE_STAPLE, "udon"))
    # dessert / fruit
    if top == "野菜・果物" and mid == "果物":
        out.add((ROLE_DESSERT, "fruit"))
    if top == "卵・乳製品・豆乳・デザート" and mid in DESSERT_MIDS:
        out.add((ROLE_DESSERT, "dessert"))
    return out


# ── scoring ─────────────────────────────────────────────────────────────────


def jitter(*parts) -> float:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:4], "big") / 2**32


def season_noun(p: dict) -> str:
    for n in SEASON_NOUNS:
        if n in p["title"]:
            return n
    return short_name(p["title"]).split(" ")[0]


def season_reason(p: dict) -> str:
    if re.search(r"鍋|しゃぶ", p["title"]) and not any(n in p["title"] for n in SEASON_NOUNS[:-1]):
        return "鍋の季節にぴったり"
    return f"旬の{season_noun(p)}"


def main_noun(p: dict) -> str:
    for n in MAIN_NOUNS:
        if n in p["title"]:
            return {"からあげ": "唐揚げ", "生姜焼": "生姜焼き"}.get(n, n)
    return short_name(p["title"])


@dataclass
class Ctx:
    profile: dict
    hist: dict
    req: dict
    today: dt.date
    customer_id: str
    servings: int
    rules: list = field(default_factory=list)
    quick_pref: bool = False


def signals_for(p: dict, ctx: Ctx) -> list:
    """→ [(tag, weight, reason)] ordered by weight."""
    out = []
    t = p["title"]
    n = ctx.hist["by_product"].get(p["id"], 0)
    if n >= 2:
        out.append((TAG_FREQ, 2.5 + min(n, 10) * 0.12, f"よく購入されている{short_name(t)}"))
    else:
        lt = ctx.hist["by_leaf"].get(p["leaf"])
        if lt and lt[0] >= 4:
            out.append((TAG_FREQ, 1.3, f"いつもの{lt[1]}と同じ定番"))
    seen_member = set()
    for call, rel, label, kw in ctx.rules:
        if call in seen_member or kw not in t:
            continue
        seen_member.add(call)
        w = 2.4 if is_kid(rel) else 1.6
        out.append((TAG_FAMILY, w, f"{call}の好きな{label}"))
    if p["on_sale"]:
        d = int(round(p["discount_rate"])) if p["discount_rate"] else 0
        out.append((TAG_SALE, 1.0 + min(d, 40) / 50, f"今週特価（{d}%OFF）" if d else "今週特価"))
    in_season = p["seasonal"] or (ctx.today.month in p["season_months"])
    if in_season:
        out.append((TAG_SEASON, 1.6, season_reason(p)))
    if any(w in t or w in p["category"] for w in QUICK_WORDS):
        w = 2.2 if ctx.req["quick"] else (0.7 if ctx.quick_pref else 0.3)
        out.append((TAG_QUICK, w, "下ごしらえ不要で時短"))
    return sorted(out, key=lambda x: -x[1])


SINGLE_SERVING_RE = re.compile(r"(?<![0-9〜~～-])1\s*(人前|人分|食(?!入)|食分)(?![0-9×xX])")
SINGLE_PIECE_DESSERT_RE = re.compile(r"(?<![0-9〜~～-])1\s*(個|カップ|本)(?![0-9×xX入])")


def portion_qty(p: dict, role: str, servings: int) -> int:
    """Packs needed for `servings` people. Family/multi packs (3〜4人前, 5食入, 1房, 3パック, 4切 …) → 1; only clearly
    single-serving items (1人前, 1食, a single pudding …) scale with servings; mains with small packs scale by portions."""
    if servings <= 0:
        return 1
    txt = ((p.get("size") or "") + " " + p["title"]).translate(NUM)
    multi = "×" in txt or "入" in txt  # 5食入 / 3個入 / 170g×5 are multi packs
    if not multi and SINGLE_SERVING_RE.search(txt):
        return max(1, min(servings, 6))
    if role == ROLE_DESSERT and p["top"] != "野菜・果物" and not multi and SINGLE_PIECE_DESSERT_RE.search(txt):
        return max(1, min(servings, 6))
    if role != ROLE_MAIN:
        return 1
    n = pieces(p)
    if n and n < 20:
        return max(1, min(3, math.ceil(servings / n)))
    g = size_grams(p)
    if g and p["top"] in ("お肉・お肉加工品", "お魚・水産加工品", "お惣菜・ミールキット", "冷凍食品・アイス"):
        per = 80 if "カレー用" in p["title"] else 90
        return max(1, min(3, math.ceil(servings * per / g)))
    return 1


def score(p: dict, role: str, kind: str, ctx: Ctx, extra: float = 0.0) -> float:
    s = sum(w for _, w, _ in signals_for(p, ctx)) + extra
    if p["rating_count"]:
        s += (p["rating"] - 3.8) * 0.5
    if role == ROLE_MAIN:
        n = pieces(p)
        if n and ctx.servings and ctx.servings <= n <= ctx.servings + 2:
            s += 0.8
        elif n and n < ctx.servings / 2:
            s -= 0.6
    s += jitter(ctx.customer_id, ctx.today.isoformat(), ctx.req["text"], p["id"]) * (1.6 if role == ROLE_MAIN else 0.9)
    if role == ROLE_MAIN and (p["seasonal"] or ctx.today.month in p["season_months"]):
        s += 0.8  # 旬の主菜を優先
    if ctx.req["budget"]:
        s -= p["price"] * portion_qty(p, role, ctx.servings) / max(ctx.req["budget"], 1) * 3.0
    elif role == ROLE_MAIN and p["price"] * portion_qty(p, role, ctx.servings) > 2500:
        s -= 1.0
    if ctx.req["light"] and role in (ROLE_SIDE,) and kind == "veg":
        s += 0.8
    return s


# ── composition ─────────────────────────────────────────────────────────────

# Set templates: list of slots (role, allowed kinds, bonus keywords regex or None).
TEMPLATES = {
    "fish": [(ROLE_MAIN, {"fish"}, r"秋鮭|鮭|さば|ぶり"), (ROLE_SIDE, {"kids"}, None),
             (ROLE_SIDE, {"veg", "deli"}, r"きのこ|しめじ|まいたけ|ほうれん草|小松菜|おひたし|和え"),
             (ROLE_SOUP, {"instant", "deli", "tofu"}, r"みそ汁|豚汁"), (ROLE_DESSERT, {"fruit"}, None)],
    "meat": [(ROLE_MAIN, {"meat"}, r"唐揚|からあげ|ハンバーグ|生姜焼|豚こま|鶏もも|とんかつ"),
             (ROLE_SIDE, {"veg", "deli", "kids"}, r"サラダ|キャベツ|ブロッコリー|コーン"),
             (ROLE_SOUP, {"instant", "deli", "tofu"}, r"みそ汁|豚汁|スープ"), (ROLE_STAPLE, {"rice"}, None),
             (ROLE_DESSERT, {"fruit", "dessert"}, None)],
    "nabe": [(ROLE_MAIN, {"nabe_protein", "nabe_set"}, r"鍋|つくね|しゃぶ"), (ROLE_SIDE, {"nabe_veg"}, r"白菜|しめじ|ねぎ|えのき"),
             (ROLE_SOUP, {"nabe_soup"}, r"寄せ鍋|豆乳|水炊き|ちゃんこ"), (ROLE_STAPLE, {"udon"}, None),
             (ROLE_DESSERT, {"fruit"}, None)],
    "curry": [(ROLE_MAIN, {"curry_roux"}, r"中辛"), (ROLE_MAIN, {"curry_meat"}, r"豚|鶏|牛"),
              (ROLE_SIDE, {"veg", "deli", "kids"}, r"サラダ|コーン|ブロッコリー"), (ROLE_STAPLE, {"rice"}, None),
              (ROLE_DESSERT, {"fruit"}, None)],
}
CONCEPTS = {
    "fish": "{main}を主役に、{side}と{soup}を添えた野菜もとれる和の献立。デザートは{dessert}で。",
    "meat": "{main}でボリューム満点。{side}と{soup}でバランスよく、家族みんなが喜ぶ献立。",
    "nabe": "{main}と{side}をたっぷり入れて、{soup}で温まる冬支度の鍋。〆は{staple}で。",
    "curry": "家族みんなで食べられる中辛カレーに{side}を添えて。ご飯は大盛りでどうぞ。",
}
NAMES = {"fish": "{noun}の和定食セット", "meat": "{noun}の家族ごはんセット", "nabe": "{noun}のあったか鍋セット",
         "curry": "中辛カレーの家族ごはんセット"}


def _pick(pool: list, role: str, kinds: set, bonus_re, ctx: Ctx, used: set, used_other: set, budget_left=None):
    best, best_s = None, -1e9
    for p, roles in pool:
        if p["id"] in used:
            continue
        ks = {k for r, k in roles if r == role}
        if not ks & kinds:
            continue
        extra = 0.0
        if bonus_re and re.search(bonus_re, p["title"]):
            extra += 1.0
        if p["id"] in used_other:
            extra -= 2.0
        kind = next(iter(ks & kinds))
        if kind == "kids":
            extra += 1.0
        if budget_left is not None and p["price"] * portion_qty(p, role, ctx.servings) > budget_left:
            continue
        s = score(p, role, kind, ctx, extra)
        if s > best_s:
            best, best_s = (p, kind), s
    return best


def _item(p: dict, role: str, ctx: Ctx) -> dict:
    sig = signals_for(p, ctx)
    tags = sorted({t for t, _, _ in sig}, key=TAG_ORDER.index)
    reasons = []
    for t, _, r in sig:
        if r not in reasons:
            reasons.append(r)
        if len(reasons) == 2:
            break
    if not reasons:
        defaults = {ROLE_MAIN: f"{ctx.servings}人分にちょうどよい{p['size'] or '量'}", ROLE_SIDE: "彩りと野菜をプラス",
                    ROLE_SOUP: "汁物で献立を完成", ROLE_STAPLE: "ご飯大盛りにも", ROLE_DESSERT: "食後のデザートに"}
        reasons.append(defaults.get(role, "献立に合う一品"))
    qty = portion_qty(p, role, ctx.servings)
    if qty > 1:
        unit = "個" if role == ROLE_DESSERT else ("食" if SINGLE_SERVING_RE.search(p["title"] + " " + (p.get("size") or "")) else "パック")
        reasons = [f"{ctx.servings}人分で{qty}{unit}"] + reasons[:1]
    return {"role": role, "product_id": p["id"], "title": p["title"], "price": p["price"], "quantity": qty,
            "subtotal": p["price"] * qty, "image": p["image"], "on_sale": p["on_sale"], "tags": tags,
            "reason": "・".join(reasons)}


def _noun1(title: str) -> str:
    for n in ("玉子焼き", "卵焼き", "コーン", "ポテトサラダ", "サラダ", "うどん", "パックご飯", "ごはん", "ご飯"):
        if n in title:
            return "甘い玉子焼き" if n == "玉子焼き" and "甘い" in title else n
    for n in SEASON_NOUNS:
        if n in title:
            return n
    return short_name(title).split(" ")[0]


def _soup_noun(title: str) -> str:
    for n in ("豚汁", "みそ汁", "味噌汁", "すまし汁", "お吸い物", "スープ", "鍋つゆ"):
        if n in title:
            return {"味噌汁": "みそ汁"}.get(n, n)
    if "豆腐" in title or "とうふ" in title:
        return "豆腐のみそ汁"
    return short_name(title).split(" ")[0]


def compose_set(kind: str, pool: list, ctx: Ctx, used_other: set) -> dict | None:
    slots = list(TEMPLATES[kind])
    want_staple = ctx.req["staple"] or kind in ("curry", "nabe")
    used, items = set(), []
    budget_left = ctx.req["budget"] or None
    for role, kinds, bonus in slots:
        if role == ROLE_STAPLE and not want_staple:
            continue
        got = _pick(pool, role, kinds, bonus, ctx, used, used_other, budget_left)
        if not got and role == ROLE_SIDE and "kids" in kinds:  # no kid-friendly side → any side
            got = _pick(pool, role, {"veg", "deli"}, bonus, ctx, used, used_other, budget_left)
        if not got:
            continue
        p, _ = got
        used.add(p["id"])
        it = _item(p, role, ctx)
        items.append(it)
        if budget_left is not None:
            budget_left -= it["subtotal"]
    items = items[:5]
    mains = [i for i in items if i["role"] == ROLE_MAIN]
    if not mains or len(items) < 4:
        return None
    items.sort(key=lambda i: ROLE_ORDER.index(i["role"]))
    by_role = {}
    for i in items:
        by_role.setdefault(i["role"], i)
    pmap = {p["id"]: p for p, _ in pool}
    noun = main_noun(pmap[mains[0]["product_id"]])
    fmt = {
        "main": noun,
        "side": _noun1(by_role[ROLE_SIDE]["title"]) if ROLE_SIDE in by_role else "副菜",
        "soup": _soup_noun(by_role[ROLE_SOUP]["title"]) if ROLE_SOUP in by_role else "汁物",
        "dessert": season_noun(pmap[by_role[ROLE_DESSERT]["product_id"]]) if ROLE_DESSERT in by_role else "果物",
        "staple": _noun1(by_role[ROLE_STAPLE]["title"]) if ROLE_STAPLE in by_role else "うどん",
    }
    return {"kind": kind, "name": NAMES[kind].format(noun=noun), "concept": CONCEPTS[kind].format(**fmt),
            "items": items, "total_tax_included": sum(i["subtotal"] for i in items)}


def choose_kinds(req: dict, today: dt.date) -> list:
    if req["nabe"]:
        order = ["nabe", "fish", "meat"]
    elif req["curry"]:
        order = ["curry", "meat", "fish"]
    elif req["meat"] and not req["fish"]:
        order = ["meat", "curry" if today.toordinal() % 2 else "nabe", "fish"]
    elif req["fish"] and not req["meat"]:
        order = ["fish", "nabe", "meat"]
    else:
        # default: fish-centred 和定食 (さくら) first; alternatives meat (健太・蓮) + nabe/curry alternating by day
        order = ["fish", "meat", "nabe" if today.toordinal() % 2 == 0 else "curry"]
    return order


def recommend(profile: dict, history_rows: list, catalog: list, request: str = "", budget_jpy: int = 0,
              servings: int = 0, customer_id: str = "", today: dt.date | None = None) -> dict:
    today = today or dt.datetime.now(JST).date()
    req = parse_request(request)
    if budget_jpy and int(budget_jpy) > 0:
        req["budget"] = int(budget_jpy)
    servings = int(servings or 0) or req["servings"] or int(profile.get("household_size") or 0) or 4
    excl, dislikes = exclusion_words(profile), dislike_words(profile)
    hist = history_signals(history_rows)
    cooking = str(profile.get("cooking_style") or "")
    ctx = Ctx(profile=profile, hist=hist, req=req, today=today, customer_id=customer_id or profile.get("customer_id", ""),
              servings=servings, rules=family_rules(profile), quick_pref="時短" in cooking)
    seen, pool, excluded = set(), [], 0
    for p in catalog:
        if not p or p["id"] in seen:
            continue
        seen.add(p["id"])
        if blocked(p, excl, dislikes):
            excluded += 1
            continue
        roles = classify(p)
        if roles:
            pool.append((p, roles))
    sets, used_mains = [], set()
    for kind in choose_kinds(req, today):
        used_all = {i["product_id"] for s in sets for i in s["items"]}
        s = compose_set(kind, pool, ctx, used_all)
        if s and s["items"][0]["product_id"] not in used_mains:
            used_mains.add(s["items"][0]["product_id"])
            sets.append(s)
        if len(sets) == 3:
            break
    name = profile.get("name") or ""
    who = f"{name}さんご家族の" if name else ""
    theme = f"{who}今夜の夕食セット（{sets[0]['name'].replace('セット', '')}）" if sets else f"{who}今夜の夕食セット"
    family = []
    for fp in profile.get("family_preferences") or []:
        family.append(f"{fp.get('call_name') or fp.get('name')}: {'・'.join(fp.get('likes') or [])}"
                      + (f"（{'・'.join(fp.get('ng'))}）" if fp.get("ng") else ""))
    seasonal = []
    for s in sets:
        for i in s["items"]:
            if TAG_SEASON in i["tags"]:
                n = i["reason"].split("旬の", 1)[-1].split("・")[0] if "旬の" in i["reason"] else short_name(i["title"])
                if n not in seasonal:
                    seasonal.append(n)
    out = {
        "theme": theme,
        "servings": servings,
        "budget_jpy": req["budget"] or 0,
        "signals": {
            "frequent": list(dict.fromkeys(h["short"] for h in hist["top"]))[:6],
            "family": family,
            "sale_count": sum(1 for p, _ in pool if p["on_sale"]),
            "seasonal": seasonal[:6],
            "excluded": allergy_note(profile),
        },
        "sets": sets,
        "pool_size": len(pool),
        "excluded_count": excluded,
    }
    if sets:
        out["show_products_on_page_args"] = show_args(out, 0)
        for i in range(1, len(sets)):
            sets[i]["show_products_on_page_args"] = show_args(out, i)
    return out


def show_args(res: dict, idx: int = 0) -> dict:
    """Ready-to-pass args for the client function show_products_on_page (set idx, grouped by role)."""
    s = res["sets"][idx]
    sections, ids, reasons, qtys = [], [], [], []
    for role in ROLE_ORDER:
        its = [i for i in s["items"] if i["role"] == role]
        if not its:
            continue
        sections.append({"label": role, "product_ids": [i["product_id"] for i in its],
                         "reasons": [i["reason"] for i in its], "tags": [i["tags"] for i in its],
                         "quantities": [i["quantity"] for i in its]})
        ids += [i["product_id"] for i in its]
        reasons += [i["reason"] for i in its]
        qtys += [i["quantity"] for i in its]
    theme = res["theme"] if idx == 0 else res["theme"].split("（")[0] + f"（{s['name'].replace('セット', '')}）"
    return {"message": f"{s['name']}（{s['total_tax_included']:,}円・税込）", "theme": theme,
            "product_ids": ids, "reasons": reasons, "quantities": qtys, "sections": sections}
