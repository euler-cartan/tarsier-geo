"""Discovery rules for the connection flowchart (PRD §7.8, TAD §3)."""

from tarsier.timing import timed_run
import re
from collections import defaultdict
from typing import Any
from numbers import Integral

from tarsier.connectors.base import DataItem
from tarsier.connectors.registry import get_connector
from tarsier.storage import connections as connection_storage

SAMPLE_LIMIT = 1000
MIN_OVERLAP = 0.80
MIN_DISTINCT_VALUES = 5
EXCLUDED_GUESS_COLUMNS = frozenset({"objectid", "oid", "fid", "gid", "id", "pagenumber"})
GUESS_COLUMN_PREFIXES = ("from_", "to_", "new_", "old_", "feature_", "new", "old")


class DiscoveryLinks(list):
    """Keep uncertain candidates separate from positive edges."""
    def __init__(self):
        super().__init__()
        self.could_not_verify = 0

    def extend(self, links):
        self.could_not_verify += getattr(links, "could_not_verify", 0)
        super().extend(links)


class ColumnValues(dict):
    def __init__(self, *args, connector, config, item, **kwargs):
        super().__init__(*args, **kwargs)
        self.connector, self.config, self.item = connector, config, item
        self.details = {}


def _option_a(left, lc, right, rc):
    """Return qualifying/not qualifying/unknown, without sampling the lookup side."""
    lv, rv = _matching_sets(left[lc], right[rc])
    if min(len(lv), len(rv)) < MIN_DISTINCT_VALUES:
        return False
    li, ri = left.details[lc], right.details[rc]
    if li["complete"] and ri["complete"]:
        return len(lv & rv) / min(len(lv), len(rv)) >= MIN_OVERLAP
    le = len(lv) if li["complete"] else li.get("estimate")
    re = len(rv) if ri["complete"] else ri.get("estimate")
    if le is not None and re is not None:
        left_rank, right_rank = (le,), (re,)
    else:
        # A truncated sample's size is only a lower bound. Do not compare
        # that bound to the other side's catalog NDV as though both were estimates.
        left_rank = (not li["complete"], len(lv), li.get("row_estimate") or float("inf"))
        right_rank = (not ri["complete"], len(rv), ri.get("row_estimate") or float("inf"))
    source, sc, target, tc = (left, lc, right, rc) if left_rank <= right_rank else (right, rc, left, lc)
    probe = getattr(target.connector, "probe_column_values", None)
    if probe is None:
        # A bounded sample cannot establish that the full column has no match.
        return None
    return probe(target.config, target.item, tc, source[sc], source.details[sc].get("type"))


def _normal_column(name: str) -> str:
    return re.sub(r"\s+", "_", name.strip().lower()).strip("_")


def _guess_column_name(name: str) -> str:
    normalized = _normal_column(name)
    for prefix in GUESS_COLUMN_PREFIXES:
        if normalized.startswith(prefix):
            return normalized[len(prefix):]
    return normalized


def _values_for_column(frame, column: str) -> set[Any]:
    values: set[Any] = set()
    raw = frame.attrs.get("integer_values", {}).get(column, frame[column].tolist())
    for value in raw:
        if value is None:
            continue
        try:
            if value != value:  # NaN
                continue
            hash(value)
        except (TypeError, ValueError):
            continue
        values.add(value.item() if hasattr(value, "item") else value)
    return values


def _matching_sets(left: set[Any], right: set[Any]) -> tuple[set[Any], set[Any]]:
    """Only the approved text/non-negative-whole-number boundary is coerced."""
    def text(values):
        return bool(values) and all(isinstance(v, str) for v in values)
    def integers(values):
        return bool(values) and all(isinstance(v, Integral) and not isinstance(v, bool) for v in values)
    def digits(values):
        return {v.strip() for v in values if v.strip() and all("0" <= c <= "9" for c in v.strip())}
    if text(left) and integers(right):
        return digits(left), {str(v) for v in right if v >= 0}
    if integers(left) and text(right):
        return {str(v) for v in left if v >= 0}, digits(right)
    return left, right


