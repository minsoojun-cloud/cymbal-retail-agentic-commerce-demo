"""Gate 1 (rule-based validation) and Gate 2 (composite confidence score) — Cymbal Retail.

Food safety rule (特定原材料): allergen values are NEVER auto-approved unless the evidence is an explicit
allergen statement found verbatim in the source (description / package label / document), and every allergen in the
value appears in that statement. Anything else (guess, structured 「なし」 only, title mentions an allergen that is not in
the list, not found at all) goes to HITL review with the reason.
"""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

from .schema import ALLERGEN_VARIANTS, ALLERGENS_MANDATORY, ATTR_BY_KEY

AUTO_APPROVED = "auto_approved"
NEEDS_REVIEW = "needs_review"
REJECTED = "rejected"
APPROVED = "approved"          # approved by a human (HITL)
EDITED = "edited"              # corrected + approved by a human
HUMAN_REJECTED = "human_rejected"

FINAL_OK = {AUTO_APPROVED, APPROVED, EDITED}


# ── Evidence grounding ───────────────────────────────────────────────────────

def _squash(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"[\s・、。,.:：()（）\[\]【】「」●◆■※/／]", "", s).lower()


def evidence_match(evidence: str, source_text: str, raw_value: str = "") -> float:
    """1.0 exact substring, 0.8 match after NFKC/whitespace squash, 0.5 only the raw value is found, else 0."""
    if not evidence:
        return 0.0
    if evidence in source_text:
        return 1.0
    if _squash(evidence) and _squash(evidence) in _squash(source_text):
        return 0.8
    if raw_value and _squash(raw_value) and _squash(raw_value) in _squash(source_text):
        return 0.5
    return 0.0


def token_confidence(avg_logprobs: float | None) -> float | None:
    if avg_logprobs is None:
        return None
    try:
        return max(0.0, min(1.0, math.exp(float(avg_logprobs))))
    except (TypeError, ValueError, OverflowError):
        return None


def composite_score(ev: float, self_conf: float, tok: float | None) -> float:
    self_conf = max(0.0, min(1.0, float(self_conf or 0)))
    if tok is None:
        s = 0.6 * ev + 0.4 * self_conf
    else:
        s = 0.5 * ev + 0.3 * self_conf + 0.2 * tok
    return round(s, 3)


# ── Gate 1: rules ────────────────────────────────────────────────────────────

def check_limits(key: str, value: Any) -> str | None:
    d = ATTR_BY_KEY.get(key)
    if not d or d.limits is None or not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    lo, hi = d.limits
    if value < lo or value > hi:
        return f"物理限界値外: {value:g}{d.unit}（許容 {lo:g}〜{hi:g}{d.unit}）"
    return None


ALLERGEN_CONTEXT_RE = re.compile(r"(特定原材料|アレルゲン|アレルギー|allergens?\s*:|原材料の一部に|含む|を含みます)", re.I)


_FALSE_HITS = {
    "そば": re.compile(r"(焼き?|やき|中華|ソース)そば|焼きソバ|焼ソバ"),   # 焼きそば・中華そば are wheat noodles
}


def allergen_mentions(text: str, only: list[str] | None = None) -> set[str]:
    """Canonical allergens whose spelling variants occur in `text` (optionally restricted to `only`)."""
    t = unicodedata.normalize("NFKC", text or "")
    hits = set()
    for canon, variants in ALLERGEN_VARIANTS.items():
        if only is not None and canon not in only:
            continue
        tt = _FALSE_HITS[canon].sub("", t) if canon in _FALSE_HITS else t
        for v in variants:
            v2 = unicodedata.normalize("NFKC", v)
            if canon == "乳" and v2 == "乳":
                # 「乳」 alone is too short (乳酸菌, 豆乳…): only inside an allergen statement list
                if re.search(r"(特定原材料|アレルゲン|allergens?)[^\n]{0,40}(?<![豆母])乳(?!酸)", tt, re.I):
                    hits.add(canon)
                    break
                continue
            if v2 in tt:
                hits.add(canon)
                break
    return hits


