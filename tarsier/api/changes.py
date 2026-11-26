"""Change-tracking routes (PRD §7.4, FSD §10)."""

from dataclasses import asdict
from datetime import datetime, time, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from datetime import timedelta

from tarsier.changes.engine import volume_series
from tarsier.limits import CHANGE_EVENTS_PAGE
from tarsier.changes import sync
from tarsier.connectors.base import ConnectorError
from tarsier.connectors.tiers import get_connection_type_info
from tarsier.storage import change_log
from tarsier.storage import connections as storage

router = APIRouter(prefix="/api/connections/{connection_id}")


def _require(connection_id: str):
    saved = storage.get_connection(connection_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="No such connection.")
    return saved


def _parse_day(value: str, end: bool) -> datetime:
    try:
        day = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(400, "Dates must use YYYY-MM-DD.") from exc
    stamp = datetime.combine(day.date(), time.max if end else time.min)
    return stamp.replace(tzinfo=timezone.utc)


def _event_payload(event) -> dict:
    payload = asdict(event)
    payload["occurred_at"] = event.occurred_at.isoformat()
    return payload


@router.get("/changes")
def get_changes(
    connection_id: str,
    schema: str | None = None,
    name: str | None = None,
    feature_id: str | None = None,
    user: str | None = None,
    action: str | None = None,
    start: str | None = None,
    end: str | None = None,
    days: int = 90,
):
    saved = _require(connection_id)
    info = get_connection_type_info(saved.type)
    if info.change_tracking == "none":
        return {
            "available": False,
            "reason": "Change tracking isn't available for file connections  -  Tarsier takes no snapshots of files.",
            "mode": "none",
            "events": [],
            "volume": [],
        }
    if saved.type != "postgis":
        return {
            "available": False,
            "reason": "Change tracking for this connection type depends on its own audit setup and isn't built in this phase.",
            "mode": "none",
            "events": [],
            "volume": [],
        }
    state = change_log.get_state(connection_id)
    start_dt = _parse_day(start, False) if start else None
    end_dt = _parse_day(end, True) if end else None
    if start_dt and end_dt and start_dt > end_dt:
        raise HTTPException(400, "Start date must be on or before end date.")
    filters = dict(
        schema=schema, name=name, feature_id=feature_id, user=user, action=action, start=start_dt, end=end_dt
    )
    # A busy database logs millions of changes. Send the newest page and the
    # true total; the filters narrow it further.
    events = change_log.list_events(connection_id, limit=CHANGE_EVENTS_PAGE, **filters)
    action_counts = change_log.count_by_action(connection_id, **filters)
    total = sum(action_counts.values())
    days = max(1, min(days or 90, 3660))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return {
        "available": True,
        "mode": state.mode if state else "none",
        "reason": None if (state and state.mode != "none") else "Change tracking isn't enabled yet.",
        "events": [_event_payload(e) for e in events],
        "total_events": total,
        "action_counts": action_counts,
        "truncated": total > len(events),
        "volume": volume_series(change_log.daily_counts(connection_id, since), days=days),
        "report": change_log.latest_report(connection_id),
        "report_interval": state.report_interval if state else None,
        "tracking_health": sync.tracking_health(connection_id),
    }


@router.post("/changes/sync", status_code=202)
def post_sync(connection_id: str):
    _require(connection_id)
    try:
        count = sync.sync_connection(connection_id)
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "captured": count}


class AcknowledgeBody(BaseModel):
    acknowledge_failures_up_to: int = Field(ge=0, strict=True)


@router.post("/changes/acknowledge")
def post_acknowledge(connection_id: str, body: AcknowledgeBody):
    _require(connection_id)
    health = sync.tracking_health(connection_id)
    observed = health.get("logging_failures")
    if observed is None:
        raise HTTPException(status_code=409, detail="The failure counter could not be verified. Try again when tracking health is available.")
    if body.acknowledge_failures_up_to > observed:
        raise HTTPException(status_code=409, detail="Only observed tracking failures can be marked as reviewed.")
    try:
        change_log.acknowledge_failures(connection_id, body.acknowledge_failures_up_to)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "ok", "tracking_health": sync.tracking_health(connection_id)}


@router.post("/changes/install-triggers", status_code=202)
def post_install(connection_id: str):
    _require(connection_id)
    try:
        sync.enable_triggers(connection_id)
        sync.sync_connection(connection_id)
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "mode": "triggers"}


@router.post("/changes/enable-polling", status_code=202)
def post_polling(connection_id: str):
    _require(connection_id)
    try:
        sync.enable_polling(connection_id)
        sync.sync_connection(connection_id)
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "mode": "polling"}


class ReportBody(BaseModel):
    interval: str = "daily"


@router.post("/changes/report")
def post_report(connection_id: str, body: ReportBody):
    _require(connection_id)
    if body.interval not in ("daily", "weekly"):
        raise HTTPException(status_code=400, detail="Interval must be daily or weekly.")
    return sync.generate_report(connection_id, body.interval)


@router.put("/changes/report/schedule")
def put_schedule(connection_id: str, body: ReportBody):
    _require(connection_id)
    if body.interval not in ("daily", "weekly", "off"):
        raise HTTPException(status_code=400, detail="Interval must be daily, weekly, or off.")
    interval = None if body.interval == "off" else body.interval
    change_log.set_report_interval(connection_id, interval)
    return {"status": "ok", "interval": interval}
