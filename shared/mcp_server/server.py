"""Cymbal Retail Commerce MCP Server (Vertex AI Search for Commerce / Retail API + BigQuery).

MCP Streamable HTTP (stateless JSON) compatibility settings:
  1. loose Accept header check
  2. minimal list_tools with clean_schema (no title/default)
  3. FastMCP(stateless_http=True, json_response=True, DNS rebinding protection off), endpoint /mcp

Tools:
  - search_products       : Retail search via servingConfigs/default_search (max 100 items, IN_STOCK only,
                            「N円以下」 helper; grocery + general merchandise attributes)
  - get_product_details   : full product (description / attributes / images / rating)
  - compare_products      : comparison rows (価格/内容量・サイズ/ラベル/評価/産地 or 素材...) ready for the
                            client-side show_comparison function
  - get_customer_profile  : BigQuery ${BQ_DATASET}.customers (fallback: bundled personas.json)
  - get_purchase_history  : BigQuery ${BQ_DATASET}.purchase_history (fallback: bundled JSONL)
  - recommend_dinner_set  : dinner product sets (主菜/副菜/汁物/主食/デザート・果物) from persona + history frequency +
                            sale + seasonal items (dinner.py; catalog from BigQuery ${BQ_DATASET}.products, cached)
"""
import asyncio
import inspect
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
from typing import Annotated

from pydantic import BeforeValidator

from mcp.server.fastmcp import FastMCP
from mcp.server.streamable_http import StreamableHTTPServerTransport
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import Tool as MCPTool

import dinner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cymbal-commerce-mcp")

# ── GECX compatibility patches ────────────────────────────────────────────────


# 1. Bypass strict Accept header validation
def loose_check_accept_headers(self, request):
    return True, True


StreamableHTTPServerTransport._check_accept_headers = loose_check_accept_headers