def check_allergen_evidence(value: Any, evidence: str, ev: float, source_text: str, title: str = "",
                            source_field: str = "") -> str | None:
    """Return a review reason if the allergen value is not provably grounded, else None."""
    if ev < 0.8:
        return "特定原材料の根拠が原本に一字一句見つかりません（推測で補完しない）"
    if not ALLERGEN_CONTEXT_RE.search(evidence or ""):
        return "根拠が特定原材料・アレルゲン表示ではありません（明示的な表示が必要）"
    items = [x for x in str(value or "").split("・") if x and x != "なし"]
    ev_hits = allergen_mentions(evidence)
    missing = [x for x in items if x not in ev_hits]
    if missing:
        return f"根拠に「{'・'.join(missing)}」の表示がありません"
    if str(value) == "なし":
        # 「なし」 must be stated in the product copy / label / document, not only a structured catalog field
        if source_field == "attributes" or re.match(r"\s*allergens\s*:", evidence or "", re.I):
            return "「なし」は構造化属性のみの記載です。パッケージの表示で確認してください"
    title_hits = allergen_mentions(title, only=ALLERGENS_MANDATORY)   # 表示義務 8 品目
    extra = sorted(h for h in title_hits if h not in items)
    if extra:
        return f"商品名に「{'・'.join(extra)}」を含みますが特定原材料に記載がありません（要確認）"
    return None


def check_consistency(values: dict[str, Any], title: str = "") -> dict[str, str]:
    """Cross-attribute consistency. Returns {attr_key: reason}."""
    issues: dict[str, str] = {}
    t = unicodedata.normalize("NFKC", title or "")
    st = values.get("storage_method")
    if isinstance(st, str):
        if "冷凍" in t and st != "冷凍" and "解凍" not in t:
            issues["storage_method"] = f"商品名に「冷凍」とあるのに保存方法が「{st}」"
        elif re.search(r"(生|鮮魚|刺身|切り身|精肉)", t) and st == "常温" and values.get("_group") == "fresh":
            issues["storage_method"] = "生鮮品で保存方法が「常温」は不自然"
    bb = values.get("best_before_days")
    if isinstance(bb, (int, float)) and values.get("storage_method") == "冷蔵" and bb > 120:
        issues["best_before_days"] = f"冷蔵品で賞味期限 {bb:g} 日は不自然"
    w, d, h = values.get("width_cm"), values.get("depth_cm"), values.get("height_cm")
    dia = values.get("diameter_cm")
    if isinstance(dia, (int, float)) and isinstance(w, (int, float)) and dia > w * 1.5:
        issues["diameter_cm"] = f"直径 {dia:g}cm が幅 {w:g}cm を大きく超過"
    ct = values.get("cook_time_min")
    if isinstance(ct, (int, float)) and values.get("_group") == "prepared" and ct > 120:
        issues["cook_time_min"] = f"調理時間 {ct:g} 分は惣菜・冷凍食品として不自然"
    vol, wt = values.get("net_volume_ml"), values.get("net_weight_g")
    if isinstance(vol, (int, float)) and isinstance(wt, (int, float)) and values.get("_group") in ("grocery", "prepared"):
        if wt > 0 and (vol / wt > 20 or wt / vol > 20):
            issues["net_volume_ml"] = f"内容量 {wt:g}g と {vol:g}ml の比が不自然"
    _ = d, h
    return issues


# ── Gate decision ────────────────────────────────────────────────────────────

def decide(norm_ok: bool, norm_note: str, limit_issue: str | None, consistency_issue: str | None,
           ev: float, score: float, threshold: float, safety_issue: str | None = None) -> tuple[str, str, str]:
    """Returns (gate_status, gate, reason). gate ∈ {gate1, gate2, gate3}."""
    if limit_issue:
        return REJECTED, "gate1", limit_issue
    if not norm_ok:
        return NEEDS_REVIEW, "gate1", f"単位正規化に失敗: {norm_note}"
    if consistency_issue:
        return NEEDS_REVIEW, "gate1", consistency_issue
    if safety_issue:
        return NEEDS_REVIEW, "gate1", f"食品安全ルール: {safety_issue}"
    if ev == 0:
        return NEEDS_REVIEW, "gate2", "根拠スニペットが原本に見つかりません（ハルシネーションの可能性）"
    if score >= threshold:
        return AUTO_APPROVED, "gate2", f"複合スコア {score:.2f} ≥ {threshold:.2f}"
    return NEEDS_REVIEW, "gate2", f"複合スコア {score:.2f} < {threshold:.2f}（確信度不足）"
