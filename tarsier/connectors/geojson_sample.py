"""Convert a bounded GeoJSON FeatureCollection to Tarsier's stats shape."""

import pandas as pd
from shapely.geometry import shape

from tarsier.connectors.base import ConnectorError, SampleResult


def sample_feature_collection(payload: dict, limit: int, *, vector: bool, provider_sampled: bool = False) -> SampleResult:
    features = payload.get("features")
    if not isinstance(features, list):
        raise ConnectorError("The service response did not contain a GeoJSON feature list.")

    sampled_features = features[:limit]
    rows = [feature.get("properties") or {} for feature in sampled_features]
    frame = pd.DataFrame(rows)
    if not vector:
        return SampleResult(dataframe=frame, is_sample=provider_sampled or len(features) > limit)

    centers_x: list[float | None] = []
    centers_y: list[float | None] = []
    null_geometry: list[bool] = []
    for feature in sampled_features:
        geometry_json = feature.get("geometry")
        if geometry_json is None:
            centers_x.append(None)
            centers_y.append(None)
            null_geometry.append(True)
            continue
        try:
            geometry = shape(geometry_json)
            if geometry.is_empty:
                centers_x.append(None)
                centers_y.append(None)
                null_geometry.append(True)
                continue
            center = geometry.centroid
        except Exception as exc:
            raise ConnectorError("The service returned geometry that Tarsier could not read.") from exc
        centers_x.append(float(center.x))
        centers_y.append(float(center.y))
        null_geometry.append(False)

    frame["__cx"] = centers_x
    frame["__cy"] = centers_y
    frame["__geom_null"] = null_geometry
    return SampleResult(
        dataframe=frame,
        is_sample=provider_sampled or len(features) > limit,
        geometry_columns=("__cx", "__cy"),
        null_geometry_column="__geom_null",
    )
