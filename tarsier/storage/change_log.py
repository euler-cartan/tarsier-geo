"""SQLite copy of captured changes (TAD §8)."""

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, literal_column
from sqlalchemy.dialects.sqlite import insert

from tarsier.changes.engine import ChangeEventView, changed_fields, is_mass_batch, report_summary
from tarsier.storage.db import get_session
from tarsier.storage.models import (
    ChangeEvent,
    EventCaptureCursor,
    ChangeFingerprint,
    ChangeFingerprintSnapshot,
    ChangeReport,
    ChangeTrackingState,
)


def get_state(connection_id: str) -> ChangeTrackingState | None:
    with get_session() as session:
        return session.get(ChangeTrackingState, connection_id)


def set_mode(connection_id: str, mode: str) -> None:
    with get_session() as session:
        record = session.get(ChangeTrackingState, connection_id)
        if record is None:
            record = ChangeTrackingState(connection_id=connection_id, mode=mode, last_source_log_id=0)
            session.add(record)
        else:
            record.mode = mode
        session.commit()


def set_report_interval(connection_id: str, interval: str | None) -> None:
    with get_session() as session:
        record = session.get(ChangeTrackingState, connection_id)
        if record is None:
            record = ChangeTrackingState(connection_id=connection_id, mode="none", last_source_log_id=0)
            session.add(record)
        record.report_interval = interval
        session.commit()


def acknowledge_failures(connection_id: str, value: int) -> None:
    with get_session() as session:
        record = session.get(ChangeTrackingState, connection_id)
        if record is None or record.mode != "triggers":
            raise ValueError("Trigger tracking is not enabled.")
        if record.acknowledged_failures is None or value > record.acknowledged_failures:
            record.acknowledged_failures = value
            record.acknowledged_at = datetime.now(timezone.utc)
            session.commit()


def record_sync(connection_id: str, last_source_log_id: int) -> None:
    with get_session() as session:
        record = session.get(ChangeTrackingState, connection_id)
        if record is None:
            record = ChangeTrackingState(connection_id=connection_id, mode="triggers", last_source_log_id=0)
            session.add(record)
        record.last_source_log_id = last_source_log_id
        record.utc_cache_version = 1
        record.last_sync_at = datetime.now(timezone.utc)
        session.commit()


def insert_events(connection_id: str, rows: list[dict], table_counts: dict[tuple[str, str], int | None]) -> None:
    grouped: dict[tuple[str, str, str | None], list[dict]] = {}
    for row in rows:
        key = (row["schema"], row["name"], None if row.get("txid") is None else str(row["txid"]))
        grouped.setdefault(key, []).append(row)

    mass_keys = set()
    for (schema, name, txid), batch in grouped.items():
        if txid is None:
            continue
        if is_mass_batch(len(batch), table_counts.get((schema, name))):
            mass_keys.add((schema, name, txid))

    with get_session() as session:
        source_ids = [r["source_log_id"] for r in rows if r.get("source_log_id") is not None]
        existing = {event.source_log_id: event for event in session.query(ChangeEvent).filter(
            ChangeEvent.connection_id == connection_id,
            ChangeEvent.source_log_id.in_(source_ids),
        )} if source_ids else {}
        new_count = sum(existing.get(row.get("source_log_id")) is None for row in rows)
        next_capture = None
        if new_count:
            statement = insert(EventCaptureCursor).values(connection_id=connection_id, last_value=new_count)
            statement = statement.on_conflict_do_update(
                index_elements=[EventCaptureCursor.connection_id],
                set_={"last_value": EventCaptureCursor.last_value + new_count},
            )
            session.execute(statement)
            next_capture = session.get(EventCaptureCursor, connection_id).last_value - new_count + 1
        for row in rows:
            previous = existing.get(row.get("source_log_id"))
            if previous is not None:
                previous.feature_id = row.get("feature_id")
                previous.occurred_at = _utc(row["occurred_at"])
                continue
            txid = None if row.get("txid") is None else str(row["txid"])
            event = ChangeEvent(
                id=str(uuid.uuid4()),
                connection_id=connection_id,
                occurred_at=_utc(row["occurred_at"]),
                db_user=row.get("db_user"),
                action=row["action"],
                schema=row["schema"],
                name=row["name"],
                feature_id=row.get("feature_id"),
                before_json=json.dumps(row["before"]) if row.get("before") is not None else None,
                after_json=json.dumps(row["after"]) if row.get("after") is not None else None,
                txid=txid,
                source=row.get("source") or "trigger",
                is_mass=(row["schema"], row["name"], txid) in mass_keys,
                source_log_id=row.get("source_log_id"),
                capture_seq=next_capture,
            )
            next_capture += 1
            session.add(event)
        session.commit()


