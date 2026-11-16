"""「AI による概要」 — Gemini (Vertex AI, google-genai) summary + per-product highlight reasons + follow-up.

Returns JSON: {summary, highlights:[{product_id, reason}], followup:{question, answers:[str]}, source}
Falls back to a deterministic template when Gemini is unavailable (AI_MOCK=1, no credentials, timeout).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

log = logging.getLogger("cymbal-site.ai")

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_LOCATION = os.environ.get("GEMINI_LOCATION", "global")
PROJECT_ID = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT") or ""
BRAND_NAME = (os.environ.get("BRAND_NAME") or "Cymbal Retail").strip() or "Cymbal Retail"
AI_TIMEOUT = float(os.environ.get("AI_TIMEOUT_SEC", "25"))

_client = None
_cache: dict[tuple, dict] = {}

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "highlights": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "product_id": {"type": "STRING"}, "reason": {"type": "STRING"}}, "required": ["product_id", "reason"]}},
        "followup": {"type": "OBJECT", "properties": {
            "question": {"type": "STRING"}, "answers": {"type": "ARRAY", "items": {"type": "STRING"}}},
            "required": ["question", "answers"]},
    },
    "required": ["summary", "highlights", "followup"],
}

PROMPT = """あなたは日本の総合スーパー「Cymbal Retail」のオンラインストアの検索アシスタントです。
お客様の検索キーワードと、検索結果の上位商品リストを読み、Google 検索の「AI による概要」のような短い要約を作ってください。

# ルール
- summary: 日本語で 2〜3 文、合計 140 文字以内。検索意図に対して、どんな選択肢があるか（価格帯・セール・特徴など）を俯瞰して伝える。誇張や事実にない情報は書かない。
- highlights: 特におすすめの商品を 3 件まで。product_id は必ずリスト内の id をそのまま使う。reason は 30 文字以内の日本語（例:「セールで20%オフ、評価★4.6」）。
- followup: 検索結果をさらに絞り込むための短い質問（25 文字以内）と、その回答候補 3〜5 個（各 10 文字以内、そのまま検索キーワードに追加できる語）。
- 価格は税込の円表記（例: ¥398）。

# 検索キーワード
{q}

