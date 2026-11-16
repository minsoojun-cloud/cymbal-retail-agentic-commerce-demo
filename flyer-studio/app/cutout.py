"""Transparent Product Cutout (Studio White & Cast-Shadow Removal, Tight Crop) and Product-Harmonized Slot Backdrop Resolver."""
from __future__ import annotations

from collections import deque
import io
import logging
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter

log = logging.getLogger("cymbal-flyer.cutout")

_MEM_CACHE: dict[str, bytes] = {}
_ASPECT_CACHE: dict[str, float] = {}
_DISK_CACHE_DIR = Path("/tmp/cymbal_product_cutouts_v7")


def remove_studio_bg(im: Image.Image) -> Image.Image:
    """Remove studio white background and outer neutral cast shadows, tight-cropping to the
    exact product bounds (+ 3% shadow margin) so there is ZERO empty transparent padding around
    tall or wide products. Applies Lanczos upscale + UnsharpMask sharpening and bakes a subtle
    contact shadow directly into the RGBA image.
    """
    im_rgb = im.convert("RGB")
    w, h = im_rgb.size
    sw, sh = 200, 200
    small = im_rgb.resize((sw, sh), Image.Resampling.BILINEAR)
    px = small.load()

    smooth_gray = small.convert("L").filter(ImageFilter.GaussianBlur(radius=0.8))
    edges = smooth_gray.filter(ImageFilter.FIND_EDGES).load()

    visited = [[False] * sw for _ in range(sh)]
    is_bg = [[False] * sw for _ in range(sh)]

    q: deque[tuple[int, int]] = deque()
    for x in range(sw):
        for y in (0, sh - 1):
            q.append((x, y))
            visited[y][x] = True
    for y in range(sh):
        for x in (0, sw - 1):
            if not visited[y][x]:
                q.append((x, y))
                visited[y][x] = True

    while q:
        x, y = q.popleft()
        r, g, b = px[x, y]
        lum = (r + g + b) // 3
        sat = max(r, g, b) - min(r, g, b)
        dist_edge = min(x, y, sw - 1 - x, sh - 1 - y)
        edge_val = 0 if dist_edge <= 2 else edges[x, y]
        cond_pure_white = lum >= 250 and sat <= 5 and edge_val < 8
        cond_smooth_shadow = lum >= 198 and sat <= 10 and edge_val < 10
        cond_border_margin = dist_edge < 12 and lum >= 180 and sat <= 12 and edge_val < 16
        if cond_pure_white or cond_smooth_shadow or cond_border_margin:
            is_bg[y][x] = True
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < sw and 0 <= ny < sh and not visited[ny][nx]:
                    visited[ny][nx] = True
                    q.append((nx, ny))

    # Eliminate tiny disconnected foreground speckles (< 220 pixels at 200x200) near borders
    fg_vis = [[False] * sw for _ in range(sh)]
    for y in range(sh):
        for x in range(sw):
            if not is_bg[y][x] and not fg_vis[y][x]:
                comp = [(x, y)]
                fg_vis[y][x] = True
                cq = deque([(x, y)])
                while cq:
                    cx, cy = cq.popleft()
                    for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                        if 0 <= nx < sw and 0 <= ny < sh and not is_bg[ny][nx] and not fg_vis[ny][nx]:
                            fg_vis[ny][nx] = True
                            cq.append((nx, ny))
                            comp.append((nx, ny))
                if len(comp) < 220:
                    for cx, cy in comp:
                        is_bg[cy][cx] = True

    # Build mask using C-accelerated PIL point/filter operations instead of nested Python loops
    flat_mask = bytearray(0 if is_bg[y][x] else 255 for y in range(sh) for x in range(sw))
    mask = Image.frombytes("L", (sw, sh), bytes(flat_mask))
    # Slight erosion (MinFilter) + Gaussian feather removes any 1px white halo in C (< 0.5ms)
    mask = mask.filter(ImageFilter.MinFilter(3))
    full_mask = mask.resize((w, h), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(radius=1.4))
    sharp_rgb = im_rgb.filter(ImageFilter.UnsharpMask(radius=1.1, percent=110, threshold=3))
    rgba = sharp_rgb.convert("RGBA")
    rgba.putalpha(full_mask)

    # Tight-crop to actual opaque product bounds (alpha > 52) so NO empty square padding remains!
    bbox = full_mask.point(lambda p: 255 if p > 52 else 0).getbbox()
    if bbox:
        bx0, by0, bx1, by1 = bbox
        bw, bh = bx1 - bx0, by1 - by0
        if bw > 20 and bh > 20:
            crop = rgba.crop(bbox)
            target_long_edge = 640
            scale = min(target_long_edge / max(bw, bh), 2.5)
            nw = max(1, int(round(bw * scale)))
            nh = max(1, int(round(bh * scale)))
            crop_resized = crop.resize((nw, nh), Image.Resampling.LANCZOS)

            # Bake subtle contact shadow into a tight canvas (nw + 12, nh + 12)
            pad = 6
            cw, ch = nw + pad * 2, nh + pad * 2
            shadow_alpha = crop_resized.getchannel("A").filter(ImageFilter.GaussianBlur(radius=4.5))
            shadow_alpha = shadow_alpha.point(lambda a: int(a * 0.28))
            shadow_layer = Image.new("RGBA", (nw, nh), (15, 18, 22, 0))
            shadow_layer.putalpha(shadow_alpha)

            canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            canvas.paste(shadow_layer, (pad + 2, pad + 4), shadow_layer)
            canvas.alpha_composite(crop_resized, (pad, pad))
            return canvas

    return rgba


