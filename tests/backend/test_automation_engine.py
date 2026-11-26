from datetime import datetime, timedelta, timezone

import pytest

from tarsier.automation.engine import (
    ACTION_KINDS,
    CONDITION_KINDS,
    TRIGGER_KINDS,
    RunContext,
    is_schedule_due,
    template_graph,
    validate_automation_graph,
    walk_graph,
)

NOW = datetime(2026, 10, 11, 18, 30, tzinfo=timezone.utc)


def ctx(**kwargs):
    base = RunContext(
        connection_id="c1",
        events=[],
        items=[{"schema": "public", "name": "water_mains", "kind": "vector", "row_count": 100, "size_bytes": 1000}],
        previous_items=[{"schema": "public", "name": "water_mains", "row_count": 100, "size_bytes": 1000}],
        quality_failures=[],
        quality_scores={},
        previous_quality={},
        now=NOW,
        last_run_at=None,
        dry_run=True,
    )
    for key, value in kwargs.items():
        setattr(base, key, value)
    return base


def test_catalog_covers_prd_kinds():
    assert set(TRIGGER_KINDS) == {
        "any_change",
        "schedule",
        "threshold",
        "specific_user",
        "quality_failure",
        "new_feature", "schema_change", "layer_presence", "freshness",
    }
    assert set(CONDITION_KINDS) == {"user_eq", "count_drop", "layer_eq", "value_out_of_range", "event_action", "quality_below", "has_failures", "item_kind"}
    assert set(ACTION_KINDS) == {"email", "chat", "webhook", "log", "run_quality", "ai_summarize", "scan_statistics", "change_report"}


def test_schedule_due_daily_and_interval():
    assert is_schedule_due({"hour": 18, "minute": 0}, None, NOW)
    assert not is_schedule_due({"hour": 19, "minute": 0}, None, NOW)
    last = NOW.replace(hour=18, minute=5)
    assert not is_schedule_due({"hour": 18, "minute": 0}, last, NOW)
    assert is_schedule_due({"every_minutes": 15}, NOW - timedelta(minutes=16), NOW)
    assert not is_schedule_due({"every_minutes": 15}, NOW - timedelta(minutes=5), NOW)


def test_mass_delete_template_fires_on_mass_event():
    spec = template_graph("mass_delete")
    ran = []

    def handler(node, _ctx):
        ran.append(node["kind"])
        return {"ok": True, "message": "logged"}

    ok, _, trace = walk_graph(
        spec["graph"],
        ctx(events=[{"action": "delete", "is_mass": True, "name": "water_mains", "schema": "public"}]),
        handler,
    )
    assert ok
    assert ran == ["log"]
    assert trace[0]["ok"] is True


def test_quality_chain_skips_notify_when_checks_pass():
    spec = template_graph("quality_then_notify")
    kinds = []

    def handler(node, c):
        kinds.append(node["kind"])
        if node["kind"] == "run_quality":
            c.quality_failures = []
        return {"ok": True, "message": node["kind"]}

    walk_graph(spec["graph"], ctx(events=[{"action": "update", "is_mass": False, "name": "water_mains"}]), handler)
    assert kinds == ["run_quality"]


def test_quality_chain_notifies_when_checks_fail():
    spec = template_graph("quality_then_notify")
    kinds = []

    def handler(node, c):
        kinds.append(node["kind"])
        if node["kind"] == "run_quality":
            c.quality_failures = [{"name": "water_mains", "check_id": "validity"}]
        return {"ok": True, "message": node["kind"]}

    walk_graph(spec["graph"], ctx(events=[{"action": "update", "is_mass": False, "name": "water_mains"}]), handler)
    assert kinds == ["run_quality", "log", "email"]


def test_actions_never_include_a_write_to_user_data():
    assert "write" not in ACTION_KINDS
    assert "update" not in ACTION_KINDS
    assert "delete" not in ACTION_KINDS


def test_validate_rejects_mismatched_role_and_kind():
    with pytest.raises(ValueError, match="Unknown automation role"):
        validate_automation_graph(
            {
                "nodes": [
                    {"id": "t1", "role": "specific_user", "kind": "new_feature"},
                    {"id": "a1", "role": "action", "kind": "log"},
                ],
                "edges": [{"from": "t1", "to": "a1"}],
            }
        )


def test_validate_fills_role_from_kind():
    graph = validate_automation_graph(
        {
            "nodes": [
                {"id": "t1", "kind": "schedule", "config": {"hour": 18}},
                {"id": "a1", "kind": "ai_summarize", "config": {"notify": "email"}},
            ],
            "edges": [{"from": "t1", "to": "a1"}],
        }
    )
    assert graph["nodes"][0]["role"] == "trigger"
    assert graph["nodes"][1]["role"] == "action"


def branching_graph():
    return {"nodes": [
        {"id": "t", "kind": "any_change", "role": "trigger", "config": {}},
        {"id": "c", "kind": "user_eq", "role": "condition", "config": {"user": "alice"}},
        {"id": "yes", "kind": "log", "role": "action", "config": {}},
        {"id": "no", "kind": "log", "role": "action", "config": {}},
    ], "edges": [{"from": "t", "to": "c"}, {"from": "c", "to": "yes", "branch": "true"}, {"from": "c", "to": "no", "branch": "false"}]}


@pytest.mark.parametrize("user,expected", [("alice", "yes"), ("bob", "no")])
def test_condition_ports_choose_exactly_one_branch(user, expected):
    graph = validate_automation_graph(branching_graph())
    ran = []
    walk_graph(graph, ctx(events=[{"db_user": user}]), lambda node, _: ran.append(node["id"]) or {"ok": True})
    assert ran == [expected]


def test_failed_action_stops_downstream_execution():
    graph = branching_graph()
    graph["edges"] = [{"from": "t", "to": "yes"}, {"from": "yes", "to": "no"}]
    graph["nodes"] = [n for n in graph["nodes"] if n["id"] != "c"]
    ran = []
    ok, _, _ = walk_graph(validate_automation_graph(graph), ctx(events=[{}]), lambda node, _: ran.append(node["id"]) or {"ok": False})
    assert not ok
    assert ran == ["yes"]


@pytest.mark.parametrize("edge", [{"from": "yes", "to": "c"}, {"from": "t", "to": "missing"}, {"from": "c", "to": "t"}])
def test_invalid_connections_are_rejected(edge):
    graph = branching_graph()
    graph["edges"].append(edge)
    with pytest.raises(ValueError):
        validate_automation_graph(graph)


def test_disconnected_nodes_are_not_silently_connected():
    graph = branching_graph()
    graph["edges"] = []
    with pytest.raises(ValueError, match="Connect every node"):
        validate_automation_graph(graph)


def test_canvas_positions_survive_validation():
    graph = branching_graph()
    graph["nodes"][0]["position"] = {"x": 96, "y": 144}
    assert validate_automation_graph(graph)["nodes"][0]["position"] == {"x": 96, "y": 144}
