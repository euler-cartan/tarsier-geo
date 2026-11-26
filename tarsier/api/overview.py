"""Routes behind the Overview page (PRD §7.1, FSD §6) and the per-item
Detail page (PRD §7.9, FSD §7).
"""

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from tarsier import overview as overview_module
from tarsier.ai.client import AIError, AINotConfiguredError
from tarsier.ai.query import interpret_question, run_filter, schema_from_frame
from tarsier.connectors.base import ConnectorError
from tarsier.raster import scan as raster_scan
from tarsier.stats import scan as stats_scan
from tarsier.storage import connections as storage
from tarsier.storage import item_cache, preview_cache, raster_cache, stats_cache

router = APIRouter(prefix="/api/connections/{connection_id}")


def _require_connection(connection_id: str):
    saved = storage.get_connection(connection_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="No such connection.")
    return saved


@router.post("/scan", status_code=202)
def scan(connection_id: str):
    _require_connection(connection_id)
    try:
        overview_module.scan_connection(connection_id)
    except ConnectorError as exc:
        storage.record_check_result(connection_id, "error")
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}


@router.get("/overview")
def get_overview(connection_id: str):
    _require_connection(connection_id)
    summary = overview_module.get_overview(connection_id)
    return asdict(summary)


@router.post("/checks", status_code=202)
def start_full_check(connection_id: str, mode: Literal["full"] = "full"):
    _require_connection(connection_id)
    from tarsier.checks import start
    return start(connection_id,mode=mode)


@router.get("/checks")
def full_check_status(connection_id: str):
    _require_connection(connection_id)
    from tarsier.checks import status
    return status(connection_id)


@router.get("/item")
def get_item(connection_id: str, schema: str = "", name: str = ""):
    _require_connection(connection_id)
    cached = item_cache.get_item(connection_id, schema, name)
    if cached is None:
        raise HTTPException(status_code=404, detail="This item hasn't been scanned yet.")
    return {**asdict(cached), **overview_module.get_item_health(connection_id, schema, name)}


@router.get("/item/map")
def get_item_map(connection_id: str, schema: str = "", name: str = ""):
    _require_connection(connection_id)
    from tarsier.storage import map_cache
    preview = map_cache.get(connection_id, schema, name)
    if preview is None:
        raise HTTPException(404, "Map geometry has not been loaded yet.")
    return preview


@router.post("/item/map/scan")
def scan_item_map(connection_id: str, schema: str = "", name: str = ""):
    _require_connection(connection_id)
    import json
    from tarsier.storage import map_cache
    from tarsier.quality.scan import _load_context
    try:
        _, connector, config, _, item = _load_context(connection_id, schema, name)
        if item.kind != "vector" or not hasattr(connector, "sample_geometries"):
            raise ConnectorError("Geometry previews are not available for this source.")
        sample = connector.sample_geometries(config, item, limit=300)
        frame = sample.geodataframe
        if frame.crs is None:
            raise ConnectorError("This layer has no known projection. A map cannot be placed reliably.")
        frame = frame.to_crs(4326)
        frame = frame.loc[frame.geometry.notna() & ~frame.geometry.is_empty]
        # Map geometry only. Attribute values are not needed for this preview.
        result = {"geojson": json.loads(frame[[frame.geometry.name]].to_json()), "bbox": frame.total_bounds.tolist() if len(frame) else None, "is_sample": sample.is_sample, "feature_count": len(frame)}
        map_cache.save(connection_id, schema, name, result)
        return result
    except ConnectorError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, "The map preview could not be read. Check the layer projection and source connection.") from exc


@router.post("/item/stats/scan", status_code=202)
def scan_item_stats(connection_id: str, schema: str = "", name: str = "", full: bool = False):
    _require_connection(connection_id)
    try:
        stats_scan.scan_item_stats(connection_id, schema, name, full=full)
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}


@router.get("/item/stats")
def get_item_stats(connection_id: str, schema: str = "", name: str = ""):
    _require_connection(connection_id)
    stats = stats_cache.get_stats(connection_id, schema, name)
    if stats is None:
        raise HTTPException(status_code=404, detail="Statistics haven't been run for this item yet.")
    return asdict(stats)


@router.post("/item/raster/scan", status_code=202)
def scan_item_raster(connection_id: str, schema: str = "", name: str = "", full: bool = False):
    _require_connection(connection_id)
    try:
        raster_scan.scan_item_raster(connection_id, schema, name, full=full)
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}


@router.get("/item/raster")
def get_item_raster(connection_id: str, schema: str = "", name: str = ""):
    _require_connection(connection_id)
    cached = raster_cache.get_detail(connection_id, schema, name)
    if cached is None:
        raise HTTPException(status_code=404, detail="Raster detail hasn't been read for this item yet.")
    detail, scanned_at = cached
    return {**asdict(detail), "scanned_at": scanned_at}


@router.post("/item/preview/scan", status_code=202)
def scan_item_preview(connection_id: str, schema: str = "", name: str = ""):
    _require_connection(connection_id)
    try:
        stats_scan.scan_item_preview(connection_id, schema, name)
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "ok"}


@router.get("/item/preview")
def get_item_preview(connection_id: str, schema: str = "", name: str = ""):
    _require_connection(connection_id)
    cached = preview_cache.get_preview(connection_id, schema, name)
    if cached is None:
        raise HTTPException(status_code=404, detail="Sample rows haven't been loaded for this item yet.")
    return cached


@router.get("/statistics/summary")
def get_statistics_summary(connection_id: str):
    _require_connection(connection_id)
    cached = item_cache.list_items(connection_id)
    all_stats = stats_cache.get_all_stats(connection_id)
    layers = []
    for item in cached:
        stats = all_stats.get((item.schema, item.name))
        layers.append(
            {
                "schema": item.schema,
                "name": item.name,
                "kind": item.kind,
                "is_scanned": stats is not None,
                "is_sample": stats.is_sample if stats is not None else None,
                "sampled_row_count": stats.sampled_row_count if stats is not None else None,
                "messy_category_count": len(stats.messy_category_rows) if stats is not None else None,
                "duplicate_count": len(stats.duplicate_rows) if stats is not None else None,
                "out_of_range_count": len(stats.out_of_range_rows) if stats is not None else None,
                "map_outlier_count": stats.spatial_outlier_count if stats is not None else None,
                "null_geometry_count": stats.null_geometry_count if stats is not None else None,
            }
        )
    return {
        "connection_id": connection_id,
        "layers": layers,
    }


class AiQueryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    question: str
    item_schema: str = Field(default="", alias="schema")
    name: str = ""


@router.post("/item/ai-query")
def ai_query(connection_id: str, body: AiQueryRequest):
    _require_connection(connection_id)
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Type a question about this data.")
    try:
        sample = stats_scan.load_item_sample(connection_id, body.item_schema, body.name)
        hidden = set(sample.geometry_columns or ())
        if sample.null_geometry_column:
            hidden.add(sample.null_geometry_column)
        spec = interpret_question(body.question, schema_from_frame(sample.dataframe, hidden))
        rows = run_filter(sample.dataframe, spec, sample.geometry_columns, sample.null_geometry_column)
    except AINotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"caption": spec.caption, "rows": rows, "is_sample": sample.is_sample}
