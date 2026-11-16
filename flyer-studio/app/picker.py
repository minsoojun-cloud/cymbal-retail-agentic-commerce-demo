"""Deterministic product scoring & candidate selection for weekly chirashi auto-pickup.

Combines:
  1. Sale / discount rate (`on_sale`, `discount_rate`)
  2. Promotional campaigns (`promo_text`)
  3. Seasonality (`is_seasonal`, `season_months`)
  4. Popularity (`rating * log10(10 + rating_count)`)
  5. Theme alignment (keywords matched against title, category, dishes, labels)
  6. Target household fit (family of 4 -> large packs/kid-friendly dishes; seniors -> small portions/fish/deli; single/time-saving -> frozen/meal kits)
  7. Local community origin (`origin` matching store region -> 地産地消 boost)
"""
from __future__ import annotations

import collections
import datetime as dt
import math
import re
from typing import Any

from .repository import FlyerRepository

BULK_WORDS = ("業務用",)

# Japanese retail food commemorative days observed in the 93-flyer survey & standard supermarket calendar
FOOD_ANNIVERSARIES: dict[str, list[dict[str, Any]]] = {
    "11-11": [
        {"name": "鮭の日", "keywords": ["鮭", "サーモン"], "category": "お魚・水産加工品"},
        {"name": "チーズの日", "keywords": ["チーズ"], "category": "卵・乳製品・豆乳・デザート"},
        {"name": "麺の日", "keywords": ["うどん", "そば", "ラーメン", "パスタ", "麺"], "category": "お米・麺・インスタント"},
    ],
    "11-15": [
        {"name": "七五三（お祝い食卓）", "keywords": ["刺身", "寿司", "赤飯", "鯛", "黒毛和牛", "ケーキ"], "category": "お魚・水産加工品"},
    ],
    "11-19": [
        {"name": "ボジョレー・ワイン解禁", "keywords": ["ワイン", "チーズ", "生ハム", "ローストビーフ"], "category": "お酒・ノンアルコール"},
    ],
    "11-22": [
        {"name": "いい夫婦の日（ごちそうディナー）", "keywords": ["ステーキ", "黒毛和牛", "刺身", "寿司", "ケーキ", "ワイン"], "category": "お肉・お肉加工品"},
    ],
    "11-29": [
        {"name": "いい肉の日（29の日・肉の大市）", "keywords": ["牛", "豚", "鶏", "焼肉", "ステーキ", "すき焼き"], "category": "お肉・お肉加工品"},
    ],
}

THEME_SYNONYMS: dict[str, list[str]] = {
    "秋": ["秋", "鮭", "きのこ", "しめじ", "えのき", "舞茸", "さつまいも", "栗", "柿", "りんご", "梨", "新米", "さんま", "鍋"],
    "野菜": ["野菜", "キャベツ", "ブロッコリー", "白菜", "大根", "トマト", "玉ねぎ", "じゃがいも", "にんじん", "ほうれん草", "小松菜", "レタス", "きのこ"],
    "旬": ["旬", "季節", "新米", "秋", "鍋", "みかん", "りんご", "ぶどう", "柿", "鮭", "ぶり", "きのこ"],
    "鍋": ["鍋", "白菜", "ねぎ", "きのこ", "しめじ", "えのき", "豆腐", "しらたき", "鶏もも", "豚バラ", "たら", "つみれ", "鍋つゆ", "ぽん酢", "うどん"],
    "新米": ["新米", "こしひかり", "米", "ごはん", "鮭", "明太子", "納豆", "漬物", "海苔", "味噌汁"],
    "肉": ["牛", "豚", "鶏", "もも", "ロース", "バラ", "カルビ", "ステーキ", "焼肉", "すき焼き", "ハンバーグ", "ウインナー", "唐揚"],
    "魚": ["まぐろ", "サーモン", "鮭", "ぶり", "さば", "あじ", "えび", "いか", "たこ", "刺身", "寿司", "うなぎ"],
    "家計": ["ベーシック", "徳用", "大パック", "均一", "たまご", "牛乳", "豆腐", "納豆", "もやし", "食パン", "うどん"],
    "時短": ["お惣菜", "ミールキット", "冷凍", "弁当", "餃子", "唐揚", "コロッケ", "レトルト", "レンジ"],
}


def extract_theme_terms(theme: str, period_from: str = "", period_to: str = "") -> list[str]:
    raw = (theme or "").strip()
    terms: list[str] = []
    for token in re.split(r"[\s・、,／/「」『』（）()！!〜~]+", raw):
        token = token.strip()
        if len(token) >= 2 and token not in ("特集", "フェア", "セール", "今週", "チラシ", "大売出し", "お買い得"):
            terms.append(token.lower())
    for key, syns in THEME_SYNONYMS.items():
        if key in raw:
            for s in syns:
                if s.lower() not in terms:
                    terms.append(s.lower())
    for ann in matching_anniversaries(period_from, period_to):
        for kw in ann.get("keywords", []):
            if kw.lower() not in terms:
                terms.append(kw.lower())
    return terms


