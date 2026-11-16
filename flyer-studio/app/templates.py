"""Chirashi layout templates, frame shapes (including frame-overflowing cutouts), photo overlay modes, and palettes."""
from __future__ import annotations

import copy
import math
from typing import Any

FRAME_SHAPES = [
    {"id": "overflow_cutout", "label": "枠からはみ出す自由形（写真が枠外へ飛び出すダイナミック型）", "desc": "商品写真やバッジが枠線を越えて大きく飛び出すチラシ特有の迫力スタイル"},
    {"id": "rect", "label": "長方形（標準グリッド枠）", "desc": "すっきり整列した直四角形の定番枠"},
    {"id": "cutout", "label": "自由形コラージュ（切り抜き）", "desc": "商品写真を大きく配置し、価格とバッジを重ねるスタイル"},
    {"id": "burst", "label": "爆弾・超特ギザギザ強調", "desc": "赤・黄ギザギザ台座と放射背景で目玉価格を強烈に訴求"},
    {"id": "vertical", "label": "縦型カード（写真上＋情報下）", "desc": "上部に商品写真、下部に商品名と大きな価格を配置する構成"},
    {"id": "horizontal", "label": "横ワイド長方形（写真左＋大価格右）", "desc": "横長スペースを活かして写真と特大価格を並べる構成"},
    {"id": "circle", "label": "丸型スポット（円形・ワンポイント）", "desc": "円形フレームに商品を収め、価格バッジを添える構成"},
    {"id": "tilted", "label": "斜めポップ強調枠", "desc": "枠や写真を少し傾けて動きとライブ感を出すPOPスタイル"},
    {"id": "rounded", "label": "角丸プレミアムカード", "desc": "白背景の角丸カードで清潔感・信頼感を高める構成"},
]

LAYOUT_MODES = [
    {"id": "overlay_full", "label": "写真全面＋写真の上に説明・価格を重ねて表示（王道オーバーレイ）"},
    {"id": "overlay_price", "label": "写真大＋写真の上に価格を重ねる（説明は帯表示）"},
    {"id": "overflow_frame", "label": "枠からはみ出す特大写真＋重ね価格・説明"},
    {"id": "split_vertical", "label": "上下分割（写真上・説明と価格下）"},
    {"id": "split_horizontal", "label": "左右分割（写真左・説明と価格右）"},
]

OVERLAY_POSITIONS = [
    {"id": "bottom_split", "label": "左下・下部に説明＋右下に価格を重ねる（標準）"},
    {"id": "top_text_bottom_price", "label": "上部に説明帯＋右下に特大価格を重ねる"},
    {"id": "right_stack", "label": "右側に説明と価格を縦に重ねる"},
]

SLOT_SPANS = [
    {"id": "auto", "label": "自動（ゾーン内で隙間なく最適配分）", "w": 0, "h": 0},
    {"id": "hero_2x2", "label": "特大ヒーロー（2×2・4マス相当）", "w": 2, "h": 2},
    {"id": "wide_2x1", "label": "横ワイド長方形（2×1・2マス相当）", "w": 2, "h": 1},
    {"id": "tall_1x2", "label": "縦ロング長方形（1×2・2マス相当）", "w": 1, "h": 2},
    {"id": "std_1x1", "label": "標準（1×1・1マス相当）", "w": 1, "h": 1},
]

NUMERAL_STYLES = [
    {"id": "graphic_pop", "label": "立体POP絵文字数字（赤＋白黒二重フチ・立体影）"},
    {"id": "yellow_pop", "label": "超特イエローPOP数字（赤黒台座＋黄色立体数字）"},
    {"id": "gothic_bold", "label": "標準ゴシック太字数字（すっきり高視認性）"},
    {"id": "mincho_premium", "label": "上質明朝・セリフ数字（百貨店・高品質トーン）"},
]

PRICE_STYLES = [
    {"id": "dual", "label": "本体＋税込併記（標準）"},
    {"id": "was_now", "label": "通常価格 → 特別価格"},
    {"id": "percent_off", "label": "○%OFF 強調"},
    {"id": "uniform", "label": "均一価格（ゾーン共通）"},
    {"id": "bundle", "label": "よりどりまとめ売り"},
]

BADGE_PRESETS = [
    "超特!!",
    "超目玉",
    "特価",
    "広告の品",
    "旬",
    "日替り",
    "半額",
    "新米",
    "地産地消",
    "お1人様2点限り",
    "数量限定",
    "タイムサービス",
    "人気商品",
]