def _item_key(schema: str, name: str) -> tuple[str, str]:
    return schema or "", name


def guess_between(
    left_item: DataItem,
    left_values: dict[str, set[Any]],
    left_sample: bool,
    right_item: DataItem,
    right_values: dict[str, set[Any]],
    right_sample: bool,
    official_keys: set | None = None,
) -> list[dict]:
    """The locked TAD connection-guess rule for one pair of items: same normalized
    column name (after the approved prefix strip), neither an excluded internal
    column, >=5 distinct values each side, >=80% of the smaller set shared.
    Used identically within one connection and across connections (PRD §14.10).
    """
    guesses = DiscoveryLinks()
    left_names: dict[str, list[str]] = defaultdict(list)
    right_names: dict[str, list[str]] = defaultdict(list)
    for name in left_values:
        left_names[_guess_column_name(name)].append(name)
    for name in right_values:
        right_names[_guess_column_name(name)].append(name)
    for normalized in left_names.keys() & right_names.keys():
        if normalized in EXCLUDED_GUESS_COLUMNS:
            continue
        for left_column in left_names[normalized]:
            for right_column in right_names[normalized]:
                relation_key = (
                    left_item.schema, left_item.name, left_column,
                    right_item.schema, right_item.name, right_column,
                )
                reverse_key = relation_key[3:] + relation_key[:3]
                if official_keys and (relation_key in official_keys or reverse_key in official_keys):
                    continue
                if isinstance(left_values, ColumnValues) and isinstance(right_values, ColumnValues):
                    qualifies = _option_a(left_values, left_column, right_values, right_column)
                else:
                    left_set, right_set = _matching_sets(left_values[left_column], right_values[right_column])
                    qualifies = (min(len(left_set), len(right_set)) >= MIN_DISTINCT_VALUES
                                 and len(left_set & right_set) / min(len(left_set), len(right_set)) >= MIN_OVERLAP)
                if qualifies is None:
                    guesses.could_not_verify += 1
                    continue
                if not qualifies:
                    continue
                guesses.append({
                    "source_schema": left_item.schema,
                    "source_name": left_item.name,
                    "source_column": left_column,
                    "target_schema": right_item.schema,
                    "target_name": right_item.name,
                    "target_column": right_column,
                    "kind": "guessed", "status": "guessed",
                    "sample_based": (not (left_values.details[left_column]["complete"] and right_values.details[right_column]["complete"])
                                     if isinstance(left_values, ColumnValues) and isinstance(right_values, ColumnValues) else left_sample or right_sample),
                })
    return guesses


def sample_item_values(connector, config, items: list[DataItem]) -> tuple[list[tuple[DataItem, dict[str, set[Any]], bool]], dict]:
    """Capture complete or bounded distinct sets and their direction metadata."""
    samples = []
    columns_by_item: dict[tuple[str, str], set[str]] = defaultdict(set)
    sample_rows = getattr(connector, "sample_rows", None)
    if not sample_rows:
        return samples, columns_by_item
    for item in items:
        if item.kind == "raster":
            continue
        result = sample_rows(config, item, limit=SAMPLE_LIMIT)
        names = [str(c) for c in result.dataframe.columns if c not in {"__cx", "__cy", "__geom_null"}]
        columns_by_item[_item_key(item.schema, item.name)].update(names)
        import inspect
        has_distinct = "distinct_column" in inspect.signature(sample_rows).parameters
        values = ColumnValues({name: _values_for_column(result.dataframe, name) for name in names}, connector=connector, config=config, item=item)
        metadata = getattr(connector, "column_guess_metadata", lambda *_: {})(config, item)
        for name in names:
            values.details[name] = {"complete": not result.is_sample, **metadata.get(name, {})}
        # Distinct lookahead establishes completeness without full NDV counts.
        if has_distinct:
            for name in names:
                if _guess_column_name(name) in EXCLUDED_GUESS_COLUMNS:
                    continue
                distinct = sample_rows(config, item, limit=SAMPLE_LIMIT, distinct_column=name)
                values[name] = _values_for_column(distinct.dataframe, name)
                values.details[name]["complete"] = not distinct.is_sample
        samples.append((item, values if has_distinct else dict(values), result.is_sample))
    return samples, columns_by_item


