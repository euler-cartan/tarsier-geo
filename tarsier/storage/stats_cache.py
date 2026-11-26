"""Read/write the per-item statistics cache (TAD §8)  -  computed by a scan,
read by the Statistics tab. Never recomputed on page load.
"""

from tarsier.timing import timed_phase
import dataclasses
import json
from datetime import datetime, timezone
from sqlalchemy import func

from tarsier.connectors.base import ConnectorError
from tarsier.stats.engine import ColumnStats, TableStats
from tarsier.storage.db import get_session
from tarsier.storage.models import StatsCache

MAX_STATS_CACHE_BYTES = 64 * 1024 * 1024


@timed_phase("cache_write")
def save_stats(connection_id: str, schema: str, name: str, stats: TableStats) -> None:
    payload = json.dumps(dataclasses.asdict(stats))
    if len(payload.encode("utf-8")) > MAX_STATS_CACHE_BYTES:
        raise ConnectorError("The statistics result exceeds 64 MiB. Run a sample check instead.")
    with get_session() as session:
        record = session.get(StatsCache, (connection_id, schema, name))
        if record is None:
            record = StatsCache(connection_id=connection_id, schema=schema, name=name)
            session.add(record)
        record.stats_json = payload
        record.scanned_at = datetime.now(timezone.utc)
        session.commit()


def get_stats(connection_id: str, schema: str, name: str) -> TableStats | None:
    with get_session() as session:
        size = session.query(func.length(StatsCache.stats_json)).filter_by(
            connection_id=connection_id, schema=schema, name=name
        ).scalar()
        if size is None or size > MAX_STATS_CACHE_BYTES:
            return None
        record = session.get(StatsCache, (connection_id, schema, name))
        if record is None:
            return None
        return _stats_from_payload(json.loads(record.stats_json))


def get_all_stats(connection_id: str) -> dict[tuple[str, str], TableStats]:
    with get_session() as session:
        rows = session.query(StatsCache).filter_by(connection_id=connection_id).filter(
            func.length(StatsCache.stats_json) <= MAX_STATS_CACHE_BYTES
        ).all()
        return {
            (row.schema, row.name): _stats_from_payload(json.loads(row.stats_json))
            for row in rows
        }


def _stats_from_payload(payload: dict) -> TableStats:
    payload["columns"] = [_column_from_payload(c) for c in payload["columns"]]
    for key in (
        "messy_category_rows",
        "out_of_range_rows",
        "duplicate_rows",
        "map_outlier_rows",
        "null_geometry_rows",
    ):
        payload.setdefault(key, [])
    return TableStats(**payload)


def _column_from_payload(payload: dict) -> ColumnStats:
    data = dict(payload)
    data.setdefault("histogram", None)
    top = data.get("top_values") or []
    data["top_values"] = [tuple(item) for item in top]
    return ColumnStats(**data)


def delete_all_for_connection(connection_id: str) -> None:
    with get_session() as session:
        session.query(StatsCache).filter(StatsCache.connection_id == connection_id).delete()
        session.commit()
