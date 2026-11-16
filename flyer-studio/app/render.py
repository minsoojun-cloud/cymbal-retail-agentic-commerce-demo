"""Chirashi HTML/CSS/SVG Bento renderer and headless Chromium -> PDF / JPEG exporter.

Addresses all visual & layout requirements:
  1. Zero-whitespace Bento row packing (works cleanly for small 4-item flyers up to 60+ item high-density flyers).
  2. High-freedom slot shapes (`cutout`, `vertical`, `burst`, `horizontal`, `circle`, `rounded`), slot spans (`hero_2x2`, `wide_2x1`, `tall_1x2`, `std_1x1`), and custom image scale (`img_scale`).
  3. Zero text overlap + automatic font scaling (`--slot-scale` + inline SVG viewBox price lockups + JS auto-fit pass).
  4. Official Cymbal Retail target logo matching the ADK storefront (`online-store-adk/static/img/logo.svg`).
  5. Graphical 3D outlined POP numerals (`graphic_pop`, `yellow_pop`) and standard typographic numerals (`gothic_bold`, `mincho_premium`).
  6. Product-harmonized sheet, zone, and slot background colors.
"""
from __future__ import annotations

import base64
import hashlib
import html as _html
import logging
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .cutout import (
    get_product_cutout_aspect_ratio,
    get_product_cutout_path_and_bytes,
    get_product_cutout_png_bytes,
    resolve_default_slot_bg_image,
)
from .templates import PAPER_FORMATS, SLOT_BG_PALETTES, harmonize_category_bg

log = logging.getLogger("cymbal-flyer.render")

APP_DIR = Path(__file__).resolve().parent
SERVICE_DIR = APP_DIR.parent
REPO_DIR = SERVICE_DIR.parent

PAPER_BY_ID = {p["id"]: p for p in PAPER_FORMATS}
BG_BY_ID = {b["id"]: b["color"] for b in SLOT_BG_PALETTES if b.get("color")}

CYMBAL_LOGO_SVG = """<svg viewBox="0 0 196 40" class="ch-cymbal-logo" role="img" aria-label="Cymbal Retail">
  <defs>
    <linearGradient id="crg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#4285f4"/>
      <stop offset="1" stop-color="#1a5fd0"/>
    </linearGradient>
  </defs>
  <g transform="translate(20 20)">
    <circle r="17" fill="url(#crg)"/>
    <circle r="11.5" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="1.6"/>
    <circle r="6" fill="none" stroke="#fff" stroke-opacity=".85" stroke-width="1.6"/>
    <circle r="2.2" fill="#fbbc04"/>
  </g>
  <text x="45" y="27.5" font-family="'Google Sans','Noto Sans CJK JP','Noto Sans JP',sans-serif" font-size="22" font-weight="800" letter-spacing="-0.4" fill="#202124">Cymbal</text>
  <text x="126" y="27.5" font-family="'Google Sans','Noto Sans CJK JP','Noto Sans JP',sans-serif" font-size="22" font-weight="500" letter-spacing="-0.2" fill="#5f6368">Retail</text>
</svg>"""


def _esc(val: Any) -> str:
    return _html.escape(str(val if val is not None else ""), quote=True)


def _resolve_local_image_file(img_uri: str) -> Path | None:
    if not img_uri:
        return None
    name = img_uri.split("?")[0].rsplit("/", 1)[-1]
    for cand in (
        SERVICE_DIR / "static" / "img" / "products" / name,
        REPO_DIR / "online-store-adk" / "static" / "img" / "products" / name,
    ):
        if cand.is_file():
            return cand
    return None


def _img_src(img_uri: str, embed_data_uri: bool = False) -> str:
    if not img_uri:
        return ""
    p = _resolve_local_image_file(img_uri)
    if embed_data_uri:
        if p is not None:
            try:
                disk_p, png_bytes, _ = get_product_cutout_path_and_bytes(p)
                if disk_p is not None and disk_p.is_file():
                    return f"file://{_esc(str(disk_p.resolve()))}"
                b64 = base64.b64encode(png_bytes).decode("ascii")
                return f"data:image/png;base64,{b64}"
            except Exception:  # noqa: BLE001
                return f"file://{_esc(str(p.resolve()))}"
        return _esc(img_uri)
    if p is not None:
        return f"/api/product_cutout/{_esc(p.name)}"
    return _esc(img_uri)


def _bg_image_css_url(bg_url: str, embed_data_uri: bool = False) -> str:
    """Resolve `/api/bg_images/<id>.jpg` or `/static/img/bg_presets/<id>.jpg` for CSS `background-image`.
    When `embed_data_uri=True` (PDF/JPEG export), uses local `file://` URLs so Chromium shares decoded
    textures in memory instead of duplicating 80 base64 strings in RAM.
    """
    u = (bg_url or "").strip()
    if not u:
        return ""
    if embed_data_uri:
        if "/static/img/bg_presets/" in u:
            fname = u.split("/static/img/bg_presets/")[-1].split("?")[0]
            cand = SERVICE_DIR / "static" / "img" / "bg_presets" / fname
            if cand.is_file():
                return f"url('file://{_esc(str(cand.resolve()))}')"
        elif "/api/bg_images/" in u:
            fname = u.split("/api/bg_images/")[-1].split("?")[0]
            try:
                from .main import get_repo

                cache_dir = Path("/tmp/cymbal_bg_export_cache")
                cache_dir.mkdir(parents=True, exist_ok=True)
                cache_p = cache_dir / fname
                if not cache_p.is_file():
                    raw = get_repo().read_bytes(f"bg_images/{fname}")
                    if raw:
                        cache_p.write_bytes(raw)
                if cache_p.is_file():
                    return f"url('file://{_esc(str(cache_p.resolve()))}')"
            except Exception:  # noqa: BLE001
                pass
    return f"url('{_esc(u)}')"


