"""AI jobs 2–4 (PRD §7.7). Schema/counts only  -  never raw row values, never writes."""

from __future__ import annotations

import difflib
import re
from datetime import datetime, timezone

from tarsier.ai.client import AIError, chat
from tarsier.ai.query import _extract_json
from tarsier.automation.engine import (
    ACTION_KINDS,
    CONDITION_KINDS,
    TRIGGER_KINDS,
    validate_automation_graph,
)
from tarsier.storage import change_log, item_cache, quality_cache


def explain_changes(connection_id: str) -> dict:
    summary = change_counts(connection_id)
    listing = _format_change_counts(summary)
    result = chat(
        [
            {
                "role": "system",
                "content": (
                    "You explain geospatial database change activity in plain English. "
                    "You are given counts only  -  never row values. Do not suggest writing to the database. "
                    "Reply with a short paragraph."
                ),
            },
            {"role": "user", "content": listing},
        ]
    )
    return {"job": "explain-changes", "text": result.content, "facts": summary}


def explain_quality(connection_id: str, schema: str, name: str, check_id: str) -> dict:
    checks = quality_cache.get_checks(connection_id, schema, name)
    check = checks.get(check_id)
    if check is None:
        raise AIError("That quality check hasn't been run yet.")
    facts = {
        "layer": f"{schema}.{name}" if schema else name,
        "check_id": check_id,
        "status": getattr(check, "status", None),
        "fail_count": getattr(check, "fail_count", 0),
        "message": getattr(check, "message", None),
    }
    result = chat(
        [
            {
                "role": "system",
                "content": (
                    "You explain a geospatial quality-check result and suggest a fix a person could make. "
                    "You never apply the fix. You are not given geometries or row values. "
                    "Reply with two short paragraphs: explanation, then suggested fix."
                ),
            },
            {"role": "user", "content": str(facts)},
        ]
    )
    return {"job": "explain-quality", "text": result.content, "facts": facts}


_ANSWER_RULES = """You are the assistant inside Tarsier, an app that monitors geospatial data.
You are talking with the person who looks after this data. Be clear, friendly and complete.

How to answer:
- Start with the direct answer. Then explain what it means in everyday words, and say what the person can do next and on which screen.
- For a question about data, 3 to 7 sentences is usual. Use "- " bullet points when listing more than two things. Never answer with a fragment.
- A follow-up such as "why?" or "what do you mean?" refers to your previous answer: explain that answer more simply, with the reason.
- A greeting gets one short friendly sentence offering help.
- Use only the FACTS and this conversation. Never invent layer names, numbers or reasons. If the FACTS do not show it, say so and say where to look.
- Health scores run from 0 to 100; 100 means every check that ran passed.
- If change tracking is off, never say "0 changes": say changes are not being tracked, so it is unknown whether data changed.
- Do not describe Tarsier or list its features unless asked.
- You cannot open screens, see row values or change anything.
- Plain text. You may use **bold** for names.

Screens: Overview (health, full check), Statistics, Snapshots, Changes, Alerts, Automations, Flowchart. Opening a layer shows its Statistics and Quality tabs.
About Tarsier (use only if asked): a local app showing health scores, statistics, quality checks, change history, alerts, automations, a relationship flowchart and snapshots for PostGIS, Oracle, SQL Server, GIS files, ArcGIS and GeoServer. It does not edit the monitored data."""

_HISTORY_MESSAGES = 8


def answer_question(connection_id: str, question: str, history: list[dict] | None = None) -> dict:
    """Answer a question from cached metadata and counts, never row values."""
    question = question.strip()[:2000]
    if not question:
        raise AIError("Type a question first.")
    history = (history or [])[-_HISTORY_MESSAGES:]
    unknown = _unknown_layer_reply(connection_id, question)
    if unknown:
        return {"job": "ask", "text": unknown}
    # A follow-up names no layer itself, so keep the layers named earlier in view.
    context = " ".join([m["text"] for m in history if m["role"] == "user"] + [question])
    facts = _answer_facts(connection_id, context)
    messages = [{"role": "system", "content": f"{_ANSWER_RULES}{chr(10) * 2}FACTS:{chr(10)}{facts}"}]
    for item in history:
        messages.append({"role": "assistant" if item["role"] == "ai" else "user", "content": item["text"][:1500]})
    messages.append({"role": "user", "content": question})
    return {"job": "ask", "text": chat(messages).content.strip()}


def _unknown_layer_reply(connection_id: str, question: str) -> str | None:
    """Small models invent figures for layers that do not exist, so answer that case directly."""
    from tarsier.storage import connections

    names = [(i.schema, i.name) for i in item_cache.list_items(connection_id)]
    if not names or any(_mentions(question.lower(), name) for _, name in names):
        return None
    asked = re.findall(r"[A-Za-z][A-Za-z0-9]*(?:[._][A-Za-z0-9]+)*_[A-Za-z0-9_]+", question)
    if not asked:
        return None
    wanted = asked[0]
    short = wanted.lower().split(".")[-1]
    elsewhere = [
        c.name
        for c in connections.list_connections()
        if c.id != connection_id and any(_mentions(short, i.name) for i in item_cache.list_items(c.id))
    ]
    here = connections.get_connection(connection_id)
    text = f"I can't find a layer or table called **{wanted}** in **{here.name if here else 'this connection'}**."
    close = difflib.get_close_matches(short, [name.lower() for _, name in names], n=3, cutoff=0.5)
    if close:
        text += " Did you mean " + ", ".join(f"**{c}**" for c in close) + "?"
    if elsewhere:
        text += f" It is in **{elsewhere[0]}**: choose that connection at the top of the page, then ask again."
    return text


