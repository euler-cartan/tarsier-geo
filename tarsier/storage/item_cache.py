"""Read/write the per-item metadata cache (TAD §8)  -  upserted by a scan,
read by the Overview and detail pages. Never recomputed on page load.
"""

from tarsier.timing import timed_phase
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from tarsier.connectors.base import DataItem, ItemMetadata
from tarsier.storage.db import get_session
from tarsier.storage.models import ItemMetadataCache


@dataclass(frozen=True)
class CachedItem:
    connection_id: str
    schema: str
    name: str
    kind: str
    geometry_type: str | None
    srid: int | None
    path: str | None
    row_count: int | None
    row_count_is_estimate: bool
    row_count_is_capped: bool
    size_bytes: int | None
    has_index: bool | None
    bbox: tuple[float, float, float, float] | None
    last_modified: str | None
    raster_width: int | None
    raster_height: int | None
    raster_band_count: int | None
    raster_dtype: str | None
    raster_nodata: float | None
    scanned_at: datetime

    @classmethod
    def _from_record(cls, record: ItemMetadataCache) -> "CachedItem":
        return cls(
            connection_id=record.connection_id,
            schema=record.schema,
            name=record.name,
            kind=record.kind,
            geometry_type=record.geometry_type,
            srid=record.srid,
            path=record.path,
            row_count=record.row_count,
            row_count_is_estimate=record.row_count_is_estimate,
            row_count_is_capped=bool(record.row_count_is_capped),
            size_bytes=record.size_bytes,
            has_index=record.has_index,
            bbox=tuple(json.loads(record.bbox_json)) if record.bbox_json else None,
            last_modified=record.last_modified,
            raster_width=record.raster_width,
            raster_height=record.raster_height,
            raster_band_count=record.raster_band_count,
            raster_dtype=record.raster_dtype,
            raster_nodata=record.raster_nodata,
            scanned_at=record.scanned_at,
        )


@timed_phase("cache_write")
def upsert_item(connection_id: str, item: DataItem, metadata: ItemMetadata) -> None:
    with get_session() as session:
        record = session.get(ItemMetadataCache, (connection_id, item.schema, item.name))
        if record is None:
            record = ItemMetadataCache(connection_id=connection_id, schema=item.schema, name=item.name)
            session.add(record)

        record.kind = item.kind
        record.geometry_type = item.geometry_type
        record.srid = item.srid
        record.path = item.path
        record.row_count = metadata.row_count
        record.row_count_is_estimate = metadata.row_count_is_estimate
        record.row_count_is_capped = metadata.row_count_is_capped
        record.size_bytes = metadata.size_bytes
        record.has_index = metadata.has_index
        record.bbox_json = json.dumps(list(metadata.bbox)) if metadata.bbox else None
        record.last_modified = metadata.last_modified
        record.raster_width = metadata.raster_width
        record.raster_height = metadata.raster_height
        record.raster_band_count = metadata.raster_band_count
        record.raster_dtype = metadata.raster_dtype
        record.raster_nodata = metadata.raster_nodata
        record.scanned_at = datetime.now(timezone.utc)
        session.commit()


@timed_phase("cache_write")
def remove_items_not_in(connection_id: str, current_keys: set[tuple[str, str]]) -> None:
    """Drops cache rows for items the latest scan no longer found (deleted/renamed)."""
    with get_session() as session:
        records = (
            session.query(ItemMetadataCache)
            .filter(ItemMetadataCache.connection_id == connection_id)
            .all()
        )
        for record in records:
            if (record.schema, record.name) not in current_keys:
                session.delete(record)
        session.commit()


def list_items(connection_id: str) -> list[CachedItem]:
    with get_session() as session:
        records = (
            session.query(ItemMetadataCache)
            .filter(ItemMetadataCache.connection_id == connection_id)
            .order_by(ItemMetadataCache.schema, ItemMetadataCache.name)
            .all()
        )
        return [CachedItem._from_record(r) for r in records]


def get_item(connection_id: str, schema: str, name: str) -> CachedItem | None:
    with get_session() as session:
        record = session.get(ItemMetadataCache, (connection_id, schema, name))
        return CachedItem._from_record(record) if record else None


def delete_all_for_connection(connection_id: str) -> None:
    with get_session() as session:
        session.query(ItemMetadataCache).filter(ItemMetadataCache.connection_id == connection_id).delete()
        session.commit()
