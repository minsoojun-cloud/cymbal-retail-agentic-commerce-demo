"""Unit tests for recommend_dinner_set (dinner.py + server wiring). No network: catalog / profile / history are fakes.

Run:
  cd shared/mcp_server && uv run --no-project --with-requirements requirements.txt --with pytest pytest -q tests
"""
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dinner  # noqa: E402
import server  # noqa: E402

TODAY = dt.date(2026, 11, 4)
_SEED_PERSONAS = Path(__file__).resolve().parents[3] / "seed" / "personas" / "personas.json"
_BUNDLED_PERSONAS = Path(__file__).resolve().parents[1] / "data" / "personas.json"
PERSONA = json.loads((_SEED_PERSONAS if _SEED_PERSONAS.exists() else _BUNDLED_PERSONAS).read_text(encoding="utf-8"))[0]


def row(pid, title, cat, price, original=None, sale=False, seasonal=False, size="", allergens=(), avail="IN_STOCK",
        months=None, desc=""):
    attrs = [{"key": "on_sale", "value": {"text": ["true" if sale else "false"]}},
             {"key": "discount_rate", "value": {"numbers": [20.0 if sale else 0.0]}},
             {"key": "is_seasonal", "value": {"text": ["true" if seasonal else "false"]}},
             {"key": "size", "value": {"text": [size]}},
             {"key": "allergens", "value": {"text": list(allergens) or ["なし"]}},
             {"key": "is_food", "value": {"text": ["true"]}}]
    if months:
        attrs.append({"key": "season_months", "value": {"numbers": [float(m) for m in months]}})
    return {"id": pid, "title": title, "categories": [cat], "attributes": attrs, "description": desc,
            "priceInfo": {"price": float(price), "originalPrice": float(original or price)}, "availability": avail,
            "images": [{"uri": f"https://img/{pid}.jpg"}], "rating": {"averageRating": 4.2, "ratingCount": 50}}


