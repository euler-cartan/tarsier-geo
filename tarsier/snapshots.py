"""Immutable local (Geo)Parquet versions and safe DuckDB analytics (PRD 14.2–4).

Versions are immutable Parquet files, written
through Tarsier's read-only connectors. No generated SQL or extensions execute.
"""
from __future__ import annotations

from tarsier.timing import timed_run, timed_phase
import json
import re
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pandas as pd

from tarsier.connectors.base import ConnectorError
from tarsier.connectors.registry import get_connector
from tarsier.limits import SNAPSHOT_MAX_ROWS
from tarsier.storage import connections, settings
from tarsier.storage.paths import tarsier_home
from tarsier.stats.filter import parse_filter_payload

_lock = threading.Lock()
DATABASE_TYPES = {"postgis", "oracle", "sqlserver"}
# A snapshot holds a whole table in memory while it is written. Tables above
# this many rows are skipped and reported, never half-captured (tarsier.limits).
MAX_ROWS = SNAPSHOT_MAX_ROWS


def root() -> Path:
    path = tarsier_home() / "snapshots"
    path.mkdir(exist_ok=True)
    return path


def versions(connection_id: str) -> list[dict]:
    records = []
    for path in root().glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # one unreadable manifest must not hide every other snapshot
        if not isinstance(record, dict) or record.get("id") != path.stem or not re.fullmatch(r"[0-9a-f]{32}", path.stem):
            raise ValueError("Invalid snapshot manifest.")
        if record.get("connection_id") == connection_id:
            records.append(record)
    return sorted(records, key=lambda r: r["created_at"], reverse=True)


def get_version(connection_id: str, version_id: str) -> dict:
    for version in versions(connection_id):
        if version["id"] == version_id:
            return version
    raise ValueError("Snapshot not found on this connection.")


@timed_run("snapshot")
def capture(connection_id: str) -> dict:
    saved = connections.get_connection(connection_id)
    if saved is None or saved.type not in DATABASE_TYPES:
        raise ValueError("Snapshots are available for database connections only. Files are never versioned.")
    with _lock:
        connector = get_connector(saved.type)
        config = connector.build_config(saved.config, connections.get_connection_password(saved.id))
        results, failures = [], []
        too_large = f"Snapshot exceeds the {MAX_ROWS:,} row capture limit; no partial version was saved."
        from tarsier.storage import item_cache
        known_rows = {(i.schema, i.name): i.row_count for i in item_cache.list_items(connection_id)}
        for item in connector.list_items(config):
            if item.kind == "raster":
                failures.append({"name": item.qualified_name, "message": "Raster snapshot capture is not available."})
                continue
            # Decide from the cached row count where possible, so an oversized
            # table is skipped without reading a single row of it.
            if (known_rows.get((item.schema, item.name)) or 0) > MAX_ROWS:
                failures.append({"name": item.qualified_name, "message": too_large})
                continue
            try:
                if item.kind == "vector":
                    if not hasattr(connector, "sample_geometries"):
                        raise ConnectorError("Geometry reading is unavailable for this connector.")
                    sample = connector.sample_geometries(config, item, limit=MAX_ROWS)
                    frame = sample.geodataframe
                else:
                    sample = connector.sample_rows(config, item, limit=MAX_ROWS)
                    frame = sample.dataframe
                # Do not pass a truncated sample off as a complete version.
                if sample.is_sample:
                    raise ConnectorError(too_large)
                results.append(write_version(connection_id, item.schema, item.name, frame))
            except Exception as exc:
                message = str(exc) if isinstance(exc, ConnectorError) else "Could not capture this item; no complete version was saved."
                failures.append({"name": item.qualified_name, "message": message})
        prune()
        settings._set_value(f"snapshot_attempt:{connection_id}", datetime.now(timezone.utc).isoformat())
        return {"versions": results, "unavailable": failures}


@timed_phase("cache_write")
def write_version(connection_id: str, schema: str, name: str, frame) -> dict:
    """Publish metadata last so interrupted writes never become visible versions."""
    import geopandas as gpd
    version_id = uuid.uuid4().hex
    path = root() / f"{version_id}.parquet"
    temporary = path.with_suffix(".partial")
    is_geo = isinstance(frame, gpd.GeoDataFrame)
    columns = [{"name": str(c), "type": str(frame[c].dtype)} for c in frame.columns]
    previous = next((r for r in versions(connection_id) if r["schema"] == schema and r["name"] == name), None)
    record = {"id": version_id, "connection_id": connection_id, "schema": schema, "name": name,
              "created_at": datetime.now(timezone.utc).isoformat(), "row_count": len(frame),
              "columns": columns, "geospatial": is_geo, "crs": str(frame.crs) if is_geo and frame.crs else None,
              "geometry_column": frame.geometry.name if is_geo else None,
              "schema_changed": bool(previous and previous["columns"] != columns),
              "projection_changed": bool(previous and previous.get("crs") != (str(frame.crs) if is_geo and frame.crs else None))}
    try:
        frame.to_parquet(temporary, index=False)
        temporary.replace(path)
        record["size_bytes"] = path.stat().st_size
        metadata = root() / f"{version_id}.json"
        pending = metadata.with_suffix(".partial-json")
        pending.write_text(json.dumps(record), encoding="utf-8")
        pending.replace(metadata)
    except Exception:
        temporary.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise
    return record


