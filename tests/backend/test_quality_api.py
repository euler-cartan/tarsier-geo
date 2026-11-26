"""Quality tab API — independent per-check scan (TRS-035, TRS-036, TRS-039)."""

import pytest
from fastapi.testclient import TestClient

from tarsier.api.app import create_app

PLANTED = "tests/datasets/quality_planted"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    return TestClient(create_app())


@pytest.fixture
def connection_id(client):
    response = client.post(
        "/api/connections",
        json={"name": "Quality planted", "type": "files", "config": {"folder": PLANTED}},
    )
    return response.json()["id"]


def _scan(client, connection_id, name, check, **extra):
    return client.post(
        f"/api/connections/{connection_id}/item/quality/scan",
        params={"schema": "", "name": name, "check": check, **extra},
    )


def test_never_run_is_distinct_from_passing(client, connection_id):
    response = client.get(
        f"/api/connections/{connection_id}/item/quality",
        params={"schema": "", "name": "parcels", "kind": "vector"},
    )
    assert response.status_code == 200
    validity = response.json()["checks"]["validity"]
    assert validity["status"] == "never_run"
    assert validity["fail_count"] == 0


def test_each_check_can_finish_on_its_own(client, connection_id):
    scan = _scan(client, connection_id, "parcels", "validity")
    assert scan.status_code == 202
    assert scan.json()["check"]["status"] == "danger"
    body = client.get(
        f"/api/connections/{connection_id}/item/quality",
        params={"schema": "", "name": "parcels", "kind": "vector"},
    ).json()
    assert body["checks"]["validity"]["status"] == "danger"
    assert body["checks"]["overlaps"]["status"] == "never_run"


def test_planted_topology_and_projection(client, connection_id):
    assert _scan(client, connection_id, "parcels", "overlaps").json()["check"]["fail_count"] >= 2
    assert _scan(client, connection_id, "parcels", "slivers").json()["check"]["fail_count"] == 1
    assert _scan(client, connection_id, "parcels", "gaps").json()["check"]["fail_count"] == 1
    assert _scan(client, connection_id, "parcels", "completeness").json()["check"]["failing_rows"][0]["objectid"] == 3
    dangles = _scan(client, connection_id, "roads", "dangles").json()["check"]
    assert dangles["fail_count"] == 1
    odd = _scan(client, connection_id, "odd_crs", "projection").json()["check"]
    assert odd["status"] == "danger"


def test_boundary_picker_and_outside_feature(client, connection_id):
    put = client.put(
        f"/api/connections/{connection_id}/item/quality/settings",
        json={"schema": "", "name": "parcels", "boundary_schema": "", "boundary_name": "city_limit"},
    )
    assert put.status_code == 200
    result = _scan(client, connection_id, "parcels", "boundary").json()["check"]
    assert result["fail_count"] == 1
    assert result["failing_rows"][0]["objectid"] == 8


def test_custom_rules_create_edit_delete(client, connection_id):
    created = client.post(
        f"/api/connections/{connection_id}/item/quality/rules",
        json={"schema": "", "name": "parcels", "kind": "attribute", "field": "diameter", "operator": "gt", "value": "0"},
    )
    assert created.status_code == 200
    rule_id = created.json()["id"]
    flagged = _scan(client, connection_id, "parcels", "custom_rules").json()["check"]
    assert flagged["fail_count"] == 1
    edited = client.put(
        f"/api/connections/{connection_id}/item/quality/rules/{rule_id}",
        json={"schema": "", "name": "parcels", "kind": "geometry_type", "field": "category", "operator": "eq", "value": "Road", "geometry_type": "LineString"},
    )
    assert edited.status_code == 200
    geo = _scan(client, connection_id, "parcels", "custom_rules").json()["check"]
    assert geo["fail_count"] == 1
    assert geo["failing_rows"][0]["category"] == "Road"
    deleted = client.delete(f"/api/connections/{connection_id}/item/quality/rules/{rule_id}")
    assert deleted.status_code == 200


def test_tabular_completeness(client, connection_id):
    result = _scan(client, connection_id, "missing_ids.csv", "completeness").json()["check"]
    assert result["failing_rows"][0]["id"] == 3
    na = _scan(client, connection_id, "missing_ids.csv", "validity")
    assert na.status_code == 400
