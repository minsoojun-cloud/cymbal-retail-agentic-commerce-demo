"""Gemini structured-output slot composer + strict catalog price/ID verification and deterministic fallback."""
from __future__ import annotations

import logging
import os
from typing import Any, Optional
from pydantic import BaseModel, Field

from .picker import select_candidates_for_template, score_product, parse_month, extract_theme_terms, is_excluded
from .repository import FlyerRepository
from .templates import BADGE_PRESETS, build_template_slots

log = logging.getLogger("cymbal-flyer.composer")

PROJECT_ID = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_LOCATION = os.environ.get("GEMINI_LOCATION", "global")


class SlotFillSchema(BaseModel):
    slot_id: str = Field(description="テンプレートの枠ID（例: day1-hero-1）")
    product_id: str = Field(description="候補リスト内の商品IDのみ指定")
    catch_copy: str = Field(description="20文字以内の日本語販促キャッチコピー（価格数字は書かない）")
    badge: str = Field(description="バッジ文言（例: 超目玉, 特価, 旬, 日替り, 地産地消, 人気商品）")
    reason: str = Field(description="この枠に選定した理由（日本語・25文字以内）")


class MenuProposalSchema(BaseModel):
    dish_name: str = Field(description="提案する献立・メニュー名（例: 秋鮭と彩りきのこのちゃんちゃん焼き）")
    servings_label: str = Field(description="対象人数（例: 4人家族分・約15分）")
    description: str = Field(description="献立のおすすめポイント（40文字以内）")
    ingredient_product_ids: list[str] = Field(description="候補リスト内の関連商品ID（2〜4点）")


class ZoneHeadingSchema(BaseModel):
    zone_id: str = Field(description="ゾーンID")
    title: str = Field(description="テーマ・ターゲットに合わせたゾーン見出し")
    subtitle: str = Field(description="ゾーンの補足コピー")


class FlyerDraftSchema(BaseModel):
    title: str = Field(description="チラシ最上部の大見出し（例: 秋の味覚と旬の野菜 大収穫祭）")
    subtitle: str = Field(description="サブコピー（例: ご家族の食卓を応援！産地直送の旬食材と今週の超特価）")
    lead_copy: str = Field(description="地域のお客様への呼びかけコピー（45文字以内）")
    zone_headings: list[ZoneHeadingSchema] = Field(description="各ゾーンの見出し提案")
    fills: list[SlotFillSchema] = Field(description="全スロットへの商品割り当て")
    menu_proposals: list[MenuProposalSchema] = Field(description="テーマ・ターゲットに合わせた献立提案（2件）")


def _default_catch_copy(prod: dict, role: str, theme: str, target: str) -> str:
    origin = prod.get("origin") or ""
    dishes = prod.get("dishes") or []
    promo = prod.get("promo_text") or ""
    if role == "hero":
        if origin and ("産" in origin or "国内" in origin):
            return f"{origin}！鮮度抜群の今週の主役"[:20]
        if dishes:
            return f"{dishes[0]}に最適！バイヤー厳選目玉"[:20]
        return "売り切れご免！朝一番の超目玉品"[:20]
    if "シニア" in target or "少人数" in target:
        return "使い切りやすく毎日の食卓に便利"[:20]
    if "家族" in target or "主婦" in target:
        if dishes:
            return f"ご家族みんな大好き！{dishes[0]}に"[:20]
        return "ご家族のまとめ買いに嬉しいお買得"[:20]
    if promo:
        return promo[:20]
    if prod.get("is_seasonal"):
        return "今が一番おいしい旬の味わい"[:20]
    return "毎日のお買物を応援する特別奉仕"[:20]


def _default_badge(prod: dict, slot: dict) -> str:
    if slot.get("role") == "hero":
        return slot.get("default_badge") or "超目玉"
    tags = prod.get("pickup_tags") or []
    for t in tags:
        if t in BADGE_PRESETS:
            return t
    return slot.get("default_badge") or "特価"


