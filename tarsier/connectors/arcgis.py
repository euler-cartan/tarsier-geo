"""ArcGIS Enterprise connector (PRD §5, TAD §6.1). Read-only.

Reached over ArcGIS's own REST Services Directory (JSON) via plain
`requests`  -  not Esri's official `arcgis` Python package, which is a very
large SDK built for far more than listing services; a lightweight REST
client is all PRD §5's "connects and lists its contents" needs.

FeatureServer/MapServer responses already separate "layers" (spatial) from
"tables" (non-spatial) natively, so that split comes for free from the API
rather than needing inference like the database connectors.

Note: not verified against a genuine ArcGIS Enterprise instance  -  no
feasible way to stand one up locally (licensed enterprise product).
Tested against a mock server reproducing the documented REST contract.
"""

from tarsier.timing import timed_phase
from dataclasses import dataclass

import requests

from tarsier.connectors.base import ConnectorError, DataItem, ItemMetadata, SampleResult
from tarsier.connectors.geojson_sample import sample_feature_collection

_TIMEOUT = 5

_GEOMETRY_TYPE_LABELS = {
    "esriGeometryPoint": "Point",
    "esriGeometryMultipoint": "MultiPoint",
    "esriGeometryPolyline": "LineString",
    "esriGeometryPolygon": "Polygon",
}


@dataclass(frozen=True)
class ArcGISConnectionConfig:
    base_url: str  # e.g. "http://localhost:6080/arcgis/rest/services"
    token: str | None = None


def build_config(config: dict, password: str | None = None) -> ArcGISConnectionConfig:
    return ArcGISConnectionConfig(base_url=config.get("base_url", ""), token=config.get("token") or password)


def _get_json(config: ArcGISConnectionConfig, path: str = "") -> dict:
    url = f"{config.base_url.rstrip('/')}/{path.lstrip('/')}" if path else config.base_url
    params = {"f": "json"}
    if config.token:
        params["token"] = config.token
    try:
        response = requests.get(url, params=params, timeout=_TIMEOUT)
    except requests.exceptions.ConnectionError as exc:
        raise ConnectorError(f"Could not connect to {config.base_url}  -  check the address and that the server is reachable.") from exc
    except requests.exceptions.Timeout as exc:
        raise ConnectorError(f"Connecting to {config.base_url} timed out.") from exc
    except requests.exceptions.RequestException as exc:
        # e.g. a missing http:// prefix or an otherwise malformed address
        raise ConnectorError("Enter the ArcGIS REST services address, starting with \"http://\" or \"https://\".") from exc

    if not response.ok:
        raise ConnectorError(f"ArcGIS Server returned an error ({response.status_code}) for {path or '/'}.")

    try:
        payload = response.json()
    except ValueError as exc:
        # A sign-in page or proxy error page instead of the REST directory.
        raise ConnectorError(
            "That address did not answer as an ArcGIS REST services directory. "
            "Check the URL (it usually ends in /arcgis/rest/services)."
        ) from exc
    if isinstance(payload, dict) and "error" in payload:
        error = payload["error"]
        message = error.get("message", "Unknown error")
        if error.get("code") == 499 or "token" in message.lower() or "credentials" in message.lower():
            raise ConnectorError("Could not connect: invalid or missing token/credentials.")
        raise ConnectorError(f"ArcGIS Server returned an error: {message}")
    return payload


def test_connection(config: ArcGISConnectionConfig) -> None:
    _get_json(config)


@timed_phase("fetch")
def list_items(config: ArcGISConnectionConfig) -> list[DataItem]:
    items = list(_walk_folder(config, ""))
    return sorted(items, key=lambda item: (item.schema, item.name))


@timed_phase("fetch")
def list_item_columns(config: ArcGISConnectionConfig, item: DataItem) -> list[str]:
    """Return layer field names from ArcGIS metadata without reading rows."""
    if item.kind == "raster":
        return []
    detail = _get_json(config, item.path)
    return [field["name"] for field in detail.get("fields", []) if field.get("name")]


def _walk_folder(config: ArcGISConnectionConfig, folder: str):
    payload = _get_json(config, folder)

    for service in payload.get("services", []):
        name = service["name"]
        service_type = service["type"]
        # Service names from a sub-folder come back as "folder/name".
        short_name = name.rsplit("/", 1)[-1]
        yield from _list_service_contents(config, name, short_name, folder or "root", service_type)

    for sub_folder in payload.get("folders", []):
        next_path = f"{folder}/{sub_folder}" if folder else sub_folder
        yield from _walk_folder(config, next_path)


