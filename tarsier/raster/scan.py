"""Orchestrates computing and caching one raster's detail (PRD §8).
Same pattern as tarsier.stats.scan: re-list the connection for a fresh
DataItem, ask the connector for the detail, cache it.
"""

from tarsier.timing import timed_run
from tarsier.connectors.base import ConnectorError
from tarsier.connectors.registry import get_connector
from tarsier.raster.analyze import RasterDetail
from tarsier.storage import connections as connection_storage
from tarsier.storage import raster_cache


@timed_run("raster")
def scan_item_raster(connection_id: str, schema: str, name: str, *, full: bool = False) -> RasterDetail:
    saved = connection_storage.get_connection(connection_id)
    if saved is None:
        raise ValueError(f"No such connection: {connection_id!r}")

    password = connection_storage.get_connection_password(connection_id)
    connector = get_connector(saved.type)
    config = connector.build_config(saved.config, password)

    if not hasattr(connector, "raster_detail"):
        raise ConnectorError(f"Raster detail isn't available yet for {saved.type} connections.")

    item = next((i for i in connector.list_items(config) if i.schema == schema and i.name == name), None)
    if item is None:
        raise ConnectorError(f"{name!r} was not found on this connection  -  try running a check first.")
    if item.kind != "raster":
        raise ConnectorError(f"{name!r} is not a raster.")

    detail = connector.raster_detail(config, item, full=full)
    raster_cache.save_detail(connection_id, schema, name, detail)
    return detail