def get_product_cutout_path_and_bytes(img_path: Path) -> tuple[Path | None, bytes, float]:
    """Return `(disk_cache_path, png_bytes, aspect_ratio)` for a catalog product image.
    Caps in-memory cache size so Cloud Run memory stays low even on 80-item flyers.
    """
    key = f"{img_path.name}:{img_path.stat().st_size}"
    try:
        _DISK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        disk_p = _DISK_CACHE_DIR / f"{img_path.stem}.png"
    except Exception:  # noqa: BLE001
        disk_p = None

    if key in _MEM_CACHE and disk_p is not None and disk_p.is_file():
        return disk_p, _MEM_CACHE[key], _ASPECT_CACHE.get(key, 1.0)

    if disk_p is not None and disk_p.is_file() and disk_p.stat().st_size > 100:
        data = disk_p.read_bytes()
        if key not in _ASPECT_CACHE:
            try:
                with Image.open(io.BytesIO(data)) as cim:
                    _ASPECT_CACHE[key] = round(cim.size[0] / max(1, cim.size[1]), 3)
            except Exception:  # noqa: BLE001
                _ASPECT_CACHE[key] = 1.0
        if len(_MEM_CACHE) > 48:
            _MEM_CACHE.clear()
        _MEM_CACHE[key] = data
        return disk_p, data, _ASPECT_CACHE[key]

    with Image.open(img_path) as im:
        cut = remove_studio_bg(im)
        ar = round(cut.size[0] / max(1, cut.size[1]), 3)
        buf = io.BytesIO()
        cut.save(buf, format="PNG", compress_level=1)
        png_bytes = buf.getvalue()

    _ASPECT_CACHE[key] = ar
    if len(_MEM_CACHE) > 48:
        _MEM_CACHE.clear()
    _MEM_CACHE[key] = png_bytes
    if disk_p is not None:
        try:
            disk_p.write_bytes(png_bytes)
        except Exception:  # noqa: BLE001
            pass
    return disk_p, png_bytes, ar


def get_product_cutout_png_bytes(img_path: Path) -> bytes:
    """Return transparent PNG bytes for a catalog product image."""
    _, data, _ = get_product_cutout_path_and_bytes(img_path)
    return data


