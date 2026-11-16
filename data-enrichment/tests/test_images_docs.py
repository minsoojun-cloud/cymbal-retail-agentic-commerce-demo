"""Tests for ① seasonal image studio presets and ② document extraction (offline: Gemini & GCS are stubbed)."""
import io
import json
import os
import tempfile

os.environ["OFFLINE"] = "true"
os.environ.setdefault("LOCAL_GCS_DIR", tempfile.mkdtemp(prefix="gcs_test_"))

from fastapi.testclient import TestClient  # noqa: E402

from app import doc_extract, image_presets, main  # noqa: E402
from app.config import settings  # noqa: E402
from app.repository import product_to_row, store  # noqa: E402

settings.offline = True

SANMA = {
    "sku": "4925319234365", "title": "北海道産 生さんま 2尾", "brand": "", "category": "お魚・水産加工品 > さんま > 生さんま",
    "group": "fresh", "price": 398, "description": "脂ののった秋の味覚。塩焼きでどうぞ。\n内容量：2尾 / 産地：北海道産 / 保存方法：冷蔵",
    "product_url": "", "image_url": "",
    "raw_attributes": {"season_months": "9 / 10 / 11", "on_sale": "true", "promo_text": "今週のおトクな！おすすめ品",
                       "dishes": "塩焼き / 蒲焼き"},
}
HAKUSAI = {
    "sku": "4913667472959", "title": "茨城県産 白菜 1/2カット", "brand": "", "category": "野菜・果物 > 葉物野菜 > 白菜",
    "group": "fresh", "price": 198, "description": "鍋物や漬物に。\n内容量：1/2カット / 産地：茨城県産 / 保存方法：冷蔵",
    "product_url": "", "image_url": "", "raw_attributes": {"season_months": "11 / 12 / 1 / 2", "on_sale": "false"},
}
SPONGE = {
    "sku": "4925863331336", "title": "Cymbal キッチンスポンジ 3個入", "brand": "Cymbal", "category": "日用品・キッチン消耗品 > 台所用スポンジ",
    "group": "living", "price": 198, "description": "よく泡立ち水切れのよい台所用スポンジです。", "product_url": "", "image_url": "",
    "raw_attributes": {"size": "3個入", "on_sale": "false"},
}
PAN = {
    "sku": "4954950777214", "title": "Cymbal ベーシック フッ素加工フライパン 20cm", "brand": "Cymbal ベーシック",
    "category": "キッチン・調理器具 > フライパン・鍋 > フライパン", "group": "kitchen", "price": 1280,
    "description": "毎日使いやすい20cmのフライパン。", "product_url": "", "image_url": "", "raw_attributes": {"base_id": "z_kitchen_pan_20"},
}

client = TestClient(main.app)


def setup_module(_):
    store.products.clear(); store.records.clear(); store.extras.clear(); store.images.clear()
    store.load([dict(SANMA), dict(HAKUSAI), dict(SPONGE), dict(PAN)])


def _ids(presets):
    return {p["id"]: p for p in presets}


def test_presets_gating_requires_evidence():
    s = _ids(image_presets.evaluate(SANMA, []))
    assert s["autumn-taste"]["available"] and "9" in s["autumn-taste"]["evidence"]
    assert s["sale"]["available"] and "on_sale" in s["sale"]["evidence"]
    assert not s["winter-nabe"]["available"] and "鍋" in s["winter-nabe"]["reason"]
    assert not s["summer-cool"]["available"]
    h = _ids(image_presets.evaluate(HAKUSAI, []))
    assert h["winter-nabe"]["available"] and "鍋" in h["winter-nabe"]["evidence"]
    assert not h["sale"]["available"]                      # on_sale=false, no promo -> no sale banner
    assert h["ec-white"]["available"] and h["lifestyle"]["available"]


def test_presets_category_filter():
    ids = set(_ids(image_presets.evaluate(SPONGE, [])))
    assert "autumn-taste" not in ids and "winter-nabe" not in ids and "ec-white" in ids and "newlife" in ids


