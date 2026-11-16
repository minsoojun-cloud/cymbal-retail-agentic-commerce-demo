"""Generate the fictional Cymbal sample documents used by 「資料から抽出」.

    python scripts/make_samples.py [--font /path/to/NotoSansJP-Regular.otf]

Outputs (samples/docs/):
  spec_cymbal_frypan_20cm.pdf      メーカー仕様書（フライパン 20cm, JAN 4954950777214）
  price_list_2026winter_nabe.xlsx  冬の鍋フェア 価格表（既存 JAN 4 行 + 新規 1 行）
  label_cymbal_carbonara.png       食品表示ラベル写真風（冷凍カルボナーラ, アレルギー表示枠付き）
All values are fictional demo data.
"""
from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "samples" / "docs"


def find_font(bold: bool = False) -> str:
    pats = ["~/.local/share/fonts/**/NotoSansJP-%s.otf" % ("Bold" if bold else "Regular"),
            "/usr/share/fonts/**/NotoSansCJK*-%s.tt*" % ("Bold" if bold else "Regular"),
            "/usr/share/fonts/**/DroidSansFallback*.ttf"]
    for p in pats:
        hits = glob.glob(os.path.expanduser(p), recursive=True)
        if hits:
            return hits[0]
    raise SystemExit("Japanese font not found; pass --font")


def make_pdf(path: Path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib.styles import ParagraphStyle

    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    F = "HeiseiKakuGo-W5"
    h1 = ParagraphStyle("h1", fontName=F, fontSize=17, leading=24, textColor=colors.HexColor("#1a73e8"))
    body = ParagraphStyle("b", fontName=F, fontSize=10, leading=16)
    small = ParagraphStyle("s", fontName=F, fontSize=8, leading=12, textColor=colors.HexColor("#5f6368"))
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm)
    rows = [["項目", "仕様"],
            ["商品名", "Cymbal ベーシック フッ素加工フライパン 20cm"],
            ["JANコード", "4954950777214"],
            ["品番", "CB-FP20"],
            ["サイズ", "直径20×深さ5.0cm（全長37.5cm）"],
            ["重量", "約480g"],
            ["素材", "本体：アルミニウム合金 / 内面：フッ素樹脂塗膜加工 / 外面：焼付塗装 / ハンドル：フェノール樹脂"],
            ["対応熱源", "IH対応（100V/200V）・ガス火対応"],
            ["食器洗い乾燥機", "使用できません（手洗いしてください）"],
            ["電子レンジ・オーブン", "使用できません"],
            ["生産国", "中国製"],
            ["販売者", "Cymbal Retail 株式会社（架空）"]]
    cell = ParagraphStyle("c", fontName=F, fontSize=9.5, leading=14)
    rows = [[Paragraph(a, cell), Paragraph(b, cell)] for a, b in rows]
    t = Table(rows, colWidths=[42 * mm, 132 * mm])
    t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), F), ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f0fe")),
                           ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#f8f9fa")),
                           ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dadce0")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story = [Paragraph("商品仕様書", h1), Paragraph("Cymbal ベーシック フッ素加工フライパン 20cm", body), Spacer(1, 6 * mm),
             Paragraph("毎日の目玉焼きや少量の炒め物にちょうどいい20cmサイズ。フッ素樹脂加工で焦げつきにくく、少ない油で調理できます。", body),
             Spacer(1, 5 * mm), t, Spacer(1, 6 * mm),
             Paragraph("ご使用上の注意：空焚きや強火での使用はフッ素樹脂加工の劣化の原因になります。IHでご使用の際は鍋底の直径12cm以上に対応した機種でお使いください。", body),
             Spacer(1, 10 * mm), Paragraph("※本資料はデモ用の架空データです（Cymbal Retail デモ）。", small)]
    doc.build(story)


