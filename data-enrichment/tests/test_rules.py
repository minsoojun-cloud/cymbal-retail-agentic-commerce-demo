"""Gate 1/2 rules, food-safety allergen evidence rule and the 3-stage gate decision."""
import os

os.environ["OFFLINE"] = "true"

from app.config import settings  # noqa: E402
from app.pipeline import process_stage1  # noqa: E402
from app.rules import (AUTO_APPROVED, NEEDS_REVIEW, REJECTED, allergen_mentions, check_allergen_evidence,  # noqa: E402
                       check_consistency, check_limits, composite_score, decide, evidence_match)

settings.offline = True


def test_evidence_match_levels():
    src = "内容量：3切（約240g） / 産地：静岡県産"
    assert evidence_match("産地：静岡県産", src) == 1.0
    assert evidence_match("産地: 静岡県産", src) == 0.8          # NFKC / whitespace squash
    assert evidence_match("静岡産のかじき", src, "静岡県産") == 0.5  # only the raw value is found
    assert evidence_match("北海道産", src) == 0.0


def test_composite_score_weights():
    assert composite_score(1.0, 1.0, 1.0) == 1.0
    assert composite_score(1.0, 0.8, None) == round(0.6 + 0.32, 3)
    assert composite_score(0.5, 0.9, 0.9) == round(0.25 + 0.27 + 0.18, 3)


def test_limits_reject():
    assert check_limits("net_weight_g", 50000)       # 50kg of food in one pack -> physically implausible
    assert check_limits("net_weight_g", 240) is None
    assert check_limits("width_cm", 900)


def test_decide_three_stages():
    th = 0.9
    assert decide(True, "", "物理限界値外", None, 1.0, 1.0, th)[0] == REJECTED
    assert decide(False, "単位なし", None, None, 1.0, 1.0, th)[0] == NEEDS_REVIEW
    assert decide(True, "", None, None, 0.0, 0.95, th)[0] == NEEDS_REVIEW
    assert decide(True, "", None, None, 1.0, 0.95, th)[0] == AUTO_APPROVED
    st, gate, reason = decide(True, "", None, None, 1.0, 0.95, th, "特定原材料の根拠なし")
    assert st == NEEDS_REVIEW and gate == "gate1" and "食品安全ルール" in reason


def test_consistency_frozen_title():
    issues = check_consistency({"storage_method": "冷蔵", "_group": "prepared"}, "Cymbal 冷凍 カルボナーラ 260g")
    assert "storage_method" in issues
    assert not check_consistency({"storage_method": "冷凍", "_group": "prepared"}, "Cymbal 冷凍 カルボナーラ 260g")


# ── allergen evidence rule ───────────────────────────────────────────────────
SRC = "【タイトル】Cymbal えびピラフ 450g\n【説明文】えびの旨みが広がるピラフ。\n内容量：450g / 保存方法：冷凍 / 特定原材料：えび・小麦・乳\n【属性】\nallergens: えび / 小麦 / 乳"


def test_allergen_ok_when_statement_quoted():
    assert check_allergen_evidence("えび・小麦・乳", "特定原材料：えび・小麦・乳", 1.0, SRC, "Cymbal えびピラフ 450g") is None


def test_allergen_review_when_not_grounded():
    assert check_allergen_evidence("えび・小麦・乳", "えびピラフ", 1.0, SRC, "Cymbal えびピラフ 450g")   # no allergen context
    assert check_allergen_evidence("えび・小麦・乳", "特定原材料：えび・小麦・乳", 0.0, SRC, "")            # not in source
    assert check_allergen_evidence("えび・小麦・乳・卵", "特定原材料：えび・小麦・乳", 1.0, SRC, "")          # 卵 not in evidence


def test_allergen_title_mentions_mandatory_item():
    r = check_allergen_evidence("小麦・乳", "特定原材料：小麦・乳", 1.0, "特定原材料：小麦・乳", "Cymbal えびグラタン")
    assert r and "えび" in r


def test_allergen_nashi_only_structured_needs_review():
    src = "【説明文】酒粕でじっくり漬け込みました。\n【属性】\nallergens: なし"
    r = check_allergen_evidence("なし", "allergens: なし", 1.0, src, "奈良漬", "attributes")
    assert r and "構造化属性" in r
    assert check_allergen_evidence("なし", "特定原材料：なし", 1.0, "特定原材料：なし", "奈良漬", "description") is None


def test_allergen_mentions_false_hits():
    assert "そば" not in allergen_mentions("Cymbal ソース焼きそば 3食", only=["そば"])
    assert "そば" in allergen_mentions("年越し 天ぷらそば", only=["そば"])
    assert "乳" not in allergen_mentions("豆乳 1000ml")


FOOD = {"sku": "F1", "title": "Cymbal えびピラフ 450g", "brand": "Cymbal", "category": "冷凍食品・アイス > 冷凍 ごはん",
        "group": "prepared", "description": "えびの旨みが広がるピラフ。\n内容量：450g / 保存方法：冷凍 / 特定原材料：えび・小麦・乳",
        "raw_attributes": {}}


def test_pipeline_missing_allergen_goes_to_review():
    p = {**FOOD, "description": "えびの旨みが広がるピラフ。内容量：450g"}
    recs = process_stage1(p, {"attributes": [
        {"key": "net_weight_g", "raw_value": "450g", "evidence": "内容量：450g", "source_field": "description", "confidence": 0.98}],
        "not_found": ["allergens"]}, None, "j", "m")
    al = next(r for r in recs if r["attr_key"] == "allergens")
    assert al["gate_status"] == NEEDS_REVIEW and al["value"] is None and "推測" in al["reason"]
    assert next(r for r in recs if r["attr_key"] == "net_weight_g")["gate_status"] == AUTO_APPROVED


def test_pipeline_guessed_allergen_is_not_auto_approved():
    p = {**FOOD, "description": "えびの旨みが広がるピラフ。内容量：450g"}
    recs = process_stage1(p, {"attributes": [
        {"key": "allergens", "raw_value": "えび", "evidence": "えびの旨み", "source_field": "description", "confidence": 0.99}],
        "not_found": []}, None, "j", "m")
    assert recs[0]["gate_status"] == NEEDS_REVIEW and "食品安全ルール" in recs[0]["reason"]


def test_pipeline_grounded_allergen_auto_approved():
    recs = process_stage1(FOOD, {"attributes": [
        {"key": "allergens", "raw_value": "特定原材料：えび・小麦・乳", "evidence": "特定原材料：えび・小麦・乳",
         "source_field": "description", "confidence": 0.99}], "not_found": []}, None, "j", "m")
    assert recs[0]["gate_status"] == AUTO_APPROVED and recs[0]["value"] == "えび・小麦・乳"


def test_pipeline_conflict_with_catalog_attribute():
    p = {**FOOD, "raw_attributes": {"allergens": "小麦 / 乳"}}
    recs = process_stage1(p, {"attributes": [
        {"key": "allergens", "raw_value": "特定原材料：えび・小麦・乳", "evidence": "特定原材料：えび・小麦・乳",
         "source_field": "description", "confidence": 0.99}], "not_found": []}, None, "j", "m")
    assert recs[0]["gate_status"] == NEEDS_REVIEW and "一致しません" in recs[0]["reason"]
