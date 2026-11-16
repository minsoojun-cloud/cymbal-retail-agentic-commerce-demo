"""Target (golden-record) attribute schema and Gemini responseSchema definitions — Cymbal Retail (grocery + GM)."""
from __future__ import annotations

from dataclasses import dataclass, field

# ── Category groups ──────────────────────────────────────────────────────────
CATEGORY_GROUPS = {
    "fresh": "生鮮（野菜・果物・肉・魚）",
    "prepared": "惣菜・冷凍・主食",
    "grocery": "加工食品・飲料",
    "kitchen": "キッチン・調理器具",
    "living": "日用品・生活雑貨",
    "beauty": "ビューティー",
    "pet": "ペット用品",
}
GROUP_SHORT = {"fresh": "生鮮", "prepared": "惣菜・冷凍", "grocery": "加工食品", "kitchen": "キッチン",
               "living": "日用品・雑貨", "beauty": "ビューティー", "pet": "ペット"}
FOOD_GROUPS = ("fresh", "prepared", "grocery")
GM_GROUPS = ("kitchen", "living", "beauty", "pet")

# Cymbal top categories (attributes.top_category / first segment of categories[0]) → group
TOP_CATEGORY_GROUP = {
    "野菜・果物": "fresh", "お肉・お肉加工品": "fresh", "お魚・水産加工品": "fresh",
    "冷凍食品・アイス": "prepared", "お惣菜・ミールキット": "prepared", "お米・麺・インスタント": "prepared",
    "調味料": "grocery", "缶詰・粉類・乾物": "grocery", "お菓子・製菓": "grocery", "卵・乳製品・豆乳・デザート": "grocery",
    "豆腐・納豆・練り物": "grocery", "飲料・水": "grocery", "パン・シリアル・ジャム・はちみつ": "grocery",
    "お酒・ノンアルコール": "grocery", "ベビー・キッズ食品": "grocery",
    "キッチン・調理器具": "kitchen", "日用品・キッチン消耗品": "living", "生活雑貨・インテリア": "living",
    "ビューティー・パーソナルケア": "beauty", "ペット用品": "pet",
}


def category_group(category_path: str) -> str:
    """Map a product category path ('A > B > C') or free text to a category group key."""
    p = category_path or ""
    top = p.split(">")[0].strip()
    if top in TOP_CATEGORY_GROUP:
        return TOP_CATEGORY_GROUP[top]
    for k, g in TOP_CATEGORY_GROUP.items():
        if k in p:
            return g
    # free-text fallbacks (CSV / document ingest)
    rules = (("pet", ("ペット", "犬", "猫", "ドッグ", "キャット")),
             ("beauty", ("化粧", "スキンケア", "シャンプー", "入浴剤", "ハンドクリーム", "コスメ", "ボディ")),
             ("kitchen", ("フライパン", "鍋", "包丁", "まな板", "保存容器", "調理器具", "キッチンツール", "食器")),
             ("living", ("洗剤", "ティッシュ", "スポンジ", "傘", "タオル", "収納", "雑貨", "日用品")),
             ("prepared", ("冷凍", "惣菜", "弁当", "ミールキット", "レトルト", "カップ麺", "インスタント", "米")),
             ("fresh", ("産 ", "鮮魚", "精肉", "野菜", "果物", "切り身", "尾", "玉")))
    for g, words in rules:
        if any(w in p for w in words):
            return g
    return "grocery"


@dataclass(frozen=True)
class AttrDef:
    key: str
    label: str
    type: str  # number | text | bool
    unit: str = ""
    kind: str = ""  # normalizer kind
    groups: tuple[str, ...] = FOOD_GROUPS
    limits: tuple[float, float] | None = None
    raw_keys: tuple[str, ...] = field(default_factory=tuple)  # source attribute keys that carry the same info
    hint: str = ""   # extraction hint shown to Gemini


