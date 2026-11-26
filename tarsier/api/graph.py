"""Relationship-graph routes (PRD 14.1). Read-only views over Tarsier's own derived graph."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from tarsier.graph import engine

router = APIRouter(prefix="/api/graph")


def _guard():
    if not engine.is_available():
        raise HTTPException(status_code=503, detail=asdict(engine.graph_status())["message"])


@router.get("/status")
def get_status():
    return asdict(engine.graph_status())


@router.post("/rebuild")
def rebuild():
    _guard()
    return asdict(engine.rebuild_graph())


@router.get("/overview")
def get_overview(confirmed_only: bool = False):
    _guard()
    return engine.overview(confirmed_only)


@router.get("/neighborhood")
def get_neighborhood(connection_id: str, name: str, schema: str = "", hops: int = 2, confirmed_only: bool = False):
    _guard()
    return engine.neighborhood(engine.item_key(connection_id, schema, name), hops, confirmed_only)


@router.get("/neighbors")
def get_neighbors(connection_id: str, name: str, schema: str = "", hops: int = 2, confirmed_only: bool = False):
    _guard()
    key = engine.item_key(connection_id, schema, name)
    return {"key": key, "hops": hops, "items": engine.neighbors(key, hops, confirmed_only)}


@router.get("/path")
def get_path(
    from_connection_id: str, from_name: str, to_connection_id: str, to_name: str,
    from_schema: str = "", to_schema: str = "", confirmed_only: bool = False,
):
    _guard()
    result = engine.shortest_path(
        engine.item_key(from_connection_id, from_schema, from_name),
        engine.item_key(to_connection_id, to_schema, to_name),
        confirmed_only,
    )
    return {"connected": result is not None, "path": result}
