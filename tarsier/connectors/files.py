"""Files-in-folders connector (PRD §5, §6.2, TAD §3). Read-only.

Scans a folder (recursively) for the formats PRD §5 names: shapefile,
GeoPackage, GeoTIFF, and CSV. No database involved, so there's nothing to
enforce read-only against  -  Tarsier simply never opens these files for
writing. A GeoPackage can hold several layers in one file; each is listed
separately. Metadata only (no change tracking  -  PRD §5: files have none).
"""

from tarsier.timing import timed_phase
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyogrio
import rasterio

from tarsier.connectors.base import (
    ConnectorError,
    DataItem,
    GeometrySample,
    IdColumnSample,
    ItemMetadata,
    SampleResult,
    find_id_column,
)

_VECTOR_EXTENSIONS = {".shp", ".gpkg"}
_RASTER_EXTENSIONS = {".tif", ".tiff"}
_TABULAR_EXTENSIONS = {".csv"}


@dataclass(frozen=True)
class FilesConnectionConfig:
    folder: str


def build_config(config: dict, password: str | None = None) -> FilesConnectionConfig:
    # No credentials for a folder connection  -  `password` is accepted only
    # so every connector's build_config has the same shape for the registry.
    return FilesConnectionConfig(folder=config.get("folder", ""))


def test_connection(config: FilesConnectionConfig) -> None:
    path = Path(config.folder)
    if not path.exists():
        raise ConnectorError(f"Folder does not exist: {config.folder}")
    if not path.is_dir():
        raise ConnectorError(f"Not a folder: {config.folder}")


@timed_phase("fetch")
def list_items(config: FilesConnectionConfig) -> list[DataItem]:
    root = Path(config.folder)
    test_connection(config)

    items: list[DataItem] = []
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        suffix = file_path.suffix.lower()
        relative = str(file_path.relative_to(root))

        if suffix == ".gpkg":
            items.extend(_list_geopackage_layers(file_path, relative))
        elif suffix == ".shp":
            items.append(_shapefile_item(file_path, relative))
        elif suffix in _RASTER_EXTENSIONS:
            items.append(_raster_item(file_path, relative))
        elif suffix in _TABULAR_EXTENSIONS:
            items.append(DataItem(schema="", name=file_path.name, kind="tabular", path=relative))

    return items


def _shapefile_item(file_path: Path, relative: str) -> DataItem:
    try:
        info = pyogrio.read_info(file_path)
    except Exception as exc:  # pragma: no cover - corrupt/unreadable file
        raise ConnectorError(f"Could not read {relative}: {exc}") from exc
    srid = _srid_from_crs(info.get("crs"))
    return DataItem(
        schema="", name=file_path.stem, kind="vector",
        geometry_type=info.get("geometry_type"), srid=srid, path=relative,
    )


def _list_geopackage_layers(file_path: Path, relative: str) -> list[DataItem]:
    try:
        layers = pyogrio.list_layers(file_path)
    except Exception as exc:  # pragma: no cover - corrupt/unreadable file
        raise ConnectorError(f"Could not read {relative}: {exc}") from exc

    items = []
    for layer_name, geom_type in layers:
        if geom_type is None:
            # A geometry-less table inside a GeoPackage is a standalone table
            # (PRD §6.2). A vector layer's own attributes are part of that
            # layer and never appear as a second item (PRD §6.1).
            items.append(DataItem(schema="", name=layer_name, kind="tabular", path=relative))
            continue
        info = pyogrio.read_info(file_path, layer=layer_name)
        srid = _srid_from_crs(info.get("crs"))
        items.append(
            DataItem(
                schema="", name=layer_name, kind="vector",
                geometry_type=info.get("geometry_type"), srid=srid, path=relative,
            )
        )
    return items


def _raster_item(file_path: Path, relative: str) -> DataItem:
    try:
        with rasterio.open(file_path) as dataset:
            srid = dataset.crs.to_epsg() if dataset.crs else None
    except Exception as exc:  # pragma: no cover - corrupt/unreadable file
        raise ConnectorError(f"Could not read {relative}: {exc}") from exc
    return DataItem(schema="", name=file_path.name, kind="raster", srid=srid, path=relative)


