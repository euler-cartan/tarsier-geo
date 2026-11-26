"""Database Overview page (PRD §7.1, FSD §6). Scans a connection on demand
(TAD §8  -  never on every page load) and caches the result; the Overview
itself only ever reads the cache.

Two numeric thresholds PRD/FSD/FTL/DVS never pin down (no day count, no
"heaviest" definition given)  -  picked here and documented, not guessed
silently: a layer is "stale" if untouched for 90+ days (FSD's own mockup
example, "Stale  -  94 days", is in that ballpark) and "heavy" if it's among
the 3 largest items in the connection and over 1MB (so trivial test data
doesn't get flagged as heavy).
"""

from tarsier.timing import timed_run
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from tarsier.connectors.registry import get_connector
from tarsier.connectors.base import ItemMetadata
from tarsier.health import calculate_health, quality_is_sample
from tarsier.storage import change_log, connections as connection_storage, item_cache, quality_cache, settings
from tarsier.storage import flowchart as flowchart_storage

STALE_AFTER_DAYS = 90


def _evaluate_alerts(connection_id: str) -> None:
    try:
        from tarsier.alerts.evaluate import evaluate_connection

        evaluate_connection(connection_id)
    except Exception:
        pass
    try:
        from tarsier.automation.evaluate import evaluate_connection as evaluate_autos

        evaluate_autos(connection_id)
    except Exception:
        return
HEAVY_COUNT = 3
HEAVY_MIN_BYTES = 1_000_000


@timed_run("inventory")
def scan_connection(connection_id: str) -> None:
    saved = connection_storage.get_connection(connection_id)
    if saved is None:
        raise ValueError(f"No such connection: {connection_id!r}")

    password = connection_storage.get_connection_password(connection_id)
    connector = get_connector(saved.type)
    config = connector.build_config(saved.config, password)

    items = connector.list_items(config)
    notice = ""
    if saved.type == "postgis":
        from tarsier.connectors.postgis import spatial_features_available
        if not spatial_features_available(config):
            notice = "PostGIS is not installed in this database. Spatial features are unavailable; non-spatial tables are still available."
    settings._set_value(f"scan_notice:{connection_id}", notice)
    unreadable = {(item.schema, item.name) for item in items if not item.readable}
    settings._set_value(f"unreadable_items:{connection_id}", json.dumps(sorted(unreadable)))
    for item in items:
        metadata = connector.describe_item(config, item) if item.readable else ItemMetadata()
        item_cache.upsert_item(connection_id, item, metadata)

    current_keys = {(item.schema, item.name) for item in items}
    item_cache.remove_items_not_in(connection_id, current_keys)

    connection_storage.record_scan_result(connection_id)
    from tarsier.graph.engine import refresh_quietly

    refresh_quietly()
    _evaluate_alerts(connection_id)


@dataclass(frozen=True)
class OverviewLayerRow:
    schema: str
    name: str
    kind: str
    geometry_type: str | None
    srid: int | None
    row_count: int | None
    row_count_is_estimate: bool
    row_count_is_capped: bool
    size_bytes: int | None
    has_index: bool | None
    last_modified: str | None
    is_stale: bool
    is_heavy: bool
    health_score: int | None
    health_components: dict[str, int | None]
    health_is_sample: bool
    readable: bool


@dataclass(frozen=True)
class ProjectionGroup:
    srid: int | None
    layer_count: int
    is_majority: bool


@dataclass(frozen=True)
class OverviewSummary:
    connection_id: str
    connection_name: str
    connection_type: str
    last_scanned_at: datetime | None
    ever_scanned: bool
    total_layers: int
    relationship_count: int
    total_size_bytes: int | None
    health_score: int | None
    health_coverage_count: int
    health_components: dict[str, int | None]
    health_is_sample: bool
    source_notice: str | None
    no_permission_count: int
    layers: list[OverviewLayerRow]
    projections: list[ProjectionGroup]


