"""Cymbal Retail チラシ作成スタジオ (FastAPI BFF + Japanese SPA).

Routes:
  GET  /                                         SPA (`static/index.html`, injects cross-link URLs)
  GET  /api/health, /healthz                     Health check
  GET  /api/me                                   Current logged-in user + available demo personas
  POST /api/me/switch                            Switch active logged-in user cookie (`cr_flyer_user`)
  GET  /api/templates                            Base templates (T1..T4) + custom saved templates + presets
  POST /api/templates                            Save a custom template (`テンプレートとして保存`)
  GET  /api/products/search                      Search catalog products (keyword, category, on_sale, seasonal)
  GET  /api/products/{product_id}                Get single product details
  POST /api/flyers/generate                      Generate a new flyer draft (or reuse from `base_flyer_id`)
  GET  /api/flyers/{flyer_id}                    Get draft or archived flyer
  PUT  /api/flyers/{flyer_id}                    Update draft flyer (title, store, community, zones, slots)
  GET  /api/flyers/{flyer_id}/preview_html       Rendered chirashi HTML for live preview
  POST /api/flyers/{flyer_id}/slots/{slot_id}/suggest   AI / ranked alternative product suggestion for a slot
  PUT  /api/flyers/{flyer_id}/slots/{slot_id}/offer     Set or clear flyer-only special price (`チラシ特別価格`)
  POST /api/flyers/{flyer_id}/reselect           Re-run auto-pickup for unlocked slots (`商品を選び直す`)
  POST /api/flyers/{flyer_id}/submit             Submit draft for manager review (`確認を依頼`)
  POST /api/flyers/{flyer_id}/approve            Manager approval + GCS archive (`承認して保管`)
  POST /api/flyers/{flyer_id}/reject             Manager rejection back to draft (`差し戻し`)
  POST /api/flyers/{flyer_id}/export             Export PDF or JPEG (`?format=pdf|jpeg&dpi=150|300`)
  GET  /api/archive                              List manager-approved archived flyers (+ drafts)
  GET  /api/archive/{flyer_id}                   View frozen snapshot of an approved flyer
"""
from __future__ import annotations

