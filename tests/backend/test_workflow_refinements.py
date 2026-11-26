from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from tarsier import snapshots
from tarsier.ai import query as ai_query
from tarsier.ai.client import AIError
from tarsier.api.app import create_app
from tarsier.automation import engine, evaluate
from tarsier.storage import alerts, automations, change_log, connections


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    saved = connections.create_connection("Test database", "postgis", {})
    return saved.id, TestClient(create_app())


def context(**changes):
    values = dict(connection_id="c", events=[], items=[{"schema": "public", "name": "pipes", "kind": "vector", "last_modified": "2020-01-01", "row_count": 50}], previous_items=[], quality_failures=[], quality_scores={"public.pipes": 65}, previous_quality={}, now=datetime.now(timezone.utc), last_run_at=None, dry_run=False)
    return engine.RunContext(**{**values, **changes})


def test_snapshot_plan_runs_reviewed_filter_once_with_bound_values(local, monkeypatch):
    connection_id, client = local
    version = snapshots.write_version(connection_id, "public", "inventory", pd.DataFrame({"id": [1, 2, 3], "stock_qty": [3, 12, 20], "supplier": [None, "Atlas", None]}))
    calls = []
    def chat(messages):
        calls.append(messages)
        return SimpleNamespace(content='{"caption":"untrusted prose", "combine":"and", "conditions":[{"column":"stock_qty","op":"<","value":10},{"column":"supplier","op":"is_null"}]}')
    monkeypatch.setattr(ai_query, "chat", chat)
    base = f"/api/connections/{connection_id}/snapshots/{version['id']}"
    plan = client.post(base + "/plan", json={"question": "Items below 10 units AND without a supplier"}).json()
    assert plan["caption"] == "stock_qty < 10 AND supplier IS NULL"
    result = client.post(base + "/query", json={"filter_payload": plan["filter"]}).json()
    assert result["rows"] == [{"id": 1, "stock_qty": 3, "supplier": None}]
    assert len(calls) == 1
    assert result["params"] == [10, 200]
    assert "WHERE \"stock_qty\" < ? AND \"supplier\" IS NULL" in result["sql"]
    attack = "Atlas' OR 1=1 --"
    injected = client.post(base + "/query", json={"filter_payload": {"conditions": [{"column": "supplier", "op": "=", "value": attack}]}}).json()
    assert injected["count"] == 0 and attack not in injected["sql"]


def test_unsupported_ai_intent_is_rejected_not_partially_run(local, monkeypatch):
    monkeypatch.setattr(ai_query, "chat", lambda messages: SimpleNamespace(content='{"unsupported":"Grouping is not supported. Choose a row filter."}'))
    with pytest.raises(AIError, match="Grouping"):
        ai_query.interpret_question("Group by material", [{"name": "material", "type": "text"}])


def test_snapshot_plan_without_ai_configuration_returns_actionable_error(local):
    connection_id, client = local
    version = snapshots.write_version(connection_id, "", "items", pd.DataFrame({"id": [1]}))
    response = client.post(f"/api/connections/{connection_id}/snapshots/{version['id']}/plan", json={"question": "id above 1"})
    assert response.status_code == 400
    assert "AI" in response.json()["detail"]


@pytest.mark.parametrize("kind,config,expected", [
    ("schema_change", {}, True), ("layer_presence", {"presence": "added"}, True),
    ("layer_presence", {"layer": "other"}, False), ("freshness", {"threshold_days": 30}, True),
    ("freshness", {"schema": "other"}, False),
])
def test_new_triggers_honor_targets(kind, config, expected):
    ctx = context(events=[{"action": "schema", "name": "pipes", "schema": "public"}])
    assert engine.trigger_matches({"kind": kind, "config": config}, ctx) is expected