CATALOG_ROWS = [
    row("F1", "北海道産 生秋鮭 切り身 4切（約320g）", "お魚・水産加工品 > 鮮魚 > 鮭・サーモン", 640, 800, sale=True, seasonal=True, size="4切（約320g）"),
    row("F2", "ノルウェー産 塩さば 切り身 4切", "お魚・水産加工品 > 塩さば・塩鮭 > 塩さば", 473, size="4切"),
    row("X1", "えび天ぷら 4尾", "お惣菜・ミールキット > 揚げ物 > 天ぷら", 500, sale=True, allergens=["えび", "小麦"]),
    row("X2", "国産 むきエビ 鍋用 200g", "お魚・水産加工品 > えび・かに > むきえび", 600, sale=True, seasonal=True),
    row("X3", "海鮮しゅうまい 8個", "お惣菜・ミールキット > 中華惣菜 > 焼売", 300, allergens=["えび"]),
    row("X4", "国産 若鶏もも 唐揚げ用 2kg 業務用", "お肉・お肉加工品 > 鶏肉 > もも肉", 1800, sale=True),
    row("X5", "北海道産 生秋鮭 切り身 8切", "お魚・水産加工品 > 鮮魚 > 鮭・サーモン", 900, sale=True, seasonal=True, avail="OUT_OF_STOCK"),
    row("X6", "Cymbal 1歳頃から こどものみそ汁 5食入", "ベビー・キッズ食品 > 幼児食 > 子ども向けスープ・みそ汁", 321),
    row("X7", "激辛 麻辣 豚肉炒め ミールキット 2人前", "お惣菜・ミールキット > ミールキット > 中華のミールキット", 700, sale=True),
    row("M1", "[店内調理] 国産若鶏の唐揚げ（もも）約400g", "お惣菜・ミールキット > 揚げ物 > 唐揚げ", 645, size="約400g"),
    row("M2", "Cymbal 国産牛豚 ハンバーグ 4個入", "冷凍食品・アイス > 冷凍 お肉おかず > ハンバーグ", 538, sale=True, size="4個"),
    row("M3", "カナダ産 豚こま切れ 400g", "お肉・お肉加工品 > 豚肉 > こま切れ・切り落とし", 516, size="400g"),
    row("S1", "Cymbal 自然解凍OK お弁当用 甘い玉子焼き 8個入", "冷凍食品・アイス > 冷凍 お弁当おかず > 卵焼き", 267, size="8個", allergens=["卵"]),
    row("S2", "Cymbal スイートコーン ホールカーネル 190g", "缶詰・粉類・乾物 > 缶詰 > コーン缶", 98, sale=True),
    row("S3", "国産 ほうれん草 1束", "野菜・果物 > 野菜 > 葉物野菜", 198, seasonal=True),
    row("S4", "長野県産 ぶなしめじ 1パック", "野菜・果物 > きのこ > しめじ", 108, months=[9, 10, 11]),
    row("S5", "国産 白菜 1/2カット", "野菜・果物 > 野菜 > 葉物野菜", 170, sale=True, seasonal=True),
    row("S6", "ポテトサラダ 200g", "お惣菜・ミールキット > サラダ > ポテトサラダ", 300),
    row("P1", "Cymbal 生みそタイプ みそ汁 とうふ 10食入", "お米・麺・インスタント > インスタントスープ・みそ汁 > 即席みそ汁", 278, sale=True),
    row("P2", "国産大豆 絹ごし豆腐 300g", "豆腐・納豆・練り物 > 豆腐 > 絹ごし豆腐", 98),
    row("N1", "Cymbal 寄せ鍋つゆ ストレート 3〜4人前 750g", "調味料 > 鍋つゆ・鍋の素 > 寄せ鍋つゆ", 213, seasonal=True),
    row("N2", "国産 鍋用 鶏つくね 300g", "お肉・お肉加工品 > 鶏肉 > 鍋用・味付け", 494, seasonal=True, size="300g"),
    row("N3", "Cymbal ゆでうどん 180g×3食", "お米・麺・インスタント > 麺 > うどん", 98),
    row("C1", "Cymbal カレールー 中辛 8皿分", "調味料 > カレー・シチュー > カレールー", 138),
    row("C2", "国産 豚肩ロース カレー用角切り 350g", "お肉・お肉加工品 > 豚肉 > 角切り・ブロック", 516, size="350g"),
    row("R1", "Cymbal パックご飯 200g×3", "お米・麺・インスタント > パックご飯・レンジご飯 > 白ご飯", 298),
    row("D1", "青森県産 りんご（ふじ）3玉", "野菜・果物 > 果物 > りんご", 498, 598, sale=True, seasonal=True),
    row("D2", "愛知県産 次郎柿 4個", "野菜・果物 > 果物 > 柿", 473, seasonal=True),
]
CATALOG = [dinner.normalize_product(r) for r in CATALOG_ROWS]
HISTORY = [
    {"product_id": "M3", "product_title": "カナダ産 豚こま切れ 400g", "category": "お肉・お肉加工品 > 豚肉 > こま切れ・切り落とし", "times": 9},
    {"product_id": "S4", "product_title": "長野県産 ぶなしめじ 1パック", "category": "野菜・果物 > きのこ > しめじ", "times": 6},
    {"product_id": "Z9", "product_title": "国産 キャベツ 1玉", "category": "野菜・果物 > 野菜 > 葉物野菜", "times": 5},
]


def rec(request="", **kw):
    return dinner.recommend(PERSONA, HISTORY, CATALOG, request=request, customer_id="CR-0001", today=kw.pop("today", TODAY), **kw)


def all_items(res):
    return [i for s in res["sets"] for i in s["items"]]


# ── composition ──────────────────────────────────────────────────────────────

