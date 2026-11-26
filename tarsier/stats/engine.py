"""Per-column statistics and the data-quality flags Feature B wants
alongside them (PRD §7.2). Connector-agnostic: every connector's
`sample_rows()` returns the same shape (a pandas DataFrame plus, for
vector items, a parallel centroid_x/centroid_y/geom_is_null set of
columns), so this module never needs to know which connector the data
came from.

See TAD "Statistics engine methodology" for the locked formulas
(IQR out-of-range, messy categories, MAD spatial outliers) and the
Phase 3 rule that each flag stores the matching sample rows, not
counts only.
"""

from tarsier.timing import timed_phase
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
import json

import numpy as np
import pandas as pd

OUTLIER_IQR_MULTIPLIER = 1.5
SPATIAL_OUTLIER_MAD_MULTIPLIER = 3.0
HISTOGRAM_BINS = 15
EMPTY_WARNING_SHARE = 0.20


@dataclass(frozen=True)
class ColumnStats:
    name: str
    is_numeric: bool
    minimum: float | str | None = None
    maximum: float | str | None = None
    average: float | None = None
    empty_count: int = 0
    unique_count: int = 0
    top_values: list[tuple[str, int]] = field(default_factory=list)
    messy_groups: list[list[str]] = field(default_factory=list)
    out_of_range_count: int | None = None  # numeric columns only
    histogram: list[dict] | None = None  # numeric: {start, end, count} × 15


@dataclass(frozen=True)
class TableStats:
    sampled_row_count: int
    is_sample: bool
    columns: list[ColumnStats]
    duplicate_row_count: int
    null_geometry_count: int | None = None  # vector items only
    spatial_outlier_count: int | None = None  # vector items only
    messy_category_rows: list[dict] = field(default_factory=list)
    out_of_range_rows: list[dict] = field(default_factory=list)
    duplicate_rows: list[dict] = field(default_factory=list)
    map_outlier_rows: list[dict] = field(default_factory=list)
    null_geometry_rows: list[dict] = field(default_factory=list)
    sample_details: dict = field(default_factory=dict)


@timed_phase("compute")
def compute_table_stats(
    df: pd.DataFrame,
    is_sample: bool,
    geometry_columns: tuple[str, str] | None = None,  # (centroid_x, centroid_y)
    null_geometry_column: str | None = None,
) -> TableStats:
    geom_cols = tuple(c for c in (geometry_columns or ()) if c in df.columns)
    null_col = null_geometry_column if null_geometry_column in df.columns else None
    attribute_df = df.drop(columns=[c for c in geom_cols + ((null_col,) if null_col else ())])
    for column in attribute_df.columns:
        if not pd.api.types.is_numeric_dtype(attribute_df[column]):
            attribute_df[column] = attribute_df[column].map(_stat_value)

    columns: list[ColumnStats] = []
    messy_mask = pd.Series(False, index=df.index)
    range_mask = pd.Series(False, index=df.index)
    for col in attribute_df.columns:
        stats, messy, outliers = _compute_column_stats(attribute_df[col])
        columns.append(stats)
        messy_mask = messy_mask | messy
        range_mask = range_mask | outliers

    duplicate_mask = attribute_df.duplicated(keep=False) if not attribute_df.empty else pd.Series(False, index=df.index)
    duplicate_row_count = int(attribute_df.duplicated().sum()) if not attribute_df.empty else 0

    null_geometry_count = None
    null_mask = pd.Series(False, index=df.index)
    if null_col:
        null_mask = df[null_col].fillna(False).astype(bool)
        null_geometry_count = int(null_mask.sum())

    spatial_outlier_count = None
    spatial_mask = pd.Series(False, index=df.index)
    if len(geom_cols) == 2:
        spatial_mask = _spatial_outlier_mask(df[geom_cols[0]], df[geom_cols[1]])
        spatial_outlier_count = int(spatial_mask.sum())

    return TableStats(
        sampled_row_count=len(df),
        is_sample=is_sample,
        columns=columns,
        duplicate_row_count=duplicate_row_count,
        null_geometry_count=null_geometry_count,
        spatial_outlier_count=spatial_outlier_count,
        messy_category_rows=_rows(df, messy_mask, geom_cols, null_col),
        out_of_range_rows=_rows(df, range_mask, geom_cols, null_col),
        duplicate_rows=_rows(df, duplicate_mask, geom_cols, null_col),
        map_outlier_rows=_rows(df, spatial_mask, geom_cols, null_col),
        null_geometry_rows=_rows(df, null_mask, geom_cols, null_col),
    )