def _srid_from_crs(crs) -> int | None:
    if not crs:
        return None
    # pyogrio's `crs` is an EPSG-style string like "EPSG:4326".
    if isinstance(crs, str) and crs.upper().startswith("EPSG:"):
        try:
            return int(crs.split(":")[1])
        except ValueError:
            return None
    return None


@timed_phase("fetch")
def describe_item(config: FilesConnectionConfig, item: DataItem) -> ItemMetadata:
    root = Path(config.folder)
    file_path = root / item.path
    last_modified = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()

    if item.kind == "vector":
        is_geopackage = file_path.suffix.lower() == ".gpkg"
        info = pyogrio.read_info(file_path, layer=item.name if is_geopackage else None)
        bounds = info.get("total_bounds")
        has_index = (file_path.with_suffix(".qix").exists() or file_path.with_suffix(".sbn").exists()) if not is_geopackage else None
        return ItemMetadata(
            row_count=info.get("features"),
            size_bytes=file_path.stat().st_size,
            has_index=has_index,
            bbox=tuple(bounds) if bounds is not None else None,
            last_modified=last_modified,
        )

    if item.kind == "raster":
        with rasterio.open(file_path) as dataset:
            bounds = dataset.bounds
            return ItemMetadata(
                size_bytes=file_path.stat().st_size,
                bbox=(bounds.left, bounds.bottom, bounds.right, bounds.top),
                last_modified=last_modified,
                raster_width=dataset.width,
                raster_height=dataset.height,
                raster_band_count=dataset.count,
                raster_dtype=dataset.dtypes[0] if dataset.dtypes else None,
                raster_nodata=dataset.nodata,
            )

    # tabular (CSV, or a geometry-less GeoPackage table)
    if file_path.suffix.lower() == ".gpkg":
        info = pyogrio.read_info(file_path, layer=item.name)
        return ItemMetadata(
            row_count=info.get("features"),
            size_bytes=file_path.stat().st_size,
            last_modified=last_modified,
        )
    with open(file_path, newline="", encoding="utf-8", errors="replace") as f:
        row_count = sum(1 for _ in f) - 1  # minus the header row
    return ItemMetadata(
        row_count=max(row_count, 0),
        size_bytes=file_path.stat().st_size,
        last_modified=last_modified,
    )


def _read_tabular(file_path: Path, item: DataItem, *, nrows: int | None = None, usecols: list[str] | None = None) -> pd.DataFrame:
    """Rows of a CSV, or of a geometry-less GeoPackage table."""
    try:
        if file_path.suffix.lower() == ".gpkg":
            frame = pyogrio.read_dataframe(
                file_path, layer=item.name, columns=usecols, max_features=nrows if nrows else None, read_geometry=False
            )
            return frame.iloc[:0] if nrows == 0 else frame
        return pd.read_csv(file_path, nrows=nrows, usecols=usecols)
    except Exception as exc:  # pragma: no cover - corrupt/unreadable file
        raise ConnectorError(f"Could not read {item.path}: {exc}") from exc


