"""Plain-English → structured filter (PRD §7.2 job 1, TAD §7.2).

Sends schema only. Applies the returned filter on Tarsier's read-only
sample  -  the model never touches the user's database.
"""

from __future__ import annotations

import json
import re

import pandas as pd

from tarsier.ai.client import AIError, chat
from tarsier.stats.engine import _public_row
from tarsier.stats.filter import FilterError, StructuredFilter, apply_filter, parse_filter_payload

_SYSTEM = """You turn a plain-English question about a table into a structured filter.
You are given column names and types only  -  never row values, never SQL access.
Reply with JSON only, no markdown, no commentary, of this exact shape:
{"caption":"stock_qty < 10 AND warehouse = East","combine":"and","conditions":[{"column":"stock_qty","op":"<","value":10},{"column":"warehouse","op":"=","value":"East"}]}
Allowed op values: =, !=, <, <=, >, >=, is_null, is_not_null.
combine is "and" or "or".
Use only the given column names. Never invent columns. Never output SQL.
Preserve every part of the user's request, including AND/OR, dates, units, and exact comparisons.
If the request is ambiguous, asks to modify data, or needs unsupported operations
(such as joins, grouping, sorting, or nested boolean groups), return
{"unsupported":"Explain what cannot be represented and ask a precise follow-up"}.
Never silently omit part of a request or replace it with a different filter.
"""


def schema_from_frame(df: pd.DataFrame, hidden: set[str]) -> list[dict]:
    columns = []
    for name in df.columns:
        if name in hidden:
            continue
        series = df[name]
        kind = "number" if pd.api.types.is_numeric_dtype(series) else "text"
        columns.append({"name": str(name), "type": kind})
    return columns


def interpret_question(question: str, columns: list[dict]) -> StructuredFilter:
    listing = ", ".join(f"{c['name']} ({c['type']})" for c in columns)
    result = chat(
        [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": f"Columns: {listing}\nQuestion: {question.strip()}",
            },
        ]
    )
    try:
        payload = _extract_json(result.content)
    except (json.JSONDecodeError, ValueError) as exc:
        raise AIError("The AI did not return a usable filter. Try rephrasing the question.") from exc
    allowed = {c["name"] for c in columns}
    if isinstance(payload, dict) and payload.get("unsupported"):
        raise AIError(str(payload["unsupported"])[:600])
    try:
        return parse_filter_payload(payload, allowed)
    except FilterError as exc:
        raise AIError(str(exc)) from exc


def run_filter(
    df: pd.DataFrame,
    spec: StructuredFilter,
    geometry_columns: tuple[str, str] | None,
    null_geometry_column: str | None,
) -> list[dict]:
    hidden = set(geometry_columns or ())
    if null_geometry_column:
        hidden.add(null_geometry_column)
    filtered = apply_filter(df, spec)
    geom = tuple(c for c in (geometry_columns or ()) if c in df.columns)
    null_col = null_geometry_column if null_geometry_column in df.columns else None
    return [_public_row(row, geom, null_col) for row in filtered.to_dict(orient="records")]


def _extract_json(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object")
    return json.loads(stripped[start : end + 1])