def test_presets_use_approved_attributes():
    recs = [{"kind": "attribute", "attr_key": "cook_time_min", "value": 3, "unit": "分", "gate_status": "auto_approved"}]
    q = _ids(image_presets.evaluate(SANMA, recs))
    assert q["quick-dinner"]["available"] and "3 分" in q["quick-dinner"]["evidence"]
    recs[0]["gate_status"] = "needs_review"               # not approved -> not evidence
    assert not _ids(image_presets.evaluate(SANMA, recs))["quick-dinner"]["available"]


def test_generate_save_delete_flow():
    r = client.get("/api/images/presets", params={"sku": SANMA["sku"]})
    assert r.status_code == 200 and r.json()["options"]["default_size"] == 600
    bad = client.post(f"/api/products/{SANMA['sku']}/images/generate", json={"presets": ["winter-nabe"], "base": {"type": "none"}})
    assert bad.status_code == 400
    with client.stream("POST", f"/api/products/{SANMA['sku']}/images/generate",
                       json={"presets": ["autumn-taste"], "base": {"type": "none"}, "n": 3, "size": 300}) as resp:
        evs = [json.loads(l[6:]) for l in resp.iter_lines() if l.startswith("data: ")]
    imgs = [e["image"] for e in evs if e["event"] == "image"]
    assert len(imgs) == 3 and evs[-1]["event"] == "complete"
    for im in imgs:
        assert im["gcs_uri"].startswith(f"gs://{settings.image_bucket}/{SANMA['sku']}/{SANMA['sku']}_autumn-taste_")
        assert im["gcs_uri"].endswith(".jpg") and (im["width"], im["height"]) == (300, 300)
    g = client.get(imgs[0]["url"])
    assert g.status_code == 200 and g.headers["content-type"] == "image/jpeg"
    s = client.post(f"/api/products/{SANMA['sku']}/images/save",
                    json={"image_ids": [imgs[0]["image_id"], imgs[1]["image_id"]], "primary_id": imgs[1]["image_id"],
                          "update_aics": False})
    assert s.status_code == 200 and len(s.json()["saved"]) == 2 and s.json()["aics"] is None
    assert client.get(f"/api/products/{SANMA['sku']}").json()["product"]["images"][0]["is_primary"]
    d = client.delete(f"/api/products/{SANMA['sku']}/images/{imgs[2]['image_id']}")
    assert d.status_code == 200 and d.json()["gcs_deleted"]
    assert client.get(imgs[2]["url"]).status_code == 404


def test_size_option_non_square():
    with client.stream("POST", f"/api/products/{SPONGE['sku']}/images/generate",
                       json={"presets": ["ec-white"], "base": {"type": "none"}, "n": 2, "size": 600, "aspect": "16:9"}) as resp:
        evs = [json.loads(l[6:]) for l in resp.iter_lines() if l.startswith("data: ")]
    im = next(e["image"] for e in evs if e["event"] == "image")
    assert max(im["width"], im["height"]) == 600


def test_xlsx_to_text():
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = "価格表"
    ws.append(["JAN", "商品名", "税込価格"]); ws.append(["4913667472959", "白菜 1/2カット", 198])
    buf = io.BytesIO(); wb.save(buf)
    t = doc_extract.xlsx_to_text(buf.getvalue())
    assert "### シート: 価格表" in t and "4913667472959\t白菜 1/2カット\t198" in t


def test_match_sku_by_jan_and_title():
    m = doc_extract.match_sku({"jan": "4954950777214", "title": ""}, list(store.products.values()))
    assert m and m[0]["sku"] == PAN["sku"] and m[0]["why"] == "JAN一致"
    m = doc_extract.match_sku({"title": "Cymbal ベーシック フッ素加工フライパン 20cm"}, list(store.products.values()))
    assert m and m[0]["sku"] == PAN["sku"]


