"""Saved AI assistant conversations (local SQLite only)."""

from tarsier.storage.db import get_session
from tarsier.storage.models import ChatMessage

_MAX_CONVERSATIONS = 100


def add_exchange(connection_id: str, conversation_id: str, question: str, answer: str) -> None:
    with get_session() as session:
        for role, text in (("user", question), ("ai", answer)):
            session.add(ChatMessage(connection_id=connection_id, conversation_id=conversation_id, role=role, text=text[:20000]))
        session.commit()
    for old in list_conversations(connection_id, limit=None)[_MAX_CONVERSATIONS:]:
        delete_conversation(connection_id, old["id"])


def get_messages(connection_id: str, conversation_id: str) -> list[dict]:
    with get_session() as session:
        rows = (
            session.query(ChatMessage)
            .filter_by(connection_id=connection_id, conversation_id=conversation_id)
            .order_by(ChatMessage.id)
            .all()
        )
        return [{"role": r.role, "text": r.text} for r in rows]


def list_conversations(connection_id: str, limit: int | None = _MAX_CONVERSATIONS) -> list[dict]:
    """Newest first. The title is the first thing the user asked."""
    found: dict[str, dict] = {}
    with get_session() as session:
        rows = session.query(ChatMessage).filter_by(connection_id=connection_id).order_by(ChatMessage.id).all()
        for row in rows:
            item = found.setdefault(row.conversation_id, {"id": row.conversation_id, "title": row.text[:80], "last": row.id})
            item["last"] = row.id
            item["updated_at"] = row.created_at.isoformat()
    ordered = sorted(found.values(), key=lambda c: c["last"], reverse=True)
    for item in ordered:
        del item["last"]
    return ordered[:limit]


def delete_conversation(connection_id: str, conversation_id: str) -> None:
    with get_session() as session:
        session.query(ChatMessage).filter_by(connection_id=connection_id, conversation_id=conversation_id).delete()
        session.commit()


def delete_all_for_connection(connection_id: str) -> None:
    with get_session() as session:
        session.query(ChatMessage).filter_by(connection_id=connection_id).delete()
        session.commit()
