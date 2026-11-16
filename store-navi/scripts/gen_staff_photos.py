"""Generate demo shelf photos for the Store Navi staff app (棚登録デモ, CONTRACT v9 slot labels) with Vertex AI Gemini + QA.

Each photo: a Japanese supermarket / drug-corner shelf section seen by a clerk's smartphone, with
  - the fixture number plate 「A01」 at the shelf end/header (real fixture ids from data/layouts/<store>.json v2), and
  - a clearly readable shelf-edge SLOT LABEL tag 「A01-203」 on the price rail directly under the target product
    (slot = <fixture>-<tier><NN>, 30 cm, NN left→right facing the fixture); the product spans `facings` slots.
The catalog packshot (online-store-adk/static/img/products/<base_id>_p.jpg) is a reference image for the package.

- generator : $GEN_MODEL (default gemini-3.1-flash-image, fallback gemini-2.5-flash-image) @ global
- QA        : $QA_MODEL (default gemini-3-flash-preview): slot label exact? plate exact? product visible/matching? tier?
              + target bounding box (used by the fallback)
- fallback  : after --attempts, a crisp PIL slot tag is drawn on the rail under the product box (and the plate if needed)
- output    : static/staff/demo_photos/<id>_<store>_<slot>.jpg (1024 px) + demo_photos.json
              {photos:[{id, file, store_id, fixture_id, slot_ids, tier, side, position, facings, product_id, hint,
                        seed_slot_ids, title, method, model, qa, gondola_id (=fixture_id)}]}
- products  : data/scenarios.json staff_photo_products (+ staff_photo_products_detail) ; target slots are chosen
              DIFFERENT from the seed shelf_locations slots so a demo registration visibly moves the product.

Usage:
  source ../config.env
  GOOGLE_CLOUD_QUOTA_PROJECT=$PROJECT_ID uv run --no-project --with google-genai --with pillow \
      python scripts/gen_staff_photos.py [--only ph01 ph03] [--attempts 4] [--dry-run] [--force] [--gcs]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import io
import json
import os
import random
import re
import sys
import threading
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAVI = ROOT / "store-navi"
DATA = NAVI / "data"
IMG_DIR = Path(os.environ.get("PRODUCT_IMAGES_DIR") or (ROOT / "online-store-adk" / "static" / "img" / "products"))
OUT_DIR = NAVI / "static" / "staff" / "demo_photos"
MANIFEST = OUT_DIR / "demo_photos.json"
CATALOG = Path(os.environ.get("DATA_FILE") or os.environ.get("CATALOG_JSONL") or (ROOT / "seed" / "catalog" / "products_retail.jsonl"))
SCRATCH = Path(os.environ.get("STAFF_PHOTO_SCRATCH", "/tmp/cymbal_staff_photos"))
PROJECT = os.environ.get("PROJECT_ID", "")
GEN_MODEL = os.environ.get("IMAGE_MODEL") or os.environ.get("GEN_MODEL") or "gemini-3.1-flash-image"
FALLBACK_GEN_MODEL = os.environ.get("FALLBACK_GEN_MODEL", "gemini-2.5-flash-image")
QA_MODEL = os.environ.get("QA_MODEL") or os.environ.get("GEMINI_MODEL") or "gemini-3.8-flash"
BUCKET = os.environ.get("STORE_NAVI_BUCKET") or os.environ.get("PHOTO_BUCKET") or (f"{PROJECT}-store-navi" if PROJECT else "cymbal-store-navi")
MAX_PHOTOS = 10

ORD = {1: "1st (bottom)", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th (top)", 6: "6th"}
FIXTURE_DESC = {
    "gondola": "a white metal gondola shelf (900 mm bays) with horizontal shelf boards",
    "wall": "a wall shelf unit with horizontal shelf boards",
    "endcap": "an end-cap display shelf",
    "multideck": "an open refrigerated multideck case with lit shelves",
    "reach_in": "a reach-in freezer with glass doors (photo taken with a door open)",
    "chest": "a low chest freezer seen from the front-top",
    "flat_table": "a low flat produce table",
    "deli_table": "a deli display table",
    "flower": "a flower stand",
    "counter": "a pharmacy counter back shelf",
}

_client = None
lock = threading.Lock()


def client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(vertexai=True, project=PROJECT, location="global")
    return _client


def with_retry(fn, tries=7):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # 429 / 5xx backoff
            msg = str(e)
            if any(k in msg for k in ("429", "RESOURCE_EXHAUSTED", "503", "500", "UNAVAILABLE", "DEADLINE")) and i < tries - 1:
                time.sleep(min(60, 4 * 2 ** i) + random.random() * 3)
                continue
            raise


# ------------------------------------------------------------------------------------------------ data
def load_catalog() -> dict[str, dict]:
    out = {}
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        p = json.loads(line)
        if p.get("type", "PRIMARY") not in ("PRIMARY", ""):
            continue
        attrs = {a["key"]: a["value"] for a in p.get("attributes") or []}
        base = (attrs.get("base_id") or {}).get("text", [""])[0]
        out[p["id"]] = {"id": p["id"], "title": p.get("title", ""), "category": (p.get("categories") or [""])[0],
                        "base_id": base, "brand": (p.get("brands") or [""])[0],
                        "drug_class": (attrs.get("drug_class") or {}).get("text", [""])[0],
                        "abuse_control": (attrs.get("abuse_control") or {}).get("text", ["false"])[0] == "true"}
    return out


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_layout(store_id: str) -> dict:
    return json.loads((DATA / "layouts" / f"{store_id}.json").read_text(encoding="utf-8"))


def fixtures_of(lay: dict) -> dict[str, dict]:
    out = {}
    for f in lay.get("fixtures") or []:
        f = dict(f)
        f["tiers"] = int(f.get("tiers") or 1)
        if not f.get("slots_per_tier"):
            f["slots_per_tier"] = max(1, round(float(f.get("length_cm") or 90) / float(f.get("slot_width_cm") or 30)))
        out[f["id"]] = f
    return out


def category_fixture(fx: dict[str, dict], category: str) -> dict | None:
    path = category.replace(" > ", ">")
    best, blen = None, -1
    for f in fx.values():
        for c in f.get("categories") or []:
            cc = str(c).replace(" > ", ">")
            if path.startswith(cc) and len(cc) > blen:
                best, blen = f, len(cc)
    return best


def packshot(prod: dict) -> Path | None:
    p = IMG_DIR / f"{prod['base_id']}_p.jpg"
    return p if prod.get("base_id") and p.exists() else None


def parse_slot(t: str):
    t = unicodedata.normalize("NFKC", t or "").upper()
    m = re.search(r"([A-Z]{1,2})\s*[-‐－ー―_ ]?\s*(\d{2})\s*[-‐－ー―_ ]\s*(\d)\s*(\d{2})", t)
    return (f"{m.group(1)}{m.group(2)}", int(m.group(3)), int(m.group(4))) if m else None


def sid(fid: str, tier: int, idx: int) -> str:
    return f"{fid}-{tier}{idx:02d}"


def load_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    return json.loads(MANIFEST.read_text(encoding="utf-8")).get("photos", [])


def choose_target(f: dict, seed_slots: list[str], want_facings: int, k: int, heavy: bool = False) -> tuple[int, int, int]:
    """(tier, start_idx, facings) on fixture f, not overlapping the seed slots (prefer another tier, golden zone)."""
    tiers, spt = int(f["tiers"]), int(f["slots_per_tier"])
    seed = [p for p in (parse_slot(s) for s in seed_slots) if p]
    seed_tier = seed[0][1] if seed else None
    seed_idx = {p[2] for p in seed}
    facings = max(1, min(want_facings, spt))
    order = [1, 2, 3] if heavy else ([3, 4, 2, 5, 1] if tiers >= 4 else list(range(tiers, 0, -1)))
    tier_pref = [t for t in order if t <= tiers]
    tier_pref = [t for t in tier_pref if t != seed_tier] + ([seed_tier] if seed_tier and seed_tier <= tiers else [])
    tier = tier_pref[k % max(1, min(2, len(tier_pref)))] if tier_pref else 1
    cands = list(range(2, spt - facings + 2)) or [1]
    cands.sort(key=lambda i: (abs(i - (spt + 1) / 2), i))
    for start in cands:
        rng = set(range(start, start + facings))
        if tier != seed_tier or not (rng & seed_idx):
            return tier, start, facings
    return tier, 1, facings


def build_jobs(cat: dict[str, dict]) -> list[dict]:
    seed: dict[tuple[str, str], dict] = {}
    for r in read_jsonl(DATA / "shelf_locations.jsonl"):
        k = (r["store_id"], r["product_id"])
        if k not in seed or str(r.get("registered_at", "")) >= str(seed[k].get("registered_at", "")):
            seed[k] = r
    scen = json.loads((DATA / "scenarios.json").read_text(encoding="utf-8")) if (DATA / "scenarios.json").exists() else {}
    detail = {d.get("product_id"): d for d in scen.get("staff_photo_products_detail") or [] if isinstance(d, dict)}
    specs = []
    for x in scen.get("staff_photo_products") or []:
        x = {"product_id": x} if isinstance(x, str) else dict(x)
        d = detail.get(x.get("product_id"), {})
        specs.append({"store_id": x.get("store_id") or d.get("store_id") or "S01", "product_id": x["product_id"],
                      "fixture_id": x.get("fixture_id") or d.get("fixture_id"), "hint": x.get("hint") or d.get("hint"),
                      "slot_ids": x.get("target_slot_ids") or d.get("target_slot_ids")})
    specs = specs[:MAX_PHOTOS]
    prev = {p.get("product_id"): p["id"] for p in load_manifest()}
    taken = {prev[s["product_id"]] for s in specs if s["product_id"] in prev}
    jobs = []
    for k, s in enumerate(specs):
        prod = cat.get(s["product_id"])
        if prod is None:
            print(f"[skip] {s['product_id']}: not in catalog", flush=True)
            continue
        lay = load_layout(s["store_id"])
        fx = fixtures_of(lay)
        sd = seed.get((s["store_id"], prod["id"])) or {}
        seed_slots = sd.get("slot_ids") or []
        if isinstance(seed_slots, str):
            seed_slots = json.loads(seed_slots)
        f = fx.get(s.get("fixture_id") or "") or fx.get(sd.get("fixture_id") or "") or category_fixture(fx, prod["category"])
        if f is None:
            print(f"[skip] {prod['id']}: no fixture in {s['store_id']}", flush=True)
            continue
        if s.get("slot_ids"):
            ps = [parse_slot(x) for x in s["slot_ids"]]
            tier, start, facings = ps[0][1], ps[0][2], len(ps)
        else:
            want = 1 if prod["category"].startswith("医薬品") or len(seed_slots) <= 1 and k % 2 else 2
            heavy = any(w in prod["category"] + prod["title"] for w in ("洗濯", "洗剤", "お米", "2L", "kg"))
            tier, start, facings = choose_target(f, seed_slots, want, k, heavy)
        slots = [sid(f["id"], tier, i) for i in range(start, start + facings)]
        pid = prev.get(prod["id"])
        if not pid:
            n = 1
            while f"ph{n:02d}" in taken:
                n += 1
            pid = f"ph{n:02d}"
        taken.add(pid)
        hint = s.get("hint") or prod["category"].split(">")[-1].strip()
        jobs.append({"id": pid, "store_id": s["store_id"], "fixture_id": f["id"], "fixture_type": f.get("type", "gondola"),
                     "fixture_label": f.get("label", ""), "tiers": int(f["tiers"]), "slots_per_tier": int(f["slots_per_tier"]),
                     "tier": tier, "position": start, "facings": facings, "slot_ids": slots, "seed_slot_ids": seed_slots,
                     "side": f.get("face"), "product_id": prod["id"], "title": prod["title"], "category": prod["category"],
                     "drug_class": prod["drug_class"], "hint": hint, "ref": str(packshot(prod) or "")})
    return jobs


# ------------------------------------------------------------------------------------------------ generation
def build_prompt(job: dict, feedback: str = "") -> str:
    plate, label = job["fixture_id"], job["slot_ids"][0]
    is_med = job["category"].startswith("医薬品")
    neighbours = ("other generic over-the-counter medicine boxes and bottles with plain, unbranded pastel packaging"
                  if is_med else "other generic products of similar categories with plain, unbranded packaging")
    span = ("exactly one 30 cm slot (2-3 small packages side by side)" if job["facings"] == 1
            else f"{job['facings']} adjacent 30 cm slots ({job['facings'] * 2}-{job['facings'] * 3} facings side by side)")
    fixture = FIXTURE_DESC.get(job["fixture_type"], FIXTURE_DESC["gondola"])
    p = f"""Photorealistic photo taken with a smartphone by a store clerk in a bright, clean Japanese supermarket with a