def _svg_qr_matrix(text: str) -> str:
    digest = hashlib.sha256((text or "https://cymbal.example").encode("utf-8")).digest()
    n = 15
    cells: list[str] = []

    def is_finder(r: int, c: int) -> tuple[bool, bool]:
        for fr, fc in ((0, 0), (0, n - 5), (n - 5, 0)):
            if fr <= r < fr + 5 and fc <= c < fc + 5:
                dr, dc = r - fr, c - fc
                on = dr in (0, 4) or dc in (0, 4) or (1 <= dr <= 3 and 1 <= dc <= 3)
                return True, on
        return False, False

    bit_idx = 0
    for r in range(n):
        for c in range(n):
            in_f, f_on = is_finder(r, c)
            if in_f:
                on = f_on
            else:
                byte_v = digest[(bit_idx // 8) % len(digest)]
                on = bool((byte_v >> (bit_idx % 8)) & 1)
                bit_idx += 1
            if on:
                cells.append(f'<rect x="{c}" y="{r}" width="1" height="1" fill="#111"/>')
    return (
        f'<svg viewBox="-1 -1 {n + 2} {n + 2}" class="ch-qr-svg" aria-label="QRコード">'
        f'<rect x="-1" y="-1" width="{n + 2}" height="{n + 2}" fill="#fff"/>'
        f'{"".join(cells)}</svg>'
    )


def _render_price_svg_numeral(
    num_str: str,
    yen_str: str,
    numeral_style: str,
    prefix_label: str = "本体",
    is_uniform: bool = False,
) -> str:
    """Render `[本体]` (or `[各]`) tightly locked next to graphical POP numerals inside a single SVG viewBox.

    By placing the prefix badge at `x=2..40` and starting `<text x="45" text-anchor="start">` with `<tspan>`
    for the number and `<tspan dx="2">` for `円`, the gap between `本体` and the first digit is ALWAYS
    exactly 5 SVG units (~0.4mm), and `円` is ALWAYS 2 SVG units after the last digit—eliminating any
    detached `本体` label or width miscalculation across all digit counts.
    """
    est_num_w = sum(15 if c == "," else (28 if c == "1" else 33) for c in num_str)
    est_yen_w = len(yen_str) * 28
    vb_w = 45 + est_num_w + est_yen_w + 10
    vb_h = 64

    is_yellow_bg = numeral_style == "yellow_pop" or is_uniform
    badge_fill = "#d50000" if not is_yellow_bg else "#fffde7"
    badge_stroke = "#b71c1c" if not is_yellow_bg else "#ffeb3b"
    badge_text_fill = "#ffffff" if not is_yellow_bg else "#b71c1c"

    if len(prefix_label) == 2:
        # Authentic Japanese chirashi 2-row stacked `[本 / 体]` or compact horizontal `[本体]` badge right beside the first digit
        prefix_svg = (
            f'<g class="svg-hontai-group">'
            f'<rect x="2" y="13" width="37" height="39" rx="5" fill="{badge_fill}" stroke="{badge_stroke}" stroke-width="1.8"/>'
            f'<text x="20.5" y="29.5" text-anchor="middle" class="svg-hontai-txt" fill="{badge_text_fill}">{_esc(prefix_label[0])}</text>'
            f'<text x="20.5" y="46.5" text-anchor="middle" class="svg-hontai-txt" fill="{badge_text_fill}">{_esc(prefix_label[1])}</text>'
            f"</g>"
        )
        num_start_x = 44
    else:
        prefix_svg = (
            f'<g class="svg-hontai-group">'
            f'<rect x="2" y="18" width="32" height="32" rx="5" fill="{badge_fill}" stroke="{badge_stroke}" stroke-width="1.8"/>'
            f'<text x="18" y="40" text-anchor="middle" class="svg-hontai-txt" fill="{badge_text_fill}">{_esc(prefix_label)}</text>'
            f"</g>"
        )
        num_start_x = 39

    if numeral_style == "yellow_pop":
        return (
            f'<svg viewBox="0 0 {vb_w} {vb_h}" class="ch-price-svg ch-price-svg--yellow" preserveAspectRatio="xMaxYMid meet">'
            f"{prefix_svg}"
            f'<text x="{num_start_x + 2}" y="53" text-anchor="start" class="svg-num-shadow">'
            f'<tspan>{_esc(num_str)}</tspan><tspan dx="2" class="svg-yen-shadow">{_esc(yen_str)}</tspan>'
            f"</text>"
            f'<text x="{num_start_x}" y="50" text-anchor="start">'
            f'<tspan class="svg-num-yellow">{_esc(num_str)}</tspan><tspan dx="2" class="svg-yen-yellow">{_esc(yen_str)}</tspan>'
            f"</text>"
            f"</svg>"
        )
    if numeral_style == "gothic_bold":
        return (
            f'<svg viewBox="0 0 {vb_w} {vb_h}" class="ch-price-svg ch-price-svg--gothic" preserveAspectRatio="xMaxYMid meet">'
            f"{prefix_svg}"
            f'<text x="{num_start_x}" y="51" text-anchor="start">'
            f'<tspan class="svg-num-gothic">{_esc(num_str)}</tspan><tspan dx="2" class="svg-yen-gothic">{_esc(yen_str)}</tspan>'
            f"</text>"
            f"</svg>"
        )
    if numeral_style == "mincho_premium":
        return (
            f'<svg viewBox="0 0 {vb_w} {vb_h}" class="ch-price-svg ch-price-svg--mincho" preserveAspectRatio="xMaxYMid meet">'
            f"{prefix_svg}"
            f'<text x="{num_start_x}" y="51" text-anchor="start">'
            f'<tspan class="svg-num-mincho">{_esc(num_str)}</tspan><tspan dx="2" class="svg-yen-mincho">{_esc(yen_str)}</tspan>'
            f"</text>"
            f"</svg>"
        )
    # Default: `graphic_pop` — 3D layered red/white/black POP graphic numerals
    return (
        f'<svg viewBox="0 0 {vb_w} {vb_h}" class="ch-price-svg ch-price-svg--pop" preserveAspectRatio="xMaxYMid meet">'
        f"{prefix_svg}"
        f'<text x="{num_start_x + 2}" y="54" text-anchor="start">'
        f'<tspan class="svg-num-drop">{_esc(num_str)}</tspan><tspan dx="2" class="svg-yen-drop">{_esc(yen_str)}</tspan>'
        f"</text>"
        f'<text x="{num_start_x}" y="51" text-anchor="start">'
        f'<tspan class="svg-num-pop">{_esc(num_str)}</tspan><tspan dx="2" class="svg-yen-pop">{_esc(yen_str)}</tspan>'
        f"</text>"
        f"</svg>"
    )


def _format_price_block(slot: dict[str, Any], zone: dict[str, Any], default_num_style: str = "graphic_pop") -> str:
    prod = slot.get("product") or {}
    style = slot.get("price_style") or "dual"
    shape = slot.get("shape") or "vertical"
    num_style = slot.get("numeral_style") or ("yellow_pop" if shape == "burst" else default_num_style)
    price_ex = int(prod.get("price_tax_excluded") or 0)
    price_inc_exact = float(prod.get("price_tax_included_exact") or round(price_ex * 1.08, 2))
    orig_ex = int(prod.get("original_price_tax_excluded") or price_ex)
    disc_pct = int(round(float(prod.get("discount_rate") or 0.0) * 100))
    has_disc = orig_ex > price_ex > 0
    qa_p_scale = float(slot.get("qa_price_scale") or 1.0)
    p_scale_style = f' style="--p-scale:{qa_p_scale:.2f};"' if abs(qa_p_scale - 1.0) > 0.02 else ""

    if slot.get("discontinued"):
        return (
            '<div class="ch-price ch-price--discontinued">'
            '<span class="ch-disc-tag">販売終了</span>'
            f'<span class="ch-disc-note">旧本体{price_ex:,}円</span>'
            "</div>"
        )

    if style == "uniform" and zone.get("uniform_price_ex"):
        u_ex = int(zone["uniform_price_ex"])
        u_inc = round(u_ex * 1.08, 2)
        svg_num = _render_price_svg_numeral(f"{u_ex:,}", "円均", num_style, prefix_label="各", is_uniform=True)
        return (
            f'<div class="ch-price ch-price--uniform ch-price--num-{_esc(num_style)}"{p_scale_style}>'
            '<div class="ch-price__main-row">'
            f"{svg_num}"
            "</div>"
            f'<div class="ch-price__tax">税込 {u_inc:.2f}円</div>'
            "</div>"
        )

    pre_pills: list[str] = []
    if style == "was_now" and has_disc:
        pre_pills.append(f'<span class="ch-price__was">通常<s>{orig_ex:,}円</s>▶</span>')
    elif style == "percent_off" and has_disc and disc_pct > 0:
        pre_pills.append(f'<span class="ch-price__pct">{disc_pct}%OFF</span>')
    elif style == "bundle":
        bundle_ex = int(round(price_ex * 1.9))
        pre_pills.append(f'<span class="ch-price__bundle">よりどり2点 {bundle_ex:,}円</span>')

    if prod.get("has_flyer_offer"):
        lim = _esc(prod.get("offer_limit_text") or "特別価格")
        pre_pills.append(f'<span class="ch-offer-pill">{lim}</span>')

    pre_html = f'<div class="ch-price__pre-row">{"".join(pre_pills)}</div>' if pre_pills else ""
    svg_num = _render_price_svg_numeral(f"{price_ex:,}", "円", num_style, prefix_label="本体")

    return (
        f'<div class="ch-price ch-price--{_esc(style)} ch-price--num-{_esc(num_style)}"{p_scale_style}>'
        f"{pre_html}"
        '<div class="ch-price__main-row">'
        f"{svg_num}"
        "</div>"
        f'<div class="ch-price__tax">税込 {price_inc_exact:,.2f}円</div>'
        "</div>"
    )


def _slot_resolved_bg(slot: dict[str, Any]) -> tuple[str, bool]:
    """Return `(css_background_color, is_dark)` for a slot."""
    bg_choice = str(slot.get("bg_color") or "auto").strip()
    if bg_choice.startswith("#"):
        is_dark = bg_choice.lower() in ("#263238", "#1c1c1c", "#212121", "#1a237e", "#000000")
        return bg_choice, is_dark
    if bg_choice in BG_BY_ID:
        col = BG_BY_ID[bg_choice]
        return col, (bg_choice == "dark")
    prod = slot.get("product") or {}
    cat = prod.get("category") or ""
    role = slot.get("role") or "grid"
    return harmonize_category_bg(cat, role), False


def _slot_flex_weight(slot: dict[str, Any]) -> float:
    custom_w = float(slot.get("width_weight") or 0.0)
    if custom_w > 0 and abs(custom_w - 1.0) > 0.04:
        return max(0.68, min(1.42, custom_w))
    # Adapt slot width weight to the product cutout's natural aspect ratio (narrow products get narrower slots, wide products get wider slots)
    prod = slot.get("product") or {}
    p_file = _resolve_local_image_file(prod.get("image") or "")
    cut_ar = get_product_cutout_aspect_ratio(p_file)
    ar_weight = max(0.76, min(1.28, cut_ar ** 0.55))

    span = slot.get("size_span") or "auto"
    base = ar_weight
    if span == "hero_2x2":
        base = max(ar_weight, 1.22)
    elif span == "wide_2x1":
        base = max(ar_weight, 1.28)
    elif span == "tall_1x2":
        base = min(ar_weight, 0.92)
    elif slot.get("role") == "hero":
        base = max(ar_weight, 1.14)
    return max(0.72, min(1.38, base))


def _partition_slots_into_bento_rows(
    z_slots: list[dict[str, Any]],
    zone_w_mm: float = 172.0,
    zone_h_mm: float = 92.0,
) -> list[list[dict[str, Any]]]:
    """Partition a zone's slots into balanced full-width flex rows such that:
    1. There is NEVER an empty cell on any row.
    2. Every slot's width-to-height aspect ratio stays within [0.78, 1.46] — preventing BOTH
       tall skinny vertical strips (like 0.35:1 on left zones) AND overly flat wide strips (>1.5:1).
    """
    n = len(z_slots)
    if n == 0:
        return []
    if n == 1:
        return [z_slots]

    min_ar = 0.78
    max_ar = 1.46
    ideal_ar = 1.10

    def _build_rows_for_r(num_rows: int) -> list[list[dict[str, Any]]]:
        num_rows = max(1, min(num_rows, n))
        heroes = [s for s in z_slots if s.get("role") == "hero" or s.get("size_span") in ("hero_2x2", "wide_2x1")]
        if n == 6 and num_rows == 2 and len(heroes) == 2:
            ar_24 = (zone_w_mm / max(24.0, zone_h_mm)) * (0.5 + 0.25)
            if min_ar <= ar_24 <= max_ar:
                return [z_slots[:2], z_slots[2:]]
        base = n // num_rows
        extra = n % num_rows
        counts = [base + (1 if r >= (num_rows - extra) else 0) for r in range(num_rows)]
        out: list[list[dict[str, Any]]] = []
        idx = 0
        for c in counts:
            out.append(z_slots[idx : idx + c])
            idx += c
        return [r for r in out if r]

    best_rows: list[list[dict[str, Any]]] | None = None
    best_score = 1e9

    for r_cand in range(1, n + 1):
        cand_rows = _build_rows_for_r(r_cand)
        # Never put 1 single item alone on a wide row if n >= 2
        if len(cand_rows[0]) == 1 and n >= 2 and (zone_w_mm / max(20.0, zone_h_mm / len(cand_rows))) > max_ar:
            continue
        inv_sum = sum(1.0 / len(r) for r in cand_rows)
        est_ar = (zone_w_mm / max(24.0, zone_h_mm)) * inv_sum
        # Check the aspect ratio of the most crowded row (smallest width) and least crowded row (largest width)
        min_row_c = min(len(r) for r in cand_rows)
        max_row_c = max(len(r) for r in cand_rows)
        row_h_avg = max(14.0, zone_h_mm / len(cand_rows))
        widest_slot_ar = (zone_w_mm / min_row_c) / row_h_avg
        narrowest_slot_ar = (zone_w_mm / max_row_c) / row_h_avg

        penalty = abs(est_ar - ideal_ar)
        if widest_slot_ar > max_ar:
            penalty += (widest_slot_ar - max_ar) * 4.5
        if narrowest_slot_ar < min_ar:
            penalty += (min_ar - narrowest_slot_ar) * 4.0
        # Slight preference for 2 rows on 5..8 items when aspect ratio is healthy
        if 5 <= n <= 8 and r_cand == 2 and wid_ok(widest_slot_ar, narrowest_slot_ar):
            penalty -= 0.18

        if penalty < best_score:
            best_score = penalty
            best_rows = cand_rows

    return best_rows or _build_rows_for_r(max(1, round(math.sqrt(n))))


def wid_ok(widest_ar: float, narrowest_ar: float) -> bool:
    return widest_ar <= 1.52 and narrowest_ar >= 0.72


def _render_slot_card(
    slot: dict[str, Any],
    zone: dict[str, Any],
    default_num_style: str,
    embed_images: bool,
    interactive: bool,
    flyer_theme: str = "",
    flex_w_override: float | None = None,
) -> str:
    sid = slot["slot_id"]
    zid = zone["id"]
    prod = slot.get("product") or {}
    shape = slot.get("shape") or "rect"
    layout_mode = slot.get("layout_mode") or ("overlay_full" if shape in ("overflow_cutout", "cutout", "burst") else "overlay_price")
    overlay_pos = slot.get("overlay_pos") or "bottom_split"
    role = slot.get("role") or "grid"
    size = slot.get("size") or "M"
    size_span = slot.get("size_span") or "auto"
    raw_scale = int(slot.get("img_scale") or 0)
    if raw_scale <= 0 or raw_scale == 100:
        img_scale = 1.16 if role == "hero" else 1.12
    else:
        img_scale = max(70, min(raw_scale, 175)) / 100.0
    badge = slot.get("badge") or ""
    catch_copy = slot.get("catch_copy") or ""
    origin = prod.get("origin") or ""
    unit_label = prod.get("unit_label") or prod.get("size") or ""
    flyer_name = prod.get("flyer_name") or prod.get("title") or ""
    img_src = _img_src(prod.get("image") or "", embed_data_uri=embed_images)

    bg_hex, is_dark = _slot_resolved_bg(slot)
    resolved_bg_url = resolve_default_slot_bg_image(slot, flyer_theme=flyer_theme)
    slot_bg_img = _bg_image_css_url(resolved_bg_url, embed_data_uri=embed_images)
    bg_style_extra = f"background-image:{slot_bg_img}; background-size:cover; background-position:center;" if slot_bg_img else ""
    flex_w = flex_w_override if flex_w_override is not None else _slot_flex_weight(slot)

    disc_cls = " is-discontinued" if slot.get("discontinued") else ""
    curr_disc_cls = " is-now-discontinued" if slot.get("currently_discontinued_in_master") else ""
    lock_cls = " is-locked" if slot.get("locked") else ""
    offer_cls = " has-offer" if prod.get("has_flyer_offer") else ""
    dark_cls = " is-dark-bg" if is_dark else ""

    lock_badge = '<span class="ch-slot__lock" title="固定枠">🔒</span>' if (interactive and slot.get("locked")) else ""
    now_disc_badge = (
        '<span class="ch-slot__nowdisc">※現在マスタ販売終了</span>'
        if slot.get("currently_discontinued_in_master")
        else ""
    )
    disc_overlay = (
        '<div class="ch-slot__disc-banner">販売終了（クリックして代替商品を検索）</div>'
        if slot.get("discontinued")
        else ""
    )

    badge_el = f'<span class="ch-slot__badge">{_esc(badge)}</span>' if badge else ""
    origin_short = origin[:10] if origin else ""
    origin_el = f'<span class="ch-slot__origin">{_esc(origin_short)}</span>' if origin_short else ""

    price_html = _format_price_block(slot, zone, default_num_style=default_num_style)

    return (
        f'<article class="ch-slot ch-slot--role-{_esc(role)} ch-slot--size-{_esc(size)} '
        f'ch-slot--span-{_esc(size_span)} ch-slot--shape-{_esc(shape)} '
        f'ch-slot--layout-{_esc(layout_mode)} ch-slot--opos-{_esc(overlay_pos)}'
        f'{disc_cls}{curr_disc_cls}{lock_cls}{offer_cls}{dark_cls}" '
        f'style="flex:{flex_w:.2f} 1 0%; --slot-bg:{_esc(bg_hex)}; --img-scale:{img_scale:.2f}; {bg_style_extra}" '
        f'data-slot-id="{_esc(sid)}" data-zone-id="{_esc(zid)}" data-product-id="{_esc(slot.get("product_id"))}">'
        f"{lock_badge}{now_disc_badge}{disc_overlay}"
        f'<div class="ch-slot__top-bar">{badge_el}{origin_el}</div>'
        f'<div class="ch-slot__main-area">'
        f'<div class="ch-slot__img-wrap">'
        f'<img src="{img_src}" alt="{_esc(flyer_name)}" loading="eager"/>'
        f"</div>"
        f'<div class="ch-slot__info-price">'
        f'<div class="ch-slot__text-col">'
        f'<div class="ch-slot__copy">{_esc(catch_copy)}</div>'
        f'<h4 class="ch-slot__name">{_esc(flyer_name)}</h4>'
        f'<div class="ch-slot__unit">{_esc(unit_label)}</div>'
        f"</div>"
        f"{price_html}"
        f"</div>"
        f"</div>"
        f"</article>"
    )


def _compute_sheet_harmony_gradient(slots: list[dict[str, Any]], tone: str) -> str:
    if tone == "すっきり":
        return "linear-gradient(180deg, #f4f9f5 0%, #ffffff 50%, #f1f7fc 100%)"
    if tone == "上質":
        return "linear-gradient(180deg, #fdfaf2 0%, #f9f3e3 55%, #f5ece0 100%)"
    # Analyze dominant category in slots for product-harmonized sheet backdrop
    cat_counts: dict[str, int] = {}
    for s in slots:
        c = (s.get("product") or {}).get("category") or ""
        if c:
            cat_counts[c] = cat_counts.get(c, 0) + 1
    top_cat = max(cat_counts.items(), key=lambda kv: kv[1])[0] if cat_counts else ""
    if "野菜" in top_cat or "果物" in top_cat:
        return "radial-gradient(circle at 18% 12%, #f1f8e9 0%, #fffef7 55%, #e8f5e9 100%)"
    if "お魚" in top_cat:
        return "radial-gradient(circle at 18% 12%, #e3f2fd 0%, #fffef9 55%, #e8f4fd 100%)"
    if "お肉" in top_cat:
        return "radial-gradient(circle at 18% 12%, #ffebee 0%, #fffdf7 55%, #fff3e0 100%)"
    return "radial-gradient(circle at 15% 10%, #fff9c4 0%, #fffdf6 55%, #ffecb3 100%)"


def render_flyer_html(flyer_doc: dict[str, Any], interactive: bool = False, embed_images: bool = False) -> str:
    """Render a complete, zero-whitespace Japanese supermarket chirashi HTML document."""
    paper_id = flyer_doc.get("paper") or "B4-landscape"
    paper = PAPER_BY_ID.get(paper_id, PAPER_BY_ID["B4-landscape"])
    w_mm, h_mm = paper["width_mm"], paper["height_mm"]
    is_portrait = h_mm > w_mm
    tone = flyer_doc.get("tone") or "にぎやか"
    tpl_id = flyer_doc.get("template_id") or "T1"
    default_num_style = flyer_doc.get("numeral_style") or "graphic_pop"
    status = flyer_doc.get("status") or "下書き"
    period = flyer_doc.get("period") or {}
    store = flyer_doc.get("store") or {}
    comm = flyer_doc.get("community") or {}
    slots = flyer_doc.get("slots") or []
    zones = [z for z in (flyer_doc.get("zones") or []) if any(s.get("zone_id") == z.get("id") for s in slots)]
    if not zones and (flyer_doc.get("zones") or []):
        zones = flyer_doc.get("zones") or []
    menus = flyer_doc.get("menu_proposals") or []

    slots_by_zone: dict[str, list[dict[str, Any]]] = {}
    for s in slots:
        slots_by_zone.setdefault(s.get("zone_id") or "", []).append(s)

    total_slots = max(1, len(slots))
    # Continuous global font/element scale based on total item count so text never overlaps
    if total_slots <= 8:
        global_scale = 1.24
    elif total_slots <= 14:
        global_scale = 1.08
    elif total_slots <= 22:
        global_scale = 0.96
    elif total_slots <= 32:
        global_scale = 0.84
    elif total_slots <= 45:
        global_scale = 0.72
    else:
        global_scale = max(0.56, 0.72 * math.sqrt(45.0 / total_slots))

    sheet_bg = flyer_doc.get("sheet_bg") or _compute_sheet_harmony_gradient(slots, tone)
    sheet_bg_img = _bg_image_css_url(flyer_doc.get("bg_image_url") or "", embed_data_uri=embed_images)
    if sheet_bg_img:
        sheet_bg = f"{sheet_bg_img} center/cover no-repeat"
    tone_class = {"にぎやか": "ch-tone-loud", "すっきり": "ch-tone-clean", "上質": "ch-tone-premium"}.get(tone, "ch-tone-loud")

    watermark_html = ""
    if not interactive and status != "承認済み":
        watermark_html = '<div class="ch-watermark">確認用（未承認下書き）</div>'

    body_w_mm = max(180.0, w_mm - 8.0)
    body_h_mm = max(140.0, h_mm - (56.0 if (menus and total_slots <= 32) else 44.0))

    # Group zones into balanced columns so every zone's height is proportional to the vertical space its rows require!
    def _zone_weight(z: dict[str, Any]) -> float:
        zs = slots_by_zone.get(z["id"]) or []
        n_z = len(zs)
        if n_z <= 0:
            return 1.0
        if n_z <= 3:
            # 1 row of 2 or 3 items
            return max(1.0, 3.2 / max(2, n_z))
        if n_z == 4:
            # 1 row of 4 items across -> compact vertical height so each of the 4 cards is near-square (~1.0:1)
            return 1.15
        hero_c = sum(1 for s in zs if s.get("role") == "hero")
        return max(1.4, (n_z * 0.42 + hero_c * 0.18))

    def _render_single_zone(z: dict[str, Any], col_width_fraction: float, zone_height_fraction: float = 0.5) -> str:
        zid = z["id"]
        z_slots = slots_by_zone.get(zid) or []
        fcolor = z.get("frame_color") or "red"
        ztype = z.get("zone_type") or "day_block"
        zw = _zone_weight(z)

        zone_w_mm = max(75.0, body_w_mm * col_width_fraction - 2.5)
        zone_h_mm = max(32.0, body_h_mm * zone_height_fraction - 7.5)

        bento_rows = _partition_slots_into_bento_rows(z_slots, zone_w_mm=zone_w_mm, zone_h_mm=zone_h_mm)

        uniform_banner = ""
        if ztype == "uniform_price" and z.get("uniform_price_ex"):
            u_ex = int(z["uniform_price_ex"])
            u_inc = round(u_ex * 1.08, 2)
            uniform_banner = (
                f'<div class="ch-uniform-hero">'
                f'<span class="ch-uniform-hero__kaku">どれでも各</span>'
                f'<span class="ch-uniform-hero__num">{u_ex}</span>'
                f'<span class="ch-uniform-hero__yen">円均一</span>'
                f'<span class="ch-uniform-hero__tax">（税込 {u_inc:.2f}円）</span>'
                f"</div>"
            )

        # Allocate each row's vertical flex proportional to `1 / len(row_slots)` and normalize so sum(flex_grow) >= len(bento_rows) >= 1.0
        raw_row_flex: list[float] = []
        for row_slots in bento_rows:
            inv_c = (1.0 / max(1, len(row_slots))) ** 0.78
            max_rw = max((float(s.get("row_weight") or 1.0) for s in row_slots), default=1.0)
            raw_row_flex.append(inv_c * max_rw)
        total_rf = sum(raw_row_flex) or 1.0
        row_flex_list = [(rf / total_rf) * max(1, len(bento_rows)) for rf in raw_row_flex]

        row_htmls: list[str] = []
        for row_slots, rf in zip(bento_rows, row_flex_list):
            row_h_mm = max(18.0, zone_h_mm * (rf / max(1, len(bento_rows))))
            raw_weights = [_slot_flex_weight(s) for s in row_slots]
            sum_w = sum(raw_weights) or 1.0
            # Clamp any slot whose width would exceed 1.48 * row_h_mm so aspect ratio is strictly <= 1.5
            max_allowed_share = min(0.95, (1.48 * row_h_mm) / max(1.0, zone_w_mm))
            clamped_weights: list[float] = []
            for rw in raw_weights:
                share = rw / sum_w
                if len(row_slots) >= 2 and share > max_allowed_share and max_allowed_share >= (1.0 / len(row_slots)):
                    clamped_weights.append(max_allowed_share * sum_w)
                else:
                    clamped_weights.append(rw)

            cards_str = "".join(
                _render_slot_card(
                    s,
                    z,
                    default_num_style,
                    embed_images,
                    interactive,
                    flyer_theme=flyer_doc.get("theme") or "",
                    flex_w_override=cw,
                )
                for s, cw in zip(row_slots, clamped_weights)
            )
            row_htmls.append(f'<div class="ch-bento-row" style="flex:{rf:.3f} 1 0%;">{cards_str}</div>')

        zone_bg_img = _bg_image_css_url(z.get("bg_image_url") or "", embed_data_uri=embed_images)
        zone_bg_style = f"background-image:{zone_bg_img}; background-size:cover; background-position:center;" if zone_bg_img else ""

        return (
            f'<section class="ch-zone ch-zone--color-{_esc(fcolor)} ch-zone--type-{_esc(ztype)}" '
            f'style="flex:{zw:.2f} 1 0%; {zone_bg_style}" data-zone-id="{_esc(zid)}">'
            f'<header class="ch-zone__hdr" data-edit-zone="{_esc(zid)}">'
            f'<div class="ch-zone__tab">{_esc(z["title"])}</div>'
            f'<div class="ch-zone__sub">{_esc(z.get("subtitle") or "")}</div>'
            f"{uniform_banner}"
            f"</header>"
            f'<div class="ch-zone__slots">{"".join(row_htmls)}</div>'
            f"</section>"
        )

    # Decide column layout for zones so the entire body has zero empty space
    if len(zones) == 1:
        body_columns_html = f'<div class="ch-body-col" style="flex:1 1 0%;">{_render_single_zone(zones[0], 1.0, 1.0)}</div>'
    elif is_portrait and len(zones) <= 3:
        tot_zw = sum(_zone_weight(z) for z in zones) or 1.0
        all_z = "".join(_render_single_zone(z, 1.0, _zone_weight(z) / tot_zw) for z in zones)
        body_columns_html = f'<div class="ch-body-col" style="flex:1 1 0%;">{all_z}</div>'
    elif len(zones) == 2:
        w0, w1 = _zone_weight(zones[0]), _zone_weight(zones[1])
        c1 = _render_single_zone(zones[0], 0.5, 1.0)
        c2 = _render_single_zone(zones[1], 0.5, 1.0)
        body_columns_html = (
            f'<div class="ch-body-col" style="flex:{w0:.2f} 1 0%;">{c1}</div>'
            f'<div class="ch-body-col" style="flex:{w1:.2f} 1 0%;">{c2}</div>'
        )
    elif len(zones) == 3 and tpl_id == "T3" and total_slots <= 21:
        cols = []
        for z in zones:
            w = _zone_weight(z)
            cols.append(f'<div class="ch-body-col" style="flex:{w:.2f} 1 0%;">{_render_single_zone(z, 0.33, 1.0)}</div>')
        body_columns_html = "".join(cols)
    else:
        # Partition zones into Left Column and Right Column balanced by total zone weight!
        left_zones = [zones[0]]
        right_zones = zones[1:]
        if len(zones) >= 4:
            w01 = _zone_weight(zones[0]) + _zone_weight(zones[1])
            w23 = sum(_zone_weight(z) for z in zones[2:])
            w03 = _zone_weight(zones[0]) + _zone_weight(zones[-1])
            w12 = sum(_zone_weight(z) for z in zones[1:-1])
            if abs(w03 - w12) < abs(w01 - w23):
                left_zones = [zones[0], zones[-1]]
                right_zones = zones[1:-1]
            else:
                left_zones = zones[:2]
                right_zones = zones[2:]
        left_w = sum(_zone_weight(z) for z in left_zones) or 1.0
        right_w = sum(_zone_weight(z) for z in right_zones) or 1.0
        ratio_l = max(0.42, min(0.58, left_w / (left_w + right_w)))
        ratio_r = 1.0 - ratio_l
        left_html = "".join(_render_single_zone(z, ratio_l, _zone_weight(z) / left_w) for z in left_zones)
        right_html = "".join(_render_single_zone(z, ratio_r, _zone_weight(z) / right_w) for z in right_zones)
        body_columns_html = (
            f'<div class="ch-body-col" style="flex:{ratio_l:.3f} 1 0%;">{left_html}</div>'
            f'<div class="ch-body-col" style="flex:{ratio_r:.3f} 1 0%;">{right_html}</div>'
        )

    # Menu proposals strip (omitted automatically when total_slots > 32 to give maximum room to product cells)
    menu_strip_html = ""
    if menus and total_slots <= 32:
        m_cards: list[str] = []
        for m in menus[:2]:
            ings = m.get("ingredients") or []
            ing_tags = "".join(
                f'<span class="ch-menu__ing">{_esc(i.get("flyer_name"))}（本体{int(i.get("price_tax_excluded") or 0):,}円）</span>'
                for i in ings[:4]
            )
            m_cards.append(
                f'<div class="ch-menu-card">'
                f'<div class="ch-menu-card__top">'
                f'<span class="ch-menu-card__tag">献立提案</span>'
                f'<strong>{_esc(m.get("dish_name"))}</strong>'
                f'<span class="ch-menu-card__srv">{_esc(m.get("servings_label"))}</span>'
                f"</div>"
                f'<div class="ch-menu-card__ings">関連食材：{ing_tags}</div>'
                f"</div>"
            )
        menu_strip_html = f'<section class="ch-menus">{"".join(m_cards)}</section>'

    reg_events = comm.get("regular_events") or [
        "毎週火曜日は火曜市",
        "毎週木曜シニアデー5%OFF",
        "子育て応援パスポート5%OFF",
    ]
    ev_pills = "".join(f'<span class="ch-ev-pill">{_esc(e)}</span>' for e in reg_events if e)
    ann_txt = comm.get("announcement") or "週末朝市・旬の試食販売を開催！地域生産者直売コーナーも毎日入荷中"
    res_txt = comm.get("reservation") or "クリスマスケーキ・特選おせち ご予約承り中"
    qr_url = comm.get("qr_url") or os.environ.get("STORE_URL") or os.environ.get("ONLINE_STORE_URL") or "https://cymbal-retail.example.com"
    qr_label = comm.get("qr_label") or "ネットスーパー・公式LINEクーポン"
    disclaimer = (
        comm.get("disclaimer")
        or "※写真はすべてイメージです。※チラシ掲載品は豊富に取り揃えておりますが、万一品切れの際はご容赦ください。※価格は本体価格（税抜）と税込参考価格を併記しています。"
    )

    store_name = store.get("name") or "Cymbal 世田谷店"
    store_pref = store.get("prefecture") or "東京都"
    store_hours = store.get("hours") or "朝9:00〜夜22:00"
    store_tel = store.get("tel") or "03-5555-0199"
    store_parking = store.get("parking") or "駐車場完備"

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8"/>
<title>{_esc(flyer_doc.get("title") or "Cymbal Retail チラシ")}</title>
<style>
  @page {{
    size: {w_mm}mm {h_mm}mm;
    margin: 0;
  }}
  @media print {{
    *, *::before, *::after {{
      box-shadow: none !important;
      text-shadow: none !important;
    }}
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  html, body {{
    width: {w_mm}mm;
    height: {h_mm}mm;
    font-family: "Noto Sans CJK JP", "Noto Sans JP", "Hiragino Kaku Gothic ProN", "Meiryo", sans-serif;
    background: #fffdf5;
    color: #1c1c1c;
    overflow: hidden;
  }}
  .ch-sheet {{
    --g-scale: {global_scale:.3f};
    position: relative;
    width: {w_mm}mm;
    height: {h_mm}mm;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 2.8mm 3.2mm 2.5mm;
    background: {sheet_bg};
    border: 1.3mm solid #c62828;
  }}
  .ch-tone-clean.ch-sheet {{ border-color: #1b5e20; }}
  .ch-tone-premium.ch-sheet {{ border-color: #6a1b9a; }}

  .ch-watermark {{
    position: absolute;
    top: 48%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(-16deg);
    font-size: 20mm;
    font-weight: 900;
    color: rgba(198, 40, 40, 0.09);
    border: 1.4mm dashed rgba(198, 40, 40, 0.18);
    padding: 2.5mm 9mm;
    pointer-events: none;
    z-index: 50;
    white-space: nowrap;
  }}

  /* Header band with official Cymbal Retail logo */
  .ch-hdr {{
    display: grid;
    grid-template-columns: 64mm 1fr 76mm;
    gap: 2.2mm;
    align-items: stretch;
    background: linear-gradient(135deg, #d32f2f 0%, #b71c1c 60%, #e65100 100%);
    color: #fff;
    border-radius: 1.8mm;
    padding: 1.8mm 2.6mm;
    flex-shrink: 0;
  }}
  .ch-tone-clean .ch-hdr {{
    background: linear-gradient(135deg, #1b5e20 0%, #2e7d32 70%, #00695c 100%);
  }}
  .ch-tone-premium .ch-hdr {{
    background: linear-gradient(135deg, #28183b 0%, #5d1827 65%, #795548 100%);
  }}
  .ch-hdr__brand {{
    background: #ffffff;
    border-radius: 1.4mm;
    padding: 1.2mm 2mm;
    display: flex;
    flex-direction: column;
    justify-content: center;
    box-shadow: 0 0.3mm 0.8mm rgba(0,0,0,0.12);
  }}
  .ch-cymbal-logo {{
    width: 44mm;
    height: 9mm;
    display: block;
  }}
  .ch-hdr__store {{
    font-size: 2.55mm;
    font-weight: 900;
    color: #202124;
    margin-top: 0.3mm;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .ch-hdr__period {{
    margin-top: 0.4mm;
    background: #ffeb3b;
    color: #b71c1c;
    font-size: 2.45mm;
    font-weight: 900;
    padding: 0.25mm 1.2mm;
    border-radius: 0.8mm;
    display: inline-block;
    white-space: nowrap;
  }}
  .ch-hdr__center {{
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 0 1.2mm;
    min-width: 0;
  }}
  .ch-hdr__target-pill {{
    display: inline-block;
    align-self: flex-start;
    background: #ffeb3b;
    color: #b71c1c;
    font-size: 2.4mm;
    font-weight: 900;
    padding: 0.2mm 1.8mm;
    border-radius: 99mm;
    margin-bottom: 0.4mm;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  .ch-hdr__title {{
    font-size: 6.6mm;
    font-weight: 900;
    line-height: 1.06;
    color: #fffde7;
    text-shadow: 0.5mm 0.5mm 0 #000, -0.3mm -0.3mm 0 #b71c1c;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .ch-hdr__sub {{
    font-size: 2.65mm;
    font-weight: 700;
    color: #fff9c4;
    margin-top: 0.3mm;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .ch-hdr__right {{
    background: rgba(255,255,255,0.96);
    color: #1c1c1c;
    border-radius: 1.4mm;
    padding: 1.1mm 1.8mm;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    font-size: 2.25mm;
  }}
  .ch-hdr__res-title {{
    background: #d84315;
    color: #fff;
    font-weight: 900;
    padding: 0.2mm 1mm;
    border-radius: 0.6mm;
    font-size: 2.15mm;
    display: inline-block;
  }}
  .ch-hdr__res-body {{
    font-weight: 800;
    color: #222;
    line-height: 1.2;
    margin-top: 0.3mm;
  }}
  .ch-hdr__ev-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.5mm;
    margin-top: 0.4mm;
  }}
  .ch-ev-pill {{
    background: #fff3e0;
    border: 0.25mm solid #ef6c00;
    color: #bf360c;
    font-weight: 800;
    font-size: 1.95mm;
    padding: 0.15mm 0.9mm;
    border-radius: 0.6mm;
  }}

  /* Zero-whitespace Bento Body */
  .ch-body {{
    flex: 1;
    min-height: 0;
    margin: 1.6mm 0 1.2mm;
    display: flex;
    flex-direction: row;
    gap: 1.8mm;
  }}
  .ch-body-col {{
    display: flex;
    flex-direction: column;
    gap: 1.8mm;
    min-width: 0;
    min-height: 0;
  }}

  .ch-zone {{
    border: 0.75mm solid #c62828;
    border-radius: 1.8mm;
    background-color: rgba(255, 255, 255, 0.92);
    display: flex;
    flex-direction: column;
    min-height: 0;
    min-width: 0;
    overflow: hidden;
  }}
  .ch-zone--color-red {{ border-color: #d32f2f; }}
  .ch-zone--color-green {{ border-color: #2e7d32; }}
  .ch-zone--color-blue {{ border-color: #1565c0; }}
  .ch-zone--color-yellow {{ border-color: #f57f17; }}
  .ch-zone--color-orange {{ border-color: #ef6c00; }}
  .ch-zone--color-navy {{ border-color: #1a237e; }}
  .ch-zone--color-autumn {{ border-color: #b71c1c; }}
  .ch-zone--color-gold {{ border-color: #6d4c41; }}

  .ch-zone__hdr {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1.6mm;
    padding: 0.8mm 2mm;
    background: #d32f2f;
    color: #fff;
    flex-shrink: 0;
    cursor: pointer;
  }}
  .ch-zone--color-green .ch-zone__hdr {{ background: #2e7d32; }}
  .ch-zone--color-blue .ch-zone__hdr {{ background: #1565c0; }}
  .ch-zone--color-yellow .ch-zone__hdr {{ background: #f57f17; }}
  .ch-zone--color-orange .ch-zone__hdr {{ background: #ef6c00; }}
  .ch-zone--color-navy .ch-zone__hdr {{ background: #1a237e; }}
  .ch-zone--color-autumn .ch-zone__hdr {{ background: linear-gradient(90deg, #b71c1c, #d84315); }}
  .ch-zone--color-gold .ch-zone__hdr {{ background: #5d4037; }}

  .ch-zone__tab {{
    font-size: calc(3.1mm * var(--g-scale));
    font-weight: 900;
    background: #ffeb3b;
    color: #b71c1c;
    padding: 0.2mm 1.8mm;
    border-radius: 0.9mm;
    white-space: nowrap;
  }}
  .ch-zone__sub {{
    font-size: calc(2.15mm * var(--g-scale));
    font-weight: 700;
    color: #fff;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
  }}
  .ch-uniform-hero {{
    background: #ffeb3b;
    color: #c62828;
    padding: 0.15mm 1.5mm;
    border-radius: 0.8mm;
    font-weight: 900;
    font-size: calc(2.4mm * var(--g-scale));
    white-space: nowrap;
  }}
  .ch-uniform-hero__num {{ font-size: calc(3.4mm * var(--g-scale)); font-weight: 900; }}

  .ch-zone__slots {{
    flex: 1;
    min-height: 0;
    padding: 1.1mm;
    display: flex;
    flex-direction: column;
    gap: 1.1mm;
  }}
  .ch-bento-row {{
    display: flex;
    flex-direction: row;
    gap: 1.1mm;
    min-height: 0;
    min-width: 0;
    width: 100%;
  }}

  /* Slot card — zero overlapping tags, harmonious background */
  .ch-slot {{
    position: relative;
    background-color: var(--slot-bg, #ffffff);
    border: 0.3mm solid rgba(0, 0, 0, 0.14);
    border-radius: 1.3mm;
    padding: 0.8mm 1.1mm;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    cursor: pointer;
    transition: box-shadow 0.12s;
  }}
  .ch-slot.is-dark-bg {{
    color: #fff;
    border-color: #ffca28;
  }}
  .ch-slot.is-dark-bg .ch-slot__name {{ color: #fff !important; }}
  .ch-slot.is-dark-bg .ch-slot__unit {{ color: #cfd8dc !important; }}
  .ch-slot.is-dark-bg .ch-slot__copy {{ color: #ffeb3b !important; }}
  .ch-slot.is-dark-bg .ch-price__tax {{ color: #eceff1 !important; }}
  .ch-slot.is-dark-bg .ch-price__hontai {{ color: #ffeb3b !important; border-color: #ffeb3b !important; }}

  .ch-slot--role-hero {{
    border: 0.55mm solid #ef6c00;
    box-shadow: inset 0 0 0 0.3mm rgba(255, 235, 59, 0.6);
  }}

  /* Top non-overlapping tag bar — floats over top corners so product image fills full slot height */
  .ch-slot__top-bar {{
    position: absolute;
    top: 0.65mm;
    left: 0.85mm;
    right: 0.85mm;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.8mm;
    z-index: 6;
    pointer-events: none;
  }}
  .ch-slot__badge {{
    background: #d32f2f;
    color: #ffeb3b;
    font-size: calc(2.05mm * var(--g-scale));
    font-weight: 900;
    padding: 0.15mm 1.1mm;
    border-radius: 0.6mm;
    white-space: nowrap;
    line-height: 1.15;
    box-shadow: 0 0.2mm 0.4mm rgba(0,0,0,0.18);
  }}
  .ch-slot--role-hero .ch-slot__badge {{
    background: linear-gradient(135deg, #d50000 0%, #ff6d00 100%);
    font-size: calc(2.35mm * var(--g-scale));
    transform: rotate(-2deg);
  }}
  .ch-slot__origin {{
    background: #1b5e20;
    color: #ffffff;
    font-size: calc(1.85mm * var(--g-scale));
    font-weight: 800;
    padding: 0.15mm 0.9mm;
    border-radius: 0.6mm;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 58%;
    line-height: 1.15;
  }}

  /* Main content layout inside slot — guarantees large product image + zero text/price overlap */
  .ch-slot__main-area {{
    flex: 1;
    min-height: 0;
    min-width: 0;
    display: flex;
    flex-direction: row;
    gap: 1.2mm;
    align-items: center;
  }}

  .ch-slot__img-wrap {{
    width: 50%;
    height: 100%;
    min-height: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    overflow: hidden;
  }}
  .ch-slot--role-hero .ch-slot__img-wrap {{
    width: 52%;
  }}

  /* Vertical, Rounded & Circle cards: Photo fills top (flex:1), full-width name + price stacked at bottom */
  .ch-slot--shape-vertical .ch-slot__main-area,
  .ch-slot--shape-rounded .ch-slot__main-area,
  .ch-slot--shape-circle .ch-slot__main-area {{
    flex-direction: column;
    align-items: stretch;
    justify-content: space-between;
    gap: 0.4mm;
  }}
  .ch-slot--shape-vertical .ch-slot__img-wrap,
  .ch-slot--shape-rounded .ch-slot__img-wrap,
  .ch-slot--shape-circle .ch-slot__img-wrap {{
    width: 100%;
    height: auto;
    flex: 1 1 0%;
    min-height: 0;
    padding: 0.2mm;
  }}
  .ch-slot--shape-vertical .ch-slot__info-price,
  .ch-slot--shape-rounded .ch-slot__info-price,
  .ch-slot--shape-circle .ch-slot__info-price {{
    flex: 0 0 auto;
    width: 100%;
    justify-content: flex-end;
    gap: 0.15mm;
  }}
  .ch-slot--shape-vertical .ch-slot__name,
  .ch-slot--shape-rounded .ch-slot__name,
  .ch-slot--shape-circle .ch-slot__name {{
    -webkit-line-clamp: 1;
  }}

  /* Shape variations including overflow_cutout, rect, tilted */
  .ch-slot--shape-rect {{
    border: 0.35mm solid rgba(0,0,0,0.22);
    border-radius: 0.6mm;
  }}
  .ch-slot--shape-overflow_cutout {{
    overflow: visible !important;
    border: 0.45mm solid rgba(211, 47, 47, 0.45);
    z-index: 3;
  }}
  .ch-slot--shape-overflow_cutout .ch-slot__img-wrap {{
    overflow: visible !important;
  }}
  .ch-slot--shape-overflow_cutout .ch-slot__img-wrap img {{
    mix-blend-mode: normal;
    transform: scale(var(--img-scale, 1.18)) translateY(-2%);
    border-radius: 1.2mm;
  }}
  .ch-slot--shape-overflow_cutout .ch-slot__badge {{
    transform: translate(-0.8mm, -0.6mm) rotate(-3deg) scale(1.05);
    box-shadow: 0 0.4mm 0.9mm rgba(0,0,0,0.3);
  }}
  .ch-slot--shape-tilted {{
    transform: rotate(-1.1deg);
    border: 0.55mm solid #d84315;
    box-shadow: 0 0.5mm 1.2mm rgba(0,0,0,0.15);
  }}
  .ch-slot--shape-cutout {{
    border: 0.35mm dashed rgba(211, 47, 47, 0.38);
  }}
  .ch-slot--shape-cutout .ch-slot__img-wrap img {{
    mix-blend-mode: normal;
  }}
  .ch-slot.is-dark-bg.ch-slot--shape-cutout .ch-slot__img-wrap img,
  .ch-slot.is-dark-bg.ch-slot--shape-overflow_cutout .ch-slot__img-wrap img {{
    mix-blend-mode: normal;
    border-radius: 1.2mm;
  }}

  /* Overlay Layout Modes: Product photo fills almost the entire frame (98% x 95%), compact text & price at bottom */
  .ch-slot--layout-overlay_full .ch-slot__main-area,
  .ch-slot--layout-overflow_frame .ch-slot__main-area {{
    position: relative;
    display: block;
    width: 100%;
    height: 100%;
  }}
  .ch-slot--layout-overlay_full .ch-slot__img-wrap,
  .ch-slot--layout-overflow_frame .ch-slot__img-wrap {{
    position: absolute;
    inset: -3% -2% 2% -2%;
    width: 104%;
    height: 101%;
    z-index: 1;
    overflow: visible !important;
  }}
  .ch-slot--layout-overlay_full .ch-slot__info-price,
  .ch-slot--layout-overflow_frame .ch-slot__info-price {{
    position: relative;
    z-index: 4;
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: row;
    flex-wrap: nowrap;
    justify-content: space-between;
    align-items: flex-end;
    gap: 0.6mm;
    pointer-events: none;
  }}
  .ch-slot--layout-overlay_full .ch-slot__text-col,
  .ch-slot--layout-overflow_frame .ch-slot__text-col {{
    background: rgba(255, 255, 255, 0.94);
    border-left: 0.8mm solid #d32f2f;
    padding: 0.3mm 0.85mm;
    border-radius: 0.8mm;
    box-shadow: 0 0.25mm 0.7mm rgba(0,0,0,0.16);
    flex: 1 1 0%;
    max-width: 60%;
    align-self: flex-end;
    margin-bottom: 0;
  }}
  .ch-slot--layout-overlay_full .ch-price,
  .ch-slot--layout-overflow_frame .ch-price {{
    flex-shrink: 0;
    width: auto;
    max-width: 52%;
    background: rgba(255, 253, 231, 0.96);
    border: 0.4mm solid #fbc02d;
    border-radius: 1.1mm;
    padding: 0.2mm 0.85mm;
    box-shadow: 0 0.3mm 0.8mm rgba(0,0,0,0.22);
  }}
  .ch-slot--layout-overlay_full .ch-price__tax,
  .ch-slot--layout-overflow_frame .ch-price__tax {{
    color: #263238 !important;
    font-weight: 800;
  }}
  .ch-slot--opos-top_text_bottom_price.ch-slot--layout-overlay_full .ch-slot__info-price,
  .ch-slot--opos-top_text_bottom_price.ch-slot--layout-overflow_frame .ch-slot__info-price {{
    flex-direction: column;
    justify-content: flex-end;
    align-items: flex-end;
  }}
  .ch-slot--opos-top_text_bottom_price.ch-slot--layout-overlay_full .ch-slot__text-col {{
    align-self: flex-start;
    margin-bottom: auto;
    margin-top: 4.2mm;
    max-width: 78%;
  }}
  .ch-slot--opos-right_stack.ch-slot--layout-overlay_full .ch-slot__info-price {{
    flex-direction: column;
    justify-content: flex-end;
    align-items: flex-end;
  }}
  .ch-slot--opos-right_stack.ch-slot--layout-overlay_full .ch-slot__text-col {{
    align-self: flex-end;
    margin-bottom: 0.4mm;
    max-width: 78%;
  }}

  /* Overlay Price mode: Full-frame product photo (98% x 95%) with compact single-row bottom text+price bar */
  .ch-slot--layout-overlay_price .ch-slot__main-area {{
    position: relative;
    display: block;
    width: 100%;
    height: 100%;
  }}
  .ch-slot--layout-overlay_price .ch-slot__img-wrap {{
    position: absolute;
    inset: -3% -2% 2% -2%;
    width: 104%;
    height: 101%;
    z-index: 1;
    overflow: visible !important;
  }}
  .ch-slot--layout-overlay_price .ch-slot__info-price {{
    position: relative;
    z-index: 4;
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: row;
    flex-wrap: nowrap;
    align-items: flex-end;
    justify-content: space-between;
    gap: 0.45mm;
    pointer-events: none;
  }}
  .ch-slot--layout-overlay_price .ch-slot__text-col {{
    flex: 1 1 0%;
    min-width: 0;
    max-width: 62%;
    padding: 0.2mm 0.65mm;
  }}
  .ch-slot--layout-overlay_price .ch-price {{
    flex-shrink: 0;
    background: rgba(255, 253, 231, 0.95);
    border: 0.3mm solid #fdd835;
    border-radius: 0.9mm;
    padding: 0.15mm 0.65mm;
    width: auto;
    max-width: 52%;
    box-shadow: 0 0.2mm 0.6mm rgba(0,0,0,0.14);
  }}
  .ch-slot--layout-overlay_price .ch-price__tax {{
    color: #263238 !important;
  }}

  /* Split Vertical mode: large upper photo (overflowing slightly) + compact single-row bottom text+price bar */
  .ch-slot--layout-split_vertical .ch-slot__main-area {{
    flex-direction: column;
    align-items: stretch;
    justify-content: space-between;
    gap: 0.2mm;
  }}
  .ch-slot--layout-split_vertical .ch-slot__img-wrap {{
    width: 100%;
    height: auto;
    flex: 1 1 0%;
    min-height: 0;
    overflow: visible !important;
  }}
  .ch-slot--layout-split_vertical .ch-slot__info-price {{
    flex: 0 0 auto;
    width: 100%;
    display: flex;
    flex-direction: row;
    flex-wrap: nowrap;
    align-items: flex-end;
    justify-content: space-between;
    gap: 0.45mm;
    z-index: 4;
  }}
  .ch-slot--layout-split_vertical .ch-slot__text-col {{
    flex: 1 1 0%;
    min-width: 0;
    max-width: 62%;
    padding: 0.2mm 0.65mm;
  }}
  .ch-slot--layout-split_vertical .ch-price {{
    flex-shrink: 0;
    background: rgba(255, 253, 231, 0.95);
    border: 0.3mm solid #fdd835;
    border-radius: 0.9mm;
    padding: 0.15mm 0.65mm;
    width: auto;
    max-width: 52%;
    box-shadow: 0 0.2mm 0.6mm rgba(0,0,0,0.14);
  }}

  .ch-slot--shape-burst {{
    background: radial-gradient(circle at 28% 35%, #fffde7 0%, #ffe082 68%, #ffca28 100%) !important;
    border: 0.65mm solid #d50000;
  }}
  .ch-slot--shape-burst .ch-price {{
    background: linear-gradient(135deg, #d50000 0%, #b71c1c 100%);
    color: #ffeb3b;
    padding: 0.35mm 1.1mm;
    border-radius: 1.1mm;
    box-shadow: 0 0.3mm 0.7mm rgba(0,0,0,0.25);
  }}
  .ch-slot--shape-burst .ch-price__hontai,
  .ch-slot--shape-burst .ch-price__kaku {{
    color: #fff !important;
    border-color: #ffeb3b !important;
  }}
  .ch-slot--shape-burst .ch-price__tax {{
    color: #fffde7 !important;
  }}

  .ch-slot--shape-circle {{
    border-radius: 3.2mm;
    border: 0.5mm solid #ef6c00;
  }}
  .ch-slot--shape-circle .ch-slot__img-wrap img {{
    border-radius: 50%;
    border: 0.45mm solid #ffca28;
    background: #fff;
    padding: 0.3mm;
  }}

  .ch-slot--shape-rounded {{
    border-radius: 2.5mm;
    border: 0.4mm solid #90caf9;
    box-shadow: 0 0.3mm 0.8mm rgba(0,0,0,0.06);
  }}

  .ch-slot__img-wrap img {{
    width: 100%;
    height: 100%;
    object-fit: contain;
    object-position: center 36%;
    background: transparent !important;
    transform: scale(var(--img-scale, 1.12));
    transform-origin: center 40%;
    image-rendering: high-quality;
  }}

  /* Right/Bottom column of slot: text on top, price on bottom-right -> never collides! */
  .ch-slot__info-price {{
    flex: 1;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 0.8mm;
    align-items: stretch;
  }}
  .ch-slot__text-col {{
    min-width: 0;
    overflow: hidden;
    background: rgba(255, 255, 255, 0.90);
    border-radius: 0.75mm;
    padding: 0.25mm 0.75mm;
    box-shadow: 0 0.15mm 0.45mm rgba(0, 0, 0, 0.09);
  }}
  .ch-slot.is-dark-bg .ch-slot__text-col {{
    background: rgba(24, 32, 38, 0.86);
  }}
  .ch-slot__copy {{
    font-size: calc(1.9mm * var(--g-scale));
    font-weight: 800;
    color: #c62828;
    line-height: 1.12;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  .ch-slot__name {{
    font-size: calc(2.5mm * var(--g-scale));
    font-weight: 900;
    color: #111;
    line-height: 1.15;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }}
  .ch-slot--role-hero .ch-slot__name {{
    font-size: calc(3.3mm * var(--g-scale));
  }}
  .ch-slot--role-hero .ch-slot__copy {{
    font-size: calc(2.3mm * var(--g-scale));
  }}
  .ch-slot__unit {{
    font-size: calc(1.85mm * var(--g-scale));
    color: #455a64;
    font-weight: 700;
    margin-top: 0.1mm;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}

  /* SVG Graphical Price Lockup (never clips, sits cleanly below text-col) */
  .ch-price {{
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    justify-content: flex-end;
    margin-top: 0.1mm;
    width: 100%;
  }}
  .ch-price__pre-row {{
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 0.4mm;
    margin-bottom: 0.15mm;
  }}
  .ch-price__was, .ch-price__pct, .ch-price__bundle {{
    font-size: calc(1.85mm * var(--g-scale));
    font-weight: 900;
    color: #b71c1c;
    background: #fff8e1;
    border: 0.2mm solid #ef6c00;
    padding: 0.05mm 0.7mm;
    border-radius: 0.5mm;
    white-space: nowrap;
  }}
  .ch-offer-pill {{
    background: #ff6f00;
    color: #fff;
    font-size: calc(1.8mm * var(--g-scale));
    font-weight: 900;
    padding: 0.05mm 0.8mm;
    border-radius: 0.5mm;
    white-space: nowrap;
  }}
  .ch-price__main-row {{
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 0.4mm;
    width: 100%;
  }}
  .ch-price__hontai, .ch-price__kaku {{
    font-size: calc(1.85mm * var(--g-scale));
    font-weight: 900;
    color: #222;
    border: 0.25mm solid #333;
    padding: 0.1mm 0.4mm;
    border-radius: 0.4mm;
    line-height: 1;
    flex-shrink: 0;
  }}
  .ch-price-svg {{
    height: calc(6.6mm * var(--g-scale) * var(--p-scale, 1));
    max-width: 100%;
    width: auto;
    display: block;
    overflow: visible;
  }}
  .ch-slot--role-hero .ch-price-svg {{
    height: calc(8.4mm * var(--g-scale) * var(--p-scale, 1));
  }}
  .svg-hontai-txt {{
    font-family: "Noto Sans CJK JP", sans-serif;
    font-size: 15.5px;
    font-weight: 900;
  }}
  /* SVG Numeral Styles */
  .svg-num-drop {{
    font-family: "Noto Sans CJK JP", "Arial Black", Impact, sans-serif;
    font-size: 54px;
    font-weight: 900;
    font-style: italic;
    fill: #111111;
    stroke: #111111;
    stroke-width: 8px;
    stroke-linejoin: round;
    paint-order: stroke fill;
  }}
  .svg-yen-drop, .svg-yen-shadow {{
    font-family: "Noto Sans CJK JP", sans-serif;
    font-size: 27px;
    font-weight: 900;
    fill: #111111;
    stroke: #111111;
    stroke-width: 5px;
    stroke-linejoin: round;
    paint-order: stroke fill;
  }}
  .svg-num-pop {{
    font-family: "Noto Sans CJK JP", "Arial Black", Impact, sans-serif;
    font-size: 54px;
    font-weight: 900;
    font-style: italic;
    fill: #e50000;
    stroke: #ffffff;
    stroke-width: 6.5px;
    stroke-linejoin: round;
    paint-order: stroke fill;
  }}
  .svg-yen-pop {{
    font-family: "Noto Sans CJK JP", sans-serif;
    font-size: 27px;
    font-weight: 900;
    fill: #d50000;
    stroke: #ffffff;
    stroke-width: 4px;
    stroke-linejoin: round;
    paint-order: stroke fill;
  }}
  .svg-num-shadow {{
    font-family: "Noto Sans CJK JP", "Arial Black", Impact, sans-serif;
    font-size: 54px;
    font-weight: 900;
    font-style: italic;
    fill: #000000;
    stroke: #000000;
    stroke-width: 8px;
    stroke-linejoin: round;
    paint-order: stroke fill;
  }}
  .svg-num-yellow {{
    font-family: "Noto Sans CJK JP", "Arial Black", Impact, sans-serif;
    font-size: 54px;
    font-weight: 900;
    font-style: italic;
    fill: #ffeb3b;
    stroke: #b71c1c;
    stroke-width: 5px;
    stroke-linejoin: round;
    paint-order: stroke fill;
  }}
  .svg-yen-yellow {{
    font-family: "Noto Sans CJK JP", sans-serif;
    font-size: 26px;
    font-weight: 900;
    fill: #ffeb3b;
    stroke: #000;
    stroke-width: 3.5px;
    paint-order: stroke fill;
  }}
  .svg-num-gothic {{
    font-family: "Noto Sans CJK JP", sans-serif;
    font-size: 50px;
    font-weight: 900;
    fill: #c62828;
  }}
  .svg-yen-gothic {{
    font-family: "Noto Sans CJK JP", sans-serif;
    font-size: 25px;
    font-weight: 800;
    fill: #c62828;
  }}
  .svg-num-mincho {{
    font-family: "Noto Serif CJK JP", "Hiragino Mincho ProN", serif;
    font-size: 50px;
    font-weight: 900;
    fill: #880e4f;
  }}
  .svg-yen-mincho {{
    font-family: "Noto Serif CJK JP", serif;
    font-size: 24px;
    font-weight: 800;
    fill: #880e4f;
  }}

  .ch-price__tax {{
    font-size: calc(1.9mm * var(--g-scale));
    font-weight: 800;
    color: #222;
    white-space: nowrap;
    line-height: 1.05;
  }}

  /* Discontinued & lock states */
  .ch-slot__lock {{
    position: absolute;
    top: 0.5mm;
    right: 0.6mm;
    font-size: 2.5mm;
    z-index: 4;
  }}
  .ch-slot__nowdisc {{
    position: absolute;
    top: 0.5mm;
    right: 0.6mm;
    background: #616161;
    color: #fff;
    font-size: 1.85mm;
    font-weight: 800;
    padding: 0.15mm 0.8mm;
    border-radius: 0.6mm;
    z-index: 4;
  }}
  .ch-slot.is-discontinued {{
    background: #f5f5f5 !important;
    border: 0.6mm dashed #d32f2f !important;
  }}
  .ch-slot.is-discontinued .ch-slot__img-wrap img {{
    filter: grayscale(100%) opacity(0.45);
  }}
  .ch-slot.is-discontinued .ch-slot__name {{
    color: #757575;
    text-decoration: line-through;
  }}
  .ch-slot__disc-banner {{
    position: absolute;
    inset: auto 0 0 0;
    background: rgba(198, 40, 40, 0.94);
    color: #fff;
    font-size: 2.0mm;
    font-weight: 900;
    text-align: center;
    padding: 0.4mm;
    z-index: 5;
  }}
  .ch-disc-tag {{
    background: #c62828;
    color: #fff;
    font-weight: 900;
    font-size: 2.1mm;
    padding: 0.15mm 1mm;
    border-radius: 0.5mm;
  }}
  .ch-disc-note {{
    font-size: 1.8mm;
    color: #666;
  }}

  /* Menu strip */
  .ch-menus {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(90mm, 1fr));
    gap: 1.5mm;
    margin-bottom: 1.1mm;
    flex-shrink: 0;
  }}
  .ch-menu-card {{
    background: linear-gradient(90deg, #fff8e1 0%, #ffffff 100%);
    border: 0.4mm solid #fbc02d;
    border-radius: 1.2mm;
    padding: 0.8mm 1.8mm;
    font-size: 2.05mm;
  }}
  .ch-menu-card__top {{
    display: flex;
    align-items: center;
    gap: 1mm;
    color: #b71c1c;
  }}
  .ch-menu-card__tag {{
    background: #d32f2f;
    color: #fff;
    font-weight: 900;
    padding: 0.1mm 0.9mm;
    border-radius: 0.5mm;
    font-size: 1.85mm;
  }}
  .ch-menu-card__srv {{ color: #444; font-weight: 700; font-size: 1.85mm; }}
  .ch-menu-card__ings {{
    margin-top: 0.2mm;
    font-weight: 700;
    color: #1b5e20;
    display: flex;
    flex-wrap: wrap;
    gap: 0.7mm;
  }}

  /* Footer community & store block */
  .ch-ftr {{
    display: grid;
    grid-template-columns: 1.25fr 1.05fr 60mm;
    gap: 1.8mm;
    align-items: center;
    background: #263238;
    color: #fff;
    border-radius: 1.5mm;
    padding: 1.2mm 2.2mm;
    font-size: 2.1mm;
    flex-shrink: 0;
  }}
  .ch-ftr__store-name {{
    font-size: 2.95mm;
    font-weight: 900;
    color: #ffeb3b;
  }}
  .ch-ftr__disc {{
    font-size: 1.7mm;
    color: #b0bec5;
    margin-top: 0.2mm;
  }}
  .ch-ftr__ann {{
    background: rgba(255,255,255,0.1);
    border-left: 0.8mm solid #ffca28;
    padding: 0.7mm 1.4mm;
    border-radius: 0.7mm;
  }}
  .ch-ftr__ann-lbl {{
    color: #ffca28;
    font-weight: 900;
    font-size: 2.0mm;
  }}
  .ch-ftr__qr-box {{
    display: flex;
    align-items: center;
    gap: 1.3mm;
    background: #fff;
    color: #111;
    padding: 0.6mm 1.2mm;
    border-radius: 1.1mm;
  }}
  .ch-qr-svg {{
    width: 10mm;
    height: 10mm;
    flex-shrink: 0;
  }}
  .ch-ftr__qr-txt {{
    font-size: 1.85mm;
    font-weight: 800;
    line-height: 1.18;
  }}
</style>
</head>
<body>
<div class="ch-sheet {tone_class} ch-tpl-{_esc(tpl_id)}" id="chirashi-sheet">
  {watermark_html}
  <header class="ch-hdr">
    <div class="ch-hdr__brand">
      {CYMBAL_LOGO_SVG}
      <div class="ch-hdr__store">{_esc(store_name)}（{_esc(store_pref)}）</div>
      <div class="ch-hdr__period">売出期間：{_esc(period.get("from") or "")} ▶ {_esc(period.get("to") or "")}</div>
    </div>
    <div class="ch-hdr__center">
      <span class="ch-hdr__target-pill">対象：{_esc(flyer_doc.get("target") or "地域の皆様")} ・ テーマ：{_esc(flyer_doc.get("theme") or "今週の特売")}</span>
      <h1 class="ch-hdr__title">{_esc(flyer_doc.get("title") or "今週の大感謝祭")}</h1>
      <div class="ch-hdr__sub">{_esc(flyer_doc.get("subtitle") or "")}</div>
    </div>
    <div class="ch-hdr__right">
      <div>
        <span class="ch-hdr__res-title">ご予約・季節企画</span>
        <div class="ch-hdr__res-body">{_esc(res_txt)}</div>
      </div>
      <div class="ch-hdr__ev-row">{ev_pills}</div>
    </div>
  </header>

  <main class="ch-body">
    {body_columns_html}
  </main>

  {menu_strip_html}

  <footer class="ch-ftr">
    <div>
      <div class="ch-ftr__store-name">{_esc(store_name)} 営業時間：{_esc(store_hours)} ／ TEL：{_esc(store_tel)}（{_esc(store_parking)}）</div>
      <div class="ch-ftr__disc">{_esc(disclaimer)}</div>
    </div>
    <div class="ch-ftr__ann">
      <div class="ch-ftr__ann-lbl">地域のお知らせ・イベント情報</div>
      <div>{_esc(ann_txt)}</div>
    </div>
    <div class="ch-ftr__qr-box">
      {_svg_qr_matrix(qr_url)}
      <div class="ch-ftr__qr-txt">{_esc(qr_label)}<br/><span style="font-size:1.65mm;color:#1565c0">スマホでチラシ＆クーポン</span></div>
    </div>
  </footer>
</div>
<script>
  // 5-Pass Post-Render DOM Quality Assurance & Collision / Image-Fill Auto-Correction Engine
  function runChirashiDomQaPass() {{
    // Pass 1: Tight-fit every SVG price lockup viewBox to the exact rendered bounding box of [本体] + digits + 円
    document.querySelectorAll('.ch-price-svg').forEach((svg) => {{
      try {{
        const bbox = svg.getBBox();
        if (bbox && bbox.width > 10 && bbox.height > 10) {{
          const vx = Math.floor(bbox.x - 3);
          const vw = Math.ceil(bbox.width + 7);
          svg.setAttribute('viewBox', vx + ' 0 ' + vw + ' 64');
        }}
      }} catch (e) {{}}
    }});

    const slots = document.querySelectorAll('.ch-slot');
    slots.forEach((slot) => {{
      const sRect = slot.getBoundingClientRect();
      if (!sRect || sRect.width <= 0 || sRect.height <= 0) return;

      // Pass 2: Scale down typography on very short slots in high-density flyers (e.g. 40..80 items)
      if (sRect.height < 95) {{
        const factor = Math.max(0.54, sRect.height / 98);
        slot.style.fontSize = (factor * 100) + '%';
        const svg = slot.querySelector('.ch-price-svg');
        if (svg) svg.style.height = Math.max(13, Math.round(23 * factor)) + 'px';
        const copyEl = slot.querySelector('.ch-slot__copy');
        if (copyEl && sRect.height < 78) copyEl.style.display = 'none';
        const nameEl = slot.querySelector('.ch-slot__name');
        if (nameEl && sRect.height < 68) nameEl.style.webkitLineClamp = '1';
      }}

      // Pass 3: Top-bar badge vs origin collision check & auto-fix
      const badgeEl = slot.querySelector('.ch-slot__badge');
      const originEl = slot.querySelector('.ch-slot__origin');
      if (badgeEl && originEl) {{
        let bRect = badgeEl.getBoundingClientRect();
        let oRect = originEl.getBoundingClientRect();
        if (bRect.right > oRect.left - 3) {{
          badgeEl.style.fontSize = '80%';
          originEl.style.fontSize = '78%';
          originEl.style.maxWidth = '46%';
        }}
      }}

      // Pass 4: Bottom bar text-col vs price box collision & overflow auto-resolver
      const textCol = slot.querySelector('.ch-slot__text-col');
      const priceBox = slot.querySelector('.ch-price');
      const priceSvg = slot.querySelector('.ch-price-svg');
      if (textCol && priceBox) {{
        for (let step = 0; step < 5; step++) {{
          const tRect = textCol.getBoundingClientRect();
          const pRect = priceBox.getBoundingClientRect();
          const sNow = slot.getBoundingClientRect();
          const horizOverlap = tRect.right > pRect.left - 1 && !(tRect.bottom < pRect.top || tRect.top > pRect.bottom);
          const rightOverflow = pRect.right > sNow.right + 1;
          if (!horizOverlap && !rightOverflow) break;
          if (priceSvg) {{
            const curH = priceSvg.getBoundingClientRect().height;
            priceSvg.style.height = Math.max(13, curH * 0.90) + 'px';
          }}
          priceBox.style.padding = '0.1mm 0.45mm';
          textCol.style.maxWidth = '54%';
        }}
      }}

      // Pass 5: Product Image vs Empty Whitespace Verification & Auto-Boost
      // Ensures the product photo ALWAYS dominates the slot (allowed to pop slightly outside the slot border)
      const img = slot.querySelector('.ch-slot__img-wrap img');
      if (img && img.naturalWidth > 0 && img.naturalHeight > 0) {{
        const natAr = img.naturalWidth / img.naturalHeight;
        const boxW = sRect.width * 1.04;
        const boxH = sRect.height * 1.01;
        const boxAr = boxW / Math.max(1, boxH);
        let drawnW, drawnH;
        if (natAr > boxAr) {{
          drawnW = boxW;
          drawnH = boxW / natAr;
        }} else {{
          drawnH = boxH;
          drawnW = boxH * natAr;
        }}
        const widthFill = drawnW / Math.max(1, sRect.width);
        const heightFill = drawnH / Math.max(1, sRect.height);
        const areaFill = (drawnW * drawnH) / Math.max(1, sRect.width * sRect.height);
        const curScale = parseFloat(slot.style.getPropertyValue('--img-scale') || '1.16') || 1.16;
        // Allow up to 12% controlled pop-out beyond slot frame without covering zone headers or neighboring text
        const maxSafeScale = Math.min(1.38, (sRect.height * 1.12) / Math.max(1, drawnH), (sRect.width * 1.14) / Math.max(1, drawnW));
        if (widthFill * curScale < 0.78 || heightFill * curScale < 0.86 || areaFill < 0.74) {{
          const reqW = 0.80 / Math.max(0.42, widthFill);
          const reqH = 0.88 / Math.max(0.42, heightFill);
          const reqA = Math.sqrt(0.80 / Math.max(0.32, areaFill));
          const boost = Math.min(maxSafeScale, Math.max(curScale, reqW, reqH, reqA));
          slot.style.setProperty('--img-scale', boost.toFixed(2));
          img.style.transform = 'scale(' + boost.toFixed(2) + ') translateY(-3%)';
        }} else if (curScale > maxSafeScale) {{
          slot.style.setProperty('--img-scale', maxSafeScale.toFixed(2));
          img.style.transform = 'scale(' + maxSafeScale.toFixed(2) + ') translateY(-3%)';
        }}
      }}
    }});
  }}
  runChirashiDomQaPass();
  window.addEventListener('load', runChirashiDomQaPass);
  document.querySelectorAll('.ch-slot__img-wrap img').forEach((im) => {{
    im.addEventListener('load', runChirashiDomQaPass);
  }});
</script>
</body>
</html>
"""


def find_chrome_binary() -> str:
    for cand in ("google-chrome", "chromium", "chromium-browser", "/usr/bin/google-chrome", "/usr/bin/chromium"):
        p = shutil.which(cand)
        if p:
            return p
    raise RuntimeError("Chromium / Google Chrome バイナリが見つかりません。")


def export_flyer_pdf(flyer_doc: dict[str, Any]) -> bytes:
    """Render flyer HTML to a single-page high-resolution vector PDF via headless Chromium."""
    html_str = render_flyer_html(flyer_doc, interactive=False, embed_images=True)
    chrome = find_chrome_binary()
    with tempfile.TemporaryDirectory() as tmp:
        html_path = os.path.join(tmp, "flyer.html")
        pdf_path = os.path.join(tmp, "flyer.pdf")
        Path(html_path).write_text(html_str, encoding="utf-8")
        cmd = [
            chrome,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--allow-file-access-from-files",
            "--font-render-hinting=none",
            f"--print-to-pdf={pdf_path}",
            "--no-pdf-header-footer",
            html_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        if res.returncode != 0 or not os.path.exists(pdf_path):
            raise RuntimeError(f"PDF生成に失敗しました: {res.stderr[:300]}")
        return Path(pdf_path).read_bytes()


def export_flyer_jpeg(flyer_doc: dict[str, Any], dpi: int = 300, pdf_bytes: bytes | None = None) -> bytes:
    """Render flyer to PDF and rasterize to Ultra-HD JPEG (default 300 DPI / 4300x3035px, up to 450 DPI for print)."""
    dpi_clamped = max(150, min(int(dpi or 300), 450))
    if pdf_bytes is None:
        pdf_bytes = export_flyer_pdf(flyer_doc)
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, "flyer.pdf")
        out_prefix = os.path.join(tmp, "flyer")
        Path(pdf_path).write_bytes(pdf_bytes)
        cmd = [
            "pdftoppm",
            "-jpeg",
            "-jpegopt",
            "quality=95",
            "-aa",
            "yes",
            "-aaVector",
            "yes",
            "-r",
            str(dpi_clamped),
            "-singlefile",
            pdf_path,
            out_prefix,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        jpg_path = out_prefix + ".jpg"
        if res.returncode != 0 or not os.path.exists(jpg_path):
            raise RuntimeError(f"JPEG生成に失敗しました: {res.stderr[:300]}")
        return Path(jpg_path).read_bytes()
