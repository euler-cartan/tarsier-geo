import pytest
from fastapi.testclient import TestClient
from tarsier.api.app import create_app
from tarsier.storage import connections, secrets
from tarsier.notifications import delivery


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path / "home"))
    return TestClient(create_app())


def test_local_origin_guard(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health", headers={"origin": "http://testserver"}).status_code == 200
    assert client.get("/api/health", headers={"origin": "https://unrelated.example"}).status_code == 403
    assert client.get("/api/health", headers={"host": "unrelated.example"}).status_code == 403


def test_edit_connection_tests_before_saving(client, tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    c = connections.create_connection("Original", "files", {"folder": str(folder)})
    url = f"/api/connections/{c.id}"
    assert client.put(url, json={"name": "Edited", "type": "files", "config": {"folder": str(folder / "missing")}}).status_code == 400
    assert connections.get_connection(c.id).name == "Original"
    assert client.put(url, json={"name": "Edited", "type": "files", "config": {"folder": str(folder)}}).status_code == 200
    assert connections.get_connection(c.id).name == "Edited"
    assert client.delete(url).status_code == 200
    assert connections.get_connection(c.id) is None


def test_chat_credentials_masked_and_delivery_explicit(client, monkeypatch):
    stored = {}
    monkeypatch.setattr(secrets, "set_secret", lambda k,v: stored.update({k:v}))
    monkeypatch.setattr(secrets, "get_secret", lambda k: stored.get(k))
    calls = []
    monkeypatch.setattr(delivery, "send_webhook", lambda url,payload: calls.append((url,payload)))
    response = client.put("/api/settings/chat-channels/slack", json={"url": "https://hooks.example.org/private-token"})
    assert response.status_code == 200
    assert "private-token" not in response.text
    assert calls == []  # configuring never sends a message
    delivery.send_chat("slack", "A quality check failed")
    assert calls == [("https://hooks.example.org/private-token", {"text": "A quality check failed"})]
    with pytest.raises(delivery.DeliveryError, match="Configure"):
        delivery.send_chat("teams", "test")


def test_cached_navigation_and_design_document(client):
    c = connections.create_connection("Example", "files", {})
    result = client.get("/api/navigation")
    assert any(item["url"] == f"/connections/{c.id}/snapshots" for item in result.json())
    assert client.get("/api/about/resources/LICENSE").status_code == 200


def test_teams_gets_a_shortened_adaptive_card_and_slack_stays_plain_text(monkeypatch):
    import json
    calls = []
    monkeypatch.setattr(secrets, "get_secret", lambda k: f"https://hooks.example.org/{k}")
    monkeypatch.setattr(delivery, "send_webhook", lambda url, payload: calls.append(payload))
    delivery.send_chat("teams", "Quality check failed")
    delivery.send_chat("teams", "é" * 50_000)
    delivery.send_chat("slack", "Quality check failed")
    card = calls[0]["attachments"][0]
    assert calls[0]["type"] == "message"
    assert card["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert card["content"]["body"] == [{"type": "TextBlock", "text": "Quality check failed", "wrap": True}]
    assert len(json.dumps(calls[1])) < 28_000
    assert calls[1]["attachments"][0]["content"]["body"][0]["text"].endswith("(shortened)")
    assert calls[2] == {"text": "Quality check failed"}
