"""Unit tests for the CES bridge (CONTRACT v4) with a fake CES runtime (httpx.MockTransport).

run: pytest tests/test_ces_bridge.py   (from repo root)
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import httpx
import pytest

SITE = Path(__file__).resolve().parents[1]
ROOT = SITE.parent
sys.path.insert(0, str(SITE))

CANDIDATES = (
    ([Path(os.environ["DATA_FILE"])] if os.environ.get("DATA_FILE") else [])
    + ([Path(os.environ["CATALOG_JSONL"])] if os.environ.get("CATALOG_JSONL") else [])
    + [SITE / "data" / "products_retail.jsonl", ROOT / "seed" / "catalog" / "products_retail.jsonl"]
)
DATA = next((p for p in CANDIDATES if p.exists()), SITE / "data" / "products_retail.jsonl")
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="catalog JSONL not found")

APP = "projects/test-proj/locations/us/apps/cymbal-concierge"
TOOL = APP + "/tools/"
IDS = {"show_products_on_page": "fe0aabbf", "add_to_cart": "0cf85d65", "start_checkout": "97ee11d5",
       "select_delivery_slot": "762fbfb6", "place_order": "2ec0960a", "suggest_replies": "22ad3d4c",
       "show_comparison": "ee303f89", "get_cart": "622427ad", "get_order_status": "24f32f6a"}
TOOL_MAP = {}
for _n, _i in IDS.items():
    TOOL_MAP[_i] = _n
    TOOL_MAP[TOOL + _i] = _n
    TOOL_MAP[TOOL.replace("test-proj", "123456") + _i] = _n


@pytest.fixture()
def bridge(monkeypatch):
    monkeypatch.setenv("CES_APP_NAME", APP)
    monkeypatch.setenv("CES_DEPLOYMENT_NAME", "projects/123456/locations/us/apps/cymbal-concierge/deployments/dep-1")
    monkeypatch.setenv("CES_TOOL_ID_MAP", json.dumps(TOOL_MAP))
    monkeypatch.setenv("CES_MODEL", "gemini-3.5-flash")
    from app import ces_bridge

    ces_bridge.STATES.clear()
    ces_bridge._LOCKS.clear()
    return ces_bridge


class FakeTokens:
    cleared = 0

    async def headers(self):
        return {"Authorization": "Bearer fake", "Content-Type": "application/json"}

    def clear(self):
        self.cleared += 1


class FakeCes:
    """Scripted CES: `script` is a list of responses, one per HTTP request. Each response is either an int (HTTP
    error status) or a list of SessionOutput dicts. Records every request body."""

    def __init__(self, script, stream=True):
        self.script = list(script)
        self.requests: list[dict] = []
        self.urls: list[str] = []
        self.stream = stream

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.urls.append(str(request.url))
        self.requests.append(json.loads(request.content))
        item = self.script.pop(0)
        if isinstance(item, int):
            return httpx.Response(item, json={"error": {"code": item, "message": "Resource has been exhausted"}})
        if ":streamRunSession" in str(request.url):
            body = "".join("data: " + json.dumps({"outputs": [o]}, ensure_ascii=False) + "\n\n" for o in item)
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())
        return httpx.Response(200, json={"outputs": item})

    def client(self, bridge):
        http = httpx.AsyncClient(transport=httpx.MockTransport(self.handler))
        return bridge.CesClient(http=http, tokens=FakeTokens(), stream=self.stream)


def tc(name, args, by="tool", cid=None):
    d = {"id": cid or f"adk-{name}", "args": args}
    if by == "tool":
        d["tool"] = TOOL + IDS[name]
    elif by == "number":
        d["tool"] = TOOL.replace("test-proj", "123456") + IDS[name]
    else:
        d["displayName"] = name
    return {"toolCalls": {"toolCalls": [d]}, "turnIndex": 1}


def run(bridge, ces, body, sleeps=None):
    async def go():
        out = []
        async def fake_sleep(s):
            if sleeps is not None:
                sleeps.append(s)
        async for p in bridge.run_turn(body, ces, sleep=fake_sleep):
            out.append(p)
        return out
    return asyncio.run(go())


def body(msg, sid="s-test", page_state=None):
    return {"session_id": sid, "customer_id": "CR-0001", "customer_name": "さくら", "visitor_id": "v-1",
            "message": msg, "page_state": page_state or {"cart": [], "checkout": {"state": "idle", "slot_id": None},
                                                         "orders": [], "page_context": {"view": "home"}}}


def catalog_items(bridge, n):
    items = [(pid, p) for pid, p in bridge.CATALOG.products.items() if p["availability"] == "IN_STOCK" and p["price"] > 0]
    return items[:n]


# ─────────────────────────────────────────────────────────────────────────────────────────────
def test_resolve_tool_name_variants(bridge):
    r = bridge.resolve_tool_name
    assert r({"tool": TOOL + IDS["add_to_cart"]}) == "add_to_cart"
    assert r({"tool": TOOL.replace("test-proj", "123456") + IDS["place_order"]}) == "place_order"
    assert r({"tool": "projects/other/locations/us/apps/x/tools/" + IDS["start_checkout"]}) == "start_checkout"  # uuid
    assert r({"displayName": "show_comparison"}) == "show_comparison"
    assert r({"displayName": "cymbal_commerce_mcp_search_products"}) == "search_products"
    assert r({"tool": TOOL + "unknown-id", "displayName": "suggest_replies"}) == "suggest_replies"


def test_session_mapping_and_deployment(bridge):
    a = bridge.ces_session_name("browser-1")
    assert a == bridge.ces_session_name("browser-1") and a != bridge.ces_session_name("browser-2")
    assert re.fullmatch(APP + r"/sessions/web-[0-9a-f]{32}", a)
    assert bridge.deployment() == APP + "/deployments/dep-1"


def test_dinner_turn_tool_loop_actions_chips_text(bridge):
    (p1, _), (p2, _) = catalog_items(bridge, 2)
    show_args = {"message": "秋鮭の和定食セット", "theme": "さくらさんご家族の今夜の夕食セット", "product_ids": [p1, p2],
                 "reasons": ["旬の秋鮭", "よく購入"], "quantities": [1, 2],
                 "sections": [{"label": "主菜", "product_ids": [p1], "reasons": ["旬の秋鮭"], "quantities": [1]},
                              {"label": "副菜", "product_ids": [p2], "reasons": ["よく購入"], "quantities": [2]}]}
    out1 = tc("show_products_on_page", show_args)
    out1["toolCalls"]["toolCalls"].append({"id": "adk-chips", "tool": TOOL + IDS["suggest_replies"],
                                           "args": {"items": ["セットをカートに入れる", "別の案", "予算1,500円で"]}})
    fake = FakeCes([
        [out1, {"turnCompleted": True, "diagnosticInfo": {"messages": [{"role": "Root_Agent", "chunks": [
            {"toolCall": {"id": "x", "displayName": "cymbal_commerce_mcp_recommend_dinner_set", "args": {}}}]}],
            "rootSpan": {"name": "root", "childSpans": [
                {"name": "LLM", "attributes": {"input token count": 9000, "output token count": 40}},
                {"name": "Tool", "attributes": {}},
                {"name": "LLM", "attributes": {"input token count": 12000, "output token count": 300}}]}}}],
        [{"text": "今夜は「秋鮭の和定食セット」はいかがでしょう。"},
         {"text": "以前お知らせいただいたアレルギー情報を反映し、えびを含む商品は除いています。"},
         {"turnCompleted": True}],
    ])
    ev = run(bridge, fake.client(bridge), body("今夜の夕食をお勧めしてね", sid="s-dinner"))
    types = [e["type"] for e in ev]
    assert ev[0] == {"type": "status", "text": "考えています…"}
    assert "おすすめ商品を表示しています…" in [e.get("text") for e in ev if e["type"] == "status"]
    acts = [e for e in ev if e["type"] == "action"]
    assert [a["name"] for a in acts] == ["show_products_on_page"]
    assert acts[0]["args"]["sections"] == show_args["sections"] and acts[0]["args"]["quantities"] == [1, 2]
    assert acts[0]["result"] == {"shown": 2}
    assert types.index("action") < types.index("text") < types.index("chips") < types.index("done")
    assert next(e for e in ev if e["type"] == "chips")["items"] == ["セットをカートに入れる", "別の案", "予算1,500円で"]
    text = "".join(e["text"] for e in ev if e["type"] == "text")
    assert text.startswith("今夜は") and "えびを含む商品は除いています" in text
    done = ev[-1]
    assert done["type"] == "done" and done["session_id"] == "s-dinner" and done["model"] == "gemini-3.5-flash"
    t = done["timings"]
    assert t["ces_calls"] == 2 and t["first_status_ms"] is not None and t["first_action_ms"] <= t["first_text_ms"] <= t["total_ms"]
    assert done["_internal"]["mcp_calls"] == ["recommend_dinner_set"]
    assert done["usage"] == {"llm_calls": 2, "input_tokens": 21000, "output_tokens": 340}
    # request 1: variables + text, session config with pinned deployment and text streaming
    r1, r2 = fake.requests
    assert fake.urls[0].endswith(":streamRunSession?alt=sse")
    assert r1["config"]["session"] == bridge.ces_session_name("s-dinner")
    assert r1["config"]["deployment"] == APP + "/deployments/dep-1" and r1["config"]["enableTextStreaming"] is True
    v = r1["inputs"][0]["variables"]
    assert v["customer_id"] == "CR-0001" and v["customer_name"] == "さくら" and v["visitor_id"] == "v-1"
    assert "カートは空です" in v["cart_summary"] and "えび" in v["persona_summary"]
    assert r1["inputs"][1] == {"text": "今夜の夕食をお勧めしてね"}
    # request 2: tool responses with matching ids / tool names
    resps = r2["inputs"][0]["toolResponses"]["toolResponses"]
    assert [x["id"] for x in resps] == ["adk-show_products_on_page", "adk-chips"]
    assert resps[0]["tool"] == TOOL + IDS["show_products_on_page"] and resps[0]["response"] == {"shown": 2}
    assert resps[1]["response"] == {"shown": 3}


def test_set_to_cart_then_checkout_and_order(bridge):
    (p1, c1), (p2, c2) = catalog_items(bridge, 2)
    sid = "s-buy"
    adds = {"toolCalls": {"toolCalls": [
        {"id": "a1", "tool": TOOL + IDS["add_to_cart"], "args": {"product_id": p1, "quantity": 1}},
        {"id": "a2", "tool": TOOL.replace("test-proj", "123456") + IDS["add_to_cart"], "args": {"product_id": p2, "quantity": 2}},
    ]}}
    fake = FakeCes([[adds], [{"text": "夕食セット 2 点をカートに入れました。"}]])
    ev = run(bridge, fake.client(bridge), body("セットをカートに入れて", sid=sid))
    acts = [e for e in ev if e["type"] == "action"]
    assert [(a["name"], a["args"]) for a in acts] == [("add_to_cart", {"product_id": p1, "quantity": 1}),
                                                       ("add_to_cart", {"product_id": p2, "quantity": 2})]
    assert [e["text"] for e in ev if e["type"] == "status"] == ["考えています…", "カートに追加しています…"]  # deduped
    total = c1["price"] + 2 * c2["price"]
    assert acts[-1]["result"] == {"ok": True, "cart_count": 3, "cart_total_tax_included": total, "title": c2["title"]}
    assert next(e for e in ev if e["type"] == "chips")["items"] == ["レジに進みます", "カートの中身は？"]  # fallback chips

    # next turns: the page sends back its state (here: the bridge's own state, which the page mirrors)
    st = bridge.shop_state(sid)
    ps = lambda: {"cart": [dict(l) for l in st.cart], "checkout": dict(st.checkout), "orders": list(st.orders),
                  "page_context": {"view": "home"}}
    fake = FakeCes([[tc("start_checkout", {}, by="displayName")], [{"text": "ご注文手続きを始めます。"}]])
    ev = run(bridge, fake.client(bridge), body("レジに進みます", sid=sid, page_state=ps()))
    a = next(e for e in ev if e["type"] == "action")
    assert a["name"] == "start_checkout" and a["result"]["ok"] and a["result"]["cart_total_tax_included"] == total
    assert [s["slot_id"] for s in a["result"]["slots"]] == ["d1_am", "d1_pm", "d1_eve", "d2_am", "d2_pm"]
    assert "チェックアウト状態: idle" in fake.requests[0]["inputs"][0]["variables"]["cart_summary"]

    fake = FakeCes([[tc("select_delivery_slot", {"slot_id": "d1_pm"})], [{"text": "確定してよろしいですか？"}]])
    ev = run(bridge, fake.client(bridge), body("明日 14:00-17:00 でお願いします", sid=sid, page_state=ps()))
    a = next(e for e in ev if e["type"] == "action")
    ship = 0 if total >= 3000 else 330
    assert a["result"] == {"ok": True, "slot_label": "明日 14:00-17:00", "payment_method": "Cymbal Pay（VISA **** 4242）",
                           "total_tax_included": total + ship, "subtotal_tax_included": total, "shipping_fee": ship,
                           "next": "confirm"}

    fake = FakeCes([[tc("place_order", {})], [{"text": "ご注文ありがとうございます。"}]])
    ev = run(bridge, fake.client(bridge), body("注文を確定してください", sid=sid, page_state=ps()))
    a = next(e for e in ev if e["type"] == "action")
    assert a["name"] == "place_order" and re.fullmatch(r"CR-\d{8}-\d{4}", a["args"]["order_id"])
    assert a["result"]["order_id"] == a["args"]["order_id"] and a["result"]["slot_label"] == "明日 14:00-17:00"
    resp = fake.requests[1]["inputs"][0]["toolResponses"]["toolResponses"][0]["response"]
    assert resp["order_id"] == a["args"]["order_id"]
    assert next(e for e in ev if e["type"] == "chips")["items"] == ["配送状況は？", "今夜の夕食をお勧めしてね"]


def test_place_order_without_slot_is_rejected_and_not_emitted(bridge):
    (p1, c1), = catalog_items(bridge, 1)
    ps = {"cart": [{"product_id": p1, "title": c1["title"], "price": c1["price"], "qty": 1}],
          "checkout": {"state": "idle", "slot_id": None}, "orders": [], "page_context": {}}
    fake = FakeCes([[tc("place_order", {})], [{"text": "先にお届け日時をお選びください。"}]])
    ev = run(bridge, fake.client(bridge), body("注文を確定してください", sid="s-noslot", page_state=ps))
    assert not [e for e in ev if e["type"] == "action"]
    assert fake.requests[1]["inputs"][0]["toolResponses"]["toolResponses"][0]["response"]["error"] == "NO_SLOT_SELECTED"


def test_streamed_text_chunks_and_cumulative_repeat_not_duplicated(bridge):
    fake = FakeCes([[{"text": "さくらさん、"}, {"text": "こんにちは。"}, {"text": "さくらさん、こんにちは。"},
                     {"turnCompleted": True}]])
    ev = run(bridge, fake.client(bridge), body("こんにちは", sid="s-hello"))
    assert "".join(e["text"] for e in ev if e["type"] == "text") == "さくらさん、こんにちは。"
    assert ev[-1]["_internal"]["reply"] == "さくらさん、こんにちは。"
    assert next(e for e in ev if e["type"] == "chips")["items"][0] == "今夜の夕食をお勧めしてね"


def test_fallback_text_when_agent_returns_no_text(bridge):
    (p1, _), = catalog_items(bridge, 1)
    fake = FakeCes([[tc("add_to_cart", {"product_id": p1})], [{"turnCompleted": True}]])
    ev = run(bridge, fake.client(bridge), body("1番目をカートに入れて", sid="s-notext"))
    assert "".join(e["text"] for e in ev if e["type"] == "text") == "カートに追加しました。このままレジに進むこともできます。"


def test_429_backoff_then_success(bridge):
    fake = FakeCes([429, 429, [{"text": "こんにちは。"}]])
    sleeps = []
    ev = run(bridge, fake.client(bridge), body("こんにちは", sid="s-429"), sleeps=sleeps)
    assert sleeps == [3.0, 6.0]
    assert [e["text"] for e in ev if e["type"] == "status"].count("ただいま混み合っています。少々お待ちください…") == 2
    assert "".join(e["text"] for e in ev if e["type"] == "text") == "こんにちは。"
    assert ev[-1]["type"] == "done" and ev[-1]["timings"]["ces_calls"] == 3


def test_429_exhausted_becomes_friendly_error(bridge, monkeypatch):
    monkeypatch.setenv("CES_RETRY_DELAYS", "1")
    fake = FakeCes([429, 429])
    ev = run(bridge, fake.client(bridge), body("こんにちは", sid="s-429b"), sleeps=[])
    err = next(e for e in ev if e["type"] == "error")
    assert err["status"] == 429 and "混み合っています" in err["message"]
    assert ev[-1]["type"] == "done" and ev[-1]["session_id"] == "s-429b"


def test_403_error_clears_token(bridge):
    fake = FakeCes([403])
    ces = fake.client(bridge)
    ev = run(bridge, ces, body("こんにちは", sid="s-403"))
    assert next(e for e in ev if e["type"] == "error")["status"] == 403 and ces.tokens.cleared == 1


def test_run_session_non_streaming_path(bridge):
    fake = FakeCes([[tc("get_cart", {})], [{"text": "カートは空です。"}]], stream=False)
    ev = run(bridge, fake.client(bridge), body("カートの中身は？", sid="s-rs"))
    assert all(u.endswith(":runSession") for u in fake.urls)
    assert "enableTextStreaming" not in fake.requests[0]["config"]
    assert [e["name"] for e in ev if e["type"] == "action"] == ["get_cart"]


def test_persona_summary_never_names_allergy_member(bridge):
    s = bridge.persona_summary("CR-0001")
    assert "えび（要除去）" in s and "長女: えび" not in s and "えび（アレルギー）" not in s
    assert bridge.persona_summary("nobody") == "（なし）"


def test_site_endpoint_uses_ces_backend(monkeypatch, bridge):
    os.environ["DATA_FILE"] = str(DATA)
    os.environ["AI_MOCK"] = "1"
    monkeypatch.delenv("ADK_AGENT_URL", raising=False)
    monkeypatch.setenv("AGENT_BACKEND", "ces")
    from fastapi.testclient import TestClient
    from app import main

    fake = FakeCes([[{"text": "こんにちは。"}]])
    monkeypatch.setattr(main.ces_bridge, "get_client", lambda: fake.client(bridge))
    with TestClient(main.app) as c:
        cfg = json.loads(c.get("/config.js").text[len("window.CR_CONFIG = "):].rstrip(";\n"))
        assert cfg["agentMode"] == "live" and cfg["agentBackend"] == "ces" and cfg["agentPlatform"] == "GECX AI Studio"
        c.cookies.set("cr_visitor", "v-abc")
        r = c.post("/api/agent/stream", json={"session_id": "s-web", "message": "こんにちは", "customer_id": "SPOOF"})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        ev = [json.loads(l[6:]) for l in r.text.split("\n") if l.startswith("data: ")]
        assert ev[0]["type"] == "status" and ev[-1]["type"] == "done" and "_internal" not in ev[-1]
        v = fake.requests[0]["inputs"][0]["variables"]
        assert v["customer_id"] == "CR-0001" and v["visitor_id"] == "v-abc"
        monkeypatch.setenv("AGENT_BACKEND", "adk")  # adk without ADK_AGENT_URL → mock
        cfg = json.loads(c.get("/config.js").text[len("window.CR_CONFIG = "):].rstrip(";\n"))
        assert cfg["agentMode"] == "mock" and cfg["agentBackend"] == "mock"


def test_site_shop_is_a_copy_of_the_adk_shop():
    """CONTRACT v4: the bridge must compute identical results / ids / slots / shipping / order ids as the ADK agent."""
    import ast

    def body(p):
        tree = ast.parse(Path(p).read_text(encoding="utf-8"))
        tree.body = tree.body[1:]  # drop the module docstring
        return ast.dump(tree)
    assert body(SITE / "app" / "shop.py") == body(ROOT / "shared" / "adk_agent" / "cymbal_agent" / "shop.py")
