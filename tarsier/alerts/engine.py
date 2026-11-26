"""Pure alert conditions (TAD Phase 6 / PRD §7.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from tarsier.quality.engine import _when_mask, NEW_RULE_OPERATORS
from tarsier.connectors.base import ConnectorError

ROW_COUNT_DROP_SHARE = 0.25
FRESHNESS_DAYS = 90
QUALITY_DROP_POINTS = 10
SIZE_SPIKE_SHARE = 0.50

ALERT_KINDS = (
    "mass_change",
    "row_count_drop",
    "schema_change",
    "freshness",
    "quality_score_drop",
    "specific_user",
    "layer_presence",
    "size_spike",
    "banned_value",
)

KIND_LABELS = {
    "mass_change": "Mass delete / mass edit",
    "row_count_drop": "Row count dropped",
    "schema_change": "Schema changed",
    "freshness": "Layer not updated (freshness)",
    "quality_score_drop": "Quality score dropped",
    "specific_user": "Specific user",
    "layer_presence": "New or dropped layer",
    "size_spike": "Size grew abnormally",
    "banned_value": "Banned value appeared",
}


@dataclass(frozen=True)
class AlertMatch:
    message: str
    details: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.details.get("is_sample") and "sample-based" not in self.message:
            object.__setattr__(self, "message", self.message + " (sample-based; not a full check)")


@dataclass
class AlertContext:
    items: list[dict]
    previous_items: list[dict] | None
    events: list[dict]
    quality_scores: dict[str, int]
    previous_quality: dict[str, int]
    now: datetime
    sample_values: dict[str, list] | None = None  # field -> values
    sample_rows: dict[str, dict] | None = None  # qualified target -> bounded current rows
    quality_samples: dict[str, bool] = field(default_factory=dict)
    previous_quality_samples: dict[str, bool] = field(default_factory=dict)


def quality_score(checks: dict) -> int | None:
    ran = [c for c in checks.values() if getattr(c, "status", None) not in ("never_run", "not_applicable")]
    if not ran:
        return None
    good = sum(1 for c in ran if c.status in {"good", "sampled"})
    return round(100 * good / len(ran))


def item_key(schema: str, name: str) -> str:
    return f"{schema}.{name}" if schema else name


def _target_ok(config: dict, schema: str, name: str) -> bool:
    want_schema = config.get("target_schema") or ""
    want_name = config.get("target_name") or ""
    if want_name and name != want_name:
        return False
    if want_schema and schema != want_schema:
        return False
    return True


def _prev_map(previous: list[dict] | None) -> dict[str, dict]:
    if not previous:
        return {}
    return {item_key(i.get("schema") or "", i["name"]): i for i in previous}


def evaluate_rule(kind: str, config: dict, ctx: AlertContext) -> list[AlertMatch]:
    if kind == "banned_value" and config.get("operator") == "is_unique":
        raise ConnectorError("IS UNIQUE is available only for quality rules, not alerts.")
    if ctx.previous_items is None and kind in {
        "row_count_drop",
        "layer_presence",
        "size_spike",
        "quality_score_drop",
    }:
        return []
    runners = {
        "mass_change": _mass,
        "row_count_drop": _row_drop,
        "schema_change": _schema,
        "freshness": _freshness,
        "quality_score_drop": _quality_drop,
        "specific_user": _user,
        "layer_presence": _presence,
        "size_spike": _size,
        "banned_value": _banned,
    }
    return runners[kind](config, ctx)


def _mass(config: dict, ctx: AlertContext) -> list[AlertMatch]:
    matches = []
    for event in ctx.events:
        if not event.get("is_mass"):
            continue
        if not _target_ok(config, event.get("schema") or "", event.get("name") or ""):
            continue
        matches.append(
            AlertMatch(
                f"Mass {event.get('action')} on {item_key(event.get('schema') or '', event.get('name') or '')}",
                {"event_id": event.get("id")},
            )
        )
    return matches


def _schema(config: dict, ctx: AlertContext) -> list[AlertMatch]:
    matches = []
    for event in ctx.events:
        if event.get("action") != "schema":
            continue
        if not _target_ok(config, event.get("schema") or "", event.get("name") or ""):
            continue
        matches.append(AlertMatch(f"Schema changed on {event.get('name')}", {"event_id": event.get("id")}))
    return matches


def _user(config: dict, ctx: AlertContext) -> list[AlertMatch]:
    wanted = (config.get("user") or "").strip().lower()
    if not wanted:
        return []
    matches = []
    for event in ctx.events:
        who = (event.get("db_user") or "").lower()
        if who != wanted:
            continue
        if not _target_ok(config, event.get("schema") or "", event.get("name") or ""):
            continue
        matches.append(
            AlertMatch(
                f"{event.get('db_user')} {event.get('action')} on {event.get('name')}",
                {"event_id": event.get("id")},
            )
        )
    return matches


def _row_drop(config: dict, ctx: AlertContext) -> list[AlertMatch]:
    share = float(config.get("threshold_share") or ROW_COUNT_DROP_SHARE)
    prev = _prev_map(ctx.previous_items)
    matches = []
    for item in ctx.items:
        if not _target_ok(config, item.get("schema") or "", item["name"]):
            continue
        old = prev.get(item_key(item.get("schema") or "", item["name"]))
        if not old or old.get("row_count") in (None, 0) or item.get("row_count") is None:
            continue
        drop = old["row_count"] - item["row_count"]
        if drop > 0 and drop >= share * old["row_count"]:
            matches.append(
                AlertMatch(
                    f"{item['name']} row count dropped from {old['row_count']} to {item['row_count']}",
                    {"from": old["row_count"], "to": item["row_count"]},
                )
            )
    return matches


def _size(config: dict, ctx: AlertContext) -> list[AlertMatch]:
    share = float(config.get("threshold_share") or SIZE_SPIKE_SHARE)
    prev = _prev_map(ctx.previous_items)
    matches = []
    for item in ctx.items:
        if not _target_ok(config, item.get("schema") or "", item["name"]):
            continue
        old = prev.get(item_key(item.get("schema") or "", item["name"]))
        if not old or not old.get("size_bytes") or not item.get("size_bytes"):
            continue
        if item["size_bytes"] >= old["size_bytes"] * (1 + share):
            matches.append(
                AlertMatch(
                    f"{item['name']} size grew from {old['size_bytes']} to {item['size_bytes']} bytes",
                    {"from": old["size_bytes"], "to": item["size_bytes"]},
                )
            )
    return matches


def _presence(config: dict, ctx: AlertContext) -> list[AlertMatch]:
    mode = config.get("presence") or "either"
    prev = {item_key(i.get("schema") or "", i["name"]) for i in ctx.previous_items or [] if _target_ok(config, i.get("schema") or "", i["name"])}
    current = {item_key(i.get("schema") or "", i["name"]) for i in ctx.items if _target_ok(config, i.get("schema") or "", i["name"])}
    matches = []
    if mode in ("added", "either"):
        for key in sorted(current - prev):
            matches.append(AlertMatch(f"New layer {key}", {"layer": key, "change": "added"}))
    if mode in ("dropped", "either"):
        for key in sorted(prev - current):
            matches.append(AlertMatch(f"Dropped layer {key}", {"layer": key, "change": "dropped"}))
    return matches


def _freshness(config: dict, ctx: AlertContext) -> list[AlertMatch]:
    days = int(config.get("threshold_days") or FRESHNESS_DAYS)
    cutoff = ctx.now - timedelta(days=days)
    matches = []
    for item in ctx.items:
        if not _target_ok(config, item.get("schema") or "", item["name"]):
            continue
        stamp = _freshness_stamp(item, ctx.events)
        if stamp is None or stamp >= cutoff:
            continue
        matches.append(
            AlertMatch(
                f"{item['name']} last updated {stamp.date().isoformat()}, older than {days} days",
                {"last_updated": stamp.isoformat()},
            )
        )
    return matches


def _freshness_stamp(item: dict, events: list[dict]) -> datetime | None:
    raw = item.get("last_modified")
    if raw:
        try:
            value = datetime.fromisoformat(raw)
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    related = [
        e
        for e in events
        if e.get("name") == item["name"] and (e.get("schema") or "") == (item.get("schema") or "")
    ]
    if related:
        stamps = [_as_utc(e["occurred_at"]) for e in related if e.get("occurred_at")]
        if stamps:
            return max(stamps)
    scanned = item.get("scanned_at")
    if isinstance(scanned, datetime):
        return scanned if scanned.tzinfo else scanned.replace(tzinfo=timezone.utc)
    return None


def _quality_drop(config: dict, ctx: AlertContext) -> list[AlertMatch]:
    points = int(config.get("threshold_points") or QUALITY_DROP_POINTS)
    matches = []
    for key, score in ctx.quality_scores.items():
        schema, name = (key.split(".", 1) if "." in key else ("", key))
        if not _target_ok(config, schema, name):
            continue
        old = ctx.previous_quality.get(key)
        if old is None:
            continue
        if old - score >= points:
            matches.append(
                AlertMatch(
                    f"{name} quality score dropped from {old} to {score}",
                    {"from": old, "to": score, "is_sample": bool(ctx.quality_samples.get(key) or ctx.previous_quality_samples.get(key))},
                )
            )
    return matches


def _banned(config: dict, ctx: AlertContext) -> list[AlertMatch]:
    field = config.get("field")
    if not field:
        return []
    import pandas as pd

    if config.get("operator") in NEW_RULE_OPERATORS:
        key = item_key(config.get("target_schema") or "", config.get("target_name") or "")
        sample = (ctx.sample_rows or {}).get(key, {})
        frame = pd.DataFrame(sample.get("rows") or [])
        if frame.empty or field not in frame:return []
        hits = _when_mask(frame[field], config["operator"], config.get("value"), frame=frame)
        count = int(hits.sum())
        return [AlertMatch(f"Banned value on {field} matched {count} time(s)", {"field":field,"count":count,"is_sample":sample.get("is_sample",False)})] if count else []

    values: list[Any] = []
    if ctx.sample_values and field in ctx.sample_values:
        values.extend(ctx.sample_values[field])
    event_matches = []
    for event in ctx.events:
        after = event.get("after") or {}
        if field in after and _target_ok(config, event.get("schema") or "", event.get("name") or ""):
            if bool(_when_mask(pd.Series([after[field]]), config.get("operator") or "eq", config.get("value")).iloc[0]):
                event_matches.append(AlertMatch(f"Banned value on {field} matched a recorded edit", {"field":field,"count":1,"event_id":event["id"]}))
    if not values:
        return event_matches
    series = pd.Series(values)
    hits = _when_mask(series, config.get("operator") or "eq", config.get("value"))
    count = int(hits.sum())
    if count == 0:
        return event_matches
    return event_matches + [AlertMatch(f"Banned value on {field} matched {count} time(s)", {"field": field, "count": count, "is_sample": bool(getattr(ctx.sample_values, "is_sample", True))})]


def _as_utc(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
