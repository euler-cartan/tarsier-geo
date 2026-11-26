"""CRUD for automation graphs and run history."""

import json
import uuid
from datetime import datetime, timezone

from tarsier.storage import webhook_vault
from tarsier.storage.db import get_session
from tarsier.storage.models import Automation, AutomationRun


def list_automations(connection_id: str) -> list[dict]:
    with get_session() as session:
        rows = session.query(Automation).filter_by(connection_id=connection_id).all()
        return [_auto(row) for row in rows]


def get_automation(automation_id: str) -> dict | None:
    with get_session() as session:
        row = session.get(Automation, automation_id)
        return _auto(row) if row else None


def create_automation(connection_id: str, body: dict) -> dict:
    with get_session() as session:
        from tarsier.storage.event_receipts import creation_checkpoint
        capture_checkpoint, source_log_checkpoint = creation_checkpoint(session, connection_id)
        row = Automation(
            id=str(uuid.uuid4()),
            connection_id=connection_id,
            title=body.get("title") or "Untitled automation",
            graph_json=json.dumps(webhook_vault.protect_graph(body.get("graph") or {"nodes": [], "edges": []})),
            paused=bool(body.get("paused", False)),
            event_checkpoint=capture_checkpoint,
            source_log_checkpoint=source_log_checkpoint,
        )
        session.add(row)
        session.commit()
        return _auto(row)


def update_automation(automation_id: str, body: dict) -> dict | None:
    with get_session() as session:
        row = session.get(Automation, automation_id)
        if row is None:
            return None
        if "title" in body:
            row.title = body["title"]
        if "graph" in body:
            row.graph_json = json.dumps(
                webhook_vault.protect_graph(body["graph"] or {"nodes": [], "edges": []}, json.loads(row.graph_json or "{}"))
            )
        if "paused" in body:
            row.paused = bool(body["paused"])
        session.commit()
        return _auto(row)


def delete_automation(automation_id: str) -> bool:
    with get_session() as session:
        row = session.get(Automation, automation_id)
        if row is None:
            return False
        session.query(AutomationRun).filter_by(automation_id=automation_id).delete()
        webhook_vault.purge_graph(json.loads(row.graph_json or "{}"))
        session.delete(row)
        session.commit()
        return True


def record_run(
    automation_id: str,
    connection_id: str,
    *,
    dry_run: bool,
    ok: bool,
    message: str,
    trace: list,
) -> dict:
    with get_session() as session:
        row = AutomationRun(
            id=str(uuid.uuid4()),
            automation_id=automation_id,
            connection_id=connection_id,
            ran_at=datetime.now(timezone.utc),
            dry_run=dry_run,
            ok=ok,
            message=message,
            trace_json=json.dumps(trace),
        )
        session.add(row)
        auto = session.get(Automation, automation_id)
        if auto is not None and not dry_run:
            auto.last_run_at = row.ran_at
        session.commit()
        return _run(row)


def list_runs(connection_id: str, limit: int = 20) -> list[dict]:
    with get_session() as session:
        rows = (
            session.query(AutomationRun)
            .filter_by(connection_id=connection_id)
            .order_by(AutomationRun.ran_at.desc())
            .limit(limit)
            .all()
        )
        return [_run(row) for row in rows]


def save_snapshot(automation_id: str, snapshot: dict) -> None:
    with get_session() as session:
        row = session.get(Automation, automation_id)
        if row is None:
            return
        row.snapshot_json = json.dumps(snapshot)
        session.commit()


def delete_all_for_connection(connection_id: str) -> None:
    with get_session() as session:
        existing = session.query(Automation).filter_by(connection_id=connection_id).all()
        for row in existing:
            webhook_vault.purge_graph(json.loads(row.graph_json or "{}"))
        ids = [r.id for r in existing]
        if ids:
            session.query(AutomationRun).filter(AutomationRun.automation_id.in_(ids)).delete(synchronize_session=False)
        session.query(Automation).filter_by(connection_id=connection_id).delete()
        session.commit()


def _auto(row: Automation) -> dict:
    return {
        "id": row.id,
        "connection_id": row.connection_id,
        "title": row.title,
        "graph": json.loads(row.graph_json),
        "paused": row.paused,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "snapshot": json.loads(row.snapshot_json) if row.snapshot_json else None,
        "event_checkpoint": row.event_checkpoint,
        "source_log_checkpoint": row.source_log_checkpoint,
    }


def _run(row: AutomationRun) -> dict:
    return {
        "id": row.id,
        "automation_id": row.automation_id,
        "connection_id": row.connection_id,
        "ran_at": row.ran_at.isoformat(),
        "dry_run": row.dry_run,
        "ok": row.ok,
        "message": row.message,
        "trace": json.loads(row.trace_json),
    }
