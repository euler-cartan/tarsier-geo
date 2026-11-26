"""Maps a connection `type` string to its connector module.

Every connector module exposes the same shape: `build_config(config, password)`,
`test_connection(config)`, `list_items(config)`, and `describe_item(config, item)`.
Used by both the Add Connection flow (api/connections.py) and the Overview
scan (overview.py), so the per-type config-building logic lives in exactly
one place.
"""

from tarsier.connectors import arcgis, files, geoserver, oracle, postgis, sqlserver

CONNECTORS = {
    "postgis": postgis,
    "oracle": oracle,
    "sqlserver": sqlserver,
    "files": files,
    "arcgis": arcgis,
    "geoserver": geoserver,
}


def get_connector(type_id: str):
    try:
        return CONNECTORS[type_id]
    except KeyError:
        raise ValueError(f"Unknown connection type: {type_id!r}") from None