@pytest.mark.parametrize("kind,config,expected", [
    ("event_action", {"action": "delete"}, True), ("event_action", {"action": "insert"}, False),
    ("event_action", {"action": "delete", "schema": "other"}, False),
    ("quality_below", {"score": 80}, True), ("quality_below", {"score": 60}, False),
    ("quality_below", {"layer": "unchecked"}, False),
    ("item_kind", {"item_kind": "vector"}, True), ("item_kind", {"item_kind": "raster"}, False),
    ("has_failures", {}, True), ("has_failures", {"schema": "other"}, False),
])
def test_conditions_evaluate_cached_context(kind, config, expected):
    ctx = context(events=[{"action": "delete", "schema": "public", "name": "pipes"}], quality_failures=[{"schema": "public", "name": "pipes"}])
    assert engine.condition_holds({"kind": kind, "config": config}, ctx) is expected


def test_true_false_routing_and_action_failure_stop_downstream():
    graph = {"nodes": [
        {"id": "t", "role": "trigger", "kind": "schedule", "config": {"every_minutes": 1}},
        {"id": "c", "role": "condition", "kind": "quality_below", "config": {"score": 50}},
        {"id": "yes", "role": "action", "kind": "log"}, {"id": "no", "role": "action", "kind": "log"},
        {"id": "after", "role": "action", "kind": "log"}],
        "edges": [{"from": "t", "to": "c"}, {"from": "c", "to": "yes", "branch": "true"}, {"from": "c", "to": "no", "branch": "false"}, {"from": "no", "to": "after"}]}
    graph = engine.validate_automation_graph(graph)
    called = []
    def handler(node, ctx):
        called.append(node["id"])
        return {"ok": False, "message": "Delivery failed"}
    ok, message, trace = engine.walk_graph(graph, context(), handler)
    assert not ok and called == ["no"] and message == "Delivery failed"
    assert [s["node_id"] for s in trace] == ["t", "c", "no"]


def test_all_templates_validate_and_reject_invalid_ports():
    for template in engine.TEMPLATES.values():
        engine.validate_automation_graph(template["graph"])
    graph = engine.template_graph("daily_report")["graph"]
    with pytest.raises(ValueError, match="false output"):
        engine.validate_automation_graph({**graph, "edges": [{"from": "t1", "to": "a1", "branch": "false"}]})
    with pytest.raises(ValueError, match="incoming"):
        engine.validate_automation_graph({**graph, "edges": [{"from": "a1", "to": "t1"}]})


@pytest.mark.parametrize("kind,config", [("freshness", {"threshold_days": -1}), ("quality_below", {"score": 101}), ("event_action", {"action": "drop_database"}), ("item_kind", {"item_kind": "unknown"}), ("count_drop", {"percent": "nan"})])
def test_new_node_parameters_rejected(kind, config):
    role = engine.KIND_TO_ROLE[kind]
    graph = {"nodes": [{"id": "t", "role": "trigger", "kind": "schedule"}, {"id": "c", "role": role, "kind": kind, "config": config}, {"id": "a", "role": "action", "kind": "log"}], "edges": []}
    with pytest.raises(ValueError):
        engine.validate_automation_graph(graph)


def test_local_actions_have_backend_effects_and_dry_run_has_none(local, monkeypatch):
    connection_id, client = local
    ctx = context(connection_id=connection_id)
    scans = []
    monkeypatch.setattr("tarsier.stats.scan.scan_item_stats", lambda *args: scans.append(args))
    node = {"kind": "scan_statistics", "config": {"schema": "public", "layer": "pipes"}}
    assert evaluate._handle(node, ctx)["ok"]
    assert scans == [(connection_id, "public", "pipes")]
    assert evaluate._handle({"kind": "change_report", "config": {"interval": "weekly"}}, ctx)["ok"]
    assert change_log.latest_report(connection_id)["interval"] == "weekly"
    assert change_log.get_state(connection_id).report_interval is None
    ctx.dry_run = True
    scans.clear()
    evaluate._handle(node, ctx)
    assert not scans


def test_alert_preview_does_not_deliver_persist_or_advance_baseline(local, monkeypatch):
    connection_id, client = local
    def forbidden(*args):
        pytest.fail("Preview must not deliver")
    monkeypatch.setattr("tarsier.alerts.evaluate._deliver", forbidden)
    base = f"/api/connections/{connection_id}"
    body = {"kind": "row_count_drop", "config": {"threshold_share": .1, "notify": "log"}}
    result = client.post(base + "/alerts/preview", json=body)
    assert result.status_code == 200 and result.json()["baseline_available"] is False
    assert alerts.list_rules(connection_id) == [] and alerts.list_fires(connection_id) == []
    assert alerts.get_snapshot(connection_id) is None
    assert client.post(base + "/alerts", json={**body, "config": {"threshold_share": -1}}).status_code == 400
    rule = client.post(base + "/alerts", json=body).json()
    other = connections.create_connection("Other", "postgis", {}).id
    assert client.delete(f"/api/connections/{other}/alerts/{rule['id']}").status_code == 404


