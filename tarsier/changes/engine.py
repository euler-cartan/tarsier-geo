"""Mass-change, volume spikes, compare-window, and report summaries (TAD Phase 5)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

MASS_ABSOLUTE = 50
MASS_SHARE = 0.25
MASS_FLOOR = 10
SPIKE_MULTIPLIER = 3.0
SPIKE_ZERO_MEAN_FLOOR = 10


@dataclass(frozen=True)
class ChangeEventView:
    id: str
    occurred_at: datetime
    db_user: str | None
    action: str
    schema: str
    name: str
    feature_id: str | None
    before: dict | None
    after: dict | None
    txid: str | None
    source: str
    is_mass: bool
    changed_fields: list[str] = field(default_factory=list)
    source_log_id: int | None = None
    capture_seq: int | None = None


def changed_fields(before: dict | None, after: dict | None) -> list[str]:
    old = before or {}
    new = after or {}
    keys = set(old) | set(new)
    return sorted(k for k in keys if old.get(k) != new.get(k))


def is_mass_batch(change_count: int, table_row_count: int | None) -> bool:
    if change_count >= MASS_ABSOLUTE:
        return True
    if table_row_count and change_count >= MASS_FLOOR and change_count >= MASS_SHARE * table_row_count:
        return True
    return False


def volume_by_day(events: list[ChangeEventView], days: int = 90) -> list[dict]:
    daily: dict[str, dict[str, int]] = {}
    for event in events:
        bucket = daily.setdefault(_as_utc(event.occurred_at).date().isoformat(), {})
        bucket[event.action] = bucket.get(event.action, 0) + 1
    return volume_series(daily, days)


def volume_series(daily: dict[str, dict[str, int]], days: int = 90) -> list[dict]:
    """Per-day series with spike flags from {day: {action: count}} totals."""
    if not days or days < 1:
        days = 90
    days = min(days, 3660)
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days - 1)
    counts: dict = defaultdict(lambda: {"total": 0, "insert": 0, "update": 0, "delete": 0, "schema": 0})
    for day, actions in daily.items():
        if start.isoformat() <= day <= end.isoformat():
            bucket = counts[day]
            for action, total in actions.items():
                bucket["total"] += total
                if action in bucket and action != "total":
                    bucket[action] += total
    series = []
    cursor = start
    window: list[int] = []
    while cursor <= end:
        key = cursor.isoformat()
        total = counts[key]["total"]
        mean = (sum(window[-7:]) / len(window[-7:])) if window else 0.0
        spike = total > SPIKE_MULTIPLIER * mean if mean > 0 else total >= SPIKE_ZERO_MEAN_FLOOR
        series.append(
            {
                "date": key,
                "count": total,
                "insert": counts[key]["insert"],
                "update": counts[key]["update"],
                "delete": counts[key]["delete"],
                "schema": counts[key]["schema"],
                "is_spike": spike,
            }
        )
        window.append(total)
        cursor += timedelta(days=1)
    return series


def in_date_range(events: list[ChangeEventView], start: datetime, end: datetime) -> list[ChangeEventView]:
    start_u = _as_utc(start)
    end_u = _as_utc(end)
    return [e for e in events if start_u <= _as_utc(e.occurred_at) <= end_u]


def report_summary(events: list[ChangeEventView]) -> dict:
    by_action: dict[str, int] = defaultdict(int)
    mass_tx = {e.txid for e in events if e.is_mass and e.txid}
    schema_events = [e for e in events if e.action == "schema"]
    for event in events:
        by_action[event.action] += 1
    return {
        "total": len(events),
        "by_action": dict(by_action),
        "mass_batches": len(mass_tx),
        "schema_changes": len(schema_events),
        "unknown_who": sum(1 for e in events if not e.db_user),
    }


def diff_fingerprints(previous: dict[str, str], current: dict[str, str]) -> list[dict]:
    """Polling: map feature_id → md5. Returns insert/update/delete stubs."""
    changes = []
    for fid, digest in current.items():
        if fid not in previous:
            changes.append({"action": "insert", "feature_id": fid})
        elif previous[fid] != digest:
            changes.append({"action": "update", "feature_id": fid})
    for fid in previous:
        if fid not in current:
            changes.append({"action": "delete", "feature_id": fid})
    return changes


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