SLOT_BG_PALETTES = [
    {"id": "auto", "label": "✨ 商品に合う背景画像を自動合成（推奨）", "color": ""},
    {"id": "bg:ocean_ice", "label": "🐟 鮮魚・クラッシュアイス背景画像", "color": "#eef8ff"},
    {"id": "bg:autumn_wood", "label": "🍁 秋の味覚・紅葉と木目テーブル背景画像", "color": "#fff8e7"},
    {"id": "bg:fresh_farm", "label": "🥬 朝採れ青果・グリーン＆水滴背景画像", "color": "#f1f8e9"},
    {"id": "bg:meat_gold", "label": "🥩 精肉・プレミアム金箔和紙背景画像", "color": "#fff3f0"},
    {"id": "bg:nabe_steam", "label": "🍲 あったか鍋・惣菜の和食卓背景画像", "color": "#fff6e5"},
    {"id": "bg:harvest_pantry", "label": "🌾 お米・調味料の黄金稲穂＆木目背景画像", "color": "#fffde7"},
    {"id": "bg:dairy_morning", "label": "🥛 日配・ベーカリーの朝陽ボケ背景画像", "color": "#fffdf2"},
    {"id": "bg:sale_burst", "label": "💥 大特売・赤黄サンバースト背景画像", "color": "#fff9c4"},
    {"id": "cream", "label": "単色：特売ウォームクリーム", "color": "#fffde7"},
    {"id": "leaf", "label": "単色：青果フレッシュグリーン", "color": "#f1f8e9"},
    {"id": "meat", "label": "単色：精肉ウォームローズ", "color": "#fff3f0"},
    {"id": "ocean", "label": "単色：鮮魚マリンアイスブルー", "color": "#eef8ff"},
    {"id": "deli", "label": "単色：惣菜・秋穫アンバー", "color": "#fff6e5"},
    {"id": "white", "label": "単色：クリーン純白", "color": "#ffffff"},
    {"id": "dark", "label": "単色：黒生鮮プレミアム", "color": "#263238"},
]

PAPER_FORMATS = [
    {"id": "B4-landscape", "label": "B4 横（折込チラシ標準・364×257mm）", "width_mm": 364, "height_mm": 257, "aspect": "364 / 257"},
    {"id": "B4-portrait", "label": "B4 縦（257×364mm）", "width_mm": 257, "height_mm": 364, "aspect": "257 / 364"},
    {"id": "A4-landscape", "label": "A4 横（297×210mm）", "width_mm": 297, "height_mm": 210, "aspect": "297 / 210"},
    {"id": "A4-portrait", "label": "A4 縦（210×297mm）", "width_mm": 210, "height_mm": 297, "aspect": "210 / 297"},
]


def harmonize_category_bg(category: str, role: str = "grid") -> str:
    """Return a soft background color that harmonizes with the product's food/merchandise category."""
    c = category or ""
    if "野菜" in c or "果物" in c:
        return "#e8f5e9" if role == "hero" else "#f4fbf1"
    if "お肉" in c:
        return "#ffebee" if role == "hero" else "#fff5f3"
    if "お魚" in c or "水産" in c:
        return "#e3f2fd" if role == "hero" else "#f1f8fe"
    if "卵" in c or "乳製品" in c or "豆腐" in c or "パン" in c:
        return "#fff8e1" if role == "hero" else "#fffdf2"
    if "お惣菜" in c or "冷凍" in c or "お米" in c:
        return "#fff3e0" if role == "hero" else "#fffaf2"
    if "お酒" in c or "飲料" in c or "お菓子" in c:
        return "#fce4ec" if role == "hero" else "#fff9fb"
    return "#fffde7" if role == "hero" else "#ffffff"