drugstore corner (Kansai food-market style). The camera faces {fixture} straight on at chest height, landscape 4:3,
close enough that the shelf-edge labels are legible; about 1.2 m of the fixture is visible.

FIXTURE PLATE: at the top-left end of the fixture, a rectangular sign, white with a thick Cymbal-blue (#1a73e8) border,
showing exactly "{plate}" in big bold black sans-serif characters (no hyphen, nothing else on the plate).

SLOT LABEL TAG (most important): every shelf has a white price rail along its front edge. Directly under the LEFT edge of the
target product, on the price rail of the {ORD.get(job['tier'], str(job['tier']))} shelf from the bottom (tier {job['tier']}
of {job['tiers']}), there is a white rectangular shelf-edge label tag (about 9 x 3.5 cm, clearly visible, front-facing,
sharp) printed with exactly "{label}" in large bold black monospace characters (letter, two digits, hyphen, three digits).
All other tags on the rails are small and BLANK (no text) so that "{label}" is the only readable tag.

TARGET PRODUCT: the product shown in the reference image — reproduce its package shape, colours and design faithfully —
displayed front-facing on that tier, occupying {span}, right above the "{label}" tag, well lit and the focus of the photo.
Product: {job['title']} (category {job['category'].split('>')[-1].strip()}).
Other shelves and slots hold {neighbours}. No real brand names or logos. No people, no hands, no carts.
Natural store lighting, slight realistic perspective, sharp focus, true-to-life colours."""
    if feedback:
        p += f"\nIMPORTANT — fix these problems from the previous attempt: {feedback}"
    return p


def _gen_once(prompt: str, ref: bytes | None, model: str) -> bytes | None:
    from google.genai import types
    contents = []
    if ref:
        contents.append(types.Part.from_bytes(data=ref, mime_type="image/jpeg"))
        contents.append("Reference image of the target product package (pure packshot):")
    contents.append(prompt)
    r = with_retry(lambda: client().models.generate_content(
        model=model, contents=contents,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"], image_config=types.ImageConfig(aspect_ratio="4:3"))))
    cands = getattr(r, "candidates", None) or []
    parts = (cands[0].content.parts if cands and cands[0].content else None) or []
    for part in parts:
        if part.inline_data and part.inline_data.data:
            return part.inline_data.data
    return None


def generate(prompt: str, ref: bytes | None) -> tuple[bytes | None, str]:
    try:
        return _gen_once(prompt, ref, GEN_MODEL), GEN_MODEL
    except Exception as e:
        if FALLBACK_GEN_MODEL and FALLBACK_GEN_MODEL != GEN_MODEL:
            print(f"  gen {GEN_MODEL} failed ({str(e)[:80]}), fallback {FALLBACK_GEN_MODEL}", flush=True)
            return _gen_once(prompt, ref, FALLBACK_GEN_MODEL), FALLBACK_GEN_MODEL
        raise


def norm_fixture(t: str) -> str:
    t = unicodedata.normalize("NFKC", t or "").upper().strip()
    m = re.search(r"([A-Z]{1,2})\s*-?\s*(\d{1,2})", t)
    return f"{m.group(1)}{int(m.group(2)):02d}" if m else t


def _mime(b: bytes) -> str:
    return "image/png" if b[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


def qa(img: bytes, job: dict, ref: bytes | None) -> dict:
    from google.genai import types
    q = (f"You are QA for demo photos of a Japanese store shelf. Image 1 is the generated shelf photo"
         f"{'; image 2 is the reference packshot of the target product' if ref else ''}.\n"
         f"Expected: fixture plate \"{job['fixture_id']}\"; shelf-edge slot label tag \"{job['slot_ids'][0]}\" directly under "
         f"the target product ({job['title']}) on tier {job['tier']} of {job['tiers']} (1 = bottom).\n"
         "Read EXACTLY what is printed (Latin letters/digits/hyphen) on the slot label tag under the target product and on the "
         "fixture plate. Check whether the target product (matching the reference package) is clearly visible, count its tier "
         "from the bottom, and whether there are people/hands or real-world brand logos. Also give the bounding box of the "
         "target product facings as [ymin, xmin, ymax, xmax] normalized 0-1000. "
         'Reply ONLY JSON: {"slot_label_text": str, "slot_label_readable": bool, "plate_text": str, "product_visible": bool, '
         '"product_matches_reference": bool, "product_tier": int, "people_or_real_logos": bool, "target_box": [int,int,int,int], '
         '"score": 0-10, "issues": "short English"}')
    contents = [types.Part.from_bytes(data=img, mime_type=_mime(img))]
    if ref:
        contents.append(types.Part.from_bytes(data=ref, mime_type="image/jpeg"))
    contents.append(q)
    r = with_retry(lambda: client().models.generate_content(
        model=QA_MODEL, contents=contents,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0)))
    try:
        d = json.loads(r.text)
    except Exception:
        return {"ok": False, "rank": 0, "issues": "unparseable QA"}
    ps = parse_slot(d.get("slot_label_text", ""))
    slot_ok = bool(ps) and sid(*ps) == job["slot_ids"][0]
    plate_ok = norm_fixture(d.get("plate_text", "")) == job["fixture_id"]
    prod_ok = bool(d.get("product_visible")) and bool(d.get("product_matches_reference", True))
    tier_ok = int(d.get("product_tier") or 0) == job["tier"]
    clean = not d.get("people_or_real_logos")
    d.update({"slot_ok": slot_ok, "plate_ok": plate_ok, "product_ok": prod_ok, "tier_ok": tier_ok, "clean": clean,
              "ok": slot_ok and prod_ok})
    d["rank"] = float(d.get("score") or 0) + (5 if slot_ok else 0) + (2 if plate_ok else 0) + (3 if prod_ok else 0) \
        + (1 if tier_ok else 0)
    return d


def feedback_of(d: dict, job: dict) -> str:
    out = []
    if not d.get("slot_ok"):
        out.append(f"the shelf-edge label tag under the target product must read exactly \"{job['slot_ids'][0]}\" in large bold "
                   f"characters and be clearly legible (QA read \"{d.get('slot_label_text', '')}\")")
    if not d.get("plate_ok"):
        out.append(f"the fixture plate must read exactly \"{job['fixture_id']}\" (QA read \"{d.get('plate_text', '')}\")")
    if not d.get("product_ok"):
        out.append("the target product from the reference image must be clearly visible and match the reference package")
    if not d.get("tier_ok"):
        out.append(f"put the target product on tier {job['tier']} counted from the bottom (QA saw tier {d.get('product_tier')})")
    if not d.get("clean"):
        out.append("remove people, hands and any real brand logos")
    if d.get("issues") and str(d["issues"]).lower() not in ("none", ""):
        out.append(str(d["issues"]))
    return "; ".join(out)


def to_jpeg(img: bytes, width: int = 1024) -> bytes:
    from PIL import Image
    im = Image.open(io.BytesIO(img)).convert("RGB")
    if im.width != width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88, optimize=True, progressive=True)
    return buf.getvalue()


def _font(d, text: str, max_w: float, size: int):
    from PIL import ImageFont
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        if os.path.exists(f):
            font = ImageFont.truetype(f, size)
            while d.textlength(text, font=font) > max_w and size > 8:
                size -= 1
                font = ImageFont.truetype(f, size)
            return font
    return ImageFont.load_default()


def _tag(d, x0: int, y0: int, w: int, h: int, text: str, border: str, bw: int):
    d.rounded_rectangle([x0 + 3, y0 + 4, x0 + w + 3, y0 + h + 4], radius=max(2, h // 8), fill=(0, 0, 0))
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=max(2, h // 8), fill="white", outline=border, width=bw)
    font = _font(d, text, w * .86, int(h * .66))
    bb = d.textbbox((0, 0), text, font=font)
    d.text((x0 + (w - (bb[2] - bb[0])) / 2 - bb[0], y0 + (h - (bb[3] - bb[1])) / 2 - bb[1]), text, fill="#202124", font=font)


def overlay(img: bytes, job: dict, d: dict, slot: bool, plate: bool) -> bytes:
    """Fallback: crisp slot tag on the rail just under the target box (and/or fixture plate at the top-left)."""
    from PIL import Image, ImageDraw
    im = Image.open(io.BytesIO(img)).convert("RGB")
    W, H = im.size
    dr = ImageDraw.Draw(im)
    if plate:
        _tag(dr, int(W * .03), int(H * .035), int(W * .16), int(H * .10), job["fixture_id"], "#1a73e8", max(4, H // 120))
    if slot:
        box = d.get("target_box") or [450, 380, 650, 620]
        try:
            ymin, xmin, ymax, xmax = [int(v) for v in box]
        except Exception:
            ymin, xmin, ymax, xmax = 450, 380, 650, 620
        tw, th = int(W * .17), int(H * .055)
        x0 = max(4, min(W - tw - 4, int(xmin / 1000 * W)))
        y0 = max(4, min(H - th - 4, int(ymax / 1000 * H) + 4))
        _tag(dr, x0, y0, tw, th, job["slot_ids"][0], "#5f6368", 2)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def process(job: dict, attempts: int) -> dict:
    ref = Path(job["ref"]).read_bytes() if job.get("ref") else None
    best, feedback, model_used = None, "", GEN_MODEL
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, attempts + 1):
        img, model_used = generate(build_prompt(job, feedback), ref)
        if not img:
            feedback = "no image returned"
            continue
        (SCRATCH / f"v9_{job['id']}_a{attempt}.{'png' if _mime(img) == 'image/png' else 'jpg'}").write_bytes(img)
        d = qa(img, job, ref)
        print(f"  {job['id']} a{attempt}: slot='{d.get('slot_label_text')}' ok={d.get('slot_ok')} plate='{d.get('plate_text')}' "
              f"prod={d.get('product_ok')} tier={d.get('product_tier')}/{job['tier']} score={d.get('score')} "
              f"{str(d.get('issues', ''))[:80]}", flush=True)
        if best is None or d["rank"] > best[1]["rank"]:
            best = (img, d, attempt)
        if d["ok"] and d.get("plate_ok") and d.get("tier_ok"):
            break
        if d["ok"] and attempt >= max(2, attempts - 1):
            break
        feedback = feedback_of(d, job)
    if best is None:
        return {**job, "ok": False, "note": "generation failed"}
    img, d, attempt = best
    method = "generated"
    if not d.get("slot_ok") or not d.get("plate_ok"):
        img = overlay(img, job, d, slot=not d.get("slot_ok"), plate=not d.get("plate_ok"))
        d2 = qa(img, job, ref)
        print(f"  {job['id']} overlay: slot='{d2.get('slot_label_text')}' ok={d2.get('slot_ok')} plate_ok={d2.get('plate_ok')}",
              flush=True)
        d, method = d2, "generated+overlay"
    jpg = to_jpeg(img)
    fname = f"{job['id']}_{job['store_id']}_{job['slot_ids'][0]}.jpg"
    (OUT_DIR / fname).write_bytes(jpg)
    return {**job, "ok": bool(d.get("ok")), "file": fname, "method": method, "attempts": attempt, "model": model_used,
            "qa": {k: d.get(k) for k in ("slot_label_text", "slot_ok", "plate_text", "plate_ok", "product_ok", "product_tier",
                                         "tier_ok", "clean", "score", "issues")}}


KEYS = ("id", "file", "store_id", "fixture_id", "slot_ids", "tier", "side", "position", "facings", "product_id", "hint",
        "seed_slot_ids", "title", "method", "model", "qa")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--attempts", type=int, default=4)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true", help="print the job list only")
    ap.add_argument("--force", action="store_true", help="regenerate photos that already passed QA")
    ap.add_argument("--gcs", action="store_true", help=f"also copy photos to gs://{BUCKET}/demo_photos/")
    a = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cat = load_catalog()
    all_jobs = build_jobs(cat)
    jobs = [j for j in all_jobs if not a.only or j["id"] in set(a.only)]
    for j in jobs:
        print(f"{j['id']} {j['store_id']} {j['fixture_id']}({j['fixture_type']}) {','.join(j['slot_ids'])} tier {j['tier']}/{j['tiers']} "
              f"seed={j['seed_slot_ids']} {j['product_id']} {j['title']} ref={'yes' if j['ref'] else 'NO'}", flush=True)
    if a.dry_run:
        return
    old = {p["id"]: p for p in load_manifest()}
    want = {j["id"]: j for j in all_jobs}
    if not a.only:  # prune photos for products no longer listed / v8 photos without slot ids
        for pid_, p in list(old.items()):
            w = want.get(pid_)
            if not w or w["product_id"] != p.get("product_id") or not p.get("slot_ids"):
                print(f"prune {pid_} ({p.get('title')})", flush=True)
                (OUT_DIR / p["file"]).unlink(missing_ok=True)
                old.pop(pid_)
    if not a.force:
        reuse = [j for j in jobs if j["id"] in old and old[j["id"]].get("product_id") == j["product_id"]
                 and (old[j["id"]].get("qa") or {}).get("slot_ok") and (OUT_DIR / old[j["id"]]["file"]).exists()]
        for j in reuse:
            print(f"reuse {j['id']} (already passed QA: {old[j['id']]['slot_ids']})", flush=True)
        jobs = [j for j in jobs if j not in reuse]
    results = []
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(process, j, a.attempts): j for j in jobs}
        for f in cf.as_completed(futs):
            try:
                results.append(f.result())
            except Exception as e:
                j = futs[f]
                print(f"[error] {j['id']}: {e}", flush=True)
                results.append({**j, "ok": False, "note": str(e)[:200]})
    for r in results:
        if r.get("file"):
            if r["id"] in old and old[r["id"]].get("file") != r["file"]:
                (OUT_DIR / old[r["id"]]["file"]).unlink(missing_ok=True)
            old[r["id"]] = {k: r.get(k) for k in KEYS} | {"gondola_id": r["fixture_id"]}
    photos = sorted(old.values(), key=lambda p: p["id"])
    MANIFEST.write_text(json.dumps({"version": 2, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "photos": photos},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    report = SCRATCH / f"v9_qa_report_{time.strftime('%H%M%S')}.json"
    report.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for r in results if r.get("ok"))
    print(f"done: {ok}/{len(results)} passed QA; manifest {MANIFEST} ({len(photos)} photos); report {report}", flush=True)
    if a.gcs:
        from google.cloud import storage
        b = storage.Client(project=PROJECT).bucket(BUCKET)
        for p in photos:
            b.blob(f"demo_photos/{p['file']}").upload_from_filename(str(OUT_DIR / p["file"]), content_type="image/jpeg")
        b.blob("demo_photos/demo_photos.json").upload_from_filename(str(MANIFEST), content_type="application/json")
        print(f"uploaded {len(photos)} photos to gs://{BUCKET}/demo_photos/", flush=True)


if __name__ == "__main__":
    sys.exit(main())
