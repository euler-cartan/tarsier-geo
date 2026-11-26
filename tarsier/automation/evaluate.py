"""Build context and walk saved automations (TAD Phase 7)."""

from __future__ import annotations

from tarsier.timing import timed_phase
import threading
from datetime import datetime, timezone

from tarsier.alerts.engine import item_key, quality_score
from tarsier.automation.engine import RunContext, walk_graph
from tarsier.notifications.delivery import DeliveryError, send_email, send_webhook, send_chat
from tarsier.limits import EVENT_EVALUATION_WINDOW
from tarsier.storage import automations as auto_store
from tarsier.storage import webhook_vault
from tarsier.storage import change_log, item_cache, quality_cache
from tarsier.storage.event_receipts import after_creation

_busy = threading.local()


@timed_phase("alert")
def evaluate_connection(connection_id: str, *, dry_run_id: str | None = None) -> list[dict]:
    if getattr(_busy, "on", False):
        return []
    _busy.on = True
    try:
        return _evaluate(connection_id, dry_run_id)
    finally:
        _busy.on = False


def run_one(connection_id: str, automation_id: str, *, dry_run: bool) -> dict:
    auto = auto_store.get_automation(automation_id)
    if auto is None or auto["connection_id"] != connection_id:
        return {"ok": False, "message": "No such automation.", "trace": []}
    ctx = _context(connection_id, auto, include_all_events=dry_run)
    ctx.dry_run = dry_run
    if not dry_run:
        from tarsier.storage.event_receipts import claim_events
        ctx.events = claim_events("automation", automation_id, ctx.events)
    ok, message, trace = walk_graph(auto["graph"], ctx, lambda node, c: _handle(node, c))
    if not dry_run:
        auto_store.save_snapshot(automation_id, _snapshot_payload(ctx))
    record = auto_store.record_run(
        automation_id, connection_id, dry_run=dry_run, ok=ok, message=message, trace=trace
    )
    return record


def _evaluate(connection_id: str, dry_run_id: str | None) -> list[dict]:
    ran = []
    for auto in auto_store.list_automations(connection_id):
        if auto["paused"]:
            continue
        if dry_run_id and auto["id"] != dry_run_id:
            continue
        ctx = _context(connection_id, auto)
        kinds = {n.get("kind") for n in auto["graph"].get("nodes") or []}
        if ctx.previous_items is None and kinds.intersection({"threshold", "layer_presence", "count_drop"}):
            auto_store.save_snapshot(auto["id"], _snapshot_payload(ctx))
            continue
        from tarsier.storage.event_receipts import claim_events
        ctx.events = claim_events("automation", auto["id"], ctx.events)
        ok, message, trace = walk_graph(auto["graph"], ctx, lambda node, c: _handle(node, c))
        auto_store.save_snapshot(auto["id"], _snapshot_payload(ctx))
        if any(step.get("role") == "trigger" and step.get("ok") for step in trace):
            ran.append(
                auto_store.record_run(
                    auto["id"], connection_id, dry_run=False, ok=ok, message=message, trace=trace
                )
            )
    return ran


