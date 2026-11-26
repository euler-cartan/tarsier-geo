"""Covers the Overview/Detail-page API routes (PRD §7.1, §7.9)."""

import pytest
from fastapi.testclient import TestClient

from tarsier.api.app import create_app
from tarsier.storage import connections as storage


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    return TestClient(create_app())


@pytest.fixture
def connection_id(client):
    response = client.post(
        "/api/connections",
        json={"name": "Sample files", "type": "files", "config": {"folder": "tests/datasets/files_sample"}},
    )
    return response.json()["id"]


def test_overview_before_any_scan_reports_not_yet_scanned(client, connection_id):
    response = client.get(f"/api/connections/{connection_id}/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["ever_scanned"] is False
    assert body["total_layers"] == 0
    assert body["relationship_count"] == 0


def test_scan_then_overview_reports_items(client, connection_id):
    scan_response = client.post(f"/api/connections/{connection_id}/scan")
    assert scan_response.status_code == 202

    overview_response = client.get(f"/api/connections/{connection_id}/overview")
    body = overview_response.json()
    assert body["ever_scanned"] is True
    assert body["total_layers"] == 6


def test_item_detail_after_scan(client, connection_id):
    client.post(f"/api/connections/{connection_id}/scan")

    response = client.get(f"/api/connections/{connection_id}/item", params={"schema": "", "name": "water_mains"})
    assert response.status_code == 200
    assert response.json()["row_count"] == 2


def test_item_detail_before_scan_is_a_clean_404(client, connection_id):
    response = client.get(f"/api/connections/{connection_id}/item", params={"name": "water_mains"})
    assert response.status_code == 404


def test_overview_for_unknown_connection_is_404(client):
    response = client.get("/api/connections/does-not-exist/overview")
    assert response.status_code == 404


def test_scan_for_unreachable_connection_fails_cleanly(client):
    bad_id = storage.create_connection(
        name="Bad", type="files", config={"folder": "tests/datasets/does_not_exist"}
    ).id
    response = client.post(f"/api/connections/{bad_id}/scan")
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]
