"""AI & Procedural Background Image Generator for Chirashi Templates, Zones, and Product Slots.

Uses Vertex AI Gemini Image (`gemini-2.5-flash-image` / `gemini-3.1-flash-image`) to generate atmospheric
product backdrops (e.g., autumn maple wood table, fresh morning farm droplets, crushed ice seafood counter,
traditional Japanese gold/crimson washi festivity), with a fast high-resolution SVG->JPEG fallback via
headless Chromium / ImageMagick so generation always succeeds even offline or under quota limits.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .repository import FlyerRepository

log = logging.getLogger("cymbal-flyer.bg_gen")

PROJECT_ID = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
GEMINI_LOCATION = os.environ.get("GEMINI_LOCATION", "global")
IMAGE_MODELS = (
    os.environ.get("FLYER_IMAGE_MODEL", "gemini-2.5-flash-image"),
    "gemini-3.1-flash-image",
)

BG_PRESETS: list[dict[str, str]] = [
    {
        "id": "autumn_wood",
        "label": "🍁 秋の味覚・紅葉と温かみのある木目テーブル",
        "prompt": "Warm rustic Japanese wooden dining table with soft autumn maple leaves (momiji) and warm golden sunlight bokeh in the corners, bright clean center space for placing food product photos, commercial supermarket flyer background, no text, no letters.",
        "svg_theme": "autumn",
    },
    {
        "id": "fresh_farm",
        "label": "🥬 朝採れ青果・みずみずしい緑と水滴ボケ",
        "prompt": "Fresh morning green vegetable garden bokeh with sparkling water droplets and soft sunlit wooden crate texture at the bottom, bright clean center for food product display, Japanese supermarket flyer backdrop, no text.",
        "svg_theme": "green",
    },
    {
        "id": "ocean_ice",
        "label": "🐟 鮮魚市場・クラッシュアイスと青海波",
        "prompt": "Glistening crushed ice surface with subtle Japanese seigaiha ocean wave pattern in cool marine blue and white, bright clean center for sashimi and seafood product placement, commercial flyer background, no text.",
        "svg_theme": "ocean",
    },
    {
        "id": "meat_gold",
        "label": "🥩 精肉・黒毛和牛向け黒金プレミアム和紙",
        "prompt": "Luxury Japanese dark charcoal and warm crimson-gold washi paper texture with subtle gold leaf sparkles along the edges, appetizing gourmet meat flyer background, no text.",
        "svg_theme": "meat",
    },
    {
        "id": "nabe_steam",
        "label": "🍲 あったか鍋・湯気と和風団らん食卓",
        "prompt": "Warm cozy Japanese winter dining scene with soft rising steam, warmtatami/wood tones and golden lantern glow in the background, clean center for hotpot ingredients, no text.",
        "svg_theme": "nabe",
    },
    {
        "id": "sale_burst",
        "label": "💥 大特売・赤黄サンバースト集中線背景",
        "prompt": "Energetic Japanese supermarket bargain sale background with bright yellow and red radial sunburst rays and festive confetti around the edges, bright center for product placement, no text.",
        "svg_theme": "burst",
    },
]


def _render_procedural_svg_backdrop(svg_theme: str, prompt: str) -> bytes:
    """Render a rich, high-resolution artistic SVG backdrop and rasterize via ImageMagick `convert` to JPEG."""
    themes = {
        "autumn": {
            "bg1": "#fff8e7",
            "bg2": "#ffe0b2",
            "bg3": "#ffcc80",
            "accent1": "#e65100",
            "accent2": "#d84315",
            "accent3": "#ffb300",
        },
        "green": {
            "bg1": "#f4fbf1",
            "bg2": "#dcedc8",
            "bg3": "#a5d6a7",
            "accent1": "#2e7d32",
            "accent2": "#66bb6a",
            "accent3": "#ffee58",
        },
        "ocean": {
            "bg1": "#f0f9ff",
            "bg2": "#b3e5fc",
            "bg3": "#81d4fa",
            "accent1": "#0277bd",
            "accent2": "#29b6f6",
            "accent3": "#ffffff",
        },
        "meat": {
            "bg1": "#3e1c1c",
            "bg2": "#5d1919",
            "bg3": "#261414",
            "accent1": "#ffd54f",
            "accent2": "#ff8a65",
            "accent3": "#ffca28",
        },
        "nabe": {
            "bg1": "#fffaf0",
            "bg2": "#ffe8cc",
            "bg3": "#ffd199",
            "accent1": "#bf360c",
            "accent2": "#fb8c00",
            "accent3": "#fff59d",
        },
        "burst": {
            "bg1": "#fffde7",
            "bg2": "#fff176",
            "bg3": "#ffd54f",
            "accent1": "#d50000",
            "accent2": "#ff6d00",
            "accent3": "#ffffff",
        },
    }
    t = themes.get(svg_theme, themes["autumn"])

    # Build decorative rays, bokeh circles, and seasonal motifs around the edges while keeping the center clean for products
    rays = []
    for i in range(0, 360, 15):
        rays.append(
            f'<polygon points="400,300 {400 + int(600 * __import__("math").cos(i * 0.01745))},{300 + int(600 * __import__("math").sin(i * 0.01745))} '
            f'{400 + int(600 * __import__("math").cos((i + 7) * 0.01745))},{300 + int(600 * __import__("math").sin((i + 7) * 0.01745))}" '
            f'fill="{t["accent2"]}" fill-opacity="0.10"/>'
        )

    bokeh = [
        f'<circle cx="70" cy="70" r="85" fill="{t["accent1"]}" fill-opacity="0.16"/>',
        f'<circle cx="730" cy="80" r="95" fill="{t["accent2"]}" fill-opacity="0.18"/>',
        f'<circle cx="90" cy="520" r="105" fill="{t["accent3"]}" fill-opacity="0.22"/>',
        f'<circle cx="720" cy="530" r="90" fill="{t["accent1"]}" fill-opacity="0.15"/>',
        f'<circle cx="400" cy="300" r="250" fill="{t["bg1"]}" fill-opacity="0.72"/>',
    ]

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600" viewBox="0 0 800 600">
  <defs>
    <radialGradient id="rg" cx="50%" cy="48%" r="70%">
      <stop offset="0%" stop-color="{t['bg1']}"/>
      <stop offset="65%" stop-color="{t['bg2']}"/>
      <stop offset="100%" stop-color="{t['bg3']}"/>
    </radialGradient>
  </defs>
  <rect width="800" height="600" fill="url(#rg)"/>
  <g>{"".join(rays)}</g>
  <g>{"".join(bokeh)}</g>
</svg>"""

    with tempfile.TemporaryDirectory() as tmp:
        svg_p = os.path.join(tmp, "bg.svg")
        jpg_p = os.path.join(tmp, "bg.jpg")
        Path(svg_p).write_text(svg, encoding="utf-8")
        try:
            subprocess.run(["convert", svg_p, "-quality", "90", jpg_p], check=True, timeout=15)
            return Path(jpg_p).read_bytes()
        except Exception:  # noqa: BLE001
            from .render import find_chrome_binary

            chrome = find_chrome_binary()
            pdf_p = os.path.join(tmp, "bg.pdf")
            html_p = os.path.join(tmp, "bg.html")
            Path(html_p).write_text(
                f'<!doctype html><html><head><style>@page{{size:800px 600px;margin:0}}body{{margin:0}}</style></head><body>{svg}</body></html>',
                encoding="utf-8",
            )
            subprocess.run(
                [chrome, "--headless", "--no-sandbox", "--disable-gpu", f"--print-to-pdf={pdf_p}", f"file://{html_p}"],
                check=True,
                timeout=20,
            )
            subprocess.run(["pdftoppm", "-jpeg", "-r", "96", "-singlefile", pdf_p, os.path.join(tmp, "out")], check=True, timeout=15)
            return Path(os.path.join(tmp, "out.jpg")).read_bytes()