BASE_TEMPLATES: dict[str, dict[str, Any]] = {
    "T1": {
        "id": "T1",
        "name": "日替りコラージュ＆均一祭（写真重ね王道型）",
        "survey_type": "A: 枠はみ出し目玉＋写真オーバーレイ価格＋均一ブロック型",
        "description": "目玉商品は枠からはみ出す特大写真の上に説明と立体POP価格を重ね、一般枠も隙間なく配置する最も反響の高い王道構成です。",
        "paper": "B4-landscape",
        "default_tone": "にぎやか",
        "default_numeral_style": "graphic_pop",
        "default_layout_mode": "overlay_full",
        "default_item_count": 20,
        "recommended_range": [6, 60],
        "bg_image_url": "",
        "slot_overrides": {},
        "zones": [
            {
                "id": "day1",
                "title": "11/11(水)限り 超特!! オープン目玉",
                "subtitle": "1家族様1点限り！バイヤー厳選の朝一番超特価",
                "zone_type": "day_hero",
                "frame_color": "red",
                "weight": 1.35,
                "bg_image_url": "",
                "categories": ["野菜・果物", "お肉・お肉加工品", "お魚・水産加工品", "卵・乳製品・豆乳・デザート"],
                "hero_count": 2,
                "grid_count": 4,
                "hero_shape": "overflow_cutout",
                "grid_shape": "rect",
                "hero_layout_mode": "overlay_full",
                "grid_layout_mode": "overlay_price",
                "default_badge": "超特!!",
            },
            {
                "id": "day2",
                "title": "11/12(木)・13(金)限り 日替り連続超特価",
                "subtitle": "生鮮から定番グロサリーまで毎日がお買得",
                "zone_type": "day_block",
                "frame_color": "blue",
                "weight": 1.15,
                "bg_image_url": "",
                "categories": ["お肉・お肉加工品", "お魚・水産加工品", "お惣菜・ミールキット", "調味料"],
                "hero_count": 2,
                "grid_count": 3,
                "hero_shape": "overflow_cutout",
                "grid_shape": "rect",
                "hero_layout_mode": "overlay_full",
                "grid_layout_mode": "overlay_price",
                "default_badge": "日替り",
            },
            {
                "id": "kinitsu",
                "title": "11/12(木)▶13(金) 大均市 99円均一（税込106.92円）",
                "subtitle": "新鮮野菜・きのこ・日配・パン・お菓子までどれでも99円均一！",
                "zone_type": "uniform_price",
                "frame_color": "green",
                "weight": 1.0,
                "bg_image_url": "",
                "uniform_price_ex": 99,
                "uniform_price_inc": 107,
                "categories": ["野菜・果物", "豆腐・納豆・練り物", "お菓子・製菓", "パン・シリアル・ジャム・はちみつ"],
                "hero_count": 1,
                "grid_count": 4,
                "hero_shape": "burst",
                "grid_shape": "overflow_cutout",
                "hero_layout_mode": "overlay_full",
                "grid_layout_mode": "overlay_full",
                "default_badge": "人気の品!",
            },
            {
                "id": "weekly",
                "title": "よりどり・まとめ買い＆くらし応援大特価",
                "subtitle": "新米・冷凍食品・調味料・飲料の週間特別奉仕",
                "zone_type": "weekly_grid",
                "frame_color": "orange",
                "weight": 0.9,
                "bg_image_url": "",
                "categories": ["お米・麺・インスタント", "冷凍食品・アイス", "調味料", "飲料・水", "日用品・キッチン消耗品"],
                "hero_count": 1,
                "grid_count": 3,
                "hero_shape": "horizontal",
                "grid_shape": "rect",
                "hero_layout_mode": "overlay_price",
                "grid_layout_mode": "overlay_price",
                "default_badge": "特価",
            },
        ],
    },
    "T2": {
        "id": "T2",
        "name": "号外セール・厳選おすすめグリッド（長方形整列型）",
        "survey_type": "B: 号外セール＋整然長方形カードグリッド型",
        "description": "左側に枠からはみ出す超目玉品を配置し、右側に食品・日配・飲料の長方形カードを隙間なく整然と並べる高視認構成です。",
        "paper": "B4-landscape",
        "default_tone": "にぎやか",
        "default_numeral_style": "graphic_pop",
        "default_layout_mode": "overlay_price",
        "default_item_count": 20,
        "recommended_range": [6, 56],
        "bg_image_url": "",
        "slot_overrides": {},
        "zones": [
            {
                "id": "ichi_hero",
                "title": "店舗限定 号外セール！厳選おすすめ超目玉",
                "subtitle": "皆様へ感謝の気持ちを価格に！広告対象品はチラシ掲載品のみ",
                "zone_type": "market_hero",
                "frame_color": "navy",
                "weight": 1.25,
                "bg_image_url": "",
                "categories": ["卵・乳製品・豆乳・デザート", "お肉・お肉加工品", "冷凍食品・アイス", "野菜・果物"],
                "hero_count": 2,
                "grid_count": 6,
                "hero_shape": "burst",
                "grid_shape": "rect",
                "hero_layout_mode": "overlay_full",
                "grid_layout_mode": "overlay_price",
                "default_badge": "超目玉",
            },
            {
                "id": "yoridori",
                "title": "食品・パン・お菓子・日配 大放出コーナー",
                "subtitle": "まとめ買いに嬉しい定番人気商品を限界価格で",
                "zone_type": "bundle_block",
                "frame_color": "red",
                "weight": 1.1,
                "bg_image_url": "",
                "categories": ["お米・麺・インスタント", "調味料", "パン・シリアル・ジャム・はちみつ", "お菓子・製菓"],
                "hero_count": 1,
                "grid_count": 5,
                "hero_shape": "overflow_cutout",
                "grid_shape": "rect",
                "hero_layout_mode": "overlay_full",
                "grid_layout_mode": "overlay_price",
                "default_badge": "お1人様2点限り",
            },
            {
                "id": "stock_up",
                "title": "冷蔵・冷凍・飲料・お酒 お買い得セレクション",
                "subtitle": "毎日の食卓と晩酌を応援する特別プライス",
                "zone_type": "weekly_grid",
                "frame_color": "blue",
                "weight": 1.0,
                "bg_image_url": "",
                "categories": ["冷凍食品・アイス", "飲料・水", "お酒・ノンアルコール", "お惣菜・ミールキット"],
                "hero_count": 1,
                "grid_count": 5,
                "hero_shape": "horizontal",
                "grid_shape": "rect",
                "hero_layout_mode": "overlay_price",
                "grid_layout_mode": "overlay_price",
                "default_badge": "特価",
            },
        ],
    },
    "T3": {
        "id": "T3",
        "name": "テーマ・献立提案（旬・背景ビジュアル＆写真重ね型）",
        "survey_type": "C: 季節テーマ・写真全面オーバーレイ＆献立提案型",
        "description": "「秋の味覚」「旬の野菜」「あったか鍋」など、背景ビジュアルと写真全面オーバーレイでシズル感を最大限に引き出す特集型紙面です。",
        "paper": "B4-landscape",
        "default_tone": "上質",
        "default_numeral_style": "graphic_pop",
        "default_layout_mode": "overlay_full",
        "default_item_count": 16,
        "recommended_range": [6, 40],
        "bg_image_url": "",
        "slot_overrides": {},
        "zones": [
            {
                "id": "theme_hero",
                "title": "旬を味わう！今週の主役食材（産地直送）",
                "subtitle": "バイヤーが産地・鮮度にこだわった季節のメイン食材",
                "zone_type": "theme_hero",
                "frame_color": "autumn",
                "weight": 1.3,
                "bg_image_url": "",
                "categories": ["野菜・果物", "お魚・水産加工品", "お肉・お肉加工品"],
                "hero_count": 2,
                "grid_count": 4,
                "hero_shape": "overflow_cutout",
                "grid_shape": "cutout",
                "hero_layout_mode": "overlay_full",
                "grid_layout_mode": "overlay_full",
                "default_badge": "旬",
            },
            {
                "id": "menu_set",
                "title": "今夜の献立まるごと提案！一緒に揃える関連食材",
                "subtitle": "メイン料理を引き立てる副菜・つゆ・調味料・新米",
                "zone_type": "menu_proposal",
                "frame_color": "green",
                "weight": 1.0,
                "bg_image_url": "",
                "categories": ["豆腐・納豆・練り物", "調味料", "お米・麺・インスタント", "野菜・果物"],
                "hero_count": 1,
                "grid_count": 4,
                "hero_shape": "overflow_cutout",
                "grid_shape": "rounded",
                "hero_layout_mode": "overlay_full",
                "grid_layout_mode": "overlay_price",
                "default_badge": "地産地消",
            },
            {
                "id": "deli_sweet",
                "title": "食卓を彩る出来立てお惣菜＆季節のスイーツ・晩酌",
                "subtitle": "忙しい日にも嬉しい名物デリカと食後の楽しみ",
                "zone_type": "weekly_grid",
                "frame_color": "gold",
                "weight": 1.0,
                "bg_image_url": "",
                "categories": ["お惣菜・ミールキット", "卵・乳製品・豆乳・デザート", "お菓子・製菓", "お酒・ノンアルコール"],
                "hero_count": 1,
                "grid_count": 4,
                "hero_shape": "circle",
                "grid_shape": "rounded",
                "hero_layout_mode": "overlay_full",
                "grid_layout_mode": "overlay_price",
                "default_badge": "人気商品",
            },
        ],
    },
    "T4": {
        "id": "T4",
        "name": "すっきりEDLP・生協カード型",
        "survey_type": "D: 整然グリッド・EDLP型（オーケー・ルミエール・生協カード構成）",
        "description": "角丸カードと整然としたグリッドで商品の特徴・産地・納得価格を分かりやすく伝える信頼感重視の構成です。",
        "paper": "B4-portrait",
        "default_tone": "すっきり",
        "default_numeral_style": "gothic_bold",
        "default_layout_mode": "overlay_price",
        "default_item_count": 15,
        "recommended_range": [6, 45],
        "bg_image_url": "",
        "slot_overrides": {},
        "zones": [
            {
                "id": "edlp_fresh",
                "title": "毎日の食卓に安心・新鮮！生鮮おすすめ品",
                "subtitle": "産地と品質を厳選した青果・精肉・鮮魚",
                "zone_type": "card_grid",
                "frame_color": "green",
                "weight": 1.1,
                "bg_image_url": "",
                "categories": ["野菜・果物", "お肉・お肉加工品", "お魚・水産加工品"],
                "hero_count": 2,
                "grid_count": 3,
                "hero_shape": "horizontal",
                "grid_shape": "rounded",
                "hero_layout_mode": "overlay_price",
                "grid_layout_mode": "overlay_price",
                "default_badge": "地産地消",
            },
            {
                "id": "edlp_daily",
                "title": "いつでも納得価格！日配・冷蔵の定番品",
                "subtitle": "たまご・牛乳・豆腐・お惣菜など毎日使う必需品",
                "zone_type": "card_grid",
                "frame_color": "blue",
                "weight": 1.0,
                "bg_image_url": "",
                "categories": ["卵・乳製品・豆乳・デザート", "豆腐・納豆・練り物", "お惣菜・ミールキット", "パン・シリアル・ジャム・はちみつ"],
                "hero_count": 1,
                "grid_count": 4,
                "hero_shape": "rounded",
                "grid_shape": "rounded",
                "hero_layout_mode": "overlay_price",
                "grid_layout_mode": "overlay_price",
                "default_badge": "特価",
            },
            {
                "id": "edlp_pantry",
                "title": "くらしの定番・まとめ買いグロサリー＆生活用品",
                "subtitle": "お米・冷凍食品・調味料・日用品までエブリデイロープライス",
                "zone_type": "card_grid",
                "frame_color": "navy",
                "weight": 1.0,
                "bg_image_url": "",
                "categories": ["お米・麺・インスタント", "冷凍食品・アイス", "調味料", "日用品・キッチン消耗品"],
                "hero_count": 1,
                "grid_count": 4,
                "hero_shape": "rounded",
                "grid_shape": "rounded",
                "hero_layout_mode": "overlay_price",
                "grid_layout_mode": "overlay_price",
                "default_badge": "広告の品",
            },
        ],
    },
}


