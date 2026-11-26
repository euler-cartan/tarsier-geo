"""Local aggregate timing evidence. Never inspect arguments for data or secrets."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache, wraps
import inspect
import json
from pathlib import Path
import subprocess
import time
import uuid

_current = ContextVar("tarsier_timing_run", default=None)
_PHASES = ("fetch", "compute", "cache_write", "alert", "graph")


def _utc():
    return datetime.now(timezone.utc).isoformat()


@lru_cache(maxsize=1)
def build_commit():
    try:
        value = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent,
                                        stderr=subprocess.DEVNULL, timeout=2).decode().strip()
        return value if len(value) == 40 and all(c in "0123456789abcdef" for c in value) else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _outcome(exc):
    if exc is None:
        return "completed"
    if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt)):
        return "cancelled"
    current = exc
    while current is not None:
        if isinstance(current, TimeoutError) or getattr(current, "sqlstate", None) == "57014" or getattr(current, "pgcode", None) == "57014":
            return "timeout"
        current = current.__cause__
    return "failed"


@dataclass
class Run:
    run_id: str
    build_commit: str
    connection_id: str | None
    item: str | None
    check: str
    started_utc: str = field(default_factory=_utc)
    started: float = field(default_factory=time.perf_counter)
    spans: list = field(default_factory=list)
    stack: list = field(default_factory=list)
    rows: int | None = None
    bytes: int | None = None
    forced_outcome: str | None = None
    byte_measure: str = "dataframe_deep_memory_estimate_not_wire_or_native_geometry"


def record_outcome(outcome):
    if outcome not in {"failed", "completed_with_errors", "cancelled", "timeout"}:
        return
    run = _current.get()
    if run is not None and run.forced_outcome not in {"cancelled", "timeout"}:
        run.forced_outcome = outcome


def record_timeout():
    run = _current.get()
    if run is not None:
        run.forced_outcome = "timeout"


def observe(result):
    run = _current.get()
    if run is None:
        return
    frame = getattr(result, "dataframe", None)
    if frame is None:
        frame = getattr(result, "geodataframe", None)
    if frame is not None:
        count = len(frame)
        size = int(frame.memory_usage(index=True, deep=True).sum())
        run.rows = (run.rows or 0) + count
        run.bytes = (run.bytes or 0) + size
    elif getattr(result, "values", None) is not None and hasattr(result.values, "memory_usage"):
        run.rows = (run.rows or 0) + len(result.values)
        run.bytes = (run.bytes or 0) + int(result.values.memory_usage(index=True, deep=True))


@contextmanager
def phase(name, *, item=None, check=None):
    run = _current.get()
    if run is None:
        yield
        return
    if name not in _PHASES:
        raise ValueError("Unknown timing phase")
    start, utc = time.perf_counter(), _utc()
    entry = {"children": 0.0}
    run.stack.append(entry)
    error = None
    try:
        yield
    except BaseException as exc:
        error = exc
        raise
    finally:
        elapsed = time.perf_counter() - start
        run.stack.pop()
        if run.stack:
            run.stack[-1]["children"] += elapsed
        run.spans.append({"phase": name, "item": item or run.item, "check": check or run.check,
                          "started_utc": utc, "ended_utc": _utc(), "elapsed": elapsed,
                          "exclusive_seconds": max(0.0, elapsed-entry["children"]), "outcome": _outcome(error)})


def timed_phase(name, *, observe_rows=False):
    def decorate(fn):
        signature = inspect.signature(fn)
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if _current.get() is None:
                return fn(*args, **kwargs)
            bound = signature.bind(*args, **kwargs).arguments
            item = bound.get("item") or getattr(bound.get("self"), "item", None)
            with phase(name, item=getattr(item, "qualified_name", None), check=fn.__name__):
                result = fn(*args, **kwargs)
                if observe_rows:
                    observe(result)
                return result
        return wrapped
    return decorate


def timed_run(check):
    def decorate(fn):
        signature = inspect.signature(fn)
        @wraps(fn)
        def wrapped(*args, **kwargs):
            bound = signature.bind(*args, **kwargs).arguments
            item = '.'.join(str(bound[k]) for k in ("schema", "name") if bound.get(k)) or None
            active = _current.get()
            if active is not None:
                prior = active.item, active.check
                active.item, active.check = item or active.item, bound.get("check_id", check)
                try:
                    return fn(*args, **kwargs)
                finally:
                    active.item, active.check = prior
            run = Run(uuid.uuid4().hex, build_commit(), bound.get("connection_id"), item, bound.get("check_id", check))
            token = _current.set(run)
            error = None
            try:
                return fn(*args, **kwargs)
            except BaseException as exc:
                error = exc
                raise
            finally:
                _current.reset(token)
                ended, elapsed = _utc(), time.perf_counter()-run.started
                outcome = run.forced_outcome or _outcome(error)
                if outcome == "completed":
                    outcomes = {s["outcome"] for s in run.spans}
                    outcome = "cancelled" if "cancelled" in outcomes else "timeout" if "timeout" in outcomes else "completed_with_errors" if "failed" in outcomes else outcome
                totals = {p: sum(s["exclusive_seconds"] for s in run.spans if s["phase"] == p) for p in _PHASES}
                from tarsier.storage.run_timings import save_run
                save_run({"run_id": run.run_id, "build_commit": run.build_commit, "connection_id": run.connection_id,
                          "item": run.item, "check": run.check, "started_utc": run.started_utc, "ended_utc": ended,
                          "elapsed_seconds": elapsed, "rows": run.rows, "bytes": run.bytes,
                          "byte_measure": run.byte_measure,
                          **{p+"_seconds": v for p,v in totals.items()},
                          "unattributed_seconds": max(0.0, elapsed-sum(totals.values())),
                          "outcome": outcome, "timeout": outcome == "timeout", "cancelled": outcome == "cancelled",
                          "spans": run.spans})
        return wrapped
    return decorate


def current_run_id():
    run = _current.get()
    return run.run_id if run is not None else None


def observe_acquisition(rows, serialized_bytes):
    run = _current.get()
    if run is not None:
        run.rows = (run.rows or 0) + rows
        run.bytes = (run.bytes or 0) + serialized_bytes
        run.byte_measure = "bounded_serialized_UTF8_payload_bytes_including_duplicate_draws"
