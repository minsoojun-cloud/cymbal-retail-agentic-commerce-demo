"""Draft management, manager approval & GCS archiving, custom templates, and reuse with live master re-hydration."""
from __future__ import annotations

import copy
import datetime as dt
import logging
import os
import uuid
from typing import Any

from .composer import hydrate_slot_product
from .qa_validator import run_flyer_qa_and_autofix
from .repository import FlyerRepository, compute_tax_included
from .templates import BASE_TEMPLATES

log = logging.getLogger("cymbal-flyer.archive")
JST = dt.timezone(dt.timedelta(hours=9))

DISCONTINUED_TEST_PRODUCT_ID = "4999999000001"
SAMPLE_ARCHIVE_ID = "fl-sample-20261028-01"


def now_jst_iso() -> str:
    return dt.datetime.now(JST).isoformat(timespec="seconds")


def hydrate_flyer_live(repo: FlyerRepository, flyer_doc: dict[str, Any]) -> dict[str, Any]:
    """Re-hydrate all slots of a draft flyer from the live catalog master."""
    doc = copy.deepcopy(flyer_doc)
    new_slots: list[dict[str, Any]] = []
    discontinued_count = 0
    out_of_stock_count = 0
    for s in doc.get("slots") or []:
        h = hydrate_slot_product(repo, s, s.get("offer"))
        if h.get("discontinued"):
            discontinued_count += 1
        if h.get("out_of_stock"):
            out_of_stock_count += 1
        new_slots.append(h)
    doc["slots"] = new_slots
    doc["discontinued_count"] = discontinued_count
    doc["out_of_stock_count"] = out_of_stock_count
    return doc


def snapshot_flyer_for_approval(repo: FlyerRepository, flyer_doc: dict[str, Any], approver: dict[str, str]) -> dict[str, Any]:
    """Freeze a flyer snapshot at manager approval time so historical views always preserve exact prices & names."""
    live = hydrate_flyer_live(repo, flyer_doc)
    if live.get("discontinued_count", 0) > 0:
        raise ValueError("販売終了の商品が残っているため、承認して保管できません。該当枠の商品を差し替えてください。")

    snap_doc = copy.deepcopy(live)
    snap_doc["status"] = "承認済み"
    snap_doc["approved_by"] = {
        "id": approver.get("id", "mgr-tanaka"),
        "name": approver.get("name", "店長 田中"),
        "role": approver.get("role", "manager"),
    }
    snap_doc["approved_at"] = now_jst_iso()

    for s in snap_doc.get("slots") or []:
        prod = s.get("product") or {}
        s["snapshot"] = {
            "product_id": s.get("product_id"),
            "title": prod.get("title") or "",
            "flyer_name": prod.get("flyer_name") or "",
            "brand": prod.get("brand") or "",
            "category": prod.get("category") or "",
            "origin": prod.get("origin") or "",
            "unit_label": prod.get("unit_label") or "",
            "price_per_100g": prod.get("price_per_100g"),
            "pack_type": prod.get("pack_type") or "",
            "image": prod.get("image") or "",
            "price_tax_excluded": prod.get("price_tax_excluded") or 0,
            "price": prod.get("price") or 0,
            "price_tax_included_exact": prod.get("price_tax_included_exact") or 0.0,
            "original_price_tax_excluded": prod.get("original_price_tax_excluded") or 0,
            "original_price": prod.get("original_price") or 0,
            "discount_rate": prod.get("discount_rate") or 0.0,
            "tax_rate": prod.get("tax_rate") or 0.08,
            "has_flyer_offer": bool(prod.get("has_flyer_offer")),
            "offer_limit_text": prod.get("offer_limit_text") or "",
        }
    return snap_doc


def render_archived_flyer_view(repo: FlyerRepository, archived_doc: dict[str, Any]) -> dict[str, Any]:
    """Return an archived flyer using its frozen approval-time snapshot, annotating whether each item is still in master."""
    doc = copy.deepcopy(archived_doc)
    now_discontinued = 0
    for s in doc.get("slots") or []:
        pid = str(s.get("product_id") or "")
        snap = s.get("snapshot") or s.get("product") or {}
        s["product"] = dict(snap)
        in_master = repo.get_product(pid) is not None
        s["currently_discontinued_in_master"] = not in_master
        s["discontinued"] = False  # In historical view, display the frozen snapshot as printed
        if not in_master:
            now_discontinued += 1
    doc["currently_discontinued_count"] = now_discontinued
    return doc


