import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SN = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    state = tmp_path_factory.mktemp("sn_admin_state")
    keys = ["DATA_MODE", "SEARCH_MODE", "APP_MODE", "SN_STATE_DIR", "RETAIL_LOCAL_INVENTORY", "STAFF_PREWARM"]
    old = {k: os.environ.get(k) for k in keys}
    os.environ.update({
        "DATA_MODE": "local",
        "SEARCH_MODE": "local",
        "APP_MODE": "staff",
        "SN_STATE_DIR": str(state),
        "RETAIL_LOCAL_INVENTORY": "0",
        "STAFF_PREWARM": "0"
    })
    if str(SN) not in sys.path:
        sys.path.insert(0, str(SN))
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]
    yield state
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]


@pytest.fixture(scope="module")
def client(env):
    main = importlib.import_module("app.main")
    return TestClient(main.app)


def test_admin_role_forbidden_without_manager_role(client):
    res = client.get("/api/admin/stores/S01/editor")
    assert res.status_code == 403
    assert "店長権限" in res.json()["detail"]


def test_admin_role_allowed_with_cookie(client):
    client.cookies.set("sn_role", "manager")
    res = client.get("/api/admin/stores/S01/editor")
    assert res.status_code == 200
    data = res.json()
    assert data["store"]["store_id"] == "S01"
    assert "current_version" in data
    assert "layout" in data
    assert "versions" in data


def test_draft_lifecycle_and_preview(client):
    client.cookies.set("sn_role", "manager")
    # Get current editor state
    res = client.get("/api/admin/stores/S01/editor")
    assert res.status_code == 200
    lay = res.json()["layout"]

    # Save a draft
    draft = dict(lay)
    draft["fixtures"] = list(lay.get("fixtures", []))
    res = client.put("/api/admin/stores/S01/draft", json={"draft": draft, "editor_name": "テスト店長"})
    assert res.status_code == 200

    # Preview draft
    res = client.post("/api/admin/stores/S01/draft/preview", json={"draft": draft})
    assert res.status_code == 200
    p_data = res.json()
    assert p_data["valid"] is True
    assert "diff" in p_data
    assert "impact" in p_data

    # Delete draft
    res = client.delete("/api/admin/stores/S01/draft")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_staff_unassigned_endpoint(client):
    res = client.get("/api/staff/unassigned?store_id=S01")
    assert res.status_code == 200
    data = res.json()
    assert data["store_id"] == "S01"
    assert "count" in data
    assert isinstance(data["items"], list)
