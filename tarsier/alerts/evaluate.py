"""Gather cache/change context and fire matching alerts (TAD Phase 6)."""

from tarsier.timing import timed_phase
import logging
from datetime import datetime, timedelta, timezone

from tarsier.alerts.engine import AlertContext, AlertMatch, evaluate_rule, item_key, quality_score
from tarsier.limits import EVENT_EVALUATION_WINDOW
from tarsier.notifications.delivery import DeliveryError, send_email, send_webhook, send_chat
from tarsier.storage import alerts as alert_store
from tarsier.storage import webhook_vault
from tarsier.storage import change_log
from tarsier.storage import item_cache
from tarsier.storage import quality_cache


_log = logging.getLogger("tarsier.alerts")
REPEAT_AFTER = timedelta(hours=24)
_STATE_KINDS = {"freshness", "banned_value"}
MAX_FIRES_PER_RULE_PER_PASS = 10


def _context(connection_id: str) -> AlertContext:
    items = [
        {
            "schema": i.schema,
            "name": i.name,
            "row_count": i.row_count,
            "size_bytes": i.size_bytes,
            "last_modified": i.last_modified,
            "scanned_at": i.scanned_at,
        }
        for i in item_cache.list_items(connection_id)
    ]
    scores = {}
    quality_samples = {}
    for item in items:
        checks = quality_cache.get_checks(connection_id, item["schema"], item["name"])
        from tarsier.health import quality_is_sample
        quality_samples[item_key(item["schema"], item["name"])] = quality_is_sample(checks)
        score = quality_score(checks)
        if score is not None:
            scores[item_key(item["schema"], item["name"])] = score

    previous = alert_store.get_snapshot(connection_id)
    events = [
        {
            "id": e.id,
            "action": e.action,
            "schema": e.schema,
            "name": e.name,
            "db_user": e.db_user,
            "is_mass": e.is_mass,
            "occurred_at": e.occurred_at,
            "after": e.after,
            "capture_seq": e.capture_seq,
            "source_log_id": e.source_log_id,
        }
        for e in change_log.list_events(connection_id, limit=EVENT_EVALUATION_WINDOW)
    ]
    ctx = AlertContext(
        items=items,
        previous_items=None if previous is None else previous.get("items"),
        events=events,
        quality_scores=scores,
        previous_quality={} if previous is None else previous.get("quality_scores") or {},
        now=datetime.now(timezone.utc),
        quality_samples=quality_samples,
        previous_quality_samples={} if previous is None else previous.get("quality_samples") or {},
        sample_values={},
        sample_rows={},
    )

    return ctx


def preview_rule(connection_id: str, rule: dict) -> dict:
    ctx = _context(connection_id)
    if rule["kind"] == "banned_value":
        ctx.sample_values = _banned_samples(connection_id, [rule])
        ctx.sample_rows = _banned_rows(connection_id, [rule])
    config = {**rule["config"], "target_schema": rule["target_schema"], "target_name": rule["target_name"]}
    matches = evaluate_rule(rule["kind"], config, ctx)
    return {"matches": [{"message": m.message, "details": m.details} for m in matches], "baseline_available": ctx.previous_items is not None, "message": "Preview uses cached data. No notifications sent or history changed."}


@timed_phase("alert")
def evaluate_connection(connection_id: str) -> list[dict]:
    ctx = _context(connection_id)
    previous = ctx.previous_items
    SNAPSHOT_KINDS = {"row_count_drop", "layer_presence", "size_spike", "quality_score_drop"}
    from dataclasses import replace
    from tarsier.storage.event_receipts import after_creation, pending
    fired: list[dict] = []
    for rule in alert_store.list_rules(connection_id):
        if rule["paused"]:
            continue
        if previous is None and rule["kind"] in SNAPSHOT_KINDS:
            continue
        config = dict(rule["config"])
        config["target_schema"] = rule["target_schema"]
        config["target_name"] = rule["target_name"]
        ctx.sample_values = _banned_samples(connection_id, [rule]) if rule["kind"] == "banned_value" else {}
        ctx.sample_rows = _banned_rows(connection_id, [rule]) if rule["kind"] == "banned_value" else {}
        rule_ctx = (replace(ctx, events=pending("alert", rule["id"], after_creation(
                        ctx.events, rule.get("event_checkpoint"), rule.get("source_log_checkpoint"))))
                    if rule["kind"] in {"mass_change", "schema_change", "specific_user", "banned_value"} else ctx)
        try:
            matches = evaluate_rule(rule["kind"], config, rule_ctx)
        except Exception:
            # One rule that cannot be evaluated (its column was dropped, say)
            # must not stop the other rules.
            _log.warning("Alert rule %s could not be evaluated", rule["id"], exc_info=True)
            continue
        matches = _collapse(rule["id"], matches)
        channel = config.get("notify") or "log"
        for match in matches:
            # A condition that stays true (a stale layer, a banned value still
            # present) is re-raised once a day, not on every one-minute pass.
            if "event_id" not in match.details and rule["kind"] in _STATE_KINDS and alert_store.fired_since(
                rule["id"], match.message, ctx.now - REPEAT_AFTER
            ):
                continue
            record = alert_store.record_fire(
                rule["id"], connection_id, match.message, match.details, channel
            )
            if record is None:
                continue
            status, delivery_message = _deliver(channel, config, record, rule.get("title") or "Alert")
            alert_store.update_fire_delivery(record["id"], status, delivery_message)
            record["delivery_status"] = status
            record["delivery_message"] = delivery_message
            fired.append(record)

    alert_store.save_snapshot(
        connection_id,
        {"items": ctx.items, "quality_scores": ctx.quality_scores, "quality_samples": ctx.quality_samples},
    )
    return fired


