"""Covers PRD Phase 0 "Done when": the skeleton app runs (TAD §1, §4)."""

from fastapi.testclient import TestClient

from tarsier.api.app import create_app


def test_health_endpoint_reports_ok():
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_deep_client_side_route_falls_back_to_index_html():
    """A hard navigation/refresh on a React Router path (e.g.
    /connections/<id>/overview) isn't a real file on disk — it must still
    serve index.html so React Router can take over, not a bare 404. Found
    via live browser testing: this broke outright before the fix."""
    client = TestClient(create_app())
    response = client.get("/connections/some-id/overview")
    assert response.status_code == 200
    assert "<div id=\"root\">" in response.text
