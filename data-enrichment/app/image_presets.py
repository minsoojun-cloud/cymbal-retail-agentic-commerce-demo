"""Seasonal / promotional image presets and rule-based availability ("only if the product has the evidence").

Availability is decided by rules only (approved attributes, approved feature tags, raw catalog attributes and
keyword evidence in the source text) – deterministic, fast and explainable. Gemini is not used here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .normalizer import parse_months
from .prompts import source_text
from .rules import FINAL_OK
from .schema import ATTR_BY_KEY, FOOD_GROUPS

ALL_GROUPS = frozenset({"fresh", "prepared", "grocery", "kitchen", "living", "beauty", "pet"})
FOOD = frozenset(FOOD_GROUPS)
SEASON_LABEL = {"spring": "春", "summer": "夏", "autumn": "秋", "winter": "冬", "yearend": "年末年始",
                "newlife": "新生活", "all": "通年"}


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    season: str
    icon: str
    groups: frozenset
    prompt: str
    attrs: tuple[str, ...] = ()        # approved golden attribute keys that satisfy the requirement
    raw_keys: tuple[str, ...] = ()     # raw catalog attribute keys that satisfy the requirement (non-empty)
    raw_true: tuple[str, ...] = ()     # raw catalog attribute keys whose value must be "true"
    tags: tuple[str, ...] = ()         # approved feature tags that satisfy the requirement
    months: tuple[int, ...] = ()       # season months (approved `season` or raw season_months) overlapping these
    text_regex: str = ""               # keyword evidence in the source text
    attr_max: tuple[str, float] | None = None   # approved numeric attribute <= value (e.g. cook_time_min <= 15)
    facts: tuple[str, ...] = ()        # verified spec keys allowed in the image text
    need_label: str = ""               # used in the "not available" reason
    always: bool = False               # no requirement

    @property
    def requires_any(self) -> bool:
        return not self.always


PRESETS: list[Preset] = [
    Preset("autumn-taste", "秋の味覚", "autumn", "🍁", FOOD,
           "実りの秋の食卓。木のテーブルに紅葉や栗・きのこなど秋の小物、温かみのあるオレンジと茶色のトーン。旬の食材のおいしさが伝わる写真。",
           months=(9, 10, 11), tags=("旬",),
           text_regex=r"秋|新米|栗|さんま|秋鮭|きのこ|しめじ|まいたけ|さつまいも|かぼちゃ|柿|梨|りんご|ぶどう|紅葉",
           facts=("season", "origin"), need_label="秋の旬・秋の味覚"),
    Preset("winter-nabe", "冬：鍋", "winter", "🍲", FOOD | {"kitchen"},
           "寒い冬の夜、湯気の立つ土鍋を家族で囲むあたたかな食卓。湯気と柔らかな電球色の光、ほっとする雰囲気。",
           tags=("鍋向き",), text_regex=r"鍋|しゃぶしゃぶ|すき焼|おでん|水炊き|ちゃんこ",
           facts=("net_weight_g", "origin"), need_label="鍋料理・鍋での利用"),
    Preset("yearend", "年末年始", "yearend", "🎍", FOOD | {"beauty", "living"},
           "お正月・年末の華やかな食卓。紅白・金のアクセント、松や水引など和の正月飾り。家族や親戚が集まる晴れの日の雰囲気。",
           months=(12, 1), tags=("おもてなし", "ギフト", "パーティー"),
           text_regex=r"年末年始|お正月|正月|おせち|年越し|お雑煮|お歳暮|クリスマス|冬のご挨拶|ギフト",
           need_label="年末年始・ギフト・行事"),
    Preset("newlife", "新生活", "newlife", "🌸", frozenset({"kitchen", "living", "prepared", "grocery", "beauty"}),
           "春の新生活。桜の季節、明るく片付いたワンルームや新居のキッチン。若草色と白のさわやかなトーン。",
           tags=("省スペース", "スタッキング", "時短", "使い切りサイズ", "お弁当向き"),
           text_regex=r"新生活|一人暮らし|ひとり暮らし|お弁当|作り置き|収納|省スペース|コンパクト",
           need_label="新生活・一人暮らし・お弁当"),
    Preset("summer-cool", "夏：冷やし", "summer", "🧊", FOOD | {"kitchen"},
           "夏の涼しげな食卓。ガラスの器・氷・水滴、青と白の爽やかなトーン、明るい日差し。",
           months=(6, 7, 8), tags=("ひんやり",),
           text_regex=r"冷やし|冷たい|冷やして|そうめん|冷麺|ざる|アイス|かき氷|麦茶|水出し|ひんやり|夏",
           need_label="冷やして食べる・夏向け"),
    Preset("quick-dinner", "平日：時短ごはん", "all", "⏱️", FOOD,
           "平日の夕方、手早く整った夕食の食卓。共働き家族のキッチン、明るく清潔感のある写真。",
           tags=("時短", "電子レンジ調理", "温めるだけ"), attr_max=("cook_time_min", 15),
           text_regex=r"時短|レンジで|温めるだけ|焼くだけ|すぐに|手軽|カット済",
           facts=("cook_time_min",), need_label="時短調理（調理時間・レンジ調理）"),
    Preset("ec-white", "EC用：白背景", "all", "⬜", ALL_GROUPS,
           "純白の背景、商品を中央に大きく配置、柔らかい接地影。EC 商品ページ用のクリーンな商品写真。", always=True),
    Preset("lifestyle", "ライフスタイル", "all", "🏠", ALL_GROUPS,
           "日本の一般的な家庭のダイニング・キッチン・リビングで自然に使われているシーン。明るく清潔感のある写真。", always=True),
    Preset("sale", "セール", "all", "🏷️", ALL_GROUPS,
           "スーパーのチラシ・特売コーナー風の明るく元気な背景（Cymbal ブルー #1a73e8 と赤・黄色のアクセント）。商品は中央で大きく。価格の数字は描かない。",
           raw_true=("on_sale",), raw_keys=("promo_text",), text_regex=r"特価|セール|タイムセール|おトク",
           need_label="セール・特価（on_sale / 販促文）"),
]
PRESET_BY_ID = {p.id: p for p in PRESETS}


def _approved(recs: list[dict]) -> tuple[dict[str, dict], set[str]]:
    attrs = {r["attr_key"]: r for r in recs if r.get("kind") == "attribute" and r.get("gate_status") in FINAL_OK
             and r.get("value") not in (None, "", False)}
    tags = {str(r.get("value")) for r in recs if r.get("kind") == "tag" and r.get("gate_status") in FINAL_OK}
    return attrs, tags


def _fmt(rec: dict) -> str:
    v = rec.get("value")
    if isinstance(v, bool):
        return "あり" if v else "なし"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    unit = rec.get("unit") or ""
    return f"{v} {unit}".strip()


def verified_facts(keys: tuple[str, ...], recs: list[dict]) -> list[dict]:
    attrs, _ = _approved(recs)
    out = []
    for k in keys:
        if k in attrs:
            d = ATTR_BY_KEY.get(k)
            out.append({"key": k, "label": d.label if d else k, "value": _fmt(attrs[k])})
    return out


def evidence_view(product: dict) -> dict:
    """Product copy without internal catalog keys that are not product evidence."""
    raw = {k: v for k, v in (product.get("raw_attributes") or {}).items()
           if k not in ("base_id", "top_category", "price_tax_excluded", "original_price_tax_excluded", "discount_rate",
                        "is_food", "is_seasonal")}
    return {**product, "raw_attributes": raw}


def _months_of(product: dict, attrs: dict) -> list[int]:
    if "season" in attrs:
        return parse_months(str(attrs["season"].get("value") or "")) or []
    raw = str((product.get("raw_attributes") or {}).get("season_months") or "")
    return parse_months(raw) or [] if raw else []


def evaluate_one(pr: Preset, product: dict, recs: list[dict]) -> dict:
    attrs, tags = _approved(recs)
    raw = product.get("raw_attributes") or {}
    evidence, ok = "", pr.always
    if not ok:
        hit_tag = next((t for t in pr.tags if t in tags), None)
        hit_attr = next((k for k in pr.attrs if k in attrs), None)
        hit_true = next((k for k in pr.raw_true if str(raw.get(k) or "").strip().lower() == "true"), None)
        hit_raw = next((k for k in pr.raw_keys if str(raw.get(k) or "").strip()), None)
        months = _months_of(product, attrs) if pr.months else []
        hit_month = sorted(set(months) & set(pr.months))
        hit_max = None
        if pr.attr_max and pr.attr_max[0] in attrs:
            v = attrs[pr.attr_max[0]].get("value")
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v <= pr.attr_max[1]:
                hit_max = pr.attr_max[0]
        if hit_tag:
            ok, evidence = True, f"承認済みタグ「{hit_tag}」"
        elif hit_true:
            ok, evidence = True, f"{hit_true}: true" + (f"（{str(raw.get('promo_text'))[:30]}）" if raw.get("promo_text") else "")
        elif hit_month:
            ok, evidence = True, f"旬の時期 {'・'.join(str(m) for m in months)}月（{'・'.join(str(m) for m in hit_month)}月が該当）"
        elif hit_max:
            d = ATTR_BY_KEY.get(hit_max)
            ok, evidence = True, f"{d.label if d else hit_max} {_fmt(attrs[hit_max])}"
        elif hit_attr:
            d = ATTR_BY_KEY.get(hit_attr)
            ok, evidence = True, f"{d.label if d else hit_attr} {_fmt(attrs[hit_attr])}"
        elif hit_raw:
            ok, evidence = True, f"{hit_raw}: {str(raw[hit_raw])[:40]}"
        elif pr.text_regex:
            # category paths are not product evidence
            src = "\n".join(l for l in source_text(evidence_view(product)).splitlines() if not l.startswith("【カテゴリ】"))
            m = re.search(pr.text_regex, src)
            if m:
                s, e = max(0, m.start() - 12), min(len(src), m.end() + 12)
                ok, evidence = True, src[s:e].replace("\n", " ").strip()
    return {
        "id": pr.id, "label": pr.label, "season": pr.season, "season_label": SEASON_LABEL.get(pr.season, ""),
        "icon": pr.icon, "available": ok,
        "reason": "" if ok else f"この商品には{pr.need_label}に関する根拠がありません",
        "evidence": evidence, "facts": [{"label": f["label"], "value": f["value"]} for f in verified_facts(pr.facts, recs)],
        "prompt": pr.prompt,
    }


def evaluate(product: dict, recs: list[dict]) -> list[dict]:
    g = product.get("group") or "grocery"
    return [evaluate_one(p, product, recs) for p in PRESETS if g in p.groups]
