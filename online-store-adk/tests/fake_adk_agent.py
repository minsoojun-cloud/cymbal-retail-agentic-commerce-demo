"""Fake ADK agent service for local E2E of the LIVE chat path (SSE), no Gemini needed.

  DATA_FILE=../seed/catalog/products_retail.jsonl uvicorn tests.fake_adk_agent:app --port 8091   (from online-store-adk)
  ADK_AGENT_URL=http://127.0.0.1:8091 uvicorn app.main:app --port 8092                            (from online-store-adk)

POST /api/chat/stream {session_id, customer_id, customer_name, visitor_id, message, page_state}
→ text/event-stream: status / text (deltas) / action / chips / done, computed from page_state like the real agent.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import random
from pathlib import Path

from fastapi import Body, FastAPI, Request
from fastapi.responses import StreamingResponse

SITE = Path(__file__).resolve().parents[1]
ROOT = SITE.parent
DATA = Path(
    os.environ.get("DATA_FILE")
    or os.environ.get("CATALOG_JSONL")
    or (SITE / "data" / "products_retail.jsonl" if (SITE / "data" / "products_retail.jsonl").exists()
        else ROOT / "seed" / "catalog" / "products_retail.jsonl")
)
CATALOG: dict[str, dict] = {}
for line in DATA.read_text(encoding="utf-8").splitlines():
    try:
        p = json.loads(line)
    except json.JSONDecodeError:
        continue
    CATALOG[p["id"]] = {"id": p["id"], "title": p["title"], "price": int(p["priceInfo"]["price"]), "cat": (p.get("categories") or [""])[0]}

SLOTS = {"d1_am": "明日 9:00-12:00", "d1_pm": "明日 14:00-17:00", "d1_eve": "明日 18:00-21:00",
         "d2_am": "明後日 9:00-12:00", "d2_pm": "明後日 14:00-17:00"}
SESS: dict[str, dict] = {}
app = FastAPI(title="fake cymbal-adk-agent")
REQUESTS: list[dict] = []


def find(word: str, cat: str = "") -> dict | None:
    for p in CATALOG.values():
        if word in p["title"] and cat in p["cat"] and "業務用" not in p["title"] and "えび" not in p["title"]:
            return p
    return None


def slot_of(msg: str) -> str:
    """slot label (「明日 14:00-17:00」) or natural language (voice: 「明日の午後」「明後日の午前」「明日の夜」)"""
    for k, v in SLOTS.items():
        if v in msg:
            return k
    day = "d2" if "明後日" in msg else "d1" if "明日" in msg else ""
    part = "pm" if ("午後" in msg or "14" in msg) else "eve" if ("夜" in msg or "18" in msg) else "am" if ("午前" in msg or "9時" in msg) else ""
    if not day or not part or (day == "d2" and part == "eve"):
        return ""
    return f"{day}_{part}"


def ev(**k) -> bytes:
    return ("data: " + json.dumps(k, ensure_ascii=False) + "\n\n").encode()


async def say(text: str):
    for i in range(0, len(text), 6):
        yield ev(type="text", text=text[i:i + 6], author="cymbal_concierge")
        await asyncio.sleep(0.02)


def totals(cart: list[dict]) -> tuple[int, int]:
    sub = sum(int(l["price"]) * int(l["qty"]) for l in cart)
    return sub, (0 if sub >= 3000 or sub == 0 else 330)


async def turn(body: dict):
    msg = body.get("message", "")
    ps = body.get("page_state") or {}
    cart = ps.get("cart") or []
    sess = SESS.setdefault(body.get("session_id", ""), {})
    yield ev(type="status", text="考えています…")
    await asyncio.sleep(0.15)
    if "夕食" in msg or "献立" in msg:
        yield ev(type="status", text="購入履歴とご家族の好みを確認しています…")
        roles = [("主菜", find("秋鮭 切り身") or find("鮭"), ["よく購入", "家族の好み"], 2),
                 ("副菜", find("ひじき"), ["時短"], 1), ("汁物", find("豚汁"), ["家族の好み"], 1),
                 ("デザート・果物", find("みかん", "果物"), ["旬"], 1)]
        secs = [{"label": r, "product_ids": [p["id"]], "reasons": [r + "のおすすめ（テスト）"], "tags": [t], "quantities": [q]}
                for r, p, t, q in roles if p]
        sess["set"] = [(s["product_ids"][0], s["quantities"][0]) for s in secs]
        args = {"theme": body.get("customer_name", "") + "さんご家族の今夜の夕食セット（テスト）", "message": "よく購入・家族の好み・旬から",
                "product_ids": [s["product_ids"][0] for s in secs], "reasons": [s["reasons"][0] for s in secs], "sections": secs}
        yield ev(type="action", name="show_products_on_page", args=args, result={"shown": len(secs)})
        async for c in say(f"今夜は**秋鮭の和定食**はいかがでしょう。\n- 主菜：秋鮭\n- 副菜・汁物・果物つき（{len(secs)}品）"):
            yield c
        yield ev(type="chips", items=["セットをカートに入れて", "別のセットを見せて"])
    elif "セット" in msg and ("カート" in msg or "入れ" in msg):
        for pid, q in sess.get("set", []):
            yield ev(type="action", name="add_to_cart", args={"product_id": pid, "quantity": q}, result={"ok": True})
        async for c in say("セットをカートに入れました。"):
            yield c
        yield ev(type="chips", items=["レジに進む"])
    elif "レジ" in msg:
        if not cart:
            async for c in say("カートが空です。"):
                yield c
        else:
            yield ev(type="action", name="start_checkout", args={}, result={"ok": True, "slots": [{"slot_id": k, "label": v} for k, v in SLOTS.items()]})
            async for c in say("お届け日時をお選びください。"):
                yield c
    elif "お願いします" in msg and slot_of(msg):
        sid = slot_of(msg)
        sub, ship = totals(cart)
        yield ev(type="action", name="select_delivery_slot", args={"slot_id": sid}, result={"ok": True, "total_tax_included": sub + ship})
        async for c in say(f"{SLOTS[sid]}でお届けします。内容をご確認ください。"):
            yield c
    elif "確定" in msg:
        oid = "CR-" + dt.date.today().strftime("%Y%m%d") + "-" + str(random.randint(1000, 9999))
        sub, ship = totals(cart)
        yield ev(type="status", text="注文を確定しています…")
        yield ev(type="action", name="place_order", args={"order_id": oid}, result={"ok": True, "order_id": oid, "total_tax_included": sub + ship})
        async for c in say(f"ご注文を確定しました（**{oid}**）。"):
            yield c
        yield ev(type="chips", items=["注文状況は？"])
    else:
        async for c in say("こんにちは！ご用件をどうぞ。"):
            yield c
    yield ev(type="done", session_id=body.get("session_id", ""))


@app.post("/api/chat/stream")
async def chat_stream(request: Request, body: dict = Body(default={})):
    REQUESTS.append({"auth": bool(request.headers.get("authorization")), **body})
    return StreamingResponse(turn(body), media_type="text/event-stream")


@app.get("/debug/requests")
async def debug_requests():
    return REQUESTS[-20:]
