"""Geoserver connector (PRD §5, TAD §6.1). Read-only.

Geoserver is reached over its own REST Admin API (JSON) via plain HTTP  -
no client library beyond `requests`, since the API already returns clean
JSON (TAD doesn't lock a library for this; chose the lightest option over
pulling in a general OGC client like owslib for no real benefit here).

Geoserver is fundamentally a spatial server: resources are either vector
"feature types" or raster "coverages"  -  there's no plain-tabular concept
to report (PRD §6.2's "tabular" kind doesn't apply here).
"""

from tarsier.timing import timed_phase
from dataclasses import dataclass
from xml.etree import ElementTree

import requests

from tarsier.connectors.base import ConnectorError, DataItem, ItemMetadata, SampleResult
from tarsier.connectors.geojson_sample import sample_feature_collection

_TIMEOUT = 5


@dataclass(frozen=True)
class GeoserverConnectionConfig:
    base_url: str  # e.g. "http://localhost:8080/geoserver"
    username: str = "admin"
    password: str | None = None

    @property
    def auth(self):
        return (self.username, self.password or "")


def build_config(config: dict, password: str | None = None) -> GeoserverConnectionConfig:
    return GeoserverConnectionConfig(
        base_url=config.get("base_url", ""), username=config.get("username", "admin"), password=password
    )


def _get_json(config: GeoserverConnectionConfig, path: str) -> dict:
    url = f"{config.base_url.rstrip('/')}/{path.lstrip('/')}"
    try:
        response = requests.get(url, auth=config.auth, timeout=_TIMEOUT)
    except requests.exceptions.ConnectionError as exc:
        raise ConnectorError(f"Could not connect to {config.base_url}  -  check the address and that the server is reachable.") from exc
    except requests.exceptions.Timeout as exc:
        raise ConnectorError(f"Connecting to {config.base_url} timed out.") from exc
    except requests.exceptions.RequestException as exc:
        # e.g. a missing http:// prefix or an otherwise malformed address
        raise ConnectorError("Enter the GeoServer address, starting with \"http://\" or \"https://\".") from exc

    if response.status_code == 401:
        raise ConnectorError(f"Could not connect: the username or password for {config.username!r} was rejected.")
    if not response.ok:
        raise ConnectorError(f"Geoserver returned an error ({response.status_code}) for {path}.")
    try:
        return response.json()
    except ValueError as exc:
        raise ConnectorError(
            "That address did not answer as a GeoServer REST API. "
            "Check the URL (it usually ends in /geoserver)."
        ) from exc


def test_connection(config: GeoserverConnectionConfig) -> None:
    _get_json(config, "rest/workspaces.json")


@timed_phase("fetch")
def list_items(config: GeoserverConnectionConfig) -> list[DataItem]:
    workspaces_payload = _get_json(config, "rest/workspaces.json")
    workspace_entry = workspaces_payload.get("workspaces") or {}
    workspaces = workspace_entry.get("workspace", []) if isinstance(workspace_entry, dict) else []

    items: list[DataItem] = []
    for ws in workspaces:
        ws_name = ws["name"]
        items.extend(_list_feature_types(config, ws_name))
        items.extend(_list_coverages(config, ws_name))

    return sorted(items, key=lambda item: (item.schema, item.name))


@timed_phase("fetch")
def list_item_columns(config: GeoserverConnectionConfig, item: DataItem) -> list[str]:
    """Return feature type field names from Geoserver metadata."""
    if item.kind != "vector":
        return []
    detail = _get_json(config, f"rest/workspaces/{item.schema}/featuretypes/{item.name}.json")
    attributes = detail.get("featureType", {}).get("attributes", {}).get("attribute", [])
    if isinstance(attributes, dict):
        attributes = [attributes]
    return [attribute["name"] for attribute in attributes if attribute.get("name")]


def _list_feature_types(config: GeoserverConnectionConfig, workspace: str) -> list[DataItem]:
    try:
        payload = _get_json(config, f"rest/workspaces/{workspace}/featuretypes.json")
    except ConnectorError:
        return []  # workspace has no vector data store configured
    entry = payload.get("featureTypes") or {}
    names = [ft["name"] for ft in entry.get("featureType", [])] if isinstance(entry, dict) else []

    items = []
    for name in names:
        detail = _get_json(config, f"rest/workspaces/{workspace}/featuretypes/{name}.json").get("featureType", {})
        srid = _srid_from_srs(detail.get("srs"))
        items.append(DataItem(schema=workspace, name=name, kind="vector", geometry_type=None, srid=srid))
    return items


def _list_coverages(config: GeoserverConnectionConfig, workspace: str) -> list[DataItem]:
    try:
        payload = _get_json(config, f"rest/workspaces/{workspace}/coverages.json")
    except ConnectorError:
        return []  # workspace has no raster store configured
    entry = payload.get("coverages") or {}
    names = [cov["name"] for cov in entry.get("coverage", [])] if isinstance(entry, dict) else []

    items = []
    for name in names:
        detail = _get_json(config, f"rest/workspaces/{workspace}/coverages/{name}.json").get("coverage", {})
        srid = _srid_from_srs(detail.get("srs"))
        items.append(DataItem(schema=workspace, name=name, kind="raster", srid=srid))
    return items