def get_overview(connection_id: str) -> OverviewSummary:
    saved = connection_storage.get_connection(connection_id)
    if saved is None:
        raise ValueError(f"No such connection: {connection_id!r}")

    cached = item_cache.list_items(connection_id)
    unreadable = _unreadable_items(connection_id)
    checks_by_item = quality_cache.get_all_checks(connection_id)
    last_events = change_log.latest_event_times(connection_id)
    health_by_key = {
        (item.schema, item.name): calculate_health(
            item.last_modified,
            last_events.get((item.schema, item.name)),
            checks_by_item.get((item.schema, item.name), {}),
        )
        for item in cached if (item.schema, item.name) not in unreadable
    }
    ever_scanned = saved.last_scanned_at is not None

    sized = sorted((c for c in cached if c.size_bytes), key=lambda c: c.size_bytes, reverse=True)
    heavy_keys = {(c.schema, c.name) for c in sized[:HEAVY_COUNT] if c.size_bytes >= HEAVY_MIN_BYTES}

    stale_cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_AFTER_DAYS)

    rows = [
        OverviewLayerRow(
            schema=c.schema,
            name=c.name,
            kind=c.kind,
            geometry_type=c.geometry_type,
            srid=c.srid,
            row_count=c.row_count,
            row_count_is_estimate=c.row_count_is_estimate,
            row_count_is_capped=c.row_count_is_capped,
            size_bytes=c.size_bytes,
            has_index=c.has_index,
            last_modified=c.last_modified,
            is_stale=_is_stale(
                c.last_modified,
                last_events.get((c.schema, c.name)),
                saved.last_scanned_at,
                stale_cutoff,
            ),
            is_heavy=(c.schema, c.name) in heavy_keys,
            health_score=health_by_key[(c.schema, c.name)]["score"] if (c.schema, c.name) not in unreadable else None,
            health_components=health_by_key[(c.schema, c.name)]["components"] if (c.schema, c.name) not in unreadable else {"quality": None, "freshness": None, "completeness": None},
            health_is_sample=(c.schema, c.name) not in unreadable and quality_is_sample(checks_by_item.get((c.schema, c.name), {})),
            readable=(c.schema, c.name) not in unreadable,
        )
        for c in cached
    ]

    sized_values = [c.size_bytes for c in cached if c.size_bytes is not None]
    total_size = sum(sized_values) if sized_values else None
    layer_scores = [value["score"] for value in health_by_key.values() if value["score"] is not None]
    database_score = round(sum(layer_scores) / len(layer_scores)) if layer_scores else None
    component_means: dict[str, int | None] = {}
    for name in ("quality", "freshness", "completeness"):
        values = [
            result["components"][name]
            for result in health_by_key.values()
            if result["components"][name] is not None
        ]
        component_means[name] = round(sum(values) / len(values)) if values else None

    return OverviewSummary(
        connection_id=connection_id,
        connection_name=saved.name,
        connection_type=saved.type,
        last_scanned_at=saved.last_scanned_at,
        ever_scanned=ever_scanned,
        total_layers=len(cached),
        relationship_count=flowchart_storage.count_links(connection_id),
        total_size_bytes=total_size,
        health_score=database_score,
        health_coverage_count=len(layer_scores),
        health_components=component_means,
        health_is_sample=any(row.health_is_sample for row in rows),
        source_notice=settings._get_value(f"scan_notice:{connection_id}") or None,
        no_permission_count=len(unreadable),
        layers=rows,
        projections=_group_projections(cached),
    )


def _unreadable_items(connection_id: str) -> set[tuple[str, str]]:
    value = settings._get_value(f"unreadable_items:{connection_id}")
    return {tuple(item) for item in json.loads(value)} if value else set()


def get_item_health(connection_id: str, schema: str, name: str) -> dict:
    if (schema, name) in _unreadable_items(connection_id):
        return {"health_score": None, "health_components": {"quality": None, "freshness": None, "completeness": None}, "health_is_sample": False, "readable": False}
    cached = item_cache.get_item(connection_id, schema, name)
    if cached is None:
        return {
            "health_score": None,
            "health_components": {"quality": None, "freshness": None, "completeness": None},
        }
    last_event = change_log.latest_event_times(connection_id).get((schema, name))
    result = calculate_health(
        cached.last_modified,
        last_event,
        quality_cache.get_checks(connection_id, schema, name),
    )
    return {"health_score": result["score"], "health_components": result["components"],
            "health_is_sample": quality_is_sample(quality_cache.get_checks(connection_id, schema, name)), "readable": True}


def _is_stale(
    last_modified: str | None,
    latest_event: datetime | None,
    last_scanned_at: datetime | None,
    cutoff: datetime,
) -> bool:
    modified = None
    if last_modified:
        try:
            modified = datetime.fromisoformat(last_modified)
        except ValueError:
            pass
    modified = modified or latest_event or last_scanned_at
    if modified is None:
        return False
    if modified.tzinfo is None:
        modified = modified.replace(tzinfo=timezone.utc)
    return modified < cutoff


def _group_projections(cached) -> list[ProjectionGroup]:
    counts: dict[int | None, int] = {}
    for c in cached:
        if c.srid is not None:
            counts[c.srid] = counts.get(c.srid, 0) + 1
    if not counts:
        return []
    majority_srid = max(counts, key=counts.get)
    return [
        ProjectionGroup(srid=srid, layer_count=count, is_majority=(srid == majority_srid))
        for srid, count in sorted(counts.items(), key=lambda kv: -kv[1])
    ]