# 2. Return minimal tool definitions (GECX prefers standard name/description/inputSchema)
def clean_schema(schema):
    """Recursively remove fields that often cause issues in strict parsers."""
    if not isinstance(schema, dict):
        return schema
    schema.pop("title", None)
    schema.pop("default", None)
    if "properties" in schema:
        for prop in schema["properties"].values():
            clean_schema(prop)
    for _, v in list(schema.items()):
        if isinstance(v, dict):
            clean_schema(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    clean_schema(item)
    return schema


async def list_tools_minimal(self) -> list[MCPTool]:
    result = []
    for info in self._tool_manager.list_tools():
        cleaned_desc = inspect.cleandoc(info.description) if info.description else ""
        cleaned_schema = clean_schema(json.loads(json.dumps(info.parameters)))  # deep copy
        result.append(MCPTool(name=info.name, description=cleaned_desc, inputSchema=cleaned_schema))
    return result


FastMCP.list_tools = list_tools_minimal

# 3. Stateless JSON transport
mcp = FastMCP(
    "CymbalCommerceMCP",
    stateless_http=True,  # Required for GECX (stateless requests)
    json_response=True,  # JSON responses instead of SSE
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

# ── Configuration ────────────────────────────────────────────────────────────
PROJECT_ID = os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "cymbal-demo-project"
REGION = os.getenv("REGION", "asia-northeast1")
LOCATION = os.getenv("LOCATION", "global")
CATALOG = os.getenv("CATALOG", "default_catalog")
SERVING_CONFIG = os.getenv("SERVING_CONFIG", "default_search")
COMPACT_RESULTS = os.getenv("COMPACT_RESULTS", "false").lower() == "true"
BRANCH = os.getenv("BRANCH", "0")
BQ_DATASET = os.getenv("BQ_DATASET", "cymbal")
BQ_LOCATION = os.getenv("BQ_LOCATION") or REGION
DEFAULT_VISITOR_ID = "mcp-agent-session"

MAX_PAGE_SIZE = 100  # requirement: max 100 products per search
SEARCH_TIMEOUT_S = 4.5  # Retail search RPC timeout
HYDRATE_BUDGET_S = 4.5  # overall budget for parallel get_product hydration
BQ_TIMEOUT_S = 8.0
IN_STOCK_FILTER = 'availability: ANY("IN_STOCK")'

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1] if len(_HERE.parents) > 1 else _HERE
DATA_DIRS = [
    Path(os.getenv("DATA_DIR", _HERE / "data")),
    Path(os.getenv("PERSONAS_DIR", _REPO_ROOT / "seed" / "personas")),
]

PRICE_CAP_RE = re.compile(r"([0-9０-９,，]+)\s*円\s*(?:以下|以内|未満|まで)")

# ── Lazy clients (overridable in tests) ──────────────────────────────────────
_clients: dict = {}


def _search_client():
    if "search" not in _clients:
        from google.cloud import retail_v2

        _clients["search"] = retail_v2.SearchServiceClient()
    return _clients["search"]


def _product_client():
    if "product" not in _clients:
        from google.cloud import retail_v2

        _clients["product"] = retail_v2.ProductServiceClient()
    return _clients["product"]


def _bq_client():
    if "bq" not in _clients:
        from google.cloud import bigquery

        _clients["bq"] = bigquery.Client(project=PROJECT_ID, location=BQ_LOCATION)
    return _clients["bq"]


def get_catalog_name():
    return f"projects/{PROJECT_ID}/locations/{LOCATION}/catalogs/{CATALOG}"


def get_serving_config():
    return f"{get_catalog_name()}/servingConfigs/{SERVING_CONFIG}"


def product_name(product_id: str) -> str:
    return f"{get_catalog_name()}/branches/{BRANCH}/products/{product_id}"


# ── Helpers ──────────────────────────────────────────────────────────────────


def clamp_page_size(page_size) -> int:
    """Clamp page_size to 1..100 (requirement: max 100 products)."""
    try:
        n = int(page_size) if page_size is not None else 20
    except (TypeError, ValueError):
        n = 20
    return max(1, min(n, MAX_PAGE_SIZE))


def extract_price_cap(query: str):
    """「3,000円以下」「500円以内」 → 3000 / 500 (None if absent)."""
    if not query:
        return None
    m = PRICE_CAP_RE.search(query)
    if not m:
        return None
    digits = m.group(1).translate(str.maketrans("０１２３４５６７８９，", "0123456789,")).replace(",", "")
    try:
        return int(digits)
    except ValueError:
        return None


def build_filter(user_filter, query: str, include_out_of_stock: bool = False):
    """Compose the Retail filter: (user filter | price-cap helper) AND IN_STOCK.

    Returns (filter_string, price_cap).
    """
    parts = []
    price_cap = None
    uf = (user_filter or "").strip()
    if uf:
        parts.append(uf)
    else:
        price_cap = extract_price_cap(query)
        if price_cap:
            parts.append(f"price: IN(*, {float(price_cap)}i)")
    if not include_out_of_stock:
        parts.append(IN_STOCK_FILTER)
    if len(parts) > 1:
        return " AND ".join(f"({p})" for p in parts), price_cap
    return (parts[0] if parts else ""), price_cap


def attrs_to_dict(attributes) -> dict:
    """Retail CustomAttribute map → plain dict (single values unwrapped)."""
    out = {}
    if not attributes:
        return out
    for k, v in attributes.items():
        text = list(getattr(v, "text", []) or [])
        nums = list(getattr(v, "numbers", []) or [])
        if text:
            out[k] = text[0] if len(text) == 1 else text
        elif nums:
            out[k] = nums[0] if len(nums) == 1 else nums
    return out


def _to_int(x):
    try:
        return int(round(float(x))) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _join(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return " / ".join(str(x) for x in v if x not in (None, ""))
    return str(v)


def _rating(p):
    """Retail Product.rating → {average, count} or None."""
    r = getattr(p, "rating", None)
    try:
        if r and (r.average_rating or r.rating_count):
            return {"average": round(float(r.average_rating), 2), "count": int(r.rating_count)}
    except (AttributeError, TypeError, ValueError):
        pass
    return None


def summarize_product(product_id: str, p) -> dict:
    """Retail Product → widget-compatible productDetails item."""
    attrs = attrs_to_dict(getattr(p, "attributes", None))
    cats = list(getattr(p, "categories", []) or [])
    subtitle = cats[0].split(">")[-1].strip() if cats else (attrs.get("top_category") or "")
    pi = getattr(p, "price_info", None)
    price = _to_int(getattr(pi, "price", None)) if pi else None
    original = _to_int(getattr(pi, "original_price", None)) if pi else None
    if not original or (price and original < price):
        original = price
    on_sale_raw = attrs.get("on_sale")
    on_sale = str(on_sale_raw).lower() == "true" if on_sale_raw is not None else bool(price and original and price < original)
    promo = attrs.get("promo_text")
    if isinstance(promo, list):
        promo = " / ".join(promo)
    labels = attrs.get("labels") or []
    if isinstance(labels, str):
        labels = [labels]
    brands = list(getattr(p, "brands", []) or [])
    item = {
        "productId": product_id,
        "title": getattr(p, "title", "") or "",
        "subtitle": subtitle,
        "price": price or 0,
        "priceTaxExcluded": _to_int(attrs.get("price_tax_excluded")),
        "originalPrice": original or 0,
        "onSale": on_sale,
        "discountRate": float(attrs.get("discount_rate") or 0.0),
        "promoText": promo or "",
        "size": attrs.get("size") or "",
        "allergens": (" / ".join(a) if isinstance(a := attrs.get("allergens"), list) else (a or "")),
        "brand": brands[0] if brands else (attrs.get("brand_line") or ""),
        "topCategory": attrs.get("top_category") or (cats[0].split(">")[0].strip() if cats else ""),
        "labels": labels,
        "origin": _join(attrs.get("origin")),
        "material": _join(attrs.get("material")),
        "color": _join(attrs.get("color")),
        "capacity": _join(attrs.get("capacity")),
        "rating": _rating(p),
        "uri": getattr(p, "uri", "") or "",
        "imageUris": [img.uri for img in (getattr(p, "images", []) or []) if getattr(img, "uri", None)],
    }
    if COMPACT_RESULTS:
        # The agent never needs URLs/images (the page fetches them by ID); drop them and empty defaults to save tokens.
        for k in ("uri", "imageUris", "priceTaxExcluded", "subtitle"):
            item.pop(k, None)
        if not item["onSale"]:
            for k in ("onSale", "discountRate", "originalPrice"):
                item.pop(k, None)
        for k in ("promoText", "size", "brand", "labels", "origin", "material", "color", "capacity", "rating"):
            if not item.get(k):
                item.pop(k, None)
        if item.get("allergens") in ("", "なし"):
            item.pop("allergens", None)
    return item


def _needs_hydration(p) -> bool:
    return not (
        getattr(p, "title", None)
        and getattr(p, "images", None)
        and getattr(p, "uri", None)
        and getattr(p, "attributes", None)
        and "on_sale" in getattr(p, "attributes", {})
    )


def _hydrate(product_client, product_id, p, timeout):
    try:
        name = getattr(p, "name", None) or product_name(product_id)
        return product_client.get_product(name=name, timeout=max(0.5, timeout))
    except Exception as e:  # keep partial search data
        logger.warning("get_product failed for %s: %s", product_id, e)
        return p


def _is_invalid_argument(e: Exception) -> bool:
    try:
        from google.api_core import exceptions as gexc

        if isinstance(e, gexc.InvalidArgument):
            return True
    except Exception:
        pass
    return "INVALID_ARGUMENT" in str(e) or str(e).startswith("400")


def _do_search(query, page_size, filter_str, visitor_id):
    from google.cloud import retail_v2

    req = retail_v2.SearchRequest(
        placement=get_serving_config(),
        branch=f"{get_catalog_name()}/branches/{BRANCH}",
        query=query or "",
        page_size=page_size,
        filter=filter_str or "",
        visitor_id=visitor_id or DEFAULT_VISITOR_ID,
    )
    resp = _search_client().search(request=req, timeout=SEARCH_TIMEOUT_S)
    results = []
    total = 0
    for r in resp:  # pager — first page only (page_size <= 100)
        results.append(r)
        if len(results) >= page_size:
            break
    try:
        total = int(resp.total_size)
    except Exception:
        total = len(results)
    return results, total


def strip_price_phrase(query: str) -> str:
    """「300円以下のにんじん」→「にんじん」 (the phrase hurts text matching once it is a filter)."""
    q = PRICE_CAP_RE.sub(" ", query or "")
    q = re.sub(r"^[\sのでをと、]+|[\sのでをと、]+$", "", q)
    return re.sub(r"\s+", " ", q).strip()


SEARCH_BQ_FALLBACK = os.getenv("SEARCH_BQ_FALLBACK", "true").lower() == "true"
_ON_SALE_RE = re.compile(r'attributes\.on_sale:\s*ANY\("true"\)')
_CAT_RE = re.compile(r'categories:\s*ANY\("([^"]+)"\)')
_TOKEN_SPLIT = re.compile(r"[\s　、，,・/]+")


def _bq_row_to_product(row: dict):
    """cymbal.products row (Retail schema) → object compatible with summarize_product."""
    from types import SimpleNamespace as NS

    attrs = {}
    for a in row.get("attributes") or []:
        v = a.get("value") or {}
        attrs[a.get("key")] = NS(text=list(v.get("text") or []), numbers=list(v.get("numbers") or []))
    pi = row.get("priceInfo") or {}
    rt = row.get("rating") or {}
    return NS(
        name=product_name(row.get("id")), title=row.get("title") or "", categories=list(row.get("categories") or []),
        price_info=NS(price=pi.get("price"), original_price=pi.get("originalPrice")), attributes=attrs,
        images=[NS(uri=i.get("uri")) for i in row.get("images") or []], uri=row.get("uri") or "",
        description=row.get("description") or "", brands=list(row.get("brands") or []),
        availability=NS(name=row.get("availability") or "IN_STOCK"),
        rating=NS(average_rating=rt.get("averageRating") or 0.0, rating_count=rt.get("ratingCount") or 0),
    )


def bq_search_fallback(query: str, page_size: int, user_filter, price_cap) -> list:
    """Keyword search on BigQuery cymbal.products (used while the Retail index is still empty/lagging)."""
    from google.cloud import bigquery

    tokens = [t for t in _TOKEN_SPLIT.split(query or "") if t][:4]
    where, params = ["availability = 'IN_STOCK'"], []
    for i, t in enumerate(tokens):
        where.append(f"(STRPOS(title, @t{i}) > 0 OR STRPOS(ARRAY_TO_STRING(categories, ' '), @t{i}) > 0 "
                     f"OR STRPOS(ARRAY_TO_STRING(tags, ' '), @t{i}) > 0)")
        params.append(bigquery.ScalarQueryParameter(f"t{i}", "STRING", t))
    if price_cap:
        where.append("priceInfo.price <= @cap")
        params.append(bigquery.ScalarQueryParameter("cap", "FLOAT64", float(price_cap)))
    uf = user_filter or ""
    if _ON_SALE_RE.search(uf):
        where.append("priceInfo.price < priceInfo.originalPrice")
    m = _CAT_RE.search(uf)
    if m:
        where.append("STRPOS(ARRAY_TO_STRING(categories, ' '), @cat) > 0")
        params.append(bigquery.ScalarQueryParameter("cat", "STRING", m.group(1)))
    sql = (f"SELECT id, title, categories, brands, description, attributes, priceInfo, rating, availability, uri, images "
           f"FROM `{PROJECT_ID}.{BQ_DATASET}.products` WHERE {' AND '.join(where)} "
           f"ORDER BY rating.ratingCount DESC LIMIT {int(page_size)}")
    return [(r["id"], _bq_row_to_product(r)) for r in _bq_query(sql, params)]


def search_products_sync(query, page_size=20, filter=None, visitor_id=None) -> dict:
    t0 = time.monotonic()
    page_size = clamp_page_size(page_size)
    filter_str, price_cap = build_filter(filter, query)
    query_cap = extract_price_cap(query)
    if query_cap:
        query = strip_price_phrase(query)
    warning = None
    try:
        results, total = _do_search(query, page_size, filter_str, visitor_id)
    except Exception as e:
        if (filter or price_cap) and _is_invalid_argument(e):
            # retry once without the user / price filter (keep IN_STOCK)
            warning = f"filter '{filter_str}' was rejected by the catalog ({str(e)[:160]}); retried without it."
            logger.warning(warning)
            filter_str, price_cap = IN_STOCK_FILTER, query_cap  # cap still post-filtered
            results, total = _do_search(query, page_size, filter_str, visitor_id)
        else:
            raise

    details = []
    if results:
        remaining = max(0.5, HYDRATE_BUDGET_S - (time.monotonic() - t0))
        pc = _product_client()
        ex = ThreadPoolExecutor(max_workers=min(len(results), 20))
        futs = {}
        for r in results:
            if _needs_hydration(r.product):
                futs[r.id] = ex.submit(_hydrate, pc, r.id, r.product, remaining)
        if futs:
            wait(list(futs.values()), timeout=remaining)
        ex.shutdown(wait=False, cancel_futures=True)
        for r in results:
            f = futs.get(r.id)
            p = f.result() if (f is not None and f.done() and not f.cancelled()) else r.product
            item = summarize_product(r.id, p)
            if price_cap and item["price"] and item["price"] > price_cap:
                continue
            details.append(item)

    source = "retail"
    if not details and SEARCH_BQ_FALLBACK and (query or "").strip():
        try:
            for pid, p in bq_search_fallback(query, page_size, filter, price_cap or query_cap):
                details.append(summarize_product(pid, p))
            total = len(details)
            source = "bigquery_fallback"
        except Exception as e:  # never fail the tool because of the fallback
            logger.warning("BQ search fallback failed: %s", e)

    out = {"productDetails": details, "totalSize": total}
    if source != "retail":
        out["_source"] = source
    if price_cap:
        out["appliedPriceCap"] = price_cap
    if warning:
        out["warning"] = warning
    return out


# ── BigQuery / bundled-data helpers ──────────────────────────────────────────


def _find_data_file(name: str):
    for d in DATA_DIRS:
        p = Path(d) / name
        if p.exists():
            return p
    return None


def _load_personas() -> list:
    p = _find_data_file("personas.json")
    if not p:
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else [data]


def _load_history_rows() -> list:
    p = _find_data_file("purchase_history.jsonl")
    if not p:
        return []
    with p.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _bq_query(sql: str, params: list) -> list:
    from google.cloud import bigquery

    job = _bq_client().query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    return [dict(row.items()) for row in job.result(timeout=BQ_TIMEOUT_S)]


def _maybe_json(v):
    if isinstance(v, str) and v[:1] in "[{":
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def get_customer_profile_sync(customer_id: str) -> dict:
    from google.cloud import bigquery

    try:
        rows = _bq_query(
            f"SELECT * FROM `{PROJECT_ID}.{BQ_DATASET}.customers` WHERE customer_id = @cid LIMIT 1",
            [bigquery.ScalarQueryParameter("cid", "STRING", customer_id)],
        )
        if rows:
            prof = {k: _maybe_json(v) for k, v in rows[0].items()}
            # profile_json (full persona JSON written by seed/personas/load_to_bq.sh) wins over autodetected columns
            pj = prof.pop("profile_json", None)
            if isinstance(pj, dict):
                prof.update(pj)
            # fill fields missing in an older BQ table from the bundled persona (e.g. family_preferences)
            for bundled in _load_personas():
                if bundled.get("customer_id") == customer_id:
                    for k, v in bundled.items():
                        if prof.get(k) in (None, "", []):
                            prof[k] = v
            prof["_source"] = "bigquery"
            return prof
        logger.info("customer %s not found in BQ; trying bundled personas", customer_id)
    except Exception as e:
        logger.warning("BQ customers query failed (%s); using bundled personas.json", e)
    for prof in _load_personas():
        if prof.get("customer_id") == customer_id:
            return {**prof, "_source": "bundled"}
    return {"error": f"customer {customer_id} not found"}


def _summarize_history(rows: list, customer_id, month, year, limit) -> dict:
    rows = sorted(rows, key=lambda r: (str(r.get("order_date")), str(r.get("order_id"))), reverse=True)
    agg = {}
    for r in rows:
        a = agg.setdefault(
            r.get("product_id"),
            {"product_id": r.get("product_id"), "product_title": r.get("product_title"), "category": r.get("category"), "quantity": 0, "times": 0},
        )
        a["quantity"] += int(r.get("quantity") or 0)
        a["times"] += 1
    top = sorted(agg.values(), key=lambda a: (-a["times"], -a["quantity"]))[:15]
    orders = {r.get("order_id") for r in rows}
    return {
        "customerId": customer_id,
        "month": month,
        "year": year,
        "orderCount": len(orders),
        "totalRows": len(rows),
        "totalAmount": sum(int(r.get("amount") or 0) for r in rows),
        "topProducts": top,
        "purchases": [{k: (str(v) if k == "order_date" else v) for k, v in r.items()} for r in rows[:limit]],
    }


def parse_month(month):
    """10 / "10" → (10, None); "2025-10" / "2025/10" / "2025-10-01" → (10, 2025)."""
    if month is None or month == "":
        return None, None
    if isinstance(month, (int, float)):
        m = int(month)
        return (m if 1 <= m <= 12 else None), None
    s = str(month).strip().translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    mm = re.match(r"^(\d{4})\s*[-/年.]\s*(\d{1,2})", s)
    if mm:
        y, m = int(mm.group(1)), int(mm.group(2))
        return (m if 1 <= m <= 12 else None), y
    mm = re.match(r"^(\d{1,2})\s*月?$", s)
    if mm and 1 <= int(mm.group(1)) <= 12:
        return int(mm.group(1)), None
    raise ValueError(f"invalid month '{month}' (use 1-12 or 'YYYY-MM')")


def get_purchase_history_sync(customer_id: str, month=None, limit=30, year=None) -> dict:
    from google.cloud import bigquery

    limit = max(1, min(int(limit or 30), 200))
    month, parsed_year = parse_month(month)
    year = int(year) if year else parsed_year
    where = ["customer_id = @cid"]
    params = [bigquery.ScalarQueryParameter("cid", "STRING", customer_id)]
    if month:
        where.append("EXTRACT(MONTH FROM order_date) = @m")
        params.append(bigquery.ScalarQueryParameter("m", "INT64", month))
    if year:
        where.append("EXTRACT(YEAR FROM order_date) = @y")
        params.append(bigquery.ScalarQueryParameter("y", "INT64", year))
    sql = (
        "SELECT order_id, customer_id, order_date, product_id, product_title, category, quantity, "
        f"unit_price_tax_included, amount FROM `{PROJECT_ID}.{BQ_DATASET}.purchase_history` "
        f"WHERE {' AND '.join(where)} ORDER BY order_date DESC, order_id DESC LIMIT 1000"
    )
    source = "bigquery"
    try:
        rows = _bq_query(sql, params)
    except Exception as e:
        logger.warning("BQ purchase_history query failed (%s); using bundled JSONL", e)
        source = "bundled"
        rows = []
        for r in _load_history_rows():
            d = str(r.get("order_date", ""))
            if r.get("customer_id") != customer_id:
                continue
            if month and (len(d) < 7 or int(d[5:7]) != month):
                continue
            if year and (len(d) < 4 or int(d[:4]) != year):
                continue
            rows.append(r)
    out = _summarize_history(rows, customer_id, month, year, limit)
    out["_source"] = source
    return out


# ── comparison ──────────────────────────────────────────────────────────────

MAX_COMPARE = 4


def parse_product_ids(product_ids) -> list:
    """["a","b"] / "a,b" / "a b" / '["a","b"]' → unique ids (order kept, max MAX_COMPARE)."""
    if product_ids is None:
        return []
    if isinstance(product_ids, str):
        txt = product_ids.strip()
        if txt.startswith("["):
            try:
                product_ids = json.loads(txt)
            except ValueError:
                product_ids = re.split(r"[\s,、，]+", txt.strip("[]"))
        else:
            product_ids = re.split(r"[\s,、，]+", txt)
    out = []
    for x in product_ids:
        x = str(x).strip().strip('"\'')
        if x and x not in out:
            out.append(x)
    return out[:MAX_COMPARE]


def _yen(v) -> str:
    return f"¥{int(v):,}" if v else "-"


def _is_food(p, attrs: dict) -> bool:
    v = attrs.get("is_food")
    if v is not None:
        return str(v).lower() == "true"
    return bool(attrs.get("storage_type") or attrs.get("allergens"))


def build_comparison(items: list) -> dict:
    """items: [(product_id, retail Product)] → {title, product_ids, products, rows:[{label, values}]}.

    Rows (always): 価格（税込）, 内容量・サイズ, ラベル, 評価. Then 産地 for food, 素材 for general
    merchandise (both when mixed), plus optional ブランド / セール / カラー / 容量 / アレルゲン when present.
    """
    summaries, attrs_list, foods = [], [], []
    for pid, p in items:
        summaries.append(summarize_product(pid, p))
        a = attrs_to_dict(getattr(p, "attributes", None))
        attrs_list.append(a)
        foods.append(_is_food(p, a))

    def row(label, values, always=False):
        values = [v if v not in (None, "") else "-" for v in values]
        if always or any(v != "-" for v in values):
            rows.append({"label": label, "values": values})

    rows: list = []
    row("価格（税込）", [_yen(s.get("price")) + (f"（通常{_yen(s.get('originalPrice'))}）" if s.get("onSale") and s.get("originalPrice") and s.get("originalPrice") != s.get("price") else "") for s in summaries], True)
    row("内容量・サイズ", [s.get("size") for s in summaries], True)
    row("ラベル", [" / ".join(s.get("labels") or []) for s in summaries], True)
    row("評価", [f"★{s['rating']['average']:.1f}（{s['rating']['count']}件）" if s.get("rating") else "-" for s in summaries], True)
    if any(foods):
        row("産地", [s.get("origin") for s in summaries], True)
    if not all(foods):
        row("素材", [s.get("material") for s in summaries], True)
    row("ブランド", [s.get("brand") for s in summaries])
    row("容量", [s.get("capacity") for s in summaries])
    row("カラー", [s.get("color") for s in summaries])
    if any(foods):
        row("アレルゲン", [s.get("allergens") if f else "" for s, f in zip(summaries, foods)])
    row("セール", ["{}%OFF".format(int(round(s.get("discountRate") or 0))) if s.get("onSale") and s.get("discountRate") else "" for s in summaries])
    cats = {s.get("subtitle") or "" for s in summaries}
    title = f"{cats.pop()}の比較" if len(cats) == 1 and "" not in cats else "商品の比較"
    return {
        "title": title,
        "product_ids": [s["productId"] for s in summaries],
        "products": [{"productId": s["productId"], "title": s["title"], "price": s.get("price")} for s in summaries],
        "rows": rows,
    }


def compare_products_sync(product_ids) -> dict:
    ids = parse_product_ids(product_ids)
    if len(ids) < 2:
        return {"error": "compare_products needs 2-4 product_ids", "product_ids": ids, "rows": []}
    pc = _product_client()
    with ThreadPoolExecutor(max_workers=len(ids)) as ex:
        futs = {pid: ex.submit(pc.get_product, name=product_name(pid), timeout=4.0) for pid in ids}
    items, missing = [], []
    for pid in ids:
        try:
            items.append((pid, futs[pid].result()))
        except Exception as e:  # keep going with the others
            logger.warning("compare: get_product failed for %s: %s", pid, e)
            missing.append(pid)
    if len(items) < 2:
        return {"error": f"products not found: {missing}", "product_ids": [i for i, _ in items], "rows": []}
    out = build_comparison(items)
    if missing:
        out["missing"] = missing
    return out


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


# ── dinner set (CONTRACT v2: recommend_dinner_set) ──────────────────────────

DINNER_TOPS = ["野菜・果物", "お肉・お肉加工品", "お魚・水産加工品", "お惣菜・ミールキット", "豆腐・納豆・練り物",
               "卵・乳製品・豆乳・デザート", "冷凍食品・アイス", "お米・麺・インスタント"]
DINNER_EXTRA_CATS = r"コーン缶|カレールー|鍋つゆ|鍋の素"
DINNER_CATALOG_TTL_S = int(os.getenv("DINNER_CATALOG_TTL_S", "900"))
DINNER_BQ_TIMEOUT_S = float(os.getenv("DINNER_BQ_TIMEOUT_S", "25"))
DINNER_CATALOG_FILE = (
    os.getenv("DINNER_CATALOG_FILE")
    or os.getenv("CATALOG_JSONL")
    or str(_REPO_ROOT / "seed" / "catalog" / "products_retail.jsonl")
)
# Retail-search fallback queries (used only when BigQuery and the local catalog file are both unavailable).
DINNER_SEARCH_QUERIES = ["秋鮭 切り身", "塩さば", "さんま", "たら 切り身", "唐揚げ", "ハンバーグ", "豚こま", "鶏もも",
                         "豚バラ しゃぶしゃぶ", "鶏つくね", "ミールキット", "玉子焼き", "スイートコーン", "サラダ", "ほうれん草",
                         "しめじ", "白菜", "キャベツ", "みそ汁", "豆腐", "鍋つゆ", "中辛 カレールー", "カレー用", "パックご飯",
                         "うどん", "りんご", "柿", "みかん", "梨", "バナナ"]
_dinner_cache = {"at": 0.0, "items": None, "source": ""}
_dinner_lock = threading.Lock()


def _dinner_catalog_bq() -> list:
    from google.cloud import bigquery

    sql = (
        "SELECT id, title, categories, attributes, priceInfo, images, rating, availability, description "
        f"FROM `{PROJECT_ID}.{BQ_DATASET}.products` WHERE availability = 'IN_STOCK' AND ("
        "TRIM(SPLIT(categories[SAFE_OFFSET(0)], '>')[SAFE_OFFSET(0)]) IN UNNEST(@tops) "
        "OR REGEXP_CONTAINS(ARRAY_TO_STRING(categories, ' '), @extra))"
    )
    params = [bigquery.ArrayQueryParameter("tops", "STRING", DINNER_TOPS),
              bigquery.ScalarQueryParameter("extra", "STRING", DINNER_EXTRA_CATS)]
    job = _bq_client().query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    return [dinner.normalize_product(dict(r.items())) for r in job.result(timeout=DINNER_BQ_TIMEOUT_S)]


def _dinner_catalog_file() -> list:
    p = Path(DINNER_CATALOG_FILE)
    if not p.exists():
        return []
    out = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(dinner.normalize_product(json.loads(line)))
    return out


def _dinner_catalog_search() -> list:
    out = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(search_products_sync, q, 30, None, None) for q in DINNER_SEARCH_QUERIES]
        for f in futs:
            try:
                out += [dinner.normalize_summary(s) for s in f.result().get("productDetails", [])]
            except Exception as e:  # keep the others
                logger.warning("dinner search fallback failed: %s", e)
    return out


def _load_dinner_catalog() -> tuple:
    for source, fn in (("bigquery", _dinner_catalog_bq), ("file", _dinner_catalog_file), ("retail_search", _dinner_catalog_search)):
        try:
            items = [i for i in fn() if i]
        except Exception as e:
            logger.warning("dinner catalog via %s failed: %s", source, e)
            continue
        if items:
            logger.info("dinner catalog: %d items from %s", len(items), source)
            return items, source
    return [], "none"


def _refresh_dinner_catalog():
    if not _dinner_lock.acquire(blocking=False):
        return  # a refresh is already running
    try:
        items, source = _load_dinner_catalog()
        if items:
            _dinner_cache.update(at=time.monotonic(), items=items, source=source)
    finally:
        _dinner_lock.release()


def dinner_catalog() -> tuple:
    """(items, source) — BigQuery cymbal.products (cached, stale-while-revalidate), else local catalog file, else
    Retail search."""
    c = _dinner_cache
    if c["items"]:
        if time.monotonic() - c["at"] >= DINNER_CATALOG_TTL_S:
            threading.Thread(target=_refresh_dinner_catalog, daemon=True).start()
        return c["items"], c["source"]
    with _dinner_lock:  # cold: load synchronously (once)
        if not c["items"]:
            items, source = _load_dinner_catalog()
            if items:
                c.update(at=time.monotonic(), items=items, source=source)
    return (c["items"] or []), (c["source"] or "none")


def dinner_history_rows(customer_id: str) -> tuple:
    from google.cloud import bigquery

    try:
        rows = _bq_query(
            "SELECT product_id, ANY_VALUE(product_title) AS product_title, ANY_VALUE(category) AS category, "
            f"COUNT(*) AS times FROM `{PROJECT_ID}.{BQ_DATASET}.purchase_history` WHERE customer_id = @cid GROUP BY product_id",
            [bigquery.ScalarQueryParameter("cid", "STRING", customer_id)],
        )
        return rows, "bigquery"
    except Exception as e:
        logger.warning("BQ history aggregation failed (%s); using bundled JSONL", e)
        return [r for r in _load_history_rows() if r.get("customer_id") == customer_id], "bundled"


def recommend_dinner_set_sync(customer_id: str, request: str = "", budget_jpy=0, servings=0, today=None) -> dict:
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_prof = ex.submit(get_customer_profile_sync, customer_id)
        f_hist = ex.submit(dinner_history_rows, customer_id)
        f_cat = ex.submit(dinner_catalog)
        profile, (rows, hsrc), (catalog, csrc) = f_prof.result(), f_hist.result(), f_cat.result()
    if profile.get("error"):
        profile = {"customer_id": customer_id}
    if not catalog:
        return {"error": "catalog unavailable", "sets": []}
    res = dinner.recommend(profile, rows, catalog, request=request or "", budget_jpy=_int0(budget_jpy),
                           servings=_int0(servings), customer_id=customer_id, today=today)
    res["_source"] = {"profile": profile.get("_source", "none"), "history": hsrc, "catalog": csrc}
    if not res["sets"]:
        res["error"] = "no set could be composed (catalog too small or every candidate excluded)"
    return res


def _int0(v) -> int:
    try:
        return int(float(v)) if v not in (None, "") else 0
    except (TypeError, ValueError):
        return 0


if os.getenv("DINNER_WARM", "false").lower() == "true":  # warm the catalog cache on Cloud Run start-up
    threading.Thread(target=dinner_catalog, daemon=True).start()


# month accepts int (10) or "YYYY-MM"; schema stays a plain string for GECX.
MonthArg = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, (int, float)) else v)]
# product_ids accepts a JSON array or a comma separated string; schema stays array<string>.
IdsArg = Annotated[list[str], BeforeValidator(lambda v: parse_product_ids(v) if isinstance(v, str) else v)]

