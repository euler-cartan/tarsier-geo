from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from tarsier import flowchart
from tarsier.connectors import postgis
from tarsier.connectors.base import DataItem


def columns(values, *, complete, estimate=None, probe=None):
    result = flowchart.ColumnValues({"key": set(values)}, connector=SimpleNamespace(probe_column_values=probe) if probe else SimpleNamespace(), config=None, item=DataItem("s", "t", "tabular"))
    result.details["key"] = {"complete": complete, "estimate": estimate}
    return result


def test_complete_sets_do_not_probe():
    left = columns(range(1000), complete=True)
    right = columns(range(200, 1200), complete=True)
    assert flowchart._option_a(left, "key", right, "key") is True
    right["key"].remove(200)
    assert flowchart._option_a(left, "key", right, "key") is False


def test_pg_stats_direction_and_full_lookup():
    seen = []
    def probe(config, item, column, values, datatype):
        seen.append(values)
        return True
    left = columns(range(1000), complete=False, estimate=9000, probe=probe)
    right = columns(range(1000, 2000), complete=False, estimate=2000, probe=probe)
    assert flowchart._option_a(left, "key", right, "key") is True
    assert seen == [right["key"]]


def test_bounded_estimate_and_unsupported_are_unknown():
    assert flowchart._option_a(columns(range(1000), complete=False), "key", columns(range(1000), complete=False), "key") is None


def test_timeout_is_not_a_negative_or_an_edge():
    left = columns(range(1000), complete=False, probe=lambda *_: None)
    right = columns(range(1000), complete=False, probe=lambda *_: None)
    result = flowchart.guess_between(DataItem("s", "a", "tabular"), left, True, DataItem("s", "b", "tabular"), right, True)
    assert result == [] and result.could_not_verify == 1
    official = {("s", "b", "key", "s", "a", "key")}
    result = flowchart.guess_between(DataItem("s", "a", "tabular"), left, True, DataItem("s", "b", "tabular"), right, True, official)
    assert result.could_not_verify == 0


def test_postgis_lookup_enforces_timeout_and_parameterization(monkeypatch):
    seen = {}
    monkeypatch.setattr(postgis, "column_guess_metadata", lambda *_: {"key": {"type": "text"}})
    class Cancelled(Exception):
        sqlstate = "57014"
    class Engine:
        def connect(self): return self
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def dispose(self): seen["disposed"] = True
        def execute(self, sql, params):
            seen.update(sql=str(sql), params=params)
            raise OperationalError("lookup", {}, Cancelled())
    def build(config, **kwargs):
        seen.update(kwargs)
        return Engine()
    monkeypatch.setattr(postgis, "_build_engine", build)
    assert postgis.probe_column_values(None, DataItem("s", "t", "tabular"), "key", {"a'", "b", "c", "d", "e"}, "text") is None
    assert seen["statement_timeout_ms"] == 5000 and seen["disposed"]
    assert "a'" not in seen["sql"] and "a'" in seen["params"]["values"]


def test_unknown_count_persists_and_is_in_scan_response(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    from tarsier.api.flowchart import _scan_outcome
    from tarsier.storage.flowchart import get_scan_outcome
    links = flowchart.DiscoveryLinks()
    links.could_not_verify = 2
    result = _scan_outcome(links, "test")
    assert result["could_not_verify"] == 2
    assert "could not verify" in result["message"].lower()
    assert "no link" not in result["message"]
    assert get_scan_outcome("test") == result


@pytest.mark.parametrize("right_estimate", [None, 2971])
def test_missing_stats_tie_uses_estimated_live_rows_not_pair_order(right_estimate):
    seen = []
    def probe(config, item, column, values, datatype):
        seen.append(values)
        return True
    left = columns(range(1000), complete=False, probe=probe)
    right = columns(range(1000, 2000), complete=False, estimate=right_estimate, probe=probe)
    left.details["key"]["row_estimate"] = 70000
    right.details["key"]["row_estimate"] = 10000
    assert flowchart._option_a(left, "key", right, "key") is True
    assert seen == [right["key"]]


@pytest.mark.parametrize("source_type,target_type,values", [
    ("text", "numeric", {"1.5", "2.5", "3.5", "4.5", "5.5"}),
    ("numeric", "text", {1.5, 2.5, 3.5, 4.5, 5.5}),
])
def test_probe_does_not_extend_text_coercion_to_fractions(monkeypatch, source_type, target_type, values):
    monkeypatch.setattr(postgis, "column_guess_metadata", lambda *_: {"key": {"type": target_type}})
    monkeypatch.setattr(postgis, "_build_engine", lambda *_a, **_kw: pytest.fail("Must not issue a lookup for unsupported coercion"))
    assert postgis.probe_column_values(None, DataItem("s", "t", "tabular"), "key", values, source_type) is False