EX = {"idx": 0, "model_number": "", "jan": "4954950777214", "title": "Cymbal ベーシック フッ素加工フライパン 20cm",
      "description": "", "price": 1280, "attributes": [
          {"key": "material", "label": "素材", "value": "アルミニウム合金（内面フッ素樹脂加工）", "evidence": "本体：アルミニウム合金", "page": 1},
          {"key": "ih_compatible", "label": "IH対応", "value": "IH対応（100V/200V）", "evidence": "IH対応（100V/200V）", "page": 1},
          {"key": "dimensions", "label": "寸法", "value": "直径20×深さ5.0cm", "evidence": "直径20×深さ5.0cm", "page": 1}]}


def test_merge_fill_vs_overwrite():
    base = {**PAN, "raw_attributes": {"base_id": "z_kitchen_pan_20", "material": "アルミニウム"}}
    p, diff = doc_extract.merge(dict(base), EX, "fill", PAN["sku"], "spec.pdf", "gs://b/spec.pdf")
    acts = {d["field"]: d["action"] for d in diff}
    assert acts["attr:material"] == "keep" and p["raw_attributes"]["material"] == "アルミニウム"
    assert acts["attr:ih_compatible"] == "add" and p["raw_attributes"]["ih_compatible"] == "IH対応（100V/200V）"
    assert any(d["key"] == "material" for d in p["doc_sources"])          # kept values stay as document evidence
    p2, _ = doc_extract.merge(dict(base), EX, "overwrite", PAN["sku"], "spec.pdf", "gs://b/spec.pdf")
    assert p2["raw_attributes"]["material"].startswith("アルミニウム合金")
    new, d3 = doc_extract.merge(None, EX, "fill", "DOC-PAN", "spec.pdf", "gs://b/spec.pdf")
    assert new["group"] == "kitchen" and all(d["action"] == "new" for d in d3)


def test_docs_preview_and_apply():
    r = client.post("/api/docs/preview", json={"sku": PAN["sku"], "product": EX, "mode": "fill"})
    assert r.status_code == 200 and r.json()["changes"] >= 1
    with client.stream("POST", "/api/docs/apply", json={"items": [{"sku": PAN["sku"], "product": EX, "mode": "fill",
                                                                   "file_uri": "gs://b/spec.pdf", "file_name": "spec.pdf"}],
                                                        "update_aics": False}) as resp:
        evs = [json.loads(l[6:]) for l in resp.iter_lines() if l.startswith("data: ")]
    kinds = [e["event"] for e in evs]
    assert "merged" in kinds and "enriched" in kinds and kinds[-1] == "complete" and "aics" not in kinds
    det = client.get(f"/api/products/{PAN['sku']}").json()
    assert "【資料】" in det["source_text"] and "IH対応（100V/200V）" in det["source_text"]


def test_product_row_has_latest_columns():
    row = product_to_row({**PAN, "source": "doc", "doc_sources": [{"file_name": "x"}]})
    assert row["updated_at"] and row["source"] == "doc" and json.loads(row["doc_sources_json"])[0]["file_name"] == "x"


def test_overwrite_keeps_identity_fields():
    p, diff = doc_extract.merge(dict(PAN), {**EX, "title": "別名フライパン", "price": 1280.0}, "overwrite", PAN["sku"], "x.pdf", "gs://b/x.pdf")
    acts = {d["field"]: d["action"] for d in diff}
    assert acts["title"] == "keep" and p["title"] == PAN["title"]


def test_aics_product_row_never_rewrites_numeric_attributes():
    from app import aics
    existing = {"id": "1", "title": "x", "attributes": [{"key": "price_tax_excluded", "value": {"numbers": [248.0], "text": []}},
                                                        {"key": "origin", "value": {"text": ["国産"], "numbers": []}}]}
    row, n = aics.product_row({"sku": "1", "raw_attributes": {"price_tax_excluded": "248", "origin": "国産", "allergens": "卵"}}, existing)
    attrs = {a["key"]: a for a in row["attributes"]}
    assert attrs["price_tax_excluded"]["value"]["numbers"] == [248.0] and n == 1 and attrs["allergens"]["value"]["text"] == ["卵"]
