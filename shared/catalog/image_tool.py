"""デモカタログ用ライセンス適合画像検索・リサイズ補助ツール。

Wikimedia Commons / Openverse から商用・改変可ライセンスの画像を検索し、
600x600 JPEG として online-store-adk/static/img/products/ に保存してクレジットを記録する。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time

import requests
from PIL import Image, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
IMG_DIR = os.environ.get("PRODUCT_IMAGES_DIR", f"{REPO_ROOT}/online-store-adk/static/img/products")
CREDITS = os.environ.get("CREDITS_FILE", f"{HERE}/blueprint/credits.jsonl")
UA = "CymbalRetailDemoCatalog/1.0 (Google Cloud Retail Demo) python-requests"
OK_LIC = re.compile(r"^(cc0|pdm|public domain|cc by(-sa)?( \d(\.\d)?)?|by|by-sa)", re.I)


def _strip(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def search_commons(q, n):
    r = requests.get("https://commons.wikimedia.org/w/api.php", headers={"User-Agent": UA}, timeout=30, params={
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"{q} filetype:bitmap", "gsrlimit": n, "prop": "imageinfo",
        "iiprop": "url|extmetadata|size", "iiurlwidth": 900})
    out = []
    for p in (r.json().get("query", {}).get("pages", {}) or {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        m = ii.get("extmetadata", {})
        lic = _strip(m.get("LicenseShortName", {}).get("value"))
        out.append({"title": p.get("title"), "thumb": ii.get("thumburl"), "license": lic,
                    "author": _strip(m.get("Artist", {}).get("value"))[:120],
                    "page": ii.get("descriptionurl"), "w": ii.get("width"), "h": ii.get("height"),
                    "allowed": bool(OK_LIC.match(lic or "")) and "nc" not in lic.lower() and "nd" not in lic.lower()})
    return out


def search_openverse(q, n):
    r = requests.get("https://api.openverse.org/v1/images/", headers={"User-Agent": UA}, timeout=30,
                     params={"q": q, "page_size": n, "license_type": "commercial,modification"})
    out = []
    for x in r.json().get("results", []):
        lic = f"{x.get('license', '')} {x.get('license_version', '')}".strip()
        out.append({"title": x.get("title"), "thumb": x.get("url"), "license": f"CC {lic}".upper().replace("CC CC0", "CC0"),
                    "author": (x.get("creator") or "")[:120], "page": x.get("foreign_landing_url"),
                    "w": x.get("width"), "h": x.get("height"), "allowed": True})
    return out


def save(url, out, meta):
    os.makedirs(IMG_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(CREDITS), exist_ok=True)
    for attempt in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
            r.raise_for_status()
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3)
    im = Image.open(io.BytesIO(r.content))
    im = ImageOps.exif_transpose(im).convert("RGB")
    im = ImageOps.fit(im, (600, 600), method=Image.LANCZOS, centering=(0.5, 0.5))
    path = f"{IMG_DIR}/{out}.jpg"
    im.save(path, "JPEG", quality=82, optimize=True, progressive=True)
    rec = {"file": f"{out}.jpg", **meta, "source_url": url}
    with open(CREDITS, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps({"saved": path, "bytes": os.path.getsize(path)}))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("--q", required=True)
    s.add_argument("--source", default="commons", choices=["commons", "openverse"]); s.add_argument("--n", type=int, default=8)
    v = sub.add_parser("save"); v.add_argument("--url", required=True); v.add_argument("--out", required=True)
    for k in ("title", "license", "author", "page", "category"):
        v.add_argument(f"--{k}", default="")
    a = ap.parse_args()
    if a.cmd == "search":
        res = search_commons(a.q, a.n) if a.source == "commons" else search_openverse(a.q, a.n)
        res = [dict(idx=i, **x) for i, x in enumerate(res) if x.get("thumb")]
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        if not (OK_LIC.match(a.license or "") and "nc" not in a.license.lower() and "nd" not in a.license.lower()):
            sys.exit(f"license not allowed: {a.license}")
        save(a.url, a.out, {"title": a.title, "license": a.license, "author": a.author, "page": a.page, "category": a.category})
        time.sleep(1)


if __name__ == "__main__":
    main()
