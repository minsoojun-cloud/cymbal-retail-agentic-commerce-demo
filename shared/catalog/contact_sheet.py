"""目視 QA 用に商品画像サムネイルのコンタクトシート（グリッド画像）を生成する。"""
import glob
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
IMG_DIR = os.environ.get("PRODUCT_IMAGES_DIR", os.path.join(REPO_ROOT, "online-store-adk/static/img/products"))
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "/tmp/cr_sheets"
prefix = sys.argv[1] if len(sys.argv) > 1 else ""
os.makedirs(OUT_DIR, exist_ok=True)
files = sorted(f for f in glob.glob(f"{IMG_DIR}/{prefix}*.jpg"))
COLS, T, LABEL = 8, 170, 16
per = COLS * 6
for page in range(0, len(files), per):
    chunk = files[page:page + per]
    rows = (len(chunk) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * T, rows * (T + LABEL)), "white")
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(chunk):
        im = Image.open(f).convert("RGB").resize((T - 4, T - 4))
        x, y = (i % COLS) * T, (i // COLS) * (T + LABEL)
        sheet.paste(im, (x + 2, y + 2))
        d.text((x + 3, y + T - 1), os.path.basename(f)[:-4][:27], fill="black")
    out = f"{OUT_DIR}/{prefix or 'all'}_{page // per + 1}.jpg"
    sheet.save(out, quality=80)
    print(out, len(chunk))
