"""Quality-check formulas (TAD Phase 4 / PRD §7.3). Connector-agnostic."""

from __future__ import annotations

from tarsier.timing import timed_phase
import dataclasses
import math
import multiprocessing
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import pandas as pd
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon
from shapely.ops import unary_union

from tarsier.stats.engine import _cell, _public_row
from tarsier.connectors.base import ConnectorError

COMPARISONS = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "=", "ne": "!="}
NEW_RULE_OPERATORS = frozenset({*("column_" + op for op in COMPARISONS), "matches", "not_matches", "is_unique"})
RULE_OPERATORS = frozenset({*COMPARISONS, "is_null", "is_not_null", *NEW_RULE_OPERATORS})
PATTERN_TIMEOUT_SECONDS = 300


def _pattern_worker(values, pattern, output):
    try:
        compiled = re.compile(pattern)
        output.send([False if value is None else bool(compiled.search(value)) for value in values])
    finally:
        output.close()


def _pattern_mask(series, pattern):
    try:
        re.compile(pattern)
    except (re.error, OverflowError) as exc:
        raise ConnectorError("Invalid regular expression. Check the text pattern.") from exc
    # Python's regex engine has no timeout. A bounded worker prevents a valid
    # but pathological expression from hanging the API or its scheduler.
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    worker = context.Process(target=_pattern_worker, args=(
        [None if pd.isna(v) else str(v) for v in series], pattern, sender), daemon=True)
    worker.start(); sender.close()
    try:
        if not receiver.poll(PATTERN_TIMEOUT_SECONDS):
            raise ConnectorError("Text pattern evaluation reached the five-minute limit. Simplify the pattern or use a sample.")
        try:
            return pd.Series(receiver.recv(), index=series.index, dtype=bool)
        except EOFError as exc:
            raise ConnectorError("Text pattern evaluation could not finish. Simplify the pattern or use a sample.") from exc
    finally:
        receiver.close()
        if worker.is_alive(): worker.terminate()
        worker.join()

SLIVER_COMPACTNESS = 0.05
SMALL_AREA_SHARE = 0.01
DANGLE_TOLERANCE_SHARE = 0.001

VECTOR_CHECKS = (
    "validity",
    "overlaps",
    "slivers",
    "gaps",
    "dangles",
    "completeness",
    "projection",
    "boundary",
    "custom_rules",
)
TABULAR_CHECKS = ("completeness", "custom_rules")
GEOMETRY_CHECKS = ("validity", "overlaps", "slivers", "gaps", "dangles", "boundary", "custom_rules")
CheckStatus = Literal["good", "sampled", "warning", "danger", "not_applicable", "never_run"]


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    status: CheckStatus
    fail_count: int = 0
    message: str | None = None
    failing_rows: list[dict] = field(default_factory=list)
    is_sample: bool = False
    scanned_at: str | None = None
    completeness_score: int | None = None
    skipped_count: int = 0
    sample_details: dict = field(default_factory=dict)

    def __post_init__(self):
        # Also normalizes older cached sample results at the read boundary.
        if self.is_sample and self.status in {"good", "sampled"}:
            object.__setattr__(self, "status", "sampled")
            object.__setattr__(self, "message", "none found in sample, not a full check")
        elif self.is_sample and self.message and not self.message.startswith("Sample-based: "):
            object.__setattr__(self, "message", "Sample-based: " + self.message)


def applicable_checks(kind: str) -> tuple[str, ...]:
    if kind == "vector":
        return VECTOR_CHECKS
    if kind == "tabular":
        return TABULAR_CHECKS
    return ()


def never_run_result(check_id: str) -> CheckResult:
    return CheckResult(check_id=check_id, status="never_run")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finished(
    check_id: str,
    rows: list[dict],
    *,
    is_sample: bool = False,
    message: str | None = None,
    status: CheckStatus | None = None,
    completeness_score: int | None = None,
    skipped_count: int = 0,
) -> CheckResult:
    if status is None:
        status = "danger" if rows else "good"
    return CheckResult(
        check_id=check_id,
        status=status,
        fail_count=len(rows),
        message=message,
        failing_rows=rows,
        is_sample=is_sample,
        scanned_at=_now(),
        completeness_score=completeness_score,
        skipped_count=skipped_count,
    )