def _context(connection_id: str, auto: dict, *, include_all_events: bool = False) -> RunContext:
    items = [
        {
            "schema": i.schema,
            "name": i.name,
            "kind": i.kind,
            "row_count": i.row_count,
            "size_bytes": i.size_bytes,
            "last_modified": i.last_modified,
        }
        for i in item_cache.list_items(connection_id)
    ]
    scores = {}
    is_sample = False
    failures = []
    for item in items:
        checks = quality_cache.get_checks(connection_id, item["schema"], item["name"])
        from tarsier.health import quality_is_sample
        is_sample = is_sample or quality_is_sample(checks)
        score = quality_score(checks)
        if score is not None:
            scores[item_key(item["schema"], item["name"])] = score
        for check in checks.values():
            if check.status == "danger":
                failures.append(
                    {
                        "schema": item["schema"],
                        "name": item["name"],
                        "check_id": check.check_id,
                        "status": check.status,
                    }
                )
    last = auto.get("last_run_at")
    last_dt = datetime.fromisoformat(last) if last else None
    if last_dt and last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    events = []
    for e in change_log.list_events(connection_id, limit=EVENT_EVALUATION_WINDOW):
        when = e.occurred_at
        if when is not None and when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        events.append(
            {
                "id": e.id,
                "action": e.action,
                "schema": e.schema,
                "name": e.name,
                "db_user": e.db_user,
                "is_mass": e.is_mass,
                "occurred_at": when.isoformat() if when else None,
                "capture_seq": e.capture_seq,
                "source_log_id": e.source_log_id,
            }
        )
    events = after_creation(events, auto.get("event_checkpoint"), auto.get("source_log_checkpoint"))
    if not include_all_events:
        from tarsier.storage.event_receipts import pending
        events = pending("automation", auto["id"], events)
    snap = auto.get("snapshot") or {}
    range_values = _range_samples(connection_id, auto)
    return RunContext(
        connection_id=connection_id,
        events=events,
        items=items,
        previous_items=None if not snap else snap.get("items"),
        quality_failures=failures,
        quality_scores=scores,
        previous_quality={} if not snap else snap.get("quality_scores") or {},
        now=datetime.now(timezone.utc),
        last_run_at=last_dt,
        dry_run=False,
        sample_values=range_values,
        is_sample=is_sample or bool(getattr(range_values, "is_sample", bool(range_values))),
        previous_is_sample=snap.get("is_sample", False),
        trigger_last_runs=snap.get("trigger_last_runs"),
    )


def _snapshot_payload(ctx: RunContext) -> dict:
    return {"items": ctx.items, "quality_scores": ctx.quality_scores, "trigger_last_runs": ctx.trigger_last_runs, "is_sample": ctx.is_sample}


def _range_samples(connection_id: str, auto: dict) -> dict:
    from tarsier.stats import scan as stats_scan

    from tarsier.alerts.evaluate import SampleValues
    values = SampleValues()
    for node in auto.get("graph", {}).get("nodes") or []:
        if node.get("kind") != "value_out_of_range":
            continue
        field = (node.get("config") or {}).get("field")
        name = (node.get("config") or {}).get("layer") or (node.get("config") or {}).get("name")
        if not field or not name:
            continue
        try:
            sample = stats_scan.load_item_sample(connection_id, (node.get("config") or {}).get("schema") or "", name)
        except Exception:
            continue
        values.is_sample = values.is_sample or sample.is_sample
        if field in sample.dataframe.columns:
            values[f"node:{node.get('id')}:{field}"] = sample.dataframe[field].tolist()
    return values


def _handle(node: dict, ctx: RunContext) -> dict:
    if ctx.is_sample or ctx.previous_is_sample:
        config = dict(node.get("config") or {})
        if node.get("kind") in {"log", "email", "chat"}:
            config["message"] = str(config.get("message") or "An automation ran in Tarsier.") + " (sample-based; not a full check)"
        node = {**node, "config": config}
    result = _handle_result(node, ctx)
    if ctx.is_sample or ctx.previous_is_sample:
        result = {**result, "is_sample": True,
                  "message": str(result.get("message") or "") + " (sample-based; not a full check)"}
    return result


