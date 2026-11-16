"""Unit tests for the Cymbal Retail storefront backend (local DATA_FILE mode, Gemini mocked).

run: pytest tests/test_site_api.py   (from repo root)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parents[1]
ROOT = SITE.parent
sys.path.insert(0, str(SITE))

CANDIDATES = (
    ([Path(os.environ["DATA_FILE"])] if os.environ.get("DATA_FILE") else [])
    + ([Path(os.environ["CATALOG_JSONL"])] if os.environ.get("CATALOG_JSONL") else [])
    + [SITE / "data" / "products_retail.jsonl", ROOT / "seed" / "catalog" / "products_retail.jsonl"]
)
DATA = next((p for p in CANDIDATES if p.exists()), None)
pytestmark = pytest.mark.skipif(DATA is None, reason="catalog JSONL not found")


@pytest.fixture(scope="module")
def client():
    os.environ["DATA_FILE"] = str(DATA)
    os.environ["AI_MOCK"] = "1"
    os.environ.pop("ADK_AGENT_URL", None)
    os.environ.pop("AGENT_BACKEND", None)  # v4: these tests cover mock + the ADK proxy (CES bridge: test_ces_bridge.py)
    os.environ.pop("CES_APP_NAME", None)
    os.environ["DELIVERY_SPEED_SEC"] = "3"
    from fastapi.testclient import TestClient
    from app import main

    main.reset_engine()
    with TestClient(main.app) as c:
        yield c


def test_index_sets_cookies(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Cymbal" in r.text
    assert r.cookies.get("cr_customer") == "CR-0001"
    assert r.cookies.get("cr_visitor", "").startswith("v-")


def test_config_js(client):
    r = client.get("/config.js")
    assert r.status_code == 200
    body = r.text
    assert body.startswith("window.CR_CONFIG = ")
    cfg = json.loads(body[len("window.CR_CONFIG = "):].rstrip(";\n"))
    # CONTRACT v3: CES config removed; mock concierge while ADK_AGENT_URL is unset
    assert "deploymentName" not in cfg and "toolIdMap" not in cfg and "tokenBroker" not in cfg
    assert cfg["agentMode"] == "mock" and cfg["agentEndpoint"] == "/api/agent/stream"
    assert cfg["deliverySpeedSec"] == 3


def test_search_shape(client):
    r = client.get("/api/search", params={"q": "カレー", "page_size": 12})
    assert r.status_code == 200
    j = r.json()
    for k in ("results", "total", "facets", "tiles", "conversation", "corrected_query", "applied_filter"):
        assert k in j
    assert 0 < len(j["results"]) <= 12
    assert j["total"] >= len(j["results"])
    p = j["results"][0]
    for k in ("id", "title", "brand", "category", "price", "original_price", "on_sale", "discount_rate", "image",
              "rating", "rating_count", "size", "labels", "availability", "description"):
        assert k in p, k
    assert p["image"].startswith("/img/products/")
    assert all(0 <= x["discount_rate"] <= 1 for x in j["results"])
    keys = {f["key"] for f in j["facets"]}
    assert {"attributes.top_category", "brands", "price"} <= keys
    for f in j["facets"]:
        assert f["label"] and all({"value", "count", "selected"} <= set(v) for v in f["values"])
    assert j["tiles"] and all({"label", "filter"} <= set(t) for t in j["tiles"])
    conv = j["conversation"]
    assert {"id", "refined_query", "followup_question", "suggested_answers"} <= set(conv)
    assert conv["followup_question"] and conv["suggested_answers"]


def test_search_facet_filter_and_price(client):
    base = client.get("/api/search", params={"q": "カレー"}).json()
    cat = next(f for f in base["facets"] if f["key"] == "attributes.top_category")["values"][0]["value"]
    j = client.get("/api/search", params={"q": "カレー", "facets": json.dumps({"attributes.top_category": [cat]})}).json()
    assert j["total"] <= base["total"]
    assert all(p["category"] == cat for p in j["results"])
    assert 'attributes.top_category: ANY("' in j["applied_filter"]
    j2 = client.get("/api/search", params={"q": "カレー", "facets": json.dumps({"price": ["0-300"]})}).json()
    assert all(p["price"] < 300 for p in j2["results"])
    assert "price: IN(0i, 300e)" in j2["applied_filter"]


def test_search_tiles_and_answer(client):
    base = client.get("/api/search", params={"q": "カレー"}).json()
    t = base["tiles"][0]
    j = client.get("/api/search", params={"q": "カレー", "tiles": json.dumps([t])}).json()
    assert j["total"] <= base["total"] and j["total"] > 0
    act = base["conversation"]["answer_actions"][0]
    j2 = client.get("/api/search", params={"q": "カレー", "conversation_id": base["conversation"]["id"],
                                           "answer": act["label"], "answer_key": act["key"], "answer_value": act["value"]}).json()
    assert j2["total"] <= base["total"]


def test_search_pagination(client):
    p1 = client.get("/api/search", params={"q": "カレー", "page": 1, "page_size": 5}).json()
    p2 = client.get("/api/search", params={"q": "カレー", "page": 2, "page_size": 5}).json()
    assert {p["id"] for p in p1["results"]}.isdisjoint({p["id"] for p in p2["results"]})


def test_autocomplete(client):
    j = client.get("/api/autocomplete", params={"q": "カレ"}).json()
    assert j["suggestions"] and any("カレ" in s for s in j["suggestions"])
    assert client.get("/api/autocomplete", params={"q": ""}).json() == {"suggestions": []}


def test_products(client):
    ids = [p["id"] for p in client.get("/api/search", params={"q": "カレー", "page_size": 3}).json()["results"]]
    j = client.get("/api/products", params={"ids": ",".join(ids + ["nope"])}).json()
    assert [p["id"] for p in j["products"]] == ids


def test_ai_summary_template(client):
    ids = [p["id"] for p in client.get("/api/search", params={"q": "カレー", "page_size": 6}).json()["results"]]
    j = client.post("/api/ai-summary", json={"q": "カレー", "product_ids": ids}).json()
    assert j["summary"]
    assert all(h["product_id"] in ids for h in j["highlights"])
    assert "followup" in j


def test_home_and_features(client):
    h = client.get("/api/home").json()
    assert h["categories"] and h["sale"] and h["recommended"]
    assert all(p["on_sale"] for p in h["sale"])
    f = client.get("/api/features").json()
    assert f["engine"] == "local" and f["catalog_size"] > 1000


def test_static_assets(client):
    for path in ("/css/theme.css", "/js/app.js", "/js/chat.js", "/js/checkout.js", "/js/orders.js", "/js/cart.js",
                 "/js/chat_rich.js", "/js/chat_cards.js", "/js/home.js", "/js/router.js"):
        assert client.get(path).status_code == 200, path
    img = client.get("/api/search", params={"q": "カレー", "page_size": 1}).json()["results"][0]["image"]
    assert client.get(img).status_code == 200


def test_index_loads_chat_rich_modules_in_order(client):
    """chat_rich.js (card injection into our panel) must load before chat_cards.js, both after chat.js."""
    html = client.get("/").text
    i_chat, i_rich, i_cards = (html.index(f'src="/js/{n}.js"') for n in ("chat", "chat_rich", "chat_cards"))
    assert i_chat < i_rich < i_cards
    # CONTRACT v3: own slide-over panel, no CES chat-messenger widget
    for el_id in ("cr-chat", "cr-chat-log", "cr-chat-input", "cr-chat-typing", "cr-chat-status", "cr-chat-reset", "cr-fab"):
        assert f'id="{el_id}"' in html, el_id
    chat = client.get("/js/chat.js").text
    for banned in ("chat-messenger", "gstatic.com/chat-messenger", "deploymentName", "toolIdMap"):
        assert banned not in chat, banned
    for needed in ("/api/agent/stream", "page_state", "sessionStorage", "isComposing", "compositionend", "order_id",
                   "case 'status'", "case 'text'", "case 'action'", "case 'chips'", "case 'done'", "case 'error'"):
        assert needed in chat, needed
    assert "placeOrder(orderId)" in client.get("/js/checkout.js").text
    cards = client.get("/js/chat_cards.js").text
    for phrase in ("レジに進みます", "でお願いします", "注文を確定してください", "C.PAYMENT", "配達完了"):
        assert phrase in cards, phrase
    search_js = client.get("/js/search.js").text
    assert "sections" in search_js and "cr-set-sec" in search_js
    # CONTRACT v2.1: optional per-section quantities → ×N display, Σ price×qty total, set add with quantities
    assert "quantities" in search_js and "* it.qty" in search_js
    assert "quantities" in cards and "x.qty" in cards


def test_dinner_set_mock_queries_return_products(client):
    """The mock-chat dinner set is built from real catalog ids via /api/search (one per role)."""
    for q in ("秋鮭 切り身", "ひじき", "豚汁", "ごはん", "みかん"):
        res = client.get("/api/search", params={"q": q, "page_size": 10}).json()
        assert res["results"], q
        ids = [p["id"] for p in res["results"]]
        got = client.get("/api/products", params={"ids": ",".join(ids[:3])}).json()["products"]
        assert len(got) == len(ids[:3])


def test_filter_builder():
    from app.search import facets_to_filter, merge_filters

    f = facets_to_filter({"brands": ["A", 'B"q'], "price": ["0-300", "5000-"]})
    assert 'brands: ANY("A", "B\\"q")' in f
    assert "(price: IN(0i, 300e) OR price: IN(5000i, *))" in f
    assert merge_filters("a", "", "b") == "(a) AND (b)"


def test_retail_feature_fallback(monkeypatch):
    """RetailSearch drops rejected advanced features and still answers (no network: fake client)."""
    from app import search as S
    from app.catalog import Catalog

    class Resp:
        def __init__(self):
            self.results, self.facets, self.total_size, self.corrected_query = [], [], 0, ""
            self.tile_navigation_result = None
            self.conversational_search_result = None

    class FakeClient:
        def __init__(self):
            self.calls = []

        def search(self, request, timeout=None):
            self.calls.append(request)
            if request.tile_navigation_spec.tile_navigation_requested or request.conversational_search_spec.followup_conversation_requested:
                raise ValueError("400 feature not enabled")
            return Resp()

    eng = S.RetailSearch.__new__(S.RetailSearch)
    from google.cloud import retail_v2alpha
    eng.retail = retail_v2alpha
    eng.catalog = Catalog(str(DATA))
    eng.local = S.LocalSearch(eng.catalog)
    eng.client = FakeClient()
    eng.catalog_name = "projects/1/locations/global/catalogs/default_catalog"
    eng.placement = eng.catalog_name + "/servingConfigs/default_search"
    eng.branch = eng.catalog_name + "/branches/0"
    eng.disabled, eng.conv_answers, eng.pcache = {}, {}, {}
    eng.status = {f: "untested" for f in S.ADVANCED}
    import threading
    eng.lock = threading.Lock()
    out = eng.search("カレー")
    assert out["engine"] == "retail"
    assert out["features"]["tile_navigation"] == "fallback"
    assert out["features"]["conversational"] == "fallback"
    assert out["features"]["query_expansion"] == "live"
    assert "tile_navigation" in eng.disabled and "conversational" in eng.disabled


def test_hiragana_retry_and_suggestions(client):
    j = client.get("/api/search", params={"q": "ふらいぱん"}).json()
    if j["total"]:
        assert j["corrected_query"] in ("", "フライパン")
    k = client.get("/api/search", params={"q": "かれー"}).json()
    assert k["total"] > 0 and k["corrected_query"] == "カレー"
    assert k["results_query"] == "カレー"
    s = client.get("/api/autocomplete", params={"q": "ふら"}).json()["suggestions"]
    assert any("フラ" in x for x in s)


def test_kana_helper():
    from app.catalog import has_hiragana, to_katakana
    assert to_katakana("ふらいぱん") == "フライパン" and has_hiragana("ふら") and not has_hiragana("フラ")


# ---------------------------------------------------------------------------- v3: home recommendations
def test_recommendations_all_types(client):
    seen_titles = {}
    for t in ("for_you", "buy_again", "sale", "seasonal", "new", "popular"):
        j = client.get("/api/recommendations", params={"type": t, "limit": 12}).json()
        assert j["type"] == t and j["title"] and j["customer_id"] == "CR-0001", j
        items = j["items"]
        assert 6 <= len(items) <= 12, (t, len(items))
        for p in items:
            for k in ("id", "title", "price", "image", "reason", "tags"):
                assert k in p, (t, k)
            assert p["image"].startswith("/img/products/")
            assert not any(w in p["title"] for w in ("えび", "エビ", "海老", "業務用")), (t, p["title"])
        assert len({p["image"] for p in items}) == len(items), t  # one product per image
        seen_titles[t] = j["title"]
    assert seen_titles["for_you"] == "さくらさんへのおすすめ"


def test_recommendations_semantics(client):
    fy = client.get("/api/recommendations", params={"type": "for_you", "limit": 16}).json()["items"]
    reasons = " ".join(p["reason"] for p in fy)
    # family preferences (personas family_preferences) drive the personal row
    assert sum(n in reasons for n in ("さくらさん", "健太さん", "蓮くん", "陽菜ちゃん")) >= 3, reasons
    assert any("家族の好み" in p["tags"] for p in fy)
    again = client.get("/api/recommendations", params={"type": "buy_again"}).json()["items"]
    counts = [p["purchase_count"] for p in again]
    assert counts == sorted(counts, reverse=True) and counts[0] >= 10, counts
    hist_path = ROOT / "seed" / "personas" / "purchase_history.jsonl"
    if not hist_path.exists():
        hist_path = ROOT / "shared" / "mcp_server" / "data" / "purchase_history.jsonl"
    hist = [json.loads(l) for l in hist_path.read_text().splitlines() if l.strip()]
    bought = {r["product_id"] for r in hist}
    assert all(p["id"] in bought for p in again)
    sale = client.get("/api/recommendations", params={"type": "sale"}).json()["items"]
    assert all(p["on_sale"] and p["price"] < p["original_price"] for p in sale)
    new = client.get("/api/recommendations", params={"type": "new", "limit": 8}).json()["items"]
    assert {p["category"] for p in new[:4]} == {"キッチン・調理器具", "ビューティー・パーソナルケア", "ペット用品", "生活雑貨・インテリア"}
    pop = client.get("/api/recommendations", params={"type": "popular", "limit": 5}).json()["items"]
    assert [p["rank"] for p in pop] == [1, 2, 3, 4, 5]
    seas = client.get("/api/recommendations", params={"type": "seasonal", "limit": 6}).json()["items"]
    assert all("旬" in p["tags"] for p in seas)
    assert client.get("/api/recommendations", params={"type": "bogus"}).json()["type"] == "for_you"


# ---------------------------------------------------------------------------- v3: ADK agent proxy
def test_agent_stream_mock_mode_returns_503(client):
    r = client.post("/api/agent/stream", json={"message": "こんにちは"})
    assert r.status_code == 503 and r.json()["error"] == "AGENT_NOT_CONFIGURED"


UPSTREAM_SSE = (
    'data: {"type":"status","text":"商品を検索しています…"}\n\n'
    'data: {"type":"text","text":"今夜は","author":"cymbal_concierge"}\n\n'
    'data: {"type":"action","name":"add_to_cart","args":{"product_id":"4903577695999","quantity":2},"result":{"ok":true}}\n\n'
    'data: {"type":"chips","items":["レジに進む"]}\n\n'
    'data: {"type":"done","session_id":"s-abc"}\n\n'
).encode()


@pytest.fixture()
def fake_upstream(monkeypatch):
    """ADK_AGENT_URL set + httpx MockTransport standing in for the private Cloud Run agent."""
    import httpx
    from app import agent_proxy

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        if seen["body"]["message"] == "forbidden":
            return httpx.Response(403, text="Forbidden")
        async def chunks():  # SSE arrives in arbitrary chunks (split mid-event)
            for i in range(0, len(UPSTREAM_SSE), 37):
                yield UPSTREAM_SSE[i:i + 37]
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=chunks())

    real = httpx.AsyncClient
    monkeypatch.setattr(agent_proxy.httpx, "AsyncClient", lambda *a, **k: real(transport=httpx.MockTransport(handler)))
    monkeypatch.setenv("ADK_AGENT_URL", "https://cymbal-adk-agent-test.a.run.app/")
    calls = []

    def fake_fetch(req, audience):
        calls.append(audience)
        return "header.eyJleHAiOiA0MTAyNDQ0ODAwfQ.sig"  # exp = 2100-01-01
    import google.oauth2.id_token
    monkeypatch.setattr(google.oauth2.id_token, "fetch_id_token", fake_fetch)
    agent_proxy._token.clear()
    seen["token_calls"] = calls
    yield seen
    agent_proxy._token.clear()


def test_agent_stream_proxies_sse_with_id_token(client, fake_upstream):
    cfg = client.get("/config.js").text
    assert '"agentMode": "live"' in cfg
    client.cookies.clear()
    client.cookies.set("cr_customer", "CR-0001")
    client.cookies.set("cr_visitor", "v-test123")
    page_state = {"cart": [{"product_id": "4903577695999", "title": "卵", "price": 267, "qty": 1}],
                  "checkout": {"state": "idle", "slot_id": None}, "orders": [],
                  "page_context": {"view": "home", "query": None, "product_id": None}}
    r = client.post("/api/agent/stream", json={"session_id": "s-1", "message": "今夜の夕食をお勧めしてね",
                                               "page_state": page_state, "customer_id": "SPOOF"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.content == UPSTREAM_SSE  # streamed through unchanged
    assert fake_upstream["url"] == "https://cymbal-adk-agent-test.a.run.app/api/chat/stream"
    assert fake_upstream["auth"] == "Bearer header.eyJleHAiOiA0MTAyNDQ0ODAwfQ.sig"
    assert fake_upstream["token_calls"] == ["https://cymbal-adk-agent-test.a.run.app"]  # audience = service URL
    b = fake_upstream["body"]
    assert b["customer_id"] == "CR-0001" and b["customer_name"] == "さくら" and b["visitor_id"] == "v-test123"
    assert b["session_id"] == "s-1" and b["message"] == "今夜の夕食をお勧めしてね" and b["page_state"] == page_state
    # token is cached for the next turn
    client.post("/api/agent/stream", json={"session_id": "s-1", "message": "セットをカートに入れて"})
    assert len(fake_upstream["token_calls"]) == 1


def test_agent_stream_upstream_error_becomes_sse_error(client, fake_upstream):
    r = client.post("/api/agent/stream", json={"session_id": "s-2", "message": "forbidden"})
    assert r.status_code == 200
    events = [json.loads(l[6:]) for l in r.text.split("\n") if l.startswith("data: ")]
    assert events[0]["type"] == "error" and "403" in events[0]["message"]
    assert events[-1] == {"type": "done", "session_id": "s-2"}
    assert client.post("/api/agent/stream", json={"message": "  "}).status_code == 400


# ---------- CONTRACT v5: two storefront services (cymbal-site = GECX, cymbal-site-adk = ADK + enrichment link) ----------
ENRICH = "https://cymbal-data-enrichment.example.run.app"


def _cfg(client) -> dict:
    body = client.get("/config.js").text
    return json.loads(body[len("window.CR_CONFIG = "):].rstrip(";\n"))


def test_config_js_enrich_link_only_when_env_set(client, monkeypatch):
    monkeypatch.delenv("ENRICH_URL", raising=False)
    assert "enrichUrl" not in _cfg(client)  # GECX site (no ENRICH_URL) stays unchanged
    monkeypatch.setenv("ENRICH_URL", "  ")
    assert "enrichUrl" not in _cfg(client)
    monkeypatch.setenv("ENRICH_URL", "javascript:alert(1)")  # only http(s) URLs are exposed
    assert "enrichUrl" not in _cfg(client)
    monkeypatch.setenv("ENRICH_URL", ENRICH)
    assert _cfg(client)["enrichUrl"] == ENRICH


@pytest.mark.parametrize("env,backend,platform", [
    # cymbal-site (GECX): AGENT_BACKEND=ces + CES config, ADK_AGENT_URL also present in the env → still ces
    ({"AGENT_BACKEND": "ces", "CES_APP_NAME": "projects/p/locations/us/apps/a",
      "ADK_AGENT_URL": "https://adk.example"}, "ces", "GECX AI Studio"),
    # cymbal-site-adk: AGENT_BACKEND=adk + ADK_AGENT_URL (CES vars blanked by deploy.sh) → adk
    ({"AGENT_BACKEND": "adk", "ADK_AGENT_URL": "https://adk.example", "CES_APP_NAME": ""},
     "adk", "Agent Development Kit"),
    # explicit adk wins even if CES config leaked into the env
    ({"AGENT_BACKEND": "ADK", "ADK_AGENT_URL": "https://adk.example", "CES_APP_NAME": "projects/p/apps/a"},
     "adk", "Agent Development Kit"),
    # a backend without its configuration → local mock concierge
    ({"AGENT_BACKEND": "adk", "ADK_AGENT_URL": ""}, "mock", ""),
    ({"AGENT_BACKEND": "ces", "CES_APP_NAME": ""}, "mock", ""),
    # unset: ces when CES configured, else adk when ADK_AGENT_URL is set
    ({"AGENT_BACKEND": "", "CES_APP_NAME": "projects/p/apps/a", "ADK_AGENT_URL": "https://adk.example"},
     "ces", "GECX AI Studio"),
    ({"AGENT_BACKEND": "", "CES_APP_NAME": "", "ADK_AGENT_URL": "https://adk.example"},
     "adk", "Agent Development Kit"),
])
def test_backend_selection(client, monkeypatch, env, backend, platform):
    for k in ("AGENT_BACKEND", "CES_APP_NAME", "ADK_AGENT_URL", "ENRICH_URL"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from app import main

    assert main.agent_backend() == backend
    cfg = _cfg(client)
    assert cfg["agentBackend"] == backend and cfg["agentPlatform"] == platform
    assert cfg["agentMode"] == ("mock" if backend == "mock" else "live")


def test_index_has_no_static_enrich_link(client):
    # the link is injected by app.js only when CR_CONFIG.enrichUrl exists → GECX DOM unchanged
    html = client.get("/").text
    assert "cr-enrich-link" not in html
    js = client.get("/js/app.js").text
    assert "cr-enrich-link" in js and "商品データエンリッチメント・スタジオへ" in js