def recommend_template_id(theme: str, tone: str = "") -> str:
    t = f"{theme or ''} {tone or ''}"
    if any(k in t for k in ("号外", "市", "爆安", "衝撃", "限界", "祭り")):
        return "T2"
    if any(k in t for k in ("特集", "フェア", "旬", "味覚", "鍋", "献立", "メニュー", "新米", "秋", "冬", "上質")):
        return "T3"
    if any(k in t for k in ("すっきり", "EDLP", "毎日", "生協", "コープ", "定番")):
        return "T4"
    return "T1"


def build_template_slots(
    template: dict[str, Any],
    item_count: int | None = None,
    zone_counts: dict[str, int] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    """Expand a template into concrete slots, applying per-zone defaults and per-slot overrides (`slot_overrides`)."""
    tpl = copy.deepcopy(template)
    zones = tpl.get("zones") or []
    if not zones:
        return tpl, [], None

    slot_overrides: dict[str, dict[str, Any]] = tpl.get("slot_overrides") or {}
    base_totals = [max(1, int(z.get("hero_count", 0)) + int(z.get("grid_count", 1))) for z in zones]
    base_sum = sum(base_totals) or 1

    if zone_counts:
        target_totals = [max(0, int(zone_counts.get(z["id"], base_totals[i]))) for i, z in enumerate(zones)]
        if sum(target_totals) == 0:
            target_totals = base_totals
    elif item_count is not None and int(item_count) > 0:
        req = max(1, int(item_count))
        if req < len(zones):
            zones = zones[:req]
            tpl["zones"] = zones
            target_totals = [1] * req
        else:
            raw = [req * (b / base_sum) for b in base_totals]
            target_totals = [max(1, int(math.floor(x))) for x in raw]
            rem = req - sum(target_totals)
            order = sorted(range(len(zones)), key=lambda i: (raw[i] - target_totals[i], base_totals[i]), reverse=True)
            for idx in order[: max(0, rem)]:
                target_totals[idx] += 1
    else:
        target_totals = base_totals

    default_num_style = tpl.get("default_numeral_style") or "graphic_pop"
    default_layout_mode = tpl.get("default_layout_mode") or "overlay_full"
    flat_slots: list[dict[str, Any]] = []
    active_zones: list[dict[str, Any]] = []

    for z_idx, z in enumerate(zones):
        tot = target_totals[z_idx]
        if tot <= 0:
            continue
        base_hero = int(z.get("hero_count", 1))
        if tot == 1:
            hero_n, grid_n = 1, 0
        elif tot <= 3:
            hero_n = min(1, base_hero)
            grid_n = tot - hero_n
        else:
            hero_n = min(base_hero, max(1, tot // 3)) if base_hero > 0 else 0
            grid_n = max(0, tot - hero_n)

        z["hero_count"] = hero_n
        z["grid_count"] = grid_n
        z_slots: list[dict[str, Any]] = []
        z_overrides = z.get("slot_overrides") or {}

        for h in range(hero_n):
            sid = f"{z['id']}-hero-{h + 1}"
            h_shape = z.get("hero_shape") or ("overflow_cutout" if h == 0 else "burst")
            if h == 1 and h_shape == "overflow_cutout" and tot >= 5:
                h_shape = "burst"
            h_layout = z.get("hero_layout_mode") or default_layout_mode
            slot = {
                "slot_id": sid,
                "zone_id": z["id"],
                "zone_title": z["title"],
                "role": "hero",
                "size": "hero" if h == 0 else "L",
                "size_span": "hero_2x2" if h == 0 else "wide_2x1",
                "width_weight": 1.8 if h == 0 else 1.4,
                "row_weight": 1.4,
                "img_scale": 122 if h_shape == "overflow_cutout" else 110,
                "shape": h_shape,
                "layout_mode": h_layout,
                "overlay_pos": "bottom_split",
                "numeral_style": "yellow_pop" if h_shape == "burst" else default_num_style,
                "bg_color": "auto",
                "bg_image_url": z.get("bg_image_url") or "",
                "price_style": "uniform" if z.get("zone_type") == "uniform_price" else "dual",
                "default_badge": z.get("default_badge", "超特!!"),
                "categories": z.get("categories") or [],
            }
            ov = {**(slot_overrides.get(sid) or {}), **(z_overrides.get(sid) or {})}
            if ov:
                slot.update(ov)
            z_slots.append(slot)
            flat_slots.append(slot)

        for g in range(grid_n):
            sid = f"{z['id']}-grid-{g + 1}"
            g_shape = z.get("grid_shape") or "rect"
            g_layout = z.get("grid_layout_mode") or "overlay_price"
            slot = {
                "slot_id": sid,
                "zone_id": z["id"],
                "zone_title": z["title"],
                "role": "grid",
                "size": "M" if tot <= 16 else ("S" if tot <= 36 else "XS"),
                "size_span": "auto",
                "width_weight": 1.0,
                "row_weight": 1.0,
                "img_scale": 115 if g_shape == "overflow_cutout" else 100,
                "shape": g_shape,
                "layout_mode": g_layout,
                "overlay_pos": "bottom_split",
                "numeral_style": default_num_style,
                "bg_color": "auto",
                "bg_image_url": "",
                "price_style": "uniform" if z.get("zone_type") == "uniform_price" else "dual",
                "default_badge": z.get("default_badge", "特価"),
                "categories": z.get("categories") or [],
            }
            ov = {**(slot_overrides.get(sid) or {}), **(z_overrides.get(sid) or {})}
            if ov:
                slot.update(ov)
            z_slots.append(slot)
            flat_slots.append(slot)

        z["slots"] = z_slots
        active_zones.append(z)

    tpl["zones"] = active_zones
    total_items = len(flat_slots)
    tpl["resolved_item_count"] = total_items
    warning = None
    if total_items > 60:
        warning = f"掲載商品数が {total_items} 点のため、文字重なり防止の自動縮小レイアウトを適用しています。"
    return tpl, flat_slots, warning