def _na(check_id: str, message: str) -> CheckResult:
    return CheckResult(check_id=check_id, status="not_applicable", message=message, scanned_at=_now())


def geometry_check_applicability(check_id: str, geometry_type: str | None) -> CheckResult | None:
    """Only a definite catalog type can rule out a geometry-specific check.

    Generic/unknown metadata must retain the row-based path: mixed layers can
    contain polygons or lines even when their catalog cannot name one type.
    """
    required = {"overlaps": {"POLYGON", "MULTIPOLYGON"},
                "slivers": {"POLYGON", "MULTIPOLYGON"},
                "gaps": {"POLYGON", "MULTIPOLYGON"},
                "dangles": {"LINESTRING", "MULTILINESTRING"}}
    if check_id not in required or not geometry_type:
        return None
    kind = "".join(geometry_type.upper().split())
    if kind.startswith("3D"):
        kind = kind[2:]
    for suffix in ("ZM", "Z", "M"):
        if kind.endswith(suffix):
            kind = kind[:-len(suffix)]
            break
    known = {"POINT", "MULTIPOINT", "LINESTRING", "MULTILINESTRING",
             "POLYGON", "MULTIPOLYGON", "GEOMETRYCOLLECTION"}
    if kind not in known or kind in required[check_id]:
        return None
    family = "line" if check_id == "dangles" else "polygon"
    return _na(check_id, f"This check applies only to {family} layers.")


def _planar(gdf):
    out = gdf.copy()
    if out.crs is not None:
        out = out.set_crs(None, allow_override=True)
    return out


def _attribute_rows(gdf, mask) -> list[dict]:
    geom_name = gdf.geometry.name
    frame = gdf.drop(columns=[geom_name], errors="ignore").copy()
    centroids = gdf.geometry.centroid
    frame["__cx"] = centroids.x
    frame["__cy"] = centroids.y
    return _rows_from_frame(frame, mask, ("__cx", "__cy"), None)


def _rows_from_frame(df: pd.DataFrame, mask, geom_cols, null_col) -> list[dict]:
    if not mask.any():
        return []
    return [_public_row(row, geom_cols, null_col) for row in df.loc[mask].to_dict(orient="records")]


def _polygon_rows(gdf):
    types = gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    return gdf[gdf.geometry.notna() & types & gdf.geometry.is_valid]


@timed_phase("compute")
def check_validity(gdf, *, is_sample: bool = False) -> CheckResult:
    gdf = _planar(gdf)
    mask = gdf.geometry.notna() & ~gdf.geometry.is_valid
    return _finished("validity", _attribute_rows(gdf, mask), is_sample=is_sample)


@timed_phase("compute")
def check_overlaps(gdf, *, is_sample: bool = False) -> CheckResult:
    gdf = _planar(gdf)
    polys = _polygon_rows(gdf)
    if len(polys) < 2:
        return _na("overlaps", "Need at least two valid polygons.")
    failing = pd.Series(False, index=gdf.index)
    sindex = polys.sindex
    indexes = list(polys.index)
    for i, idx in enumerate(indexes):
        geom = polys.geometry.loc[idx]
        for other_pos in sindex.intersection(geom.bounds):
            other_idx = indexes[other_pos]
            if other_idx <= idx:
                continue
            other = polys.geometry.loc[other_idx]
            if not geom.intersects(other):
                continue
            inter = geom.intersection(other)
            if inter.area > 0:
                failing.loc[idx] = True
                failing.loc[other_idx] = True
    return _finished("overlaps", _attribute_rows(gdf, failing), is_sample=is_sample)


@timed_phase("compute")
def check_slivers(gdf, *, is_sample: bool = False) -> CheckResult:
    gdf = _planar(gdf)
    polys = _polygon_rows(gdf)
    if polys.empty:
        return _na("slivers", "No valid polygons in this layer.")
    areas = polys.geometry.area
    perims = polys.geometry.length
    compactness = pd.Series(0.0, index=polys.index)
    ok = perims > 0
    compactness.loc[ok] = 4 * math.pi * areas[ok] / (perims[ok] ** 2)
    median = float(areas.median())
    if median <= 0:
        return _na("slivers", "Polygon areas are zero.")
    thin = compactness < SLIVER_COMPACTNESS
    small = areas < (SMALL_AREA_SHARE * median)
    sliver = thin & small
    mask = pd.Series(False, index=gdf.index)
    mask.loc[sliver[sliver].index] = True
    return _finished("slivers", _attribute_rows(gdf, mask), is_sample=is_sample)


