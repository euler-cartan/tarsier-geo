import pytest
from fastapi.testclient import TestClient

from tarsier.api.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    return TestClient(create_app())


@pytest.fixture
def connection_id(client):
    response = client.post(
        "/api/connections",
        json={"name": "Files", "type": "files", "config": {"folder": "tests/datasets/files_sample"}},
    )
    return response.json()["id"]


def test_create_edit_pause_delete_every_kind(client, connection_id):
    kinds = client.get(f"/api/connections/{connection_id}/alerts/kinds").json()
    assert {k["id"] for k in kinds} >= {
        "mass_change",
        "row_count_drop",
        "schema_change",
        "freshness",
        "quality_score_drop",
        "specific_user",
        "layer_presence",
        "size_spike",
        "banned_value",
    }
    created_ids = []
    for kind in kinds:
        body = {"kind": kind["id"], "title": kind["label"], "target_name": "", "config": {"notify": "log"}}
        if kind["id"] == "specific_user":
            body["config"]["user"] = "alice"
        if kind["id"] == "banned_value":
            body["config"].update({"field": "diameter_mm", "operator": "lt", "value": "0"})
        response = client.post(f"/api/connections/{connection_id}/alerts", json=body)
        assert response.status_code == 200, response.text
        created_ids.append(response.json()["id"])
    rule_id = created_ids[0]
    paused = client.put(
        f"/api/connections/{connection_id}/alerts/{rule_id}",
        json={"kind": "mass_change", "title": "Mass", "paused": True, "config": {"notify": "log"}},
    )
    assert paused.json()["paused"] is True
    listed = client.get(f"/api/connections/{connection_id}/alerts").json()
    assert len(listed["rules"]) == len(kinds)
    deleted = client.delete(f"/api/connections/{connection_id}/alerts/{rule_id}")
    assert deleted.status_code == 200


def test_evaluate_fires_banned_value_on_sample(client, connection_id):
    client.post(
        f"/api/connections/{connection_id}/alerts",
        json={
            "kind": "banned_value",
            "title": "Missing stock quantity",
            "target_name": "sample_inventory.csv",
            "config": {"field": "stock_qty", "operator": "is_null", "notify": "log"},
        },
    )
    response = client.post(f"/api/connections/{connection_id}/alerts/evaluate")
    assert response.status_code == 202
    fires = client.get(f"/api/connections/{connection_id}/alerts").json()["fires"]
    assert any("Banned value" in f["message"] for f in fires)


def test_evaluating_after_a_scan_saves_the_snapshot(tmp_path, monkeypatch):
    """Regression: items carry a datetime scanned_at, which used to make the snapshot unsaveable."""
    from tarsier.storage import alerts as alert_store

    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    client = TestClient(create_app())
    connection_id = client.post(
        "/api/connections",
        json={"name": "Files", "type": "files", "config": {"folder": "tests/datasets/files_sample"}},
    ).json()["id"]
    client.post(f"/api/connections/{connection_id}/scan")
    assert client.post(f"/api/connections/{connection_id}/alerts/evaluate").status_code == 202
    snapshot = alert_store.get_snapshot(connection_id)
    assert snapshot is not None and snapshot["items"]