def matching_anniversaries(period_from: str = "", period_to: str = "") -> list[dict[str, Any]]:
    try:
        d0 = dt.date.fromisoformat(period_from[:10]) if period_from else dt.date(2026, 11, 11)
        d1 = dt.date.fromisoformat(period_to[:10]) if period_to else d0 + dt.timedelta(days=6)
    except ValueError:
        d0 = dt.date(2026, 11, 11)
        d1 = d0 + dt.timedelta(days=6)
    out: list[dict[str, Any]] = []
    cur = d0
    steps = 0
    while cur <= d1 and steps <= 31:
        mmdd = cur.strftime("%m-%d")
        for a in FOOD_ANNIVERSARIES.get(mmdd, []):
            out.append({"date": cur.isoformat(), "mmdd": cur.strftime("%-m/%-d"), **a})
        cur += dt.timedelta(days=1)
        steps += 1
    return out


def parse_month(period_from: str = "") -> int:
    if period_from and len(period_from) >= 7:
        try:
            return int(period_from[5:7])
        except ValueError:
            pass
    return 11


def popularity_score(n: dict) -> float:
    return float(n.get("rating") or 0.0) * math.log10(10 + int(n.get("rating_count") or 0))


def target_fit_score(n: dict, target: str) -> tuple[float, str]:
    t = (target or "").strip()
    if not t:
        return 0.0, ""
    hay = n["_hay"]
    cat = n.get("category") or ""
    pack = n.get("pack_type") or ""
    boost = 0.0
    reason = ""

    # Family / 30s-40s housewife / kids
    if any(k in t for k in ("家族", "ファミリー", "主婦", "4人", "3人", "子ども", "キッズ", "育ち盛り", "弁当")):
        if pack == "大パック":
            boost += 1.0
            reason = "ご家族向け大容量"
        if any(k in hay for k in ("カレー", "ハンバーグ", "唐揚", "餃子", "焼肉", "とんかつ", "オムライス", "パスタ", "シチュー", "ウインナー", "ポテト")):
            boost += 0.9
            reason = reason or "ご家族・お子様に人気の献立"
        if "ベビー・キッズ" in cat or "お菓子" in cat:
            boost += 0.4

    # Seniors / small households / 2-person
    if any(k in t for k in ("シニア", "少人数", "2人", "夫婦", "ご年配", "60代", "70代", "健康")):
        if pack == "少量・1人前":
            boost += 1.1
            reason = "食べきり・適量サイズ"
        if any(k in cat for k in ("お魚", "野菜", "豆腐", "お惣菜")) or any(
            k in hay for k in ("刺身", "煮物", "焼き魚", "塩さば", "西京", "黒豆", "ひじき", "筑前煮", "国産", "減塩", "オーガニック")
        ):
            boost += 0.9
            reason = reason or "和食・健康志向におすすめ"

    # Singles / busy dual-income / time-saving
    if any(k in t for k in ("単身", "一人暮らし", "1人", "共働き", "時短", "忙しい", "働く")):
        if any(k in cat for k in ("お惣菜・ミールキット", "冷凍食品・アイス")) or any(
            k in hay for k in ("ミールキット", "レンジ", "弁当", "1人前", "小分け", "レトルト", "簡単")
        ):
            boost += 1.2
            reason = "時短・すぐ食べられる便利品"

    return boost, reason


def score_product(n: dict, month: int, theme_terms: list[str], target: str = "",
                  store_prefecture: str = "") -> tuple[float, list[str], str]:
    """Compute composite chirashi pickup score, badges, and selection reason."""
    s = 0.0
    tags: list[str] = []
    reasons: list[str] = []

    if n.get("on_sale"):
        disc = float(n.get("discount_rate") or 0.0)
        s += 1.2 + 3.0 * disc
        pct = int(round(disc * 100))
        tags.append("特価")
        reasons.append(f"{pct}%OFF特価" if pct >= 5 else "今週の特価")

    promo = n.get("promo_text") or ""
    if promo:
        s += 0.8
        reasons.append(promo)

    season_months = n.get("season_months") or []
    if n.get("is_seasonal") or (month in season_months):
        s += 1.1
        tags.append("旬")
        reasons.append("今が旬の食材")

    pop = popularity_score(n)
    s += 0.08 * pop
    if float(n.get("rating") or 0) >= 4.5 and int(n.get("rating_count") or 0) >= 80:
        tags.append("人気商品")

    if theme_terms:
        hits = [term for term in theme_terms if term in n["_hay"]]
        if hits:
            title_hits = [term for term in hits if term in n["flyer_name"].lower() or term in n["category"].lower()]
            s += 1.8 * min(len(hits), 3) + (1.2 if title_hits else 0.0)
            reasons.insert(0, f"テーマ「{hits[0]}」関連")

    t_boost, t_reason = target_fit_score(n, target)
    if t_boost > 0:
        s += t_boost
        if t_reason:
            reasons.append(t_reason)

    origin = n.get("origin") or ""
    if store_prefecture and store_prefecture[:2] in origin:
        s += 0.9
        tags.insert(0, "地産地消")
        reasons.insert(0, f"地元・{origin}")
    elif "国産" in origin or "県産" in origin or "北海道産" in origin:
        s += 0.25

    reason_str = "・".join(dict.fromkeys([r for r in reasons if r])) or f"★{n.get('rating', 4.2)} 人気定番"
    return s, list(dict.fromkeys(tags)), reason_str


