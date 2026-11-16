"""HTTP API (DATA_MODE=local, AGENT_MODE=mock) — CONTRACT v8 Store Navi BFF."""
from __future__ import annotations

import json

from conftest import sse_events


def test_config_js(client):
    r = client.get("/config.js")
    assert r.status_code == 200 and r.text.startswith("window.SN_CONFIG = ")
    cfg = json.loads(r.text[len("window.SN_CONFIG = "):].rstrip(";\n"))
    assert cfg["appMode"] == "customer" and cfg["agentMode"] in ("live", "mock")
    assert cfg["onlineStoreUrl"].startswith("https://")
    assert {c["customer_id"] for c in cfg["customers"]} >= {"CR-0001", "CR-0002", "CR-0003"}
    assert "staffUrl" not in cfg  # only when STAFF_URL is set


def test_stores_nearest(client):
    r = client.get("/api/stores", params={"lat": 35.5314, "lng": 139.6978}).json()
    assert r["nearest_id"] == "S01" and r["stores"][0]["in_store"] is True
    assert {"distance_m", "open_now", "in_store"} <= set(r["stores"][0])


def test_store_home_personalized(client):
    client.post("/api/login", json={"customer_id": "CR-0001"})
    a = client.get("/api/stores/S01/home").json()
    client.post("/api/login", json={"customer_id": "CR-0003"})
    b = client.get("/api/stores/S01/home").json()
    client.post("/api/login", json={"customer_id": "CR-0001"})
    assert a["customer"]["customer_id"] == "CR-0001" and b["customer"]["customer_id"] == "CR-0003"
    pa = [c for c in a["coupons"] if c["personal"]]
    pb = [c for c in b["coupons"] if c["personal"]]
    assert pa and pb and all(c["customer_id"] == "CR-0001" for c in pa) and all(c["customer_id"] == "CR-0003" for c in pb)
    assert a["coupons"][0]["personal"] and a["coupons"][0]["badge"] == "さくらさん限定"
    assert all(o["product"]["id"] for o in a["offers"])
    assert [o["product_id"] for o in a["offers"]] != [o["product_id"] for o in b["offers"]]
    assert client.get("/api/stores/S99/home").status_code == 404


def test_login_rejects_unknown(client):
    assert client.post("/api/login", json={"customer_id": "CR-9999"}).status_code == 400


def test_autocomplete(client):
    r = client.get("/api/autocomplete", params={"q": "か"}).json()
    assert r["suggestions"] and r["source"] in ("retail", "local")
    assert client.get("/api/autocomplete", params={"q": ""}).json()["suggestions"] == []


def test_search_availability_current_first(client, scenarios):
    r = client.get("/api/search", params={"q": "総合かぜ薬 錠剤", "store_id": "S01"}).json()
    assert r["results"]
    for p in r["results"]:
        av = p["availability"]
        assert av["current"]["store_id"] == "S01"
        assert "drug_class" in p and "abuse_control" in p and "age_min" in p
    pid = scenarios["cold_tablet_out_at_S01"]["product_id"]
    hit = [p for p in r["results"] if p["id"] == pid]
    assert hit and hit[0]["availability"]["current"]["status"] == "out_of_stock"


def test_search_symptom_fallback(client):
    """Symptom-only queries (AICS may return 0) fall back to local symptom / synonym matching."""
    for q in ("熱", "せき", "鼻水", "かぜ"):
        r = client.get("/api/search", params={"q": q, "store_id": "S01", "page_size": 10}).json()
        assert r["results"], q
        assert any(p.get("drug_class") for p in r["results"][:5]), q
    from app import deps

    ids = deps.symptom_search("熱", 10)
    assert ids and any("解熱" in (deps.to_product(i).get("category_path") or "") or "発熱" in deps.to_product(i).get("symptoms", [])
                       for i in ids[:5])


def test_search_in_store_only(client):
    r = client.get("/api/search", params={"q": "冷却シート", "store_id": "S01", "in_store_only": 1}).json()
    assert r["results"]
    assert all(p["availability"]["current"]["status"] in ("in_stock", "low_stock") for p in r["results"])


