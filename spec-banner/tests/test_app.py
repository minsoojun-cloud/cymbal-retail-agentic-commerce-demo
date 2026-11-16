"""Comprehensive backend tests for `cymbal-spec-banner`.

Tests:
1. All 6 categories' schema & seeded products (`>= 18` products).
2. Reading from `mst_product` + `mst_product_kinohyo` and updating specs via `PUT /api/products/{identifier}/specs`.
3. Creating a new product in `mst_product` + `mst_product_kinohyo` (`POST /api/products`) and syncing (`POST /api/sync-master`).
4. Importing actual `*機能表入力シート.xlsx` files via `POST /api/import-excel` across multiple categories.
5. Exporting JPEG (`POST /api/export/jpeg`) and PDF (`POST /api/export/pdf`) and verifying valid `%PDF-` / JPEG headers (`\xff\xd8\xff`) and non-zero sizes.
6. Sending an email with JPEG & PDF attachments (`POST /api/email/send`) and verifying `banner_mail_log` via `GET /api/email/logs`.
"""

from __future__ import annotations

import os
import pathlib

from fastapi.testclient import TestClient
import pytest

from edion_banner.main import get_app

SAMPLES_DIR = pathlib.Path(
    os.environ.get("BANNER_SAMPLES_DIR", "/tmp/drive_samples")
)


@pytest.fixture()
def client(tmp_path: pathlib.Path) -> TestClient:
    os.environ["DISABLE_LIVE_EMAIL"] = "1"
    os.environ["LOCAL_STORAGE_DIR"] = str(tmp_path / "banners")
    db_path = tmp_path / "test_edion_banner.db"
    app = get_app(f"sqlite:///{db_path}")
    return TestClient(app)