def _collapse(rule_id: str, matches: list) -> list:
    """One bulk load can match a rule thousands of times. Past a handful, raise
    a single summary instead of thousands of log entries and notifications.
    The summarised events are claimed, so they are not raised again."""
    if len(matches) <= MAX_FIRES_PER_RULE_PER_PASS or not all(m.details.get("event_id") for m in matches):
        return matches
    from tarsier.storage.event_receipts import claim_events

    accepted = claim_events("alert", rule_id, [{"id": m.details["event_id"]} for m in matches])
    if not accepted:
        return []
    return [
        AlertMatch(
            f"{len(accepted):,} matches in one pass. First: {matches[0].message}",
            {"count": len(accepted), "examples": [m.message for m in matches[:5]]},
        )
    ]


class SampleValues(dict):
    is_sample = False


def _banned_samples(connection_id: str, rules: list[dict] | None = None) -> dict[str, list]:
    from tarsier.stats import scan as stats_scan
    from tarsier.quality.engine import NEW_RULE_OPERATORS

    values = SampleValues()
    for rule in rules if rules is not None else alert_store.list_rules(connection_id):
        if rule["kind"] != "banned_value" or (rules is None and rule["paused"]):
            continue
        if (rule["config"] or {}).get("operator") in NEW_RULE_OPERATORS:
            continue
        if (rule["config"] or {}).get("operator") in NEW_RULE_OPERATORS:
            continue
        field = (rule["config"] or {}).get("field")
        name = rule["target_name"]
        if not field or not name:
            continue
        try:
            sample = stats_scan.load_item_sample(connection_id, rule["target_schema"], name)
        except Exception:
            continue
        values.is_sample = values.is_sample or sample.is_sample
        if field in sample.dataframe.columns:
            values.setdefault(field, []).extend(sample.dataframe[field].tolist())
    return values


def _banned_rows(connection_id: str, rules: list[dict] | None = None) -> dict[str, dict]:
    from tarsier.stats.scan import load_item_sample_limited
    from tarsier.quality.engine import NEW_RULE_OPERATORS
    samples = {}
    for rule in rules if rules is not None else alert_store.list_rules(connection_id):
        if rule["kind"] != "banned_value" or (rules is None and rule["paused"]) or rule["config"].get("operator") not in NEW_RULE_OPERATORS:
            continue
        key = item_key(rule["target_schema"],rule["target_name"])
        if key not in samples:
            sample = load_item_sample_limited(connection_id,rule["target_schema"],rule["target_name"],1000)
            samples[key] = {"rows":sample.dataframe.to_dict(orient="records"),"is_sample":sample.is_sample}
    return samples


def _deliver(channel: str, config: dict, fire: dict, title: str) -> tuple[str, str]:
    if channel == "log":
        return "logged", "Written to the Tarsier alert log."
    try:
        if channel in ("slack", "teams"):
            send_chat(channel, f"{title}: {fire['message']}")
            return "sent", f"{channel.title()} message delivered."
        if channel == "webhook":
            send_webhook(webhook_vault.resolve(config), fire)
            return "sent", "Webhook delivered."
        if channel == "email":
            send_email(config.get("email_recipients"), f"Tarsier alert: {title}", fire["message"])
            return "sent", "Email delivered."
        return "logged", "Written to the Tarsier alert log."
    except DeliveryError as exc:
        return "failed", str(exc)
