"""Scripted concierge (agentMode=mock, or when the live model is unavailable). Same SSE events as the live agent.

Covers the demo scenarios deterministically: fever / cold consultation (medicine + support items, numbered route),
red flags (受診勧奨 first, no medicine), abuse-control quantity requests, plain product finding, greeting.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from .. import deps, inventory, offers, repository, stores
from . import safety
from .tools import IN_STOCK, _shelf_text, build_store_items

IN = set(IN_STOCK)


def _pick(store_id: str, pred: Callable[[dict], bool], age: float | None = None, prefer: str = "") -> dict | None:
    cat = deps.get_catalog()
    best, bscore = None, None
    for n in cat.items.values():
        if not pred(n):
            continue
        p = deps.to_product(n)
        if p is None:
            continue
        if age is not None and p.get("drug_class") in safety.MEDICINE_CLASSES and (p.get("age_min") or 0) > age:
            continue
        inv = inventory.inventory_for(store_id, p["id"])
        status = inv["status"] if inv else "not_carried"
        score = (0 if status in IN else 1 if status == "out_of_stock" else 2,
                 0 if prefer and prefer in p["title"] else 1, len(p["title"]), p["id"])
        if bscore is None or score < bscore:
            best, bscore = p, score
    return best


def _path_has(*words: str) -> Callable[[dict], bool]:
    return lambda n: all(w in (n.get("category_path") or "") or w in n.get("title", "") for w in words)


def _title_has(*words: str) -> Callable[[dict], bool]:
    return lambda n: all(w in n.get("title", "") for w in words)


def fever_items(store_id: str, age: float | None, flags: list[dict]) -> list[dict]:
    child = age is not None and age < 15
    items: list[dict] = []
    scen = repository.load_scenarios().get(f"fever_set_{store_id}") or []
    if not safety.is_blocking(flags) and not any(f["level"] == "crisis" for f in flags):
        if child:
            med = _pick(store_id, _path_has("かぜ薬"), age, prefer="子ども") or _pick(store_id, _path_has("解熱鎮痛薬"), age)
        else:
            med = None
            for pid in scen:
                p = deps.to_product(pid)
                if p and re.search(r"(子ども|こども|小児|キッズ)", p.get("title", "")):
                    continue  # adult consultation → adult product
                if p and safety.symptom_group(p) == "fever_cold" and p.get("drug_class") in safety.MEDICINE_CLASSES:
                    med = p
                    break
            med = med or _pick(store_id, lambda n: "解熱鎮痛薬" in (n.get("category_path") or ""), age)
        if med:
            items.append({"product_id": med["id"], "role": "解熱鎮痛薬" if "解熱" in (med.get("category_path") or "") else "かぜ薬",
                          "reason": "発熱・頭痛などの症状に合う候補"})
    sheet = _pick(store_id, _title_has("冷却ジェルシート"), prefer="子ども用" if child else "大人用")
    ors = _pick(store_id, _title_has("経口補水液"), prefer="500ml")
    thermo = _pick(store_id, _title_has("体温計"), prefer="ベビー" if age is not None and age < 2 else "予測式")
    mask = _pick(store_id, lambda n: "マスク" in n.get("title", "") and "不織布" in n.get("title", ""),
                 prefer="子ども用" if child else "ふつう")
    for p, role, reason in ((sheet, "冷却シート", "おでこを冷やして休みやすく"), (ors, "水分補給", "発熱時の水分・電解質補給に"),
                            (thermo, "体温計", "熱の経過をこまめに確認"), (mask, "マスク", "ご家族へのうつり予防に")):
        if p:
            items.append({"product_id": p["id"], "role": role, "reason": reason})
    return items[:5]


FEVER_RX = r"(熱|発熱|かぜ|風邪|カゼ|のど|喉|せき|咳|寒気|悪寒|だるい)"


def respond(message: str, store_id: str, customer_id: str, flags: list[dict], abuse: list[str],
            age: float | None, emit_preface: bool = True) -> list[dict[str, Any]]:
    """Returns the SSE payload list (without done) for one scripted turn."""
    out: list[dict[str, Any]] = [{"type": "status", "text": "考えています…"}]
    persona = offers.get_persona(customer_id)
    name = persona.get("name", "")
    store = stores.get_store(store_id) or {}
    pre = safety.red_flag_preface(flags)
    if pre and emit_preface:
        out.append({"type": "text", "text": pre + "\n\n", "author": "store_concierge"})
    crisis = any(f["level"] == "crisis" for f in flags)
    if crisis:
        out.append({"type": "chips", "items": ["薬剤師に相談したい", "店舗の電話番号は？"]})
        return out
    if abuse:
        if emit_preface or pre:
            out.append({"type": "text", "text": safety.ABUSE_GUIDANCE, "author": "store_concierge"})
        out.append({"type": "chips", "items": ["薬剤師に相談したい", "1個だけ欲しい", "のどの痛みに合う商品"]})
        return out
    if re.search(FEVER_RX, message):
        out.append({"type": "status", "text": "商品を探しています…"})
        items = fever_items(store_id, age, flags)
        blocking = safety.is_blocking(flags)
        advice = ("・水分をこまめにとり、体を温めて十分に休みましょう\n・室内は加湿（湿度50〜60%目安）を\n"
                  "・熱が高い・続く場合は早めに医療機関へ")
        theme = "受診までの補助（医薬品は表示していません）" if blocking else \
            ("お子さまの発熱・かぜのセルフケア" if age is not None and age < 15 else "発熱・かぜの初期症状のセルフケア")
        args, summary = build_store_items(store_id, customer_id, theme, advice, items, flags, age, red_flag=blocking)
        out.append({"type": "status", "text": "売場と回る順番を準備しています…"})
        out.append({"type": "action", "name": "show_store_items", "args": args, "result": {"ok": True, "shown": summary["shown"]}})
        numbered = [it for it in args["items"] if it.get("no")]
        lines = []
        if not pre:
            lines.append(f"{name}さん、おつらいですね。{store.get('short_name', '')}で症状に合う商品の候補をご用意しました。")
        else:
            lines.append("受診までの間に役立つ補助用品をご案内します。")
        if numbered:
            first = numbered[0]
            sh = _shelf_text((first["availability"].get("current") or {}).get("shelf")) or ""
            lines.append(f"①「{first['product']['title']}」は {sh} にあります。番号順に回るとレジまで約{int((args['route'] or {}).get('length_m') or 0)}mです。")
        missing = [it for it in args["items"] if not it.get("no")]
        if missing:
            alt = missing[0]
            near = [n for n in alt["availability"]["nearby"] if n["status"] in IN]
            where = f"{near[0]['short_name']}（約{near[0]['distance_m'] / 1000:.1f}km）" if near else "オンライン"
            lines.append(f"「{alt['product']['title']}」はこの店舗では在庫がありませんが、{where}でお求めいただけます。")
        if customer_id == "CR-0002" and not blocking:
            lines.append("お飲みのお薬との飲み合わせは、ご購入前に薬剤師にご確認ください。")
        if any(it["product"].get("drug_class") == "第1類医薬品" for it in args["items"]):
            lines.append("第1類医薬品はご購入時に薬剤師からの説明が必要です。")
        lines.append("パッケージ記載の用法・用量を守ってお使いください。「まとめて棚を探す」で回る順番に棚をご案内します。")
        out.append({"type": "text", "text": "".join(lines), "author": "store_concierge"})
        out.append({"type": "chips", "items": ["まとめて棚を探す", "子ども用はある？", "近くの店舗の在庫は？"]})
        return out
    if re.fullmatch(r"\s*(こんにちは|こんばんは|おはよう.*|はじめまして|hi|hello)\s*[!！。]?\s*", message, re.I):
        out.append({"type": "text", "text": f"{name}さん、こんにちは。{store.get('short_name', '')}のAIコンシェルジュです。"
                    "症状に合う商品の候補探しや、在庫・棚の場所・回る順番をご案内します。", "author": "store_concierge"})
        out.append({"type": "chips", "items": ["熱っぽい", "目が疲れる", "経口補水液はどこ？"]})
        return out
    # plain product finding
    q = re.sub(r"(はどこ|どこにあり|ありますか|ある\?|ある？|を探して|がほしい|が欲しい|ください|[？?。！!])", " ", message).strip() or message
    out.append({"type": "status", "text": "商品を探しています…"})
    try:
        res = deps.get_engine().search(q, "", {}, [], "", "", "", "", 1, 12, "store-navi-mock", "")
        ids = [r["id"] for r in res.get("results") or []]
    except Exception:  # noqa: BLE001
        ids = [n["id"] for _, n in deps.get_catalog().text_search(q)[:12]]
    prods = deps.hydrate(ids)
    prods.sort(key=lambda p: (inventory.inventory_for(store_id, p["id"]) or {}).get("status") not in IN)
    items = [{"product_id": p["id"], "role": p.get("category_path", "").split(">")[-1].strip(), "reason": "お探しの商品の候補"}
             for p in prods[:3]]
    if not items:
        out.append({"type": "text", "text": f"申し訳ございません、「{q}」に該当する商品が見つかりませんでした。別の言葉でお試しください。",
                    "author": "store_concierge"})
        return out
    args, summary = build_store_items(store_id, customer_id, f"「{q}」の候補", "", items, flags, age)
    out.append({"type": "action", "name": "show_store_items", "args": args, "result": {"ok": True, "shown": summary["shown"]}})
    out.append({"type": "text", "text": f"「{q}」の候補を {summary['shown']} 件表示しました。番号の順に棚をご案内できます。",
                "author": "store_concierge"})
    out.append({"type": "chips", "items": ["まとめて棚を探す", "近くの店舗の在庫は？"]})
    return out