def test_primary_set_is_balanced():
    res = rec("今夜の夕食をお勧めしてね")
    assert 1 <= len(res["sets"]) <= 3
    p = res["sets"][0]
    roles = [i["role"] for i in p["items"]]
    assert 4 <= len(p["items"]) <= 5
    assert roles[0] == "主菜" and len(set(roles)) >= 3
    assert p["kind"] == "fish"  # default: 和定食 for さくら
    assert p["total_tax_included"] == sum(i["subtotal"] for i in p["items"])
    for s in res["sets"]:
        assert 4 <= len(s["items"]) <= 5 and s["name"] and s["concept"]
    assert res["servings"] == 4 and res["theme"].startswith("さくらさんご家族の今夜の夕食セット")


def test_allergen_bulk_oos_dislikes_excluded():
    ids = {i["product_id"] for i in all_items(rec("今夜の夕食をお勧めしてね"))}
    ids |= {i["product_id"] for i in all_items(rec("鍋にしたい"))}
    ids |= {i["product_id"] for i in all_items(rec("お肉がいいな"))}
    assert not ids & {"X1", "X2", "X3", "X4", "X5", "X6", "X7"}
    for i in all_items(rec("")):
        assert not any(w in i["title"] for w in ("えび", "エビ", "海老", "シュリンプ", "業務用"))


def test_tags_and_reasons_are_grounded():
    items = {i["product_id"]: i for i in all_items(rec("")) + all_items(rec("お肉がいいな"))}
    for i in items.values():
        assert i["reason"] and set(i["tags"]) <= set(dinner.TAG_ORDER)
    if "F1" in items:
        assert {"特価", "旬"} <= set(items["F1"]["tags"])
    kid = [i for i in items.values() if i["product_id"] in ("S1", "S2")]
    assert kid and all("家族の好み" in i["tags"] and "陽菜ちゃん" in i["reason"] for i in kid)
    if "M3" in items:
        assert "よく購入" in items["M3"]["tags"] and "よく購入" in items["M3"]["reason"]


def test_fish_set_has_kid_friendly_side():
    p = rec("")["sets"][0]
    assert any(i["product_id"] in ("S1", "S2") for i in p["items"] if i["role"] == "副菜")


@pytest.mark.parametrize("req,kind", [("お肉がいいな", "meat"), ("鍋にしたい", "nabe"), ("カレーが食べたい", "curry"),
                                      ("魚で", "fish")])
def test_request_changes_primary(req, kind):
    res = rec(req)
    assert res["sets"][0]["kind"] == kind


def test_curry_set_has_staple_and_chukara():
    p = rec("カレーが食べたい")["sets"][0]
    ids = [i["product_id"] for i in p["items"]]
    assert "C1" in ids and "R1" in ids


def test_budget_respected():
    for b in (1500, 2000):
        res = rec("", budget_jpy=b)
        assert res["budget_jpy"] == b
        for s in res["sets"]:
            assert s["total_tax_included"] <= b
    assert rec("予算1500円で")["budget_jpy"] == 1500


def test_servings_quantity():
    two = {i["product_id"]: i for i in rec("", servings=2)["sets"][0]["items"]}
    six = {i["product_id"]: i for i in rec("", servings=6)["sets"][0]["items"]}
    main2 = next(i for i in two.values() if i["role"] == "主菜")
    assert main2["quantity"] == 1
    main6 = next(i for i in six.values() if i["role"] == "主菜")
    assert main6["quantity"] >= 1 and main6["subtotal"] == main6["price"] * main6["quantity"]
    assert rec("2人分の晩ご飯")["servings"] == 2


def test_quick_request_prefers_quick_items():
    res = rec("時短で簡単に")
    assert sum("時短" in i["tags"] for i in res["sets"][0]["items"]) >= 1


def test_deterministic_per_day():
    a, b = rec("今夜の夕食"), rec("今夜の夕食")
    assert json.dumps(a, ensure_ascii=False) == json.dumps(b, ensure_ascii=False)
    assert dinner.jitter("CR-0001", "2026-11-04", "", "F1") != dinner.jitter("CR-0001", "2026-11-05", "", "F1")


