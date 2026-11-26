from types import SimpleNamespace

import pytest

from tarsier.connectors import postgis
from tarsier.connectors.base import ConnectorError, DataItem

ITEM = DataItem("s", "table", "tabular")


@pytest.mark.parametrize("primary,fallback,method,basis", [
    (3000, 9000, "complete", "reltuples"),
    (1, None, "complete", "reltuples"),
    (3001, None, "multi_seed_system", "reltuples"),
    (1000000, None, "multi_seed_system", "reltuples"),
    (-1, 2000, "complete", "n_live_tup"),
    (0, 9000, "multi_seed_system", "n_live_tup"),
    (None, 9000, "multi_seed_system", "n_live_tup"),
    (float("nan"), 9000, "multi_seed_system", "n_live_tup"),
    (float("inf"), 9000, "multi_seed_system", "n_live_tup"),
    (True, 9000, "multi_seed_system", "n_live_tup"),
    ("100", 9000, "multi_seed_system", "n_live_tup"),
    (-1, 0, "bounded_tid", "no usable row estimate"),
    (None, None, "bounded_tid", "no usable row estimate"),
    (0, float("nan"), "bounded_tid", "no usable row estimate"),
    (False, -1, "bounded_tid", "no usable row estimate"),
])
def test_estimate_guards_and_small_table_rule(primary, fallback, method, basis):
    plan = postgis.sampling_plan(primary, fallback)
    assert plan["method"] == method and plan["basis"] == basis
    if method == "multi_seed_system":
        assert plan["percent"] == min(50, 100*1500/primary if basis == "reltuples" else 100*1500/fallback)
        assert 0 < plan["percent"] <= 50
    if method == "bounded_tid":
        assert plan["percent"] is None and plan["page_budget"] == 40
        assert plan["address_budget"] == 10000 and plan["row_budget"] == 2000


class Result:
    def __init__(self, rows=None, plan=None): self.rows, self.plan = rows, plan
    def mappings(self): return self
    def all(self): return self.rows
    def scalar_one(self): return [{"Plan": self.plan}]


class Connection:
    def __init__(self, rows, plan=None): self.rows, self.plan, self.calls = rows, plan, []
    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params))
        return Result(self.rows, self.plan)


def meta(monkeypatch, estimate, **extra):
    value = dict(reltuples=estimate, n_live_tup=None, bytes=1000*8192, block_size=8192, relkind="r", amname="heap")
    value.update(extra)
    monkeypatch.setattr(postgis, "_row_estimate", lambda *_: value)


def test_small_table_is_complete_with_all_rows_and_no_system_cap(monkeypatch):
    meta(monkeypatch, 2500)
    conn = Connection([{"value": i} for i in range(2500)])
    rows, sampled, details = postgis._guarded_rows(conn, ITEM, ['"value"'])
    assert len(rows) == 2500 and sampled is False and details["complete"] is True
    assert details["method"] == "complete" and details["seed_vector"] == []
    assert "TABLESAMPLE" not in conn.calls[0][0]


def test_stale_small_estimate_never_labels_truncated_results_complete(monkeypatch):
    meta(monkeypatch, 2)
    rows, sampled, details = postgis._guarded_rows(Connection([{"value": i} for i in range(4001)]), ITEM, ['"value"'])
    assert sampled and len(rows) == 4000 and details["budget_limited"]
    assert details["complete"] is False


def test_ten_seed_draws_deduplicate_identity_not_equal_values(monkeypatch):
    meta(monkeypatch, 100000)
    conn = Connection([
        {"value": "same", "__tarsier_sample_oid": 1, "__tarsier_sample_tid": "(1,1)", "__tarsier_sample_draw": 0},
        {"value": "same", "__tarsier_sample_oid": 1, "__tarsier_sample_tid": "(1,1)", "__tarsier_sample_draw": 1},
        {"value": "same", "__tarsier_sample_oid": 1, "__tarsier_sample_tid": "(1,2)", "__tarsier_sample_draw": 1},
    ])
    rows, sampled, details = postgis._guarded_rows(conn, ITEM, ['"value"'])
    assert sampled and len(rows) == 2 and rows[0] == rows[1]
    sql, params = conn.calls[0]
    assert sql.count("TABLESAMPLE SYSTEM") == 10 and sql.count("LIMIT 401") == 10
    assert [params[f"seed{i}"] for i in range(10)] == list(range(719,729))
    assert params["percent"] == .15
    assert details["row_count"] == 2 and not details["budget_limited"]
    assert details["seed_vector"] == list(range(719,729))