def make_xlsx(path: Path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "冬の鍋フェア"
    ws.append(["2026 冬の鍋フェア 価格表（12/1〜1/15）"])
    ws.append([])
    ws.append(["JAN", "商品名", "内容量", "産地", "保存方法", "旬", "おすすめの鍋", "税込価格"])
    rows = [
        ["4913667472959", "茨城県産 白菜 1/2カット", "1/2カット", "茨城県産", "冷蔵", "11月〜2月", "寄せ鍋・キムチ鍋・水炊き", 198],
        ["4958688424846", "宮城県産 かき むき身 生食用 150g", "150g", "宮城県産", "要冷蔵（10℃以下）", "11月〜2月", "土手鍋・かき鍋", 798],
        ["4922835139112", "北海道産 ボイル毛がに 2尾セット（約800g）", "約800g", "北海道産", "冷凍（-18℃以下）", "12月〜3月", "かに鍋", 6980],
        ["4978886449342", "国産 ぶなしめじ 3パック（約300g）", "3パック（約300g）", "国産", "冷蔵", "9月〜12月", "寄せ鍋・すき焼き", 258],
        ["4990000000017", "Cymbal 鍋つゆ 寄せ鍋しょうゆ 750g（3〜4人前）", "750g", "国内製造", "常温", "", "寄せ鍋", 298],
    ]
    for r in rows:
        ws.append(r)
    ws["A1"].font = Font(bold=True, size=14, color="1A73E8")
    for c in ws[3]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="E8F0FE")
        c.alignment = Alignment(horizontal="center")
    for col, w in zip("ABCDEFGH", (16, 42, 18, 12, 18, 12, 22, 10)):
        ws.column_dimensions[col].width = w
    ws.append([])
    ws.append(["※デモ用の架空データです。新規 JAN 4990000000017 はカタログ未登録（新規登録の例）。"])
    wb.save(path)


def make_label(path: Path, font: str, bold: str):
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1100, 1250
    im = Image.new("RGB", (W, H), (250, 248, 242))
    d = ImageDraw.Draw(im)
    f = lambda s, b=False: ImageFont.truetype(bold if b else font, s)  # noqa: E731
    # package-ish header band
    d.rectangle([0, 0, W, 200], fill=(26, 115, 232))
    d.text((50, 40), "Cymbal ベーシック", font=f(34, True), fill="white")
    d.text((50, 95), "冷凍 カルボナーラ 260g", font=f(52, True), fill="white")
    d.text((W - 300, 140), "JAN 4911478160614", font=f(24), fill=(232, 240, 254))
    # 一括表示 table
    x0, y0, x1 = 50, 250, W - 50
    rows = [("名称", "冷凍パスタ（スパゲッティ）"),
            ("原材料名", "めん（デュラム小麦のセモリナ、食塩）、ソース（クリーム、\nベーコン、卵黄、チーズ、植物油脂、食塩、黒こしょう）／\n増粘剤（加工でん粉）、調味料（アミノ酸等）、乳化剤、\n（一部に小麦・卵・乳成分・大豆・豚肉を含む）"),
            ("内容量", "260g"),
            ("賞味期限", "枠外右下に記載（製造日より12ヶ月）"),
            ("保存方法", "-18℃以下で保存してください"),
            ("調理方法", "電子レンジ 600W 約5分30秒 / 500W 約6分30秒"),
            ("製造者", "Cymbal Retail 株式会社（架空）東京都港区…")]
    y = y0
    for k, v in rows:
        lines = v.split("\n")
        h = 22 + 40 * len(lines)
        d.rectangle([x0, y, x1, y + h], outline=(60, 64, 67), width=2)
        d.line([x0 + 200, y, x0 + 200, y + h], fill=(60, 64, 67), width=2)
        d.text((x0 + 18, y + 14), k, font=f(28, True), fill=(32, 33, 36))
        for i, ln in enumerate(lines):
            d.text((x0 + 220, y + 14 + i * 40), ln, font=f(25), fill=(32, 33, 36))
        y += h
    # allergen box
    y += 40
    d.rectangle([x0, y, x1, y + 190], outline=(217, 48, 37), width=5)
    d.rectangle([x0, y, x1, y + 56], fill=(217, 48, 37))
    d.text((x0 + 20, y + 8), "アレルギー表示（特定原材料等）", font=f(32, True), fill="white")
    d.text((x0 + 24, y + 78), "特定原材料：小麦・卵・乳成分・大豆・豚肉", font=f(36, True), fill=(32, 33, 36))
    d.text((x0 + 24, y + 134), "本品製造工場では、えび・かにを含む製品を生産しています。", font=f(24), fill=(95, 99, 104))
    d.text((x0, H - 60), "※デモ用の架空ラベルです（Cymbal Retail デモ）", font=f(22), fill=(128, 134, 139))
    im = im.rotate(1.2, expand=True, fillcolor=(235, 235, 235))   # slightly tilted like a photo
    im.save(path, "PNG", optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font")
    ap.add_argument("--bold-font")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    font = a.font or find_font(False)
    bold = a.bold_font or (find_font(True) if not a.font else a.font)
    make_pdf(OUT / "spec_cymbal_frypan_20cm.pdf")
    make_xlsx(OUT / "price_list_2026winter_nabe.xlsx")
    make_label(OUT / "label_cymbal_carbonara.png", font, bold)
    for p in sorted(OUT.iterdir()):
        print(p.name, p.stat().st_size)


if __name__ == "__main__":
    main()