def _handle_result(node: dict, ctx: RunContext) -> dict:
    kind = node.get("kind")
    config = node.get("config") or {}
    if ctx.dry_run:
        if kind == "run_quality":
            return {"ok": True, "message": "Would run quality checks."}
        if kind == "webhook":
            return {"ok": True, "message": "Would POST webhook (skipped on test run)."}
        if kind == "email":
            return {"ok": True, "message": "Would send an email (skipped on test run)."}
        if kind == "ai_summarize":
            return {"ok": True, "message": "Would summarize and deliver today's changes (skipped on test run)."}
        return {"ok": True, "message": f"Would {kind}."}

    if kind == "log":
        return {"ok": True, "message": config.get("message") or "Logged."}
    if kind == "email":
        try:
            send_email(
                config.get("email_recipients"),
                str(config.get("subject") or "Tarsier automation notification"),
                str(config.get("message") or "An automation ran in Tarsier."),
            )
        except DeliveryError as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, "message": "Email delivered."}
    if kind == "chat":
        try:
            send_chat(config.get("channel") or "slack", config.get("message") or "A Tarsier automation ran.")
        except DeliveryError as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, "message": "Chat message delivered."}
    if kind == "webhook":
        try:
            send_webhook(webhook_vault.resolve(config), {"source": "tarsier-automation", "is_sample": ctx.is_sample or ctx.previous_is_sample, "scope": "sample-based; not a full check" if ctx.is_sample or ctx.previous_is_sample else "recorded changes/full checks"})
        except DeliveryError as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, "message": "Webhook sent."}
    if kind == "run_quality":
        return _run_quality(ctx, config)
    if kind == "scan_statistics":
        from tarsier.stats.scan import scan_item_stats
        target, schema = config.get("layer") or "", config.get("schema") or ""
        count = 0
        for item in ctx.items:
            if item["kind"] not in ("vector", "tabular") or (target and item["name"] != target) or (schema and item["schema"] != schema):
                continue
            scan_item_stats(ctx.connection_id, item["schema"], item["name"])
            count += 1
        return {"ok": count > 0, "message": f"Refreshed statistics for {count} items."}
    if kind == "change_report":
        from tarsier.changes.sync import generate_report
        report = generate_report(ctx.connection_id, config.get("interval") or "daily")
        return {"ok": True, "message": f"Generated report: {report.get('total', 0)} recorded changes."}
    if kind == "ai_summarize":
        try:
            from tarsier.ai.jobs import explain_changes

            body = explain_changes(ctx.connection_id)
        except Exception as exc:
            return {"ok": False, "message": str(exc)}
        summary = body["text"][:800]
        notify = config.get("notify") or "log"
        try:
            if notify == "email":
                send_email(config.get("email_recipients"), "Tarsier change summary", summary)
                return {"ok": True, "message": "Change summary emailed."}
            if notify == "webhook":
                send_webhook(webhook_vault.resolve(config), {"source": "tarsier-automation", "summary": summary})
                return {"ok": True, "message": "Change summary sent to webhook."}
            if notify in ("slack", "teams"):
                send_chat(notify, summary)
                return {"ok": True, "message": f"{notify.title()} summary delivered."}
        except DeliveryError as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, "message": summary}
    return {"ok": False, "message": "Unknown action. Update this node before running."}


def _run_quality(ctx: RunContext, config: dict) -> dict:
    from tarsier.quality.engine import applicable_checks
    from tarsier.quality.scan import scan_check

    target = config.get("name") or config.get("layer") or ""
    ran = 0
    errors = 0
    checked_items = []
    for item in ctx.items:
        if target and item["name"] != target:
            continue
        if config.get("schema") and item.get("schema") != config["schema"]:
            continue
        if item.get("kind") not in ("vector", "tabular"):
            continue
        checked_items.append(item)
        for check_id in applicable_checks(item["kind"]):
            try:
                scan_check(ctx.connection_id, item.get("schema") or "", item["name"], check_id)
                ran += 1
            except Exception:
                errors += 1
    failures = []
    for item in checked_items:
        checks = quality_cache.get_checks(ctx.connection_id, item.get("schema") or "", item["name"])
        from tarsier.health import quality_is_sample
        ctx.is_sample = ctx.is_sample or quality_is_sample(checks)
        score = quality_score(checks)
        if score is not None:
            ctx.quality_scores[item_key(item.get("schema") or "", item["name"])] = score
        for check in checks.values():
            if check.status == "danger":
                failures.append(
                    {"schema": item.get("schema") or "", "name": item["name"], "check_id": check.check_id}
                )
    ctx.quality_failures = failures
    return {"ok": ran > 0 and errors == 0, "message": f"Ran {ran} checks; {len(failures)} failing; {errors} execution errors."}
