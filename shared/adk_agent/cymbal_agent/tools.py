"""ADK function tools: MCP-backed commerce tools + page-action tools (CONTRACT client functions).

Page-action tools compute results server-side on the per-session ShopState (seeded each turn from the
request `page_state`) and record an action {name,args,result}; server.py streams these as `action` SSE
events in order so the page applies the identical change.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from google.adk.tools import ToolContext

from . import mcp_client
from .shop import Catalog, ShopState

logger = logging.getLogger("cymbal_agent.tools")

CATALOG = Catalog.load()
STATES: dict[str, ShopState] = {}
MAX_SEARCHES_PER_TURN = 3
DEFAULT_EXCLUDE = ["えび", "エビ", "海老", "シュリンプ"]


def shop_state(session_id: str) -> ShopState:
  st = STATES.get(session_id)
  if st is None:
    st = STATES[session_id] = ShopState()
  return st


def _st(ctx: ToolContext) -> ShopState:
  return shop_state(ctx.session.id)


def _customer_id(ctx: ToolContext) -> str:
  return str(ctx.state.get("customer_id") or "")


def _exclude_keywords(ctx: ToolContext) -> list[str]:
  kws = ctx.state.get("exclude_keywords")
  return list(kws) if isinstance(kws, list) else []


def _has_excluded(p: dict[str, Any], kws: list[str]) -> bool:
  if not kws:
    return False
  hay = " ".join(str(p.get(k) or "") for k in ("title", "allergens", "description"))
  if isinstance(p.get("allergens"), list):
    hay += " " + " ".join(map(str, p["allergens"]))
  return any(k in hay for k in kws)


# ── MCP-backed tools ─────────────────────────────────────────────────────────────────────────


async def search_products(query: str, tool_context: ToolContext, page_size: int = 20,
                          filter: str = "") -> dict[str, Any]:
  """Cymbal Retail のカタログを検索します（在庫ありのみ・price は税込円）。

  Args:
    query: カタログでヒットしやすい短い語（1〜3語）。例「フライパン」「中辛 カレールー」「シャンプー 詰め替え」。
      「3000円以下」を含めると価格フィルタになります。
    page_size: 取得件数（10〜30、既定 20）。
    filter: 任意の Retail filter 式。お買い得品は attributes.on_sale: ANY("true")。

  Returns:
    {productDetails:[{productId,title,price,originalPrice,onSale,size,brand,topCategory,labels,rating,...}],
     totalSize, excluded_by_allergy}。1 回の発言につき合計 3 回まで。
  """
  st = _st(tool_context)
  st.search_count += 1
  if st.search_count > MAX_SEARCHES_PER_TURN:
    return {"error": "SEARCH_LIMIT", "message": "この発言での検索は 3 回までです。見つからなかったことをお客様に伝えてください。"}
  args = {"query": query, "page_size": max(5, min(int(page_size or 20), 30))}
  if filter:
    args["filter"] = filter
  vid = tool_context.state.get("visitor_id")
  if vid:
    args["visitor_id"] = vid
  res = await mcp_client.call_tool("search_products", args)
  if isinstance(res, dict) and isinstance(res.get("productDetails"), list):
    kws = _exclude_keywords(tool_context)
    kept, dropped = [], 0
    for p in res["productDetails"]:
      if _has_excluded(p, kws):
        dropped += 1
        continue
      p.pop("image", None)
      p.pop("uri", None)
      kept.append(p)
    res["productDetails"] = kept
    res["excluded_by_allergy"] = dropped
  st.last_search = res
  return res


async def get_product_details(product_id: str) -> dict[str, Any]:
  """商品の詳細（説明・産地/素材・アレルゲン・保存方法・内容量・価格・評価）を取得します。

  Args:
    product_id: 検索結果などに含まれていた productId。
  """
  res = await mcp_client.call_tool("get_product_details", {"product_id": product_id})
  if isinstance(res, dict):
    res.pop("images", None)
  return res


async def get_purchase_history(tool_context: ToolContext, month: str = "", limit: int = 30) -> dict[str, Any]:
  """お客様の購入履歴（よく買う商品 topProducts を含む）を取得します。定番品の再購入提案に使います。

  Args:
    month: 任意。「10」や「2026-10」。空なら直近。
    limit: 最大件数（既定 30）。
  """
  return await mcp_client.call_tool("get_purchase_history", {
      "customer_id": _customer_id(tool_context), "month": month or "", "limit": int(limit or 30)})


async def compare_products(product_ids: list[str], tool_context: ToolContext, title: str = "") -> dict[str, Any]:
  """2〜4 商品の比較表を作り、そのままページに比較表（show_comparison）を表示します。

  Args:
    product_ids: 比較する productId（2〜4件、表示順）。「上位3つ」なら直前に表示した順の先頭 3 件。
    title: 任意。比較表のタイトル（例「フライパンの比較」）。

  Returns:
    {displayed: true, title, products:[{productId,title,price}], rows:[{label,values}]}。
    表は既にページに表示済みなので show_comparison を別途呼ぶ必要はありません。
  """
  ids = [str(x) for x in (product_ids or []) if x][:4]
  res = await mcp_client.call_tool("compare_products", {"product_ids": ids})
  if not isinstance(res, dict) or res.get("error") or not res.get("rows"):
    return res if isinstance(res, dict) else {"error": "compare failed"}
  args = {"title": title or res.get("title") or "商品の比較",
          "product_ids": res.get("product_ids") or ids, "rows": res.get("rows")}
  _st(tool_context).show_comparison(args)
  return {"displayed": True, **{k: res.get(k) for k in ("title", "products", "rows")}, "title": args["title"]}


def _set_show_args(dinner: dict[str, Any], idx: int) -> Optional[dict[str, Any]]:
  sets = dinner.get("sets") or []
  if not (0 <= idx < len(sets)):
    return None
  s = sets[idx]
  args = s.get("show_products_on_page_args") or (dinner.get("show_products_on_page_args") if idx == 0 else None)
  if not args:  # build from items
    items = s.get("items") or []
    sections: list[dict[str, Any]] = []
    for it in items:
      sec = next((x for x in sections if x["label"] == it.get("role")), None)
      if sec is None:
        sec = {"label": it.get("role") or "", "product_ids": [], "reasons": [], "tags": [], "quantities": []}
        sections.append(sec)
      sec["product_ids"].append(it["product_id"])
      sec["reasons"].append(it.get("reason") or "")
      sec["tags"].append(it.get("tags") or [])
      sec["quantities"].append(int(it.get("quantity") or 1))
    args = {"message": f"{s.get('name')}（{int(s.get('total_tax_included') or 0):,}円・税込）",
            "theme": dinner.get("theme") or s.get("name"),
            "product_ids": [it["product_id"] for it in items],
            "reasons": [it.get("reason") or "" for it in items],
            "quantities": [int(it.get("quantity") or 1) for it in items],
            "sections": sections}
  return json.loads(json.dumps(args, ensure_ascii=False))


def _compact_dinner(dinner: dict[str, Any], shown_idx: int) -> dict[str, Any]:
  return {
      "theme": dinner.get("theme"),
      "servings": dinner.get("servings"),
      "excluded": (dinner.get("signals") or {}).get("excluded"),
      "displayed_set_index": shown_idx,
      "sets": [{
          "index": i, "name": s.get("name"), "concept": s.get("concept"),
          "total_tax_included": s.get("total_tax_included"),
          "items": [{k: it.get(k) for k in ("role", "title", "price", "quantity", "tags", "reason")}
                    for it in s.get("items") or []],
      } for i, s in enumerate(dinner.get("sets") or [])],
  }


async def recommend_dinner_set(tool_context: ToolContext, request: str = "", budget_jpy: int = 0,
                               servings: int = 0) -> dict[str, Any]:
  """夕食・献立の相談用に「夕食の商品セット」（メイン 1 案＋別案最大 2 つ）を作り、メイン案をページに表示します。

  家族の好み・アレルギー除外・よく購入する商品・特価・旬を自動反映します。結果のメイン案（sets[0]）は
  show_products_on_page（theme / sections / quantities 付き）として既にページに表示済みです。

  Args:
    request: お客様の発言の原文（例「今夜の夕食をお勧めしてね」「お肉がいい」「鍋にしたい」）。
    budget_jpy: 予算（税込円、0 = 指定なし）。
    servings: 人数（0 = 家族の人数）。
  """
  st = _st(tool_context)
  res = await mcp_client.call_tool("recommend_dinner_set", {
      "customer_id": _customer_id(tool_context), "request": request or "",
      "budget_jpy": int(budget_jpy or 0), "servings": int(servings or 0)})
  if not isinstance(res, dict) or res.get("error") or not res.get("sets"):
    return res if isinstance(res, dict) else {"error": "dinner set failed", "sets": []}
  st.last_dinner = res
  st.current_set_index = 0
  args = _set_show_args(res, 0)
  if args:
    st.show_products(args)
  return _compact_dinner(res, 0)


async def show_dinner_set(set_index: int, tool_context: ToolContext) -> dict[str, Any]:
  """直前の recommend_dinner_set の別案（sets[set_index]）をページに表示します（「別の案」のとき）。

  Args:
    set_index: 表示するセットの index（1 または 2）。
  """
  st = _st(tool_context)
  if not st.last_dinner:
    return {"error": "NO_DINNER_SET", "message": "先に recommend_dinner_set を呼んでください。"}
  args = _set_show_args(st.last_dinner, int(set_index))
  if not args:
    return {"error": "NO_SUCH_SET", "available": len(st.last_dinner.get("sets") or [])}
  st.current_set_index = int(set_index)
  st.show_products(args)
  s = st.last_dinner["sets"][int(set_index)]
  return {"shown": len(args["product_ids"]), "set": _compact_dinner(st.last_dinner, int(set_index))["sets"][int(set_index)],
          "name": s.get("name")}


async def add_dinner_set_to_cart(tool_context: ToolContext, set_index: int = -1) -> dict[str, Any]:
  """表示中の夕食セットの全商品を、セットの数量どおりにカートへ追加します（商品ごとに add_to_cart を実行）。

  Args:
    set_index: 追加するセットの index。-1（既定）なら現在ページに表示中のセット。
  """
  st = _st(tool_context)
  if not st.last_dinner:
    return {"ok": False, "error": "NO_DINNER_SET"}
  idx = st.current_set_index if int(set_index) < 0 else int(set_index)
  sets = st.last_dinner.get("sets") or []
  if idx is None or not (0 <= idx < len(sets)):
    return {"ok": False, "error": "NO_SUCH_SET"}
  added = []
  last: dict[str, Any] = {}
  for it in sets[idx].get("items") or []:
    last = st.add_to_cart(CATALOG, it["product_id"], int(it.get("quantity") or 1),
                          title_hint=it.get("title") or "", price_hint=int(it.get("price") or 0))
    added.append({"title": last.get("title"), "quantity": int(it.get("quantity") or 1), "ok": last.get("ok")})
  return {"ok": all(a["ok"] for a in added), "set_name": sets[idx].get("name"), "added": added,
          "items_added": len(added), "cart_count": st.count(), "cart_total_tax_included": st.subtotal()}


# ── Page-action tools (names = CONTRACT client functions) ─────────────────────────────────────


async def show_products_on_page(message: str, product_ids: list[str], reasons: list[str],
                                tool_context: ToolContext, theme: str = "") -> dict[str, Any]:
  """おすすめ商品をページのメイン画面に理由バッジ付きで表示します（通常の検索結果のおすすめ用）。

  Args:
    message: グリッド上の見出し（60文字程度まで）。例「さくらさんにおすすめのフライパン」。
    product_ids: 検索結果に含まれていた productId をおすすめ順に（通常 4〜8件、最大 24件）。
    reasons: product_ids と同じ順番・同じ件数のおすすめ理由（各30文字程度）。
    theme: 任意。テーマ見出し。
  """
  st = _st(tool_context)
  ids = [str(x) for x in (product_ids or []) if x][:24]
  rs = [str(r) for r in (reasons or [])][:len(ids)]
  rs += [""] * (len(ids) - len(rs))
  args: dict[str, Any] = {"message": message, "product_ids": ids, "reasons": rs}
  if theme:
    args["theme"] = theme
  if ids and ids == st.last_shown_ids and any(a["name"] == "show_products_on_page" for a in st.actions):
    return {"shown": len(ids)}
  return st.show_products(args)


async def show_comparison(title: str, product_ids: list[str], rows: list[dict[str, Any]],
                          tool_context: ToolContext) -> dict[str, Any]:
  """独自の比較表をページに表示します。compare_products を使った場合は表示済みなので呼びません。

  Args:
    title: 比較表タイトル。
    product_ids: 2〜4件の productId。
    rows: [{label: str, values: [str]}]（values は product_ids と同じ順番・件数）。
  """
  return _st(tool_context).show_comparison({"title": title, "product_ids": product_ids, "rows": rows})


async def add_to_cart(product_id: str, tool_context: ToolContext, quantity: int = 1) -> dict[str, Any]:
  """指定した商品をカートに追加します（ページのカートに反映）。複数商品は商品ごとに呼びます。

  Args:
    product_id: 会話中のツール結果に含まれていた productId。
    quantity: 数量（既定 1）。
  """
  return _st(tool_context).add_to_cart(CATALOG, product_id, quantity)


async def get_cart(tool_context: ToolContext) -> dict[str, Any]:
  """現在のカートの中身（明細・点数・税込合計）を取得し、チャットにカートカードを表示します。"""
  return _st(tool_context).get_cart()


async def start_checkout(tool_context: ToolContext) -> dict[str, Any]:
  """ご注文手続きを開始し、選択可能な配送枠（slots）を返します。カートが空なら ok=false, error=EMPTY_CART。"""
  return _st(tool_context).start_checkout()


async def select_delivery_slot(slot_id: str, tool_context: ToolContext) -> dict[str, Any]:
  """配送枠を選択し、お支払い方法と送料込みのお支払い総額を返します（next=confirm）。

  Args:
    slot_id: d1_am（明日 9:00-12:00）/ d1_pm（明日 14:00-17:00）/ d1_eve（明日 18:00-21:00）/
      d2_am（明後日 9:00-12:00）/ d2_pm（明後日 14:00-17:00）のいずれか。
  """
  return _st(tool_context).select_delivery_slot(slot_id)


async def place_order(tool_context: ToolContext) -> dict[str, Any]:
  """注文を確定します。配送枠・お支払い方法・総額を提示したあと、お客様が明確に同意した場合にだけ呼びます。"""
  return _st(tool_context).place_order()


async def get_order_status(tool_context: ToolContext, order_id: str = "") -> dict[str, Any]:
  """注文の配送状況（status / status_label / eta）を取得し、ページに注文タイムラインを表示します。

  Args:
    order_id: 任意。注文番号（省略時は直近の注文）。
  """
  return _st(tool_context).get_order_status(order_id or "")


ALL_TOOLS = [
    search_products, get_product_details, get_purchase_history, compare_products,
    recommend_dinner_set, show_dinner_set, add_dinner_set_to_cart,
    show_products_on_page, show_comparison, add_to_cart, get_cart, start_checkout,
    select_delivery_slot, place_order, get_order_status,
]

STATUS_LABELS = {
    "search_products": "商品を検索しています…",
    "get_product_details": "商品の詳細を確認しています…",
    "get_purchase_history": "いつものお買い物を確認しています…",
    "compare_products": "比較表を作成しています…",
    "recommend_dinner_set": "ご家族に合う夕食セットを考えています…",
    "show_dinner_set": "別の案を表示しています…",
    "add_dinner_set_to_cart": "セットをカートに入れています…",
    "show_products_on_page": "おすすめ商品を表示しています…",
    "show_comparison": "比較表を表示しています…",
    "add_to_cart": "カートに追加しています…",
    "get_cart": "カートを確認しています…",
    "start_checkout": "ご注文手続きを準備しています…",
    "select_delivery_slot": "お届け日時を設定しています…",
    "place_order": "ご注文を確定しています…",
    "get_order_status": "配送状況を確認しています…",
}