import copy
import datetime as dt
import html as _html
import logging
import os
import re
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .archive import (
    JST,
    SAMPLE_ARCHIVE_ID,
    apply_slot_offer,
    create_draft_from_archived,
    ensure_sample_archived_flyer,
    hydrate_flyer_live,
    load_draft,
    now_jst_iso,
    render_archived_flyer_view,
    save_draft,
    snapshot_flyer_for_approval,
)
from .bg_gen import BG_PRESETS, generate_background_image
from .composer import compose_flyer_draft, hydrate_slot_product, suggest_slot_replacement
from .cutout import get_product_cutout_png_bytes
from .render import _resolve_local_image_file, export_flyer_jpeg, export_flyer_pdf, render_flyer_html
from .repository import FlyerRepository
from .templates import (
    BADGE_PRESETS,
    BASE_TEMPLATES,
    FRAME_SHAPES,
    LAYOUT_MODES,
    NUMERAL_STYLES,
    OVERLAY_POSITIONS,
    PAPER_FORMATS,
    PRICE_STYLES,
    SLOT_BG_PALETTES,
    SLOT_SPANS,
    build_template_slots,
    recommend_template_id,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cymbal-flyer")

APP_DIR = Path(__file__).resolve().parent
SERVICE_DIR = APP_DIR.parent
REPO_DIR = SERVICE_DIR.parent
STATIC_DIR = Path(os.environ.get("STATIC_DIR", str(SERVICE_DIR / "static")))
PRODUCTS_IMG_DIR = (
    SERVICE_DIR / "static" / "img" / "products"
    if (SERVICE_DIR / "static" / "img" / "products").is_dir()
    else REPO_DIR / "online-store-adk" / "static" / "img" / "products"
)

USERS: dict[str, dict[str, str]] = {
    "mgr-tanaka": {
        "id": "mgr-tanaka",
        "name": os.environ.get("DEFAULT_MANAGER_NAME", "店長 田中"),
        "role": "manager",
        "role_label": "店舗責任者（承認権限あり）",
    },
    "staff-sato": {
        "id": "staff-sato",
        "name": os.environ.get("DEFAULT_STAFF_NAME", "販促担当 佐藤"),
        "role": "staff",
        "role_label": "販促担当（作成・確認依頼）",
    },
}
DEFAULT_USER_ID = os.environ.get("DEFAULT_FLYER_USER_ID", "mgr-tanaka")

_repo: FlyerRepository | None = None


def get_repo() -> FlyerRepository:
    global _repo
    if _repo is None:
        _repo = FlyerRepository()
        try:
            ensure_sample_archived_flyer(_repo)
        except Exception as e:  # noqa: BLE001
            log.warning("Could not seed sample archived flyer: %s", e)
    return _repo


def reset_repo(force_local: bool = False) -> FlyerRepository:
    global _repo
    _repo = FlyerRepository(force_local=force_local)
    ensure_sample_archived_flyer(_repo)
    return _repo


def current_user(request: Request) -> dict[str, str]:
    """Resolve currently logged-in user from IAP header, `X-Flyer-User` header, or `cr_flyer_user` cookie."""
    iap_email = request.headers.get("X-Goog-Authenticated-User-Email", "")
    uid = (
        request.headers.get("X-Flyer-User", "").strip()
        or request.cookies.get("cr_flyer_user", "").strip()
        or DEFAULT_USER_ID
    )
    if uid in USERS:
        return dict(USERS[uid])
    if iap_email:
        clean = iap_email.split(":")[-1]
        return {"id": clean, "name": clean, "role": "manager", "role_label": "店舗責任者（承認権限あり）"}
    return dict(USERS[DEFAULT_USER_ID])


def _store_url() -> str:
    u = (os.environ.get("STORE_URL") or os.environ.get("ONLINE_STORE_URL") or "").strip()
    return u if u.startswith(("https://", "http://")) else ""


def _enrich_url() -> str:
    u = (os.environ.get("ENRICH_URL") or "").strip()
    return u if u.startswith(("https://", "http://")) else ""


app = FastAPI(title="Cymbal Retail チラシ作成スタジオ", version="1.0.0")


@app.on_event("startup")
async def _startup() -> None:
    get_repo()


@app.get("/healthz")
@app.get("/api/health")
def healthz():
    repo = get_repo()
    return {"ok": True, "catalog_size": len(repo.items), "source": repo.source}


@app.get("/api/me")
def api_me(request: Request):
    u = current_user(request)
    return {
        "user": u,
        "available_users": list(USERS.values()),
        "links": {"store_url": _store_url(), "enrich_url": _enrich_url()},
    }


@app.post("/api/me/switch")
def api_me_switch(payload: dict = Body(default={})):
    uid = str(payload.get("user_id") or "").strip()
    if uid not in USERS:
        return JSONResponse({"error": "指定されたユーザーが見つかりません。"}, status_code=400)
    resp = JSONResponse({"ok": True, "user": USERS[uid]})
    resp.set_cookie("cr_flyer_user", uid, max_age=60 * 60 * 24 * 30, path="/", samesite="lax")
    return resp


def _all_templates(repo: FlyerRepository) -> dict[str, dict[str, Any]]:
    out = copy.deepcopy(BASE_TEMPLATES)
    for custom in repo.list_json_prefix("templates"):
        cid = custom.get("id")
        if cid:
            out[cid] = custom
    return out


@app.get("/api/templates")
def api_templates():
    repo = get_repo()
    tpls = list(_all_templates(repo).values())
    return {
        "templates": tpls,
        "frame_shapes": FRAME_SHAPES,
        "layout_modes": LAYOUT_MODES,
        "overlay_positions": OVERLAY_POSITIONS,
        "slot_spans": SLOT_SPANS,
        "numeral_styles": NUMERAL_STYLES,
        "slot_bg_palettes": SLOT_BG_PALETTES,
        "bg_presets": BG_PRESETS,
        "price_styles": PRICE_STYLES,
        "badge_presets": BADGE_PRESETS,
        "paper_formats": PAPER_FORMATS,
        "categories": repo.categories(),
    }


@app.post("/api/bg_images/generate")
def api_generate_bg_image(payload: dict = Body(default={})):
    repo = get_repo()
    prompt = str(payload.get("prompt") or "").strip()
    preset_id = str(payload.get("preset_id") or "autumn_wood").strip()
    try:
        res = generate_background_image(repo, prompt=prompt, preset_id=preset_id)
        return {"ok": True, "bg": res}
    except Exception as e:  # noqa: BLE001
        log.exception("bg_image generation failed")
        return JSONResponse({"error": f"背景画像の生成に失敗しました: {e}"}, status_code=500)


@app.get("/api/bg_images/{bg_file}")
def api_get_bg_image(bg_file: str):
    clean = re.sub(r"[^a-zA-Z0-9._-]", "", bg_file)
    data = get_repo().read_bytes(f"bg_images/{clean}")
    if not data:
        return Response(status_code=404)
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/product_cutout/{img_file}")
def api_get_product_cutout(img_file: str):
    """Serve catalog product image with its studio white background and outer shadow removed as a transparent PNG."""
    clean = re.sub(r"[^a-zA-Z0-9._-]", "", img_file)
    p = _resolve_local_image_file(clean)
    if p is None or not p.is_file():
        return Response(status_code=404)
    try:
        png_bytes = get_product_cutout_png_bytes(p)
        return Response(png_bytes, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
    except Exception:  # noqa: BLE001
        return Response(p.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.post("/api/templates")
def api_save_template(request: Request, payload: dict = Body(default={})):
    repo = get_repo()
    user = current_user(request)
    name = str(payload.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "テンプレート名を入力してください。"}, status_code=400)

    base_id = str(payload.get("base_template_id") or "T1")
    all_tpls = _all_templates(repo)
    base_tpl = copy.deepcopy(all_tpls.get(base_id) or BASE_TEMPLATES["T1"])

    zones_in = payload.get("zones")
    if isinstance(zones_in, list) and zones_in:
        new_zones = []
        for z in zones_in:
            hero_c = max(0, int(z.get("hero_count", 1)))
            grid_c = max(0, int(z.get("grid_count", 3)))
            if hero_c + grid_c == 0:
                grid_c = 1
            new_zones.append({
                "id": str(z.get("id") or f"z-{uuid.uuid4().hex[:4]}"),
                "title": str(z.get("title") or "特売コーナー"),
                "subtitle": str(z.get("subtitle") or ""),
                "zone_type": str(z.get("zone_type") or "day_block"),
                "frame_color": str(z.get("frame_color") or "red"),
                "weight": float(z.get("weight") or 1.0),
                "bg_image_url": str(z.get("bg_image_url") or ""),
                "uniform_price_ex": z.get("uniform_price_ex"),
                "uniform_price_inc": z.get("uniform_price_inc"),
                "categories": list(z.get("categories") or []),
                "hero_count": hero_c,
                "grid_count": grid_c,
                "hero_shape": str(z.get("hero_shape") or "overflow_cutout"),
                "grid_shape": str(z.get("grid_shape") or "rect"),
                "hero_layout_mode": str(z.get("hero_layout_mode") or "overlay_full"),
                "grid_layout_mode": str(z.get("grid_layout_mode") or "overlay_price"),
                "default_badge": str(z.get("default_badge") or "特価"),
                "slot_overrides": dict(z.get("slot_overrides") or {}),
            })
        base_tpl["zones"] = new_zones

    total_cnt = sum(int(z.get("hero_count", 0)) + int(z.get("grid_count", 0)) for z in base_tpl["zones"])
    if payload.get("default_item_count"):
        total_cnt = max(1, int(payload["default_item_count"]))

    tpl_id = str(payload.get("id") or f"UT-{uuid.uuid4().hex[:6].upper()}")
    custom_tpl = {
        **base_tpl,
        "id": tpl_id,
        "name": name,
        "description": str(payload.get("description") or base_tpl.get("description") or ""),
        "is_custom": True,
        "paper": str(payload.get("paper") or base_tpl.get("paper") or "B4-landscape"),
        "default_tone": str(payload.get("default_tone") or base_tpl.get("default_tone") or "にぎやか"),
        "default_numeral_style": str(payload.get("default_numeral_style") or base_tpl.get("default_numeral_style") or "graphic_pop"),
        "default_layout_mode": str(payload.get("default_layout_mode") or base_tpl.get("default_layout_mode") or "overlay_full"),
        "bg_image_url": str(payload.get("bg_image_url") if "bg_image_url" in payload else (base_tpl.get("bg_image_url") or "")),
        "slot_overrides": dict(payload.get("slot_overrides") if isinstance(payload.get("slot_overrides"), dict) else (base_tpl.get("slot_overrides") or {})),
        "default_item_count": total_cnt,
        "created_by": user["name"],
        "created_at": now_jst_iso(),
    }
    repo.write_json(f"templates/{tpl_id}.json", custom_tpl)
    return {"ok": True, "template": custom_tpl}


@app.post("/api/templates/preview_html")
def api_template_preview_html(payload: dict = Body(default={})):
    """Render a live visual preview of a template definition (for the 3-column Template Studio tab)."""
    repo = get_repo()
    base_id = str(payload.get("id") or payload.get("base_template_id") or "T1")
    all_tpls = _all_templates(repo)
    tpl = copy.deepcopy(all_tpls.get(base_id) or BASE_TEMPLATES["T1"])
    for k in ("name", "paper", "default_tone", "default_numeral_style", "default_layout_mode", "bg_image_url", "default_item_count"):
        if k in payload and payload[k] is not None:
            tpl[k] = payload[k]
    if isinstance(payload.get("slot_overrides"), dict):
        tpl["slot_overrides"] = payload["slot_overrides"]
    if isinstance(payload.get("zones"), list) and payload["zones"]:
        tpl["zones"] = payload["zones"]

    resolved_tpl, flat_slots, _ = build_template_slots(tpl)
    sample_prods = repo.search_products(on_sale=True, limit=max(40, len(flat_slots) * 2))
    slots_out = []
    for idx, s in enumerate(flat_slots):
        p = sample_prods[idx % len(sample_prods)] if sample_prods else {}
        shape_label = next((x["label"].split("（")[0] for x in FRAME_SHAPES if x["id"] == s["shape"]), s["shape"])
        layout_label = next((x["label"].split("（")[0] for x in LAYOUT_MODES if x["id"] == s.get("layout_mode")), "")
        slots_out.append({
            **s,
            "product_id": p.get("id", f"SAMPLE-{idx+1}"),
            "catch_copy": f"【{s['slot_id']}】{shape_label}・{layout_label}"[:24],
            "badge": s.get("default_badge") or "特価",
            "product": p,
        })
    sample_doc = {
        "id": "tpl-preview",
        "template_id": tpl.get("id") or "T1",
        "paper": tpl.get("paper") or "B4-landscape",
        "tone": tpl.get("default_tone") or "にぎやか",
        "numeral_style": tpl.get("default_numeral_style") or "graphic_pop",
        "bg_image_url": tpl.get("bg_image_url") or "",
        "title": f"【テンプレート構成プレビュー】{tpl.get('name') or 'チラシテンプレート'}",
        "subtitle": f"全 {len(slots_out)} 枠（ゾーン数: {len(resolved_tpl.get('zones') or [])}）— 紙面上の任意の枠・ゾーンをクリックすると右パネルでサイズ・形態・重ね配置を編集できます",
        "theme": "テンプレート構成プレビュー",
        "target": "全ターゲット対応",
        "period": {"from": "2026-11-11", "to": "2026-11-17"},
        "store": {"name": "Cymbal 世田谷店", "prefecture": "東京都", "hours": "朝9:00〜夜22:00", "tel": "03-5555-0199"},
        "community": {},
        "zones": resolved_tpl.get("zones") or [],
        "slots": slots_out,
        "menu_proposals": [],
        "status": "承認済み",
    }
    html_str = render_flyer_html(sample_doc, interactive=True, embed_images=False)
    return HTMLResponse(html_str, headers={"Cache-Control": "no-store"})


@app.get("/api/products/search")
def api_products_search(
    q: str = "",
    category: str = "",
    on_sale: bool = False,
    seasonal: bool = False,
    limit: int = 36,
):
    repo = get_repo()
    items = repo.search_products(q=q, category=category, on_sale=on_sale, seasonal=seasonal, limit=limit)
    return {"products": items, "total": len(items)}


@app.get("/api/products/{product_id}")
def api_product_detail(product_id: str):
    p = get_repo().get_product(product_id)
    if not p:
        return JSONResponse({"error": "指定された商品は商品マスタに存在しません（販売終了）。"}, status_code=404)
    return {"product": p}


def _find_archived_flyer(repo: FlyerRepository, flyer_id: str) -> dict[str, Any] | None:
    for year in ("2026", "2025", "2027"):
        doc = repo.read_json(f"approved/{year}/{flyer_id}/flyer.json")
        if doc:
            return doc
    for doc in repo.list_json_prefix("approved"):
        if doc.get("id") == flyer_id:
            return doc
    return None


@app.post("/api/flyers/generate")
def api_flyers_generate(request: Request, payload: dict = Body(default={})):
    repo = get_repo()
    user = current_user(request)

    base_flyer_id = str(payload.get("base_flyer_id") or "").strip()
    theme = str(payload.get("theme") or "秋の味覚フェア").strip()
    target = str(payload.get("target") or "40代主婦・4人家族").strip()
    period = payload.get("period") if isinstance(payload.get("period"), dict) else {}
    period_from = str(period.get("from") or "2026-11-11").strip()
    period_to = str(period.get("to") or "2026-11-17").strip()

    # Case 1: Reuse from an archived or existing flyer (`base_flyer_id`) -> re-hydrate product codes from master
    if base_flyer_id:
        src_doc = _find_archived_flyer(repo, base_flyer_id) or load_draft(repo, base_flyer_id)
        if not src_doc:
            return JSONResponse({"error": f"元となるチラシが見つかりません: {base_flyer_id}"}, status_code=404)
        new_draft = create_draft_from_archived(
            repo=repo,
            archived_doc=src_doc,
            creator=user,
            new_theme=payload.get("theme"),
            new_target=payload.get("target"),
            period_from=period_from,
            period_to=period_to,
        )
        saved = save_draft(repo, new_draft)
        repo.record_flyer_index_in_bq(saved)
        return {"flyer": saved}

    # Case 2: Generate a fresh flyer draft from template + auto-pickup + Gemini
    all_tpls = _all_templates(repo)
    tone = str(payload.get("tone") or "").strip()
    tpl_id = str(payload.get("template_id") or "").strip() or recommend_template_id(theme, tone)
    tpl = all_tpls.get(tpl_id) or all_tpls["T1"]

    item_count_raw = payload.get("item_count")
    item_count = int(item_count_raw) if item_count_raw is not None and str(item_count_raw).strip() != "" else int(tpl.get("default_item_count") or 20)
    zone_counts = payload.get("zone_counts") if isinstance(payload.get("zone_counts"), dict) else None

    store_in = payload.get("store") if isinstance(payload.get("store"), dict) else {}
    store = {
        "name": str(store_in.get("name") or "Cymbal 世田谷店"),
        "prefecture": str(store_in.get("prefecture") or "東京都"),
        "hours": str(store_in.get("hours") or "朝9:00〜夜22:00（年中無休）"),
        "tel": str(store_in.get("tel") or "03-5555-0199"),
        "parking": str(store_in.get("parking") or "専用駐車場 120台完備"),
    }
    comm_in = payload.get("community") if isinstance(payload.get("community"), dict) else {}
    reg_ev = comm_in.get("regular_events")
    if isinstance(reg_ev, str):
        reg_ev = [x.strip() for x in reg_ev.split("・") if x.strip()]
    community = {
        "regular_events": reg_ev or ["毎週火曜日は火曜市", "毎週木曜シニアデー5%OFF", "子育て応援パスポート5%OFF"],
        "announcement": str(comm_in.get("announcement") or "週末朝市・旬の試食販売を開催！地域生産者直売コーナーも毎日入荷中"),
        "reservation": str(comm_in.get("reservation") or "クリスマスケーキ・特選おせち 早期ご予約承り中（早割10%OFF）"),
        "qr_url": str(comm_in.get("qr_url") or _store_url() or "https://cymbal-retail.example.com"),
        "qr_label": str(comm_in.get("qr_label") or "ネットスーパー＆公式LINEクーポン"),
        "disclaimer": str(
            comm_in.get("disclaimer")
            or "※写真はすべてイメージです。※チラシ掲載品は豊富に取り揃えておりますが、万一品切れの際はご容赦ください。※価格は本体価格と税込参考価格を併記しています。"
        ),
    }

    composed = compose_flyer_draft(
        repo=repo,
        template=tpl,
        theme=theme,
        target=target,
        period_from=period_from,
        period_to=period_to,
        store=store,
        community=community,
        item_count=item_count,
        zone_counts=zone_counts,
    )

    flyer_id = f"fl-{dt.datetime.now(JST).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
    flyer_doc = {
        "id": flyer_id,
        "template_id": tpl["id"],
        "paper": str(payload.get("paper") or tpl.get("paper") or "B4-landscape"),
        "tone": tone or tpl.get("default_tone") or "にぎやか",
        "numeral_style": str(payload.get("numeral_style") or tpl.get("default_numeral_style") or "graphic_pop"),
        "sheet_bg": str(payload.get("sheet_bg") or ""),
        "bg_image_url": str(payload.get("bg_image_url") if "bg_image_url" in payload else (tpl.get("bg_image_url") or "")),
        "title": composed["title"],
        "subtitle": composed["subtitle"],
        "lead_copy": composed["lead_copy"],
        "theme": theme,
        "target": target,
        "period": {"from": period_from, "to": period_to},
        "store": store,
        "community": community,
        "zones": composed["zones"],
        "slots": composed["slots"],
        "menu_proposals": composed["menu_proposals"],
        "anniversaries": composed["anniversaries"],
        "composer_mode": composed["composer_mode"],
        "density_warning": composed["density_warning"],
        "status": "下書き",
        "created_by": {"id": user["id"], "name": user["name"], "role": user["role"]},
        "created_at": now_jst_iso(),
        "approved_by": None,
        "approved_at": None,
    }
    saved = save_draft(repo, flyer_doc)
    repo.record_flyer_index_in_bq(saved)
    return {"flyer": saved}


@app.get("/api/flyers/{flyer_id}")
def api_get_flyer(flyer_id: str):
    repo = get_repo()
    doc = load_draft(repo, flyer_id)
    if doc:
        return {"flyer": doc}
    arch = _find_archived_flyer(repo, flyer_id)
    if arch:
        return {"flyer": render_archived_flyer_view(repo, arch)}
    return JSONResponse({"error": "指定されたチラシが見つかりません。"}, status_code=404)


@app.put("/api/flyers/{flyer_id}")
def api_update_flyer(flyer_id: str, payload: dict = Body(default={})):
    repo = get_repo()
    existing = load_draft(repo, flyer_id)
    if not existing:
        if _find_archived_flyer(repo, flyer_id):
            return JSONResponse({"error": "承認済みのチラシは編集できません。「このチラシをもとに新規作成」をご利用ください。"}, status_code=409)
        return JSONResponse({"error": "指定されたチラシが見つかりません。"}, status_code=404)
    if existing.get("status") == "承認済み":
        return JSONResponse({"error": "承認済みのチラシは編集できません。"}, status_code=409)

    # Update top-level fields
    for field in ("title", "subtitle", "lead_copy", "theme", "target", "paper", "tone", "template_id", "numeral_style", "sheet_bg", "bg_image_url"):
        if field in payload and payload[field] is not None:
            existing[field] = payload[field]
    if isinstance(payload.get("period"), dict):
        existing["period"] = {**existing.get("period", {}), **payload["period"]}
    if isinstance(payload.get("store"), dict):
        existing["store"] = {**existing.get("store", {}), **payload["store"]}
    if isinstance(payload.get("community"), dict):
        existing["community"] = {**existing.get("community", {}), **payload["community"]}
    if isinstance(payload.get("zones"), list):
        existing["zones"] = payload["zones"]

    # Update slots & validate price_style rules
    if isinstance(payload.get("slots"), list):
        updated_slots = []
        for s_in in payload["slots"]:
            hydrated = hydrate_slot_product(repo, s_in, s_in.get("offer"))
            req_style = s_in.get("price_style")
            prod = hydrated.get("product") or {}
            has_disc = int(prod.get("original_price_tax_excluded") or 0) > int(prod.get("price_tax_excluded") or 0)
            if req_style in ("was_now", "percent_off") and not has_disc:
                return JSONResponse(
                    {"error": f"枠「{s_in.get('slot_id')}」の商品は通常価格より低い特価ではないため、「通常価格→特別価格」または「%OFF」表記は選択できません。"},
                    status_code=400,
                )
            updated_slots.append(hydrated)
        existing["slots"] = updated_slots

    # Single-slot patch convenience (`slot_update`)
    if isinstance(payload.get("slot_update"), dict):
        su = payload["slot_update"]
        sid = su.get("slot_id")
        slots = existing.get("slots") or []
        target_s = next((x for x in slots if x.get("slot_id") == sid), None)
        if not target_s:
            return JSONResponse({"error": f"指定された枠が見つかりません: {sid}"}, status_code=404)
        old_pid = target_s.get("product_id")
        for k in (
            "product_id",
            "shape",
            "size",
            "size_span",
            "width_weight",
            "row_weight",
            "img_scale",
            "layout_mode",
            "overlay_pos",
            "numeral_style",
            "bg_color",
            "bg_image_url",
            "price_style",
            "badge",
            "catch_copy",
            "locked",
        ):
            if k in su:
                target_s[k] = su[k]
        if "img_scale" in su:
            target_s["user_custom_scale"] = True
        if "layout_mode" in su:
            target_s["user_custom_layout"] = True
        if "product_id" in su and str(su["product_id"]) != str(old_pid):
            target_s["offer"] = None
            target_s["discontinued"] = False
            target_s.pop("user_custom_scale", None)
        hydrated = hydrate_slot_product(repo, target_s, target_s.get("offer"))
        prod = hydrated.get("product") or {}
        has_disc = int(prod.get("original_price_tax_excluded") or 0) > int(prod.get("price_tax_excluded") or 0)
        if su.get("price_style") in ("was_now", "percent_off") and not has_disc:
            return JSONResponse(
                {"error": "通常価格より低い特価ではない商品には、「通常価格→特別価格」または「%OFF」表記は選択できません。先にチラシ特別価格を設定するか、「本体＋税込併記」をお選びください。"},
                status_code=400,
            )
        idx = slots.index(target_s)
        slots[idx] = hydrated

    saved = save_draft(repo, existing)
    return {"flyer": saved}


@app.get("/api/flyers/{flyer_id}/preview_html")
def api_flyer_preview_html(flyer_id: str, interactive: bool = True):
    repo = get_repo()
    doc = load_draft(repo, flyer_id)
    if not doc:
        arch = _find_archived_flyer(repo, flyer_id)
        if not arch:
            return HTMLResponse("<p>チラシが見つかりません</p>", status_code=404)
        doc = render_archived_flyer_view(repo, arch)
    html_str = render_flyer_html(doc, interactive=interactive, embed_images=False)
    return HTMLResponse(html_str, headers={"Cache-Control": "no-store"})


@app.post("/api/flyers/{flyer_id}/slots/{slot_id}/suggest")
def api_slot_suggest(flyer_id: str, slot_id: str):
    repo = get_repo()
    doc = load_draft(repo, flyer_id)
    if not doc:
        return JSONResponse({"error": "下書きチラシが見つかりません。"}, status_code=404)
    if doc.get("status") == "承認済み":
        return JSONResponse({"error": "承認済みのチラシは変更できません。"}, status_code=409)
    new_slot = suggest_slot_replacement(repo, doc, slot_id)
    if not new_slot:
        return JSONResponse({"error": "代替候補の商品が見つかりませんでした。"}, status_code=404)
    slots = doc.get("slots") or []
    for i, s in enumerate(slots):
        if s.get("slot_id") == slot_id:
            slots[i] = new_slot
            break
    saved = save_draft(repo, doc)
    return {"flyer": saved, "slot": new_slot}


@app.put("/api/flyers/{flyer_id}/slots/{slot_id}/offer")
def api_slot_offer(request: Request, flyer_id: str, slot_id: str, payload: dict = Body(default={})):
    repo = get_repo()
    user = current_user(request)
    doc = load_draft(repo, flyer_id)
    if not doc:
        return JSONResponse({"error": "下書きチラシが見つかりません。"}, status_code=404)
    raw_price = payload.get("offer_price_tax_excluded")
    limit_text = str(payload.get("limit_text") or "")
    try:
        price_val = None if (raw_price is None or str(raw_price).strip() == "") else int(raw_price)
        saved, warning = apply_slot_offer(repo, doc, slot_id, price_val, limit_text, user)
        return {"flyer": saved, "warning": warning}
    except PermissionError as e:
        return JSONResponse({"error": str(e)}, status_code=409)
    except (ValueError, KeyError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/flyers/{flyer_id}/apply_template")
def api_flyer_apply_template(flyer_id: str, payload: dict = Body(default={})):
    """Immediately switch the current flyer's template & layout structure while keeping existing products (or filling new slots)."""
    repo = get_repo()
    doc = load_draft(repo, flyer_id)
    if not doc:
        return JSONResponse({"error": "下書きチラシが見つかりません。"}, status_code=404)
    if doc.get("status") == "承認済み":
        return JSONResponse({"error": "承認済みのチラシは変更できません。"}, status_code=409)

    tpl_id = str(payload.get("template_id") or doc.get("template_id") or "T1")
    all_tpls = _all_templates(repo)
    tpl = all_tpls.get(tpl_id) or all_tpls["T1"]
    req_count = int(payload.get("item_count") or tpl.get("default_item_count") or len(doc.get("slots") or []) or 20)

    resolved_tpl, flat_slots, density_warning = build_template_slots(tpl, item_count=req_count)
    old_slots = doc.get("slots") or []

    # Map existing products onto the new template's slots, and fill any extra slots via deterministic pickup
    from .picker import select_candidates_for_template

    used_pids = {str(s.get("product_id")) for s in old_slots[: len(flat_slots)] if s.get("product_id")}
    pickup = select_candidates_for_template(
        repo=repo,
        resolved_template=resolved_tpl,
        theme=doc.get("theme") or "",
        target=doc.get("target") or "",
        period_from=(doc.get("period") or {}).get("from") or "2026-11-11",
        period_to=(doc.get("period") or {}).get("to") or "2026-11-17",
        store_prefecture=(doc.get("store") or {}).get("prefecture") or "",
        locked_product_ids=used_pids,
    )
    extra_pool: list[dict] = []
    for cands in pickup["zone_candidates"].values():
        extra_pool.extend(cands)
    extra_idx = 0

    new_slots = []
    for idx, ts in enumerate(flat_slots):
        if idx < len(old_slots):
            prev = old_slots[idx]
            merged = {
                **ts,
                "product_id": prev.get("product_id"),
                "catch_copy": prev.get("catch_copy") or "",
                "badge": prev.get("badge") or ts.get("default_badge") or "特価",
                "reason": prev.get("reason") or "おすすめ特売品",
                "locked": bool(prev.get("locked")),
                "offer": prev.get("offer"),
                "snapshot": prev.get("snapshot"),
            }
            new_slots.append(hydrate_slot_product(repo, merged, prev.get("offer")))
        else:
            while extra_idx < len(extra_pool) and extra_pool[extra_idx]["id"] in used_pids:
                extra_idx += 1
            cand = extra_pool[extra_idx] if extra_idx < len(extra_pool) else (old_slots[0].get("product") or {})
            extra_idx += 1
            pid = str(cand.get("id") or "")
            used_pids.add(pid)
            merged = {
                **ts,
                "product_id": pid,
                "catch_copy": cand.get("promo_text") or "今週のおすすめ特価",
                "badge": ts.get("default_badge") or "特価",
                "reason": cand.get("pickup_reason") or "おすすめ特売品",
                "locked": False,
                "offer": None,
            }
            new_slots.append(hydrate_slot_product(repo, merged))

    doc["template_id"] = tpl["id"]
    doc["paper"] = tpl.get("paper") or doc.get("paper") or "B4-landscape"
    doc["tone"] = tpl.get("default_tone") or doc.get("tone") or "にぎやか"
    doc["numeral_style"] = tpl.get("default_numeral_style") or doc.get("numeral_style") or "graphic_pop"
    if tpl.get("bg_image_url"):
        doc["bg_image_url"] = tpl["bg_image_url"]
    doc["zones"] = [
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
    ]
    doc["slots"] = new_slots
    doc["density_warning"] = density_warning
    saved = save_draft(repo, doc)
    return {"flyer": saved}


@app.post("/api/flyers/{flyer_id}/reselect")
def api_flyer_reselect(flyer_id: str, payload: dict = Body(default={})):
    """Re-run auto-pickup for all unlocked slots (`商品を選び直す`) while keeping locked slots intact."""
    repo = get_repo()
    doc = load_draft(repo, flyer_id)
    if not doc:
        return JSONResponse({"error": "下書きチラシが見つかりません。"}, status_code=404)
    if doc.get("status") == "承認済み":
        return JSONResponse({"error": "承認済みのチラシは変更できません。"}, status_code=409)

    theme = str(payload.get("theme") if "theme" in payload else (doc.get("theme") or ""))
    target = str(payload.get("target") if "target" in payload else (doc.get("target") or ""))
    period = payload.get("period") if isinstance(payload.get("period"), dict) else (doc.get("period") or {})
    item_count = int(payload.get("item_count") or len(doc.get("slots") or []) or 20)

    locked_map = {
        s["slot_id"]: s for s in (doc.get("slots") or []) if s.get("locked") and not s.get("discontinued")
    }
    all_tpls = _all_templates(repo)
    tpl = all_tpls.get(doc.get("template_id") or "T1") or all_tpls["T1"]

    composed = compose_flyer_draft(
        repo=repo,
        template=tpl,
        theme=theme,
        target=target,
        period_from=str(period.get("from") or "2026-11-11"),
        period_to=str(period.get("to") or "2026-11-17"),
        store=doc.get("store") or {},
        community=doc.get("community") or {},
        item_count=item_count,
        existing_locked_slots=locked_map,
    )
    doc["theme"] = theme
    doc["target"] = target
    doc["period"] = period
    doc["title"] = composed["title"]
    doc["subtitle"] = composed["subtitle"]
    doc["zones"] = composed["zones"]
    doc["slots"] = composed["slots"]
    doc["menu_proposals"] = composed["menu_proposals"]
    doc["density_warning"] = composed["density_warning"]
    saved = save_draft(repo, doc)
    return {"flyer": saved}


@app.post("/api/flyers/{flyer_id}/submit")
def api_flyer_submit(request: Request, flyer_id: str):
    repo = get_repo()
    user = current_user(request)
    doc = load_draft(repo, flyer_id)
    if not doc:
        return JSONResponse({"error": "下書きチラシが見つかりません。"}, status_code=404)
    if doc.get("status") == "承認済み":
        return JSONResponse({"error": "すでに承認済みです。"}, status_code=409)
    if doc.get("discontinued_count", 0) > 0:
        return JSONResponse(
            {"error": f"販売終了の商品が {doc['discontinued_count']} 点残っているため、確認依頼できません。該当枠をクリックして代替商品に差し替えてください。"},
            status_code=400,
        )
    doc["status"] = "確認待ち"
    doc["submitted_by"] = {"id": user["id"], "name": user["name"], "role": user["role"]}
    doc["submitted_at"] = now_jst_iso()
    saved = save_draft(repo, doc)
    repo.record_flyer_index_in_bq(saved)
    return {"flyer": saved}


@app.post("/api/flyers/{flyer_id}/approve")
def api_flyer_approve(request: Request, flyer_id: str):
    repo = get_repo()
    user = current_user(request)
    if user.get("role") != "manager":
        return JSONResponse(
            {"error": f"現在のログインユーザー（{user.get('name')}）には承認権限がありません。店舗責任者（店長 田中）でログインしてください。"},
            status_code=403,
        )
    doc = load_draft(repo, flyer_id)
    if not doc:
        return JSONResponse({"error": "下書きチラシが見つかりません。"}, status_code=404)
    if doc.get("status") == "承認済み":
        return JSONResponse({"error": "すでに承認済みです。"}, status_code=409)

    try:
        approved_doc = snapshot_flyer_for_approval(repo, doc, user)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    year = (approved_doc.get("period", {}).get("from") or "2026")[:4] or "2026"
    prefix = f"approved/{year}/{flyer_id}"
    approved_doc["gcs_prefix"] = prefix

    # Generate archival PDF and JPEG artifacts and store in GCS alongside flyer.json
    try:
        pdf_bytes = export_flyer_pdf(approved_doc)
        jpg_bytes = export_flyer_jpeg(approved_doc, dpi=300, pdf_bytes=pdf_bytes)
        repo.write_bytes(f"{prefix}/flyer.pdf", pdf_bytes, "application/pdf")
        repo.write_bytes(f"{prefix}/flyer.jpg", jpg_bytes, "image/jpeg")
    except Exception as e:  # noqa: BLE001
        log.warning("Archival PDF/JPEG render warning: %s", e)

    repo.write_json(f"{prefix}/flyer.json", approved_doc)
    # Also mark draft path as approved so direct lookups know it is frozen
    repo.write_json(f"drafts/{flyer_id}/flyer.json", approved_doc)
    repo.record_flyer_index_in_bq(approved_doc, gcs_prefix=prefix)
    return {"flyer": render_archived_flyer_view(repo, approved_doc)}


@app.post("/api/flyers/{flyer_id}/reject")
def api_flyer_reject(request: Request, flyer_id: str, payload: dict = Body(default={})):
    repo = get_repo()
    user = current_user(request)
    if user.get("role") != "manager":
        return JSONResponse(
            {"error": f"現在のログインユーザー（{user.get('name')}）には差し戻し権限がありません。店舗責任者でログインしてください。"},
            status_code=403,
        )
    doc = load_draft(repo, flyer_id)
    if not doc:
        return JSONResponse({"error": "下書きチラシが見つかりません。"}, status_code=404)
    if doc.get("status") == "承認済み":
        return JSONResponse({"error": "承認済みのチラシは差し戻しできません。"}, status_code=409)
    doc["status"] = "下書き"
    doc["rejected_by"] = {"id": user["id"], "name": user["name"], "role": user["role"]}
    doc["rejected_at"] = now_jst_iso()
    doc["reject_comment"] = str(payload.get("comment") or "内容を再確認してください。")
    saved = save_draft(repo, doc)
    return {"flyer": saved}


@app.post("/api/flyers/{flyer_id}/export")
@app.get("/api/flyers/{flyer_id}/export")
def api_flyer_export(flyer_id: str, format: str = Query("pdf"), dpi: int = Query(300)):
    repo = get_repo()
    doc = load_draft(repo, flyer_id)
    if not doc:
        arch = _find_archived_flyer(repo, flyer_id)
        if not arch:
            return JSONResponse({"error": "指定されたチラシが見つかりません。"}, status_code=404)
        doc = render_archived_flyer_view(repo, arch)

    fmt = (format or "pdf").strip().lower()
    safe_theme = re.sub(r'[\\/:*?"<>|\s]+', "_", doc.get("theme") or "今週のチラシ")[:24]
    date_part = (doc.get("period", {}).get("from") or "20261111").replace("-", "")

    if fmt in ("jpg", "jpeg"):
        jpg_bytes = export_flyer_jpeg(doc, dpi=dpi)
        filename_jp = f"チラシ_{safe_theme}_{date_part}.jpg"
        encoded_fn = urllib.parse.quote(filename_jp)
        return Response(
            jpg_bytes,
            media_type="image/jpeg",
            headers={"Content-Disposition": f"attachment; filename=\"chirashi_{date_part}.jpg\"; filename*=UTF-8''{encoded_fn}"},
        )

    pdf_bytes = export_flyer_pdf(doc)
    filename_jp = f"チラシ_{safe_theme}_{date_part}.pdf"
    encoded_fn = urllib.parse.quote(filename_jp)
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"chirashi_{date_part}.pdf\"; filename*=UTF-8''{encoded_fn}"},
    )


@app.get("/api/archive")
def api_archive_list(q: str = "", from_date: str = Query("", alias="from"), to_date: str = Query("", alias="to")):
    repo = get_repo()
    ensure_sample_archived_flyer(repo)
    approved_docs = repo.list_json_prefix("approved")
    draft_docs = [d for d in repo.list_json_prefix("drafts") if d.get("status") != "承認済み"]

    def _matches(d: dict) -> bool:
        if q:
            hay = f"{d.get('title', '')} {d.get('theme', '')} {d.get('target', '')}".lower()
            if q.lower() not in hay:
                return False
        p_from = (d.get("period") or {}).get("from") or ""
        if from_date and p_from and p_from < from_date:
            return False
        if to_date and p_from and p_from > to_date:
            return False
        return True

    def _summary(d: dict, is_archived: bool) -> dict:
        slots = d.get("slots") or []
        now_disc = sum(
            1 for s in slots if repo.get_product(str(s.get("product_id") or "")) is None
        )
        return {
            "id": d.get("id"),
            "title": d.get("title"),
            "theme": d.get("theme"),
            "target": d.get("target"),
            "template_id": d.get("template_id"),
            "paper": d.get("paper") or "B4-landscape",
            "period": d.get("period") or {},
            "item_count": len(slots),
            "status": d.get("status") or ("承認済み" if is_archived else "下書き"),
            "created_by": d.get("created_by"),
            "created_at": d.get("created_at"),
            "approved_by": d.get("approved_by"),
            "approved_at": d.get("approved_at"),
            "gcs_prefix": d.get("gcs_prefix") or "",
            "currently_discontinued_count": now_disc,
            "is_sample": d.get("id") == SAMPLE_ARCHIVE_ID,
        }

    arch_list = [_summary(d, True) for d in approved_docs if _matches(d)]
    arch_list.sort(key=lambda x: x.get("approved_at") or x.get("created_at") or "", reverse=True)

    draft_list = [_summary(d, False) for d in draft_docs if _matches(d)]
    draft_list.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    return {"archived": arch_list, "drafts": draft_list}


@app.get("/api/archive/{flyer_id}")
def api_archive_detail(flyer_id: str):
    repo = get_repo()
    ensure_sample_archived_flyer(repo)
    doc = _find_archived_flyer(repo, flyer_id)
    if not doc:
        return JSONResponse({"error": "指定された保管済みチラシが見つかりません。"}, status_code=404)
    return {"flyer": render_archived_flyer_view(repo, doc)}


@app.get("/")
def index(request: Request):
    page = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    s_url = _store_url()
    e_url = _enrich_url()
    page = (
        page.replace("{{STORE_URL}}", _html.escape(s_url, quote=True))
        .replace("{{STORE_HIDDEN}}", "" if s_url else "hidden")
        .replace("{{ENRICH_URL}}", _html.escape(e_url, quote=True))
        .replace("{{ENRICH_HIDDEN}}", "" if e_url else "hidden")
    )
    resp = HTMLResponse(page, headers={"Cache-Control": "no-store"})
    if "cr_flyer_user" not in request.cookies:
        resp.set_cookie("cr_flyer_user", DEFAULT_USER_ID, max_age=60 * 60 * 24 * 30, path="/", samesite="lax")
    return resp


if PRODUCTS_IMG_DIR.is_dir():
    app.mount("/img/products", StaticFiles(directory=PRODUCTS_IMG_DIR), name="product_images")

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