ALL = FOOD_GROUPS + GM_GROUPS
ATTRS: list[AttrDef] = [
    # ── amount / size (normalised by Python) ───────────────────────────────
    AttrDef("net_weight_g", "内容量（重量）", "number", "g", "weight_g", FOOD_GROUPS + ("pet",), (1, 30000), ("size",),
            "g/kg 表記の内容量（例: 約240g、1kg、200g×3袋）"),
    AttrDef("net_volume_ml", "内容量・容量（ml）", "number", "ml", "volume_ml", ("grocery", "prepared", "kitchen", "living", "beauty"),
            (1, 30000), ("size", "capacity"), "ml/L 表記の内容量・容器容量（例: 500ml、1.8L、700ml×3個）"),
    AttrDef("pack_count", "入数", "number", "個", "count", ALL, (1, 500), ("size",),
            "個・本・枚・尾・切・玉・袋・食・パック・入 などの数量（例: 10個入、3切、5食入）"),
    AttrDef("servings", "目安人数（人前・皿分）", "number", "人前", "servings", ("prepared", "grocery"), (1, 50), (),
            "「4人前」「10皿分」など"),
    # ── food facts ─────────────────────────────────────────────────────────
    AttrDef("origin", "産地・原産国", "text", "", "origin", ALL, None, ("origin",), "「静岡県産」「国産」「アメリカ産」「日本製」など"),
    AttrDef("storage_method", "保存方法", "text", "", "storage", FOOD_GROUPS, None, ("storage_type",),
            "冷蔵 / 冷凍 / 常温 のいずれかに該当する記載（要冷蔵・冷凍食品・直射日光を避け常温 など）"),
    AttrDef("allergens", "特定原材料（アレルゲン）", "text", "", "allergens", FOOD_GROUPS + ("pet",), None, ("allergens",),
            "「特定原材料：」「アレルゲン」「アレルギー表示」の記載をそのまま転記。記載がなければ必ず not_found（推測禁止）"),
    AttrDef("best_before_days", "賞味期限目安", "number", "日", "days", ("prepared", "grocery"), (1, 3650), (),
            "「賞味期限：製造日より180日」「1年」など。記載がなければ not_found"),
    AttrDef("cook_time_min", "調理時間", "number", "分", "minutes", FOOD_GROUPS, (0.2, 600), (),
            "「レンジで約3分」「5分で完成」など調理・加熱の所要時間"),
    AttrDef("cooking_method", "調理方法", "text", "", "cooking", ("prepared", "grocery", "fresh"), None, (),
            "電子レンジ / フライパン / 湯せん / 鍋 / トースター / オーブン / そのまま など"),
    AttrDef("dishes", "用途・おすすめメニュー", "text", "", "list", FOOD_GROUPS, None, ("dishes",),
            "原文に書かれた料理名・用途（例: 照り焼き、ムニエル、お弁当）"),
    AttrDef("season", "旬の時期", "text", "", "months", ("fresh",), None, ("season_months",),
            "「旬」「秋の味覚」「10〜2月」などの時期の記載"),
    AttrDef("flavor", "味・辛さ", "text", "", "text", ("prepared", "grocery"), None, (),
            "「中辛」「塩味」「しょうゆ味」など"),
    # ── general merchandise ────────────────────────────────────────────────
    AttrDef("material", "素材", "text", "", "text", GM_GROUPS, None, ("material",), "「アルミニウム合金・フッ素樹脂加工」など"),
    AttrDef("width_cm", "幅", "number", "cm", "dim_w", ("kitchen", "living", "pet"), (0.5, 400), ("size",),
            "幅×奥行×高さ 表記はまとめてそのまま転記"),
    AttrDef("depth_cm", "奥行", "number", "cm", "dim_d", ("kitchen", "living", "pet"), (0.5, 400), ("size",), ""),
    AttrDef("height_cm", "高さ", "number", "cm", "dim_h", ("kitchen", "living", "pet"), (0.5, 400), ("size",), ""),
    AttrDef("diameter_cm", "直径・口径", "number", "cm", "diameter", ("kitchen",), (1, 100), ("size",), "「直径26cm」「26cm」など"),
    AttrDef("color", "カラー", "text", "", "text", GM_GROUPS, None, ("color",), ""),
    AttrDef("ih_compatible", "IH対応", "bool", "", "bool", ("kitchen",), None, (), "「IH対応」「ガス火専用」など"),
    AttrDef("dishwasher_safe", "食洗機対応", "bool", "", "bool", ("kitchen",), None, (), "「食洗機対応」「食洗機不可」など"),
    AttrDef("microwave_safe", "電子レンジ対応", "bool", "", "bool", ("kitchen",), None, (), ""),
    AttrDef("target_pet", "対象ペット", "text", "", "pet", ("pet",), None, (), "犬 / 猫 / 犬猫兼用 / 小動物"),
    AttrDef("target_age", "対象年齢・ライフステージ", "text", "", "text", ("pet",), None, (), "「成犬用」「7歳以上」「子猫」など"),
    AttrDef("scent", "香り", "text", "", "text", ("beauty", "living"), None, (), "「無香料」「せっけんの香り」など"),
    AttrDef("skin_type", "肌質・髪質", "text", "", "text", ("beauty",), None, (), "「敏感肌」「乾燥肌」「すべての肌質」など"),
]
ATTR_BY_KEY = {a.key: a for a in ATTRS}
ALL_ATTRIBUTE_KEYS = [a.key for a in ATTRS]


def attrs_for_group(group: str) -> list[AttrDef]:
    return [a for a in ATTRS if group in a.groups]


