"""Read/write the tabular sample-rows preview cache (TAD §8)."""

import json
from datetime import datetime, timezone

from tarsier.storage.db import get_session
from tarsier.storage.models import ItemPreviewCache


def save_preview(connection_id: str, schema: str, name: str, columns: list[dict], rows: list[dict]) -> None:
    with get_session() as session:
        record = session.get(ItemPreviewCache, (connection_id, schema, name))
        if record is None:
            record = ItemPreviewCache(connection_id=connection_id, schema=schema, name=name)
            session.add(record)
        record.preview_json = json.dumps({"columns": columns, "rows": rows})
        record.scanned_at = datetime.now(timezone.utc)
        session.commit()


def get_preview(connection_id: str, schema: str, name: str) -> dict | None:
    with get_session() as session:
        record = session.get(ItemPreviewCache, (connection_id, schema, name))
        if record is None:
            return None
        return {**json.loads(record.preview_json), "scanned_at": record.scanned_at.isoformat()}


def delete_all_for_connection(connection_id: str) -> None:
    with get_session() as session:
        session.query(ItemPreviewCache).filter(ItemPreviewCache.connection_id == connection_id).delete()
        session.commit()
