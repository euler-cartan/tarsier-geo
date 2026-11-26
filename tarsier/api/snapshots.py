from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from tarsier import snapshots
from tarsier.ai.client import AIError, AINotConfiguredError
from tarsier.stats.filter import FilterError
from tarsier.storage import connections

router = APIRouter(prefix="/api/connections/{connection_id}/snapshots")

def require(connection_id):
    saved = connections.get_connection(connection_id)
    if saved is None:
        raise HTTPException(404, "No such connection.")
    return saved

@router.get("")
def listing(connection_id: str):
    saved = require(connection_id)
    return {"available": saved.type in snapshots.DATABASE_TYPES, "versions": snapshots.versions(connection_id), "interval_days": 2, "retention_days": 90}

@router.post("/capture")
def capture(connection_id: str):
    require(connection_id)
    try:
        return snapshots.capture(connection_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

class Query(BaseModel):
    question: str = ""
    filter_payload: dict | None = None
    bbox: list[float] | None = None
    limit: int = Field(default=200, ge=1, le=1000)

@router.post("/{version_id}/plan")
def plan(connection_id: str, version_id: str, body: Query):
    require(connection_id)
    try:
        return snapshots.plan_query(connection_id, version_id, body.question)
    except (ValueError, FilterError, AIError, AINotConfiguredError) as exc:
        raise HTTPException(400, str(exc)) from exc

@router.post("/{version_id}/query")
def query(connection_id: str, version_id: str, body: Query):
    require(connection_id)
    try:
        return snapshots.query(connection_id, version_id, **body.model_dump())
    except (ValueError, FilterError, AIError, AINotConfiguredError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, "Could not query this snapshot. Check the filter and snapshot availability.") from exc

@router.get("/compare")
def compare(connection_id: str, before: str, after: str):
    require(connection_id)
    try:
        return snapshots.compare(connection_id, before, after)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