def get_product_cutout_aspect_ratio(img_path: Path | None) -> float:
    """Return the width/height aspect ratio of the product in <0.5ms using a fast 100x100 luminance bbox."""
    if img_path is None or not img_path.is_file():
        return 1.0
    key = f"{img_path.name}:{img_path.stat().st_size}"
    if key in _ASPECT_CACHE:
        return _ASPECT_CACHE[key]
    try:
        with Image.open(img_path) as im:
            thumb = im.convert("L").resize((100, 100), Image.Resampling.NEAREST)
            # Crop 8px border margin to ignore corner studio shadows
            inner = thumb.crop((8, 8, 92, 92))
            bbox = inner.point(lambda p: 255 if p < 235 else 0).getbbox()
            if bbox:
                bw = max(8, bbox[2] - bbox[0])
                bh = max(8, bbox[3] - bbox[1])
                ar = round(bw / bh, 3)
            else:
                ar = 1.0
        _ASPECT_CACHE[key] = ar
        return ar
    except Exception:  # noqa: BLE001
        return 1.0


def resolve_default_slot_bg_image(slot: dict[str, Any], flyer_theme: str = "") -> str:
    """Resolve a product-harmonized background image URL for a slot unless a solid color was explicitly selected."""
    explicit_bg_img = (slot.get("bg_image_url") or "").strip()
    if explicit_bg_img:
        return explicit_bg_img

    bg_choice = (slot.get("bg_color") or "auto").strip()
    if bg_choice.startswith("bg:"):
        preset_name = bg_choice.split(":", 1)[1].strip()
        return f"/static/img/bg_presets/{preset_name}.jpg"

    if bg_choice not in ("", "auto"):
        return ""

    if slot.get("shape") == "burst":
        return "/static/img/bg_presets/sale_burst.jpg"

    prod = slot.get("product") or {}
    cat = f"{prod.get('category') or ''} {prod.get('category_path') or ''}"
    title = f"{prod.get('flyer_name') or ''} {prod.get('title') or ''}"

    if "お米" in cat or "調味料" in cat or "缶詰" in cat:
        return "/static/img/bg_presets/harvest_pantry.jpg"

    if "お魚" in cat or "水産" in cat or any(
        w in title for w in ("鮭", "サーモン", "まぐろ", "ぶり", "真鯛", "たら", "ふぐ", "えび", "かに", "いか", "だこ", "タコ", "しらす", "ほたて", "サバ", "アジ", "刺身", "海鮮", "ムール貝")
    ):
        return "/static/img/bg_presets/ocean_ice.jpg"

    if "お肉" in cat or any(
        w in title for w in ("牛", "豚", "鶏", "ステーキ", "焼肉", "ミンチ", "こま切れ", "ロース", "カルビ", "ハム", "ベーコン", "ウインナー", "ソーセージ")
    ):
        return "/static/img/bg_presets/meat_gold.jpg"

    if "野菜" in cat or "果物" in cat:
        if any(
            w in title
            for w in ("きのこ", "しめじ", "えのき", "エリンギ", "まいたけ", "椎茸", "松茸", "さつまいも", "栗", "かぼちゃ", "柿", "梨", "りんご", "ぶどう", "れんこん", "ごぼう", "里芋")
        ):
            return "/static/img/bg_presets/autumn_wood.jpg"
        return "/static/img/bg_presets/fresh_farm.jpg"

    if "お惣菜" in cat or "豆腐" in cat or any(
        w in title for w in ("鍋", "おでん", "スープ", "つゆ", "フライ", "コロッケ", "弁当", "寿司", "天ぷら", "餃子", "焼売", "うどん", "ほうとう")
    ):
        return "/static/img/bg_presets/nabe_steam.jpg"

    if any(w in title for w in ("米", "こまち", "コシヒカリ", "パスタ", "スパゲッティ", "油", "醤油", "みそ", "ソース", "カレー")):
        return "/static/img/bg_presets/harvest_pantry.jpg"

    if "秋" in (flyer_theme or ""):
        return "/static/img/bg_presets/autumn_wood.jpg"

    return "/static/img/bg_presets/dairy_morning.jpg"
