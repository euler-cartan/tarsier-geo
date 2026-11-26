"""Connection-scoped relationship storage for the flowchart."""

from tarsier.timing import timed_phase
import json
import uuid

from sqlalchemy import or_

from tarsier.storage.db import get_session
from tarsier.storage.models import FlowchartLink, FlowchartNode


def list_links(connection_id: str) -> list[FlowchartLink]:
    with get_session() as session:
        # Own links, plus cross-connection guesses another connection made
        # about this one (PRD 14.10) - they show on both sides.
        return (
            session.query(FlowchartLink)
            .filter(or_(FlowchartLink.connection_id == connection_id, FlowchartLink.peer_connection_id == connection_id))
            .order_by(FlowchartLink.source_name, FlowchartLink.target_name)
            .all()
        )


def list_all_links() -> list[FlowchartLink]:
    with get_session() as session:
        return session.query(FlowchartLink).all()


def list_all_nodes() -> list[tuple[str, dict]]:
    with get_session() as session:
        return [
            (row.connection_id, {"schema": row.schema, "name": row.name, "kind": row.kind, "columns": json.loads(row.columns_json)})
            for row in session.query(FlowchartNode).all()
        ]


@timed_phase("cache_write")
def replace_cross_discovered(links: list[dict]) -> None:
    """Replace unresolved cross-connection guesses; keep any the user confirmed or rejected."""
    keys = ("source_connection_id", "source_schema", "source_name", "source_column",
            "target_connection_id", "target_schema", "target_name", "target_column")
    with get_session() as session:
        existing = session.query(FlowchartLink).filter(FlowchartLink.peer_connection_id.isnot(None)).all()
        settled = {
            (r.connection_id, r.source_schema, r.source_name, r.source_column,
             r.peer_connection_id, r.target_schema, r.target_name, r.target_column)
            for r in existing if r.status in {"confirmed", "rejected"}
        }
        for row in existing:
            if row.status == "guessed":
                session.delete(row)
        for link in links:
            if tuple(link[k] for k in keys) in settled:
                continue
            session.add(FlowchartLink(
                id=str(uuid.uuid4()),
                connection_id=link["source_connection_id"], peer_connection_id=link["target_connection_id"],
                source_schema=link["source_schema"], source_name=link["source_name"], source_column=link["source_column"],
                target_schema=link["target_schema"], target_name=link["target_name"], target_column=link["target_column"],
                kind="guessed", status="guessed", sample_based=link["sample_based"],
            ))
        session.commit()


@timed_phase("cache_write")
def replace_discovered(connection_id: str, nodes: list[dict], links: list[dict]) -> None:
    with get_session() as session:
        local = FlowchartLink.peer_connection_id.is_(None)  # cross-connection rows are managed separately
        existing = session.query(FlowchartLink).filter(FlowchartLink.connection_id == connection_id, local).all()
        node_keys = {(node["schema"], node["name"]) for node in nodes}
        existing = [
            row for row in existing
            if (row.source_schema, row.source_name) in node_keys and (row.target_schema, row.target_name) in node_keys
        ]
        for row in session.query(FlowchartLink).filter(FlowchartLink.connection_id == connection_id, local).all():
            if row not in existing:
                session.delete(row)
        settled = {
            (row.source_schema, row.source_name, row.source_column, row.target_schema, row.target_name, row.target_column)
            for row in existing if row.kind == "guessed" and row.status in {"confirmed", "rejected"}
        }
        session.query(FlowchartLink).filter(
            FlowchartLink.connection_id == connection_id,
            local,
            (FlowchartLink.kind == "official") | ((FlowchartLink.kind == "guessed") & (FlowchartLink.status == "guessed")),
        ).delete(synchronize_session=False)
        session.query(FlowchartNode).filter_by(connection_id=connection_id).delete(synchronize_session=False)
        for node in nodes:
            session.add(FlowchartNode(
                connection_id=connection_id,
                schema=node["schema"], name=node["name"], kind=node["kind"],
                columns_json=json.dumps(node["columns"]),
            ))
        for link in links:
            key = tuple(link.get(name, "") for name in (
                "source_schema", "source_name", "source_column", "target_schema", "target_name", "target_column"
            ))
            if link["kind"] == "guessed" and key in settled:
                continue
            session.add(FlowchartLink(id=str(uuid.uuid4()), connection_id=connection_id, **link))
        session.commit()


def list_nodes(connection_id: str) -> list[dict]:
    with get_session() as session:
        rows = session.query(FlowchartNode).filter_by(connection_id=connection_id).order_by(
            FlowchartNode.schema, FlowchartNode.name
        ).all()
        return [{"schema": row.schema, "name": row.name, "kind": row.kind,
                 "columns": json.loads(row.columns_json)} for row in rows]


def count_links(connection_id: str) -> int:
    with get_session() as session:
        return session.query(FlowchartLink).filter(
            FlowchartLink.connection_id == connection_id,
            FlowchartLink.status != "rejected",
        ).count()


def add_user_link(connection_id: str, link: dict) -> FlowchartLink:
    row = FlowchartLink(
        id=str(uuid.uuid4()), connection_id=connection_id, kind="user", status="confirmed",
        sample_based=False, **link,
    )
    with get_session() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def update_status(connection_id: str, link_id: str, status: str) -> FlowchartLink | None:
    with get_session() as session:
        row = session.query(FlowchartLink).filter(
            FlowchartLink.id == link_id,
            or_(FlowchartLink.connection_id == connection_id, FlowchartLink.peer_connection_id == connection_id),
        ).first()
        if row is None or row.kind != "guessed" or row.status != "guessed":
            return None
        row.status = status
        session.commit()
        session.refresh(row)
        return row


def delete_all_for_connection(connection_id: str) -> None:
    with get_session() as session:
        session.query(FlowchartLink).filter(
            or_(FlowchartLink.connection_id == connection_id, FlowchartLink.peer_connection_id == connection_id)
        ).delete(synchronize_session=False)
        session.query(FlowchartNode).filter_by(connection_id=connection_id).delete()
        session.commit()


@timed_phase("cache_write")
def save_scan_outcome(scope, count, message):
    from tarsier.storage.models import FlowchartScanOutcome
    with get_session() as session:
        session.merge(FlowchartScanOutcome(scope=scope, could_not_verify=count, message=message))
        session.commit()


def get_scan_outcome(scope):
    from tarsier.storage.models import FlowchartScanOutcome
    with get_session() as session:
        row = session.get(FlowchartScanOutcome, scope)
        return {"could_not_verify": row.could_not_verify, "message": row.message} if row else None
