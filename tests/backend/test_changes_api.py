from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from tarsier.api.app import create_app
from tarsier.storage import change_log
from tarsier.storage import connections as storage


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    return TestClient(create_app())


@pytest.fixture
def files_id(client):
    response = client.post(
        "/api/connections",
        json={"name": "Files", "type": "files", "config": {"folder": "tests/datasets/files_sample"}},
    )
    return response.json()["id"]


def test_files_changes_are_not_available(client, files_id):
    response = client.get(f"/api/connections/{files_id}/changes")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "file" in body["reason"].lower()
    assert body["events"] == []


def test_mass_flag_compare_report_and_feed_filter(client, tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    # This unit fixture has no database; live tracking-health behavior has its own test.
    monkeypatch.setattr("tarsier.changes.sync.tracking_health", lambda _: {"status": "unavailable", "possible_gaps": True})
    saved = storage.create_connection(name="PG", type="postgis", config={"host": "x", "database": "t"})
    change_log.set_mode(saved.id, "triggers")
    now = datetime.now(timezone.utc)
    rows = [
        {
            "occurred_at": now,
            "db_user": "alice",
            "action": "delete",
            "schema": "public",
            "name": "water_mains",
            "feature_id": str(i),
            "before": {"id": i, "material": "PVC"},
            "after": None,
            "txid": 99,
            "source": "trigger",
            "source_log_id": i,
        }
        for i in range(50)
    ]
    rows.append(
        {
            "occurred_at": now,
            "db_user": "alice",
            "action": "update",
            "schema": "public",
            "name": "water_mains",
            "feature_id": "1",
            "before": {"material": "PVC"},
            "after": {"material": "HDPE"},
            "txid": 100,
            "source": "trigger",
            "source_log_id": 51,
        }
    )
    change_log.insert_events(saved.id, rows, {("public", "water_mains"): 200})

    app_client = TestClient(create_app())
    feed = app_client.get(f"/api/connections/{saved.id}/changes", params={"action": "delete"})
    assert feed.status_code == 200
    body = feed.json()
    assert body["available"] is True
    assert body["events"][0]["is_mass"] is True
    assert all(e["action"] == "delete" for e in body["events"])
    assert any(bar["is_spike"] for bar in body["volume"] if bar["count"])

    feature = app_client.get(
        f"/api/connections/{saved.id}/changes", params={"name": "water_mains", "feature_id": "1", "action": "update"}
    ).json()
    assert len(feature["events"]) == 1
    assert feature["events"][0]["changed_fields"] == ["material"]

    report = app_client.post(f"/api/connections/{saved.id}/changes/report", json={"interval": "daily"})
    assert report.status_code == 200
    assert report.json()["total"] == 51
    assert report.json()["mass_batches"] == 1
