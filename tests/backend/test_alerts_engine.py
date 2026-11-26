from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from tarsier.alerts.engine import AlertContext, evaluate_rule, quality_score

NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


def ctx(**kwargs):
    base = AlertContext(
        items=[{"schema": "public", "name": "water_mains", "row_count": 100, "size_bytes": 1000, "last_modified": NOW.isoformat()}],
        previous_items=[{"schema": "public", "name": "water_mains", "row_count": 100, "size_bytes": 1000}],
        events=[],
        quality_scores={"public.water_mains": 90},
        previous_quality={"public.water_mains": 90},
        now=NOW,
        sample_values=None,
    )
    for key, value in kwargs.items():
        setattr(base, key, value)
    return base


def test_mass_change_uses_existing_mass_flag():
    matches = evaluate_rule(
        "mass_change",
        {},
        ctx(events=[{"id": "1", "action": "delete", "schema": "public", "name": "water_mains", "is_mass": True}]),
    )
    assert matches and "Mass delete" in matches[0].message


def test_row_count_drop_at_25_percent():
    matches = evaluate_rule(
        "row_count_drop",
        {},
        ctx(items=[{"schema": "public", "name": "water_mains", "row_count": 70, "size_bytes": 1000}]),
    )
    assert matches
    quiet = evaluate_rule(
        "row_count_drop",
        {},
        ctx(items=[{"schema": "public", "name": "water_mains", "row_count": 90, "size_bytes": 1000}]),
    )
    assert quiet == []


def test_schema_change_event():
    matches = evaluate_rule(
        "schema_change",
        {},
        ctx(events=[{"id": "s", "action": "schema", "schema": "public", "name": "water_mains"}]),
    )
    assert matches


def test_freshness_uses_90_day_window():
    stale = (NOW - timedelta(days=94)).isoformat()
    matches = evaluate_rule(
        "freshness",
        {},
        ctx(items=[{"schema": "public", "name": "water_mains", "row_count": 1, "last_modified": stale}]),
    )
    assert matches


def test_quality_score_drop_10_points():
    assert quality_score({"a": SimpleNamespace(status="good"), "b": SimpleNamespace(status="danger")}) == 50
    matches = evaluate_rule(
        "quality_score_drop",
        {},
        ctx(quality_scores={"public.water_mains": 70}, previous_quality={"public.water_mains": 90}),
    )
    assert matches


def test_specific_user_is_case_insensitive():
    matches = evaluate_rule(
        "specific_user",
        {"user": "Alice"},
        ctx(events=[{"id": "1", "action": "update", "schema": "public", "name": "water_mains", "db_user": "alice"}]),
    )
    assert matches
    other = evaluate_rule(
        "specific_user",
        {"user": "Alice"},
        ctx(events=[{"id": "1", "action": "update", "schema": "public", "name": "water_mains", "db_user": "bob"}]),
    )
    assert other == []


def test_new_and_dropped_layer():
    added = evaluate_rule(
        "layer_presence",
        {"presence": "added"},
        ctx(items=[{"schema": "public", "name": "hydrants", "row_count": 1}]),
    )
    assert any("New layer" in m.message for m in added)
    dropped = evaluate_rule(
        "layer_presence",
        {"presence": "dropped"},
        ctx(items=[]),
    )
    assert any("Dropped layer" in m.message for m in dropped)


def test_size_spike_50_percent():
    matches = evaluate_rule(
        "size_spike",
        {},
        ctx(items=[{"schema": "public", "name": "water_mains", "row_count": 100, "size_bytes": 1600}]),
    )
    assert matches


def test_banned_value_on_sample():
    matches = evaluate_rule(
        "banned_value",
        {"field": "diameter", "operator": "lt", "value": "0"},
        ctx(sample_values={"diameter": [10, -5, 3]}),
    )
    assert matches and matches[0].details["count"] == 1


def test_freshness_event_fallback_matches_overview_stale_rule():
    from tarsier.overview import _is_stale

    old_event = NOW - timedelta(days=91)
    item = {"schema": "public", "name": "water_mains", "last_modified": None, "scanned_at": NOW}
    event = {"schema": "public", "name": "water_mains", "occurred_at": old_event}
    matches = evaluate_rule("freshness", {}, ctx(items=[item], events=[event]))
    cutoff = NOW - timedelta(days=90)

    assert matches
    assert _is_stale(None, old_event, NOW, cutoff) is True


def test_freshness_recent_event_overrides_old_scan_like_overview():
    from tarsier.overview import _is_stale

    recent_event = NOW - timedelta(days=2)
    old_scan = NOW - timedelta(days=120)
    item = {"schema": "public", "name": "water_mains", "last_modified": None, "scanned_at": old_scan}
    event = {"schema": "public", "name": "water_mains", "occurred_at": recent_event}
    cutoff = NOW - timedelta(days=90)

    assert evaluate_rule("freshness", {}, ctx(items=[item], events=[event])) == []
    assert _is_stale(None, recent_event, old_scan, cutoff) is False


def test_freshness_without_event_falls_back_to_last_scan_like_overview():
    from tarsier.overview import _is_stale

    old_scan = NOW - timedelta(days=91)
    item = {"schema": "public", "name": "water_mains", "last_modified": None, "scanned_at": old_scan}
    cutoff = NOW - timedelta(days=90)

    assert evaluate_rule("freshness", {}, ctx(items=[item], events=[]))
    assert _is_stale(None, None, old_scan, cutoff) is True


def test_freshness_requires_strictly_older_than_ninety_days_like_overview():
    from tarsier.overview import _is_stale

    at_cutoff = NOW - timedelta(days=90)
    item = {"schema": "public", "name": "water_mains", "last_modified": None, "scanned_at": NOW}
    event = {"schema": "public", "name": "water_mains", "occurred_at": at_cutoff}
    cutoff = NOW - timedelta(days=90)

    assert evaluate_rule("freshness", {}, ctx(items=[item], events=[event])) == []
    assert _is_stale(None, at_cutoff, NOW, cutoff) is False



def test_freshness_last_modified_takes_precedence_over_event_and_scan():
    from tarsier.overview import _is_stale

    old_stamp = NOW - timedelta(days=91)
    recent_stamp = NOW - timedelta(days=2)
    cutoff = NOW - timedelta(days=90)
    old_item = {"schema": "public", "name": "water_mains", "last_modified": old_stamp.isoformat(), "scanned_at": recent_stamp}
    recent_item = {"schema": "public", "name": "water_mains", "last_modified": recent_stamp.isoformat(), "scanned_at": old_stamp}
    recent_event = {"schema": "public", "name": "water_mains", "occurred_at": recent_stamp}
    old_event = {"schema": "public", "name": "water_mains", "occurred_at": old_stamp}

    assert evaluate_rule("freshness", {}, ctx(items=[old_item], events=[recent_event]))
    assert _is_stale(old_stamp.isoformat(), recent_stamp, recent_stamp, cutoff) is True
    assert evaluate_rule("freshness", {}, ctx(items=[recent_item], events=[old_event])) == []
    assert _is_stale(recent_stamp.isoformat(), old_stamp, old_stamp, cutoff) is False