def generate_background_image(
    repo: FlyerRepository,
    prompt: str = "",
    preset_id: str = "autumn_wood",
) -> dict[str, Any]:
    """Generate a background image via Vertex AI Gemini Image (or procedural fallback) and store in GCS + local storage."""
    preset = next((p for p in BG_PRESETS if p["id"] == preset_id), BG_PRESETS[0])
    full_prompt = (
        f"{preset['prompt']} Additional instructions: {prompt}. "
        "Important: Soft atmospheric background texture for a Japanese supermarket promotional flyer. "
        "Keep the center area bright and uncluttered so product photos placed on top stand out clearly. "
        "Do NOT include any text, letters, numbers, or price tags in the image."
        if prompt
        else preset["prompt"]
    )

    img_bytes: bytes | None = None
    used_model = "procedural_svg"

    if os.environ.get("FLYER_AI_MODE") != "fallback" and os.environ.get("FLYER_DATA_MODE") != "local":
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(vertexai=True, project=PROJECT_ID or None, location=GEMINI_LOCATION)
            for m_id in IMAGE_MODELS:
                try:
                    resp = client.models.generate_content(
                        model=m_id,
                        contents=full_prompt,
                        config=types.GenerateContentConfig(
                            response_modalities=["IMAGE"],
                            temperature=0.6,
                        ),
                    )
                    for cand in getattr(resp, "candidates", []) or []:
                        for part in getattr(getattr(cand, "content", None), "parts", []) or []:
                            inline = getattr(part, "inline_data", None)
                            if inline and getattr(inline, "data", None):
                                img_bytes = inline.data
                                used_model = m_id
                                break
                        if img_bytes:
                            break
                    if img_bytes:
                        break
                except Exception as inner_e:  # noqa: BLE001
                    log.warning("Gemini image model %s skipped: %s", m_id, inner_e)
        except Exception as e:  # noqa: BLE001
            log.warning("Vertex AI background generation fallback used: %s", e)

    if not img_bytes:
        img_bytes = _render_procedural_svg_backdrop(preset.get("svg_theme", "autumn"), prompt)

    bg_id = f"bg-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    rel_path = f"bg_images/{bg_id}.jpg"
    repo.write_bytes(rel_path, img_bytes, "image/jpeg")

    return {
        "bg_id": bg_id,
        "url": f"/api/bg_images/{bg_id}.jpg",
        "preset_id": preset_id,
        "prompt": prompt or preset["label"],
        "model": used_model,
    }