# 検索結果（上位）
{items}
"""


def _get_client():
    global _client
    if _client is None:
        from google import genai  # lazy

        _client = genai.Client(vertexai=True, project=PROJECT_ID, location=GEMINI_LOCATION)
    return _client


def template_summary(q: str, products: list[dict]) -> dict:
    if not products:
        return {"summary": f"「{q}」に一致する商品は見つかりませんでした。キーワードを変えてお試しください。",
                "highlights": [], "followup": {"question": "", "answers": []}, "source": "template"}
    prices = [p["price"] for p in products if p.get("price")]
    sale = [p for p in products if p.get("on_sale")]
    cats = []
    for p in products:
        if p.get("category") and p["category"] not in cats:
            cats.append(p["category"])
    s = f"「{q}」では {len(products)} 件の主な候補があり、価格は ¥{min(prices):,}〜¥{max(prices):,} です。" if prices else ""
    if sale:
        s += f"うち {len(sale)} 件がセール中です。"
    if cats:
        s += f"主なカテゴリは {'・'.join(cats[:3])} です。"
    top = sorted(products, key=lambda p: (-(p.get("on_sale") or 0), -(p.get("rating") or 0)))[:3]
    hl = []
    for p in top:
        bits = []
        if p.get("on_sale") and p.get("discount_rate"):
            bits.append(f"セールで{int(round(p['discount_rate'] * 100))}%オフ")
        bits.append(f"評価★{p.get('rating', 0)}")
        hl.append({"product_id": p["id"], "reason": "、".join(bits)})
    labels: list[str] = []
    for p in products:
        for l in p.get("labels") or []:
            if l not in labels:
                labels.append(l)
    return {"summary": s, "highlights": hl,
            "followup": {"question": "どんな条件で選びますか？", "answers": (labels[:4] or ["セール", "人気"])},
            "source": "template"}


def _items_text(products: list[dict]) -> str:
    lines = []
    for p in products[:10]:
        sale = f" セール{int(round((p.get('discount_rate') or 0) * 100))}%オフ(通常¥{p.get('original_price', 0):,})" if p.get("on_sale") else ""
        lines.append(f"- id={p['id']} | {p['title']} | ¥{p.get('price', 0):,}{sale} | ★{p.get('rating')}({p.get('rating_count')}) | "
                     f"{p.get('category', '')} | {' '.join(p.get('labels') or [])}")
    return "\n".join(lines)


def _sanitize(data: dict, products: list[dict]) -> dict:
    ids = {p["id"] for p in products}
    hl = [h for h in (data.get("highlights") or []) if isinstance(h, dict) and h.get("product_id") in ids][:3]
    fu = data.get("followup") or {}
    return {"summary": str(data.get("summary") or "").strip(), "highlights": hl,
            "followup": {"question": str(fu.get("question") or ""), "answers": [str(a) for a in (fu.get("answers") or [])][:5]},
            "source": "gemini", "model": GEMINI_MODEL}


def _generate_sync(q: str, products: list[dict]) -> dict:
    from google.genai import types

    client = _get_client()
    prompt = PROMPT.replace("Cymbal Retail", BRAND_NAME) if BRAND_NAME != "Cymbal Retail" else PROMPT
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt.format(q=q, items=_items_text(products)),
        config=types.GenerateContentConfig(
            temperature=0.3, response_mime_type="application/json", response_schema=SCHEMA,
            thinking_config=(types.ThinkingConfig(thinking_level="low") if "gemini-3" in GEMINI_MODEL
                             else types.ThinkingConfig(thinking_budget=0)),
        ),
    )
    return _sanitize(json.loads(resp.text), products)


async def ai_summary(q: str, products: list[dict]) -> dict:
    key = (q, tuple(p["id"] for p in products[:10]))
    if key in _cache:
        return _cache[key]
    if os.environ.get("AI_MOCK") == "1" or not products:
        return template_summary(q, products)
    try:
        out = await asyncio.wait_for(asyncio.to_thread(_generate_sync, q, products), timeout=AI_TIMEOUT)
        if not out["summary"]:
            raise ValueError("empty summary")
        _cache[key] = out
        if len(_cache) > 500:
            _cache.pop(next(iter(_cache)))
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("Gemini summary failed (%s); using template", str(e)[:300])
        out = template_summary(q, products)
        out["error"] = str(e)[:200]
        return out


# ---------------------------------------------------------------------------
# English → Japanese for conversationalSearch follow-up texts (cached)
# ---------------------------------------------------------------------------
_tcache: dict[str, str] = {}
TRANSLATE_PROMPT = """次の英文を、日本のスーパーのオンラインストアのアシスタントが話す自然で丁寧な短い日本語に翻訳してください。
- 質問は 40 文字以内、説明文は 90 文字以内に要約してよい。
- 出力は JSON 配列（入力と同じ順番の文字列）のみ。

{items}"""


def translate_ja_sync(texts: list[str], timeout: float = 8.0) -> list[str]:
    """Translate short English texts to Japanese (Gemini). Returns '' for items that could not be translated."""
    from google.genai import types

    texts = [t or "" for t in texts]
    todo = [t for t in texts if t and t not in _tcache]
    if todo and os.environ.get("AI_MOCK") != "1":
        try:
            client = _get_client()
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=TRANSLATE_PROMPT.format(items=json.dumps(todo, ensure_ascii=False)),
                config=types.GenerateContentConfig(
                    temperature=0.2, response_mime_type="application/json",
                    response_schema={"type": "ARRAY", "items": {"type": "STRING"}},
                    http_options=types.HttpOptions(timeout=int(timeout * 1000)),
                    thinking_config=(types.ThinkingConfig(thinking_level="low") if "gemini-3" in GEMINI_MODEL
                                     else types.ThinkingConfig(thinking_budget=0)),
                ),
            )
            out = json.loads(resp.text)
            for src, ja in zip(todo, out):
                if ja:
                    _tcache[src] = str(ja)
            if len(_tcache) > 2000:
                _tcache.pop(next(iter(_tcache)))
        except Exception as e:  # noqa: BLE001
            log.warning("translate failed: %s", str(e)[:200])
    return [_tcache.get(t, "") if t else "" for t in texts]