def create_draft_from_archived(
    repo: FlyerRepository,
    archived_doc: dict[str, Any],
    creator: dict[str, str],
    new_theme: str | None = None,
    new_target: str | None = None,
    period_from: str = "2026-11-11",
    period_to: str = "2026-11-17",
) -> dict[str, Any]:
    """Reuse an archived flyer as the basis for a new draft:
    - Copies layout, zones, slot shapes/sizes, store info, community settings, and product codes (`product_id`).
    - Clears past flyer-only special offers (`offer = None`).
    - Re-hydrates every product code from the live master catalog (`repo.get_product(pid)`).
    - Any product code missing from the master is marked `discontinued=True` (`販売終了`).
    """
    new_id = f"fl-{dt.datetime.now(JST).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
    draft = copy.deepcopy(archived_doc)
    draft["id"] = new_id
    draft["based_on_flyer_id"] = archived_doc.get("id")
    draft["status"] = "下書き"
    draft["theme"] = new_theme if new_theme is not None else (archived_doc.get("theme") or "")
    draft["target"] = new_target if new_target is not None else (archived_doc.get("target") or "")
    draft["period"] = {"from": period_from, "to": period_to}
    draft["created_by"] = {
        "id": creator.get("id", "staff-sato"),
        "name": creator.get("name", "販促担当 佐藤"),
        "role": creator.get("role", "staff"),
    }
    draft["created_at"] = now_jst_iso()
    draft["submitted_by"] = None
    draft["submitted_at"] = None
    draft["approved_by"] = None
    draft["approved_at"] = None
    draft["rejected_by"] = None
    draft["rejected_at"] = None
    draft["reject_comment"] = None

    for s in draft.get("slots") or []:
        # Strip expired flyer-only special offers so the new draft uses current master prices
        s["offer"] = None
        # Keep snapshot only as fallback metadata in case the product code is discontinued in master
        if not s.get("snapshot") and s.get("product"):
            s["snapshot"] = copy.deepcopy(s["product"])

    return hydrate_flyer_live(repo, draft)


def save_draft(repo: FlyerRepository, flyer_doc: dict[str, Any]) -> dict[str, Any]:
    hydrated = hydrate_flyer_live(repo, flyer_doc)
    verified = run_flyer_qa_and_autofix(repo, hydrated)
    verified["updated_at"] = now_jst_iso()
    rel = f"drafts/{verified['id']}/flyer.json"
    repo.write_json(rel, verified)
    return verified


def load_draft(repo: FlyerRepository, flyer_id: str) -> dict[str, Any] | None:
    doc = repo.read_json(f"drafts/{flyer_id}/flyer.json")
    if not doc:
        return None
    if doc.get("status") == "承認済み":
        return render_archived_flyer_view(repo, doc)
    hydrated = hydrate_flyer_live(repo, doc)
    return run_flyer_qa_and_autofix(repo, hydrated)


def apply_slot_offer(
    repo: FlyerRepository,
    flyer_doc: dict[str, Any],
    slot_id: str,
    offer_price_tax_excluded: int | None,
    limit_text: str,
    user: dict[str, str],
) -> tuple[dict[str, Any], str | None]:
    """Set or clear a flyer-only special price (`チラシ特別価格`) on a slot."""
    if flyer_doc.get("status") == "承認済み":
        raise PermissionError("承認済みのチラシは変更できません。")

    slots = flyer_doc.get("slots") or []
    slot = next((s for s in slots if s.get("slot_id") == slot_id), None)
    if not slot:
        raise KeyError(f"指定された枠が見つかりません: {slot_id}")

    pid = str(slot.get("product_id") or "")
    master_prod = repo.get_product(pid)
    if not master_prod:
        raise ValueError("販売終了商品にはチラシ特別価格を設定できません。先に商品を差し替えてください。")

    if offer_price_tax_excluded is None or int(offer_price_tax_excluded) == 0:
        slot["offer"] = None
        saved = save_draft(repo, flyer_doc)
        return saved, None

    price_ex = int(offer_price_tax_excluded)
    if price_ex < 0:
        raise ValueError("チラシ特別価格は1円以上で入力してください。")

    tax_rate = float(master_prod.get("tax_rate") or 0.08)
    price_inc, price_inc_exact = compute_tax_included(price_ex, tax_rate)
    reg_ex = int(master_prod["price_tax_excluded"])
    reg_inc = int(master_prod["price"])

    warning = None
    if price_ex >= reg_ex:
        warning = f"入力された特別価格（本体{price_ex:,}円）は現在の通常売価（本体{reg_ex:,}円）以上です。"

    period = flyer_doc.get("period") or {}
    offer_obj = {
        "offer_id": f"of-{uuid.uuid4().hex[:10]}",
        "flyer_id": flyer_doc["id"],
        "slot_id": slot_id,
        "product_id": pid,
        "offer_price_tax_excluded": price_ex,
        "offer_price_tax_included": price_inc,
        "offer_price_tax_included_exact": price_inc_exact,
        "regular_price_tax_excluded": reg_ex,
        "regular_price_tax_included": reg_inc,
        "valid_from": period.get("from") or "",
        "valid_to": period.get("to") or "",
        "limit_text": (limit_text or "").strip(),
        "entered_by": user.get("name", "店長 田中"),
        "entered_by_id": user.get("id", "mgr-tanaka"),
        "entered_at": now_jst_iso(),
    }
    slot["offer"] = offer_obj
    # Default price style to was_now when a lower special price is set
    if price_ex < reg_ex and slot.get("price_style") == "dual":
        slot["price_style"] = "was_now"

    repo.record_offer_in_bq({
        k: v for k, v in offer_obj.items()
        if k not in ("offer_price_tax_included_exact", "entered_by_id")
    })
    saved = save_draft(repo, flyer_doc)
    return saved, warning


