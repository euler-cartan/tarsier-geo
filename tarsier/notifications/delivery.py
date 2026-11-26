"""SMTP and webhook delivery for explicitly configured notification actions."""

from email.message import EmailMessage
from email.utils import getaddresses, parseaddr
import json
import smtplib
import ssl
from urllib.parse import urlsplit

import requests

from tarsier.storage import settings


class DeliveryError(Exception):
    """A delivery failure with a safe message for the local UI/log."""


def parse_recipients(value: str | list[str] | None) -> list[str]:
    if isinstance(value, list):
        raw = ",".join(str(item) for item in value)
    else:
        raw = str(value or "")
    if "\r" in raw or "\n" in raw:
        raise DeliveryError("Enter recipient email addresses separated by commas.")
    addresses = [address.strip() for _name, address in getaddresses([raw]) if address.strip()]
    if not addresses or any("@" not in address for address in addresses):
        raise DeliveryError("Enter at least one valid recipient email address.")
    return addresses


def send_email(recipients: str | list[str] | None, subject: str, body: str) -> None:
    config = settings.get_notification_config()
    host = (config.get("host") or "").strip()
    sender = (config.get("sender") or "").strip()
    if not host or any(char.isspace() for char in host) or not sender:
        raise DeliveryError("Configure an SMTP server and sender address in Settings first.")
    to_addresses = parse_recipients(recipients)
    if "\r" in subject or "\n" in subject:
        raise DeliveryError("The email subject is invalid.")
    sender_address = parseaddr(sender)[1]
    if "@" not in sender_address or "\r" in sender or "\n" in sender:
        raise DeliveryError("The sender address in SMTP settings is invalid.")

    message = EmailMessage()
    message["From"] = sender_address
    message["To"] = ", ".join(to_addresses)
    message["Subject"] = subject[:180]
    message.set_content(body[:20_000])

    port = int(config.get("port") or 587)
    security = config.get("security") or "starttls"
    username = settings.get_smtp_username() or ""
    password = settings.get_smtp_password()
    if username and not password:
        raise DeliveryError("SMTP authentication is configured without a saved password.")

    try:
        if security == "ssl":
            client = smtplib.SMTP_SSL(host, port, timeout=10, context=ssl.create_default_context())
        else:
            client = smtplib.SMTP(host, port, timeout=10)
        with client:
            if security == "starttls":
                client.starttls(context=ssl.create_default_context())
            if username:
                client.login(username, password or "")
            client.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise DeliveryError("The SMTP server rejected the saved username or password.") from exc
    except (smtplib.SMTPException, OSError, ValueError) as exc:
        raise DeliveryError("Email could not be delivered. Check the SMTP settings and server availability.") from exc


def send_webhook(url: str, payload: dict) -> None:
    target = (url or "").strip()
    try:
        parsed = urlsplit(target)
        hostname = parsed.hostname
    except ValueError as exc:
        raise DeliveryError("Enter a valid HTTP or HTTPS webhook URL.") from exc
    if parsed.scheme not in ("http", "https") or not hostname or parsed.username or parsed.password:
        raise DeliveryError("Enter a valid HTTP or HTTPS webhook URL.")
    try:
        response = requests.post(target, json=payload, timeout=5, allow_redirects=False)
    except requests.RequestException as exc:
        raise DeliveryError("The webhook endpoint could not be reached.") from exc
    if response.status_code < 200 or response.status_code >= 300:
        raise DeliveryError(f"The webhook endpoint returned HTTP {response.status_code}.")


# Teams rejects large messages (Microsoft quotes about 28 KB), so cap the text in bytes.
_TEAMS_TEXT_BYTES = 20_000


def _teams_card(message: str) -> dict:
    """The Adaptive Card body that a Teams Workflows webhook expects."""
    # json.dumps escapes non-ASCII characters, so measure what is actually sent.
    text = message[:_TEAMS_TEXT_BYTES]
    while len(json.dumps(text)) > _TEAMS_TEXT_BYTES:
        text = text[: len(text) * 9 // 10]
    if text != message:
        text = text.rstrip() + " … (shortened)"
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {
                "type": "AdaptiveCard",
                "version": "1.2",
                "body": [{"type": "TextBlock", "text": text, "wrap": True}],
            },
        }],
    }


def send_chat(channel: str, message: str) -> None:
    from tarsier.storage.secrets import get_secret
    if channel not in ("slack", "teams"):
        raise DeliveryError("Choose Slack or Teams.")
    url = get_secret(f"notification-{channel}-webhook")
    if not url:
        raise DeliveryError(f"Configure the {channel.title()} incoming webhook in Settings first.")
    send_webhook(url, _teams_card(message) if channel == "teams" else {"text": message[:20000]})
