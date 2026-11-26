"""Tarsier's own settings (TAD §5), starting with AI configuration.

Non-secret fields live in SQLite. The API key uses the same secret store
as connection passwords (TAD §9) and is never written to SQLite or logs.
"""

from dataclasses import dataclass

from tarsier.storage import secrets
from tarsier.storage.db import get_session
from tarsier.storage.models import AppSetting

AI_SECRET_ID = "ai-api-key"
SMTP_SECRET_ID = "notification-smtp-password"
SMTP_USERNAME_SECRET_ID = "notification-smtp-username"
_APPEARANCE_KEY = "appearance_theme"
_PROVIDER_KEY = "ai_provider"
_ENDPOINT_KEY = "ai_endpoint_url"
_MODEL_KEY = "ai_model"
_SMTP_KEYS = {
    "host": "notification_smtp_host",
    "port": "notification_smtp_port",
    "security": "notification_smtp_security",
    "sender": "notification_smtp_sender",
}

OLLAMA_DEFAULT_ENDPOINT = "http://127.0.0.1:11434/v1/chat/completions"


@dataclass(frozen=True)
class AiConfig:
    provider: str | None  # "ollama" | "external" | None
    endpoint_url: str | None
    model: str | None
    api_key_set: bool

    @property
    def configured(self) -> bool:
        if self.provider not in ("ollama", "external"):
            return False
        if not self.endpoint_url or not self.model:
            return False
        if self.provider == "external" and not self.api_key_set:
            return False
        from tarsier.ai.providers import validate_provider
        try:
            validate_provider(self.provider, self.endpoint_url)
        except ValueError:
            return False
        return True


def _get_value(key: str) -> str | None:
    with get_session() as session:
        record = session.get(AppSetting, key)
        return record.value if record else None


def _set_value(key: str, value: str) -> None:
    with get_session() as session:
        record = session.get(AppSetting, key)
        if record is None:
            session.add(AppSetting(key=key, value=value))
        else:
            record.value = value
        session.commit()


def get_ai_config() -> AiConfig:
    return AiConfig(
        provider=_get_value(_PROVIDER_KEY),
        endpoint_url=_get_value(_ENDPOINT_KEY),
        model=_get_value(_MODEL_KEY),
        api_key_set=secrets.get_secret(AI_SECRET_ID) is not None,
    )


def get_ai_api_key() -> str | None:
    return secrets.get_secret(AI_SECRET_ID)


def get_notification_config() -> dict:
    return {
        key: _get_value(setting_key)
        for key, setting_key in _SMTP_KEYS.items()
    } | {
        "username_set": secrets.get_secret(SMTP_USERNAME_SECRET_ID) is not None,
        "password_set": secrets.get_secret(SMTP_SECRET_ID) is not None,
    }


def get_smtp_password() -> str | None:
    return secrets.get_secret(SMTP_SECRET_ID)


def get_smtp_username() -> str | None:
    return secrets.get_secret(SMTP_USERNAME_SECRET_ID)


def save_notification_config(
    *, host: str, port: int, security: str, username: str, sender: str,
    password: str | None = None, clear_credentials: bool = False,
) -> dict:
    host = host.strip()
    username = username.strip()
    sender = sender.strip()
    if not host or not sender:
        raise ValueError("SMTP server and sender address are required.")
    if not 1 <= port <= 65535:
        raise ValueError("SMTP port must be between 1 and 65535.")
    if security not in ("starttls", "ssl", "none"):
        raise ValueError("Choose STARTTLS, SSL/TLS, or no encryption.")
    if clear_credentials:
        secrets.delete_secret(SMTP_SECRET_ID)
        secrets.delete_secret(SMTP_USERNAME_SECRET_ID)
    else:
        if password:
            secrets.set_secret(SMTP_SECRET_ID, password)
        if username:
            secrets.set_secret(SMTP_USERNAME_SECRET_ID, username)
    for key, value in {
        "host": host,
        "port": str(port),
        "security": security,
        "sender": sender,
    }.items():
        _set_value(_SMTP_KEYS[key], value)
    return get_notification_config()


def save_ai_config(
    *,
    provider: str,
    endpoint_url: str,
    model: str,
    api_key: str | None = None,
    clear_api_key: bool = False,
) -> AiConfig:
    if provider not in ("ollama", "external"):
        raise ValueError(f"Unknown AI provider: {provider!r}")
    from tarsier.ai.providers import validate_provider
    endpoint_url = validate_provider(provider, endpoint_url, api_key)
    model = model.strip()
    if not endpoint_url or not model:
        raise ValueError("Endpoint URL and model name are required.")

    will_have_key = bool(api_key) or (not clear_api_key and secrets.get_secret(AI_SECRET_ID) is not None)
    if provider == "external" and not api_key and not clear_api_key:
        validate_provider(provider, endpoint_url, secrets.get_secret(AI_SECRET_ID))
    if provider == "external" and not will_have_key:
        raise ValueError("An API key is required for an external AI provider.")

    _set_value(_PROVIDER_KEY, provider)
    _set_value(_ENDPOINT_KEY, endpoint_url)
    _set_value(_MODEL_KEY, model)

    if clear_api_key:
        secrets.delete_secret(AI_SECRET_ID)
    elif api_key:
        secrets.set_secret(AI_SECRET_ID, api_key)

    return get_ai_config()


APPEARANCES = ("light", "dark")


def get_appearance() -> str:
    return _get_value(_APPEARANCE_KEY) or "light"


def save_appearance(theme: str) -> str:
    if theme not in APPEARANCES:
        raise ValueError("Choose light or dark appearance.")
    _set_value(_APPEARANCE_KEY, theme)
    return theme
