"""COMPLIANCE_ja.md §4 checks: red-flag detection (受診勧奨 first), abuse-control quantity, prohibited-expression filter,
drug_class notices, server-side item filter."""
from __future__ import annotations

import pytest

from app.agent import mock, safety


@pytest.mark.parametrize("text,code", [
    ("3日前から39度の熱が下がらない", "high_fever_3days"),
    ("三日前から38.8℃の熱が続いています", "high_fever_3days"),
    ("息が苦しい", "breathing"),
    ("胸が痛くて息苦しい", "breathing"),
    ("生後2か月の子が発熱", "infant_fever"),
    ("41度の熱", "fever_41"),
    ("子どもがけいれんした", "seizure"),
    ("妊娠中ですが頭痛薬を飲んでもいいですか", "pregnancy"),
    ("高血圧の薬を飲んでいます", "chronic"),
    ("水分が取れない", "dehydration"),
    ("黒い便が出た", "bleeding"),
    ("薬を飲んだ後に発疹が出た", "side_effect"),
    ("もう死にたい", "crisis"),
    ("一度にたくさん飲んだらどうなる", "crisis"),
])
def test_red_flags_detected(text, code):
    codes = [f["code"] for f in safety.detect_red_flags(text)]
    assert code in codes, (text, codes)


@pytest.mark.parametrize("text", ["昨日から熱があって、かぜっぽいです", "のどが少し痛い", "目が疲れる", "37.5度の熱"])
def test_no_false_red_flags(text):
    assert not safety.is_blocking(safety.detect_red_flags(text))


def test_preface_levels():
    em = safety.red_flag_preface(safety.detect_red_flags("息が苦しい"))
    assert em.startswith("**医療機関の受診をおすすめします。**") and "119" in em and "#7119" in em
    con = safety.red_flag_preface(safety.detect_red_flags("3日前から39度の熱が下がらない"))
    assert "受診" in con[:20] and "#7119" in con
    cr = safety.red_flag_preface(safety.detect_red_flags("死にたい"))
    assert "0570-783-556" in cr and "商品のご提案は控えます" in cr
    ph = safety.red_flag_preface(safety.detect_red_flags("高血圧の薬を飲んでいます"))
    assert "医師・薬剤師にご相談ください" in ph


def test_abuse_detection():
    assert safety.detect_abuse("かぜ薬を5箱ほしい")
    assert safety.detect_abuse("せき止めシロップをまとめ買いしたい")
    assert safety.detect_abuse("眠れないのでかぜ薬を多めに飲みたい")
    assert not safety.detect_abuse("かぜ薬がほしい")
    assert not safety.detect_abuse("マスクを5箱ほしい")  # not a medicine


def test_mock_abuse_reply_limits_quantity():
    ev = mock.respond("かぜ薬を5箱ほしい", "S01", "CR-0001", [], safety.detect_abuse("かぜ薬を5箱ほしい"), None)
    text = "".join(e.get("text", "") for e in ev if e["type"] == "text")
    assert "お一人様1個まで" in text and "薬剤師" in text
    assert not any(e["type"] == "action" for e in ev)


@pytest.mark.parametrize("bad", ["この薬で必ず治ります。", "絶対に効きます。", "最強のかぜ薬です。", "No.1の目薬。",
                                 "副作用はありません。", "確実に効く処方です。", "医師が推薦する薬です。", "インフルエンザの可能性があります。"])
def test_post_filter_replaces_banned(bad):
    out = safety.sanitize(bad)
    assert not safety.has_banned(out), out
    for w in ("必ず治", "絶対", "最強", "No.1", "副作用はありません", "確実に効", "医師が推薦", "可能性があります"):
        assert w not in out, (bad, out)


def test_streaming_filter_handles_split_tokens():
    f = safety.TextFilter()
    out = f.feed("この薬は必ず") + f.feed("治ります。安心して") + f.feed("ください") + f.flush()
    assert "必ず治" not in out and out.endswith("ください")


