"""Read/write the per-raster detail cache (TAD §8)  -  written by a raster
scan, read by the raster Overview tab. Never recomputed on page load.
"""

from tarsier.timing import timed_phase
import dataclasses
import json
from datetime import datetime, timezone

from tarsier.raster.analyze import BandStats, HistogramBin, RasterDetail
from tarsier.storage.db import get_session
from tarsier.storage.models import RasterDetailCache


@timed_phase("cache_write")
def save_detail(connection_id: str, schema: str, name: str, detail: RasterDetail) -> None:
    with get_session() as session:
        record = session.get(RasterDetailCache, (connection_id, schema, name))
        if record is None:
            record = RasterDetailCache(connection_id=connection_id, schema=schema, name=name)
            session.add(record)
        record.detail_json = json.dumps(dataclasses.asdict(detail))
        record.scanned_at = datetime.now(timezone.utc)
        session.commit()


def get_detail(connection_id: str, schema: str, name: str) -> tuple[RasterDetail, datetime] | None:
    with get_session() as session:
        record = session.get(RasterDetailCache, (connection_id, schema, name))
        if record is None:
            return None
        payload = json.loads(record.detail_json)
        payload["bands"] = [
            BandStats(**{**band, "histogram": [HistogramBin(**b) for b in band.get("histogram", [])]})
            for band in payload.get("bands", [])
        ]
        if payload.get("footprint") is not None:
            payload["footprint"] = tuple(payload["footprint"])
        return RasterDetail(**payload), record.scanned_at


def delete_all_for_connection(connection_id: str) -> None:
    with get_session() as session:
        session.query(RasterDetailCache).filter(RasterDetailCache.connection_id == connection_id).delete()
        session.commit()
