"""Optional APScheduler tick for polling + due reports (TAD §7.1)."""

import logging
import os

_log = logging.getLogger("tarsier.scheduler")
_scheduler = None


def start_scheduler() -> None:
    global _scheduler
    if os.environ.get("TARSIER_SCHEDULER") != "1":
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        return
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_tick, "interval", minutes=1, id="tarsier-changes")
    _scheduler.add_job(_snapshot_tick, "interval", hours=1, id="tarsier-snapshots")
    _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def _tick() -> None:
    from tarsier.changes import sync
    from tarsier.storage import connections as storage

    for saved in storage.list_connections():
        try:
            if saved.type == "postgis" and _sync_is_due(saved.id):
                sync.sync_connection(saved.id)
            if saved.type == "postgis":
                sync.generate_due_report(saved.id)
        except Exception:
            _log.warning("Scheduled change sync failed for connection %s", saved.id, exc_info=True)
        try:
            from tarsier.alerts.evaluate import evaluate_connection

            evaluate_connection(saved.id)
        except Exception:
            pass
        try:
            from tarsier.automation.evaluate import evaluate_connection as evaluate_autos

            evaluate_autos(saved.id)
        except Exception:
            continue


def _sync_is_due(connection_id: str) -> bool:
    """Never open a source connection for a database whose tracking is off, and
    space out polling passes (each one re-reads every tracked table)."""
    from datetime import datetime, timedelta, timezone

    from tarsier.limits import POLLING_INTERVAL_MINUTES
    from tarsier.storage import change_log

    state = change_log.get_state(connection_id)
    if state is None or state.mode == "none":
        return False
    if state.mode == "polling" and state.last_sync_at is not None:
        last = state.last_sync_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - last >= timedelta(minutes=POLLING_INTERVAL_MINUTES)
    return True


def _snapshot_tick():
    from tarsier.snapshots import capture_due
    capture_due()