@timed_phase("fetch", observe_rows=True)
def sample_rows(config: FilesConnectionConfig, item: DataItem, limit: int = 1000, *, distinct_column: str | None = None) -> SampleResult:
    """PRD §7.2's statistics engine needs actual data, not just metadata."""
    if item.kind == "raster":
        raise ConnectorError("Statistics aren't available for rasters  -  PRD §7.2 covers vector/tabular data.")

    root = Path(config.folder)
    file_path = root / item.path

    if distinct_column is not None:
        # Read attributes in bounded chunks through the same pandas/OGR readers.
        # Stop once the distinct budget is exceeded; discovery then keeps its
        # original row sample. No ordering or replacement sample is introduced.
        values = set()
        def add(frame):
            for value in frame[distinct_column].dropna():
                try:
                    values.add(value)
                except TypeError:
                    continue
                if len(values) > limit:
                    return True
            return False
        if file_path.suffix.lower() == ".csv":
            with pd.read_csv(file_path, usecols=[distinct_column], chunksize=10000) as chunks:
                for frame in chunks:
                    if add(frame):
                        break
        else:
            offset = 0
            while True:
                frame = pyogrio.read_dataframe(file_path, layer=item.name if file_path.suffix.lower() == ".gpkg" else None,
                    columns=[distinct_column], read_geometry=False, skip_features=offset, max_features=10000)
                if add(frame) or len(frame) < 10000:
                    break
                offset += len(frame)
        return SampleResult(pd.DataFrame({distinct_column: list(values)[:limit]}), len(values) > limit)

    if item.kind == "vector":
        import geopandas as gpd

        is_geopackage = file_path.suffix.lower() == ".gpkg"
        try:
            gdf = gpd.read_file(file_path, layer=item.name if is_geopackage else None, rows=slice(0, limit + 1))
        except Exception as exc:  # pragma: no cover - corrupt/unreadable file
            raise ConnectorError(f"Could not read {item.path}: {exc}") from exc

        is_sample = len(gdf) > limit
        gdf = gdf.iloc[:limit]
        centroids = gdf.geometry.centroid
        df = pd.DataFrame(gdf.drop(columns=[gdf.geometry.name]))
        df["__cx"] = centroids.x
        df["__cy"] = centroids.y
        df["__geom_null"] = gdf.geometry.isna()
        return SampleResult(
            dataframe=df, is_sample=is_sample, geometry_columns=("__cx", "__cy"), null_geometry_column="__geom_null"
        )

    # tabular (CSV, or a geometry-less GeoPackage table)
    df = _read_tabular(file_path, item, nrows=limit + 1)
    is_sample = len(df) > limit
    return SampleResult(dataframe=df.iloc[:limit], is_sample=is_sample)


@timed_phase("fetch")
def raster_detail(config: FilesConnectionConfig, item: DataItem, *, full: bool = False):
    """PRD §8 raster fields + per-band statistics, read with Rasterio."""
    from tarsier.raster.analyze import analyze_raster_file

    if item.kind != "raster":
        raise ConnectorError("Raster detail needs a raster item.")
    try:
        return analyze_raster_file(Path(config.folder) / item.path, full=full)
    except Exception as exc:  # pragma: no cover - corrupt/unreadable file
        raise ConnectorError(f"Could not read {item.path}: {exc}") from exc


@timed_phase("fetch", observe_rows=True)
def sample_geometries(config: FilesConnectionConfig, item: DataItem, limit: int = 1000) -> GeometrySample:
    if item.kind != "vector":
        raise ConnectorError("Geometry quality checks need a vector layer.")

    import geopandas as gpd

    root = Path(config.folder)
    file_path = root / item.path
    is_geopackage = file_path.suffix.lower() == ".gpkg"
    try:
        gdf = gpd.read_file(file_path, layer=item.name if is_geopackage else None, rows=slice(0, limit + 1))
    except Exception as exc:  # pragma: no cover - corrupt/unreadable file
        raise ConnectorError(f"Could not read {item.path}: {exc}") from exc
    is_sample = len(gdf) > limit
    return GeometrySample(geodataframe=gdf.iloc[:limit].copy(), is_sample=is_sample)


@timed_phase("fetch", observe_rows=True)
def sample_id_values(config: FilesConnectionConfig, item: DataItem) -> IdColumnSample | None:
    if item.kind == "raster":
        return None
    root = Path(config.folder)
    file_path = root / item.path
    if item.kind == "tabular":
        header = _read_tabular(file_path, item, nrows=0)
        column = find_id_column(list(header.columns))
        if column is None:
            return None
        values = _read_tabular(file_path, item, usecols=[column])[column]
        return IdColumnSample(column=column, values=values)

    import geopandas as gpd

    is_geopackage = file_path.suffix.lower() == ".gpkg"
    try:
        gdf = gpd.read_file(file_path, layer=item.name if is_geopackage else None)
    except Exception as exc:  # pragma: no cover
        raise ConnectorError(f"Could not read {item.path}: {exc}") from exc
    column = find_id_column([c for c in gdf.columns if c != gdf.geometry.name])
    if column is None:
        return None
    return IdColumnSample(column=column, values=gdf[column])
