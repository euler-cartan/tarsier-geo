from datetime import datetime, timedelta, timezone

from tarsier.health import calculate_health, freshness_score, quality_score
from tarsier.quality.engine import CheckResult


def test_health_uses_weighted_components():
    checks = {
        "validity": CheckResult(check_id="validity", status="good"),
        "projection": CheckResult(check_id="projection", status="danger"),
        "completeness": CheckResult(check_id="completeness", status="good", completeness_score=80),
    }
    now = datetime(2026, 10, 11, tzinfo=timezone.utc)
    last_modified = (now - timedelta(days=60)).isoformat()

    result = calculate_health(last_modified, None, checks, now)

    assert result == {
        "score": 66,
        "components": {"quality": 67, "freshness": 50, "completeness": 80},
    }


def test_health_renormalizes_available_components_and_uses_event_fallback():
    now = datetime(2026, 10, 11, tzinfo=timezone.utc)
    checks = {"validity": CheckResult(check_id="validity", status="good")}
    event_at = now - timedelta(days=30)

    result = calculate_health(None, event_at, checks, now)

    assert result == {
        "score": 100,
        "components": {"quality": 100, "freshness": 100, "completeness": None},
    }


def test_health_returns_no_score_when_every_component_is_unavailable():
    assert calculate_health(None, None, {}, datetime.now(timezone.utc)) == {
        "score": None,
        "components": {"quality": None, "freshness": None, "completeness": None},
    }


def test_quality_ignores_never_run_and_not_applicable_checks():
    checks = {
        "validity": CheckResult(check_id="validity", status="good"),
        "projection": CheckResult(check_id="projection", status="danger"),
        "boundary": CheckResult(check_id="boundary", status="not_applicable"),
        "gaps": CheckResult(check_id="gaps", status="never_run"),
    }
    assert quality_score(checks) == 50


def test_freshness_is_unavailable_without_source_timestamp():
    now = datetime.now(timezone.utc)
    assert freshness_score(None, None, now) is None
