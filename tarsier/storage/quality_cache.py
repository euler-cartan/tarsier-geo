"""Read/write per-check quality results, rules, and boundary settings."""

from tarsier.timing import timed_phase
import dataclasses
import json
import uuid
from datetime import datetime, timezone

from tarsier.quality.engine import CheckResult
from tarsier.storage.db import get_session
from tarsier.storage.models import QualityCheckCache, QualityRule, QualitySettings


@timed_phase("cache_write")
def save_check(connection_id: str, schema: str, name: str, result: CheckResult) -> None:
    with get_session() as session:
        record = session.get(QualityCheckCache, (connection_id, schema, name, result.check_id))
        if record is None:
            record = QualityCheckCache(
                connection_id=connection_id, schema=schema, name=name, check_id=result.check_id
            )
            session.add(record)
        record.result_json = json.dumps(dataclasses.asdict(result))
        record.scanned_at = datetime.now(timezone.utc)
        session.commit()


def get_checks(connection_id: str, schema: str, name: str) -> dict[str, CheckResult]:
    with get_session() as session:
        rows = (
            session.query(QualityCheckCache)
            .filter_by(connection_id=connection_id, schema=schema, name=name)
            .all()
        )
        return {row.check_id: CheckResult(**json.loads(row.result_json)) for row in rows}


def get_all_checks(connection_id: str) -> dict[tuple[str, str], dict[str, CheckResult]]:
    with get_session() as session:
        rows = session.query(QualityCheckCache).filter_by(connection_id=connection_id).all()
        grouped: dict[tuple[str, str], dict[str, CheckResult]] = {}
        for row in rows:
            grouped.setdefault((row.schema, row.name), {})[row.check_id] = CheckResult(
                **json.loads(row.result_json)
            )
        return grouped


def get_settings(connection_id: str, schema: str, name: str) -> QualitySettings | None:
    with get_session() as session:
        return session.get(QualitySettings, (connection_id, schema, name))


def set_boundary(
    connection_id: str, schema: str, name: str, boundary_schema: str | None, boundary_name: str | None
) -> None:
    with get_session() as session:
        record = session.get(QualitySettings, (connection_id, schema, name))
        if record is None:
            record = QualitySettings(connection_id=connection_id, schema=schema, name=name)
            session.add(record)
        record.boundary_schema = boundary_schema
        record.boundary_name = boundary_name
        session.commit()


def list_rules(connection_id: str, schema: str, name: str) -> list[dict]:
    with get_session() as session:
        rows = (
            session.query(QualityRule)
            .filter_by(connection_id=connection_id, schema=schema, name=name)
            .all()
        )
        return [_rule_dict(row) for row in rows]


def create_rule(connection_id: str, schema: str, name: str, body: dict) -> dict:
    rule_id = str(uuid.uuid4())
    with get_session() as session:
        record = QualityRule(
            id=rule_id,
            connection_id=connection_id,
            schema=schema,
            name=name,
            kind=body.get("kind") or "attribute",
            field=body["field"],
            operator=body.get("operator") or "eq",
            value=body.get("value"),
            geometry_type=body.get("geometry_type"),
        )
        session.add(record)
        session.commit()
        return _rule_dict(record)


def update_rule(rule_id: str, body: dict) -> dict | None:
    with get_session() as session:
        record = session.get(QualityRule, rule_id)
        if record is None:
            return None
        if "kind" in body:
            record.kind = body["kind"]
        if "field" in body:
            record.field = body["field"]
        if "operator" in body:
            record.operator = body["operator"]
        if "value" in body:
            record.value = body["value"]
        if "geometry_type" in body:
            record.geometry_type = body["geometry_type"]
        session.commit()
        return _rule_dict(record)


def delete_rule(rule_id: str) -> bool:
    with get_session() as session:
        record = session.get(QualityRule, rule_id)
        if record is None:
            return False
        session.delete(record)
        session.commit()
        return True


def get_rule(rule_id: str) -> QualityRule | None:
    with get_session() as session:
        return session.get(QualityRule, rule_id)


def delete_all_for_connection(connection_id: str) -> None:
    with get_session() as session:
        session.query(QualityCheckCache).filter(QualityCheckCache.connection_id == connection_id).delete()
        session.query(QualityRule).filter(QualityRule.connection_id == connection_id).delete()
        session.query(QualitySettings).filter(QualitySettings.connection_id == connection_id).delete()
        session.commit()


def _rule_dict(record: QualityRule) -> dict:
    return {
        "id": record.id,
        "kind": record.kind,
        "field": record.field,
        "operator": record.operator,
        "value": record.value,
        "geometry_type": record.geometry_type,
    }