def test_product_availability_and_layout_and_route(client, scenarios):
    pid = scenarios["fever_set_S01"][0]
    av = client.get(f"/api/products/{pid}/availability", params={"store_id": "S01"}).json()
    assert av["current"]["status"] in ("in_stock", "low_stock") and av["product"]["id"] == pid
    assert client.get("/api/products/0000000000000/availability").status_code == 404
    lay = client.get("/api/stores/S01/layout").json()
    assert lay["store_id"] == "S01" and (lay.get("fixtures") or lay.get("gondolas"))
    route = client.post("/api/route", json={"store_id": "S01", "product_ids": scenarios["fever_set_S01"][:4]}).json()
    assert [s["no"] for s in route["stops"]] == list(range(1, len(route["stops"]) + 1)) and route["polyline"]


def test_photos_and_static(client):
    assert client.get("/api/photos/shelf_photos/S01/nope.jpg").status_code == 404
    assert client.get("/api/photos/../../etc/passwd").status_code == 404
    assert client.get("/").status_code == 200
    assert client.get("/static/shared/img/logo.svg").status_code == 200
    assert client.get("/static/shared/css/tokens.css").status_code == 200


def test_staff_routes_absent_in_customer_mode(client):
    assert client.get("/api/staff/demo-photos").status_code in (404, 405)


def _stream(client, msg, sid="pytest-s1"):
    r = client.post("/api/agent/stream", json={"session_id": sid, "message": msg, "store_id": "S01"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    return sse_events(r.text)


def test_agent_stream_fever_mock(client):
    ev = _stream(client, "昨日から熱があって、かぜっぽいです")
    types = [e["type"] for e in ev]
    assert types[0] == "status" and types[-1] == "done" and "chips" in types
    act = next(e for e in ev if e["type"] == "action")
    assert act["name"] == "show_store_items"
    args = act["args"]
    nos = [it["no"] for it in args["items"] if it["no"]]
    assert nos == list(range(1, len(nos) + 1)) and len(nos) >= 2
    assert args["route"]["stops"] and args["disclaimer"].startswith("※本サービスは")
    meds = [it for it in args["items"] if it["product"].get("drug_class") in ("第1類医薬品", "指定第2類医薬品", "第2類医薬品", "第3類医薬品")]
    assert len(meds) <= 1
    for it in args["items"]:
        assert it["availability"]["current"]["store_id"] == "S01"


def test_agent_stream_red_flag_first(client):
    ev = _stream(client, "3日前から39度の熱が下がらない", sid="pytest-rf")
    first_text = next(e for e in ev if e["type"] == "text")
    assert "受診" in first_text["text"][:40]
    for e in ev:
        if e["type"] == "action":
            assert all(not it["product"].get("drug_class", "").endswith("類医薬品") for it in e["args"]["items"])
    assert next(e for e in ev if e["type"] == "done")["red_flags"]


def test_agent_stream_rejects_empty(client):
    assert client.post("/api/agent/stream", json={"message": " "}).status_code == 400


def test_health(client):
    h = client.get("/api/health").json()
    assert h["ok"] and h["data_mode"] == "local" and h["catalog"] > 1000


def test_fixture_elevation_endpoint(client, scenarios):
    pid = scenarios["fever_set_S01"][1]
    av = client.get(f"/api/products/{pid}/availability", params={"store_id": "S01"}).json()
    sh = av["current"]["shelf"]
    g = client.get(f"/api/stores/S01/fixtures/{sh['fixture_id']}").json()
    assert g["fixture"]["id"] == sh["fixture_id"] and g["tiers"][0]["tier"] == g["fixture"]["tiers"]
    assert all(len(t["slots"]) == g["fixture"]["slots_per_tier"] for t in g["tiers"])
    cells = {s["slot_id"]: s for t in g["tiers"] for s in t["slots"]}
    assert all(any(p["id"] == pid for p in cells[x]["products"]) for x in sh["slot_ids"])
    assert client.get("/api/stores/S01/fixtures/ZZ99").status_code == 404
