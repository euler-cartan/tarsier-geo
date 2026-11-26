"""Settings routes  -  AI configuration only in Phase 3 (FSD §13, TAD §7.2)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tarsier.ai.client import AIError, AINotConfiguredError, PRIVACY_WARNING, test_connection
from tarsier.notifications.delivery import DeliveryError, send_email
from tarsier.storage import settings as settings_store
from tarsier.storage.settings import OLLAMA_DEFAULT_ENDPOINT

router = APIRouter(prefix="/api/settings")


def _public_ai(config=None) -> dict:
    config = config or settings_store.get_ai_config()
    return {
        "provider": config.provider,
        "endpoint_url": config.endpoint_url,
        "model": config.model,
        "api_key_set": config.api_key_set,
        "configured": config.configured,
        "privacy_warning": PRIVACY_WARNING if config.provider == "external" else None,
        "ollama_default_endpoint": OLLAMA_DEFAULT_ENDPOINT,
    }


@router.get("/ai")
def get_ai_settings():
    return _public_ai()


@router.get("/ai/models")
def list_ai_models(provider: str = "ollama", endpoint_url: str = OLLAMA_DEFAULT_ENDPOINT):
    from tarsier.ai.providers import discover_models
    try:
        return {"models": discover_models(provider, endpoint_url)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class SaveAiSettingsRequest(BaseModel):
    provider: str
    endpoint_url: str
    model: str
    api_key: str | None = None
    clear_api_key: bool = False


@router.put("/ai")
def save_ai_settings(body: SaveAiSettingsRequest):
    try:
        config = settings_store.save_ai_config(
            provider=body.provider,
            endpoint_url=body.endpoint_url,
            model=body.model,
            api_key=body.api_key or None,
            clear_api_key=body.clear_api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _public_ai(config)


class TestAiSettingsRequest(BaseModel):
    provider: str
    endpoint_url: str
    model: str
    api_key: str | None = None


@router.post("/ai/test")
def test_ai_settings(body: TestAiSettingsRequest):
    key = body.api_key or None
    if not key:
        key = settings_store.get_ai_api_key()
    try:
        result = test_connection(
            provider=body.provider,
            endpoint_url=body.endpoint_url,
            model=body.model,
            api_key=key,
        )
    except AINotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "reply": result.content, "model": result.model}


@router.get("/notifications")
def get_notification_settings():
    return settings_store.get_notification_config()


class SaveNotificationSettingsRequest(BaseModel):
    host: str
    port: int = 587
    security: str = "starttls"
    username: str = ""
    sender: str
    password: str | None = None
    clear_credentials: bool = False


@router.put("/notifications")
def save_notification_settings(body: SaveNotificationSettingsRequest):
    try:
        return settings_store.save_notification_config(
            host=body.host,
            port=body.port,
            security=body.security,
            username=body.username,
            sender=body.sender,
            password=body.password or None,
            clear_credentials=body.clear_credentials,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class TestEmailRequest(BaseModel):
    recipient: str


@router.post("/notifications/test")
def send_test_email(body: TestEmailRequest):
    try:
        send_email(body.recipient, "Tarsier notification test", "This is a test email from Tarsier.")
    except DeliveryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "message": "Test email sent."}


@router.get("/appearance")
def get_appearance():
    return {"theme": settings_store.get_appearance(), "available": list(settings_store.APPEARANCES)}


class SaveAppearanceRequest(BaseModel):
    theme: str


class ChatChannelRequest(BaseModel):
    url: str = ""
    clear: bool = False


@router.get("/chat-channels")
def chat_channels():
    from tarsier.storage.secrets import get_secret
    return {channel: bool(get_secret(f"notification-{channel}-webhook")) for channel in ("slack", "teams")}


@router.put("/chat-channels/{channel}")
def save_chat_channel(channel: str, body: ChatChannelRequest):
    from urllib.parse import urlsplit
    from tarsier.storage.secrets import set_secret, delete_secret
    if channel not in ("slack", "teams"):
        raise HTTPException(400, "Choose Slack or Teams.")
    key = f"notification-{channel}-webhook"
    if body.clear:
        delete_secret(key)
    elif body.url:
        try:
            url = urlsplit(body.url)
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError()
        except ValueError as exc:
            raise HTTPException(400, "Enter an HTTPS incoming webhook URL.") from exc
        set_secret(key, body.url)
    return chat_channels()


@router.put("/appearance")
def save_appearance(body: SaveAppearanceRequest):
    try:
        theme = settings_store.save_appearance(body.theme)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"theme": theme, "available": list(settings_store.APPEARANCES)}
