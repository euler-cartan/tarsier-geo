"""Full statistics must stay bounded while sample results remain available."""

from types import SimpleNamespace

import pytest

from tarsier.connectors.base import ConnectorError, DataItem
from tarsier.stats import scan as stats_scan
from tarsier.stats.engine import TableStats
from tarsier.storage import stats_cache


def test_full_statistics_guard_uses_cached_row_count(monkeypatch):
    calls = []
    connector = SimpleNamespace(
        build_config=lambda config, password: config,
        list_items=lambda config: [DataItem(schema="public", name="wide", kind="tabular")],
        sample_rows=lambda config, item, limit: calls.append(limit) or object(),
    )
    monkeypatch.setattr(stats_scan.connection_storage, "get_connection", lambda cid: SimpleNamespace(type="postgis", config={}))
    monkeypatch.setattr(stats_scan.connection_storage, "get_connection_password", lambda cid: None)
    monkeypatch.setattr(stats_scan, "get_connector", lambda kind: connector)
    monkeypatch.setattr(stats_scan.item_cache, "get_item", lambda *args: SimpleNamespace(row_count=20_001))
    with pytest.raises(ConnectorError, match="Full statistics are not available"):
        stats_scan.load_item_sample("c1", "public", "wide", full=True)
    assert calls == []
    stats_scan.load_item_sample("c1", "public", "wide")
    assert calls == [1000]
    monkeypatch.setattr(stats_scan.item_cache, "get_item", lambda *args: SimpleNamespace(row_count=20_000))
    stats_scan.load_item_sample("c1", "public", "wide", full=True)
    assert calls[-1] == stats_scan.FULL_RUN_LIMIT


def test_oversize_result_is_rejected_before_cache_write(monkeypatch):
    monkeypatch.setattr(stats_cache, "MAX_STATS_CACHE_BYTES", 10)
    monkeypatch.setattr(stats_cache, "get_session", lambda: pytest.fail("oversize payload reached storage"))
    with pytest.raises(ConnectorError, match="exceeds 64 MiB"):
        stats_cache.save_stats("c1", "public", "wide", TableStats(1, True, [], 0))


@pytest.mark.parametrize("row_count,message", [
    (20_001, "skipped: too large for full check; sample used"),
    (None, "skipped: row count unknown; sample used"),
])
def test_overview_uses_sample_and_records_skipped_table(monkeypatch, row_count, message):
    from tarsier import checks, overview
    from tarsier.quality import engine
    from tarsier.storage import item_cache

    monkeypatch.setattr(overview, "scan_connection", lambda cid: None)
    monkeypatch.setattr(overview, "_unreadable_items", lambda cid: set())
    monkeypatch.setattr(item_cache, "list_items", lambda cid: [SimpleNamespace(schema="public", name="wide", kind="tabular", row_count=row_count)])
    monkeypatch.setattr(engine, "applicable_checks", lambda kind: ())
    calls = []
    monkeypatch.setattr(stats_scan, "scan_item_stats", lambda *args, **kwargs: calls.append(kwargs["full"]))
    monkeypatch.setattr(checks, "_save", lambda cid, job: None)
    monkeypatch.setattr(checks, "record_outcome", lambda state: None)
    job = {"state": "running", "errors": [], "skipped": [], "completed": 0, "total": 0}
    checks._run("c1", job)
    assert calls == [False]
    assert job["state"] == "completed"
    assert job["skipped"] == [{"schema": "public", "name": "wide", "check": "statistics", "message": message}]
