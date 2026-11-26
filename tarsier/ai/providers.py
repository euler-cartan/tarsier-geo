"""Provider destinations and model discovery. Credentials never enter URLs."""
from urllib.parse import urlsplit, urlunsplit

import requests

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


def validate_provider(provider: str, endpoint: str, key: str | None = None) -> str:
    endpoint = endpoint.strip().rstrip("/")
    if provider == "external":
        if endpoint != OPENROUTER_ENDPOINT:
            raise ValueError("External AI supports OpenRouter only. Select OpenRouter in Settings.")
        if key and not key.startswith("sk-or-v1-"):
            raise ValueError("Enter an OpenRouter API key (starts with sk-or-v1-).")
    elif provider == "ollama":
        parsed = urlsplit(endpoint)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Enter an HTTP or HTTPS Ollama endpoint without embedded credentials.")
    else:
        raise ValueError("Choose Ollama or OpenRouter.")
    return endpoint


def discover_models(provider: str, endpoint: str) -> list[dict]:
    endpoint = validate_provider(provider, endpoint)
    if provider == "external":
        url = "https://openrouter.ai/api/v1/models"
    else:
        parsed = urlsplit(endpoint)
        base = parsed.path.removesuffix("/v1/chat/completions").rstrip("/")
        url = urlunsplit((parsed.scheme, parsed.netloc, base + "/api/tags", "", ""))
    try:
        response = requests.get(url, timeout=12, allow_redirects=False)
        if response.status_code != 200:
            raise ValueError("Model discovery failed. Check the provider connection and retry.")
        body = response.json()
        records = body["data" if provider == "external" else "models"]
        result = []
        for item in records:
            if provider == "external" and "text" not in item.get("architecture", {}).get("output_modalities", ["text"]):
                continue
            model_id = item.get("id") if provider == "external" else item.get("name")
            if isinstance(model_id, str):
                result.append({"id": model_id, "name": item.get("name") or model_id})
        return sorted(result, key=lambda item: item["id"].lower())
    except (requests.RequestException, KeyError, TypeError) as exc:
        raise ValueError("Could not load models. Start Ollama or check your network, then retry.") from exc
