"""High-DPI Banner Renderer & Exporter (JPEG & PDF).

Supports:
1. Server-side Playwright Headless Chromium rendering (`render_banner_via_chromium_async`) of the exact
   React `<BannerCanvas>` component (`/?renderMode=1`) at `deviceScaleFactor=3` (300 DPI equivalent),
   guaranteeing 100% pixel-identical layout and typography between the monitor screen, JPEG, and PDF!
2. Converting high-DPI `image_data_url` into print-ready 300 DPI JPEG (`quality=96, subsampling=0`) and A4 PDF.
3. Server-side Pillow fallback rendering when running in unit-test environments without an active HTTP port.
4. Saving generated files to local storage and optionally to GCS (`gs://${GCS_BUCKET}/banners/`).
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas

from edion_banner.category_schemas import CATEGORY_DEFINITIONS

log = logging.getLogger(__name__)

FONT_CANDIDATES_BOLD = [
    os.path.expanduser("~/.local/share/fonts/noto-jp/NotoSansJP-Bold.otf"),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]

FONT_CANDIDATES_REGULAR = [
    os.path.expanduser("~/.local/share/fonts/noto-jp/NotoSansJP-Medium.otf"),
    os.path.expanduser("~/.local/share/fonts/noto-jp/NotoSansJP-Regular.otf"),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]

# Reusable Playwright Chromium browser state + lock
_PW_LOCK = asyncio.Lock()
_PW_INSTANCE: Any = None
_PW_BROWSER: Any = None
_PW_PAGE: Any = None


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES_REGULAR
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def decode_data_url_to_image(image_data_url: str) -> Image.Image:
    raw = image_data_url.strip()
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    img_bytes = base64.b64decode(raw)
    img = Image.open(io.BytesIO(img_bytes))
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        return bg
    return img.convert("RGB")


async def render_banner_via_chromium_async(
    category: str,
    specs: dict[str, Any],
) -> Image.Image | None:
    """Renders the exact React `<BannerCanvas>` in Headless Chromium (`deviceScaleFactor=3`)
    so JPEG and PDF exports are 100% identical to the browser monitor screen.
    """
    global _PW_INSTANCE, _PW_BROWSER, _PW_PAGE

    if "PYTEST_CURRENT_TEST" in os.environ and os.environ.get("ENABLE_PLAYWRIGHT_IN_PYTEST") != "1":
        return None

    port = os.environ.get("PORT", "8080")
    target_url = os.environ.get("RENDER_BASE_URL", f"http://127.0.0.1:{port}") + "/?renderMode=1"

    async with _PW_LOCK:
        try:
            from playwright.async_api import async_playwright

            if _PW_INSTANCE is None:
                _PW_INSTANCE = await async_playwright().start()
            if _PW_BROWSER is None or not _PW_BROWSER.is_connected():
                _PW_BROWSER = await _PW_INSTANCE.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--font-render-hinting=none"],
                )
                _PW_PAGE = None

            if _PW_PAGE is None or _PW_PAGE.is_closed():
                context = await _PW_BROWSER.new_context(
                    viewport={"width": 1200, "height": 1600},
                    device_scale_factor=3.0,
                )
                _PW_PAGE = await context.new_page()
                await _PW_PAGE.goto(target_url, wait_until="networkidle", timeout=15000)

            # Inject payload into the React render-mode page
            await _PW_PAGE.evaluate(
                "payload => window.__setRenderPayload && window.__setRenderPayload(payload)",
                {"category": category, "specs": specs},
            )
            await _PW_PAGE.wait_for_function(
                "() => document.querySelector('#banner-export-target')?.getAttribute('data-ready') === 'true'",
                timeout=5000,
            )
            await _PW_PAGE.evaluate("() => document.fonts ? document.fonts.ready : Promise.resolve()")
            await _PW_PAGE.wait_for_timeout(120)

            locator = _PW_PAGE.locator("#banner-export-target")
            png_bytes = await locator.screenshot(type="png")
            img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
            return img
        except Exception as e:
            log.warning("Playwright Chromium render fell back to Pillow: %s", e)
            _PW_PAGE = None
            return None


def render_fallback_banner_image(
    category: str,
    specs: dict[str, Any],
    product_info: dict[str, Any] | None = None,
) -> Image.Image:
    """Renders a high-resolution server-side banner image when no frontend canvas or Chromium is available."""
    cat_def = CATEGORY_DEFINITIONS.get(category, CATEGORY_DEFINITIONS["tv"])
    is_landscape = cat_def.get("orientation") == "landscape"
    width, height = (1600, 1100) if is_landscape else (1100, 1550)

    img = Image.new("RGB", (width, height), (242, 244, 247))
    draw = ImageDraw.Draw(img)

    header_color = (0, 117, 194)
    header_title = cat_def["name"]
    if category == "tv":
        tv_type = str(specs.get("type", "MiniLED"))
        if tv_type == "MiniLED":
            header_color = (27, 158, 62)
            header_title = "Mini LED テレビ"
        elif tv_type == "有機EL":
            header_color = (17, 17, 17)
            header_title = "有機ELテレビ"
        elif tv_type == "2K液晶":
            header_color = (0, 117, 194)
            header_title = "2K液晶テレビ"
        else:
            header_color = (0, 117, 194)
            header_title = "4K液晶テレビ"
    elif category == "pc":
        header_color = (31, 78, 120)
        header_title = str(specs.get("brand_logo") or specs.get("maker") or "PC")
    elif category in ("wine_cellar", "cooler_warmer"):
        header_color = (0, 122, 112)
        header_title = str(specs.get("cooling_type") or "ペルチェ方式")
    elif category == "freezer":
        header_color = (28, 84, 157)
        header_title = "冷凍庫"
    elif category == "refrigerator":
        cap = int(float(specs.get("capacity_l") or 500))
        if cap <= 349:
            header_color = (41, 171, 226)
        else:
            header_color = (0, 146, 80)
        header_title = f"定格内容量 {cap}L 冷蔵庫"

    draw.rectangle([16, 16, width - 16, height - 16], fill=(235, 237, 240), outline=(80, 80, 80), width=4)
    draw.rectangle([20, 20, width - 20, 175], fill=header_color)

    f_title = _load_font(64, bold=True)
    f_sub = _load_font(40, bold=True)
    f_label = _load_font(26, bold=True)
    f_val = _load_font(38, bold=True)
    f_small = _load_font(22, bold=False)

    maker = str(specs.get("maker") or (product_info or {}).get("maker_name") or "Cymbal Retail")
    model_no = str(specs.get("model_no") or (product_info or {}).get("search_model_no") or "")
    jan = str(specs.get("jan_code") or (product_info or {}).get("jan_code") or "")

    draw.text((50, 52), header_title, fill=(255, 255, 255), font=f_title)
    draw.text((width - 560, 42), maker, fill=(255, 255, 255), font=f_label)
    draw.text((width - 560, 82), model_no, fill=(255, 255, 255), font=f_sub)

    fields = cat_def["fields"]
    cols = 3 if is_landscape else 2
    margin_x = 40
    top_y = 205
    avail_w = width - margin_x * 2
    card_w = (avail_w - (cols - 1) * 20) // cols
    card_h = 115

    visible_fields = [f for f in fields if str(specs.get(f["key"], "")).strip() != ""][:18]
    for idx, f in enumerate(visible_fields):
        r = idx // cols
        c = idx % cols
        x0 = margin_x + c * (card_w + 20)
        y0 = top_y + r * (card_h + 18)
        if y0 + card_h > height - 90:
            break
        draw.rectangle([x0, y0, x0 + card_w, y0 + card_h], fill=(255, 255, 255), outline=(120, 120, 120), width=2)
        draw.rectangle([x0, y0, x0 + card_w, y0 + 38], fill=(95, 99, 104))
        draw.text((x0 + 14, y0 + 5), str(f["label"])[:18], fill=(255, 255, 255), font=f_small)
        val_str = str(specs.get(f["key"], ""))
        unit_str = f" {f['unit']}" if f.get("unit") and not val_str.endswith(str(f["unit"])) else ""
        draw.text((x0 + 18, y0 + 48), f"{val_str}{unit_str}"[:22], fill=(20, 20, 20), font=f_val)

    draw.rectangle([20, height - 76, width - 20, height - 20], fill=(70, 74, 78))
    draw.text(
        (45, height - 62),
        f"Cymbal Retail VMD 機能表 | カテゴリ: {cat_def['name']} | 型番: {model_no} | JAN: {jan}",
        fill=(255, 255, 255),
        font=f_small,
    )
    return img


def _encode_image_to_jpeg(img: Image.Image, quality: int = 96) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, subsampling=0, optimize=True, dpi=(300, 300))
    return buf.getvalue()


def _encode_image_to_pdf(img: Image.Image, category: str = "tv", specs: dict[str, Any] | None = None) -> bytes:
    img_w, img_h = img.size
    if img_w >= img_h:
        page_w, page_h = 841.89, 595.27
    else:
        page_w, page_h = 595.27, 841.89

    margin = 16.0
    avail_w = page_w - margin * 2
    avail_h = page_h - margin * 2
    scale = min(avail_w / img_w, avail_h / img_h)
    draw_w = img_w * scale
    draw_h = img_h * scale
    offset_x = (page_w - draw_w) / 2.0
    offset_y = (page_h - draw_h) / 2.0

    img_buf = io.BytesIO()
    img.save(img_buf, format="JPEG", quality=97, subsampling=0)
    img_buf.seek(0)

    pdf_buf = io.BytesIO()
    c = pdf_canvas.Canvas(pdf_buf, pagesize=(page_w, page_h))
    c.setTitle(f"Cymbal_VMD_Banner_{(specs or {}).get('model_no', category)}")
    c.setAuthor("Cymbal Retail VMD 機能表・POP自動生成スタジオ")
    c.drawImage(
        ImageReader(img_buf),
        offset_x,
        offset_y,
        width=draw_w,
        height=draw_h,
        preserveAspectRatio=True,
    )
    c.showPage()
    c.save()
    return pdf_buf.getvalue()


async def resolve_banner_image_async(
    image_data_url: str | None = None,
    category: str = "tv",
    specs: dict[str, Any] | None = None,
    product_info: dict[str, Any] | None = None,
) -> Image.Image:
    if image_data_url:
        return decode_data_url_to_image(image_data_url)
    chromium_img = await render_banner_via_chromium_async(category, specs or {})
    if chromium_img is not None:
        return chromium_img
    return render_fallback_banner_image(category, specs or {}, product_info)


async def generate_jpeg_bytes_async(
    image_data_url: str | None = None,
    category: str = "tv",
    specs: dict[str, Any] | None = None,
    product_info: dict[str, Any] | None = None,
    quality: int = 96,
) -> bytes:
    img = await resolve_banner_image_async(image_data_url, category, specs, product_info)
    return _encode_image_to_jpeg(img, quality=quality)


async def generate_pdf_bytes_async(
    image_data_url: str | None = None,
    category: str = "tv",
    specs: dict[str, Any] | None = None,
    product_info: dict[str, Any] | None = None,
) -> bytes:
    img = await resolve_banner_image_async(image_data_url, category, specs, product_info)
    return _encode_image_to_pdf(img, category=category, specs=specs)


def generate_jpeg_bytes(
    image_data_url: str | None = None,
    category: str = "tv",
    specs: dict[str, Any] | None = None,
    product_info: dict[str, Any] | None = None,
    quality: int = 96,
) -> bytes:
    if image_data_url:
        img = decode_data_url_to_image(image_data_url)
    else:
        img = render_fallback_banner_image(category, specs or {}, product_info)
    return _encode_image_to_jpeg(img, quality=quality)


def generate_pdf_bytes(
    image_data_url: str | None = None,
    category: str = "tv",
    specs: dict[str, Any] | None = None,
    product_info: dict[str, Any] | None = None,
) -> bytes:
    if image_data_url:
        img = decode_data_url_to_image(image_data_url)
    else:
        img = render_fallback_banner_image(category, specs or {}, product_info)
    return _encode_image_to_pdf(img, category=category, specs=specs)


def persist_banner_artifact(
    filename: str,
    data: bytes,
    content_type: str,
) -> dict[str, str]:
    """Saves the rendered JPEG or PDF locally and optionally to GCS."""
    local_dir = os.path.abspath(os.environ.get("LOCAL_STORAGE_DIR", "./data/banners"))
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, filename)
    with open(local_path, "wb") as f:
        f.write(data)

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID", "")
    default_bucket = f"{project_id}-spec-banner" if project_id else ""
    gcs_bucket = os.environ.get("GCS_BUCKET", default_bucket)
    gcs_uri = ""
    if os.environ.get("ENABLE_GCS_UPLOAD", "false").lower() == "true" and gcs_bucket:
        try:
            from google.cloud import storage

            client = storage.Client()
            bucket = client.bucket(gcs_bucket)
            blob = bucket.blob(f"banners/{filename}")
            blob.upload_from_string(data, content_type=content_type)
            gcs_uri = f"gs://{gcs_bucket}/banners/{filename}"
        except Exception as e:
            log.warning("GCS upload skipped: %s", e)

    return {
        "local_path": local_path,
        "download_url": f"/api/files/banners/{filename}",
        "gcs_uri": gcs_uri,
    }


def persist_banner_to_bigquery(
    *,
    jan_code: str,
    search_model_no: str,
    category: str,
    maker_name: str,
    product_name: str,
    specs: dict[str, Any],
    gcs_jpeg_uri: str,
    gcs_pdf_uri: str,
    jpg_bytes: bytes,
) -> str:
    """Saves the generated banner metadata, specs, and JPEG binary (base64) to BigQuery
    (`{PROJECT_ID}.{BQ_DATASET}.kinohyo_banners`).
    Does NOT modify the product master (`mst_product`).
    """
    if "PYTEST_CURRENT_TEST" in os.environ:
        return "bq://cymbal-mock/cymbal_enrichment/kinohyo_banners (mock)"

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID", "")
    dataset_id = os.environ.get("BQ_DATASET") or os.environ.get("ENRICH_BQ_DATASET", "cymbal_enrichment")
    table_id = os.environ.get("BQ_TABLE", "kinohyo_banners")

    try:
        from datetime import datetime, timezone
        import json
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/bigquery"])
        authed_session = AuthorizedSession(creds)

        clean_specs = {
            k: v
            for k, v in (specs or {}).items()
            if not str(k).startswith("_")
        }
        row = {
            "jan_code": str(jan_code or ""),
            "search_model_no": str(search_model_no or ""),
            "category": str(category or ""),
            "maker_name": str(maker_name or ""),
            "product_name": str(product_name or ""),
            "specs_json": json.dumps(clean_specs, ensure_ascii=False),
            "gcs_jpeg_uri": str(gcs_jpeg_uri or ""),
            "gcs_pdf_uri": str(gcs_pdf_uri or ""),
            "jpeg_base64": base64.b64encode(jpg_bytes).decode("ascii") if jpg_bytes else "",
            "jpeg_size_bytes": len(jpg_bytes) if jpg_bytes else 0,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        url = (
            f"https://bigquery.googleapis.com/bigquery/v2/projects/{project_id}"
            f"/datasets/{dataset_id}/tables/{table_id}/insertAll"
        )
        resp = authed_session.post(url, json={"rows": [{"json": row}]}, timeout=10)
        if resp.status_code == 200 and not resp.json().get("insertErrors"):
            return f"bq://{project_id}.{dataset_id}.{table_id}"
        log.warning("BigQuery insertAll warning: %s %s", resp.status_code, resp.text[:200])
    except Exception as e:
        log.warning("BigQuery banner save skipped: %s", e)

    return ""