# ── MCP tools ────────────────────────────────────────────────────────────────


@mcp.tool()
async def search_products(query: str, page_size: int = 10, filter: str = None, visitor_id: str = None) -> str:
    """
    Cymbal Retail の商品カタログ（食品・日用品・キッチン用品・ビューティー・ペット用品・生活雑貨）を
    自然言語で検索します（最大100件、在庫ありのみ）。
    Search the Cymbal Retail catalog (Vertex AI Search for Commerce, servingConfigs/default_search).

    Args:
      query: 検索語（例: 「フライパン」「中辛 カレールー」「シャンプー」「キャットフード」）。
             「3000円以下」を含むと価格フィルタを自動付与。
      page_size: 取得件数 1-100（既定10、100超は100に丸め）。
      filter: Retail filter式（任意）。お買い得品は 'attributes.on_sale: ANY("true")'、
              価格上限は 'price: IN(*, 3000.0i)'、カテゴリは 'categories: ANY("キッチン・調理器具")'。
      visitor_id: 訪問者ID（パーソナライズ用、任意）。
    Returns JSON: {"productDetails":[{productId,title,price(税込),originalPrice,onSale,discountRate,promoText,
      size,allergens,brand,topCategory,labels,origin,material,color,capacity,rating}], "totalSize"}
    """
    try:
        res = await asyncio.to_thread(search_products_sync, query, page_size, filter, visitor_id)
        return _dumps(res)
    except Exception as e:
        logger.exception("search_products failed")
        return _dumps({"productDetails": [], "totalSize": 0, "error": f"search failed: {e}"})


