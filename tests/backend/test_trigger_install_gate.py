"""Only the explicit history-log endpoint can start source DDL."""

from fastapi.testclient import TestClient

from tarsier.api import connections as connection_api
from tarsier.api import overview as overview_api
from tarsier.api.app import create_app
from tarsier.changes import scheduler, sync


class _FakePostgis:
    @staticmethod
    def build_config(config, password):
        return config

    @staticmethod
    def test_connection(config):
        return None


def test_connection_startup_scan_and_scheduler_never_install_triggers(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    monkeypatch.setenv("TARSIER_SCHEDULER", "0")
    monkeypatch.setattr(connection_api, "get_connection_type_info", lambda kind: object())
    monkeypatch.setattr(connection_api, "get_connector", lambda kind: _FakePostgis())
    monkeypatch.setattr(overview_api.overview_module, "scan_connection", lambda connection_id: None)
    monkeypatch.setattr(sync, "sync_connection", lambda connection_id: None)
    monkeypatch.setattr(sync, "generate_due_report", lambda connection_id: None)
    installs = []
    monkeypatch.setattr(sync, "enable_triggers", installs.append)

    with TestClient(create_app()) as client:
        body = {"name": "Test source", "type": "postgis", "config": {}}
        created = client.post("/api/connections", json=body)
        assert created.status_code == 201
        connection_id = created.json()["id"]
        assert client.get("/api/health").status_code == 200
        assert client.post(f"/api/connections/{connection_id}/scan").status_code == 202
        scheduler._tick()
        assert installs == []

        legacy = client.post("/api/connections", json={**body, "enable_triggers": True})
        assert legacy.status_code == 400
        assert "Install/Upgrade" in legacy.json()["detail"]
        assert installs == []

        explicit = client.post(f"/api/connections/{connection_id}/changes/install-triggers")
        assert explicit.status_code == 202
        assert installs == [connection_id]