def _answer_facts(connection_id: str, question: str) -> str:
    """The small set of facts relevant to a question: connection totals plus any layer it names."""
    from tarsier.overview import get_overview

    summary = get_overview(connection_id)
    changes = change_counts(connection_id)
    state = change_log.get_state(connection_id)
    tracking = state.mode if summary.connection_type == "postgis" and state else "none"
    lines = [
        f"Connection: {summary.connection_name} (type {summary.connection_type})",
        f"Layers: {summary.total_layers}",
        f"Overall health score (0-100): {summary.health_score if summary.health_score is not None else 'not checked yet'}",
    ]
    if tracking == "none":
        why = "it can be enabled on the Changes screen" if summary.connection_type == "postgis" else "not available for this connection type"
        lines.append(f"Change tracking: OFF ({why}). Whether data changed is unknown.")
    else:
        lines.append(f"Change tracking: on ({tracking}). Changes today: {changes['event_count']}, by layer: {changes['by_layer']}")

    low = sorted((l for l in summary.layers if l.health_score is not None and l.health_score < 100), key=lambda l: l.health_score)
    if low:
        lines.append("Layers with the lowest health: " + ", ".join(f"{_label(l)} {l.health_score}" for l in low[:6]))

    asked = question.lower()
    named = [l for l in summary.layers if _mentions(asked, l.name)][:4]
    for layer in named:
        rows = "unknown" if layer.row_count is None else layer.row_count
        lines.append(
            f"Layer {_label(layer)}: kind {layer.kind}, rows {rows}{' (estimate)' if layer.row_count_is_estimate else ''}, "
            f"projection {'EPSG:' + str(layer.srid) if layer.srid else 'none'}, "
            f"health {layer.health_score if layer.health_score is not None else 'not checked'}"
        )
        checks = quality_cache.get_checks(connection_id, layer.schema, layer.name)
        if checks:
            failed = [f"check '{key}' failed, {c.fail_count} rows affected" for key, c in checks.items() if c.fail_count]
            lines.append(
                f"  Quality of {_label(layer)}: {len(failed)} of {len(checks)} checks found problems. "
                + "; ".join(failed)
            )
    if not named:
        names = [_label(l) for l in summary.layers]
        lines.append("Layer names: " + ", ".join(names[:60]) + (" and more" if len(names) > 60 else ""))
    return chr(10).join(lines)


def _label(layer) -> str:
    return f"{layer.schema}.{layer.name}" if layer.schema else layer.name


def _mentions(question: str, name: str) -> bool:
    """True when the question names the layer, with or without a file extension."""
    for candidate in {name.lower(), name.lower().rsplit(".", 1)[0]}:
        if re.search(rf"(?<![a-z0-9_]){re.escape(candidate)}(?![a-z0-9_])", question):
            return True
    return False


def suggest_questions(connection_id: str) -> dict:
    """Ask the configured model for starter questions about this connection's layers.

    Only layer names and kinds are sent (no row values), and nothing is hardcoded:
    if the model cannot produce questions, the caller gets an error, not a canned list.
    """
    items = item_cache.list_items(connection_id)[:60]
    if not items:
        raise AIError("Run a check first, so Tarsier knows which layers this connection has.")
    listing = "; ".join(
        f"{item.schema + '.' if item.schema else ''}{item.name} ({item.kind or 'item'})" for item in items
    )
    result = chat(
        [
            {
                "role": "system",
                "content": (
                    "You suggest questions a person monitoring a geospatial database could ask an assistant "
                    "about its layers: health, quality, statistics, changes, projections and relationships. "
                    "Write 4 short, specific questions (under 90 characters each) that mention real layer names "
                    "from the list. Reply with JSON only: {\"questions\": [\"...\", \"...\"]}."
                ),
            },
            {"role": "user", "content": f"Layers: {listing}"},
        ]
    )
    try:
        payload = _extract_json(result.content)
    except (ValueError, TypeError) as exc:
        raise AIError("The model did not return suggested questions. Try another model.") from exc
    raw = payload.get("questions") if isinstance(payload, dict) else None
    questions = [q.strip()[:140] for q in (raw or []) if isinstance(q, str) and q.strip()][:4]
    if not questions:
        raise AIError("The model did not return suggested questions. Try another model.")
    return {"job": "suggest-questions", "text": "", "questions": questions}


