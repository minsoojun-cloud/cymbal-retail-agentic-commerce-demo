"""AI Spec Enricher using Vertex AI Gemini 2.5 Flash + Google Search Grounding.

Automatically fills missing 機能表 spec fields based on the product's JAN code,
model number, maker, and product name in `mst_product`.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
from typing import Any

from edion_banner.category_schemas import CATEGORY_DEFINITIONS, default_specs_for_category

log = logging.getLogger(__name__)


def _parse_json_from_text(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)
    if blocks:
        return json.loads(blocks[-1])
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        return json.loads(m.group(0))
    return {}


async def enrich_specs_with_gemini(
    category: str,
    product_info: dict[str, Any],
    current_specs: dict[str, Any],
) -> dict[str, Any]:
    cat_def = CATEGORY_DEFINITIONS.get(category)
    if not cat_def:
        raise ValueError(f"Unsupported category: {category}")

    base_specs = default_specs_for_category(category)
    merged = {**base_specs, **(current_specs or {})}

    field_lines = []
    for f in cat_def["fields"]:
        choices_str = f" (選択肢: {', '.join(f['choices'])})" if f.get("choices") else ""
        unit_str = f" [単位: {f['unit']}]" if f.get("unit") else ""
        field_lines.append(f"- {f['key']}: {f['label']}{unit_str}{choices_str}")

    prompt = f"""あなたは家電・総合小売 Cymbal Retail のVMD・商品機能表作成スペシャリストです。
以下の商品情報についてGoogle検索でメーカー公式仕様表を調べ、カテゴリ「{cat_def['name']} ({category})」の機能表スペックJSONを最新・正確な値で補完してください。

【商品情報 (商品マスタ)】
- JANコード: {product_info.get('jan_code', '')}
- 型番: {product_info.get('search_model_no', '')}
- メーカー名: {product_info.get('maker_name', '')}
- 商品名: {product_info.get('product_name', '')}
- 特長: {product_info.get('features', '')}

【対象フィールド定義】
{chr(10).join(field_lines)}

【現在のスペック値】
{json.dumps(merged, ensure_ascii=False)}

出力形式:
```json
{{
  "summary": "検索で確認した製品の主な仕様の要約（2〜3文）",
  "specs": {{
    "<key>": "<value>"
  }}
}}
```
"""

    model = os.environ.get("AI_MODEL", "gemini-2.5-flash")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("AI_PROJECT", "")
    location = os.environ.get("AI_LOCATION", "global")

    sources: list[dict[str, str]] = []
    queries: list[str] = []
    summary = ""
    ai_specs: dict[str, Any] = {}

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(vertexai=True, project=project, location=location)
        config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.1,
        )
        resp = await client.aio.models.generate_content(
            model=model, contents=prompt, config=config
        )
        try:
            gm = resp.candidates[0].grounding_metadata
            queries = list(gm.web_search_queries or [])
            seen = set()
            for ch in gm.grounding_chunks or []:
                title = (ch.web.title or "").strip()
                uri = ch.web.uri or ""
                if title and title not in seen:
                    seen.add(title)
                    sources.append({"title": title, "uri": uri})
        except Exception:
            pass

        parsed = _parse_json_from_text(resp.text or "")
        summary = parsed.get("summary") or "Google検索グラウンディングによりメーカー公式仕様を補完しました。"
        ai_specs = parsed.get("specs") or {}
    except Exception as e:
        log.warning("Vertex AI Gemini call fell back to smart master synthesis: %s", e)
        summary = (
            f"商品マスタ情報（{product_info.get('maker_name', '')} {product_info.get('search_model_no', '')}）"
            "およびカテゴリ標準スペックから自動補完しました。"
        )
        ai_specs = {
            "maker": product_info.get("maker_name") or merged.get("maker"),
            "model_no": product_info.get("search_model_no") or merged.get("model_no"),
            "jan_code": product_info.get("jan_code") or merged.get("jan_code"),
        }

    final_specs = {**merged}
    updated_keys: list[str] = []
    for k, v in ai_specs.items():
        if k in final_specs and v not in (None, "", "null", "不明"):
            final_specs[k] = v
            updated_keys.append(k)

    # Always ensure maker, model_no, jan_code are synced from master if blank
    if product_info.get("maker_name") and not final_specs.get("maker"):
        final_specs["maker"] = product_info["maker_name"]
    if product_info.get("search_model_no") and not final_specs.get("model_no"):
        final_specs["model_no"] = product_info["search_model_no"]
    if product_info.get("jan_code") and not final_specs.get("jan_code"):
        final_specs["jan_code"] = product_info["jan_code"]

    return {
        "specs": final_specs,
        "updated_keys": updated_keys,
        "summary": summary,
        "sources": sources[:6],
        "queries": queries,
        "model": model,
        "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
