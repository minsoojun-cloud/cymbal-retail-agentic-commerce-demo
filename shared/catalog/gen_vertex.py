"""Vertex AI で商品パックショット画像（食品・日用品・一般雑貨）を生成し自動 QA を実施するスクリプト。

- 生成モデル : $IMAGE_MODEL / $GEN_MODEL（既定 gemini-3.1-flash-image、フォールバック gemini-2.5-flash-image）
- 検証モデル : $QA_MODEL / $GEMINI_MODEL（既定 gemini-3.8-flash → gemini-3-flash-preview）
- 再試行回数 : 1 アイテムあたり最大 MAX_ATTEMPTS 回
- 再開可能   : 結果を $CATALOG_SCRATCH/gen_results_vertex.jsonl に追記し完了済み base_id をスキップ

使い方:
  source ../../install/config.env
  GOOGLE_CLOUD_QUOTA_PROJECT=$PROJECT_ID uv run --no-project --with google-genai python gen_vertex.py \
      --blueprints blueprint/z_*.json [--workers 6]
  python3 apply_packshots.py   # -> 600x600 JPEG を online-store-adk/static/img/products/ に出力
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import random
import threading
import time

from google import genai
from google.genai import types

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PROJECT = os.environ.get("PROJECT_ID", "")
LOCATION = os.environ.get("GEMINI_LOCATION", "global")
SCRATCH = os.environ.get("CATALOG_SCRATCH", "/tmp/cymbal_catalog_scratch")
OUT_DIR = f"{SCRATCH}/vertex_gen"
RESULTS = f"{SCRATCH}/gen_results_vertex.jsonl"
IMG_DIR = os.environ.get("PRODUCT_IMAGES_DIR", f"{REPO_ROOT}/online-store-adk/static/img/products")
GEN_MODEL = os.environ.get("IMAGE_MODEL") or os.environ.get("GEN_MODEL") or "gemini-3.1-flash-image"
FALLBACK_GEN_MODEL = os.environ.get("FALLBACK_GEN_MODEL", "gemini-2.5-flash-image")
QA_MODEL = os.environ.get("QA_MODEL") or os.environ.get("GEMINI_MODEL") or "gemini-3-flash-preview"
MAX_ATTEMPTS = 5

STYLE = """Photorealistic e-commerce product photo (packshot) for a Japanese online supermarket (fresh food, groceries, deli,
daily goods, kitchenware, beauty & personal care, pet supplies, home & living). Single product (or a neat set when the product is a set), shot from a
pleasing 3/4 front angle, centered, filling about 70-85% of the frame, on a PURE WHITE seamless background, bright even softbox
lighting, soft natural shadow, sharp focus, true-to-life colors and materials. No people, no hands, no animals, no room interior,
no table, no props unrelated to the product. Fresh produce, meat and fish are shown as sold in a Japanese supermarket (loose,
bunched, in a net, or in a clear-film-wrapped tray); deli dishes in a takeaway container or on a plain white plate.
ABSOLUTELY NO TEXT anywhere: no letters, no Japanese characters, no numbers, no logos, no brand marks, no barcodes, no prices.
Bottles, tubes, bags and boxes must have plain BLANK labels or simple abstract color design without any writing."""

_client = None
lock = threading.Lock()


def get_client():
    global _client
    if _client is None:
        project = os.environ.get("PROJECT_ID") or PROJECT
        if not project:
            raise RuntimeError("PROJECT_ID 環境変数を設定してください（例: source install/config.env）")
        _client = genai.Client(vertexai=True, project=project, location=LOCATION)
    return _client


def with_retry(fn, tries=8):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            if any(k in msg for k in ("429", "RESOURCE_EXHAUSTED", "503", "500", "UNAVAILABLE", "DEADLINE")) and i < tries - 1:
                time.sleep(min(60, 4 * 2 ** i) + random.random() * 3)
                continue
            raise


def build_prompt(it, feedback=""):
    p = (STYLE + f"\n\nProduct: {' / '.join(it['example_titles'])}\nCategory: {it['category']}\n"
         f"Scene: {it.get('image_brief') or ''}\n"
         "Override: ignore any surface, furniture, shelf, floor, fabric or colored background mentioned in the scene — the "
         "product always stands alone on a pure white seamless background.")
    if feedback:
        p += f"\nIMPORTANT — fix these problems from the previous attempt: {feedback}"
    return p


def generate(prompt):
    try:
        return _generate(prompt, GEN_MODEL)
    except Exception:
        if FALLBACK_GEN_MODEL and FALLBACK_GEN_MODEL != GEN_MODEL:
            return _generate(prompt, FALLBACK_GEN_MODEL)
        raise


def _generate(prompt, model):
    client = get_client()
    r = with_retry(lambda: client.models.generate_content(
        model=model, contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"], image_config=types.ImageConfig(aspect_ratio="1:1"))))
    cands = getattr(r, "candidates", None) or []
    parts = (cands[0].content.parts if cands and cands[0].content else None) or []
    for part in parts:
        if part.inline_data and part.inline_data.data:
            return part.inline_data.data
    return None


def verify(img, it):
    client = get_client()
    q = (f"You are QA for product photos of a Japanese online supermarket. Intended product: {' / '.join(it['example_titles'][:2])}. "
         f"Intended scene: {it.get('image_brief') or ''}\n"
         "Check: (1) the image clearly shows this product (correct item type, plausible materials/shape; packaged goods in realistic retail packaging); (2) there is NO visible text "
         "at all — no letters, kana, kanji, numbers or logo-like writing anywhere (tiny illegible texture is acceptable only if it does not look "
         "like characters); (3) background is a pure white seamless studio backdrop — FAIL if any floor, table, wooden surface, tiles, stone, fabric, shelf or colored backdrop is visible behind the product (packaging that is part of the product, e.g. a food tray, takeaway container, net or plain white plate, is fine); (4) no people, hands, animals, room interior. Be strict on (1) and (2). "
         'Reply ONLY JSON: {"ok": true|false, "score": 0-10, "issues": "short reason in English"}')
    r = with_retry(lambda: client.models.generate_content(
        model=QA_MODEL, contents=[types.Part.from_bytes(data=img, mime_type="image/png"), q],
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0)))
    try:
        d = json.loads(r.text)
        return bool(d.get("ok")), float(d.get("score", 0)), str(d.get("issues", ""))
    except Exception:
        return False, 0.0, "unparseable QA"


def process(it):
    best, feedback = None, ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        img = generate(build_prompt(it, feedback))
        if not img:
            feedback = "no image returned"; continue
        ok, score, issues = verify(img, it)
        if best is None or score > best[1]:
            best = (img, score, issues, attempt)
        if ok and score >= 7:
            break
        feedback = issues
    if best is None:
        return {"base_id": it["base_id"], "path": "", "ok": False, "note": "generation failed"}
    path = f"{OUT_DIR}/{it['base_id']}.png"
    open(path, "wb").write(best[0])
    return {"base_id": it["base_id"], "path": path, "ok": True, "score": best[1], "attempts": best[3],
            "note": best[2] or "passed QA"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items")
    ap.add_argument("--blueprints", nargs="*", default=[])
    ap.add_argument("--force", action="store_true", help="also regenerate items whose image already exists")
    ap.add_argument("--only", nargs="*", default=[], help="restrict to these base_ids (implies regeneration)")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    items = json.load(open(a.items, encoding="utf-8")) if a.items else []
    for bpf in a.blueprints:
        for it in json.load(open(bpf, encoding="utf-8"))["items"]:
            if not a.force and not a.only and os.path.exists(f"{IMG_DIR}/{it['base_id']}_p.jpg"):
                continue
            items.append({"base_id": it["base_id"], "example_titles": [v["title"] for v in it["variants"][:3]],
                          "category": " > ".join(it["category_path"]), "image_brief": it.get("image_brief", "")})
    if a.only:
        items = [x for x in items if x["base_id"] in set(a.only)]
    done = set()
    if os.path.exists(RESULTS) and not a.only:
        done = {json.loads(l)["base_id"] for l in open(RESULTS, encoding="utf-8") if json.loads(l).get("ok")}
    todo = [x for x in items if x["base_id"] not in done]
    print(f"items={len(items)} done={len(done)} todo={len(todo)}", flush=True)
    t0, n = time.time(), 0
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for res in ex.map(lambda x: _safe(x), todo):
            n += 1
            with lock, open(RESULTS, "a", encoding="utf-8") as f:
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
            print(f"[{n}/{len(todo)} {time.time()-t0:.0f}s] {res['base_id']} ok={res['ok']} "
                  f"score={res.get('score')} att={res.get('attempts')} {res.get('note','')[:80]}", flush=True)


def _safe(it):
    try:
        return process(it)
    except Exception as e:
        return {"base_id": it["base_id"], "path": "", "ok": False, "note": f"error: {e}"[:200]}


if __name__ == "__main__":
    main()