def build_automation(prompt: str) -> dict:
    listing = (
        f"Triggers: {', '.join(TRIGGER_KINDS)}. "
        f"Conditions: {', '.join(CONDITION_KINDS)}. "
        f"Actions: {', '.join(ACTION_KINDS)}."
    )
    result = chat(
        [
            {
                "role": "system",
                "content": (
                    "You turn a 'notify me when…' request into a Tarsier automation graph. "
                    "Reply with JSON only. role must be exactly trigger, condition, or action. "
                    "kind must belong to that role. Never put a kind name in the role field. "
                    f"Allowed: {listing} "
                    "Example for 'every evening summarize today's changes and email the team': "
                    '{"title":"Evening change summary","graph":{"nodes":['
                    '{"id":"t1","role":"trigger","kind":"schedule","config":{"hour":18,"minute":0}},'
                    '{"id":"a1","role":"action","kind":"ai_summarize","config":{"notify":"email"}}],'
                    '"edges":[{"from":"t1","to":"a1"}]}}. '
                    "Always include at least one trigger and one action. Never output SQL. "
                    "Include every step the request asks for, in order: a check to run, a condition "
                    "such as 'if any fail', and each notification. Never drop a step. If a step cannot "
                    'be built from the allowed kinds, reply {"unsupported":"what cannot be built and why"}.'
                ),
            },
            {"role": "user", "content": prompt.strip()},
        ]
    )
    try:
        payload = _extract_json(result.content)
        if isinstance(payload, dict) and payload.get("unsupported"):
            raise AIError(str(payload["unsupported"])[:600])
    except (ValueError, TypeError) as exc:
        raise AIError("The AI did not return a usable automation. Try rephrasing.") from exc
    graph = payload.get("graph") or payload
    try:
        graph = validate_automation_graph(graph if isinstance(graph, dict) else {})
    except ValueError as exc:
        raise AIError(str(exc) + " Try rephrasing.") from exc
    title = payload.get("title") or "Draft automation"
    return {
        "job": "build-automation",
        "text": title,
        "title": title,
        "graph": graph,
    }


def change_counts(connection_id: str) -> dict:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    events = [
        e
        for e in change_log.list_events(connection_id, start=start)
        if _event_when(e) and _event_when(e) >= start
    ]
    by_action: dict[str, int] = {}
    by_layer: dict[str, int] = {}
    by_user: dict[str, int] = {}
    mass = 0
    for event in events:
        by_action[event.action] = by_action.get(event.action, 0) + 1
        layer = f"{event.schema}.{event.name}" if event.schema else event.name
        by_layer[layer] = by_layer.get(layer, 0) + 1
        user = event.db_user or "unknown"
        by_user[user] = by_user.get(user, 0) + 1
        if event.is_mass:
            mass += 1
    items = [{"schema": i.schema, "name": i.name} for i in item_cache.list_items(connection_id)]
    return {
        "event_count": len(events),
        "by_action": by_action,
        "by_layer": by_layer,
        "by_user": by_user,
        "mass_events": mass,
        "layer_count": len(items),
        "day": start.date().isoformat(),
    }


def draft_rule(connection_id: str, schema: str, name: str, prompt: str) -> dict:
    from tarsier.storage import preview_cache
    preview = preview_cache.get_preview(connection_id, schema, name)
    if not prompt.strip():
        raise AIError("Describe the quality rule you want.")
    columns = preview.get("columns", []) if isinstance(preview, dict) else []
    result = chat([
        {"role": "system", "content": 'Draft a read-only quality rule as JSON: {"kind":"attribute","field":"diameter","operator":"gt","value":"0"}. Operators: gt,gte,lt,lte,eq,ne,is_null,is_not_null. A geometry rule has kind geometry_type, operator eq, value the matching attribute, and geometry_type Point,LineString,Polygon,MultiPoint,MultiLineString,MultiPolygon. Do not execute or save anything. Use supplied column names when available. Use only a column the request is clearly about; never substitute a different column. If no supplied column fits the request, reply {"unsupported":"which part has no matching column"}.'},
        {"role": "user", "content": f"Item: {name}. Columns: {columns}. Request: {prompt}"},
    ])
    try:
        rule = _extract_json(result.content)
        if isinstance(rule, dict) and rule.get("unsupported"):
            raise AIError(str(rule["unsupported"])[:600])
        if rule.get("kind") not in ("attribute", "geometry_type") or rule.get("operator") not in ("gt", "gte", "lt", "lte", "eq", "ne", "is_null", "is_not_null") or not isinstance(rule.get("field"), str) or not rule["field"].strip():
            raise ValueError()
        if columns and rule["field"] not in {c["name"] for c in columns}:
            raise ValueError()
        if rule.get("value") is not None:
            rule["value"] = str(rule["value"])
    except (ValueError, TypeError) as exc:
        raise AIError("The AI did not return a usable rule. Try rephrasing.") from exc
    return {"job": "draft-rule", "text": "Review this quality rule before saving.", "rule": rule}


def _format_change_counts(summary: dict) -> str:
    return (
        f"UTC day {summary['day']}: {summary['event_count']} changes. "
        f"By action: {summary['by_action']}. By layer: {summary['by_layer']}. "
        f"By user: {summary['by_user']}. Mass batches: {summary['mass_events']}."
    )


def _event_when(event) -> datetime | None:
    value = event.occurred_at
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