def _list_service_contents(config: ArcGISConnectionConfig, service_path: str, name: str, folder: str, service_type: str):
    if service_type == "ImageServer":
        yield DataItem(schema=folder, name=name, kind="raster", path=f"{service_path}/{service_type}")
        return

    if service_type not in ("FeatureServer", "MapServer"):
        return  # e.g. GeocodeServer, GPServer  -  not a data listing

    detail = _get_json(config, f"{service_path}/{service_type}")
    for layer in detail.get("layers", []):
        geometry_type = _GEOMETRY_TYPE_LABELS.get(layer.get("geometryType"))
        path = f"{service_path}/{service_type}/{layer['id']}"
        yield DataItem(schema=folder, name=layer["name"], kind="vector", geometry_type=geometry_type, path=path)
    for table in detail.get("tables", []):
        path = f"{service_path}/{service_type}/{table['id']}"
        yield DataItem(schema=folder, name=table["name"], kind="tabular", path=path)


@timed_phase("fetch")
def describe_item(config: ArcGISConnectionConfig, item: DataItem) -> ItemMetadata:
    if item.kind == "raster":
        detail = _get_json(config, item.path)
        extent = detail.get("extent") or {}
        bbox = _bbox_from_extent(extent)
        return ItemMetadata(bbox=bbox)

    detail = _get_json(config, item.path)
    bbox = _bbox_from_extent(detail.get("extent") or {})

    row_count = None
    try:
        url = f"{config.base_url.rstrip('/')}/{item.path}/query"
        params = {"f": "json", "where": "1=1", "returnCountOnly": "true"}
        if config.token:
            params["token"] = config.token
        response = requests.get(url, params=params, timeout=_TIMEOUT)
        if response.ok:
            row_count = response.json().get("count")
    except requests.exceptions.RequestException:
        pass

    return ItemMetadata(row_count=row_count, bbox=bbox)


@timed_phase("fetch", observe_rows=True)
def sample_rows(config: ArcGISConnectionConfig, item: DataItem, limit: int = 1000, *, distinct_column: str | None = None) -> SampleResult:
    if item.kind == "raster":
        raise ConnectorError("Statistics are unavailable for ArcGIS raster services. FeatureServer vector layers and tables are supported.")
    if not item.path or "/FeatureServer/" not in f"/{item.path}/":
        raise ConnectorError("Statistics are available only for ArcGIS FeatureServer layers and tables.")

    url = f"{config.base_url.rstrip('/')}/{item.path}/query"
    params = {
        "f": "geojson",
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true" if item.kind == "vector" else "false",
        "resultRecordCount": limit + 1,
    }
    if distinct_column is not None:
        params.update(f="json", outFields=distinct_column, returnGeometry="false", returnDistinctValues="true")
    if config.token:
        params["token"] = config.token
    try:
        response = requests.get(url, params=params, timeout=_TIMEOUT)
    except requests.exceptions.ConnectionError as exc:
        raise ConnectorError("Could not reach the ArcGIS FeatureServer to read statistics.") from exc
    except requests.exceptions.Timeout as exc:
        raise ConnectorError("The ArcGIS FeatureServer statistics request timed out.") from exc
    except requests.exceptions.RequestException as exc:
        raise ConnectorError("Could not reach the ArcGIS FeatureServer to read statistics.") from exc
    if not response.ok:
        raise ConnectorError(f"ArcGIS FeatureServer returned an error ({response.status_code}) while reading statistics.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ConnectorError("ArcGIS FeatureServer returned an unreadable statistics response.") from exc
    if isinstance(payload, dict) and "error" in payload:
        error = payload["error"]
        message = str(error.get("message", "")) if isinstance(error, dict) else ""
        if "token" in message.lower() or "credential" in message.lower():
            raise ConnectorError("Could not read statistics: invalid or missing ArcGIS token/credentials.")
        raise ConnectorError("ArcGIS FeatureServer could not return statistics for this layer.")
    if not isinstance(payload, dict):
        raise ConnectorError("ArcGIS FeatureServer returned an invalid statistics response.")
    if distinct_column is not None:
        import pandas as pd
        frame = pd.DataFrame([row.get("attributes", {}) for row in payload.get("features", [])], columns=[distinct_column])
        frame = frame.dropna().drop_duplicates()
        exceeded = bool(payload.get("exceededTransferLimit"))
        if exceeded and len(frame) <= limit:
            raise ConnectorError("The service distinct-value limit prevents a complete link comparison.")
        return SampleResult(frame.iloc[:limit], exceeded or len(frame) > limit)
    return sample_feature_collection(
        payload,
        limit,
        vector=item.kind == "vector",
        provider_sampled=bool(payload.get("exceededTransferLimit")),
    )


def _bbox_from_extent(extent: dict) -> tuple[float, float, float, float] | None:
    keys = ("xmin", "ymin", "xmax", "ymax")
    if not all(k in extent for k in keys):
        return None
    return tuple(extent[k] for k in keys)
