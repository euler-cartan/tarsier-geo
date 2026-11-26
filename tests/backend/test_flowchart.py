import pandas as pd
from fastapi.testclient import TestClient

from tarsier.api.app import create_app
from tarsier.connectors.base import DataItem, SampleResult
from tarsier.storage import connections


def test_discovery_uses_exact_normalized_names_and_eighty_percent_overlap(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    connection = connections.create_connection("test", "files", {"folder": "unused"})
    left = DataItem("", "left.csv", "tabular")
    right = DataItem("", "right.csv", "tabular")
    near_name = DataItem("", "near.csv", "tabular")

    class FakeConnector:
        def build_config(self, config, password):
            return config

        def list_items(self, config):
            return [left, right, near_name]

        def sample_rows(self, config, item, limit):
            rows = {
                "left.csv": pd.DataFrame({"parcel_id": [1, 2, 3, 4, 5]}),
                "right.csv": pd.DataFrame({"Parcel ID": [1, 2, 3, 4, 5, 6]}),
                "near.csv": pd.DataFrame({"parcelid": [1, 2, 3, 4, 5]}),
            }
            return SampleResult(rows[item.name], item.name == "left.csv")

        def list_foreign_keys(self, config):
            return [{
                "source_schema": "", "source_name": "near.csv", "source_column": "parcelid",
                "target_schema": "", "target_name": "left.csv", "target_column": "parcel_id",
            }]

    monkeypatch.setattr("tarsier.flowchart.get_connector", lambda _type: FakeConnector())
    nodes, links = __import__("tarsier.flowchart", fromlist=["discover_links"]).discover_links(connection.id)

    guesses = [link for link in links if link["kind"] == "guessed"]
    official = [link for link in links if link["kind"] == "official"]
    assert len(nodes) == 3
    assert [(link["source_name"], link["target_name"]) for link in guesses] == [("left.csv", "right.csv")]
    assert guesses[0]["sample_based"] is True
    assert len(official) == 1 and official[0]["status"] == "confirmed"


def test_discovery_ignores_excluded_columns_and_requires_five_values_each_side(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    connection = connections.create_connection("test", "files", {"folder": "unused"})
    left = DataItem("", "left.csv", "tabular")
    right = DataItem("", "right.csv", "tabular")

    class FakeConnector:
        def build_config(self, config, password):
            return config

        def list_items(self, config):
            return [left, right]

        def sample_rows(self, config, item, limit):
            rows = {
                "left.csv": pd.DataFrame({
                    "objectid": [1, 2, 3, 4, 5],
                    "oid": [1, 2, 3, 4, 5],
                    "fid": [1, 2, 3, 4, 5],
                    "gid": [1, 2, 3, 4, 5],
                    "id": [1, 2, 3, 4, 5],
                    "pagenumber": [1, 2, 3, 4, 5],
                    "parcel_id": [10, 20, 30, 40, 40],
                    "huc_code": ["a", "b", "c", "d", "e"],
                }),
                "right.csv": pd.DataFrame({
                    "OBJECTID": [1, 2, 3, 4, 5],
                    "OID": [1, 2, 3, 4, 5],
                    "FID": [1, 2, 3, 4, 5],
                    "GID": [1, 2, 3, 4, 5],
                    "ID": [1, 2, 3, 4, 5],
                    "PageNumber": [1, 2, 3, 4, 5],
                    "Parcel ID": [10, 20, 30, 40, 40],
                    "HUC_CODE": ["a", "b", "c", "d", "e"],
                }),
            }
            return SampleResult(rows[item.name], False)

    monkeypatch.setattr("tarsier.flowchart.get_connector", lambda _type: FakeConnector())
    nodes, links = __import__("tarsier.flowchart", fromlist=["discover_links"]).discover_links(connection.id)

    guesses = [link for link in links if link["kind"] == "guessed"]
    assert len(nodes) == 2
    assert [(link["source_column"], link["target_column"]) for link in guesses] == [
        ("huc_code", "HUC_CODE"),
    ]


def test_discovery_strips_approved_column_prefixes_without_changing_value_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    connection = connections.create_connection("test", "files", {"folder": "unused"})
    items = [
        DataItem("", "flow.csv", "tabular"),
        DataItem("", "flowline.csv", "tabular"),
        DataItem("", "crossreference.csv", "tabular"),
        DataItem("", "maintenance.csv", "tabular"),
    ]
    frames = {
        "flow.csv": pd.DataFrame({"from_permanent_identifier": ["a", "b", "c", "d", "e"]}),
        "flowline.csv": pd.DataFrame({"permanent_identifier": ["a", "b", "c", "d", "e"]}),
        "crossreference.csv": pd.DataFrame({"newreachcode": [1, 2, 3, 4, 5]}),
        "maintenance.csv": pd.DataFrame({"reachcode": [1, 2, 3, 4, 5]}),
    }

    class FakeConnector:
        def build_config(self, config, password):
            return config

        def list_items(self, config):
            return items

        def sample_rows(self, config, item, limit):
            return SampleResult(frames[item.name], False)

    monkeypatch.setattr("tarsier.flowchart.get_connector", lambda _type: FakeConnector())
    _, links = __import__("tarsier.flowchart", fromlist=["discover_links"]).discover_links(connection.id)

    guesses = [link for link in links if link["kind"] == "guessed"]
    assert {
        (link["source_name"], link["source_column"], link["target_name"], link["target_column"])
        for link in guesses
    } == {
        ("flow.csv", "from_permanent_identifier", "flowline.csv", "permanent_identifier"),
        ("crossreference.csv", "newreachcode", "maintenance.csv", "reachcode"),
    }


def test_flowchart_api_scan_confirm_reject_and_manual_add(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    connection = connections.create_connection("test", "files", {"folder": "unused"})
    nodes = [
        {"schema": "", "name": "a.csv", "kind": "tabular", "columns": ["id"]},
        {"schema": "", "name": "b.csv", "kind": "tabular", "columns": ["a_id"]},
    ]
    links = [{
        "source_schema": "", "source_name": "a.csv", "source_column": "id",
        "target_schema": "", "target_name": "b.csv", "target_column": "a_id",
        "kind": "guessed", "status": "guessed", "sample_based": True,
    }, {
        "source_schema": "", "source_name": "b.csv", "source_column": "a_id",
        "target_schema": "", "target_name": "a.csv", "target_column": "id",
        "kind": "guessed", "status": "guessed", "sample_based": False,
    }]
    monkeypatch.setattr("tarsier.api.flowchart.discover_links", lambda _connection_id: (nodes, links))
    client = TestClient(create_app())

    graph = client.post(f"/api/connections/{connection.id}/flowchart/scan").json()
    guess_id = graph["links"][0]["id"]
    rejected_id = graph["links"][1]["id"]
    assert graph["nodes"] == nodes
    assert client.post(f"/api/connections/{connection.id}/flowchart/links/{guess_id}/confirm").json()["status"] == "confirmed"
    assert client.post(f"/api/connections/{connection.id}/flowchart/links/{rejected_id}/reject").json()["status"] == "rejected"
    added = client.post(f"/api/connections/{connection.id}/flowchart/links", json={
        "source_schema": "", "source_name": "a.csv", "source_column": "id",
        "target_schema": "", "target_name": "b.csv", "target_column": "a_id",
    })
    assert added.status_code == 201
    assert added.json()["kind"] == "user"

    graph = client.get(f"/api/connections/{connection.id}/flowchart").json()
    assert {link["kind"] for link in graph["links"]} == {"guessed", "user"}
    assert all(link["status"] != "rejected" for link in graph["links"])
    assert client.get(f"/api/connections/{connection.id}/overview").json()["relationship_count"] == 2