# SQLite's own insertion counter. Used as a "seen up to here" cursor so
# alerts look at each captured change exactly once, however late it was synced.
_ROWID = literal_column("change_events.rowid")


def _filtered(session, connection_id, schema, name, feature_id, user, action, start, end):
    query = session.query(ChangeEvent).filter(ChangeEvent.connection_id == connection_id)
    if schema is not None:
        query = query.filter(ChangeEvent.schema == schema)
    if name:
        query = query.filter(ChangeEvent.name == name)
    if feature_id:
        query = query.filter(ChangeEvent.feature_id == feature_id)
    if user:
        query = query.filter(ChangeEvent.db_user == user)
    if action:
        query = query.filter(ChangeEvent.action == action)
    if start:
        query = query.filter(ChangeEvent.occurred_at >= _utc(start))
    if end:
        query = query.filter(ChangeEvent.occurred_at <= _utc(end))
    return query


def list_events(
    connection_id: str,
    *,
    schema: str | None = None,
    name: str | None = None,
    feature_id: str | None = None,
    user: str | None = None,
    action: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
    after_rowid: int | None = None,
    upto_rowid: int | None = None,
) -> list[ChangeEventView]:
    """Newest first. `limit` keeps a long history from being loaded whole."""
    with get_session() as session:
        query = _filtered(session, connection_id, schema, name, feature_id, user, action, start, end)
        if after_rowid is not None:
            query = query.filter(_ROWID > after_rowid)
        if upto_rowid is not None:
            query = query.filter(_ROWID <= upto_rowid)
        query = query.order_by(ChangeEvent.occurred_at.desc())
        if limit is not None:
            query = query.limit(limit)
        return [_view(row) for row in query.all()]


def count_by_action(
    connection_id: str,
    *,
    schema: str | None = None,
    name: str | None = None,
    feature_id: str | None = None,
    user: str | None = None,
    action: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, int]:
    """{action: count} for everything the filters match, not just the page returned."""
    with get_session() as session:
        rows = (
            _filtered(session, connection_id, schema, name, feature_id, user, action, start, end)
            .with_entities(ChangeEvent.action, func.count())
            .group_by(ChangeEvent.action)
            .all()
        )
        return {found: int(total) for found, total in rows}


def max_event_rowid(connection_id: str) -> int:
    with get_session() as session:
        value = (
            session.query(func.max(_ROWID))
            .select_from(ChangeEvent)
            .filter(ChangeEvent.connection_id == connection_id)
            .scalar()
        )
        return int(value or 0)


def daily_counts(connection_id: str, since: datetime) -> dict[str, dict[str, int]]:
    """{YYYY-MM-DD: {action: count}} computed by SQLite, not by loading every event."""
    with get_session() as session:
        day = func.date(ChangeEvent.occurred_at)
        rows = (
            session.query(day, ChangeEvent.action, func.count())
            .filter(ChangeEvent.connection_id == connection_id, ChangeEvent.occurred_at >= _utc(since))
            .group_by(day, ChangeEvent.action)
            .all()
        )
    counts: dict[str, dict[str, int]] = {}
    for stamp, action, total in rows:
        counts.setdefault(str(stamp), {})[action] = int(total)
    return counts


def latest_event_times(connection_id: str) -> dict[tuple[str, str], datetime]:
    """Return the last captured data-change time for each item in one query."""
    with get_session() as session:
        rows = (
            session.query(ChangeEvent.schema, ChangeEvent.name, func.max(ChangeEvent.occurred_at))
            .filter(ChangeEvent.connection_id == connection_id)
            .group_by(ChangeEvent.schema, ChangeEvent.name)
            .all()
        )
        return {(schema, name): stamp for schema, name, stamp in rows if stamp is not None}