# ── 特定原材料 (food allergen labelling, Japan: 8 mandatory + 20 recommended = 28 items) ──
ALLERGENS_MANDATORY = ["えび", "かに", "くるみ", "小麦", "そば", "卵", "乳", "落花生"]
ALLERGENS_RECOMMENDED = ["アーモンド", "あわび", "いか", "いくら", "オレンジ", "カシューナッツ", "キウイフルーツ", "牛肉",
                         "ごま", "さけ", "さば", "大豆", "鶏肉", "バナナ", "豚肉", "まつたけ", "もも", "やまいも", "りんご",
                         "ゼラチン"]
ALLERGENS_28 = ALLERGENS_MANDATORY + ALLERGENS_RECOMMENDED
# spelling variants -> canonical
ALLERGEN_VARIANTS: dict[str, list[str]] = {
    "えび": ["えび", "エビ", "海老", "ｴﾋﾞ", "シュリンプ"], "かに": ["かに", "カニ", "蟹"], "くるみ": ["くるみ", "クルミ", "胡桃"],
    "小麦": ["小麦", "こむぎ"], "そば": ["そば", "ソバ", "蕎麦"], "卵": ["卵", "たまご", "玉子", "鶏卵"],
    "乳": ["乳", "乳成分", "乳製品", "牛乳"], "落花生": ["落花生", "ピーナッツ", "らっかせい"],
    "アーモンド": ["アーモンド"], "あわび": ["あわび", "アワビ", "鮑"], "いか": ["いか", "イカ", "烏賊"], "いくら": ["いくら", "イクラ"],
    "オレンジ": ["オレンジ"], "カシューナッツ": ["カシューナッツ"], "キウイフルーツ": ["キウイフルーツ", "キウイ"],
    "牛肉": ["牛肉"], "ごま": ["ごま", "ゴマ", "胡麻"], "さけ": ["さけ", "サケ", "鮭"], "さば": ["さば", "サバ", "鯖"],
    "大豆": ["大豆", "だいず"], "鶏肉": ["鶏肉", "とり肉"], "バナナ": ["バナナ"], "豚肉": ["豚肉", "ぶた肉"],
    "まつたけ": ["まつたけ", "マツタケ", "松茸"], "もも": ["もも", "モモ", "桃"], "やまいも": ["やまいも", "山芋", "ヤマイモ", "長芋"],
    "りんご": ["りんご", "リンゴ", "林檎"], "ゼラチン": ["ゼラチン"],
}

# ── Standard feature tag dictionary (Stage 3) ─────────────────────────────────
FEATURE_TAGS: dict[str, list[str]] = {
    "fresh": ["旬", "国産", "鮮度保証", "カット済み・下処理済み", "骨なし・食べやすい", "使い切りサイズ", "大容量・まとめ買い",
              "有機・オーガニック", "お弁当向き", "子どもに人気", "時短", "鍋向き", "焼肉・BBQ向き", "おもてなし"],
    "prepared": ["時短", "電子レンジ調理", "フライパン調理", "湯せん調理", "温めるだけ", "冷凍保存", "個包装", "お弁当向き",
                 "おつまみ", "子どもに人気", "国産原料", "減塩", "鍋向き", "おもてなし", "パーティー"],
    "grocery": ["国産原料", "減塩", "糖質オフ", "無添加", "有機・オーガニック", "個包装", "大容量・まとめ買い", "常温保存",
                "ギフト", "子どもに人気", "おつまみ", "朝食向き", "時短", "ご当地", "鍋向き"],
    "kitchen": ["IH対応", "ガス火対応", "食洗機対応", "電子レンジ対応", "冷凍対応", "オーブン対応", "こびりつきにくい", "軽量",
                "スタッキング", "日本製", "ギフト", "省スペース"],
    "living": ["日本製", "詰め替え用", "大容量・まとめ買い", "抗菌・防臭", "UVカット", "晴雨兼用", "洗える", "省スペース",
               "ギフト", "無香料", "軽量"],
    "beauty": ["無香料", "敏感肌向け", "保湿", "詰め替え用", "ギフト", "日本製", "オーガニック", "UVカット", "旅行用・ミニサイズ"],
    "pet": ["犬用", "猫用", "国産", "無添加", "シニア向け", "子犬・子猫向け", "洗える", "あったか", "ひんやり", "グレインフリー",
            "おやつ", "ギフト"],
}

# ── Gemini responseSchema (OpenAPI subset used by Vertex AI) ─────────────────


