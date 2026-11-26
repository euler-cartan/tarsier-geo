"""One common chat-completions client for Ollama and any OpenAI-compatible API.

TAD §7.2: the rest of the app never branches on provider. This module is
the only place that talks to an AI HTTP endpoint. It never opens a user
data connection and never logs secrets.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

from tarsier.storage import settings as settings_store

PRIVACY_WARNING = (
    "Using an external API may send parts of your data descriptions to that provider. "
    "Use Ollama for fully private AI."
)

_TIMEOUT_SECONDS = 60


class AINotConfiguredError(Exception):
    """Raised when an AI feature is used before Settings AI config is saved."""


class AIError(Exception):
    """A configured AI endpoint could not complete the request."""


@dataclass(frozen=True)
class ChatResult:
    content: str
    provider: str
    model: str


def chat(
    messages: list[dict],
    *,
    provider: str | None = None,
    endpoint_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> ChatResult:
    """Send chat-completions messages. Omit overrides to use saved Settings."""
    resolved = _resolve(provider, endpoint_url, model, api_key)
    payload = {"model": resolved.model, "messages": messages, "temperature": 0}
    headers = {"Content-Type": "application/json"}
    # Only an external provider requires a key. A leftover key from a
    # previous external setup must not be sent to local Ollama.
    if resolved.provider == "external" and resolved.api_key:
        headers["Authorization"] = f"Bearer {resolved.api_key}"

    try:
        response = requests.post(
            resolved.endpoint_url, json=payload, headers=headers, timeout=_TIMEOUT_SECONDS, allow_redirects=False
        )
    except requests.RequestException as exc:
        raise AIError(_friendly_network_error(resolved.provider, exc)) from exc

    if response.status_code >= 300:
        raise AIError(_friendly_http_error(resolved.provider, response.status_code))

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AIError("The AI replied in a form Tarsier could not read. Check the endpoint URL.") from exc

    if not isinstance(content, str) or not content.strip():
        raise AIError("The AI returned an empty reply.")
    return ChatResult(content=content.strip(), provider=resolved.provider, model=resolved.model)


def test_connection(
    *,
    provider: str,
    endpoint_url: str,
    model: str,
    api_key: str | None = None,
) -> ChatResult:
    return chat(
        [{"role": "user", "content": "Reply with the single word pong."}],
        provider=provider,
        endpoint_url=endpoint_url,
        model=model,
        api_key=api_key,
    )


@dataclass(frozen=True)
class _Resolved:
    provider: str
    endpoint_url: str
    model: str
    api_key: str | None


def _resolve(
    provider: str | None,
    endpoint_url: str | None,
    model: str | None,
    api_key: str | None,
) -> _Resolved:
    saved = settings_store.get_ai_config()
    resolved_provider = provider or saved.provider
    resolved_endpoint = (endpoint_url or saved.endpoint_url or "").strip()
    resolved_model = (model or saved.model or "").strip()
    resolved_key = api_key if api_key is not None else settings_store.get_ai_api_key()

    if resolved_provider not in ("ollama", "external") or not resolved_endpoint or not resolved_model:
        raise AINotConfiguredError("Set up AI first in Settings.")
    if resolved_provider == "external" and not resolved_key:
        raise AINotConfiguredError("Set up AI first in Settings.")
    from tarsier.ai.providers import validate_provider
    try:
        resolved_endpoint = validate_provider(resolved_provider, resolved_endpoint, resolved_key if resolved_provider == "external" else None)
    except ValueError as exc:
        raise AINotConfiguredError(str(exc)) from exc
    return _Resolved(resolved_provider, resolved_endpoint, resolved_model, resolved_key)


def _friendly_network_error(provider: str, exc: requests.RequestException) -> str:
    if provider == "ollama":
        return (
            "Could not reach Ollama. Is it running, and is the endpoint URL the "
            "chat-completions address (usually http://127.0.0.1:11434/v1/chat/completions)?"
        )
    return "Could not reach the external AI endpoint. Check the URL and that this machine can access it."


def _friendly_http_error(provider: str, status_code: int) -> str:
    if status_code in (401, 403):
        return "The AI endpoint rejected the request. Check the API key."
    if status_code == 404:
        return "The AI endpoint was not found. Check the URL and model name."
    kind = "Ollama" if provider == "ollama" else "external AI"
    return f"The {kind} endpoint returned an error (HTTP {status_code})."