def ensure_sample_archived_flyer(repo: FlyerRepository) -> dict[str, Any]:
    """Ensure the pre-seeded archived flyer `fl-sample-20261028-01` exists with 1 discontinued item (`4999999000001`)."""
    rel = f"approved/2026/{SAMPLE_ARCHIVE_ID}/flyer.json"
    existing = repo.read_json(rel)
    if existing:
        return existing

    # Pick 11 real products across categories + 1 discontinued summer item
    real_picks: list[dict] = []
    seen_imgs: set[str] = set()
    for cat in ("野菜・果物", "お肉・お肉加工品", "お魚・水産加工品", "卵・乳製品・豆乳・デザート", "豆腐・納豆・練り物", "お惣菜・ミールキット", "調味料", "お米・麺・インスタント"):
        for p in repo.search_products(category=cat, on_sale=True, limit=6):
            if p["image"] not in seen_imgs:
                seen_imgs.add(p["image"])
                real_picks.append(p)
                if len(real_picks) >= 11:
                    break
        if len(real_picks) >= 11:
            break

    base_tpl = copy.deepcopy(BASE_TEMPLATES["T1"])
    # Compact 12-slot sample layout (4 + 3 + 3 + 2)
    zone_counts = {"day1": 4, "day2": 3, "kinitsu": 3, "weekly": 2}
    from .templates import build_template_slots

    resolved_tpl, flat_slots, _ = build_template_slots(base_tpl, zone_counts=zone_counts)

    slots: list[dict[str, Any]] = []
    for idx, s in enumerate(flat_slots):
        if idx == 3:
            # Slot 4: Discontinued summer product code (not in cymbal.products master)
            disc_snap = {
                "product_id": DISCONTINUED_TEST_PRODUCT_ID,
                "title": "Cymbal 季節限定 冷やし中華 ごまだれ・醤油だれ 2人前",
                "flyer_name": "季節限定 冷やし中華 ごまだれ・醤油だれ 2人前",
                "brand": "Cymbal",
                "category": "お米・麺・インスタント",
                "origin": "国内製造",
                "unit_label": "2人前（タレ付）",
                "price_per_100g": None,
                "pack_type": "標準",
                "image": "/img/products/dairy_eggs_p.jpg",
                "price_tax_excluded": 298,
                "price": 322,
                "price_tax_included_exact": 321.84,
                "original_price_tax_excluded": 358,
                "original_price": 387,
                "discount_rate": 0.17,
                "tax_rate": 0.08,
                "has_flyer_offer": False,
                "offer_limit_text": "",
            }
            slots.append({
                "slot_id": s["slot_id"],
                "zone_id": s["zone_id"],
                "role": s["role"],
                "size": s["size"],
                "shape": s["shape"],
                "price_style": "dual",
                "product_id": DISCONTINUED_TEST_PRODUCT_ID,
                "catch_copy": "【季節終売テスト品】喉ごし爽やか夏限定麺",
                "badge": "特価",
                "reason": "過去掲載品（現在は販売終了）",
                "locked": False,
                "offer": None,
                "snapshot": disc_snap,
                "product": disc_snap,
            })
        else:
            p = real_picks[idx if idx < 3 else (idx - 1) % len(real_picks)]
            snap = {
                "product_id": p["id"],
                "title": p["title"],
                "flyer_name": p["flyer_name"],
                "brand": p["brand"],
                "category": p["category"],
                "origin": p["origin"],
                "unit_label": p["unit_label"],
                "price_per_100g": p["price_per_100g"],
                "pack_type": p["pack_type"],
                "image": p["image"],
                "price_tax_excluded": p["price_tax_excluded"],
                "price": p["price"],
                "price_tax_included_exact": p["price_tax_included_exact"],
                "original_price_tax_excluded": p["original_price_tax_excluded"],
                "original_price": p["original_price"],
                "discount_rate": p["discount_rate"],
                "tax_rate": p["tax_rate"],
                "has_flyer_offer": False,
                "offer_limit_text": "",
            }
            slots.append({
                "slot_id": s["slot_id"],
                "zone_id": s["zone_id"],
                "role": s["role"],
                "size": s["size"],
                "shape": s["shape"],
                "price_style": s["price_style"],
                "product_id": p["id"],
                "catch_copy": "ご家族の食卓を彩る今週の厳選特価",
                "badge": s["default_badge"],
                "reason": "前回チラシ掲載実績品",
                "locked": False,
                "offer": None,
                "snapshot": snap,
                "product": snap,
            })

    sample_doc = {
        "id": SAMPLE_ARCHIVE_ID,
        "template_id": "T1",
        "paper": "B4-landscape",
        "tone": "にぎやか",
        "title": "秋の家計応援！生鮮＆日配 大感謝祭",
        "subtitle": "ご家族の食卓を応援！バイヤー厳選のお買い得品特集（販売終了商品の検証用サンプル）",
        "lead_copy": "いつもCymbal 世田谷店をご利用いただきありがとうございます。",
        "theme": "秋の家計応援フェア",
        "target": "40代主婦・4人家族",
        "period": {"from": "2026-10-28", "to": "2026-11-03"},
        "store": {
            "name": "Cymbal 世田谷店",
            "prefecture": "東京都",
            "hours": "朝9:00〜夜22:00（年中無休）",
            "tel": "03-5555-0199",
            "parking": "専用駐車場 120台完備",
            "Address": "東京都世田谷区〇〇 1-2-3",
        },
        "community": {
            "regular_events": ["毎週火曜日は火曜市", "毎週木曜シニアデー10%引", "子育て応援パスポート提示で5%OFF"],
            "announcement": "11月15日(日) 朝10時より 本まぐろ解体ショー＆試食販売を開催！",
            "reservation": "クリスマスケーキ・特選おせち 早期ご予約承り中（11/30まで早割10%OFF）",
            "qr_url": os.environ.get("STORE_URL") or os.environ.get("ONLINE_STORE_URL") or "https://cymbal-retail.example.com",
            "qr_label": "ネットスーパー＆公式アプリ クーポンはこちら",
            "disclaimer": "※写真はイメージです。※チラシ掲載品は豊富に取り揃えておりますが、万一品切れの際はご容赦ください。※価格は本体価格と税込参考価格を併記しています。",
        },
        "zones": [
            {
                "id": z["id"],
                "title": z["title"],
                "subtitle": z.get("subtitle", ""),
                "zone_type": z.get("zone_type", "day_block"),
                "frame_color": z.get("frame_color", "red"),
                "uniform_price_ex": z.get("uniform_price_ex"),
                "uniform_price_inc": z.get("uniform_price_inc"),
                "categories": z.get("categories") or [],
                "hero_count": z.get("hero_count", 0),
                "grid_count": z.get("grid_count", 0),
            }
            for z in (resolved_tpl.get("zones") or [])
        ],
        "slots": slots,
        "menu_proposals": [],
        "status": "承認済み",
        "created_by": {"id": "staff-sato", "name": "販促担当 佐藤", "role": "staff"},
        "created_at": "2026-10-27T14:20:00+09:00",
        "submitted_by": {"id": "staff-sato", "name": "販促担当 佐藤", "role": "staff"},
        "submitted_at": "2026-10-27T16:00:00+09:00",
        "approved_by": {"id": "mgr-tanaka", "name": "店長 田中", "role": "manager"},
        "approved_at": "2026-10-27T17:30:00+09:00",
        "gcs_prefix": f"approved/2026/{SAMPLE_ARCHIVE_ID}",
    }
    repo.write_json(rel, sample_doc)
    repo.record_flyer_index_in_bq(sample_doc, gcs_prefix=sample_doc["gcs_prefix"])
    return sample_doc