def test_show_args_shape():
    res = rec("")
    a = res["show_products_on_page_args"]
    flat = [pid for s in a["sections"] for pid in s["product_ids"]]
    assert a["product_ids"] == flat and len(a["reasons"]) == len(flat)
    for s in a["sections"]:
        assert s["label"] in dinner.ROLE_ORDER and len(s["reasons"]) == len(s["product_ids"]) == len(s["tags"]) == len(s["quantities"])
    qmap = {i["product_id"]: i["quantity"] for i in res["sets"][0]["items"]}
    assert a["quantities"] == [qmap[x] for x in a["product_ids"]]
    assert [q for s in a["sections"] for q in s["quantities"]] == a["quantities"]
    assert a["theme"] == res["theme"] and a["message"]
    for alt in res["sets"][1:]:
        aa = alt["show_products_on_page_args"]
        assert aa["product_ids"] == [i["product_id"] for i in alt["items"]] and alt["name"].replace("セット", "") in aa["theme"]


def test_signals():
    sig = rec("")["signals"]
    assert sig["frequent"][0] == "豚こま切れ"
    assert any(f.startswith("陽菜ちゃん") and "えび" in f for f in sig["family"])
    assert sig["sale_count"] > 0 and "えび" in sig["excluded"]


def test_exclusion_words_variants():
    words = dinner.exclusion_words(PERSONA)
    for w in ("えび", "エビ", "海老", "シュリンプ"):
        assert w in words


@pytest.mark.parametrize("title,exp", [("カナダ産 豚こま切れ 300g", "豚こま切れ"), ("Cymbal 牛乳 200ml×3本", "牛乳"),
                                       ("[鮮度+] 北海道産 生秋鮭 切り身 2切（約160g）", "秋鮭 切り身")])
def test_short_name(title, exp):
    assert dinner.short_name(title).replace("生秋鮭", "秋鮭") == exp


def test_parse_request():
    r = dinner.parse_request("時短でお肉、予算3,000円・3人分で")
    assert r["meat"] and r["quick"] and r["budget"] == 3000 and r["servings"] == 3


def test_persona_has_family_preferences():
    fp = {f["relation"]: f for f in PERSONA["family_preferences"]}
    assert set(fp) == {"本人", "夫", "長男", "長女"} and fp["長女"]["allergies"] == ["えび"]
    bundled = json.loads((Path(server.__file__).parent / "data" / "personas.json").read_text(encoding="utf-8"))[0]
    assert bundled["family_preferences"] == PERSONA["family_preferences"]


# ── server wiring ────────────────────────────────────────────────────────────

def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture
def wired(monkeypatch):
    monkeypatch.setattr(server, "get_customer_profile_sync", lambda cid: {**PERSONA, "_source": "fake"})
    monkeypatch.setattr(server, "dinner_history_rows", lambda cid: (HISTORY, "fake"))
    monkeypatch.setattr(server, "dinner_catalog", lambda: (CATALOG, "fake"))


def test_tool_via_mcp(wired):
    out = run(server.mcp.call_tool("recommend_dinner_set", {"customer_id": "CR-0001", "request": "", "budget_jpy": "0",
                                                            "servings": 4.0}))
    blocks = out[0] if isinstance(out, tuple) else out
    res = json.loads(blocks[0].text)
    assert res["sets"] and res["_source"]["catalog"] == "fake" and "show_products_on_page_args" in res


def test_tool_schema():
    tools = {t.name: t for t in run(server.mcp.list_tools())}
    s = tools["recommend_dinner_set"].inputSchema
    assert s["required"] == ["customer_id"]
    assert s["properties"]["budget_jpy"]["type"] == "integer" and s["properties"]["request"]["type"] == "string"
    assert "default" not in json.dumps(s) and "title" not in s


def test_catalog_fallback_to_file(monkeypatch, tmp_path):
    f = tmp_path / "cat.jsonl"
    f.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in CATALOG_ROWS), encoding="utf-8")

    def boom():
        raise RuntimeError("bq down")

    monkeypatch.setattr(server, "_dinner_catalog_bq", boom)
    monkeypatch.setattr(server, "DINNER_CATALOG_FILE", str(f))
    monkeypatch.setattr(server, "_dinner_cache", {"at": 0.0, "items": None, "source": ""})
    items, src = server.dinner_catalog()
    assert src == "file" and len(items) == len(CATALOG_ROWS)
    items2, src2 = server.dinner_catalog()  # cached
    assert src2 == "file" and items2 is items


