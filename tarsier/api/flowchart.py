"""Connection relationship graph API (PRD §7.8, FSD §12)."""

from tarsier.timing import timed_run

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tarsier.connectors.base import ConnectorError
from tarsier.flowchart import discover_cross_connection_links, discover_links
from tarsier.storage import connections as connection_storage
from tarsier.storage import item_cache
from tarsier.storage import flowchart as store

router = APIRouter(prefix="/api/connections/{connection_id}/flowchart")


def _require_connection(connection_id: str):
    saved = connection_storage.get_connection(connection_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="No such connection.")
    return saved


def _link_payload(row) -> dict:
    return {
        "id": row.id,
        "source_schema": row.source_schema,
        "source_name": row.source_name,
        "source_column": row.source_column,
        "target_schema": row.target_schema,
        "target_name": row.target_name,
        "target_column": row.target_column,
        "kind": row.kind,
        "status": row.status,
        "sample_based": row.sample_based,
        "source_connection_id": row.connection_id,
        "target_connection_id": row.peer_connection_id or row.connection_id,
    }


def _graph(connection_id: str) -> dict:
    links = [_link_payload(row) for row in store.list_links(connection_id) if row.status != "rejected"]
    # Items in other connections that this connection's cross-connection links point at.
    wanted = {
        (link[f"{side}_connection_id"], link[f"{side}_schema"], link[f"{side}_name"])
        for link in links
        for side in ("source", "target")
        if link[f"{side}_connection_id"] != connection_id
    }
    names = {c.id: c.name for c in connection_storage.list_connections()}
    external = []
    found = set()
    for other_id in {w[0] for w in wanted}:
        for node in store.list_nodes(other_id):
            if (other_id, node["schema"], node["name"]) in wanted:
                found.add((other_id, node["schema"], node["name"]))
                external.append({**node, "connection_id": other_id, "connection_name": names.get(other_id, other_id)})
    # The other connection may not have had its own flowchart scan yet: describe the item from the cache.
    for other_id, schema, name in wanted - found:
        cached = item_cache.get_item(other_id, schema, name)
        external.append({
            "schema": schema, "name": name, "kind": cached.kind if cached else "tabular", "columns": [],
            "connection_id": other_id, "connection_name": names.get(other_id, other_id),
        })
    return {"nodes": store.list_nodes(connection_id), "external_nodes": external, "links": links}


@router.get("")
def get_flowchart(connection_id: str):
    _require_connection(connection_id)
    return _graph(connection_id)


@router.post("/scan")
@timed_run("link_guessing")
def scan_flowchart(connection_id: str):
    _require_connection(connection_id)
    try:
        nodes, links = discover_links(connection_id)
        store.replace_discovered(connection_id, nodes, links)
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="No such connection.") from exc
    refresh_graph()
    result = _graph(connection_id)
    result.update(_scan_outcome(links, connection_id))
    return result


class AddLinkRequest(BaseModel):
    source_schema: str = ""
    source_name: str
    source_column: str
    target_schema: str = ""
    target_name: str
    target_column: str


@router.post("/links", status_code=201)
def add_link(connection_id: str, body: AddLinkRequest):
    _require_connection(connection_id)
    nodes = store.list_nodes(connection_id)
    by_item = {(node["schema"], node["name"]): node for node in nodes}
    source = by_item.get((body.source_schema, body.source_name))
    target = by_item.get((body.target_schema, body.target_name))
    if source is None or target is None or source is target:
        raise HTTPException(status_code=400, detail="Choose two different items from the latest flowchart scan.")
    if body.source_column not in source["columns"] or body.target_column not in target["columns"]:
        raise HTTPException(status_code=400, detail="Choose columns available from the latest flowchart scan.")
    row = store.add_user_link(connection_id, body.model_dump())
    refresh_graph()
    return _link_payload(row)


@router.post("/links/{link_id}/confirm")
def confirm_link(connection_id: str, link_id: str):
    _require_connection(connection_id)
    row = store.update_status(connection_id, link_id, "confirmed")
    if row is None:
        raise HTTPException(status_code=404, detail="No pending guessed link with that ID.")
    refresh_graph()
    return _link_payload(row)


@router.post("/links/{link_id}/reject")
def reject_link(connection_id: str, link_id: str):
    _require_connection(connection_id)
    row = store.update_status(connection_id, link_id, "rejected")
    if row is None:
        raise HTTPException(status_code=404, detail="No pending guessed link with that ID.")
    refresh_graph()
    return {"status": "rejected", "id": row.id}


cross_router = APIRouter(prefix="/api/flowchart")


@cross_router.post("/cross/scan")
@timed_run("cross_link_guessing")
def scan_cross_connection_links():
    """PRD 14.10: guess links between items of different connections (same rule as within one)."""
    links, skipped = discover_cross_connection_links()
    store.replace_cross_discovered(links)
    refresh_graph()
    return {"guesses": len(links), "skipped_connections": skipped, **_scan_outcome(links, "cross")}


def refresh_graph() -> None:
    from tarsier.graph.engine import refresh_quietly

    refresh_quietly()


def _scan_outcome(links, scope):
    count = getattr(links, "could_not_verify", 0)
    message = f"Could not verify {count} candidates. No conclusion about those links was made." if count else "Link scan complete; 0 candidates could not verify."
    store.save_scan_outcome(scope, count, message)
    return {"could_not_verify": count, "message": message}
