"""Store concierge tools (ADK function tools) + server-side builder for the `show_store_items` client action.

MCP tools (cymbal-commerce-mcp via ID token; fallback: AICS / local catalog directly):
  search_products, get_product_details
Local tools: check_availability
Client actions (recorded per turn → streamed as SSE `action` / `chips`): show_store_items, suggest_replies
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Optional, TypedDict

from google.adk.tools import ToolContext

from .. import config, deps, inventory, layout, offers, stores
from . import mcp_client, safety

log = logging.getLogger("store-navi.agent.tools")

MAX_SEARCHES_PER_TURN = 4
IN_STOCK = ("in_stock", "low_stock")
STATUS_JA = {"in_stock": "在庫あり", "low_stock": "残りわずか", "out_of_stock": "在庫なし", "not_carried": "取扱いなし"}


class StoreItem(TypedDict, total=False):
    """One recommended product: product_id (from search results), role (e.g. 解熱鎮痛薬 / 冷却シート), reason (~30 chars)."""
    product_id: str
    role: str
    reason: str


class TurnState:
    """Per-session state for the store concierge (seeded every turn by runner.py)."""

    def __init__(self) -> None:
        self.store_id = config.DEFAULT_STORE
        self.customer_id = config.DEFAULT_CUSTOMER
        self.flags: list[dict] = []
        self.abuse: list[str] = []
        self.age: float | None = None
        self.actions: list[dict] = []
        self.chips: list[str] = []
        self.search_count = 0
        self.last_items: list[dict] = []
        self.page_state: dict = {}

    def begin(self, store_id: str, customer_id: str, message: str, page_state: dict | None) -> None:
        self.store_id = store_id or self.store_id
        self.customer_id = customer_id or self.customer_id
        new_flags = safety.detect_red_flags(message)
        self.flags = new_flags
        self.abuse = safety.detect_abuse(message)
        age = safety.child_age(message)
        if age is not None:
            self.age = age
        self.actions = []
        self.chips = []
        self.search_count = 0
        self.page_state = page_state or {}

    def drain(self) -> list[dict]:
        out, self.actions = self.actions, []
        return out


_STATES: dict[str, TurnState] = {}
_lock = threading.Lock()


def turn_state(session_id: str) -> TurnState:
    with _lock:
        st = _STATES.get(session_id)
        if st is None:
            if len(_STATES) > 2000:
                _STATES.clear()
            st = _STATES[session_id] = TurnState()
        return st


def _st(ctx) -> TurnState:
    return turn_state(ctx.session.id)


def mcp_enabled() -> bool:
    if (os.environ.get("MCP_URL") or "").strip().lower() in ("off", "none", "0"):
        return False
    return bool(os.environ.get("MCP_URL")) or config.data_mode() == "bq"


# ---------------------------------------------------------------------------------------------- helpers
def _shelf_text(sh: dict | None) -> str | None:
    """「A01 かぜ薬 ・ A01-203（2段目・左から3番目）」 for the model."""
    if not sh:
        return None
    if sh.get("counter"):
        return "医薬品カウンター（レジでお渡し）"
    lab = f"{sh.get('fixture_id') or sh.get('gondola_id')} {sh.get('fixture_label') or ''}".strip()
    return f"{lab} ・ {sh['slot_label']}" if sh.get("slot_label") else (sh.get("label") or lab)


def _compact(p: dict, store_id: str) -> dict:
    inv = inventory.inventory_for(store_id, p["id"])
    out = {"product_id": p["id"], "title": p.get("title"), "price": p.get("price"),
           "category": p.get("category_path") or p.get("category"),
           "stock_here": STATUS_JA[inv["status"] if inv else "not_carried"],
           "qty_here": inv["quantity"] if inv else 0}
    if p.get("drug_class"):
        out.update(drug_class=p["drug_class"], symptoms=p.get("symptoms") or [], age_min=p.get("age_min"),
                   abuse_control=bool(p.get("abuse_control")))
    if p.get("on_sale"):
        out["on_sale"] = True
    return out


def _local_search(query: str, page_size: int, store_id: str) -> list[dict]:
    try:
        res = deps.get_engine().search(query, "", {}, [], "", "", "", "", 1, page_size, "store-navi-agent", query)
        ids = [r["id"] for r in res.get("results") or []]
    except Exception as e:  # noqa: BLE001
        log.warning("engine search failed: %s", e)
        ids = [n["id"] for _, n in deps.get_catalog().text_search(query)[:page_size]]
    if not ids or query.strip() in deps.SYNONYMS:
        ids = list(dict.fromkeys(deps.symptom_search(query, page_size) + ids))[:page_size]
    return [p for p in deps.hydrate(ids)]


# ---------------------------------------------------------------------------------------------- tools
async def search_products(query: str, tool_context: ToolContext, page_size: int = 12) -> dict[str, Any]:
    """Cymbal Retail のカタログ（医薬品・ヘルスケア、日用品、ビューティー、飲料など）を検索します。

    Args:
      query: ヒットしやすい短い語（1〜3語）。例「解熱鎮痛薬」「冷却シート 子ども用」「経口補水液」「目薬 疲れ目」。
      page_size: 取得件数（5〜20、既定 12）。

    Returns:
      {products:[{product_id,title,price,category,stock_here(この店舗の在庫),qty_here,drug_class,symptoms,age_min,
       abuse_control}], source}。1 回の発言につき合計 4 回まで。
    """
    st = _st(tool_context)
    st.search_count += 1
    if st.search_count > MAX_SEARCHES_PER_TURN:
        return {"error": "SEARCH_LIMIT", "message": "この発言での検索は上限です。見つかった範囲でご案内してください。"}
    n = max(5, min(int(page_size or 12), 20))
    products: list[dict] = []
    source = "mcp"
    if mcp_enabled():
        res = await mcp_client.call_tool("search_products", {"query": query, "page_size": n})
        if isinstance(res, dict) and isinstance(res.get("productDetails"), list) and res["productDetails"]:
            ids = [str(p.get("productId") or p.get("id")) for p in res["productDetails"]]
            local = {p["id"]: p for p in deps.hydrate(ids)}
            for raw in res["productDetails"]:
                pid = str(raw.get("productId") or raw.get("id"))
                if pid in local:
                    products.append(local[pid])
                else:
                    products.append({"id": pid, "title": raw.get("title"), "price": raw.get("price"),
                                     "category_path": raw.get("topCategory") or ""})
        else:
            log.info("MCP search fallback (%s)", str(res)[:160])
    if not products:
        source = "aics" if deps.get_engine().mode == "retail" else "local"
        import asyncio

        products = await asyncio.to_thread(_local_search, query, n, st.store_id)
    items = [_compact(p, st.store_id) for p in products[:n]]
    # in-stock at this store first (relevance order kept within each group)
    items.sort(key=lambda x: x["stock_here"] not in ("在庫あり", "残りわずか"))
    return {"products": items, "source": source, "store": (stores.get_store(st.store_id) or {}).get("short_name")}


async def get_product_details(product_id: str, tool_context: ToolContext) -> dict[str, Any]:
    """商品の詳細（説明・医薬品区分 drug_class・効能の範囲 symptoms・対象年齢 age_min・内容量・価格）を取得します。

    Args:
      product_id: search_products の結果にあった product_id。
    """
    st = _st(tool_context)
    p = deps.to_product(product_id)
    out: dict[str, Any] = {}
    if mcp_enabled():
        res = await mcp_client.call_tool("get_product_details", {"product_id": product_id})
        if isinstance(res, dict) and not res.get("error"):
            out.update({k: v for k, v in res.items() if k not in ("images", "image", "uri")})
    if p:
        out.update({"product_id": p["id"], "title": p.get("title"), "price": p.get("price"),
                    "description": (p.get("description") or "")[:400], "size": p.get("size"),
                    "drug_class": p.get("drug_class") or None, "symptoms": p.get("symptoms") or [],
                    "age_min": p.get("age_min"), "abuse_control": bool(p.get("abuse_control")),
                    "stock_here": _compact(p, st.store_id)["stock_here"]})
    return out or {"error": "NOT_FOUND"}


async def check_availability(product_ids: list[str], tool_context: ToolContext) -> dict[str, Any]:
    """商品の在庫を「この店舗 → 近隣店舗 → オンライン」の順で確認します（棚の位置つき）。

    Args:
      product_ids: 確認する product_id（最大 8 件）。
    """
    st = _st(tool_context)
    out = []
    for pid in [str(x) for x in (product_ids or []) if x][:8]:
        p = deps.to_product(pid)
        if not p:
            continue
        av = inventory.get_availability(pid, st.store_id, p)
        cur = av["current"] or {}
        out.append({"product_id": pid, "title": p.get("title"),
                    "here": {"store": cur.get("short_name"), "status": STATUS_JA.get(cur.get("status"), ""),
                             "qty": cur.get("quantity"), "shelf": _shelf_text(cur.get("shelf"))},
                    "nearby": [{"store": n["short_name"], "status": STATUS_JA.get(n["status"], ""),
                                "distance_km": round(n["distance_m"] / 1000, 1), "open_now": n["open_now"]}
                               for n in av["nearby"]],
                    "online": {"available": av["online"]["available"], "price": av["online"]["price"]}})
    return {"items": out}


def build_store_items(store_id: str, customer_id: str, theme: str, advice: str, items: list[dict],
                      flags: list[dict], age: float | None = None, red_flag: bool = False,
                      abuse: bool = False) -> tuple[dict, dict]:
    """Server-side enrichment for the show_store_items action. Returns (action_args, summary_for_model)."""
    resolved = []
    for it in items or []:
        if not isinstance(it, dict):
            it = it.model_dump() if hasattr(it, "model_dump") else dict(it)
        pid = str((it or {}).get("product_id") or "")
        p = deps.to_product(pid) if pid else None
        if not p:
            continue
        if any(r["product"]["id"] == pid for r in resolved):
            continue
        resolved.append({"product_id": pid, "role": str(it.get("role") or ""), "reason": str(it.get("reason") or ""),
                         "product": p})
    flags = list(flags or [])
    if red_flag and not flags:
        flags = [{"code": "model", "level": "consult", "label": "受診が必要な可能性"}]
    kept, notes = safety.filter_items(resolved, flags, age, abuse=abuse)
    route_stops = []
    for it in kept:
        av = inventory.get_availability(it["product_id"], store_id, it["product"])
        it["availability"] = av
        it["notes"] = safety.compliance_notes(it["product"])
        it["limits"] = safety.item_limits(it["product"])
        cur = av.get("current") or {}
        it["in_store"] = cur.get("status") in IN_STOCK and bool(cur.get("shelf"))
        if it["in_store"]:
            sh = cur["shelf"]
            route_stops.append({"product_id": it["product_id"], "fixture_id": sh.get("fixture_id") or sh["gondola_id"],
                                "slot_ids": sh.get("slot_ids") or [], "primary_slot": sh.get("primary_slot"),
                                "side": sh.get("side"), "tier": sh.get("tier"), "position": sh.get("position")})
    route = layout.plan_route(store_id, route_stops) if route_stops else None
    order = {s["product_id"]: s["no"] for s in (route or {}).get("stops") or []}
    for it in kept:
        it["no"] = order.get(it["product_id"])
    kept.sort(key=lambda it: (it["no"] is None, it["no"] or 0))
    store = stores.get_store(store_id) or {}
    persona = offers.get_persona(customer_id)
    args = {"theme": theme or "おすすめの商品", "advice": advice or "", "red_flag": bool(red_flag or safety.is_blocking(flags)),
            "items": [{k: it[k] for k in ("no", "product_id", "role", "reason", "product", "availability", "notes",
                                           "limits", "in_store")} for it in kept],
            "route": route, "disclaimer": safety.DISCLAIMER, "store_id": store_id,
            "store_name": store.get("short_name") or store.get("name"),
            "customer_name": persona.get("name"), "removed_by_safety": len(resolved) - len(kept)}
    summary = {"shown": len(kept), "removed_by_safety": len(resolved) - len(kept),
               "items": [{"no": it["no"], "title": it["product"].get("title"),
                          "here": STATUS_JA.get((it["availability"].get("current") or {}).get("status"), ""),
                          "shelf": _shelf_text((it["availability"].get("current") or {}).get("shelf")),
                          "nearby_in_stock": [n["short_name"] for n in it["availability"]["nearby"] if n["status"] in IN_STOCK],
                          "online": it["availability"]["online"]["available"]} for it in kept],
               "route_length_m": (route or {}).get("length_m"),
               "safety_notes": notes[:5]}
    return args, summary


async def show_store_items(theme: str, advice: str, items: list[StoreItem], tool_context: ToolContext,
                           red_flag: bool = False) -> dict[str, Any]:
    """おすすめ商品セットを画面にカード表示し、店内の棚の位置と回る順番（①②③）・経路を表示します。

    Args:
      theme: 見出し（例「発熱・かぜの初期症状のセルフケア」）。
      advice: カード上部に出す一般的なセルフケアのアドバイス（2〜3 行、診断はしない）。
      items: [{product_id, role, reason}]（2〜5 件）。role は「解熱鎮痛薬」「冷却シート」「水分補給」など、reason は 30 文字程度。
        医薬品は 1 つの症状群につき 1 品まで。残りは非医薬品のサポート用品。
      red_flag: 受診勧奨が必要な相談なら true（医薬品は表示されません）。

    Returns:
      {shown, items:[{no(回る順番。店内に在庫が無い商品は null), title, here, shelf, nearby_in_stock, online}],
       route_length_m, removed_by_safety}
    """
    st = _st(tool_context)
    args, summary = build_store_items(st.store_id, st.customer_id, theme, advice, items, st.flags, st.age, red_flag,
                                      abuse=bool(st.abuse))
    st.actions.append({"type": "action", "name": "show_store_items", "args": args, "result": {"ok": True,
                                                                                            "shown": summary["shown"]}})
    st.last_items = args["items"]
    return summary


async def suggest_replies(items: list[str], tool_context: ToolContext) -> dict[str, Any]:
    """返答の最後に、お客様が次にタップできる短い返信候補（2〜4 個、各 15 文字以内）を表示します。

    Args:
      items: 返信候補の文言。例「まとめて棚を探す」「子ども用はある？」「近くの店舗の在庫は？」。
    """
    st = _st(tool_context)
    st.chips = [str(x)[:24] for x in (items or []) if str(x).strip()][:4]
    return {"ok": True}


ALL_TOOLS = [search_products, get_product_details, check_availability, show_store_items, suggest_replies]
STATUS_LABELS = {
    "search_products": "商品を探しています…",
    "get_product_details": "商品の詳細を確認しています…",
    "check_availability": "在庫を確認しています…",
    "show_store_items": "売場と回る順番を準備しています…",
}
