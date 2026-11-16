"""生成されたパックショット画像を後処理し、ブループリントの画像参照を更新する。

- $CATALOG_SCRATCH/gen_results_vertex.jsonl を読み込む
- 四隅からのフラッドフィルで背景を純白 (#FFFFFF) に統一
- 600x600 JPEG にリサイズし online-store-adk/static/img/products/<base_id>_p.jpg に保存
"""
import argparse
import glob
import json
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BP_DIR = os.environ.get("BLUEPRINT_DIR", f"{HERE}/blueprint")
IMG_DIR = os.environ.get("PRODUCT_IMAGES_DIR", f"{REPO_ROOT}/online-store-adk/static/img/products")
RES = os.path.join(os.environ.get("CATALOG_SCRATCH", "/tmp/cymbal_catalog_scratch"), "gen_results_vertex.jsonl")


def clean(path, out):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    for xy in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]:
        r, g, b = im.getpixel(xy)
        if min(r, g, b) > 200:
            ImageDraw.floodfill(im, xy, (255, 255, 255), thresh=22)
    im = im.resize((600, 600), Image.LANCZOS)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out, "JPEG", quality=85, optimize=True, progressive=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=RES)
    ap.add_argument("--keep-cc", action="store_true", help="CC 写真をサブ画像として残す")
    ap.add_argument("--glob", default="z_*.json", help="更新対象のブループリントファイルパターン")
    ap.add_argument("--overwrite", action="store_true", help="既存の 600x600 画像も再出力する")
    a = ap.parse_args()
    if a.results.endswith(".jsonl"):
        rows = [json.loads(l) for l in open(a.results, encoding="utf-8") if l.strip()]
    else:
        rows = json.load(open(a.results, encoding="utf-8"))
    res = {r["base_id"]: r for r in rows if r.get("ok") and r.get("path")}
    done, missing = 0, []
    for f in sorted(glob.glob(f"{BP_DIR}/{a.glob}")):
        bp = json.load(open(f, encoding="utf-8"))
        for it in bp["items"]:
            r = res.get(it["base_id"])
            if not r or not os.path.exists(r["path"]):
                if not os.path.exists(f"{IMG_DIR}/{it['base_id']}_p.jpg"):
                    missing.append(it["base_id"])
                continue
            out = f"{it['base_id']}_p.jpg"
            if a.overwrite or not os.path.exists(f"{IMG_DIR}/{out}"):
                clean(r["path"], f"{IMG_DIR}/{out}")
            cc = [x for x in it.get("images", []) if not x.endswith("_p.jpg")]
            it.setdefault("cc_images", cc)
            it["images"] = [out] + (it["cc_images"] if a.keep_cc else [])
            done += 1
        json.dump(bp, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"replaced": done, "missing": missing}, ensure_ascii=False))


if __name__ == "__main__":
    main()
