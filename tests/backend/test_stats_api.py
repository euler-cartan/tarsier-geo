"""Covers the Statistics tab's API routes (PRD §7.2)."""

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
        json={"name": "Sample files", "type": "files", "config": {"folder": "tests/datasets/files_sample"}},
    )
    return response.json()["id"]


def test_stats_before_scan_is_a_clean_404(client, connection_id):
    response = client.get(
        f"/api/connections/{connection_id}/item/stats", params={"schema": "", "name": "inspection_log.csv"}
    )
    assert response.status_code == 404


def test_scan_then_get_stats(client, connection_id):
    scan_response = client.post(
        f"/api/connections/{connection_id}/item/stats/scan",
        params={"schema": "", "name": "inspection_log.csv"},
    )
    assert scan_response.status_code == 202

    stats_response = client.get(
        f"/api/connections/{connection_id}/item/stats", params={"schema": "", "name": "inspection_log.csv"}
    )
    assert stats_response.status_code == 200
    body = stats_response.json()
    assert body["sampled_row_count"] == 1
    column_names = {c["name"] for c in body["columns"]}
    assert "inspector" in column_names


def test_scan_stats_for_nonexistent_item_fails_cleanly(client, connection_id):
    response = client.post(
        f"/api/connections/{connection_id}/item/stats/scan",
        params={"schema": "", "name": "does_not_exist.csv"},
    )
    assert response.status_code == 400


def test_scan_stats_for_raster_fails_cleanly(client, connection_id):
    response = client.post(
        f"/api/connections/{connection_id}/item/stats/scan",
        params={"schema": "", "name": "sample_elevation.tif"},
    )
    assert response.status_code == 400
    assert "raster" in response.json()["detail"].lower()