@mcp.tool()
async def get_product_details(product_id: str) -> str:
    """
    商品IDの詳細（説明・産地/素材・アレルゲン・保存方法・内容量/サイズ・価格・画像・評価）を取得します。
    Get full details (description, all attributes incl. origin/material/allergens/storage, images, rating) for one product ID.
    """

    def _run():
        p = _product_client().get_product(name=product_name(product_id), timeout=4.0)
        out = summarize_product(product_id, p)
        rating = _rating(p)
        out.update(
            {
                "description": p.description or "",
                "brands": list(p.brands or []),
                "categories": list(p.categories or []),
                "availability": getattr(p.availability, "name", str(p.availability)),
                "attributes": attrs_to_dict(p.attributes),
                "rating": rating,
            }
        )
        return out

    try:
        return _dumps(await asyncio.to_thread(_run))
    except Exception as e:
        return _dumps({"error": f"Error finding product {product_id}: {e}"})


@mcp.tool()
async def compare_products(product_ids: IdsArg) -> str:
    """
    2〜4商品を比較するための比較表データを返します。結果の title / product_ids / rows はそのまま
    クライアント関数 show_comparison に渡せます。
    Compare 2-4 products. Returns {"title","product_ids","products":[{productId,title,price}],
      "rows":[{"label","values":[...]}]} — rows: 価格（税込）/内容量・サイズ/ラベル/評価/産地(食品)/素材(雑貨)
      (+ブランド/容量/カラー/アレルゲン/セール when available). values are in product_ids order.
    Args:
      product_ids: 比較する商品IDの配列（search_products の productId、2〜4件）。
    """
    try:
        return _dumps(await asyncio.to_thread(compare_products_sync, product_ids))
    except Exception as e:
        logger.exception("compare_products failed")
        return _dumps({"error": f"compare failed: {e}", "rows": []})