def test_missing_estimate_checks_tid_plan_and_exact_bounds(monkeypatch):
    meta(monkeypatch, -1)
    conn = Connection([{"value": 1}], {"Node Type": "Limit", "Plans": [{"Node Type": "Tid Scan"}]})
    rows, sampled, details = postgis._guarded_rows(conn, ITEM, ['"value"'])
    assert sampled and len(rows) == 1
    assert details["pages_addressed"] == 40 and details["tuple_addresses"] == 10000
    query, params = conn.calls[-1]
    assert "LIMIT 2000" in query and len(params["addresses"]) == 10000
    assert len({a.split(',')[0] for a in params["addresses"]}) == 40


@pytest.mark.parametrize("plan", [
    {"Node Type": "Seq Scan"},
    {"Node Type": "Limit", "Plans": [{"Node Type": "Seq Scan"}]},
    {"Node Type": "Hash Join", "Plans": [{"Node Type": "Tid Scan"}]},
    {"Node Type": "Sort", "Plans": [{"Node Type": "Tid Scan"}]},
])
def test_unsafe_plan_never_executes_source_query_or_falls_back(monkeypatch, plan):
    meta(monkeypatch, -1)
    conn = Connection([], plan)
    with pytest.raises(ConnectorError, match="no sequential-scan fallback"):
        postgis._guarded_rows(conn, ITEM, ['"value"'])
    assert len(conn.calls) == 2 and conn.calls[-1][0].startswith("EXPLAIN")


def test_nonheap_sampling_fails_without_row_read(monkeypatch):
    meta(monkeypatch, 10000, relkind="p")
    conn = Connection([])
    with pytest.raises(ConnectorError, match="heap table"):
        postgis._guarded_rows(conn, ITEM, ['"value"'])
    assert conn.calls == []


def test_sampling_details_survive_statistics_and_quality_cache_roundtrip(tmp_path, monkeypatch):
    import pandas as pd
    from tarsier.stats.engine import compute_table_stats
    from dataclasses import replace
    from tarsier.quality.engine import CheckResult
    from tarsier.storage import stats_cache, quality_cache
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    details = {"method":"multi_seed_system", "seed_vector":list(range(719,729)), "row_count":2}
    stats = replace(compute_table_stats(pd.DataFrame({"x":[1,2]}), True), sample_details=details)
    stats_cache.save_stats("test", "s", "t", stats)
    assert stats_cache.get_stats("test", "s", "t").sample_details == details
    result = CheckResult("validity", "good", is_sample=True, sample_details=details)
    quality_cache.save_check("test", "s", "t", result)
    assert quality_cache.get_checks("test", "s", "t")["validity"].sample_details == details


@pytest.mark.parametrize("estimate,full,allowed", [(1000000,False,True),(1000001,False,False),(-1,False,False),(1000001,True,True),(660386,False,True)])
def test_full_id_size_gate_and_five_second_timeout(monkeypatch, estimate, full, allowed):
    meta(monkeypatch, estimate)
    calls = []
    class Query:
        def fetchall(self): return [SimpleNamespace(column_name="id")]
    class Engine:
        def connect(self): return self
        def __enter__(self): return self
        def __exit__(self,*_): pass
        def dispose(self): pass
        def execute(self, statement, params=None):
            calls.append(str(statement))
            if "information_schema" in str(statement):return Query()
            return SimpleNamespace(fetchall=lambda: [(1,), (2,)])
    def build(config, **kwargs):
        assert kwargs["statement_timeout_ms"] == 5000
        return Engine()
    monkeypatch.setattr(postgis,"_build_engine",build)
    if allowed:
        result=postgis.sample_id_values(None,ITEM,full=full)
        assert result.values.tolist()==[1,2]
        assert any('SELECT "id"' in sql for sql in calls)
    else:
        with pytest.raises(ConnectorError,match="explicit full check"):
            postgis.sample_id_values(None,ITEM,full=full)
        assert not any('SELECT "id"' in sql for sql in calls)
