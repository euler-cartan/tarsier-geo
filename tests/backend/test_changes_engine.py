from datetime import datetime, timedelta, timezone

from tarsier.changes.engine import (
    ChangeEventView,
    changed_fields,
    diff_fingerprints,
    in_date_range,
    is_mass_batch,
    report_summary,
    volume_by_day,
)


def _event(day_offset, action="update", txid="1", is_mass=False, user="alice"):
    when = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=day_offset)
    return ChangeEventView(
        id=str(day_offset) + action,
        occurred_at=when,
        db_user=user,
        action=action,
        schema="public",
        name="water_mains",
        feature_id="1",
        before={"material": "PVC"},
        after={"material": "HDPE"} if action == "update" else None,
        txid=txid,
        source="trigger",
        is_mass=is_mass,
        changed_fields=["material"] if action == "update" else [],
    )


def test_changed_fields_only_lists_differences():
    assert changed_fields({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4}) == ["b", "c"]


def test_mass_batch_flags_large_transaction():
    assert is_mass_batch(50, 1000) is True
    assert is_mass_batch(12, 40) is True  # 25% of 40 is 10, floor 10
    assert is_mass_batch(5, 40) is False
    assert is_mass_batch(9, 10000) is False


def test_volume_spike_is_three_times_seven_day_mean():
    events = [_event(i) for i in range(1, 8)]  # 7 quiet days, 1 each
    events.extend(_event(0) for _ in range(10))  # today: 10 (> 3×1)
    series = volume_by_day(events, days=10)
    today = series[-1]
    assert today["count"] == 10
    assert today["is_spike"] is True
    assert series[-2]["is_spike"] is False


def test_compare_two_dates_inclusive():
    events = [_event(0), _event(2), _event(10)]
    start = events[1].occurred_at - timedelta(hours=1)
    end = events[0].occurred_at + timedelta(hours=1)
    matched = in_date_range(events, start, end)
    assert len(matched) == 2


def test_polling_fingerprint_diff():
    previous = {"1": "aaa", "2": "bbb"}
    current = {"1": "aaa", "3": "ccc"}
    diffs = {(d["action"], d["feature_id"]) for d in diff_fingerprints(previous, current)}
    assert diffs == {("insert", "3"), ("delete", "2")}


def test_report_summary_counts_mass_and_unknown_who():
    events = [
        _event(0, "delete", txid="tx", is_mass=True),
        _event(0, "schema", txid="tx2", user=None),
    ]
    summary = report_summary(events)
    assert summary["total"] == 2
    assert summary["mass_batches"] == 1
    assert summary["schema_changes"] == 1
    assert summary["unknown_who"] == 1
