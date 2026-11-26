"""AI query API with an invented inventory and a fake model (TRS-025/026)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from tarsier.api.app import create_app
from tarsier.storage import secrets
from tarsier.storage.settings import OLLAMA_DEFAULT_ENDPOINT


class _ForcedFailureKeyring:
    class errors:
        from keyring.errors import KeyringError, NoKeyringError  # noqa: F401

    def set_password(self, *a, **k):
        raise self.errors.NoKeyringError("no backend in test")

    def get_password(self, *a, **k):
        raise self.errors.NoKeyringError("no backend in test")

    def delete_password(self, *a, **k):
        raise self.errors.NoKeyringError("no backend in test")


class _FilterHandler(BaseHTTPRequestHandler):
    reply = {"combine": "and", "conditions": [{"column": "stock_qty", "op": "=", "value": 12}]}

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        payload = json.dumps({"choices": [{"message": {"content": json.dumps(self.server.reply)}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A003
        return


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    monkeypatch.setattr(secrets, "keyring", _ForcedFailureKeyring())
    return TestClient(create_app())


@pytest.fixture
def connection_id(client):
    response = client.post(
        "/api/connections",
        json={"name": "Sample files", "type": "files", "config": {"folder": "tests/datasets/files_sample"}},
    )
    return response.json()["id"]


@pytest.mark.parametrize(
    ("question", "reply", "expected_codes", "expected_caption"),
    [
        ("Which items have 12 units in stock?", {"column": "stock_qty", "op": "=", "value": 12}, {"A02", "A06"}, "stock_qty = 12"),
        ("Which items are stored in West?", {"column": "warehouse", "op": "=", "value": "West"}, {"A02", "A05"}, "warehouse = 'West'"),
        ("Which items have no supplier?", {"column": "supplier", "op": "is_null"}, {"A04"}, "supplier IS NULL"),
    ],
)
def test_ai_query_returns_caption_and_matching_rows(client, connection_id, question, reply, expected_codes, expected_caption):
    server = HTTPServer(("127.0.0.1", 0), _FilterHandler)
    server.reply = {"combine": "and", "conditions": [reply]}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        client.put(
            "/api/settings/ai",
            json={
                "provider": "ollama",
                "endpoint_url": f"http://{host}:{port}/v1/chat/completions",
                "model": "test",
            },
        )
        response = client.post(
            f"/api/connections/{connection_id}/item/ai-query",
            json={"question": question, "schema": "", "name": "sample_inventory.csv"},
        )
    finally:
        server.shutdown()
    assert response.status_code == 200
    body = response.json()
    assert body["caption"] == expected_caption
    assert {row["item_code"] for row in body["rows"]} == expected_codes


def test_ai_query_rejects_unknown_column(client, connection_id):
    server = HTTPServer(("127.0.0.1", 0), _FilterHandler)
    server.reply = {"combine": "and", "conditions": [{"column": "secret_price", "op": "=", "value": 1}]}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        client.put(
            "/api/settings/ai",
            json={"provider": "ollama", "endpoint_url": f"http://{host}:{port}/v1/chat/completions", "model": "test"},
        )
        response = client.post(
            f"/api/connections/{connection_id}/item/ai-query",
            json={"question": "Which items have secret price 1?", "schema": "", "name": "sample_inventory.csv"},
        )
    finally:
        server.shutdown()
    assert response.status_code == 400
    assert "isn't on this table" in response.json()["detail"]


def test_stats_scan_includes_histogram_and_flag_rows(client, connection_id):
    scan = client.post(
        f"/api/connections/{connection_id}/item/stats/scan",
        params={"schema": "", "name": "sample_inventory.csv"},
    )
    assert scan.status_code == 202
    stats = client.get(
        f"/api/connections/{connection_id}/item/stats",
        params={"schema": "", "name": "sample_inventory.csv"},
    ).json()
    stock = next(c for c in stats["columns"] if c["name"] == "stock_qty")
    assert stock["histogram"]
    assert sum(b["count"] for b in stock["histogram"]) == 5  # one null excluded
    assert "duplicate_rows" in stats