def is_excluded(n: dict) -> bool:
    if not n.get("image") or n.get("availability") == "OUT_OF_STOCK":
        return True
    title = n.get("title") or ""
    if any(w in title for w in BULK_WORDS):
        return True
    if int(n.get("price_tax_excluded") or 0) <= 0:
        return True
    return False


def select_candidates_for_template(
    repo: FlyerRepository,
    resolved_template: dict[str, Any],
    theme: str = "",
    target: str = "",
    period_from: str = "",
    period_to: str = "",
    store_prefecture: str = "",
    locked_product_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Select ranked product candidates per zone (3x each zone's slot count) with image deduplication."""
    month = parse_month(period_from)
    theme_terms = extract_theme_terms(theme, period_from, period_to)
    locked = set(locked_product_ids or set())

    # Score all eligible products once
    all_scored: list[tuple[float, dict, list[str], str]] = []
    for n in repo.items.values():
        if is_excluded(n) or n["id"] in locked:
            continue
        sc, tags, reason = score_product(n, month, theme_terms, target, store_prefecture)
        all_scored.append((sc, n, tags, reason))
    all_scored.sort(key=lambda t: -t[0])

    used_images: set[str] = {
        repo.items[pid]["image"] for pid in locked if pid in repo.items and repo.items[pid].get("image")
    }
    used_ids: set[str] = set(locked)

    zone_candidates: dict[str, list[dict[str, Any]]] = {}
    zone_deterministic_picks: dict[str, list[dict[str, Any]]] = {}

    zones = resolved_template.get("zones") or []
    total_requested = sum(len(z.get("slots") or []) for z in zones)
    per_sub_cap = 2 if total_requested <= 36 else (4 if total_requested <= 72 else 8)

    for z in zones:
        zid = z["id"]
        need = max(1, len(z.get("slots") or []))
        cand_limit = max(need * 3, 9)
        allowed_cats = set(z.get("categories") or [])
        is_uniform = z.get("zone_type") == "uniform_price"
        uniform_ex = int(z.get("uniform_price_ex") or 99)

        sub_counts: collections.Counter = collections.Counter()
        cands: list[dict[str, Any]] = []

        # Pass 1: matching zone categories (and price proximity for uniform zones)
        for sc, n, tags, reason in all_scored:
            if n["id"] in used_ids or n["image"] in used_images:
                continue
            if allowed_cats and n["category"] not in allowed_cats:
                continue
            if is_uniform and not (60 <= n["price_tax_excluded"] <= uniform_ex * 2.2):
                continue
            sub = " > ".join((n.get("category_path") or n["category"]).split(" > ")[:2])
            if len(cands) < need and sub_counts[sub] >= per_sub_cap:
                continue
            sub_counts[sub] += 1
            item = {k: v for k, v in n.items() if not k.startswith("_")}
            item["pickup_score"] = round(sc, 2)
            item["pickup_tags"] = tags
            item["pickup_reason"] = reason
            cands.append(item)
            if len(cands) >= cand_limit:
                break

        # Pass 2: if zone still needs items, relax category/sub-category constraints
        if len(cands) < need:
            cand_ids = {c["id"] for c in cands}
            for sc, n, tags, reason in all_scored:
                if n["id"] in used_ids or n["id"] in cand_ids or n["image"] in used_images:
                    continue
                if allowed_cats and n["category"] not in allowed_cats and len(cands) < need // 2:
                    continue
                item = {k: v for k, v in n.items() if not k.startswith("_")}
                item["pickup_score"] = round(sc, 2)
                item["pickup_tags"] = tags
                item["pickup_reason"] = reason
                cands.append(item)
                cand_ids.add(n["id"])
                if len(cands) >= cand_limit:
                    break

        # Reserve the top `need` deterministic picks so the next zone gets distinct images
        picks = cands[:need]
        for p in picks:
            used_ids.add(p["id"])
            used_images.add(p["image"])

        zone_candidates[zid] = cands
        zone_deterministic_picks[zid] = picks

    return {
        "month": month,
        "theme_terms": theme_terms,
        "anniversaries": matching_anniversaries(period_from, period_to),
        "zone_candidates": zone_candidates,
        "zone_deterministic_picks": zone_deterministic_picks,
    }