def _build_default_menus(picked_products: list[dict], theme: str, target: str) -> list[dict]:
    servings = "2人前（食べきり）" if any(k in target for k in ("シニア", "少人数", "2人")) else (
        "1人前（時短10分）" if any(k in target for k in ("単身", "一人", "時短")) else "4人家族分（ボリューム満点）"
    )
    dish_to_prods: dict[str, list[dict]] = {}
    for p in picked_products:
        for d in p.get("dishes") or []:
            dish_to_prods.setdefault(d, []).append(p)
    ranked_dishes = sorted(dish_to_prods.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    menus: list[dict] = []
    for dish_name, prods in ranked_dishes[:2]:
        ing = prods[:4]
        menus.append({
            "dish_name": f"今夜のご提案：{dish_name}",
            "servings_label": servings,
            "description": f"{theme or '今週の特売'}の旬食材で作る、{servings}のおすすめ献立です。",
            "ingredients": [
                {
                    "product_id": p["id"],
                    "flyer_name": p["flyer_name"],
                    "price_tax_excluded": p["price_tax_excluded"],
                    "price": p["price"],
                    "image": p["image"],
                }
                for p in ing
            ],
        })
    if not menus and picked_products:
        ing = picked_products[:3]
        menus.append({
            "dish_name": f"{theme or '今週のおすすめ'} 食卓応援セット",
            "servings_label": servings,
            "description": "目玉食材を組み合わせて今日すぐ作れる人気メニューです。",
            "ingredients": [
                {
                    "product_id": p["id"],
                    "flyer_name": p["flyer_name"],
                    "price_tax_excluded": p["price_tax_excluded"],
                    "price": p["price"],
                    "image": p["image"],
                }
                for p in ing
            ],
        })
    return menus


def _call_gemini_composer(
    resolved_template: dict[str, Any],
    flat_slots: list[dict[str, Any]],
    zone_candidates: dict[str, list[dict[str, Any]]],
    theme: str,
    target: str,
    period_from: str,
    period_to: str,
    store: dict[str, Any],
) -> FlyerDraftSchema | None:
    if os.environ.get("FLYER_AI_MODE") == "fallback":
        return None
    # For very large flyers (>48 slots), keep latency fast and avoid token truncation by using deterministic slot fill + AI/template headings
    if len(flat_slots) > 48:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(vertexai=True, project=PROJECT_ID or None, location=GEMINI_LOCATION)
        cand_lines: list[str] = []
        for zid, cands in zone_candidates.items():
            cand_lines.append(f"【ゾーン {zid} 候補】")
            for c in cands[:18]:
                cand_lines.append(
                    f"- ID:{c['id']} | {c['flyer_name']} ({c['unit_label']}) | 産地:{c.get('origin') or '-'} | "
                    f"割引:{int(round((c.get('discount_rate') or 0)*100))}% | 料理:{','.join((c.get('dishes') or [])[:3])} | 理由:{c.get('pickup_reason')}"
                )
        slot_lines = [
            f"- slot_id:{s['slot_id']} (zone:{s['zone_id']}, role:{s['role']}, shape:{s['shape']})"
            for s in flat_slots
        ]
        prompt = f"""あなたは日本の地域密着型スーパーマーケット「Cymbal Retail」の熟練チラシ編集長です。
以下の条件で今週の折込・デジタルチラシを構成してください。すべて自然な日本語で出力してください。

- テーマ: {theme or '今週の大感謝祭・生活応援セール'}
- ターゲット層: {target or '地域のご家庭・40代主婦・4人家族'}
- 期間: {period_from} 〜 {period_to}
- 店舗: {store.get('name', 'Cymbal 〇〇店')}（地域: {store.get('prefecture', '東京都')}）
- テンプレート: {resolved_template.get('name')}

【厳守ルール】
1. 各 `slot_id` には必ず下の候補リストに存在する `product_id` を重複なく割り当ててください。
2. 価格の数字はキャッチコピー内に一切書かないでください（価格はシステムが商品マスタから厳密に転記します）。
3. `catch_copy` は20文字以内で、ターゲット層に響くシズル感・ベネフィット（旬・産地・献立・お得感）を表現してください。
4. `badge` は [{', '.join(BADGE_PRESETS)}] から最適なものを選んでください。

【割り当てるスロット一覧 ({len(flat_slots)}枠)】
{chr(10).join(slot_lines)}

【ゾーン別候補商品リスト】
{chr(10).join(cand_lines)}
"""
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=FlyerDraftSchema,
                temperature=0.25,
            ),
        )
        if resp and resp.text:
            return FlyerDraftSchema.model_validate_json(resp.text)
    except Exception as e:  # noqa: BLE001
        log.warning("Gemini composer fallback triggered: %s", e)
    return None


