"""Stage 2: deterministic unit normalization (Cymbal Retail: grocery + general merchandise).

The LLM only transcribes raw values (「3切（約240g）」「幅45×奥行45×高さ40cm」「特定原材料：えび・小麦」); all unit
conversions happen here in plain Python so that the result is reproducible and auditable
(抽出と単位正規化の分離).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .schema import ALLERGEN_VARIANTS, ALLERGENS_28, ATTR_BY_KEY

NUM = r"(\d+(?:\.\d+)?)"
COUNTERS = r"(個|本|枚|尾|切れ?|玉|袋|食|パック|入り?|缶|粒|株|束|房|杯|包|組|セット|足|巻|尻|匹|台|P|p)"


@dataclass
class NormResult:
    value: Any
    unit: str
    ok: bool
    note: str = ""


def clean(raw: str) -> str:
    s = unicodedata.normalize("NFKC", str(raw or ""))
    s = s.replace(",", "")
    s = re.sub(r"(約|およそ|最大|最長|≒|程度|目安)", "", s)
    s = s.replace("～", "~").replace("〜", "~").replace("ー~", "~")
    s = s.replace("×", "x").replace("*", "x").replace("X", "x")
    return s.strip()


def _first_number(s: str) -> float | None:
    m = re.search(NUM, s)
    return float(m.group(1)) if m else None


def _num(v: float) -> float | int:
    return int(v) if float(v).is_integer() else round(v, 2)


# ── amounts ──────────────────────────────────────────────────────────────────

def parse_weight_g(s: str) -> tuple[float, str] | None:
    """'3切(約240g)' -> 240, '1kg' -> 1000, '200gx3袋' -> 600 (合算), '400g' -> 400."""
    m = re.search(NUM + r"\s*(kg|g)(?![a-wyz])\s*x\s*(\d+)\s*" + COUNTERS + "?", s, re.I)
    if m:
        unit_g = float(m.group(1)) * (1000 if m.group(2).lower() == "kg" else 1)
        n = int(m.group(3))
        return round(unit_g * n, 1), f"{_num(unit_g)}g×{n} を合算"
    m = re.search(NUM + r"\s*(kg|g)(?![a-wyz])", s, re.I)
    if not m:
        return None
    v = float(m.group(1)) * (1000 if m.group(2).lower() == "kg" else 1)
    return round(v, 1), ("kg を g に換算" if m.group(2).lower() == "kg" else "")


def parse_volume_ml(s: str) -> tuple[float, str] | None:
    """'1.8L' -> 1800, '500mlx24本' -> 500 (1本あたり), '700mlx3個' -> 700."""
    m = re.search(NUM + r"\s*(ml|mL|ML|l|L|ℓ|リットル|cc)(?![a-wyz])", s)
    if not m:
        return None
    u = m.group(2).lower()
    v = float(m.group(1)) * (1 if u in ("ml", "cc") else 1000)
    note = "L を ml に換算" if u not in ("ml", "cc") else ""
    if re.search(re.escape(m.group(0)) + r"\s*x\s*\d+", s):
        note = (note + "・" if note else "") + "1個あたりの容量（×n は入数）"
    return round(v, 1), note


def parse_count(s: str) -> tuple[int, str] | None:
    """'10個入' -> 10, '3切(約240g)' -> 3, '200gx3食' -> 3, '5食入' -> 5, '2尾' -> 2."""
    m = re.search(r"x\s*(\d+)\s*" + COUNTERS, s)
    if m:
        return int(m.group(1)), "×n 表記の入数"
    m = re.search(r"(\d+)\s*" + COUNTERS, s)
    if m:
        return int(m.group(1)), ""
    m = re.fullmatch(r"\s*(\d+)\s*", s)
    if m:
        return int(m.group(1)), "単位なし数値を入数とみなしました"
    return None


def parse_servings(s: str) -> float | None:
    m = re.search(NUM + r"\s*(人前|人分|皿分|食分|人用)", s)
    if m:
        return float(m.group(1))
    m = re.search(NUM + r"\s*~\s*" + NUM + r"\s*(人前|人分|皿分)", s)
    return float(m.group(2)) if m else None


# ── food facts ───────────────────────────────────────────────────────────────

def normalize_storage(s: str) -> str | None:
    if re.search(r"冷凍|-18|−18|マイナス18", s):
        return "冷凍"
    if re.search(r"冷蔵|10℃以下|10°C以下|チルド|要冷", s):
        return "冷蔵"
    if re.search(r"常温|直射日光|高温多湿|室温", s):
        return "常温"
    return None


def parse_allergens(s: str) -> tuple[list[str] | None, str]:
    """'特定原材料：えび・小麦・卵・乳' -> ['えび','小麦','卵','乳']; 'なし' -> []; unknown token -> None."""
    t = re.sub(r"^.*?(特定原材料(?:等)?(?:\s*\d+\s*品目)?|アレルゲン|アレルギー(?:表示)?|allergens?)\s*[:：]?", "", s, flags=re.I)
    t = re.sub(r"(を含む|を含みます|含む|\(.*?\)|（.*?）)", "", t).strip()
    if re.fullmatch(r"\s*(なし|無し|該当なし|不使用|-|ー)?\s*", t):
        return [], "表示対象なし"
    tokens = [x.strip() for x in re.split(r"[・、,/／\s]+", t) if x.strip()]
    out, unknown = [], []
    for tok in tokens:
        canon = next((c for c, vs in ALLERGEN_VARIANTS.items() if any(unicodedata.normalize("NFKC", v) == tok for v in vs)), None)
        if canon is None:
            canon = next((c for c, vs in ALLERGEN_VARIANTS.items()
                          if any(len(v) >= 2 and unicodedata.normalize("NFKC", v) in tok for v in vs)), None)
        if canon:
            if canon not in out:
                out.append(canon)
        else:
            unknown.append(tok)
    if unknown:
        return None, f"特定原材料28品目に該当しない語: {'・'.join(unknown)[:30]}"
    out.sort(key=ALLERGENS_28.index)
    return out, ""


def parse_days(s: str) -> float | None:
    m = re.search(NUM + r"\s*(年)", s)
    if m:
        return round(float(m.group(1)) * 365)
    m = re.search(NUM + r"\s*(ヶ月|か月|カ月|ヵ月|ケ月|月)", s)
    if m:
        return round(float(m.group(1)) * 30)
    m = re.search(NUM + r"\s*(日)", s)
    if m:
        return float(m.group(1))
    return None


def parse_minutes(s: str) -> float | None:
    h = re.search(NUM + r"\s*時間", s)
    mi = re.search(NUM + r"\s*分", s)
    sec = re.search(NUM + r"\s*秒", s)
    if not (h or mi or sec):
        return None
    total = (float(h.group(1)) * 60 if h else 0) + (float(mi.group(1)) if mi else 0) + (float(sec.group(1)) / 60 if sec else 0)
    return round(total, 2)


def parse_months(s: str) -> list[int] | None:
    """'10月~2月' -> [10,11,12,1,2]; '10 / 11 / 12' -> [10,11,12]; '秋' -> [9,10,11]."""
    s = unicodedata.normalize("NFKC", s or "").replace("〜", "~").replace("～", "~").replace("-", "~")
    m = re.search(r"(\d{1,2})\s*月?\s*~\s*(\d{1,2})\s*月", s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if 1 <= a <= 12 and 1 <= b <= 12:
            out, x = [], a
            while True:
                out.append(x)
                if x == b or len(out) > 12:
                    break
                x = x % 12 + 1
            return out
    nums = [int(float(x)) for x in re.findall(r"\d{1,2}(?:\.0)?", s)]
    nums = [n for n in nums if 1 <= n <= 12]
    if nums and (re.search(r"月", s) or re.fullmatch(r"[\d.\s/、,・]+", s)):
        return list(dict.fromkeys(nums))
    seasons = {"春": [3, 4, 5], "夏": [6, 7, 8], "秋": [9, 10, 11], "冬": [12, 1, 2]}
    out = []
    for k, v in seasons.items():
        if k in s:
            out += v
    return out or None


def fmt_months(ms: list[int]) -> str:
    if not ms:
        return ""
    if len(ms) >= 3 and all(ms[i + 1] == ms[i] % 12 + 1 for i in range(len(ms) - 1)):
        return f"{ms[0]}月〜{ms[-1]}月"
    return "・".join(str(m) for m in ms) + "月"


COOKING = [("電子レンジ", r"電子レンジ|レンジ|レンチン"), ("フライパン", r"フライパン|焼くだけ|炒め"), ("湯せん", r"湯せん|湯煎"),
           ("鍋", r"鍋で|煮込|ゆでる|茹で"), ("トースター", r"トースター"), ("オーブン", r"オーブン"), ("揚げ", r"揚げ|フライヤー"),
           ("そのまま", r"そのまま|解凍するだけ|開けてすぐ"), ("炊飯器", r"炊飯器")]


def normalize_cooking(s: str) -> str | None:
    hits = [name for name, rx in COOKING if re.search(rx, s)]
    return "・".join(hits) if hits else None


def normalize_pet(s: str) -> str | None:
    dog = re.search(r"犬|ドッグ|わんちゃん|ワンちゃん|dog", s, re.I)
    cat = re.search(r"猫|キャット|ねこ|ネコ|cat", s, re.I)
    if dog and cat:
        return "犬猫兼用"
    if dog:
        return "犬"
    if cat:
        return "猫"
    if re.search(r"うさぎ|ハムスター|小動物|フェレット", s):
        return "小動物"
    return None


def normalize_origin(s: str) -> str:
    s = re.sub(r"^(産地|原産国|原産地|生産国|原料原産地|製造国)\s*[:：]?\s*", "", s).strip()
    return s


# ── dimensions ───────────────────────────────────────────────────────────────

def _to_cm(v: float, unit: str) -> float:
    unit = (unit or "cm").lower()
    return round(v * {"mm": 0.1, "cm": 1, "m": 100}.get(unit, 1), 1)


def parse_dimensions(raw: str) -> dict[str, float] | None:
    """'幅45x奥行45x高さ40cm' / 'W45xD45xH40cm' / '45x45x40cm' (幅x奥行x高さ) -> {'w','d','h'} in cm."""
    s = clean(raw)
    unit_m = re.search(r"(mm|cm|m)(?![a-z])", s, re.I)
    unit = unit_m.group(1) if unit_m else "cm"
    found = {}
    for k, rx in (("w", r"(?:幅|W|横)\s*" + NUM), ("d", r"(?:奥行き?|D|マチ)\s*" + NUM), ("h", r"(?:高さ|H|縦|丈|深さ)\s*" + NUM)):
        m = re.search(rx, s)
        if m:
            found[k] = _to_cm(float(m.group(1)), unit)
    if len(found) >= 2:
        return found
    m = re.search(NUM + r"\s*x\s*" + NUM + r"\s*x\s*" + NUM + r"\s*(mm|cm|m)", s, re.I)
    if m:
        u = m.group(4)
        return {"w": _to_cm(float(m.group(1)), u), "d": _to_cm(float(m.group(2)), u), "h": _to_cm(float(m.group(3)), u),
                "_assumed": 1}
    m = re.search(NUM + r"\s*x\s*" + NUM + r"\s*(mm|cm|m)", s, re.I)
    if m:
        u = m.group(3)
        return {"w": _to_cm(float(m.group(1)), u), "d": _to_cm(float(m.group(2)), u), "_assumed": 1}
    return found or None


def _single_length(s: str) -> float | None:
    m = re.search(NUM + r"\s*(mm|cm|m)(?![a-zl])", s, re.I)
    if not m:
        return None
    return _to_cm(float(m.group(1)), m.group(2))


# ── entry point ──────────────────────────────────────────────────────────────

def normalize(key: str, raw_value: str) -> NormResult:
    """Normalize a raw transcribed value into the canonical unit / vocabulary for `key`."""
    r = _normalize(key, raw_value)
    if not r.ok and not r.note:
        r.note = f"値「{str(raw_value)[:30]}」を解釈できません"
    return r


def _normalize(key: str, raw_value: str) -> NormResult:
    d = ATTR_BY_KEY.get(key)
    if d is None:
        return NormResult(None, "", False, f"未定義の属性キー: {key}")
    s = clean(raw_value)
    if not s:
        return NormResult(None, d.unit, False, "値が空です")
    kind = d.kind
    try:
        if kind == "weight_g":
            r = parse_weight_g(s)
            return NormResult(_num(r[0]), "g", True, r[1]) if r else NormResult(None, "g", False, "g/kg 表記がありません")
        if kind == "volume_ml":
            r = parse_volume_ml(s)
            return NormResult(_num(r[0]), "ml", True, r[1]) if r else NormResult(None, "ml", False, "ml/L 表記がありません")
        if kind == "count":
            r = parse_count(s)
            return NormResult(r[0], d.unit, True, r[1]) if r else NormResult(None, d.unit, False, "数量の単位（個・本・切 など）がありません")
        if kind == "servings":
            v = parse_servings(s)
            return NormResult(_num(v), "人前", True, "") if v is not None else NormResult(None, "人前", False, "人前・皿分の表記がありません")
        if kind == "storage":
            v = normalize_storage(s)
            return NormResult(v, "", True, "冷蔵/冷凍/常温に標準化") if v else NormResult(None, "", False, "冷蔵/冷凍/常温のいずれか判別できません")
        if kind == "allergens":
            items, note = parse_allergens(s)
            if items is None:
                return NormResult(None, "", False, note)
            return NormResult("・".join(items) if items else "なし", "", True, note or "28品目の標準表記に統一")
        if kind == "days":
            v = parse_days(s)
            return NormResult(_num(v), "日", True, "年・月を日数に換算" if re.search(r"年|月", s) else "") if v is not None \
                else NormResult(None, "日", False, "日・月・年の表記がありません")
        if kind == "minutes":
            v = parse_minutes(s)
            return NormResult(_num(v), "分", True, "") if v is not None else NormResult(None, "分", False, "分・秒・時間の表記がありません")
        if kind == "cooking":
            v = normalize_cooking(s)
            return NormResult(v, "", True, "標準の調理方法に分類") if v else NormResult(s, "", True, "標準表記に未変換")
        if kind == "months":
            ms = parse_months(s)
            return NormResult(fmt_months(ms), "", True, "月の範囲に標準化") if ms else NormResult(None, "", False, "時期（月・季節）を解釈できません")
        if kind == "pet":
            v = normalize_pet(s)
            return NormResult(v, "", True, "") if v else NormResult(None, "", False, "対象ペットを判別できません")
        if kind == "origin":
            return NormResult(normalize_origin(s), "", True, "")
        if kind == "list":
            items = [x.strip() for x in re.split(r"[・、,/／]+", s) if x.strip()]
            return NormResult("・".join(dict.fromkeys(items)), "", True, "")
        if kind in ("dim_w", "dim_d", "dim_h"):
            dims = parse_dimensions(s)
            k = kind[-1]
            if dims and k in dims:
                note = "幅×奥行×高さ の順とみなして分解" if dims.get("_assumed") else "寸法表記を分解し cm に換算"
                return NormResult(_num(dims[k]), "cm", True, note)
            if not dims:
                v = _single_length(s)
                if v is not None and re.search(r"(幅|W|奥行|D|高さ|H)", s) is None and kind == "dim_w":
                    return NormResult(_num(v), "cm", True, "単一寸法を幅とみなしました")
            return NormResult(None, "cm", False, "寸法を解釈できません")
        if kind == "diameter":
            m = re.search(r"(?:直径|口径|径|φ|Φ)\s*" + NUM + r"\s*(mm|cm|m)?", s)
            if m:
                return NormResult(_num(_to_cm(float(m.group(1)), m.group(2) or "cm")), "cm", True, "")
            v = _single_length(s)
            return NormResult(_num(v), "cm", True, "単一寸法を直径とみなしました") if v is not None \
                else NormResult(None, "cm", False, "直径を解釈できません")
        if kind == "bool":
            neg = re.search(r"(不可|非対応|対応していません|使用できません|できません|×|NG|いいえ|false|専用)", s, re.I)
            if neg and "IH" in s and "専用" in s and key == "ih_compatible" and "IH専用" in s:
                return NormResult(True, "", True, "IH専用")
            return NormResult(not bool(neg), "", True, "")
        # text
        return NormResult(s, "", True, "")
    except Exception as e:  # pragma: no cover - defensive
        return NormResult(None, d.unit, False, f"正規化エラー: {e}")
