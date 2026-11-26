"""Build a GeoDataFrame from WKB rows returned by database connectors."""

import pandas as pd
from shapely import wkb


def geodataframe_from_wkb_rows(rows: list, srid: int | None, wkb_key: str = "__wkb", *, crs: str | None = None):
    import geopandas as gpd

    records = []
    geometries = []
    for row in rows:
        data = dict(row)
        raw = data.pop(wkb_key, None)
        records.append(data)
        if raw is None:
            geometries.append(None)
        else:
            geometries.append(wkb.loads(bytes(raw)))
    crs = crs or (f"EPSG:{srid}" if srid else None)
    if not records:
        return gpd.GeoDataFrame(columns=[], geometry=[], crs=crs)
    frame = pd.DataFrame.from_records(records)
    return gpd.GeoDataFrame(frame, geometry=geometries, crs=crs)
