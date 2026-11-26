"""Create/read/delete saved connection definitions (TAD §5).

Config (host, port, database, username, ...) is stored as JSON in Tarsier's
own SQLite. The password is never part of that JSON  -  it's handed to
tarsier.storage.secrets, keyed by the connection's id.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from tarsier.storage import alerts as alert_store
from tarsier.storage import automations as auto_store
from tarsier.storage import change_log, item_cache, preview_cache, quality_cache, raster_cache, secrets, stats_cache
from tarsier.storage import flowchart as flowchart_store
from tarsier.storage.db import get_session
from tarsier.storage.models import ConnectionRecord


@dataclass
class SavedConnection:
    id: str
    name: str
    type: str
    config: dict = field(default_factory=dict)
    created_at: datetime | None = None
    last_checked_at: datetime | None = None
    last_status: str | None = None
    last_scanned_at: datetime | None = None

    @classmethod
    def _from_record(cls, record: ConnectionRecord) -> "SavedConnection":
        return cls(
            id=record.id,
            name=record.name,
            type=record.type,
            config=json.loads(record.config_json),
            created_at=record.created_at,
            last_checked_at=record.last_checked_at,
            last_status=record.last_status,
            last_scanned_at=record.last_scanned_at,
        )


def create_connection(
    name: str, type: str, config: dict, password: str | None = None
) -> SavedConnection:
    connection_id = str(uuid.uuid4())
    with get_session() as session:
        record = ConnectionRecord(
            id=connection_id,
            name=name,
            type=type,
            config_json=json.dumps(config),
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        saved = SavedConnection._from_record(record)

    if password:
        secrets.set_secret(connection_id, password)

    return saved


def get_connection(connection_id: str) -> SavedConnection | None:
    with get_session() as session:
        record = session.get(ConnectionRecord, connection_id)
        return SavedConnection._from_record(record) if record else None


def get_connection_password(connection_id: str) -> str | None:
    return secrets.get_secret(connection_id)


def list_connections() -> list[SavedConnection]:
    with get_session() as session:
        records = session.query(ConnectionRecord).order_by(ConnectionRecord.name).all()
        return [SavedConnection._from_record(r) for r in records]


def delete_connection(connection_id: str) -> None:
    with get_session() as session:
        record = session.get(ConnectionRecord, connection_id)
        if record is not None:
            session.delete(record)
            session.commit()
    secrets.delete_secret(connection_id)
    item_cache.delete_all_for_connection(connection_id)
    stats_cache.delete_all_for_connection(connection_id)
    raster_cache.delete_all_for_connection(connection_id)
    preview_cache.delete_all_for_connection(connection_id)
    from tarsier.storage import map_cache
    map_cache.delete_all_for_connection(connection_id)
    quality_cache.delete_all_for_connection(connection_id)
    change_log.delete_all_for_connection(connection_id)
    alert_store.delete_all_for_connection(connection_id)
    auto_store.delete_all_for_connection(connection_id)
    flowchart_store.delete_all_for_connection(connection_id)
    from tarsier.storage import chats
    chats.delete_all_for_connection(connection_id)
    from tarsier.graph.engine import refresh_quietly

    refresh_quietly()


def record_check_result(connection_id: str, status: str) -> None:
    with get_session() as session:
        record = session.get(ConnectionRecord, connection_id)
        if record is not None:
            record.last_checked_at = datetime.now(timezone.utc)
            record.last_status = status
            session.commit()


def record_scan_result(connection_id: str) -> None:
    with get_session() as session:
        record = session.get(ConnectionRecord, connection_id)
        if record is not None:
            record.last_scanned_at = datetime.now(timezone.utc)
            session.commit()