def hydrate_slot_product(repo: FlyerRepository, slot: dict[str, Any], offer: dict[str, Any] | None = None) -> dict[str, Any]:
    """Hydrate a slot from the catalog master by `product_id` (single source of truth for prices/names).

    If `product_id` no longer exists in the master catalog, marks the slot `discontinued=True` (販売終了)
    while preserving any archived snapshot info for reference.
    """
    pid = str(slot.get("product_id") or "")
    prod = repo.get_product(pid)
    out = dict(slot)
    if prod is None:
        snap = slot.get("snapshot") or {}
        out["discontinued"] = True
        out["out_of_stock"] = False
        out["product"] = {
            "id": pid,
            "title": snap.get("title") or f"販売終了商品 ({pid})",
            "flyer_name": snap.get("flyer_name") or snap.get("title") or f"販売終了商品 ({pid})",
            "category": snap.get("category") or "",
            "origin": snap.get("origin") or "",
            "unit_label": snap.get("unit_label") or "",
            "image": snap.get("image") or "",
            "price_tax_excluded": snap.get("price_tax_excluded") or 0,
            "price": snap.get("price") or 0,
            "price_tax_included_exact": snap.get("price_tax_included_exact") or 0.0,
            "original_price_tax_excluded": snap.get("original_price_tax_excluded") or 0,
            "original_price": snap.get("original_price") or 0,
            "discount_rate": 0.0,
            "on_sale": False,
            "tax_rate": snap.get("tax_rate") or 0.08,
        }
        return out

    out["discontinued"] = False
    out["out_of_stock"] = prod.get("availability") == "OUT_OF_STOCK"

    # Apply flyer-only special offer if present on this slot
    active_offer = offer or out.get("offer")
    p_copy = dict(prod)
    if active_offer and int(active_offer.get("offer_price_tax_excluded") or 0) > 0:
        off_ex = int(active_offer["offer_price_tax_excluded"])
        off_inc = int(active_offer["offer_price_tax_included"])
        off_exact = float(active_offer.get("offer_price_tax_included_exact") or round(off_ex * (1.0 + p_copy["tax_rate"]), 2))
        reg_ex = int(p_copy["price_tax_excluded"])
        reg_inc = int(p_copy["price"])
        p_copy["regular_price_tax_excluded"] = reg_ex
        p_copy["regular_price"] = reg_inc
        p_copy["original_price_tax_excluded"] = max(reg_ex, int(p_copy.get("original_price_tax_excluded") or reg_ex))
        p_copy["original_price"] = max(reg_inc, int(p_copy.get("original_price") or reg_inc))
        p_copy["price_tax_excluded"] = off_ex
        p_copy["price"] = off_inc
        p_copy["price_tax_included_exact"] = off_exact
        p_copy["on_sale"] = off_ex < p_copy["original_price_tax_excluded"]
        if p_copy["original_price_tax_excluded"] > off_ex > 0:
            p_copy["discount_rate"] = round(
                (p_copy["original_price_tax_excluded"] - off_ex) / p_copy["original_price_tax_excluded"], 2
            )
        p_copy["has_flyer_offer"] = True
        p_copy["offer_limit_text"] = active_offer.get("limit_text") or ""
        p_copy["offer_entered_by"] = active_offer.get("entered_by") or ""
    else:
        p_copy["has_flyer_offer"] = False

    # Enforce price_style rule: was_now / percent_off require original_price_tax_excluded > price_tax_excluded
    has_discount = int(p_copy.get("original_price_tax_excluded") or 0) > int(p_copy.get("price_tax_excluded") or 0)
    if out.get("price_style") in ("was_now", "percent_off") and not has_discount:
        out["price_style"] = "dual"

    out["product"] = p_copy
    return out