def stage1_schema(group: str) -> dict:
    keys = [a.key for a in attrs_for_group(group)]
    return {
        "type": "OBJECT",
        "properties": {
            "attributes": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "key": {"type": "STRING", "enum": keys},
                        "raw_value": {"type": "STRING", "description": "原文に書かれている値を単位込みでそのまま転記（換算しない）"},
                        "evidence": {"type": "STRING", "description": "根拠となる原文の連続した文字列を一字一句そのままコピー（40字以内）"},
                        "source_field": {"type": "STRING", "enum": ["title", "description", "attributes", "documents"]},
                        "confidence": {"type": "NUMBER", "description": "0.0〜1.0 の自己確信度"},
                    },
                    "required": ["key", "raw_value", "evidence", "source_field", "confidence"],
                },
            },
            "not_found": {"type": "ARRAY", "items": {"type": "STRING", "enum": keys},
                          "description": "原文に記載がなく抽出できなかった属性キー（推測で埋めない）"},
        },
        "required": ["attributes", "not_found"],
    }


def stage3_schema(group: str) -> dict:
    return {
        "type": "OBJECT",
        "properties": {
            "feature_tags": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "tag": {"type": "STRING", "enum": FEATURE_TAGS[group]},
                        "evidence": {"type": "STRING", "description": "根拠となる原文の文字列（一字一句コピー、40字以内）"},
                        "confidence": {"type": "NUMBER"},
                    },
                    "required": ["tag", "evidence", "confidence"],
                },
            },
            "search_keywords": {"type": "ARRAY", "items": {"type": "STRING"},
                                "description": "顧客が検索しそうな日本語キーワード（5〜8個、原文の事実に基づく）"},
            "ai_summary": {"type": "STRING", "description": "商品の特長を60〜90字で要約（原文にない事実は書かない）"},
        },
        "required": ["feature_tags", "search_keywords", "ai_summary"],
    }


def gmc_schema() -> dict:
    """Google Merchant Center Conversational Attributes schema (https://support.google.com/merchants/answer/17085370)."""
    return {
        "type": "OBJECT",
        "properties": {
            "item_group_id": {
                "type": "STRING",
                "description": "サイズ・入数・味などのバリエーション共通のグループID（原本属性 base_id があればそれをそのまま使う）",
            },
            "item_group_title": {
                "type": "STRING",
                "description": "商品グループのタイトル [item_group_title]（内容量・入数・色などを除いた共通名。例: Cymbal 白玉子）",
            },
            "variant_options": {
                "type": "ARRAY",
                "description": "バリエーション オプション [variant_option]（内容量・入数・サイズ・味・カラー・産地など name:value ペア）",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "name": {"type": "STRING", "description": "属性名（例: 内容量、入数、サイズ、味、カラー）"},
                        "value": {"type": "STRING", "description": "属性値（例: 400g、10個入、Mサイズ、中辛、ネイビー）"},
                        "evidence": {"type": "STRING", "description": "根拠となる原文の文字列（40字以内）"},
                    },
                    "required": ["name", "value", "evidence"],
                },
            },
            "questions_and_answers": {
                "type": "ARRAY",
                "description": "質問と回答 [question_and_answer]（購入検討者がAI検索で尋ねる具体的な質問と、原文の事実のみに基づく正確な回答 3〜5件）",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "question": {"type": "STRING", "description": "購入検討者からの自然な質問（？で終わる）"},
                        "answer": {"type": "STRING", "description": "原文の事実に基づく簡潔で正確な回答"},
                        "evidence": {"type": "STRING", "description": "回答の根拠となる原文の連続した文字列（一字一句コピー、40字以内）"},
                        "confidence": {"type": "NUMBER", "description": "0.0〜1.0 の自己確信度"},
                    },
                    "required": ["question", "answer", "evidence", "confidence"],
                },
            },
            "product_highlights": {
                "type": "ARRAY",
                "description": "商品に関する情報 [product_highlight]（主なセールスポイント 3〜5件、各40字以内）",
                "items": {"type": "STRING"},
            },
            "related_mentions": {
                "type": "ARRAY",
                "description": "関連商品 [related_product]（説明文中で一緒に使う食材・料理・別売品として明示されているもの）",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "relationship_type": {
                            "type": "STRING",
                            "enum": ["often_bought_with", "accessory", "required_part", "similar_to", "substitute"],
                        },
                        "identifier_type": {"type": "STRING", "enum": ["id", "mpn", "gtin"]},
                        "identifier": {"type": "STRING", "description": "商品ID・JAN（不明なら名称）"},
                        "title": {"type": "STRING", "description": "関連商品の名称"},
                    },
                    "required": ["relationship_type", "identifier_type", "identifier", "title"],
                },
            },
            "document_link": {
                "type": "STRING",
                "description": "ドキュメントリンク [document_link]（原文に PDF・取扱説明書の URL があれば記載、なければ空文字）",
            },
        },
        "required": [
            "item_group_id",
            "item_group_title",
            "variant_options",
            "questions_and_answers",
            "product_highlights",
            "related_mentions",
            "document_link",
        ],
    }