@timed_run("link_guessing")
def discover_links(connection_id: str) -> tuple[list[dict], list[dict]]:
    saved = connection_storage.get_connection(connection_id)
    if saved is None:
        raise ValueError("No such connection.")
    connector = get_connector(saved.type)
    config = connector.build_config(saved.config, connection_storage.get_connection_password(connection_id))
    items = connector.list_items(config)
    item_keys = {_item_key(item.schema, item.name) for item in items}
    found = DiscoveryLinks()
    official_keys: set[tuple[str, str, str, str, str, str]] = set()
    columns_by_item: dict[tuple[str, str], set[str]] = defaultdict(set)

    list_foreign_keys = getattr(connector, "list_foreign_keys", None)
    if list_foreign_keys:
        for foreign_key in list_foreign_keys(config):
            source = _item_key(foreign_key["source_schema"], foreign_key["source_name"])
            target = _item_key(foreign_key["target_schema"], foreign_key["target_name"])
            if source in item_keys and target in item_keys:
                official_keys.add((source[0], source[1], foreign_key["source_column"], target[0], target[1], foreign_key["target_column"]))
                found.append({
                    **foreign_key,
                    "kind": "official", "status": "confirmed", "sample_based": False,
                })

    list_item_columns = getattr(connector, "list_item_columns", None)
    if list_item_columns:
        for item in items:
            columns_by_item[_item_key(item.schema, item.name)].update(list_item_columns(config, item))

    samples, sampled_columns = sample_item_values(connector, config, items)
    for key, names in sampled_columns.items():
        columns_by_item[key].update(names)
    if samples:
        for index, (left_item, left_values, left_sample) in enumerate(samples):
            for right_item, right_values, right_sample in samples[index + 1:]:
                if _item_key(left_item.schema, left_item.name) == _item_key(right_item.schema, right_item.name):
                    continue
                found.extend(
                    guess_between(left_item, left_values, left_sample, right_item, right_values, right_sample, official_keys)
                )
    nodes = [{
        "schema": item.schema, "name": item.name, "kind": item.kind,
        "columns": sorted(columns_by_item.get(_item_key(item.schema, item.name), set())),
    } for item in items]
    return nodes, found


@timed_run("cross_link_guessing")
def discover_cross_connection_links() -> tuple[list[dict], list[str]]:
    """PRD §14.10: the same guess rule, applied between items of *different* connections.

    Returns (guesses, skipped) where each guess also carries source_connection_id /
    target_connection_id, and `skipped` lists connections that could not be read
    (so one unreachable source never blocks the rest). No location-based matching:
    only column names and value overlap, exactly as within one connection.
    """
    sampled: list[tuple[str, str, list]] = []  # (connection_id, name, samples)
    skipped: list[str] = []
    for saved in connection_storage.list_connections():
        try:
            connector = get_connector(saved.type)
            config = connector.build_config(saved.config, connection_storage.get_connection_password(saved.id))
            samples, _ = sample_item_values(connector, config, connector.list_items(config))
        except Exception:
            skipped.append(saved.name)
            continue
        sampled.append((saved.id, saved.name, samples))

    found = DiscoveryLinks()
    for index, (left_id, _left_name, left_samples) in enumerate(sampled):
        for right_id, _right_name, right_samples in sampled[index + 1:]:
            for left_item, left_values, left_sample in left_samples:
                for right_item, right_values, right_sample in right_samples:
                    candidates = guess_between(left_item, left_values, left_sample, right_item, right_values, right_sample)
                    found.could_not_verify += candidates.could_not_verify
                    for guess in candidates:
                        found.append({**guess, "source_connection_id": left_id, "target_connection_id": right_id})
    return found, skipped
