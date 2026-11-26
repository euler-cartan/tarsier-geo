"""Orchestrates computing and caching one item's statistics (PRD §7.2).
Mirrors tarsier.overview's scan pattern: re-list the connection's items to
get a fresh DataItem, run the connector's sample_rows + the stats
engine, cache the result.
"""

from tarsier.timing import timed_run, timed_phase
from tarsier.connectors.base import ConnectorError, SampleResult
from tarsier.connectors.registry import get_connector
from tarsier.limits import FULL_SCAN_MAX_ROWS
from tarsier.stats.engine import compute_table_stats
from tarsier.storage import connections as connection_storage
from tarsier.storage import item_cache, preview_cache, stats_cache

DEFAULT_SAMPLE_LIMIT = 1000
# A "full" run is bounded too (tarsier.limits): a larger table is summarised
# from its first FULL_RUN_LIMIT rows and labelled as a sample.
FULL_RUN_LIMIT = FULL_SCAN_MAX_ROWS
MAX_FULL_STATS_ROWS = 20_000
FULL_STATS_UNAVAILABLE = "Full statistics are not available for tables this large in this release. Sample statistics are shown and labelled."
FULL_STATS_UNAVAILABLE_NO_SAMPLE = "Full statistics are not available for tables this large in this release. No sample statistics are available yet."
EMPTY_TABLE = "This table has no rows"
UNKNOWN_TABLE_SIZE = "Full statistics were not run because the table size could not be determined."


def load_item_sample(connection_id: str, schema: str, name: str, *, full: bool = False) -> SampleResult:
    return load_item_sample_limited(connection_id, schema, name, FULL_RUN_LIMIT if full else DEFAULT_SAMPLE_LIMIT)


@timed_phase("fetch")
def load_item_sample_limited(connection_id: str, schema: str, name: str, limit: int) -> SampleResult:
    saved = connection_storage.get_connection(connection_id)
    if saved is None:
        raise ValueError(f"No such connection: {connection_id!r}")

    password = connection_storage.get_connection_password(connection_id)
    connector = get_connector(saved.type)
    config = connector.build_config(saved.config, password)

    if not hasattr(connector, "sample_rows"):
        raise ConnectorError(f"Statistics aren't available yet for {saved.type} connections.")

    items = connector.list_items(config)
    item = next((i for i in items if i.schema == schema and i.name == name), None)
    if item is None:
        raise ConnectorError(f"{name!r} was not found on this connection  -  try running a check first.")
    if not item.readable:
        raise ConnectorError("No permission to read this table.")
    if limit == FULL_RUN_LIMIT:
        cached = item_cache.get_item(connection_id, schema, name)
        if cached is not None and cached.row_count == 0:
            raise ConnectorError(EMPTY_TABLE)
        if cached is None or cached.row_count is None:
            raise ConnectorError(UNKNOWN_TABLE_SIZE)
        if cached.row_count > MAX_FULL_STATS_ROWS:
            existing_stats = stats_cache.get_stats(connection_id, schema, name)
            message = FULL_STATS_UNAVAILABLE if existing_stats is not None and existing_stats.is_sample else FULL_STATS_UNAVAILABLE_NO_SAMPLE
            raise ConnectorError(message)

    return connector.sample_rows(config, item, limit=limit)


@timed_run("statistics")
def scan_item_stats(connection_id: str, schema: str, name: str, *, full: bool = False) -> None:
    result = load_item_sample(connection_id, schema, name, full=full)
    stats = compute_table_stats(
        result.dataframe,
        result.is_sample,
        geometry_columns=result.geometry_columns,
        null_geometry_column=result.null_geometry_column,
    )
    from dataclasses import replace
    stats = replace(stats, sample_details=getattr(result, "details", {}))
    stats_cache.save_stats(connection_id, schema, name, stats)


PREVIEW_ROWS = 20


def scan_item_preview(connection_id: str, schema: str, name: str) -> None:
    """Column schema + first rows for the tabular Overview tab (FSD §7)."""
    import json

    result = load_item_sample_limited(connection_id, schema, name, PREVIEW_ROWS)
    frame = result.dataframe
    hidden = set(result.geometry_columns or ())
    if result.null_geometry_column:
        hidden.add(result.null_geometry_column)
    frame = frame.drop(columns=[c for c in frame.columns if c in hidden])
    columns = [{"name": str(c), "type": str(frame[c].dtype)} for c in frame.columns]
    rows = json.loads(frame.head(PREVIEW_ROWS).to_json(orient="records", date_format="iso", default_handler=str))
    preview_cache.save_preview(connection_id, schema, name, columns, rows)