def test_profile_json_merge(monkeypatch):
    pj = json.dumps(PERSONA, ensure_ascii=False)
    monkeypatch.setattr(server, "_bq_query", lambda sql, params: [{"customer_id": "CR-0001", "name": "さくら",
                                                                   "family_preferences": None, "profile_json": pj}])
    prof = server.get_customer_profile_sync("CR-0001")
    assert prof["_source"] == "bigquery" and "profile_json" not in prof
    assert prof["family_preferences"][3]["call_name"] == "陽菜ちゃん"


def _p(title, size, top, price=100):
    return {"title": title, "size": size, "top": top, "price": price}


@pytest.mark.parametrize("title,size,role,top,exp", [
    ("[ミールキット] 秋鮭ときのこのちゃんちゃん焼き 3〜4人前", "3〜4人前（約900g）", "主菜", "お惣菜・ミールキット", 1),
    ("Cymbal スイートコーン ホールカーネル 190g", "190g", "副菜", "缶詰・粉類・乾物", 1),
    ("Cymbal フリーズドライ みそ汁 とうふ 5食入", "5食入", "汁物", "お米・麺・インスタント", 1),
    ("フィリピン産 バナナ 1房（4〜5本）", "1房", "デザート・果物", "野菜・果物", 1),
    ("国産 ぶなしめじ 3パック（約300g）", "3パック", "副菜", "野菜・果物", 1),
    ("梨（にっこり）1玉（大）", "1玉", "デザート・果物", "野菜・果物", 1),
    ("プリン 3個入", "3個入", "デザート・果物", "卵・乳製品・豆乳・デザート", 1),
    ("レトルトカレー 170g×5食", "850g（170g×5）", "主菜", "調味料", 1),
    ("[店内調理] 豚の生姜焼き 1人前", "1人前", "主菜", "お惣菜・ミールキット", 4),
    ("即席 みそ汁 1食", "1食", "汁物", "お米・麺・インスタント", 4),
    ("なめらかプリン 1個", "1個", "デザート・果物", "卵・乳製品・豆乳・デザート", 4),
    ("生秋鮭 切り身 2切（約160g）", "2切（約160g）", "主菜", "お魚・水産加工品", 2),
])
def test_portion_qty(title, size, role, top, exp):
    assert dinner.portion_qty(_p(title, size, top), role, 4) == exp


def test_totals_use_quantity_and_reason_mentions_it():
    extra = CATALOG + [dinner.normalize_product(row("Q1", "[店内調理] 鮭の塩焼き 1人前", "お惣菜・ミールキット > 焼き物 > 焼き魚", 350,
                                                     seasonal=True, size="1人前"))]
    for req in ("", "お肉", "鍋", "カレー", "魚で"):
        res = dinner.recommend(PERSONA, HISTORY, extra, request=req, customer_id="CR-0001", today=TODAY)
        for s in res["sets"]:
            assert s["total_tax_included"] == sum(i["price"] * i["quantity"] for i in s["items"])
            for i in s["items"]:
                assert i["subtotal"] == i["price"] * i["quantity"]
                if i["quantity"] > 1:
                    assert f"4人分で{i['quantity']}" in i["reason"]
    q = dinner._item(dinner.normalize_product(row("Q2", "[店内調理] 鮭の塩焼き 1人前", "お惣菜・ミールキット > 焼き物 > 焼き魚", 350,
                                                   size="1人前")), "主菜",
                     dinner.Ctx(profile=PERSONA, hist=dinner.history_signals([]), req=dinner.parse_request(""), today=TODAY,
                                customer_id="CR-0001", servings=4, rules=[]))
    assert q["quantity"] == 4 and q["subtotal"] == 1400 and q["reason"].startswith("4人分で4食")
