"""CRUD for alert rules, fires, and evaluation snapshots."""

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.sqlite import insert

from tarsier.storage import webhook_vault
from tarsier.storage.db import get_session
from tarsier.storage.models import AlertFire, AlertRule, AlertSnapshot


def list_rules(connection_id: str) -> list[dict]:
    with get_session() as session:
        rows = session.query(AlertRule).filter_by(connection_id=connection_id).all()
        return [_rule(row) for row in rows]


def get_rule(rule_id: str) -> dict | None:
    with get_session() as session:
        row = session.get(AlertRule, rule_id)
        return _rule(row) if row else None


def create_rule(connection_id: str, body: dict) -> dict:
    with get_session() as session:
        from tarsier.storage.event_receipts import creation_checkpoint
        capture_checkpoint, source_log_checkpoint = creation_checkpoint(session, connection_id)
        row = AlertRule(
            id=str(uuid.uuid4()),
            connection_id=connection_id,
            kind=body["kind"],
            title=body.get("title") or body["kind"],
            target_schema=body.get("target_schema") or "",
            target_name=body.get("target_name") or "",
            config_json=json.dumps(webhook_vault.protect_config(body.get("config"))),
            paused=bool(body.get("paused", False)),
            event_checkpoint=capture_checkpoint,
            source_log_checkpoint=source_log_checkpoint,
        )
        session.add(row)
        session.commit()
        return _rule(row)


def update_rule(rule_id: str, body: dict) -> dict | None:
    with get_session() as session:
        row = session.get(AlertRule, rule_id)
        if row is None:
            return None
        if "kind" in body:
            row.kind = body["kind"]
        if "title" in body:
            row.title = body["title"]
        if "target_schema" in body:
            row.target_schema = body["target_schema"] or ""
        if "target_name" in body:
            row.target_name = body["target_name"] or ""
        if "config" in body:
            row.config_json = json.dumps(
                webhook_vault.protect_config(body["config"], json.loads(row.config_json or "{}"))
            )
        if "paused" in body:
            row.paused = bool(body["paused"])
        session.commit()
        return _rule(row)


def delete_rule(rule_id: str) -> bool:
    with get_session() as session:
        row = session.get(AlertRule, rule_id)
        if row is None:
            return False
        session.query(AlertFire).filter_by(rule_id=rule_id).delete()
        webhook_vault.purge_config(json.loads(row.config_json or "{}"))
        session.delete(row)
        session.commit()
        return True


def record_fire(rule_id: str, connection_id: str, message: str, payload: dict, channel: str) -> dict | None:
    with get_session() as session:
        event_id = payload.get("event_id")
        if event_id:
            from tarsier.storage.event_receipts import claim
            if not claim(session, "alert", rule_id, event_id):
                return None
        fire = AlertFire(
            id=str(uuid.uuid4()),
            rule_id=rule_id,
            connection_id=connection_id,
            fired_at=datetime.now(timezone.utc),
            message=message,
            payload_json=json.dumps(payload),
            channel=channel,
            delivery_status="pending" if event_id else "logged",
        )
        session.add(fire)
        rule = session.get(AlertRule, rule_id)
        if rule is not None:
            rule.last_triggered_at = fire.fired_at
            rule.last_message = message
        session.commit()
        return {
            "id": fire.id,
            "rule_id": rule_id,
            "fired_at": fire.fired_at.isoformat(),
            "message": message,
            "channel": channel,
            "delivery_status": fire.delivery_status or "logged",
            "delivery_message": fire.delivery_message,
        }


def update_fire_delivery(fire_id: str, status: str, message: str) -> None:
    with get_session() as session:
        fire = session.get(AlertFire, fire_id)
        if fire is None:
            return
        fire.delivery_status = status
        fire.delivery_message = message
        session.commit()


def fired_since(rule_id: str, message: str, since: datetime) -> bool:
    """Has this rule already raised this exact message since `since`?"""
    with get_session() as session:
        return (
            session.query(AlertFire.id)
            .filter(AlertFire.rule_id == rule_id, AlertFire.message == message, AlertFire.fired_at >= since)
            .first()
            is not None
        )


def list_fires(connection_id: str, rule_id: str | None = None, limit: int = 500) -> list[dict]:
    with get_session() as session:
        query = session.query(AlertFire).filter_by(connection_id=connection_id)
        if rule_id:
            query = query.filter_by(rule_id=rule_id)
        rows = query.order_by(AlertFire.fired_at.desc()).limit(limit).all()
        return [
            {
                "id": row.id,
                "rule_id": row.rule_id,
                "fired_at": row.fired_at.isoformat(),
                "message": row.message + (" (sample-based; not a full check)" if json.loads(row.payload_json or "{}").get("is_sample") and "sample-based" not in row.message else ""),
                "channel": row.channel,
                "delivery_status": row.delivery_status or "logged",
                "delivery_message": row.delivery_message,
                "payload": json.loads(row.payload_json or "{}"),
            }
            for row in rows
        ]


def get_snapshot(connection_id: str) -> dict | None:
    with get_session() as session:
        row = session.get(AlertSnapshot, connection_id)
        if row is None:
            return None
        return json.loads(row.snapshot_json)


def save_snapshot(connection_id: str, payload: dict) -> None:
    # One statement handles both first creation and concurrent replacement.
    # Items carry datetime scan times, which must remain serializable.
    snapshot_json = json.dumps(payload, default=lambda o: o.isoformat() if hasattr(o, "isoformat") else str(o))
    statement = insert(AlertSnapshot).values(
        connection_id=connection_id,
        snapshot_json=snapshot_json,
        taken_at=datetime.now(timezone.utc),
    )
    statement = statement.on_conflict_do_update(
        index_elements=[AlertSnapshot.connection_id],
        set_={"snapshot_json": statement.excluded.snapshot_json,
              "taken_at": statement.excluded.taken_at},
    )
    with get_session() as session:
        session.execute(statement)
        session.commit()


def delete_all_for_connection(connection_id: str) -> None:
    with get_session() as session:
        session.query(AlertFire).filter_by(connection_id=connection_id).delete()
        for row in session.query(AlertRule).filter_by(connection_id=connection_id).all():
            webhook_vault.purge_config(json.loads(row.config_json or "{}"))
        session.query(AlertRule).filter_by(connection_id=connection_id).delete()
        session.query(AlertSnapshot).filter_by(connection_id=connection_id).delete()
        session.commit()


def _rule(row: AlertRule) -> dict:
    return {
        "id": row.id,
        "connection_id": row.connection_id,
        "kind": row.kind,
        "title": row.title,
        "target_schema": row.target_schema,
        "target_name": row.target_name,
        "config": json.loads(row.config_json or "{}"),
        "paused": row.paused,
        "last_triggered_at": row.last_triggered_at.isoformat() if row.last_triggered_at else None,
        "last_message": row.last_message,
        "status": "paused" if row.paused else "active",
        "event_checkpoint": row.event_checkpoint,
        "source_log_checkpoint": row.source_log_checkpoint,
    }
