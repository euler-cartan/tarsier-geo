from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from tarsier.api.app import create_app
from tarsier.storage import change_log


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


def test_template_and_scratch_and_test_run(client, connection_id):
    catalog = client.get(f"/api/connections/{connection_id}/automations/catalog").json()
    assert {t["id"] for t in catalog["templates"]} >= {"mass_delete", "evening_summary", "quality_then_notify"}
    assert {t["id"] for t in catalog["triggers"]} == {
        "any_change",
        "schedule",
        "threshold",
        "specific_user",
        "quality_failure",
        "new_feature", "schema_change", "layer_presence", "freshness",
    }
    created = client.post(
        f"/api/connections/{connection_id}/automations",
        json={"template_id": "mass_delete"},
    )
    assert created.status_code == 201
    auto_id = created.json()["id"]
    change_log.insert_events(
        connection_id,
        [
            {
                "occurred_at": datetime.now(timezone.utc),
                "db_user": "alice",
                "action": "delete",
                "schema": "",
                "name": "sample_inventory.csv",
                "txid": "99",
                "source": "test",
            }
            for _ in range(50)
        ],
        {("", "sample_inventory.csv"): 6},
    )
    test = client.post(f"/api/connections/{connection_id}/automations/{auto_id}/test-run")
    assert test.status_code == 200
    body = test.json()
    assert body["dry_run"] is True
    kinds = [s["kind"] for s in body["trace"] if s.get("ok")]
    assert "any_change" in kinds
    assert "log" in kinds

    blank = client.post(
        f"/api/connections/{connection_id}/automations",
        json={
            "title": "User filter",
            "graph": {
                "nodes": [
                    {"id": "t1", "role": "trigger", "kind": "specific_user", "config": {"user": "alice"}},
                    {"id": "c1", "role": "condition", "kind": "layer_eq", "config": {"layer": "sample_inventory.csv"}},
                    {"id": "a1", "role": "action", "kind": "log", "config": {}},
                ],
                "edges": [{"from": "t1", "to": "c1"}, {"from": "c1", "to": "a1"}],
            },
        },
    )
    assert blank.status_code == 201
    change_log.insert_events(connection_id, [{
        "occurred_at": datetime.now(timezone.utc), "db_user": "alice",
        "action": "update", "schema": "", "name": "sample_inventory.csv", "source": "test",
    }], {})
    second = client.post(
        f"/api/connections/{connection_id}/automations/{blank.json()['id']}/test-run"
    )
    assert second.json()["ok"] is True

    evening = client.post(
        f"/api/connections/{connection_id}/automations",
        json={"template_id": "evening_summary", "title": "18:00 summary"},
    )
    morning = client.post(
        f"/api/connections/{connection_id}/automations",
        json={
            "title": "Every 15 minutes",
            "graph": {
                "nodes": [
                    {"id": "t1", "role": "trigger", "kind": "schedule", "config": {"every_minutes": 15}},
                    {"id": "a1", "role": "action", "kind": "log", "config": {}},
                ],
                "edges": [{"from": "t1", "to": "a1"}],
            },
        },
    )
    listed = client.get(f"/api/connections/{connection_id}/automations").json()["automations"]
    hours = [a["title"] for a in listed]
    assert evening.status_code == 201
    assert morning.status_code == 201
    assert "18:00 summary" in hours
    assert "Every 15 minutes" in hours


def test_branches_and_positions_persist_and_preview_does_not_deliver(client, connection_id, monkeypatch):
    from tarsier.notifications import delivery
    calls = []
    monkeypatch.setattr(delivery, "send_webhook", lambda *args, **kwargs: calls.append(args))
    url = f"/api/connections/{connection_id}/automations"
    graph = {"nodes": [
        {"id": "t", "kind": "schedule", "config": {"every_minutes": 1}, "position": {"x": 48, "y": 96}},
        {"id": "c", "kind": "user_eq", "config": {"user": "nobody"}},
        {"id": "a", "kind": "webhook", "config": {"webhook_url": "https://example.org/notify"}},
    ], "edges": [{"from": "t", "to": "c"}, {"from": "c", "to": "a", "branch": "false"}]}
    created = client.post(url, json={"title": "False branch", "graph": graph, "paused": True})
    assert created.status_code == 201
    auto_id = created.json()["id"]
    graph["nodes"][0]["position"] = {"x": 144, "y": 192}
    updated = client.put(f"{url}/{auto_id}", json={"title": "Moved", "graph": graph, "paused": True})
    assert updated.status_code == 200
    stored = next(a for a in client.get(url).json()["automations"] if a["id"] == auto_id)
    assert stored["graph"]["nodes"][0]["position"] == {"x": 144, "y": 192}
    assert stored["graph"]["nodes"][0]["role"] == "trigger"
    assert stored["graph"]["edges"][1]["branch"] == "false"
    result = client.post(f"{url}/preview", json={"graph": graph}).json()
    assert result["dry_run"] is True
    assert [step["node_id"] for step in result["trace"]] == ["t", "c", "a"]
    assert calls == []
    graph["edges"].append({"from": "a", "to": "c"})
    assert client.put(f"{url}/{auto_id}", json={"graph": graph}).status_code == 400
