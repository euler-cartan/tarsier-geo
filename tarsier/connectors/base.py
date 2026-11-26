"""Shared shapes used by every connector (TAD §10's connectors/ package).

Each connector type (postgis, oracle, sqlserver, files, arcgis, geoserver)
returns listings in this common shape, per PRD §6's vector/raster/tabular
distinction, so the rest of the app doesn't need to know which connector
produced an item.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import pandas as pd

if TYPE_CHECKING:
    import geopandas as gpd

DataKind = Literal["vector", "raster", "tabular"]

ID_COLUMN_CANDIDATES = ("id", "objectid", "fid", "ogc_fid", "gid")


def find_id_column(column_names: list[str] | tuple[str, ...]) -> str | None:
    """First monotonic-ID-style column, case-insensitive (TAD Phase 4 completeness)."""
    lookup = {name.lower(): name for name in column_names}
    for candidate in ID_COLUMN_CANDIDATES:
        if candidate in lookup:
            return lookup[candidate]
    return None


@dataclass(frozen=True)
class DataItem:
    schema: str
    name: str
    kind: DataKind
    geometry_type: str | None = None
    srid: int | None = None
    # A connector-specific pointer for re-locating this exact item later
    # (describe_item, the detail page). For files: the path relative to the
    # connection's root folder (used instead of `schema`, which files have
    # no concept of). For ArcGIS: the service path + layer/table id, since
    # re-querying it needs more than just the display name.
    path: str | None = None
    # The column holding the geometry, for database connectors that need it
    # to describe the item further (e.g. a bounding box query). Files/ArcGIS/
    # Geoserver don't need this  -  their APIs give bounds without it.
    geometry_column: str | None = None
    readable: bool = True

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.name}" if self.schema else self.name


class ConnectorError(Exception):
    """Raised for any connection or listing failure, with a message safe
    to show a user directly (per FSD §15  -  no raw driver tracebacks)."""


@dataclass(frozen=True)
class ItemMetadata:
    """Overview/detail-page metadata for one item (PRD §7.1, §8).

    Every field is Optional  -  "Not available" is a valid, honest answer
    for a connector/type combination that can't cheaply provide it (FSD
    §15's "not applicable" state), never a guess.
    """

    row_count: int | None = None
    row_count_is_estimate: bool = False
    row_count_is_capped: bool = False
    size_bytes: int | None = None
    has_index: bool | None = None
    bbox: tuple[float, float, float, float] | None = None  # (xmin, ymin, xmax, ymax)
    last_modified: str | None = None  # ISO 8601, only when cheaply available (e.g. file mtime)
    # Raster-specific (PRD §8)  -  populated only by connectors that can read
    # it cheaply from metadata (currently: files).
    raster_width: int | None = None
    raster_height: int | None = None
    raster_band_count: int | None = None
    raster_dtype: str | None = None
    raster_nodata: float | None = None


@dataclass(frozen=True)
class SampleResult:
    """Rows of one item's actual data (PRD §7.2's statistics engine),
    as opposed to ItemMetadata's metadata-only summary.

    `dataframe` never contains the raw geometry column for vector items  -
    only a derived `__cx`/`__cy` centroid pair (named by `geometry_columns`)
    and a `__geom_null` boolean flag (named by `null_geometry_column`), so
    tarsier.stats.engine never needs to parse geometry itself.
    """

    dataframe: pd.DataFrame
    is_sample: bool
    geometry_columns: tuple[str, str] | None = None
    null_geometry_column: str | None = None
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class GeometrySample:
    """Rows plus raw geometry for Feature C quality checks (TAD Phase 4)."""

    geodataframe: "gpd.GeoDataFrame"
    is_sample: bool
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class IdColumnSample:
    """Full values of a monotonic integer ID column (completeness)."""

    column: str
    values: pd.Series
    # True when only the lowest IDs were read because the table is very large.
    is_sample: bool = False


def sample_frame(rows, *, columns=None, integer_columns=()):
    """Keep exact declared integer values available to link discovery.

    Pandas may otherwise turn a nullable BIGINT column into imprecise floats.
    Statistics retain their existing dataframe; only discovery reads this metadata.
    """
    frame = pd.DataFrame(rows, columns=columns)
    frame.attrs["integer_values"] = {
        name: [None if row.get(name) is None else int(row[name]) for row in rows]
        for name in integer_columns if name in frame.columns and len(rows) <= 1000
    }
    return frame