def test_health_and_seeded_categories(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["kinohyo_product_count"] >= 18
    assert data["master_product_count"] >= 18

    r_cat = client.get("/api/categories")
    assert r_cat.status_code == 200
    cats = r_cat.json()["categories"]
    cat_ids = {c["id"] for c in cats}
    assert cat_ids == {"tv", "pc", "wine_cellar", "cooler_warmer", "freezer", "refrigerator"}
    for c in cats:
        assert c["count"] >= 2
        assert len(c["fields"]) >= 10


def test_list_and_lookup_products_and_update_specs(client: TestClient) -> None:
    r = client.get("/api/products")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 18

    # Lookup by model number (TV K50XR70M2)
    r_tv = client.get("/api/products/K50XR70M2")
    assert r_tv.status_code == 200
    tv = r_tv.json()
    assert tv["category"] == "tv"
    assert tv["specs"]["type"] == "MiniLED"
    assert tv["linked_master"] is True
    orig_price = tv["edion_price"]

    # Update TV specs by 13-digit JAN code (4548736167186) and verify master is strictly read-only
    r_upd = client.put(
        "/api/products/4548736167186/specs",
        json={
            "category": "tv",
            "specs": {"type": "有機EL", "screen_size": 65},
            "edion_price": 999999,
        },
    )
    assert r_upd.status_code == 200
    updated = r_upd.json()
    assert updated["specs"]["type"] == "有機EL"
    assert updated["specs"]["screen_size"] == 65
    # Master `mst_product` is strictly READ-ONLY, so `edion_price` remains untouched!
    assert updated["edion_price"] == orig_price
    assert updated["saved_storage"]["master_readonly"] is True


def test_create_product_and_sync_master(client: TestClient) -> None:
    r = client.post(
        "/api/products",
        json={
            "category": "refrigerator",
            "jan_code": "4901234567890",
            "search_model_no": "NR-F60WX1",
            "maker_name": "パナソニック",
            "product_name": "6ドア冷蔵庫 600L",
            "edion_price": 328000,
            "specs": {"capacity_l": 600, "door_count": 6, "door_layout": "扉5枚A"},
        },
    )
    assert r.status_code == 200
    created = r.json()
    assert created["jan_code"] == "4901234567890"
    assert created["linked_master"] is True
    assert created["specs"]["capacity_l"] == 600

    r_sync = client.post("/api/sync-master")
    assert r_sync.status_code == 200
    assert r_sync.json()["status"] == "ok"


@pytest.mark.parametrize(
    ("excel_name", "expected_category"),
    [
        ("【テレビ】機能表入力シート.xlsx", "tv"),
        ("【パソコン】機能表入力シート_0224Ver.xlsx", "pc"),
        ("【メーカー様名】ワインセラー機能表入力シート.xlsx", "wine_cellar"),
        ("【メーカー様名】冷温庫機能表入力シート.xlsx", "cooler_warmer"),
        ("【メーカー様名】冷凍庫_機能表入力シート.xlsx", "freezer"),
        ("【メーカー様名】冷蔵庫_機能表入力シート_260910更新.xlsx", "refrigerator"),
    ],
)
def test_import_excel_all_6_categories(
    client: TestClient, excel_name: str, expected_category: str
) -> None:
    excel_path = SAMPLES_DIR / excel_name
    if not excel_path.exists():
        pytest.skip(f"Sample Excel not present: {excel_path}")
    with excel_path.open("rb") as fh:
        r = client.post(
            "/api/import-excel",
            files={"file": (excel_name, fh.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["detected_category"] == expected_category
    assert data["imported_count"] >= 1
    if expected_category == "pc":
        # PC sheet has FMV + 14 Microsoft Surface rows = 15 rows
        assert data["imported_count"] >= 15


def test_export_jpeg_and_pdf(client: TestClient) -> None:
    # 1. Export JPEG for Refrigerator GRA600XFS
    r_jpg = client.post(
        "/api/export/jpeg",
        json={"product_id": "GRA600XFS", "category": "refrigerator"},
    )
    assert r_jpg.status_code == 200
    assert r_jpg.headers["content-type"] == "image/jpeg"
    assert r_jpg.content[:3] == b"\xff\xd8\xff"
    assert len(r_jpg.content) > 10000

    # 2. Export PDF for PC FMVU77K3B5
    r_pdf = client.post(
        "/api/export/pdf",
        json={"product_id": "FMVU77K3B5", "category": "pc"},
    )
    assert r_pdf.status_code == 200
    assert r_pdf.headers["content-type"] == "application/pdf"
    assert r_pdf.content.startswith(b"%PDF-")
    assert len(r_pdf.content) > 10000


def test_send_email_with_attachments_and_logs(client: TestClient) -> None:
    r = client.post(
        "/api/email/send",
        json={
            "to_email": "vmd-buyer@cymbal-retail.example.com",
            "cc_email": "md-team@cymbal-retail.example.com",
            "subject": "【Cymbal VMD】SONY BRAVIA K50XR70M2 機能表バナー送付",
            "body": "機能表バナーのJPEGおよびPDFデータを添付いたします。",
            "attachment_format": "both",
            "search_model_no": "K50XR70M2",
            "category": "tv",
        },
    )
    assert r.status_code == 200
    res = r.json()
    assert res["status"] in ("SENT", "QUEUED")
    assert res["jpeg_size_bytes"] > 5000
    assert res["pdf_size_bytes"] > 5000
    assert res["jpeg_download_url"].startswith("/api/files/banners/")
    assert res["pdf_download_url"].startswith("/api/files/banners/")

    # Verify stored files are downloadable
    r_dl_jpg = client.get(res["jpeg_download_url"])
    assert r_dl_jpg.status_code == 200
    assert r_dl_jpg.content[:3] == b"\xff\xd8\xff"

    r_dl_pdf = client.get(res["pdf_download_url"])
    assert r_dl_pdf.status_code == 200
    assert r_dl_pdf.content.startswith(b"%PDF-")

    # Verify email logs endpoint
    r_logs = client.get("/api/email/logs")
    assert r_logs.status_code == 200
    logs = r_logs.json()["items"]
    assert len(logs) >= 1
    assert logs[0]["to_email"] == "vmd-buyer@cymbal-retail.example.com"


def test_dynamic_templates_and_vision_layout_analyzer(client: TestClient) -> None:
    # 1. List presets across all 6 categories
    r_list = client.get("/api/templates")
    assert r_list.status_code == 200
    items = r_list.json()["items"]
    assert len(items) >= 6
    categories_found = {t["category"] for t in items}
    assert categories_found == {"tv", "pc", "wine_cellar", "cooler_warmer", "freezer", "refrigerator"}

    # 2. Customize TV template field mapping & box geometry and save
    tv_preset = next(t for t in items if t["category"] == "tv")
    custom_schema = dict(tv_preset)
    custom_schema["header"] = dict(tv_preset["header"])
    # Swap top_right_1 and top_right_2 or bind custom field
    custom_schema["header"]["top_right_1_field_key"] = "brand"
    custom_schema["header"]["top_right_2_field_key"] = "maker"

    r_save = client.post(
        "/api/templates",
        json={
            "name": "【テスト】テレビ項目入替カスタムレイアウト",
            "category": "tv",
            "orientation": "landscape",
            "status": "published",
            "is_category_default": True,
            "assigned_models": ["K50XR70M2"],
            "schema_json": custom_schema,
        },
    )
    assert r_save.status_code == 200
    saved = r_save.json()
    assert saved["template_id"].startswith("custom_tv_")
    assert saved["header"]["top_right_1_field_key"] == "brand"
    assert saved["status"] == "published"
    assert saved["is_category_default"] is True
    assert "K50XR70M2" in saved["assigned_models"]
    assert saved["saved_storage"]["master_readonly"] is True

    # Verify the assigned product K50XR70M2 now has template_variant linked to the published template
    r_prod = client.get("/api/products/K50XR70M2")
    assert r_prod.status_code == 200
    assert r_prod.json()["template_variant"] == saved["template_id"]

    # 3. Upload an image to `/api/templates/analyze-image` and verify automatic layout generation
    r_jpg = client.post(
        "/api/export/jpeg",
        json={"product_id": "K50XR70M2", "category": "tv"},
    )
    assert r_jpg.status_code == 200
    r_vision = client.post(
        "/api/templates/analyze-image?category=tv",
        files={"file": ("sample_layout.jpg", r_jpg.content, "image/jpeg")},
    )
    assert r_vision.status_code == 200
    vdata = r_vision.json()
    assert "template" in vdata
    assert vdata["template"]["category"] == "tv"
    assert len(vdata["template"]["boxes"]) >= 5
    assert vdata["template"]["source_image_data_url"].startswith("data:image/jpeg;base64,")
