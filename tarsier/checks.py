"""Background health checks with persisted, pollable progress."""
from tarsier.timing import timed_run, record_outcome

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from tarsier.storage.settings import _get_value, _set_value

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tarsier-check")
_lock = threading.Lock()
_active: set[str] = set()


def status(connection_id):
    value = _get_value("check_job_" + connection_id)
    result = json.loads(value) if value else {"state": "idle", "completed": 0, "total": 0, "message": "No full health check has run yet.", "errors": [], "skipped": []}
    if result["state"] == "running" and connection_id not in _active:
        result.update(state="interrupted", message="The app restarted before this check finished. Run it again.")
    return result


def start(connection_id, *, mode="full"):
    if mode not in {"full", "sample_first"}:
        raise ValueError("Unknown check mode")
    with _lock:
        if connection_id in _active:
            return status(connection_id)
        _active.add(connection_id)
        job = {"state": "running", "completed": 0, "total": 0, "message": "Reading metadata. Health results will appear shortly.", "errors": [], "skipped": [], "started_at": datetime.now(timezone.utc).isoformat()}
        _save(connection_id, job)
        _pool.submit(_run if mode == "full" else _run_sample, connection_id, job)
        return job.copy()


def _save(connection_id, job):
    _set_value("check_job_" + connection_id, json.dumps(job))


@timed_run("full_health_check")
def _run(connection_id, job):
    job.setdefault("skipped", [])
    from tarsier.overview import scan_connection
    from tarsier.quality.engine import applicable_checks
    from tarsier.quality.scan import scan_check
    from tarsier.stats.scan import MAX_FULL_STATS_ROWS, scan_item_stats
    from tarsier.connectors.base import ConnectorError
    from tarsier.storage import item_cache
    try:
        scan_connection(connection_id)
        items = item_cache.list_items(connection_id)
        from tarsier.overview import _unreadable_items
        unreadable = _unreadable_items(connection_id)
        work = [(item, check) for item in items if (item.schema, item.name) not in unreadable for check in (["statistics"] + list(applicable_checks(item.kind)) if item.kind != "raster" else [])]
        job["total"] = len(work)
        for item, check in work:
            job["message"] = f"Checking {item.schema + '.' if item.schema else ''}{item.name}: {check}. Health results will appear shortly."
            _save(connection_id, job)
            try:
                if check == "statistics":
                    if item.row_count is None or item.row_count > MAX_FULL_STATS_ROWS:
                        scan_item_stats(connection_id, item.schema, item.name, full=False)
                        reason = "skipped: row count unknown; sample used" if item.row_count is None else "skipped: too large for full check; sample used"
                        job["skipped"].append({"schema": item.schema, "name": item.name, "check": check, "message": reason})
                    else:
                        scan_item_stats(connection_id, item.schema, item.name, full=True)
                else:
                    scan_check(connection_id, item.schema, item.name, check, full=True)
            except ConnectorError as exc:
                if check == "statistics" and "exceeds 64 MiB" in str(exc):
                    try:
                        scan_item_stats(connection_id, item.schema, item.name, full=False)
                        job["skipped"].append({"schema": item.schema, "name": item.name, "check": check, "message": "skipped: too large for full check; sample used"})
                    except Exception:
                        job["errors"].append({"schema": item.schema, "name": item.name, "check": check, "message": "This check could not finish. Open the layer to retry and inspect its source."})
                else:
                    job["errors"].append({"schema": item.schema, "name": item.name, "check": check, "message": "This check could not finish. Open the layer to retry and inspect its source."})
            except Exception:
                job["errors"].append({"schema": item.schema, "name": item.name, "check": check, "message": "This check could not finish. Open the layer to retry and inspect its source."})
            job["completed"] += 1
            _save(connection_id, job)
        job.update(state="completed_with_errors" if job["errors"] else "completed", message="Health check finished with some unavailable checks." if job["errors"] else "Health check complete. Results are ready.")
    except Exception:
        job.update(state="failed", message="The full check could not finish. Check the connection and retry.")
    finally:
        record_outcome(job["state"])
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save(connection_id, job)
        with _lock:
            _active.discard(connection_id)


def _run_sample(connection_id, job):
    from tarsier.checks_sample import run
    try:
        run(connection_id,job)
    except Exception:
        job.update(state="failed",message="The sample-first check could not finish; previous caches retained.",finished_at=datetime.now(timezone.utc).isoformat())
        _save(connection_id,job)
    finally:
        with _lock:
            _active.discard(connection_id)
