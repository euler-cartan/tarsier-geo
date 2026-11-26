"""Official relationships own their exact endpoint pair in either direction."""
import pandas as pd
import pytest
from tarsier import flowchart
from tarsier.connectors.base import DataItem, SampleResult
from tarsier.storage import connections


@pytest.mark.parametrize("reverse", [False, True])
def test_transit_official_link_suppresses_both_guess_directions(reverse):
    routes = DataItem("transit", "routes", "tabular")
    trips = DataItem("transit", "trips", "tabular")
    official = {("transit", "trips", "route_id", "transit", "routes", "route_id")}
    left, right = (trips, routes) if reverse else (routes, trips)
    values = {"route_id": set(range(10))}
    assert flowchart.guess_between(left, values, True, right, values, True, official) == []


def test_other_columns_and_schemas_remain_eligible():
    official = {("transit", "trips", "route_id", "transit", "routes", "route_id")}
    values = {"new_route_id": set(range(10))}
    routes = DataItem("transit", "routes", "tabular")
    trips = DataItem("transit", "trips", "tabular")
    assert len(flowchart.guess_between(routes, values, True, trips, values, True, official)) == 1
    assert len(flowchart.guess_between(DataItem("other", "routes", "tabular"),
        {"route_id": set(range(10))}, True, trips, {"route_id": set(range(10))}, True, official)) == 1


def test_discovery_preserves_declared_direction_and_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    saved = connections.create_connection("official", "files", {"folder": "unused"})
    official = {"source_schema": "transit", "source_name": "trips", "source_column": "route_id",
        "target_schema": "transit", "target_name": "routes", "target_column": "route_id", "constraint_name": "trips_route_fk"}
    class Connector:
        def build_config(self, config, password): return config
        def list_items(self, config): return [DataItem("transit", "routes", "tabular"), DataItem("transit", "trips", "tabular")]
        def list_foreign_keys(self, config): return [official]
        def sample_rows(self, config, item, limit): return SampleResult(pd.DataFrame({"route_id": range(10)}), False)
    monkeypatch.setattr(flowchart, "get_connector", lambda _: Connector())
    _, links = flowchart.discover_links(saved.id)
    assert links == [{**official, "kind": "official", "status": "confirmed", "sample_based": False}]