def test_report_schedule_off_and_date_validation(local):
    connection_id, client = local
    base = f"/api/connections/{connection_id}/changes"
    for params in ({"start": "invalid"}, {"start": "2026-10-17", "end": "2026-10-01"}):
        assert client.get(base, params=params).status_code == 400
    assert client.put(base + "/report/schedule", json={"interval": "daily"}).status_code == 200
    assert change_log.get_state(connection_id).report_interval == "daily"
    assert client.put(base + "/report/schedule", json={"interval": "off"}).status_code == 200
    assert change_log.get_state(connection_id).report_interval is None


def test_snapshot_based_automation_sets_and_uses_baseline(local, monkeypatch):
    connection_id, _ = local
    auto = automations.create_automation(connection_id, {"title": "Inventory", "graph": engine.template_graph("inventory_watch")["graph"]})
    monkeypatch.setattr(evaluate.item_cache, "list_items", lambda cid: [])
    assert evaluate.evaluate_connection(connection_id) == []
    assert automations.get_automation(auto["id"])["snapshot"]["items"] == []
    monkeypatch.setattr(evaluate.item_cache, "list_items", lambda cid: [SimpleNamespace(schema="public", name="pipes", kind="vector", row_count=1, size_bytes=100, last_modified=None)])
    runs = evaluate.evaluate_connection(connection_id)
    assert len(runs) == 1 and runs[0]["ok"]
    assert evaluate.evaluate_connection(connection_id) == []


def test_same_field_conditions_use_their_own_layer_samples():
    ctx = context(sample_values={"node:first:height": [1], "node:second:height": [100]})
    config = {"field": "height", "operator": "gt", "value": 50}
    assert not engine.condition_holds({"id": "first", "kind": "value_out_of_range", "config": config}, ctx)
    assert engine.condition_holds({"id": "second", "kind": "value_out_of_range", "config": config}, ctx)


@pytest.mark.parametrize("continue_on_pass,expected", [(True, ["run_quality", "log"]), (False, ["run_quality"])])
def test_quality_continuation_can_route_passing_checks(continue_on_pass, expected):
    graph = {"nodes": [{"id": "t", "role": "trigger", "kind": "schedule", "config": {"every_minutes": 1}}, {"id": "q", "role": "action", "kind": "run_quality", "config": {"continue_on_pass": continue_on_pass}}, {"id": "a", "role": "action", "kind": "log"}], "edges": [{"from": "t", "to": "q"}, {"from": "q", "to": "a"}]}
    actions = []
    engine.walk_graph(graph, context(), lambda node, ctx: actions.append(node["kind"]) or {"ok": True})
    assert actions == expected


def test_two_daily_schedule_triggers_keep_independent_last_runs():
    now = datetime(2026, 10, 17, 18, 0, tzinfo=timezone.utc)
    ctx = context(now=now, last_run_at=now.replace(hour=7), trigger_last_runs={"morning": now.replace(hour=7).isoformat()})
    assert not engine.trigger_matches({"id": "morning", "kind": "schedule", "config": {"hour": 7}}, ctx)
    assert engine.trigger_matches({"id": "evening", "kind": "schedule", "config": {"hour": 18}}, ctx)
    graph = {"nodes": [{"id": "evening", "role": "trigger", "kind": "schedule", "config": {"hour": 18}}, {"id": "a", "role": "action", "kind": "log"}], "edges": [{"from": "evening", "to": "a"}]}
    engine.walk_graph(graph, ctx, lambda node, ctx: {"ok": True})
    assert ctx.trigger_last_runs["evening"] == now.isoformat()
    assert not engine.trigger_matches(graph["nodes"][0], ctx)
