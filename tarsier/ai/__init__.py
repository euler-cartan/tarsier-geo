"""AI assistant (TAD §7.2)  -  one OpenAI-compatible path for Ollama and external APIs."""

from tarsier.ai.client import (
    PRIVACY_WARNING,
    AIError,
    AINotConfiguredError,
    chat,
    test_connection,
)

__all__ = [
    "PRIVACY_WARNING",
    "AIError",
    "AINotConfiguredError",
    "chat",
    "test_connection",
]
