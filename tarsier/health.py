"""Health-score component calculations (PRD §7.1, DVS §4)."""

from datetime import datetime, timezone

from tarsier.quality.engine import CheckResult

WEIGHTS = {"quality": 40, "freshness": 30, "completeness": 30}


def quality_score(checks: dict[str, CheckResult]) -> int | None:
    completed = [
        check for check in checks.values()
        if check.status not in ("never_run", "not_applicable")
    ]
    if not completed:
        return None
    return round(100 * sum(check.status in {"good", "sampled"} for check in completed) / len(completed))


def quality_is_sample(checks: dict[str, CheckResult]) -> bool:
    return any(c.is_sample and c.status not in {"never_run", "not_applicable"} for c in checks.values())


def freshness_score(last_modified: str | None, last_event_at: datetime | None, now: datetime) -> int | None:
    stamp = _parse_timestamp(last_modified)
    if stamp is None and last_event_at is not None:
        stamp = _as_utc(last_event_at)
    if stamp is None:
        return None

    age_days = max(0.0, (now - stamp).total_seconds() / 86400)
    if age_days <= 30:
        return 100
    if age_days >= 90:
        return 0
    return round((90 - age_days) * (100 / 60))


def completeness_score(checks: dict[str, CheckResult]) -> int | None:
    check = checks.get("completeness")
    return None if check is None else check.completeness_score


def calculate_health(
    last_modified: str | None,
    last_event_at: datetime | None,
    checks: dict[str, CheckResult],
    now: datetime | None = None,
) -> dict:
    now = _as_utc(now or datetime.now(timezone.utc))
    components = {
        "quality": quality_score(checks),
        "freshness": freshness_score(last_modified, last_event_at, now),
        "completeness": completeness_score(checks),
    }
    available = [
        (components[name], weight)
        for name, weight in WEIGHTS.items()
        if components[name] is not None
    ]
    score = None
    if available:
        weight_total = sum(weight for _value, weight in available)
        score = round(sum(value * weight for value, weight in available) / weight_total)
    return {"score": score, "components": components}


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return _as_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
