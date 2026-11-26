"""Apply an AI-produced structured filter to a sampled DataFrame.

The model never runs this  -  Tarsier does, on the same read-only
`sample_rows()` frame the statistics engine uses (TAD §7.2).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

ALLOWED_OPS = {"=", "!=", "<", "<=", ">", ">=", "is_null", "is_not_null"}


class FilterError(Exception):
    """The filter was malformed or named a column that isn't on this table."""


@dataclass(frozen=True)
class StructuredFilter:
    caption: str
    combine: str  # "and" | "or"
    conditions: list[dict]


def parse_filter_payload(payload: dict, allowed_columns: set[str]) -> StructuredFilter:
    if not isinstance(payload, dict):
        raise FilterError("The AI reply was not a filter object.")
    conditions = payload.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise FilterError("The AI did not return any filter conditions.")
    combine = str(payload.get("combine") or "and").lower()
    if combine not in ("and", "or"):
        raise FilterError("The AI filter must combine conditions with AND or OR.")

    cleaned = []
    for raw in conditions:
        if not isinstance(raw, dict):
            raise FilterError("Each filter condition must be an object.")
        column = str(raw.get("column") or "").strip()
        op = str(raw.get("op") or "").strip().lower().replace(" ", "_")
        if op == "eq":
            op = "="
        elif op == "neq":
            op = "!="
        elif op == "lt":
            op = "<"
        elif op == "lte":
            op = "<="
        elif op == "gt":
            op = ">"
        elif op == "gte":
            op = ">="
        if column not in allowed_columns:
            raise FilterError(f"The filter named a column that isn't on this table: {column!r}.")
        if op not in ALLOWED_OPS:
            raise FilterError(f"Unsupported filter operation: {op!r}.")
        condition = {"column": column, "op": op}
        if op not in ("is_null", "is_not_null"):
            if "value" not in raw:
                raise FilterError(f"Filter on {column} is missing a value.")
            if raw["value"] is None or isinstance(raw["value"], (dict, list)):
                raise FilterError("Comparisons need a single value. Use IS NULL for empty values.")
            condition["value"] = raw["value"]
        cleaned.append(condition)

    # Describe the validated operation rather than trusting a model's prose.
    caption = _caption(cleaned, combine)
    return StructuredFilter(caption=caption, combine=combine, conditions=cleaned)


def apply_filter(df: pd.DataFrame, spec: StructuredFilter) -> pd.DataFrame:
    if df.empty:
        return df
    masks = [_condition_mask(df, c) for c in spec.conditions]
    combined = masks[0]
    for extra in masks[1:]:
        combined = combined & extra if spec.combine == "and" else combined | extra
    return df.loc[combined]


def _condition_mask(df: pd.DataFrame, condition: dict) -> pd.Series:
    series = df[condition["column"]]
    op = condition["op"]
    if op == "is_null":
        return series.isna()
    if op == "is_not_null":
        return series.notna()
    value = condition["value"]
    numeric_value = _as_number(value)
    if pd.api.types.is_numeric_dtype(series) and numeric_value is not None:
        comparable, value = pd.to_numeric(series, errors="coerce"), numeric_value
    elif isinstance(value, str):
        comparable, value = series.astype("string"), value
    else:
        comparable = series

    if op == "=":
        return comparable == value
    if op == "!=":
        return comparable != value
    if op == "<":
        return comparable < value
    if op == "<=":
        return comparable <= value
    if op == ">":
        return comparable > value
    if op == ">=":
        return comparable >= value
    raise FilterError(f"Unsupported filter operation: {op!r}.")


def _as_number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return int(value) if value.strip().lstrip("-").isdigit() else float(value)
        except ValueError:
            return None
    return None


def _caption(conditions: list[dict], combine: str) -> str:
    parts = []
    for c in conditions:
        if c["op"] == "is_null":
            parts.append(f"{c['column']} IS NULL")
        elif c["op"] == "is_not_null":
            parts.append(f"{c['column']} IS NOT NULL")
        elif isinstance(c.get("value"), str):
            parts.append(f"{c['column']} {c['op'].upper() if c['op'] in ('=', '!=') else c['op']} {c['value']!r}")
        else:
            parts.append(f"{c['column']} {c['op']} {c['value']}")
    joiner = " AND " if combine == "and" else " OR "
    return joiner.join(parts)