def _srid_from_srs(srs: str | None) -> int | None:
    if not srs or not srs.upper().startswith("EPSG:"):
        return None
    try:
        return int(srs.split(":")[1])
    except (ValueError, IndexError):
        return None


def _bbox_from_native_bbox(detail: dict) -> tuple[float, float, float, float] | None:
    bbox = detail.get("nativeBoundingBox")
    keys = ("minx", "miny", "maxx", "maxy")
    if not bbox or not all(k in bbox for k in keys):
        return None
    return tuple(bbox[k] for k in keys)


@timed_phase("fetch")
def describe_item(config: GeoserverConnectionConfig, item: DataItem) -> ItemMetadata:
    if item.kind == "raster":
        detail = _get_json(config, f"rest/workspaces/{item.schema}/coverages/{item.name}.json").get("coverage", {})
        return ItemMetadata(bbox=_bbox_from_native_bbox(detail))

    detail = _get_json(config, f"rest/workspaces/{item.schema}/featuretypes/{item.name}.json").get("featureType", {})
    bbox = _bbox_from_native_bbox(detail)

    row_count = None
    try:
        url = f"{config.base_url.rstrip('/')}/wfs"
        params = {
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": f"{item.schema}:{item.name}", "resultType": "hits",
        }
        response = requests.get(url, params=params, auth=config.auth, timeout=_TIMEOUT)
        if response.ok:
            # Geoserver always answers a hits-only request in XML, ignoring
            # any requested outputFormat (found via a direct curl check)  -
            # numberMatched is an attribute on the root element, not JSON.
            root = ElementTree.fromstring(response.content)
            matched = root.get("numberMatched")
            if matched is not None and matched.isdigit():
                row_count = int(matched)
    except (requests.exceptions.RequestException, ElementTree.ParseError):
        pass

    return ItemMetadata(row_count=row_count, bbox=bbox)


@timed_phase("fetch", observe_rows=True)
def sample_rows(config: GeoserverConnectionConfig, item: DataItem, limit: int = 1000, *, distinct_column: str | None = None) -> SampleResult:
    if item.kind == "raster":
        raise ConnectorError("Statistics are unavailable for GeoServer raster coverages. Vector layers are supported.")

    url = f"{config.base_url.rstrip('/')}/wfs"
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": f"{item.schema}:{item.name}",
        "outputFormat": "application/json",
        "count": limit + 1,
    }
    if distinct_column is not None:
        import pandas as pd
        import time
        values = set()
        offset = 0
        deadline = time.monotonic() + _TIMEOUT
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ConnectorError("The GeoServer distinct-value read reached its existing timeout.")
            page = {**params, "propertyName": distinct_column, "startIndex": offset}
            try:
                response = requests.get(url, params=page, auth=config.auth, timeout=remaining)
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError) as exc:
                raise ConnectorError("Could not finish the GeoServer distinct-value read within its existing timeout.") from exc
            if not isinstance(payload, dict) or "features" not in payload:
                raise ConnectorError("GeoServer did not return a distinct-value page.")
            features = payload["features"]
            for feature in features:
                value = feature.get("properties", {}).get(distinct_column)
                if value is not None:
                    try:
                        values.add(value)
                    except TypeError:
                        pass
                if len(values) > limit:
                    return SampleResult(pd.DataFrame({distinct_column: list(values)[:limit]}), True)
            offset += len(features)
            total = payload.get("numberMatched", payload.get("totalFeatures"))
            if not features or (str(total).isdigit() and offset >= int(total)):
                return SampleResult(pd.DataFrame({distinct_column: list(values)}), False)
    try:
        response = requests.get(url, params=params, auth=config.auth, timeout=_TIMEOUT)
    except requests.exceptions.ConnectionError as exc:
        raise ConnectorError("Could not reach GeoServer WFS to read statistics.") from exc
    except requests.exceptions.Timeout as exc:
        raise ConnectorError("The GeoServer WFS statistics request timed out.") from exc
    except requests.exceptions.RequestException as exc:
        raise ConnectorError("Could not reach GeoServer WFS to read statistics.") from exc
    if response.status_code == 401:
        raise ConnectorError("Could not read statistics: GeoServer rejected the username or password.")
    if not response.ok:
        raise ConnectorError(f"GeoServer WFS returned an error ({response.status_code}) while reading statistics.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ConnectorError("GeoServer WFS returned an unreadable JSON statistics response.") from exc
    if not isinstance(payload, dict) or "features" not in payload:
        raise ConnectorError("GeoServer WFS did not return a JSON feature collection for this layer.")
    total = payload.get("totalFeatures", payload.get("numberMatched"))
    try:
        total_count = int(total) if total is not None else None
    except (TypeError, ValueError):
        total_count = None
    provider_sampled = total_count is not None and total_count > limit
    return sample_feature_collection(payload, limit, vector=True, provider_sampled=provider_sampled)