def _compute_column_stats(series: pd.Series) -> tuple[ColumnStats, pd.Series, pd.Series]:
    empty = series.isna() | series.map(lambda value: isinstance(value, str) and not value.strip())
    empty_count = int(empty.sum())
    non_null = series[~empty]
    is_numeric = pd.api.types.is_numeric_dtype(series)
    top_values = [(str(v), int(c)) for v, c in non_null.value_counts().head(5).items()]
    messy_mask = pd.Series(False, index=series.index)
    outlier_mask = pd.Series(False, index=series.index)

    if is_numeric:
        outlier_mask = _numeric_outlier_mask(series)
        return (
            ColumnStats(
                name=str(series.name),
                is_numeric=True,
                minimum=float(non_null.min()) if not non_null.empty else None,
                maximum=float(non_null.max()) if not non_null.empty else None,
                average=float(non_null.mean()) if not non_null.empty else None,
                empty_count=empty_count,
                unique_count=int(non_null.nunique()),
                top_values=top_values,
                out_of_range_count=int(outlier_mask.sum()),
                histogram=_histogram(non_null),
            ),
            messy_mask,
            outlier_mask,
        )

    text_values = non_null.astype(str)
    messy_groups = _detect_messy_categories(text_values)
    messy_values = {v for group in messy_groups for v in group}
    messy_mask = text_values.isin(messy_values).reindex(series.index, fill_value=False)
    return (
        ColumnStats(
            name=str(series.name),
            is_numeric=False,
            minimum=str(text_values.min()) if not text_values.empty else None,
            maximum=str(text_values.max()) if not text_values.empty else None,
            empty_count=empty_count,
            unique_count=int(text_values.nunique()),
            top_values=top_values,
            messy_groups=messy_groups,
        ),
        messy_mask,
        outlier_mask,
    )


def _numeric_outlier_mask(series: pd.Series) -> pd.Series:
    values = series.dropna()
    mask = pd.Series(False, index=series.index)
    if len(values) < 4:
        return mask
    q1, q3 = values.quantile(0.25), values.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - OUTLIER_IQR_MULTIPLIER * iqr, q3 + OUTLIER_IQR_MULTIPLIER * iqr
    return (series < lower) | (series > upper)


def _histogram(values: pd.Series) -> list[dict]:
    if values.empty:
        return []
    vmin, vmax = float(values.min()), float(values.max())
    if vmin == vmax:
        return [{"start": vmin, "end": vmax, "count": int(len(values))}]
    counts, edges = np.histogram(values.astype(float), bins=HISTOGRAM_BINS)
    return [
        {"start": float(edges[i]), "end": float(edges[i + 1]), "count": int(counts[i])}
        for i in range(HISTOGRAM_BINS)
    ]


def _detect_messy_categories(values: pd.Series) -> list[list[str]]:
    distinct = values.unique().tolist()
    normalized: dict[str, list[str]] = {}
    for v in distinct:
        key = v.strip().lower()
        normalized.setdefault(key, []).append(v)

    groups = [variants for variants in normalized.values() if len(variants) > 1]

    seen_in_group = {v for g in groups for v in g}
    normalized_keys = set(normalized.keys())
    for short, long_form in _COMMON_ABBREVIATIONS.items():
        if short in normalized_keys and long_form in normalized_keys:
            pair = [normalized[short][0], normalized[long_form][0]]
            if not any(p in seen_in_group for p in pair):
                groups.append(pair)
                seen_in_group.update(pair)

    return groups


_COMMON_ABBREVIATIONS = {
    "rd": "road", "st": "street", "ave": "avenue", "blvd": "boulevard",
    "ln": "lane", "dr": "drive", "ct": "court", "pl": "place",
    "hwy": "highway", "pkwy": "parkway", "sq": "square", "ter": "terrace",
    "cir": "circle", "mt": "mount", "ft": "fort",
}


def _spatial_outlier_mask(centroid_x: pd.Series, centroid_y: pd.Series) -> pd.Series:
    mask = pd.Series(False, index=centroid_x.index)
    valid = centroid_x.notna() & centroid_y.notna()
    x, y = centroid_x[valid], centroid_y[valid]
    if len(x) < 4:
        return mask
    center_x, center_y = x.median(), y.median()
    distances = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
    mad = (distances - distances.median()).abs().median()
    if mad == 0:
        return mask
    threshold = distances.median() + SPATIAL_OUTLIER_MAD_MULTIPLIER * mad
    mask.loc[distances[distances > threshold].index] = True
    return mask


def _count_spatial_outliers(centroid_x: pd.Series, centroid_y: pd.Series) -> int:
    return int(_spatial_outlier_mask(centroid_x, centroid_y).sum())


def _rows(df: pd.DataFrame, mask: pd.Series, geom_cols: tuple[str, ...], null_col: str | None) -> list[dict]:
    if not mask.any():
        return []
    return [_public_row(row, geom_cols, null_col) for row in df.loc[mask].to_dict(orient="records")]


def _public_row(row: dict, geom_cols: tuple[str, ...], null_col: str | None) -> dict:
    public = {}
    for key, value in row.items():
        if geom_cols and key == geom_cols[0]:
            public["centroid_x"] = _cell(value)
        elif geom_cols and len(geom_cols) > 1 and key == geom_cols[1]:
            public["centroid_y"] = _cell(value)
        elif key == null_col:
            public["geometry_missing"] = bool(value)
        else:
            public[key] = _cell(value)
    return public


def _stat_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "0x" + bytes(value).hex()
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, sort_keys=True, default=str)
    return value


def _cell(value):
    value = _stat_value(value)
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    return value
