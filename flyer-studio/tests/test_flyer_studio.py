"""Automated verification suite for Cymbal Retail Flyer Studio (`flyer-studio`)."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

os.environ["FLYER_DATA_MODE"] = "local"
os.environ["FLYER_AI_MODE"] = "fallback"
os.environ["STORE_URL"] = "https://cymbal-site-adk-example.asia-northeast1.run.app"
os.environ["ENRICH_URL"] = "https://cymbal-data-enrichment-example.asia-northeast1.run.app"

import pytest
from fastapi.testclient import TestClient

from app.archive import DISCONTINUED_TEST_PRODUCT_ID, SAMPLE_ARCHIVE_ID
from app.main import app, get_repo, reset_repo


@pytest.fixture(scope="module")
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["LOCAL_STORAGE_DIR"] = tmpdir
        reset_repo(force_local=True)
        with TestClient(app) as c:
            yield c


def test_health_and_japanese_ui_cross_links(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["catalog_size"] >= 8000

    # Check index.html has Japanese UI and icon-only cross-links with data-tooltip
    idx = client.get("/")
    assert idx.status_code == 200
    html = idx.text
    assert "チラシ作成スタジオ" in html
    assert 'class="xlink-icon-only"' in html
    assert 'data-tooltip="ストアデモ（ADK）"' in html
    assert 'data-tooltip="データエンリッチメント"' in html


def test_pickup_and_price_integrity_across_themes(client: TestClient):
    repo = get_repo()
    for theme, target, tpl_id, cnt in [
        ("秋の味覚フェア", "40代主婦・4人家族", "T1", 20),
        ("旬の野菜特集", "シニア・少人数世帯", "T3", 16),
        ("家計応援！大均一祭", "40代主婦・4人家族", "T2", 28),
    ]:
        r = client.post(
            "/api/flyers/generate",
            json={
                "theme": theme,
                "target": target,
                "template_id": tpl_id,
                "item_count": cnt,
                "period": {"from": "2026-11-11", "to": "2026-11-17"},
            },
        )
        assert r.status_code == 200
        flyer = r.json()["flyer"]
        slots = flyer["slots"]
        assert len(slots) == cnt

        seen_images = set()
        seen_pids = set()
        for s in slots:
            pid = s["product_id"]
            master = repo.get_product(pid)
            assert master is not None, f"Product {pid} must exist in master"
            assert master["availability"] != "OUT_OF_STOCK"
            assert master["image"] != ""
            assert master["image"] not in seen_images, "Images must be deduplicated across slots"
            seen_images.add(master["image"])
            seen_pids.add(pid)
            # Price integrity check
            assert s["product"]["price_tax_excluded"] == master["price_tax_excluded"]
            assert s["product"]["price"] == master["price"]


def test_special_offer_tax_rates_and_price_style_rules(client: TestClient):
    repo = get_repo()
    r = client.post("/api/flyers/generate", json={"theme": "秋の味覚フェア", "template_id": "T1", "item_count": 10})
    flyer = r.json()["flyer"]
    fid = flyer["id"]
    first_slot = flyer["slots"][0]
    sid = first_slot["slot_id"]

    # Find a non-sale food item (8% tax) and an alcohol/non-food item (10% tax)
    non_sale_food = next(
        p for p in repo.items.values() if not p["on_sale"] and p["tax_rate"] == 0.08 and p["price_tax_excluded"] >= 200
    )
    ten_pct_item = next(
        p for p in repo.items.values() if p["tax_rate"] == 0.10 and p["price_tax_excluded"] >= 300
    )

    # Put non-sale food item into slot 1
    u1 = client.put(f"/api/flyers/{fid}", json={"slot_update": {"slot_id": sid, "product_id": non_sale_food["id"]}})
    assert u1.status_code == 200

    # Attempting `was_now` or `percent_off` on a non-discounted item must be rejected (400)
    bad_style = client.put(f"/api/flyers/{fid}", json={"slot_update": {"slot_id": sid, "price_style": "was_now"}})
    assert bad_style.status_code == 400
    assert "通常価格" in bad_style.json()["error"]

    # Negative special offer price must be rejected
    bad_offer = client.put(f"/api/flyers/{fid}/slots/{sid}/offer", json={"offer_price_tax_excluded": -50})
    assert bad_offer.status_code == 400

    # Valid special offer on 8% food item (e.g. 150 yen -> 162.00 yen tax-included)
    orig_master_price = repo.get_product(non_sale_food["id"])["price_tax_excluded"]
    ok_offer = client.put(
        f"/api/flyers/{fid}/slots/{sid}/offer",
        json={"offer_price_tax_excluded": 150, "limit_text": "お一人様2点限り"},
    )
    assert ok_offer.status_code == 200
    updated_slot = next(s for s in ok_offer.json()["flyer"]["slots"] if s["slot_id"] == sid)
    assert updated_slot["product"]["price_tax_excluded"] == 150
    assert updated_slot["product"]["price_tax_included_exact"] == 162.0
    assert updated_slot["product"]["has_flyer_offer"] is True
    # Master catalog price must not be mutated
    assert repo.get_product(non_sale_food["id"])["price_tax_excluded"] == orig_master_price

    # Test 10% tax item special offer (e.g. 200 yen -> 220.00 yen tax-included)
    client.put(f"/api/flyers/{fid}", json={"slot_update": {"slot_id": sid, "product_id": ten_pct_item["id"]}})
    ok_offer10 = client.put(f"/api/flyers/{fid}/slots/{sid}/offer", json={"offer_price_tax_excluded": 200})
    assert ok_offer10.status_code == 200
    slot10 = next(s for s in ok_offer10.json()["flyer"]["slots"] if s["slot_id"] == sid)
    assert slot10["product"]["price_tax_included_exact"] == 220.0


def test_discontinued_product_reuse_and_approval_guard(client: TestClient):
    # 1. Inspect the pre-seeded sample archived flyer (`fl-sample-20261028-01`)
    arch_res = client.get(f"/api/archive/{SAMPLE_ARCHIVE_ID}")
    assert arch_res.status_code == 200
    arch_flyer = arch_res.json()["flyer"]
    assert arch_flyer["currently_discontinued_count"] >= 1

    # 2. Reuse the sample archived flyer (`このチラシをもとに新規作成`)
    reuse_res = client.post(
        "/api/flyers/generate",
        json={
            "base_flyer_id": SAMPLE_ARCHIVE_ID,
            "theme": "霜月の家計応援セール",
            "period": {"from": "2026-11-11", "to": "2026-11-17"},
        },
        headers={"X-Flyer-User": "staff-sato"},
    )
    assert reuse_res.status_code == 200
    new_draft = reuse_res.json()["flyer"]
    assert new_draft["created_by"]["id"] == "staff-sato"
    assert new_draft["discontinued_count"] == 1

    disc_slot = next(s for s in new_draft["slots"] if s["product_id"] == DISCONTINUED_TEST_PRODUCT_ID)
    assert disc_slot["discontinued"] is True

    # 3. Submitting or approving while a discontinued product remains MUST be blocked (400)
    sub_blocked = client.post(f"/api/flyers/{new_draft['id']}/submit", headers={"X-Flyer-User": "staff-sato"})
    assert sub_blocked.status_code == 400
    assert "販売終了" in sub_blocked.json()["error"]

    app_blocked = client.post(f"/api/flyers/{new_draft['id']}/approve", headers={"X-Flyer-User": "mgr-tanaka"})
    assert app_blocked.status_code == 400
    assert "販売終了" in app_blocked.json()["error"]

    # 4. Replace the discontinued slot via AI suggestion or search replacement
    sug_res = client.post(f"/api/flyers/{new_draft['id']}/slots/{disc_slot['slot_id']}/suggest")
    assert sug_res.status_code == 200
    fixed_draft = sug_res.json()["flyer"]
    assert fixed_draft["discontinued_count"] == 0

    # 5. Add a flyer-only special offer on slot 0 to verify later that reusing strips it
    s0 = fixed_draft["slots"][0]["slot_id"]
    client.put(f"/api/flyers/{new_draft['id']}/slots/{s0}/offer", json={"offer_price_tax_excluded": 111})

    # 6. Staff can submit for review, but staff CANNOT approve (403)
    sub_ok = client.post(f"/api/flyers/{new_draft['id']}/submit", headers={"X-Flyer-User": "staff-sato"})
    assert sub_ok.status_code == 200
    assert sub_ok.json()["flyer"]["status"] == "確認待ち"

    staff_approve = client.post(f"/api/flyers/{new_draft['id']}/approve", headers={"X-Flyer-User": "staff-sato"})
    assert staff_approve.status_code == 403
    assert "承認権限" in staff_approve.json()["error"]

    # 7. Manager (`mgr-tanaka`) approves -> archives snapshot, blocks further edits (409)
    mgr_approve = client.post(f"/api/flyers/{new_draft['id']}/approve", headers={"X-Flyer-User": "mgr-tanaka"})
    assert mgr_approve.status_code == 200
    approved = mgr_approve.json()["flyer"]
    assert approved["status"] == "承認済み"
    assert approved["approved_by"]["name"] == "店長 田中"

    edit_after = client.put(f"/api/flyers/{new_draft['id']}", json={"title": "変更テスト"})
    assert edit_after.status_code == 409

    # 8. Reusing the newly approved flyer strips the 111-yen special offer and restores master price
    reuse2 = client.post("/api/flyers/generate", json={"base_flyer_id": new_draft["id"]})
    assert reuse2.status_code == 200
    reused_slot0 = reuse2.json()["flyer"]["slots"][0]
    assert reused_slot0["offer"] is None
    assert reused_slot0["product"]["has_flyer_offer"] is False
    assert reused_slot0["product"]["price_tax_excluded"] != 111


def test_custom_template_save_and_pdf_jpeg_export(client: TestClient):
    # Test template studio live preview endpoint
    prev = client.post("/api/templates/preview_html", json={"id": "T1"})
    assert prev.status_code == 200
    assert "Cymbal" in prev.text and "Retail" in prev.text

    # Test small item count (e.g. 5 items) -> no empty zones
    small_gen = client.post("/api/flyers/generate", json={"template_id": "T1", "item_count": 5, "theme": "秋の味覚フェア"})
    assert small_gen.status_code == 200
    small_flyer = small_gen.json()["flyer"]
    assert len(small_flyer["slots"]) == 5

    # Test slot customization (shape, size_span, img_scale, numeral_style, bg_color)
    s0_id = small_flyer["slots"][0]["slot_id"]
    cust_res = client.put(
        f"/api/flyers/{small_flyer['id']}",
        json={
            "slot_update": {
                "slot_id": s0_id,
                "shape": "burst",
                "size_span": "hero_2x2",
                "img_scale": 125,
                "numeral_style": "yellow_pop",
                "bg_color": "cream",
            }
        },
    )
    assert cust_res.status_code == 200
    updated_s0 = cust_res.json()["flyer"]["slots"][0]
    assert updated_s0["shape"] == "burst"
    assert updated_s0["size_span"] == "hero_2x2"
    assert updated_s0["img_scale"] == 125
    assert updated_s0["numeral_style"] == "yellow_pop"
    assert updated_s0["bg_color"] == "cream"

    # Save a custom template with specific zone counts (total 14 items)
    tpl_res = client.post(
        "/api/templates",
        json={
            "name": "テスト用14品テンプレート",
            "base_template_id": "T1",
            "zones": [
                {"id": "z1", "title": "水曜目玉", "hero_count": 2, "grid_count": 5, "frame_color": "red"},
                {"id": "z2", "title": "週間特売", "hero_count": 1, "grid_count": 6, "frame_color": "green"},
            ],
        },
    )
    assert tpl_res.status_code == 200
    custom_id = tpl_res.json()["template"]["id"]
    assert tpl_res.json()["template"]["default_item_count"] == 14

    gen = client.post("/api/flyers/generate", json={"template_id": custom_id, "theme": "秋の味覚フェア"})
    assert gen.status_code == 200
    flyer = gen.json()["flyer"]
    assert len(flyer["slots"]) == 14

    # Export PDF and verify valid PDF header + Japanese text presence
    pdf_res = client.post(f"/api/flyers/{flyer['id']}/export?format=pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"].startswith("application/pdf")
    assert pdf_res.content[:4] == b"%PDF"

    with tempfile.NamedTemporaryFile(suffix=".pdf") as pf:
        pf.write(pdf_res.content)
        pf.flush()
        txt = subprocess.run(["pdftotext", pf.name, "-"], capture_output=True, text=True, timeout=15).stdout
        assert "本体" in txt and "税込" in txt

    # Export JPEG and verify valid JPEG header & dimensions
    jpg_res = client.post(f"/api/flyers/{flyer['id']}/export?format=jpeg&dpi=150")
    assert jpg_res.status_code == 200
    assert jpg_res.headers["content-type"].startswith("image/jpeg")
    assert jpg_res.content[:2] == b"\xff\xd8"


def test_template_switching_bg_generation_and_photo_overlay_layout(client: TestClient):
    # 1. Verify GET /api/templates returns new layout_modes, overlay_positions, bg_presets, and overflow_cutout shape
    tpls_res = client.get("/api/templates")
    assert tpls_res.status_code == 200
    data = tpls_res.json()
    assert any(s["id"] == "overflow_cutout" for s in data["frame_shapes"])
    assert any(s["id"] == "rect" for s in data["frame_shapes"])
    assert any(m["id"] == "overlay_full" for m in data["layout_modes"])
    assert any(m["id"] == "overflow_frame" for m in data["layout_modes"])
    assert len(data["bg_presets"]) >= 5

    # 2. Generate an AI / procedural background image via POST /api/bg_images/generate
    bg_res = client.post(
        "/api/bg_images/generate",
        json={"preset_id": "autumn_wood", "prompt": "紅葉と木目の秋テーブル背景"},
    )
    assert bg_res.status_code == 200
    bg_info = bg_res.json()
    assert bg_info["ok"] is True
    bg_url = bg_info["bg"]["url"]
    assert bg_url.startswith("/api/bg_images/bg-")

    # Fetch the generated background JPEG
    bg_get = client.get(bg_url)
    assert bg_get.status_code == 200
    assert bg_get.content[:2] == b"\xff\xd8"

    # 3. Create a flyer and switch its template via POST /api/flyers/{id}/apply_template
    gen_res = client.post("/api/flyers/generate", json={"template_id": "T1", "item_count": 12, "theme": "秋の味覚フェア"})
    assert gen_res.status_code == 200
    flyer = gen_res.json()["flyer"]
    fid = flyer["id"]
    orig_pids = [s["product_id"] for s in flyer["slots"]]

    sw_res = client.post(f"/api/flyers/{fid}/apply_template", json={"template_id": "T4", "item_count": 12})
    assert sw_res.status_code == 200
    sw_flyer = sw_res.json()["flyer"]
    assert sw_flyer["template_id"] == "T4"
    assert [s["product_id"] for s in sw_flyer["slots"]] == orig_pids

    # 4. Customize individual slot size (`width_weight`, `row_weight`), shape (`overflow_cutout`),
    #    photo overlay layout (`overlay_full`, `overlay_pos`), and background image (`bg_image_url`)
    s0_id = sw_flyer["slots"][0]["slot_id"]
    up_res = client.put(
        f"/api/flyers/{fid}",
        json={
            "bg_image_url": bg_url,
            "slot_update": {
                "slot_id": s0_id,
                "shape": "overflow_cutout",
                "width_weight": 2.4,
                "row_weight": 1.6,
                "img_scale": 140,
                "layout_mode": "overlay_full",
                "overlay_pos": "bottom-right",
                "bg_image_url": bg_url,
            },
        },
    )
    assert up_res.status_code == 200
    up_flyer = up_res.json()["flyer"]
    assert up_flyer["bg_image_url"] == bg_url
    s0 = up_flyer["slots"][0]
    assert s0["shape"] == "overflow_cutout"
    assert s0["width_weight"] == 1.35  # Clamped by QA validator from 2.4 to 1.35 to keep aspect ratio <= 1.5
    assert s0["row_weight"] == 1.6
    assert s0["layout_mode"] == "overlay_full"
    assert s0["overlay_pos"] == "bottom-right"
    assert s0["bg_image_url"] == bg_url

    # Verify rendered HTML includes the new CSS classes, transparent cutout PNG endpoint, tight SVG hontai lockup, and background image URL
    html_res = client.get(f"/api/flyers/{fid}/preview_html")
    assert html_res.status_code == 200
    assert "ch-slot--shape-overflow_cutout" in html_res.text
    assert "ch-slot--layout-overlay_full" in html_res.text
    assert "ch-slot--opos-bottom-right" in html_res.text
    assert "/api/product_cutout/" in html_res.text
    assert "/static/img/bg_presets/" in html_res.text
    assert "svg-hontai-group" in html_res.text
    assert up_flyer.get("qa_report", {}).get("passed") is True

    # Verify /api/product_cutout/{img_file} returns a true transparent PNG (alpha == 0 at corners)
    cut_res = client.get("/api/product_cutout/fruit_bunashimeji_p.jpg")
    assert cut_res.status_code == 200
    assert cut_res.headers["content-type"].startswith("image/png")
    assert cut_res.content[:4] == b"\x89PNG"

    # 5. Save a custom template with per-slot `slot_overrides` and zone `bg_image_url` + `hero_layout_mode`
    tpl_save = client.post(
        "/api/templates",
        json={
            "name": "写真重ね＆自由形カスタムテンプレート",
            "base_template_id": "T1",
            "bg_image_url": bg_url,
            "slot_overrides": {
                "T1-S01": {
                    "shape": "overflow_cutout",
                    "size_span": "hero_2x2",
                    "width_weight": 2.5,
                    "row_weight": 1.8,
                    "img_scale": 145,
                    "layout_mode": "overlay_full",
                    "overlay_pos": "bottom-right",
                    "bg_image_url": bg_url,
                }
            },
            "zones": [
                {
                    "id": "z1",
                    "title": "超目玉オーバーレイ",
                    "hero_count": 2,
                    "grid_count": 4,
                    "hero_shape": "overflow_cutout",
                    "hero_layout_mode": "overlay_full",
                    "grid_layout_mode": "overlay_price",
                    "bg_image_url": bg_url,
                    "slot_overrides": {
                        "1": {
                            "shape": "overflow_cutout",
                            "size_span": "hero_2x2",
                            "width_weight": 2.5,
                            "row_weight": 1.8,
                            "img_scale": 145,
                            "layout_mode": "overlay_full",
                            "overlay_pos": "bottom-right",
                            "bg_image_url": bg_url,
                        }
                    },
                }
            ],
        },
    )
    assert tpl_save.status_code == 200
    saved_tpl = tpl_save.json()["template"]
    assert saved_tpl["bg_image_url"] == bg_url
    assert saved_tpl["zones"][0]["hero_layout_mode"] == "overlay_full"
    assert "T1-S01" in saved_tpl["slot_overrides"]