@timed_phase("compute")
def check_gaps(gdf, *, is_sample: bool = False) -> CheckResult:
    gdf = _planar(gdf)
    polys = _polygon_rows(gdf)
    if polys.empty:
        return _na("gaps", "No valid polygons in this layer.")
    median = float(polys.geometry.area.median())
    if median <= 0:
        return _na("gaps", "Polygon areas are zero.")
    threshold = SMALL_AREA_SHARE * median
    union = unary_union(list(polys.geometry))
    rows = []
    for hole in _interior_holes(union):
        if hole.area < threshold:
            c = hole.centroid
            rows.append({"area": _cell(hole.area), "centroid_x": _cell(c.x), "centroid_y": _cell(c.y)})
    return _finished("gaps", rows, is_sample=is_sample)


def _interior_holes(geom) -> list[Polygon]:
    holes: list[Polygon] = []
    if geom is None or geom.is_empty:
        return holes
    if isinstance(geom, Polygon):
        for ring in geom.interiors:
            holes.append(Polygon(ring))
    elif isinstance(geom, MultiPolygon):
        for part in geom.geoms:
            holes.extend(_interior_holes(part))
    return holes


@timed_phase("compute")
def check_dangles(gdf, *, is_sample: bool = False) -> CheckResult:
    gdf = _planar(gdf)
    lines = gdf[gdf.geometry.notna() & gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    if lines.empty:
        return _na("dangles", "No lines in this layer.")
    minx, miny, maxx, maxy = gdf.total_bounds
    diagonal = math.hypot(maxx - minx, maxy - miny)
    if diagonal == 0 or not math.isfinite(diagonal):
        return _na("dangles", "Layer bounding box has no length.")
    tolerance = DANGLE_TOLERANCE_SHARE * diagonal
    vertices_by_row: dict[Any, list[tuple[float, float]]] = {}
    endpoints_by_row: dict[Any, list[tuple[float, float]]] = {}
    for idx, geom in lines.geometry.items():
        verts, ends = _line_vertices_and_ends(geom)
        vertices_by_row[idx] = verts
        endpoints_by_row[idx] = ends
    cells: dict[tuple[int, int], list] = {}
    for idx, verts in vertices_by_row.items():
        for x, y in verts:
            if math.isfinite(x) and math.isfinite(y):
                cells.setdefault((math.floor(x/tolerance), math.floor(y/tolerance)), []).append((idx,x,y))
    failing = pd.Series(False, index=gdf.index)
    for idx, ends in endpoints_by_row.items():
        for end in ends:
            nearby = False
            if all(math.isfinite(v) for v in end):
                cx, cy = math.floor(end[0]/tolerance), math.floor(end[1]/tolerance)
                nearby = any(other != idx and math.hypot(end[0]-x,end[1]-y) <= tolerance
                    for dx in (-1,0,1) for dy in (-1,0,1)
                    for other,x,y in cells.get((cx+dx,cy+dy), []))
            if not nearby:
                failing.loc[idx] = True
                break
    return _finished("dangles", _attribute_rows(gdf, failing), is_sample=is_sample)


def _line_vertices_and_ends(geom) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    parts = geom.geoms if isinstance(geom, MultiLineString) else (geom,)
    verts: list[tuple[float, float]] = []
    ends: list[tuple[float, float]] = []
    for part in parts:
        if not isinstance(part, LineString) or part.is_empty:
            continue
        coords = list(part.coords)
        verts.extend((float(x), float(y)) for x, y, *_ in coords)
        if coords:
            ends.append((float(coords[0][0]), float(coords[0][1])))
            ends.append((float(coords[-1][0]), float(coords[-1][1])))
    return verts, ends


MISSING_ID_ROWS_LISTED = 1000


@timed_phase("compute")
def check_completeness(id_values: pd.Series | None, column: str | None, *, is_sample: bool = False) -> CheckResult:
    if id_values is None or column is None:
        return _na("completeness", "No integer ID/OBJECTID sequence column on this layer.")
    numeric = pd.to_numeric(id_values, errors="coerce").dropna()
    try:
        ints = numeric.astype(int)
    except (TypeError, ValueError):
        return _na("completeness", f"{column} is not an integer sequence.")
    if ints.empty:
        return _na("completeness", f"{column} has no integer values.")
    if (numeric != ints).any():
        return _na("completeness", f"{column} is not an integer sequence.")
    low, high = int(ints.min()), int(ints.max())
    present = set(ints.tolist())
    span = high - low + 1
    missing_count = span - len(present)
    # Count gaps arithmetically and list only the first few. Walking every
    # integer between the lowest and highest ID never finishes on a sparse
    # key (IDs from 1 to two billion with a few thousand rows).
    rows: list[dict] = []
    if missing_count:
        ordered = sorted(present)
        for before, after in zip(ordered, ordered[1:]):
            for n in range(before + 1, after):
                rows.append({column: n})
                if len(rows) >= MISSING_ID_ROWS_LISTED:
                    break
            if len(rows) >= MISSING_ID_ROWS_LISTED:
                break
    message = None
    if missing_count:
        message = f"Missing {missing_count} value(s) in {column} between {low} and {high}."
        if missing_count > len(rows):
            message += f" Showing the first {len(rows)}."
    score = round(100 * len(present) / span)
    result = _finished("completeness", rows, message=message, is_sample=is_sample, completeness_score=score)
    return dataclasses.replace(result, fail_count=missing_count)


@timed_phase("compute")
def check_projection(item_srid: int | None, majority_srid: int | None) -> CheckResult:
    if majority_srid is None:
        return _na("projection", "No majority CRS on this connection yet.")
    if item_srid is None:
        return _na("projection", "This layer has no CRS.")
    if item_srid == majority_srid:
        return _finished("projection", [])
    return _finished(
        "projection",
        [{"srid": item_srid, "expected_srid": majority_srid}],
        message=f"Layer is EPSG:{item_srid}; most layers on this connection use EPSG:{majority_srid}.",
    )


@timed_phase("compute")
def check_boundary(gdf, boundary_gdf, *, is_sample: bool = False) -> CheckResult:
    if gdf is None or boundary_gdf is None or getattr(boundary_gdf, "empty", True):
        return _na("boundary", "Pick another vector layer on this connection as the expected area.")
    gdf = _planar(gdf)
    boundary_gdf = _planar(boundary_gdf)
    valid = boundary_gdf[boundary_gdf.geometry.notna() & boundary_gdf.geometry.is_valid]
    if valid.empty:
        return _na("boundary", "The boundary layer has no valid geometry.")
    cover = unary_union(list(valid.geometry))
    mask = gdf.geometry.notna() & ~gdf.geometry.apply(lambda geom: cover.covers(geom))
    return _finished("boundary", _attribute_rows(gdf, mask), is_sample=is_sample)


@timed_phase("compute")
def check_custom_rules(gdf_or_df, rules: list[dict], *, is_sample: bool = False) -> CheckResult:
    if not rules:
        return _na("custom_rules", "No custom rules defined for this layer.")
    is_gdf = type(gdf_or_df).__name__ == "GeoDataFrame"
    if is_gdf:
        gdf_or_df = _planar(gdf_or_df)
    frame = gdf_or_df.drop(columns=[gdf_or_df.geometry.name], errors="ignore").copy() if is_gdf else gdf_or_df.copy()
    if is_gdf:
        centroids = gdf_or_df.geometry.centroid
        frame["__cx"] = centroids.x
        frame["__cy"] = centroids.y
        geom_types = gdf_or_df.geometry.geom_type
    else:
        geom_types = None
    failing = pd.Series(False, index=frame.index)
    skipped = pd.Series(False, index=frame.index)
    for rule in rules:
        failing = failing | _rule_fail_mask(frame, geom_types, rule)
        skipped = skipped | _rule_skipped_mask(frame, rule)
    geom_cols = ("__cx", "__cy") if "__cx" in frame.columns else None
    rows = _rows_from_frame(frame, failing, geom_cols, None)
    count = int(skipped.sum())
    extended = any((rule.get("kind") or "attribute") == "attribute" and
                   rule.get("operator") in NEW_RULE_OPERATORS for rule in rules)
    message = f"{count} rows skipped, value empty" if extended else None
    return _finished("custom_rules", rows, is_sample=is_sample, message=message, skipped_count=count)


def _empty_mask(series: pd.Series) -> pd.Series:
    """The existing empty-value check: null, empty string, or whitespace only."""
    return series.isna() | series.map(lambda value: isinstance(value, str) and not value.strip())


def _rule_skipped_mask(frame: pd.DataFrame, rule: dict) -> pd.Series:
    field, operator = rule.get("field"), rule.get("operator")
    if ((rule.get("kind") or "attribute") != "attribute" or
            operator not in NEW_RULE_OPERATORS or field not in frame.columns):
        return pd.Series(False, index=frame.index)
    skipped = _empty_mask(frame[field])
    if operator.startswith("column_") and rule.get("value") in frame.columns:
        skipped = skipped | _empty_mask(frame[rule["value"]])
    return skipped


def _rule_fail_mask(frame: pd.DataFrame, geom_types, rule: dict) -> pd.Series:
    field = rule.get("field")
    kind = rule.get("kind") or "attribute"
    if field not in frame.columns:
        return pd.Series(False, index=frame.index)
    series = frame[field]
    skipped = _rule_skipped_mask(frame, rule)
    operator = rule.get("operator") or "eq"
    if kind == "attribute" and operator in NEW_RULE_OPERATORS:
        # Remove empty operands before comparison/regex/duplicate detection.
        # This also keeps mixed numeric/empty-string input comparable.
        eligible = frame.loc[~skipped]
        when = _when_mask(eligible[field], operator, rule.get("value"), frame=eligible)
        return (~when).reindex(frame.index, fill_value=False)
    when = _when_mask(series, operator, rule.get("value"), frame=frame)
    if kind == "geometry_type":
        if geom_types is None:
            return pd.Series(False, index=frame.index)
        expected = str(rule.get("geometry_type") or "")
        return when & (geom_types.astype(str) != expected)
    # attribute constraint: flag rows that do not satisfy operator/value
    return ~when & ~_rule_skipped_mask(frame, rule)


def _when_mask(series: pd.Series, operator: str, value: str | None, *, frame: pd.DataFrame | None = None) -> pd.Series:
    if operator == "is_unique":
        return series.isna() | ~series.duplicated(keep=False)
    if operator in {"matches", "not_matches"}:
        matched = _pattern_mask(series, value or "")
        return matched if operator == "matches" else (~matched & series.notna())
    if operator.startswith("column_"):
        if frame is None or value not in frame.columns:
            raise ConnectorError("Pick another column from the same table.")
        other = frame[value]
        op = operator.removeprefix("column_")
        try:
            compare = {"gt": series.gt, "gte": series.ge, "lt": series.lt,
                       "lte": series.le, "eq": series.eq, "ne": series.ne}[op]
            return compare(other).fillna(False) & series.notna() & other.notna()
        except (TypeError, ValueError, KeyError) as exc:
            raise ConnectorError("These columns do not have compatible types for this comparison.") from exc
    if operator == "is_null":
        return series.isna() | (series.astype(str).str.strip() == "")
    if operator == "is_not_null":
        return ~(series.isna() | (series.astype(str).str.strip() == ""))
    numeric = pd.to_numeric(series, errors="coerce")
    try:
        target = float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        target = None
    if operator in {"gt", "gte", "lt", "lte"} and target is not None:
        if operator == "gt":
            return numeric > target
        if operator == "gte":
            return numeric >= target
        if operator == "lt":
            return numeric < target
        return numeric <= target
    text = series.astype(str)
    expected = "" if value is None else str(value)
    if operator == "ne":
        return text != expected
    return text == expected


def majority_srid(srids: list[int | None]) -> int | None:
    counts: dict[int, int] = {}
    for srid in srids:
        if srid is None:
            continue
        counts[srid] = counts.get(srid, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)
