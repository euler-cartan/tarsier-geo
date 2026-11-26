"""Durable at-most-once event claims, local SQLite only."""
from sqlalchemy import func, text
from sqlalchemy.dialects.sqlite import insert
from tarsier.storage.models import ChangeEvent, EventCaptureCursor, EventReceipt


def initialize_upgrade(engine):
    # Claim the migration atomically. Fresh stores have no rules yet, so new
    # rules use a creation checkpoint. Upgrade existing consumers against the
    # cached-event snapshot, without deleting history.
    with engine.begin() as conn:
        if conn.execute(text("INSERT OR IGNORE INTO event_replay_upgrade(version) VALUES(1)")).rowcount == 0:
            return
        for kind, table in (("alert", "alert_rules"), ("automation", "automations")):
            conn.execute(text(f"""
                INSERT OR IGNORE INTO event_receipts(consumer_kind,consumer_id,event_key)
                SELECT :kind,r.id,e.id FROM {table} r
                JOIN change_events e ON e.connection_id=r.connection_id
            """), {"kind":kind})
            conn.execute(text(f"""
                INSERT OR IGNORE INTO event_receipts(consumer_kind,consumer_id,event_key)
                SELECT :kind,r.id,'source/'||e.connection_id||'/'||e.source||'/'||e.source_log_id
                FROM {table} r JOIN change_events e ON e.connection_id=r.connection_id
                WHERE e.source_log_id IS NOT NULL
            """), {"kind":kind})
        # Retain protection for fires whose cached event has since been pruned.
        conn.execute(text("""
            INSERT OR IGNORE INTO event_receipts(consumer_kind,consumer_id,event_key)
            SELECT 'alert',rule_id,json_extract(payload_json,'$.event_id')
            FROM alert_fires WHERE json_valid(payload_json)
            AND json_extract(payload_json,'$.event_id') IS NOT NULL
        """))


def claim(session, kind, consumer_id, event_id):
    event = session.get(ChangeEvent, event_id)
    key = (f"source/{event.connection_id}/{event.source}/{event.source_log_id}"
           if event is not None and event.source_log_id is not None else event_id)
    result = session.execute(insert(EventReceipt).values(consumer_kind=kind,consumer_id=consumer_id,event_key=key).on_conflict_do_nothing())
    if result.rowcount == 0:
        return False
    if key != event_id:
        session.execute(insert(EventReceipt).values(consumer_kind=kind,consumer_id=consumer_id,event_key=event_id).on_conflict_do_nothing())
    return True


def pending(kind, consumer_id, events):
    from tarsier.storage.db import get_session
    with get_session() as session:
        seen = {r[0] for r in session.query(EventReceipt.event_key).filter_by(consumer_kind=kind,consumer_id=consumer_id)}
    return [e for e in events if e.get("id") not in seen]


def claim_events(kind, consumer_id, events):
    from tarsier.storage.db import get_session
    with get_session() as session:
        accepted = [e for e in events if claim(session,kind,consumer_id,e["id"])]
        session.commit()
    return accepted


def creation_checkpoint(session, connection_id):
    """Take a stable local capture and source-log watermark while holding the writer lock."""
    session.execute(text("BEGIN IMMEDIATE"))
    cursor = session.get(EventCaptureCursor, connection_id)
    source_log = session.query(func.max(ChangeEvent.source_log_id)).filter_by(connection_id=connection_id).scalar()
    return (cursor.last_value if cursor else 0), source_log


def after_creation(events, capture_checkpoint, source_log_checkpoint):
    """Legacy consumers have no checkpoint and retain their previous behavior."""
    if capture_checkpoint is None:
        return events
    return [event for event in events
            if event.get("capture_seq") is not None
            and event["capture_seq"] > capture_checkpoint
            and (event.get("source_log_id") is None
                 or source_log_checkpoint is None
                 or event["source_log_id"] > source_log_checkpoint)]