def replace_fingerprints(connection_id: str, schema: str, name: str, current: dict[str, str]) -> None:
    with get_session() as session:
        session.query(ChangeFingerprint).filter_by(
            connection_id=connection_id, schema=schema, name=name
        ).delete()
        session.merge(ChangeFingerprintSnapshot(connection_id=connection_id,schema=schema,name=name))
        for fid, digest in current.items():
            session.add(
                ChangeFingerprint(
                    connection_id=connection_id,
                    schema=schema,
                    name=name,
                    feature_id=fid,
                    fingerprint=digest,
                )
            )
        session.commit()


def has_fingerprint_snapshot(connection_id: str, schema: str, name: str) -> bool:
    with get_session() as session:
        key = (connection_id,schema,name)
        return session.get(ChangeFingerprintSnapshot,key) is not None or session.query(ChangeFingerprint).filter_by(connection_id=connection_id,schema=schema,name=name).first() is not None


def get_fingerprints(connection_id: str, schema: str, name: str) -> dict[str, str]:
    with get_session() as session:
        rows = (
            session.query(ChangeFingerprint)
            .filter_by(connection_id=connection_id, schema=schema, name=name)
            .all()
        )
        return {row.feature_id: row.fingerprint for row in rows}


def save_report(connection_id: str, interval: str, period_start: datetime, period_end: datetime, events: list[ChangeEventView]) -> dict:
    payload = report_summary(events)
    payload["period_start"] = period_start.isoformat()
    payload["period_end"] = period_end.isoformat()
    with get_session() as session:
        record = ChangeReport(
            id=str(uuid.uuid4()),
            connection_id=connection_id,
            interval=interval,
            period_start=period_start,
            period_end=period_end,
            summary_json=json.dumps(payload),
            generated_at=datetime.now(timezone.utc),
        )
        session.add(record)
        state = session.get(ChangeTrackingState, connection_id)
        if state is None:
            state = ChangeTrackingState(connection_id=connection_id, mode="none", last_source_log_id=0)
            session.add(state)
        state.last_report_at = record.generated_at
        session.commit()
        payload["id"] = record.id
        payload["generated_at"] = record.generated_at.isoformat()
        payload["interval"] = interval
        return payload


def latest_report(connection_id: str) -> dict | None:
    with get_session() as session:
        record = (
            session.query(ChangeReport)
            .filter_by(connection_id=connection_id)
            .order_by(ChangeReport.generated_at.desc())
            .first()
        )
        if record is None:
            return None
        payload = json.loads(record.summary_json)
        payload["id"] = record.id
        payload["generated_at"] = record.generated_at.isoformat()
        payload["interval"] = record.interval
        return payload


def delete_all_for_connection(connection_id: str) -> None:
    with get_session() as session:
        session.query(ChangeEvent).filter(ChangeEvent.connection_id == connection_id).delete()
        session.query(EventCaptureCursor).filter(EventCaptureCursor.connection_id == connection_id).delete()
        session.query(ChangeFingerprint).filter(ChangeFingerprint.connection_id == connection_id).delete()
        session.query(ChangeFingerprintSnapshot).filter(ChangeFingerprintSnapshot.connection_id == connection_id).delete()
        session.query(ChangeReport).filter(ChangeReport.connection_id == connection_id).delete()
        session.query(ChangeTrackingState).filter(ChangeTrackingState.connection_id == connection_id).delete()
        session.commit()


def _utc(stamp: datetime) -> datetime:
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)


def _view(row: ChangeEvent) -> ChangeEventView:
    before = json.loads(row.before_json) if row.before_json else None
    after = json.loads(row.after_json) if row.after_json else None
    occurred = row.occurred_at
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=timezone.utc)
    return ChangeEventView(
        id=row.id,
        occurred_at=occurred,
        db_user=row.db_user,
        action=row.action,
        schema=row.schema,
        name=row.name,
        feature_id=row.feature_id,
        before=before,
        after=after,
        txid=row.txid,
        source=row.source,
        is_mass=row.is_mass,
        changed_fields=changed_fields(before, after),
        source_log_id=row.source_log_id,
        capture_seq=row.capture_seq,
    )
