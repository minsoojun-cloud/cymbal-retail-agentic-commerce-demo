"""Compliance guardrails for the store AI (store-navi/docs/COMPLIANCE_ja.md).

- detect_red_flags(text)  §2 受診勧奨 triggers → [{code, level: emergency|consult|crisis, label}]
- red_flag_preface(flags) text that MUST open the reply (server emits it before the model text)
- detect_abuse(text)      §1 指定濫用防止医薬品: multi-box / long-term / off-label use signals
- TextFilter              §3 post-filter for prohibited expressions (sentence-buffered for streaming)
- filter_items(...)       §3 one medicine per symptom group, age_min, red-flag → no medicines
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

DISCLAIMER = ("※本サービスは一般的な情報提供であり、医師の診断に代わるものではありません。医薬品は添付文書をよく読み、"
              "用法・用量を守ってご使用ください。症状が続く・悪化する場合は医療機関を受診してください。"
              "ご不明点は店舗の薬剤師・登録販売者にご相談ください。")

DRUG_CLASS_NOTES = {
    "第1類医薬品": "第1類医薬品：ご購入時に薬剤師からの説明が必要です。薬剤師不在時は購入できません。",
    "指定第2類医薬品": "指定第2類医薬品：使用上の注意（禁忌）を必ずご確認ください。ご不明点は薬剤師・登録販売者へ。",
    "第2類医薬品": "第2類医薬品：ご不明点は薬剤師・登録販売者にご相談ください。",
    "第3類医薬品": "第3類医薬品",
    "医薬部外品": "医薬部外品",
}
ABUSE_NOTE = ("指定濫用防止医薬品：お一人様1個まで。18歳未満の方は小容量1個のみ・年齢等の確認があります。"
              "この商品はレジ（医薬品カウンター）でお渡しします。")
MEDICINE_CLASSES = ("第1類医薬品", "指定第2類医薬品", "第2類医薬品", "第3類医薬品")


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    return t.replace("°C", "℃").replace("度C", "℃")


_KANJI_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _num(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    if s in _KANJI_NUM:
        return float(_KANJI_NUM[s])
    try:
        return float(s)
    except ValueError:
        return None


def _temperatures(t: str) -> list[float]:
    out = []
    for m in re.finditer(r"(\d{2}(?:\.\d)?)\s*(?:℃|度|ど)(?:\s*(\d)\s*分)?", t):
        v = float(m.group(1))
        if m.group(2):
            v += int(m.group(2)) / 10
        if 34 <= v <= 43:
            out.append(v)
    return out


def _days(t: str) -> float:
    best = 0.0
    for m in re.finditer(r"([0-9一二三四五六七八九十]+)\s*日(?:前|間|目|以上|も|続|ほど|くらい)", t):
        v = _num(m.group(1))
        if v:
            best = max(best, v)
    if re.search(r"(一週間|1週間|１週間|二週間|2週間|週間以上)", t):
        best = max(best, 7)
    if "一昨日" in t or "おととい" in t:
        best = max(best, 2)
    return best


def _infant_months(t: str) -> float | None:
    m = re.search(r"生後\s*([0-9一二三四五六七八九十]+)\s*(?:か月|ヶ月|カ月|ヵ月|ケ月|週)", t)
    if m:
        v = _num(m.group(1))
        if v is not None and ("週" in t[m.start():m.end()]):
            return v / 4.3
        return v
    m = re.search(r"([0-9一二三四五六七八九十]+)\s*(?:か月|ヶ月|カ月|ヵ月|ケ月)の(?:赤ちゃん|子|娘|息子|乳児|あかちゃん)", t)
    if m:
        return _num(m.group(1))
    if re.search(r"新生児", t):
        return 0.5
    return None


def child_age(text: str) -> float | None:
    """Age (years) of the person the consultation is about, when stated (e.g. 「5歳の子」「生後2か月」)."""
    t = _norm(text)
    mo = _infant_months(t)
    if mo is not None:
        return mo / 12
    m = re.search(r"([0-9一二三四五六七八九十]+)\s*(?:歳|才)", t)
    if m:
        return _num(m.group(1))
    if re.search(r"(乳児|赤ちゃん|あかちゃん)", t):
        return 0.5
    if re.search(r"(幼児|未就学)", t):
        return 3
    if re.search(r"(小学生)", t):
        return 8
    return None


FEVER_WORDS = r"(熱|発熱|ねつ)"
RULES: list[tuple[str, str, str, str]] = [
    # code, level, regex, label
    ("crisis", "crisis", r"(死にたい|消えたい|自殺|自傷|リストカット|オーバードーズ|ＯＤ|\bOD\b|まとめて飲んで|大量に飲(?:ん|み|む)|一度にたくさん飲)",
     "自傷・過量服薬の示唆"),
    ("breathing", "emergency", r"(息が苦し|呼吸が苦し|息苦し|呼吸困難|ゼーゼー|ぜーぜー|胸が痛|胸の痛|唇が紫|くちびるが紫|顔色が悪く)",
     "呼吸が苦しい・胸の痛み"),
    ("seizure", "emergency", r"(けいれん|痙攣|ひきつけ|意識がもうろう|意識が朦朧|意識がない|呼びかけに反応|反応が鈍)",
     "けいれん・意識障害"),
    ("severe_headache", "consult", r"(激しい頭痛|割れるような頭痛|今までにない頭痛|首が硬|首の硬直|首が曲がらない)", "激しい頭痛・首の硬直"),
    ("vomiting", "consult", r"(嘔吐を繰り返|何度も吐|吐き続け|繰り返し吐)", "嘔吐を繰り返す"),
    ("dehydration", "consult", r"(水分が取れ|水分がとれ|水も飲めな|水分を受け付け|尿が出な|おしっこが出な)", "水分が取れない・尿が出ない"),
    ("listless_child", "consult", r"((乳幼児|赤ちゃん|子ども|子供|こども|娘|息子).{0,12}ぐったり|ぐったりして)", "乳幼児のぐったり"),
    ("elderly_appetite", "consult", r"(高齢|祖母|祖父|おばあちゃん|おじいちゃん|親).{0,15}(食欲が(?:急に)?(?:ない|落ち)|食べなくな)", "高齢者の急な食欲低下"),
    ("pregnancy", "consult", r"(妊娠|妊婦|授乳中|授乳している|おなかに赤ちゃん)", "妊娠中・授乳中"),
    ("chronic", "consult", r"(持病|心臓病|心臓が悪|腎臓病|腎臓が悪|肝臓病|肝臓が悪|糖尿病|高血圧|血圧の薬|喘息|ぜんそく|通院中)", "持病がある"),
    ("other_meds", "consult", r"(他の薬|ほかの薬|薬を飲んで(?:いる|います|る)|服用中|服薬中|処方(?:薬|された))", "他の薬を服用中"),
    ("long_lasting", "consult", r"((?:[5-9５-９]|五|六|七|十)\s*日(?:以上)?(?:も|間)?(?:続|治らな|よくならな)|一週間|1週間|１週間|悪化して)",
     "症状が続く・悪化"),
    ("bleeding", "consult", r"(血便|黒い便|黒色便|便に血|強い腹痛|激しい腹痛|お腹が激しく痛)", "血便・黒色便・強い腹痛"),
    ("side_effect", "consult", r"((薬|飲んだ|服用).{0,15}(発疹|じんましん|蕁麻疹|かゆみ|息苦し)|(発疹|じんましん|蕁麻疹).{0,15}(薬|飲んだ後))",
     "副作用の疑い"),
]


def detect_red_flags(text: str) -> list[dict[str, str]]:
    t = _norm(text)
    flags: list[dict[str, str]] = []
    for code, level, rx, label in RULES:
        if re.search(rx, t):
            flags.append({"code": code, "level": level, "label": label})
    temps = _temperatures(t)
    days = _days(t)
    if temps and max(temps) >= 41:
        flags.append({"code": "fever_41", "level": "emergency", "label": "41℃以上の高熱"})
    elif temps and max(temps) >= 38.5 and days >= 3:
        flags.append({"code": "high_fever_3days", "level": "consult", "label": "38.5℃以上の高熱が3日以上"})
    elif re.search(FEVER_WORDS, t) and re.search(r"(下がらない|さがらない|解熱しない|ずっと続|続いて)", t) and (days >= 3 or (temps and max(temps) >= 38.5)):
        flags.append({"code": "fever_persistent", "level": "consult", "label": "高熱が下がらない"})
    mo = _infant_months(t)
    if mo is not None and mo < 3 and re.search(FEVER_WORDS, t):
        flags.append({"code": "infant_fever", "level": "consult", "label": "生後3か月未満の乳児の発熱"})
    seen, out = set(), []
    for f in flags:
        if f["code"] not in seen:
            seen.add(f["code"])
            out.append(f)
    return out


def is_blocking(flags: list[dict]) -> bool:
    """True when product suggestions must be limited to non-medicine support items (or none)."""
    return any(f["level"] in ("emergency", "crisis") or f["code"] in (
        "high_fever_3days", "fever_persistent", "infant_fever", "severe_headache", "vomiting", "dehydration",
        "listless_child", "bleeding", "side_effect", "elderly_appetite", "long_lasting") for f in flags)


def only_consult(flags: list[dict]) -> bool:
    """Pregnancy / chronic disease / other medicines: suggestions allowed only with 医師・薬剤師相談."""
    return bool(flags) and all(f["code"] in ("pregnancy", "chronic", "other_meds") for f in flags)


def red_flag_preface(flags: list[dict]) -> str:
    if not flags:
        return ""
    levels = {f["level"] for f in flags}
    labels = "・".join(f["label"] for f in flags[:3])
    if "crisis" in levels:
        return ("おつらい気持ちをお聞かせくださりありがとうございます。ひとりで抱え込まず、今すぐ相談できる窓口をご利用ください。\n"
                "・いのちの電話 0570-783-556\n・急な体調の変化や薬を多く飲んでしまった場合は 119番、迷ったら救急安心センター #7119\n"
                "このご相談では商品のご提案は控えます。店舗の薬剤師にもいつでもお声がけください。")
    if "emergency" in levels:
        return (f"**医療機関の受診をおすすめします。**「{labels}」がある場合は、すぐに119番へ連絡してください。"
                "判断に迷うときは救急安心センター #7119 にご相談ください。")
    if only_consult(flags):
        return (f"**ご使用前に医師・薬剤師にご相談ください。**（{labels}）"
                "お薬の飲み合わせや持病への影響を確認するため、店舗の薬剤師・登録販売者にお声がけください。")
    return (f"**医療機関の受診をおすすめします。**（{labels}）"
            "急な病気やけがで迷ったら救急安心センター #7119 にご相談ください。以下は受診までの補助としての情報です。")


ABUSE_RX = [
    r"([2-9２-９]|[二三四五六七八九十]|複数|何)\s*(箱|個|本|瓶|つ)",
    r"(まとめ買い|まとめて買|大量|箱買い|買いだめ|買い溜め|ストック)",
    r"(長く飲み続け|ずっと飲んで|毎日飲んで|何年も|何か月も)",
    r"(眠れない|ねむれない|気分を上げ|ハイになり|テンションを上げ|多めに飲)",
]


def detect_abuse(text: str) -> list[str]:
    t = _norm(text)
    medicine_ctx = re.search(r"(薬|せき止め|咳止め|かぜ薬|風邪薬|鼻炎|シロップ|錠|カプセル)", t)
    if not medicine_ctx:
        return []
    return [rx for rx in ABUSE_RX if re.search(rx, t)]


ABUSE_GUIDANCE = ("せき止め・かぜ薬・鼻炎薬の一部（指定濫用防止医薬品）は**お一人様1個まで**の販売です。"
                  "18歳未満の方は小容量1個のみで、年齢等の確認があります。複数個や長期の使用をご希望の場合は、"
                  "店舗の薬剤師にご相談ください。")

# §3 prohibited expressions → compliant replacements (applied to every model text)
REPLACEMENTS: list[tuple[str, str]] = [
    (r"必ず治(?:る|ります|せます)", "症状の緩和が期待できます"),
    (r"(?:すぐに?|たちまち)治(?:る|ります)", "症状をやわらげます"),
    (r"確実に効(?:く|きます)", "効果が期待できます"),
    (r"絶対に?(?:効く|効きます|治る|治ります|大丈夫|安心)", "効果が期待できます"),
    (r"絶対に?", ""),
    (r"副作用(?:は|が)?(?:一切)?(?:ありません|ない|なし|無し|ゼロ)", "副作用が起こる場合があります。添付文書をご確認ください"),
    (r"(?:完全に|とても|非常に)?安全(?:です|な薬|な商品|性が高い)", "用法・用量を守ってご使用ください"),
    (r"最適です", "役立ちます"),
    (r"最適な", "適した"),
    (r"(?m)^\s*[-*_]{3,}\s*$", ""),
    (r"(?:最強|最高|一番効く|いちばん効く|No\.?\s*1|ナンバーワン|ナンバー1|業界一|日本一)(?:の)?", ""),
    (r"(?:医師|お医者さん|薬剤師|専門家)(?:が|も)?(?:推薦|おすすめ|お勧め|推奨|太鼓判)(?:する|している|しています|の)?",
     "症状に合う候補の"),
    (r"(インフルエンザ|新型コロナ|コロナ|肺炎|胃腸炎|胃潰瘍|ウイルス性[^\s、。]{0,6}|細菌性[^\s、。]{0,6}|[^\s、。]{1,8}症)の可能性が(?:高い|あります|考えられます)",
     r"\1のような症状がみられます。気になる場合は医療機関を受診してください"),
    (r"(?:は|が)?(インフルエンザ|コロナ|肺炎|胃腸炎)(?:です|でしょう|だと思います)", "のような症状については医療機関でご確認ください"),
]
BANNED_CHECK = re.compile(r"(必ず治|絶対|最強|No\.?\s*1|一番効く|副作用(?:は|が)?(?:ありません|ない|なし)|確実に効)")


def sanitize(text: str) -> str:
    out = text
    for rx, rep in REPLACEMENTS:
        out = re.sub(rx, rep, out)
    return out


def has_banned(text: str) -> bool:
    return bool(BANNED_CHECK.search(text or ""))


class TextFilter:
    """Streaming post-filter: buffers model text until a sentence boundary so a banned phrase split across deltas
    is still replaced."""

    def __init__(self) -> None:
        self.buf = ""

    def feed(self, delta: str) -> str:
        self.buf += delta or ""
        cut = max(self.buf.rfind("。"), self.buf.rfind("\n"), self.buf.rfind("！"), self.buf.rfind("？"))
        if cut < 0:
            return ""
        out, self.buf = self.buf[:cut + 1], self.buf[cut + 1:]
        return sanitize(out)

    def flush(self) -> str:
        out, self.buf = self.buf, ""
        return sanitize(out)


GROUPS = [  # symptom groups: at most one medicine per group (成分重複を避ける)
    ("fever_cold", ("かぜ薬", "解熱鎮痛薬")),
    ("cough_throat", ("のど・せき",)),
    ("nose", ("鼻炎薬",)),
    ("stomach", ("胃腸薬",)),
    ("eye", ("目薬",)),
    ("topical", ("外用薬・湿布",)),
    ("vitamin", ("ビタミン剤・滋養強壮",)),
    ("skin", ("皮膚薬・その他",)),
]


def symptom_group(product: dict) -> str:
    path = str(product.get("category_path") or "")
    for g, subs in GROUPS:
        if any(f"> {s}" in path or path.endswith(s) or f">{s}" in path for s in subs):
            return g
    return "other:" + path


def filter_items(items: list[dict], flags: list[dict], age: float | None = None,
                 max_medicines: int = 2, abuse: bool = False) -> tuple[list[dict], list[str]]:
    """items: [{product: Product, …}]. Returns (kept, notes) applying COMPLIANCE §2/§3 server-side."""
    notes: list[str] = []
    kept: list[dict] = []
    blocking = is_blocking(flags)
    crisis = any(f["level"] == "crisis" for f in flags)
    groups_used: set[str] = set()
    meds = 0
    for it in items:
        p = it.get("product") or {}
        dc = p.get("drug_class") or ""
        is_med = dc in MEDICINE_CLASSES
        if crisis:
            notes.append("crisis: all products removed")
            continue
        if abuse and p.get("abuse_control"):
            notes.append(f"abuse signal: removed abuse_control product {p.get('id')} (pharmacist consultation)")
            continue
        if is_med and blocking:
            notes.append(f"red flag: removed medicine {p.get('id')}")
            continue
        if is_med and age is not None:
            amin = p.get("age_min")
            if amin and age < float(amin):
                notes.append(f"age_min {amin} > {age}: removed {p.get('id')}")
                continue
            title = str(p.get("title") or "")
            if age < 15 and not re.search(r"(子ども|こども|小児|キッズ|ジュニア)", title) and (amin or 0) >= 15:
                notes.append(f"under 15: removed adult medicine {p.get('id')}")
                continue
        if is_med:
            g = symptom_group(p)
            if g in groups_used or meds >= max_medicines:
                notes.append(f"duplicate medicine group {g}: removed {p.get('id')}")
                continue
            groups_used.add(g)
            meds += 1
        kept.append(it)
    return kept, notes


def compliance_notes(product: dict) -> list[str]:
    out = []
    dc = product.get("drug_class")
    if dc in DRUG_CLASS_NOTES:
        out.append(DRUG_CLASS_NOTES[dc])
    if dc == "第1類医薬品":
        out.append("店頭購入は調剤カウンターで薬剤師にお声がけください。オンラインは薬剤師による確認後の発送です。")
    if product.get("abuse_control"):
        out.append(ABUSE_NOTE)
    return out


def item_limits(product: dict) -> dict[str, Any]:
    return {"max_qty": 1 if product.get("abuse_control") else 10,
            "pharmacist_required": product.get("drug_class") == "第1類医薬品"}