def compose_flyer_draft(
    repo: FlyerRepository,
    template: dict[str, Any],
    theme: str = "",
    target: str = "",
    period_from: str = "2026-11-11",
    period_to: str = "2026-11-17",
    store: dict[str, Any] | None = None,
    community: dict[str, Any] | None = None,
    item_count: int | None = None,
    zone_counts: dict[str, int] | None = None,
    existing_locked_slots: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the 3-stage pipeline: (1) deterministic pickup -> (2) Gemini structured fill -> (3) strict DB validation."""
    store = store or {}
    community = community or {}
    locked_map = existing_locked_slots or {}
    locked_pids = {str(s.get("product_id")) for s in locked_map.values() if s.get("product_id")}

    resolved_tpl, flat_slots, density_warning = build_template_slots(template, item_count=item_count, zone_counts=zone_counts)
    pickup = select_candidates_for_template(
        repo=repo,
        resolved_template=resolved_tpl,
        theme=theme,
        target=target,
        period_from=period_from,
        period_to=period_to,
        store_prefecture=store.get("prefecture") or "",
        locked_product_ids=locked_pids,
    )

    zone_candidates = pickup["zone_candidates"]
    zone_det_picks = pickup["zone_deterministic_picks"]
    allowed_cand_map: dict[str, dict[str, Any]] = {}
    for cands in zone_candidates.values():
        for c in cands:
            allowed_cand_map[c["id"]] = c

    ai_draft = _call_gemini_composer(
        resolved_template=resolved_tpl,
        flat_slots=flat_slots,
        zone_candidates=zone_candidates,
        theme=theme,
        target=target,
        period_from=period_from,
        period_to=period_to,
        store=store,
    )

    ai_fills_by_slot: dict[str, SlotFillSchema] = {}
    if ai_draft:
        for f in ai_draft.fills:
            ai_fills_by_slot[f.slot_id] = f
        heading_map = {h.zone_id: h for h in ai_draft.zone_headings}
        for z in resolved_tpl.get("zones") or []:
            if z["id"] in heading_map:
                z["title"] = heading_map[z["id"]].title or z["title"]
                z["subtitle"] = heading_map[z["id"]].subtitle or z.get("subtitle", "")

    used_pids: set[str] = set(locked_pids)
    used_images: set[str] = {
        repo.items[pid]["image"] for pid in locked_pids if pid in repo.items and repo.items[pid].get("image")
    }

    # Build deterministic fallback queues per zone
    det_iter: dict[str, list[dict[str, Any]]] = {
        zid: list(cands) for zid, cands in zone_candidates.items()
    }

    final_slots: list[dict[str, Any]] = []
    picked_products_for_menus: list[dict[str, Any]] = []

    for s in flat_slots:
        sid = s["slot_id"]
        zid = s["zone_id"]
        if sid in locked_map:
            locked_slot = dict(locked_map[sid])
            locked_slot["locked"] = True
            hydrated = hydrate_slot_product(repo, locked_slot)
            final_slots.append(hydrated)
            if not hydrated.get("discontinued"):
                picked_products_for_menus.append(hydrated["product"])
            continue

        chosen_prod: dict[str, Any] | None = None
        catch_copy = ""
        badge = ""
        reason = ""

        ai_f = ai_fills_by_slot.get(sid)
        if ai_f and ai_f.product_id in allowed_cand_map:
            cand = allowed_cand_map[ai_f.product_id]
            if cand["id"] not in used_pids and cand["image"] not in used_images:
                chosen_prod = cand
                catch_copy = ai_f.catch_copy.strip()[:24]
                badge = ai_f.badge.strip() if ai_f.badge.strip() in BADGE_PRESETS else ""
                reason = ai_f.reason.strip()

        if chosen_prod is None:
            for cand in det_iter.get(zid, []):
                if cand["id"] not in used_pids and cand["image"] not in used_images:
                    chosen_prod = cand
                    break

        if chosen_prod is None:
            # Global fallback across all zones
            for cands in zone_candidates.values():
                for cand in cands:
                    if cand["id"] not in used_pids and cand["image"] not in used_images:
                        chosen_prod = cand
                        break
                if chosen_prod:
                    break

        if chosen_prod is None:
            continue

        used_pids.add(chosen_prod["id"])
        used_images.add(chosen_prod["image"])

        slot_entry = {
            "slot_id": sid,
            "zone_id": zid,
            "role": s["role"],
            "size": s["size"],
            "size_span": s.get("size_span", "auto"),
            "width_weight": float(s.get("width_weight") or 1.0),
            "row_weight": float(s.get("row_weight") or 1.0),
            "img_scale": int(s.get("img_scale") or 100),
            "shape": s["shape"],
            "layout_mode": s.get("layout_mode", "overlay_full"),
            "overlay_pos": s.get("overlay_pos", "bottom_split"),
            "numeral_style": s.get("numeral_style", "graphic_pop"),
            "bg_color": s.get("bg_color", "auto"),
            "bg_image_url": s.get("bg_image_url") or "",
            "price_style": s["price_style"],
            "product_id": chosen_prod["id"],
            "catch_copy": catch_copy or _default_catch_copy(chosen_prod, s["role"], theme, target),
            "badge": badge or _default_badge(chosen_prod, s),
            "reason": reason or chosen_prod.get("pickup_reason") or "おすすめ特売品",
            "locked": False,
            "offer": None,
        }
        hydrated = hydrate_slot_product(repo, slot_entry)
        final_slots.append(hydrated)
        picked_products_for_menus.append(hydrated["product"])

    # Menus
    menus: list[dict[str, Any]] = []
    if ai_draft and ai_draft.menu_proposals:
        for mp in ai_draft.menu_proposals[:2]:
            ing_list = []
            for pid in mp.ingredient_product_ids[:4]:
                p = repo.get_product(pid)
                if p:
                    ing_list.append({
                        "product_id": p["id"],
                        "flyer_name": p["flyer_name"],
                        "price_tax_excluded": p["price_tax_excluded"],
                        "price": p["price"],
                        "image": p["image"],
                    })
            if ing_list:
                menus.append({
                    "dish_name": mp.dish_name,
                    "servings_label": mp.servings_label,
                    "description": mp.description,
                    "ingredients": ing_list,
                })
    if not menus:
        menus = _build_default_menus(picked_products_for_menus, theme, target)

    default_title = f"{theme} 大奉仕！" if theme else "今週の超目玉＆旬の味覚フェア"
    default_sub = (
        f"{target}の食卓を応援！産地直送の生鮮品と厳選お買い得品が勢揃い"
        if target
        else "地域の皆様の毎日のお買物を応援！新鮮・お買得品が満載"
    )

    return {
        "title": (ai_draft.title if ai_draft and ai_draft.title else default_title),
        "subtitle": (ai_draft.subtitle if ai_draft and ai_draft.subtitle else default_sub),
        "lead_copy": (
            ai_draft.lead_copy
            if ai_draft and ai_draft.lead_copy
            else f"{store.get('name', '当店')}バイヤーが厳選した旬の味覚と特売品をお届けします。"
        ),
        "composer_mode": "gemini" if ai_draft else "deterministic_fallback",
        "density_warning": density_warning,
        "anniversaries": pickup["anniversaries"],
        "zones": [
            {
                "id": z["id"],
                "title": z["title"],
                "subtitle": z.get("subtitle", ""),
                "zone_type": z.get("zone_type", "day_block"),
                "frame_color": z.get("frame_color", "red"),
                "weight": float(z.get("weight") or 1.0),
                "bg_image_url": z.get("bg_image_url") or "",
                "uniform_price_ex": z.get("uniform_price_ex"),
                "uniform_price_inc": z.get("uniform_price_inc"),
                "categories": z.get("categories") or [],
                "hero_count": z.get("hero_count", 0),
                "grid_count": z.get("grid_count", 0),
                "hero_shape": z.get("hero_shape", "overflow_cutout"),
                "grid_shape": z.get("grid_shape", "rect"),
                "hero_layout_mode": z.get("hero_layout_mode", "overlay_full"),
                "grid_layout_mode": z.get("grid_layout_mode", "overlay_price"),
                "default_badge": z.get("default_badge", "特価"),
                "slot_overrides": z.get("slot_overrides") or {},
            }
            for z in (resolved_tpl.get("zones") or [])
        ],
        "slots": final_slots,
        "menu_proposals": menus,
    }


def suggest_slot_replacement(
    repo: FlyerRepository,
    flyer_doc: dict[str, Any],
    slot_id: str,
) -> dict[str, Any] | None:
    """Suggest the best next alternative candidate for a single slot without duplicating existing flyer items."""
    slots = flyer_doc.get("slots") or []
    target_slot = next((s for s in slots if s.get("slot_id") == slot_id), None)
    if not target_slot:
        return None
    zones = {z["id"]: z for z in (flyer_doc.get("zones") or [])}
    zone = zones.get(target_slot.get("zone_id") or "", {})
    allowed_cats = set(zone.get("categories") or [])

    used_pids = {str(s.get("product_id")) for s in slots if s.get("product_id")}
    used_imgs = {
        (s.get("product") or {}).get("image")
        for s in slots
        if (s.get("product") or {}).get("image") and s.get("slot_id") != slot_id
    }

    period = flyer_doc.get("period") or {}
    month = parse_month(period.get("from") or "")
    theme = flyer_doc.get("theme") or ""
    target = flyer_doc.get("target") or ""
    store = flyer_doc.get("store") or {}
    theme_terms = extract_theme_terms(theme, period.get("from") or "", period.get("to") or "")

    cur_prod = target_slot.get("product") or {}
    cur_cat = cur_prod.get("category") or ""

    best: tuple[float, dict, list[str], str] | None = None
    for n in repo.items.values():
        if is_excluded(n) or n["id"] in used_pids or n["image"] in used_imgs:
            continue
        sc, tags, reason = score_product(n, month, theme_terms, target, store.get("prefecture") or "")
        if cur_cat and n["category"] == cur_cat:
            sc += 1.5
        elif allowed_cats and n["category"] in allowed_cats:
            sc += 0.8
        if best is None or sc > best[0]:
            best = (sc, n, tags, reason)

    if best is None:
        return None
    _, chosen, tags, reason = best
    pub = {k: v for k, v in chosen.items() if not k.startswith("_")}
    pub["pickup_tags"] = tags
    pub["pickup_reason"] = reason

    updated = dict(target_slot)
    updated["product_id"] = pub["id"]
    updated["offer"] = None
    updated["discontinued"] = False
    updated["catch_copy"] = _default_catch_copy(pub, updated.get("role", "grid"), theme, target)
    updated["badge"] = _default_badge(pub, updated)
    updated["reason"] = reason
    return hydrate_slot_product(repo, updated)
