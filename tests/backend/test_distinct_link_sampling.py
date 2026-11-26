"""Synthetic regressions for the distinct budget, with real CSV readers."""
import pandas as pd
import pytest
from tarsier import flowchart
from tarsier.connectors import files
from tarsier.connectors.base import DataItem


def samples(tmp_path, left, right, column="code"):
    for name, values in (("left", left), ("right", right)):
        pd.DataFrame({column: values}).to_csv(tmp_path / (name + ".csv"), index=False)
    items = [DataItem("", name + ".csv", "tabular", path=name + ".csv") for name in ("left", "right")]
    return flowchart.sample_item_values(files, files.build_config({"folder": str(tmp_path)}), items)[0]


def guesses(sample):
    a, b = sample
    return flowchart.guess_between(*a, *b)


def test_repeated_rows_recover_complete_small_distinct_set(tmp_path):
    result = samples(tmp_path, [1] * 1500 + list(range(2, 11)), [2] * 1500 + [1] + list(range(3, 11)))
    assert [len(row[1]["code"]) for row in result] == [10, 10]
    assert len(guesses(result)) == 1


def test_exactly_one_thousand_distinct_uses_every_value(tmp_path):
    result = samples(tmp_path, [1] * 1500 + list(range(2, 1001)), list(range(1, 1001)))
    assert result[0][1]["code"] == set(range(1, 1001))
    assert len(guesses(result)) == 1


def test_more_than_one_thousand_uses_distinct_budget_and_requires_full_probe(tmp_path):
    result = samples(tmp_path, [1] * 1500 + list(range(2, 1002)), list(range(1, 1002)))
    assert result[0][1]["code"] == set(range(1, 1001))
    assert result[1][1]["code"] == set(range(1, 1001))
    assert all(not row[1].details["code"]["complete"] for row in result)
    # CSV currently has no bounded full-column probe. Do not treat two
    # truncated sets as either proof of a link or a verified negative.
    found = guesses(result)
    assert not found and found.could_not_verify == 1


@pytest.mark.parametrize("values", [list(range(4)), [0, 1, 2, 8, 9]])
def test_fewer_than_five_or_under_eighty_percent_do_not_link(tmp_path, values):
    assert not guesses(samples(tmp_path, list(range(5)), values))


@pytest.mark.parametrize("column", sorted(flowchart.EXCLUDED_GUESS_COLUMNS))
def test_excluded_names_remain_excluded(tmp_path, column):
    assert not guesses(samples(tmp_path, list(range(10)), list(range(10)), column))


def test_cross_connection_uses_same_distinct_reader(tmp_path, monkeypatch):
    from types import SimpleNamespace
    connections = []
    for label, first in (("a", 1), ("b", 2)):
        folder = tmp_path / label
        folder.mkdir()
        pd.DataFrame({"code": [first] * 1500 + list(range(10))}).to_csv(folder / "item.csv", index=False)
        connections.append(SimpleNamespace(id=label, name=label, type="files", config={"folder": str(folder)}))
    monkeypatch.setattr(flowchart.connection_storage, "list_connections", lambda: connections)
    monkeypatch.setattr(flowchart.connection_storage, "get_connection_password", lambda _: None)
    found, skipped = flowchart.discover_cross_connection_links()
    assert not skipped and len(found) == 1
    assert found[0]["source_connection_id"] == "a"
    assert found[0]["target_connection_id"] == "b"


@pytest.mark.parametrize("provider", ("postgis", "oracle", "sqlserver"))
def test_database_distinct_read_uses_existing_engine_and_quoted_catalog_column(provider, monkeypatch):
    import importlib
    from types import SimpleNamespace
    connector = importlib.import_module("tarsier.connectors." + provider)
    calls = []
    name = 'co"de' if provider != "sqlserver" else "co]de"
    class Result:
        def __init__(self, rows): self.rows = rows
        def fetchall(self): return self.rows
        def mappings(self): return self
        def all(self): return self.rows
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, statement, params=None):
            sql = str(statement); calls.append((sql, params))
            if "column_name" in sql and "FROM" in sql and "DISTINCT" not in sql:
                return Result([SimpleNamespace(column_name=name, data_type="text")])
            if "DISTINCT" in sql: return Result([{name: i} for i in range(1001)])
            return Result([])
    class Engine:
        disposed = False
        def connect(self): return Connection()
        def dispose(self): self.disposed = True
    engine = Engine()
    monkeypatch.setattr(connector, "_build_engine", lambda _: engine)
    result = connector.sample_rows(None, DataItem("s", "t", "tabular"), distinct_column=name)
    sql, params = next((s,p) for s,p in calls if "DISTINCT" in s)
    assert "IS NOT NULL" in sql and params["lim"] == 1001
    assert ('"co""de"' in sql) if provider != "sqlserver" else ("[co]]de]" in sql)
    assert result.is_sample and len(result.dataframe) == 1000 and engine.disposed


def test_geoserver_distinct_read_pages_repeats_with_existing_timeout(monkeypatch):
    from types import SimpleNamespace
    from tarsier.connectors import geoserver
    calls=[]
    def get(url, **kwargs):
        calls.append(kwargs)
        offset=kwargs["params"]["startIndex"]
        features=[{"properties":{"code":v}} for v in ([1,1,2] if offset==0 else [3,4,5])]
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{"features":features,"numberMatched":6})
    monkeypatch.setattr(geoserver.requests,"get",get)
    result=geoserver.sample_rows(SimpleNamespace(base_url="https://fixture.invalid",auth=None),DataItem("s","t","vector"),distinct_column="code")
    assert set(result.dataframe.code)=={1,2,3,4,5} and not result.is_sample
    assert [c["params"]["startIndex"] for c in calls]==[0,3]
    assert all(0<c["timeout"]<=geoserver._TIMEOUT for c in calls)


def test_arcgis_refuses_to_claim_completeness_when_service_truncates_distinct_values(monkeypatch):
    from types import SimpleNamespace
    from tarsier.connectors import arcgis
    from tarsier.connectors.base import ConnectorError
    def get(url, **kwargs):
        assert kwargs["params"]["returnDistinctValues"]=="true"
        assert kwargs["params"]["returnGeometry"]=="false"
        return SimpleNamespace(ok=True,json=lambda:{"features":[{"attributes":{"code":1}}],"exceededTransferLimit":True})
    monkeypatch.setattr(arcgis.requests,"get",get)
    with pytest.raises(ConnectorError,match="prevents a complete"):
        arcgis.sample_rows(SimpleNamespace(base_url="https://fixture.invalid",token=None),DataItem("","t","tabular",path="svc/FeatureServer/0"),distinct_column="code")