@mcp.tool()
async def get_customer_profile(customer_id: str) -> str:
    """
    顧客プロフィール（家族構成・好み・アレルギー・予算・配送希望・会員ランク）を取得します。
    Get the customer profile (household, taste, allergies, budget, delivery slot, loyalty). e.g. customer_id="CR-0001".
    アレルギー（例: えび）を含む商品は提案しないこと。
    """
    try:
        return _dumps(await asyncio.to_thread(get_customer_profile_sync, customer_id))
    except Exception as e:
        return _dumps({"error": f"profile lookup failed: {e}"})


@mcp.tool()
async def get_purchase_history(customer_id: str, month: MonthArg = None, limit: int = 50) -> str:
    """
    顧客の購入履歴を取得します（新しい順）。
    Get purchase history (newest first).
    Args:
      customer_id: 例 "CR-0001"
      month: 1-12（全年のその月）または "YYYY-MM"（特定の月）。「昨年の今頃」は昨年の今月 例 "2025-10"。
      limit: 返す明細の最大件数（既定50、最大200）。
    Returns JSON: {orderCount, totalAmount, topProducts[よく買う商品], purchases[order_id,order_date,product_id,
      product_title,category,quantity,unit_price_tax_included,amount]}
    """
    try:
        return _dumps(await asyncio.to_thread(get_purchase_history_sync, customer_id, month, limit))
    except Exception as e:
        return _dumps({"error": f"history lookup failed: {e}"})


