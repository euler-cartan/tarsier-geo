"""Pure when→if→do graph walk (TAD Phase 7 / PRD §7.6)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Callable

import pandas as pd

from tarsier.alerts.engine import (
    QUALITY_DROP_POINTS,
    ROW_COUNT_DROP_SHARE,
    SIZE_SPIKE_SHARE,
    AlertContext,
    evaluate_rule,
)
from tarsier.quality.engine import _when_mask

TRIGGER_KINDS = (
    "any_change",
    "schedule",
    "threshold",
    "specific_user",
    "quality_failure",
    "new_feature",
    "schema_change", "layer_presence", "freshness",
)
CONDITION_KINDS = ("user_eq", "count_drop", "layer_eq", "value_out_of_range", "event_action", "quality_below", "has_failures", "item_kind")
ACTION_KINDS = ("email", "chat", "webhook", "log", "run_quality", "ai_summarize", "scan_statistics", "change_report")
KIND_TO_ROLE = {
    **{k: "trigger" for k in TRIGGER_KINDS},
    **{k: "condition" for k in CONDITION_KINDS},
    **{k: "action" for k in ACTION_KINDS},
}

TRIGGER_LABELS = {
    "any_change": "On any change",
    "schedule": "On a schedule",
    "threshold": "Threshold crossed",
    "specific_user": "Specific user's action",
    "quality_failure": "Quality check failed",
    "new_feature": "New feature added",
    "schema_change": "Schema changed",
    "layer_presence": "Layer added or removed",
    "freshness": "Layer is stale",
}
CONDITION_LABELS = {
    "user_eq": "If user = X",
    "count_drop": "If row count drops more than Y%",
    "layer_eq": "If layer = Z",
    "value_out_of_range": "If value is out of range",
    "event_action": "If change action matches",
    "quality_below": "If quality score is below",
    "has_failures": "If quality checks are failing",
    "item_kind": "If item type matches",
}
ACTION_LABELS = {
    "email": "Send email",
    "chat": "Send Slack/Teams message",
    "webhook": "Call a webhook",
    "log": "Write to log",
    "run_quality": "Run a quality check",
    "ai_summarize": "AI summarize and send",
    "scan_statistics": "Refresh statistics",
    "change_report": "Generate change report",
}

NODE_HELP = {
    "any_change": "Runs after captured changes. Requires history logging or polling.",
    "schedule": "Runs daily at a UTC time, or at a repeating interval while Tarsier is running.",
    "threshold": "Compares cached row counts, sizes, and quality scores against the previous evaluation.",
    "specific_user": "Matches the database user in recorded changes. Polling cannot identify users.",
    "quality_failure": "Matches failing checks in the quality cache.",
    "new_feature": "Matches captured insert events.",
    "schema_change": "Matches recorded schema events. Enable change tracking first.",
    "layer_presence": "Compares the current layer inventory with the previous evaluation. First evaluation sets a baseline.",
    "freshness": "Matches layers whose known last update is older than the chosen number of days. Unknown dates do not match.",
    "user_eq": "True when every captured event belongs to this database user.",
    "count_drop": "Compares row counts with the previous evaluation. Requires a baseline.",
    "layer_eq": "Matches the layer in current events or failing checks, otherwise the inventory.",
    "value_out_of_range": "Reads a bounded source sample from the selected schema, layer, and field. This is not a full-data guarantee.",
    "event_action": "True when a captured event has the selected change action.",
    "quality_below": "True when a cached quality score is below the chosen value. Unchecked layers do not match.",
    "has_failures": "True when the selected layer has a failing quality check.",
    "item_kind": "Matches vector layers, tables, or rasters in the cached inventory.",
    "run_quality": "Runs applicable checks. Use a quality condition to route the result. Older workflows may stop here when checks pass; change the continuation setting below.",
    "scan_statistics": "Reads source samples and refreshes local statistics. Does not modify source data.",
    "change_report": "Generates a local report from recorded changes.",
    "log": "Writes a message to automation run history.",
    "email": "Uses the SMTP settings and the recipients below.",
    "chat": "Uses the saved Slack or Teams channel in Settings.",
    "webhook": "Sends a Tarsier JSON notification to the configured URL.",
    "ai_summarize": "Uses the configured AI model to summarize recorded changes and deliver the summary.",
}


@dataclass
class RunContext:
    connection_id: str
    events: list[dict]
    items: list[dict]
    previous_items: list[dict] | None
    quality_failures: list[dict]
    quality_scores: dict[str, int]
    previous_quality: dict[str, int]
    now: datetime
    last_run_at: datetime | None
    dry_run: bool
    sample_values: dict[str, list] | None = None
    trigger_last_runs: dict[str, str] | None = None
    is_sample: bool = False
    previous_is_sample: bool = False


ActionHandler = Callable[[dict, RunContext], dict]


def catalog() -> dict:
    return {
        "triggers": [{"id": k, "label": TRIGGER_LABELS[k], "role": "trigger", "description": NODE_HELP[k]} for k in TRIGGER_KINDS],
        "conditions": [{"id": k, "label": CONDITION_LABELS[k], "role": "condition", "description": NODE_HELP[k]} for k in CONDITION_KINDS],
        "actions": [{"id": k, "label": ACTION_LABELS[k], "role": "action", "description": NODE_HELP[k]} for k in ACTION_KINDS],
        "templates": [
            {"id": tid, "title": t["title"], "blurb": t["blurb"]} for tid, t in TEMPLATES.items()
        ],
    }


def validate_automation_graph(graph: dict) -> dict:
    """Accept only when→if→do nodes whose role matches a known kind.

    Models often swap fields (role=specific_user, kind=new_feature). Those
    combinations are rejected rather than silently kept.
    """
    if not isinstance(graph, dict):
        raise ValueError("Automation graph must be an object.")
    raw_nodes = graph.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("Automation needs at least one node.")
    nodes: list[dict] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_nodes, start=1):
        if not isinstance(raw, dict):
            raise ValueError("Each automation node must be an object.")
        kind = raw.get("kind")
        role = raw.get("role")
        if kind not in KIND_TO_ROLE:
            raise ValueError(f"Unknown automation kind {kind!r}.")
        expected = KIND_TO_ROLE[kind]
        if role is not None and role not in ("trigger", "condition", "action"):
            raise ValueError(f"Unknown automation role {role!r}.")
        if role is not None and role != expected:
            raise ValueError(f"Kind {kind!r} belongs in the {expected} column, not {role}.")
        node_id = str(raw.get("id") or f"{expected[0]}{index}")
        if node_id in seen:
            raise ValueError("Node IDs must be unique.")
        seen.add(node_id)
        config = raw.get("config") if isinstance(raw.get("config"), dict) else {}
        for field, low, high, default in ([('percent', 0.01, 100, 25)] if kind == 'count_drop' else [('score', 0, 100, 80)] if kind == 'quality_below' else [('threshold_days', 1, 36500, 90)] if kind == 'freshness' else []):
            try:
                value = float(config.get(field, default))
                if not math.isfinite(value) or not low <= value <= high:
                    raise ValueError()
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError(f"{field} must be between {low} and {high}.") from exc
            config = {**config, field: value}
        for field, options, default in ([('action', ('insert', 'update', 'delete', 'schema'), 'delete')] if kind == 'event_action' else [('item_kind', ('vector', 'tabular', 'raster'), 'vector')] if kind == 'item_kind' else [('presence', ('added', 'dropped', 'either'), 'either')] if kind == 'layer_presence' else [('interval', ('daily', 'weekly'), 'daily')] if kind == 'change_report' else []):
            if config.get(field, default) not in options:
                raise ValueError(f"Choose a supported {field}.")
        if kind == "schedule":
            try:
                hour, minute = int(config.get("hour", 18)), int(config.get("minute", 0))
                interval = config.get("every_minutes")
                if not 0 <= hour <= 23 or not 0 <= minute <= 59 or (interval is not None and int(interval) < 1):
                    raise ValueError()
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Choose a valid schedule hour, minute, and positive interval.") from exc
            config = {**config, "hour": hour, "minute": minute}
        if kind == "value_out_of_range" and config.get("operator", "eq") not in ("eq", "ne", "gt", "gte", "lt", "lte", "is_null", "is_not_null"):
            raise ValueError("Choose a supported comparison operator.")
        nodes.append({"id": node_id, "role": expected, "kind": kind, "config": config})
        position = raw.get("position")
        if isinstance(position, dict):
            if all(isinstance(position.get(k), (int, float)) and math.isfinite(position[k]) and abs(position[k]) <= 10000 for k in ("x", "y")):
                nodes[-1]["position"] = {k: position[k] for k in ("x", "y")}
    ids = {n["id"] for n in nodes}
    raw_edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    edges = []
    for edge in raw_edges:
        if not isinstance(edge, dict):
            raise ValueError("Each connection must be an object.")
        src, dst = edge.get("from"), edge.get("to")
        if src not in ids or dst not in ids or src == dst:
            raise ValueError("Connections must join two different existing nodes.")
        branch = edge.get("branch", "true")
        source = next(n for n in nodes if n["id"] == src)
        target = next(n for n in nodes if n["id"] == dst)
        if target["role"] == "trigger":
            raise ValueError("Triggers cannot have incoming connections.")
        if branch not in ("true", "false") or (branch == "false" and source["role"] != "condition"):
            raise ValueError("Only conditions have a false output.")
        entry = {"from": src, "to": dst}
        if source["role"] == "condition":
            entry["branch"] = branch
        if entry in edges:
            raise ValueError("This connection already exists.")
        edges.append(entry)
    if "edges" not in graph and len(nodes) > 1:
        edges = [{"from": nodes[i]["id"], "to": nodes[i + 1]["id"]} for i in range(len(nodes) - 1)]
        if any(nodes[i + 1]["role"] == "trigger" for i in range(len(nodes) - 1)):
            raise ValueError("Triggers cannot have incoming connections.")
    roles = {n["role"] for n in nodes}
    if "trigger" not in roles or "action" not in roles:
        raise ValueError("Automation needs at least one trigger and one action.")
    outgoing = {node_id: [] for node_id in ids}
    for edge in edges:
        outgoing[edge["from"]].append(edge["to"])
    visited, active = set(), set()
    def visit(node_id):
        if node_id in active:
            raise ValueError("Automation connections cannot contain a cycle.")
        if node_id in visited:
            return
        active.add(node_id)
        for child in outgoing[node_id]:
            visit(child)
        active.remove(node_id)
        visited.add(node_id)
    for node in nodes:
        if node["role"] == "trigger":
            visit(node["id"])
    if visited != ids:
        raise ValueError("Connect every node to a trigger. Disconnected nodes cannot run.")
    return {"nodes": nodes, "edges": edges}


def template_graph(template_id: str) -> dict | None:
    spec = TEMPLATES.get(template_id)
    if spec is None:
        return None
    return {"title": spec["title"], "graph": spec["graph"]}


TEMPLATES = {
    "mass_delete": {
        "title": "Log mass deletes and edits",
        "blurb": "When a mass delete or edit is captured, write it to the log.",
        "graph": {
            "nodes": [
                {"id": "t1", "role": "trigger", "kind": "any_change", "config": {"mass_only": True}},
                {"id": "a1", "role": "action", "kind": "log", "config": {"message": "Mass change"}},
            ],
            "edges": [{"from": "t1", "to": "a1"}],
        },
    },
    "evening_summary": {
        "title": "Evening change summary",
        "blurb": "Every evening, summarize today's changes in plain English.",
        "graph": {
            "nodes": [
                {"id": "t1", "role": "trigger", "kind": "schedule", "config": {"hour": 18, "minute": 0}},
                {
                    "id": "a1",
                    "role": "action",
                    "kind": "ai_summarize",
                    "config": {"notify": "email"},
                },
            ],
            "edges": [{"from": "t1", "to": "a1"}],
        },
    },
    "quality_then_notify": {
        "title": "Change → quality check → notify",
        "blurb": "On any change, run quality checks; if they fail, log and notify.",
        "graph": {
            "nodes": [
                {"id": "t1", "role": "trigger", "kind": "any_change", "config": {}},
                {"id": "a1", "role": "action", "kind": "run_quality", "config": {"continue_on_pass": True}},
                {"id": "c1", "role": "condition", "kind": "has_failures", "config": {}},
                {"id": "a2", "role": "action", "kind": "log", "config": {"message": "Quality follow-up"}},
                {"id": "a3", "role": "action", "kind": "email", "config": {}},
            ],
            "edges": [
                {"from": "t1", "to": "a1"},
                {"from": "a1", "to": "c1"},
                {"from": "c1", "to": "a2", "branch": "true"},
                {"from": "a2", "to": "a3"},
            ],
        },
    },
}

# Templates create drafts. Nothing is saved or delivered until the user saves.
for _id, _title, _blurb, _trigger, _config, _action in (
    ("schema_watch", "Record schema changes", "Keep an automation history entry when a recorded schema change appears.", "schema_change", {}, "log"),
    ("inventory_watch", "Watch layer inventory", "Record layers added or removed after the initial baseline.", "layer_presence", {"presence": "either"}, "log"),
    ("freshness_watch", "Watch stale layers", "Check known update dates and log layers older than 90 days.", "freshness", {"threshold_days": 90}, "log"),
    ("daily_statistics", "Morning statistics refresh", "Refresh local statistics from source samples each morning at 07:00 UTC.", "schedule", {"hour": 7, "minute": 0}, "scan_statistics"),
    ("daily_report", "Daily recorded-change report", "Create a local daily change report at 18:00 UTC. No AI or delivery required.", "schedule", {"hour": 18, "minute": 0}, "change_report"),
    ("quality_watch", "Log quality failures", "Record a run when cached quality checks contain failures.", "quality_failure", {}, "log"),
):
    TEMPLATES[_id] = {"title": _title, "blurb": _blurb, "graph": {
        "nodes": [{"id": "t1", "role": "trigger", "kind": _trigger, "config": _config}, {"id": "a1", "role": "action", "kind": _action, "config": {"message": _title} if _action == "log" else {}}],
        "edges": [{"from": "t1", "to": "a1"}],
    }}


def is_schedule_due(config: dict, last_run_at: datetime | None, now: datetime) -> bool:
    every = config.get("every_minutes")
    if every:
        if last_run_at is None:
            return True
        last = _aware(last_run_at)
        return now - last >= timedelta(minutes=int(every))
    hour = int(config.get("hour", 0))
    minute = int(config.get("minute", 0))
    if now.hour < hour or (now.hour == hour and now.minute < minute):
        return False
    if last_run_at is None:
        return True
    return _aware(last_run_at).date() < now.date()


def trigger_matches(node: dict, ctx: RunContext) -> bool:
    kind = node.get("kind")
    config = node.get("config") or {}
    if kind in ("schema_change", "layer_presence", "freshness"):
        return bool(evaluate_rule(kind, {**config, "target_schema": config.get("schema", ""), "target_name": config.get("layer", "")}, _alert_ctx(ctx)))
    if kind == "any_change":
        events = ctx.events
        if config.get("mass_only"):
            events = [e for e in events if e.get("is_mass")]
        return bool(events)
    if kind == "schedule":
        last = ctx.last_run_at
        if ctx.trigger_last_runs is not None:
            stamp = ctx.trigger_last_runs.get(node.get("id"))
            last = datetime.fromisoformat(stamp) if stamp else None
        return is_schedule_due(config, last, ctx.now)
    if kind == "threshold":
        if ctx.previous_items is None:
            return False
        alert_ctx = _alert_ctx(ctx)
        for alert_kind in ("row_count_drop", "size_spike", "quality_score_drop"):
            if evaluate_rule(alert_kind, config, alert_ctx):
                return True
        return False
    if kind == "specific_user":
        want = str(config.get("user") or "").lower()
        return any(str(e.get("db_user") or "").lower() == want for e in ctx.events) if want else False
    if kind == "quality_failure":
        return bool(ctx.quality_failures)
    if kind == "new_feature":
        return any(e.get("action") == "insert" for e in ctx.events)
    return False


def condition_holds(node: dict, ctx: RunContext) -> bool:
    kind = node.get("kind")
    config = node.get("config") or {}
    schema, name = config.get("schema") or "", config.get("layer") or ""
    def targeted(item):
        return (not name or item.get("name") == name) and (not schema or item.get("schema") == schema)
    if kind == "event_action":
        return any(targeted(e) and e.get("action") == config.get("action", "delete") for e in ctx.events)
    if kind == "has_failures":
        return any(targeted(f) for f in ctx.quality_failures)
    if kind == "item_kind":
        return any(targeted(i) and i.get("kind") == config.get("item_kind", "vector") for i in ctx.items)
    if kind == "quality_below":
        from tarsier.alerts.engine import item_key
        return any(targeted(i) and ctx.quality_scores.get(item_key(i.get("schema") or "", i["name"]), 101) < float(config.get("score", 80)) for i in ctx.items)
    if kind == "user_eq":
        want = str(config.get("user") or "").lower()
        if not want:
            return False
        if not ctx.events:
            return False
        return all(str(e.get("db_user") or "").lower() == want for e in ctx.events)
    if kind == "count_drop":
        if ctx.previous_items is None:
            return False
        share = float(config.get("percent") or ROW_COUNT_DROP_SHARE * 100) / 100
        alert_ctx = _alert_ctx(ctx)
        # evaluate_rule uses locked 25%; honor a stricter/looser percent here.
        return bool(evaluate_rule("row_count_drop", {**config, "threshold_share": share, "target_name": name, "target_schema": schema}, alert_ctx))
    if kind == "layer_eq":
        name = config.get("layer") or config.get("name") or ""
        if not name:
            return True
        if ctx.events:
            return any(targeted(e) for e in ctx.events)
        if ctx.quality_failures:
            return any(targeted(f) for f in ctx.quality_failures)
        return any(targeted(i) for i in ctx.items)
    if kind == "value_out_of_range":
        field = config.get("field")
        sample_key = f"node:{node.get('id')}:{field}"
        values = (ctx.sample_values or {}).get(sample_key, (ctx.sample_values or {}).get(field))
        if not field or values is None:
            return False
        series = pd.Series(values)
        mask = _when_mask(series, str(config.get("operator") or "eq"), config.get("value"))
        return bool(mask.any())
    return True


def walk_graph(graph: dict, ctx: RunContext, handler: ActionHandler) -> tuple[bool, str, list[dict]]:
    nodes = {n["id"]: n for n in graph.get("nodes") or [] if "id" in n}
    outgoing: dict[str, list[dict]] = {nid: [] for nid in nodes}
    incoming = {nid: 0 for nid in nodes}
    for edge in graph.get("edges") or []:
        src, dst = edge.get("from"), edge.get("to")
        if src in nodes and dst in nodes:
            outgoing[src].append(edge)
            incoming[dst] += 1
    roots = [nid for nid, count in incoming.items() if count == 0]
    trace: list[dict] = []
    any_trigger = False
    any_action = False

    executed: set[str] = set()

    def follow(nid: str, seen: set[str], branch: str = "true") -> None:
        nonlocal any_action
        if nid in seen:
            return
        seen = seen | {nid}
        for edge in outgoing.get(nid, []):
            if nodes[nid].get("role") == "condition" and edge.get("branch", "true") != branch:
                continue
            child = edge["to"]
            if child in executed:
                continue
            executed.add(child)
            node = nodes[child]
            role = node.get("role")
            if role == "condition":
                holds = condition_holds(node, ctx)
                branch = "true" if holds else "false"
                connected = any(e.get("branch", "true") == branch for e in outgoing[child])
                trace.append({"node_id": child, "role": role, "kind": node.get("kind"), "ok": holds, "message": f"Following {branch} output." if connected else f"No connection on {branch} output. This path ends here."})
                follow(child, seen, "true" if holds else "false")
            elif role == "action":
                try:
                    result = handler(node, ctx)
                except Exception:
                    result = {"ok": False, "message": "Action failed. Check the connection and node settings."}
                ok = result.get("ok", True)
                trace.append(
                    {
                        "node_id": child,
                        "role": role,
                        "kind": node.get("kind"),
                        "ok": ok,
                        "message": result.get("message") or "",
                    }
                )
                any_action = True
                if not ok:
                    continue
                if node.get("kind") == "run_quality" and not ctx.quality_failures and not (node.get("config") or {}).get("continue_on_pass"):
                    continue
                follow(child, seen)
            else:
                follow(child, seen)

    for rid in roots:
        node = nodes[rid]
        if node.get("role") != "trigger":
            continue
        matched = trigger_matches(node, ctx)
        trace.append({"node_id": rid, "role": "trigger", "kind": node.get("kind"), "ok": matched})
        if matched:
            any_trigger = True
            if node.get("kind") == "schedule":
                if ctx.trigger_last_runs is None:
                    ctx.trigger_last_runs = {}
                ctx.trigger_last_runs[rid] = ctx.now.isoformat()
            follow(rid, set())

    if not any_trigger:
        return False, "Trigger did not match.", trace
    if not any_action:
        return True, "Trigger matched; no action ran.", trace
    failed = [step for step in trace if step.get("role") == "action" and not step.get("ok")]
    if failed:
        return False, failed[-1].get("message") or "An action failed.", trace
    return True, "Automation ran.", trace


def _alert_ctx(ctx: RunContext) -> AlertContext:
    return AlertContext(
        items=ctx.items,
        previous_items=ctx.previous_items,
        events=ctx.events,
        quality_scores=ctx.quality_scores,
        previous_quality=ctx.previous_quality,
        now=ctx.now,
        sample_values=ctx.sample_values,
        quality_samples={key: ctx.is_sample for key in ctx.quality_scores},
        previous_quality_samples={key: ctx.previous_is_sample for key in ctx.previous_quality},
    )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# silence unused imports if QUALITY_DROP_POINTS referenced only in docs
_ = (QUALITY_DROP_POINTS, SIZE_SPIKE_SHARE)