def prune(now: datetime | None = None):
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=90)
    for path in root().glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            expired = datetime.fromisoformat(record["created_at"]) < cutoff
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if expired:
            path.with_suffix(".parquet").unlink(missing_ok=True)
            path.unlink(missing_ok=True)


def capture_due():
    prune()
    for saved in connections.list_connections():
        if saved.type not in DATABASE_TYPES:
            continue
        last = settings._get_value(f"snapshot_attempt:{saved.id}")
        if not last or datetime.now(timezone.utc) - datetime.fromisoformat(last) >= timedelta(days=2):
            try:
                capture(saved.id)
            except Exception:
                # Retry next scheduler tick; errors are not printed with credentials.
                continue


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def query(connection_id: str, version_id: str, *, question: str = "", filter_payload: dict | None = None,
          bbox: list[float] | None = None, limit: int = 200) -> dict:
    record = get_version(connection_id, version_id)
    fields = [c for c in record["columns"] if c["name"] != record.get("geometry_column")]
    spec = None
    if question.strip():
        from tarsier.ai.query import interpret_question
        spec = interpret_question(question, fields)
    elif filter_payload:
        spec = parse_filter_payload(filter_payload, {c["name"] for c in fields})
    values, clauses = [], []
    if spec:
        for condition in spec.conditions:
            column = _quote(condition["column"])
            op = condition["op"]
            if op in ("is_null", "is_not_null"):
                clauses.append(f"{column} IS {'NOT ' if op == 'is_not_null' else ''}NULL")
            else:
                clauses.append(f"{column} {op} ?")
                values.append(condition["value"])
    sql = "SELECT " + ", ".join(_quote(c["name"]) for c in fields) + " FROM snapshot"
    if clauses:
        sql += " WHERE " + f" {spec.combine.upper()} ".join(clauses)
    path = root() / f"{record['id']}.parquet"
    with duckdb.connect(config={"threads": 2, "memory_limit": "512MB", "autoinstall_known_extensions": False, "autoload_known_extensions": False}) as db:
        if bbox is not None:
            import geopandas as gpd
            from shapely.geometry import box
            if not record["geospatial"] or not record["crs"]:
                raise ValueError("Spatial search requires a snapshot with geometry and a known CRS.")
            import math
            if len(bbox) != 4 or not all(math.isfinite(n) for n in bbox) or not (-180 <= bbox[0] <= bbox[2] <= 180 and -90 <= bbox[1] <= bbox[3] <= 90):
                raise ValueError("Bounds must be west, south, east, north in EPSG:4326.")
            geo = gpd.read_parquet(path)
            extent = gpd.GeoSeries([box(*bbox)], crs=4326).to_crs(geo.crs).iloc[0]
            frame = pd.DataFrame(geo.loc[geo.intersects(extent)].drop(columns=geo.geometry.name))
            db.register("snapshot", frame)
        else:
            db.read_parquet(str(path)).create_view("snapshot")
        count = db.execute(f"SELECT count(*) FROM ({sql})", values).fetchone()[0]
        frame = db.execute(sql + " LIMIT ?", values + [max(1, min(limit, 1000))]).fetchdf()
    return {"snapshot": record, "filter": asdict(spec) if spec else None, "sql": sql + " LIMIT ?",
            "params": values + [max(1, min(limit, 1000))], "bbox": bbox, "count": count, "rows": json.loads(frame.to_json(orient="records", date_format="iso", default_handler=str))}


def plan_query(connection_id: str, version_id: str, question: str) -> dict:
    """Interpret once. The user can inspect this exact filter before execution."""
    record = get_version(connection_id, version_id)
    if not question.strip():
        return {"filter": None, "caption": "All rows"}
    from tarsier.ai.query import interpret_question
    fields = [c for c in record["columns"] if c["name"] != record.get("geometry_column")]
    spec = interpret_question(question, fields)
    return {"filter": asdict(spec), "caption": spec.caption}


def compare(connection_id: str, before: str, after: str) -> dict:
    a, b = get_version(connection_id, before), get_version(connection_id, after)
    if (a["schema"], a["name"]) != (b["schema"], b["name"]):
        raise ValueError("Choose two versions of the same item.")
    with duckdb.connect(config={"memory_limit": "512MB", "threads": 2, "autoinstall_known_extensions": False, "autoload_known_extensions": False}) as db:
        db.read_parquet(str(root() / f"{a['id']}.parquet")).create_view("older")
        db.read_parquet(str(root() / f"{b['id']}.parquet")).create_view("newer")
        common = [c["name"] for c in a["columns"] if c in b["columns"]]
        if not common:
            return {"before": a, "after": b, "message": "No compatible columns to compare.", "added": None, "removed": None}
        cols = ", ".join(_quote(c) for c in common)
        added = db.execute(f"SELECT count(*) FROM (SELECT {cols} FROM newer EXCEPT ALL SELECT {cols} FROM older)").fetchone()[0]
        removed = db.execute(f"SELECT count(*) FROM (SELECT {cols} FROM older EXCEPT ALL SELECT {cols} FROM newer)").fetchone()[0]
    return {"before": a, "after": b, "added": added, "removed": removed,
            "compared_columns": common, "message": "Compared shared columns. An edited row counts as one removal and one addition."}