IntArg = Annotated[int, BeforeValidator(_int0)]


@mcp.tool()
async def recommend_dinner_set(customer_id: str, request: str = "", budget_jpy: IntArg = 0, servings: IntArg = 0) -> str:
    """
    今夜の夕食・晩ご飯・献立・おかずの提案用に、「夕食の商品セット」（主菜・副菜・汁物・主食(必要時)・デザート/果物）を
    1案（メイン）＋別案最大2つ作ります。お客様の購入履歴（よく買う商品）、家族の好み（family_preferences）、
    アレルギー（例: えび）除外、今週の特価（on_sale）、旬の商品（is_seasonal）を組み合わせ、在庫あり・業務用サイズ除外。
    Compose dinner product sets for the customer (1 primary + up to 2 alternatives, 4-5 items each).
    Args:
      customer_id: 例 "CR-0001"
      request: お客様の要望の原文（例「お肉がいい」「魚で」「鍋にしたい」「時短で」「予算2000円」「2人分」）。無ければ空。
      budget_jpy: 予算（税込・円、任意。0 = 指定なし）。
      servings: 人数（任意。0 = 家族の人数）。
    Returns JSON: {theme, servings, signals:{frequent, family, sale_count, seasonal, excluded},
      sets:[{name, concept, items:[{role, product_id, title, price, quantity, subtotal, image, tags, reason}],
      total_tax_included}], show_products_on_page_args:{message, theme, product_ids, reasons, sections}}
      show_products_on_page_args はメイン案をそのまま show_products_on_page に渡せる形です。
    """
    try:
        return _dumps(await asyncio.to_thread(recommend_dinner_set_sync, customer_id, request, budget_jpy, servings))
    except Exception as e:
        logger.exception("recommend_dinner_set failed")
        return _dumps({"error": f"dinner set failed: {e}", "sets": []})


app = mcp.streamable_http_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), proxy_headers=True, forwarded_allow_ips="*")