def test_filter_items_rules():
    def P(pid, dc, cat, age=None):
        return {"product": {"id": pid, "drug_class": dc, "category_path": cat, "age_min": age, "title": pid}}

    items = [P("cold", "指定第2類医薬品", "医薬品・ヘルスケア > かぜ薬 > 総合かぜ薬", 15),
             P("pain", "第2類医薬品", "医薬品・ヘルスケア > 解熱鎮痛薬 > 解熱鎮痛薬", 15),
             P("sheet", "", "ビューティー・パーソナルケア > 衛生・救急用品 > 冷却シート"),
             P("ors", "", "飲料・水 > スポーツドリンク > 経口補水液")]
    kept, _ = safety.filter_items(items, [])
    ids = [i["product"]["id"] for i in kept]
    assert ids == ["cold", "sheet", "ors"]            # かぜ薬 + 解熱鎮痛薬 never together
    kept, _ = safety.filter_items(items, safety.detect_red_flags("息が苦しい"))
    assert [i["product"]["id"] for i in kept] == ["sheet", "ors"]
    kept, _ = safety.filter_items(items, safety.detect_red_flags("死にたい"))
    assert kept == []
    kept, _ = safety.filter_items(items, [], age=5)    # age_min 15 → removed for a 5-year-old
    assert [i["product"]["id"] for i in kept] == ["sheet", "ors"]


def test_child_age():
    assert safety.child_age("5歳の子が熱") == 5
    assert safety.child_age("生後2か月の子が発熱") < 0.3
    assert safety.child_age("熱っぽい") is None


def test_drug_class_notes_wording():
    n1 = safety.compliance_notes({"drug_class": "第1類医薬品"})
    assert "ご購入時に薬剤師からの説明が必要です。薬剤師不在時は購入できません。" in n1[0]
    assert any("調剤カウンター" in n for n in n1)
    assert safety.compliance_notes({"drug_class": "指定第2類医薬品"})[0].startswith("指定第2類医薬品：使用上の注意（禁忌）")
    assert "お一人様1個まで" in " ".join(safety.compliance_notes({"drug_class": "指定第2類医薬品", "abuse_control": True}))
    assert safety.DISCLAIMER.startswith("※本サービスは一般的な情報提供であり、医師の診断に代わるものではありません。")


def test_mock_red_flag_has_no_medicine_and_preface():
    flags = safety.detect_red_flags("生後2か月の子が発熱")
    ev = mock.respond("生後2か月の子が発熱", "S01", "CR-0001", flags, [], safety.child_age("生後2か月の子が発熱"))
    first = next(e for e in ev if e["type"] == "text")
    assert "受診" in first["text"][:30]
    for e in ev:
        if e["type"] == "action":
            assert all(it["product"].get("drug_class") not in safety.MEDICINE_CLASSES for it in e["args"]["items"])


def test_mock_crisis_no_products():
    flags = safety.detect_red_flags("死にたい")
    ev = mock.respond("死にたい", "S01", "CR-0001", flags, [], None)
    assert not any(e["type"] == "action" for e in ev)
    assert "0570-783-556" in "".join(e.get("text", "") for e in ev)


def test_filter_items_abuse_removes_abuse_control():
    items = [{"product": {"id": "cough", "drug_class": "指定第2類医薬品", "category_path": "医薬品・ヘルスケア > のど・せき > せき止め",
                          "abuse_control": True, "title": "cough"}},
             {"product": {"id": "candy", "drug_class": "", "category_path": "お菓子・製菓 > グミ・キャンディ > のど飴", "title": "candy"}}]
    kept, notes = safety.filter_items(items, [], abuse=True)
    assert [i["product"]["id"] for i in kept] == ["candy"] and notes


def test_stream_abuse_preface_first(client):
    from conftest import sse_events

    r = client.post("/api/agent/stream", json={"session_id": "pytest-abuse", "message": "せき止めを5箱ほしい", "store_id": "S01"})
    ev = sse_events(r.text)
    first = next(e for e in ev if e["type"] == "text")
    assert "お一人様1個まで" in first["text"]
    texts = [e["text"] for e in ev if e["type"] == "text"]
    assert sum("お一人様1個まで" in t for t in texts) == 1
