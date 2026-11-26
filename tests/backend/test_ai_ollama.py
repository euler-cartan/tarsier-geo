"""Live Ollama check for TRS-072. Skips only if Ollama isn't actually running."""

import requests
import pytest
from fastapi.testclient import TestClient

from tarsier.ai.client import chat
from tarsier.api.app import create_app
from tarsier.storage import secrets, settings as settings_store
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

OLLAMA_TAGS = "http://127.0.0.1:11434/api/tags"


def _ollama_model() -> str | None:
    try:
        response = requests.get(OLLAMA_TAGS, timeout=3)
        response.raise_for_status()
    except requests.RequestException:
        return None
    models = response.json().get("models") or []
    if not models:
        return None
    return models[0].get("name")


pytestmark = pytest.mark.skipif(_ollama_model() is None, reason="Ollama is not running with a pulled model")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    monkeypatch.setattr(secrets, "keyring", _ForcedFailureKeyring())


def test_ollama_chat_round_trip(home):
    model = _ollama_model()
    assert model
    settings_store.save_ai_config(
        provider="ollama",
        endpoint_url=OLLAMA_DEFAULT_ENDPOINT,
        model=model,
    )
    result = chat([{"role": "user", "content": "Reply with the single word pong."}])
    assert result.provider == "ollama"
    assert result.model == model
    assert result.content


def test_ollama_test_connection_via_settings_api(home):
    model = _ollama_model()
    client = TestClient(create_app())
    response = client.post(
        "/api/settings/ai/test",
        json={
            "provider": "ollama",
            "endpoint_url": OLLAMA_DEFAULT_ENDPOINT,
            "model": model,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["reply"]
