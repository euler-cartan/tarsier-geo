"""Covers TRS-117 (knowledge graph engine, PRD 14.1) and TRS-118
(cross-connection relationship guessing, PRD 14.10 / 7.8).

The graph tests need the Kuzu package (pinned 0.11.3; no wheel for Python 3.14),
so they skip where it can't be imported.
"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from tarsier.api.app import create_app
from tarsier.graph import engine

needs_kuzu = pytest.mark.skipif(not engine.is_available(), reason="kuzu is not installed for this Python version")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path / "home"))
    return TestClient(create_app())


def write(folder, name, frame):
    folder.mkdir(parents=True, exist_ok=True)
    frame.to_csv(folder / name, index=False)
    return folder


def connect(client, folder, name):
    return client.post(
        "/api/connections", json={"name": name, "type": "files", "config": {"folder": str(folder)}}
    ).json()["id"]


def ids(n=10, start=1):
    return list(range(start, start + n))


@pytest.fixture
def three_sources(client, tmp_path):
    """parcels(A) -parcel_id- taxes(B) -account_no- accounts(C); nothing links A to C directly."""
    a = write(tmp_path / "a", "parcels.csv", pd.DataFrame({"parcel_id": ids(), "owner": list("abcdefghij")}))
    b = write(tmp_path / "b", "taxes.csv", pd.DataFrame({"parcel_id": ids(), "account_no": ids(10, 100)}))
    c = write(tmp_path / "c", "accounts.csv", pd.DataFrame({"account_no": ids(10, 100), "holder": list("klmnopqrst")}))
    return {"a": connect(client, a, "Source A"), "b": connect(client, b, "Source B"), "c": connect(client, c, "Source C")}


def cross_scan(client):
    response = client.post("/api/flowchart/cross/scan")
    assert response.status_code == 200
    return response.json()


def cross_links(client, connection_id):
    return [l for l in client.get(f"/api/connections/{connection_id}/flowchart").json()["links"]
            if l["source_connection_id"] != l["target_connection_id"]]


# --- TRS-118: cross-connection guessing, same method ----------------------------


def test_matching_columns_across_connections_become_guessed_links(client, three_sources):
    result = cross_scan(client)
    assert result["guesses"] == 2 and result["skipped_connections"] == []
    assert result["could_not_verify"] == 0
    assert "0 candidates" in result["message"]
    links = cross_links(client, three_sources["a"])
    assert len(links) == 1
    link = links[0]
    assert (link["source_name"], link["source_column"]) == ("parcels.csv", "parcel_id")
    assert (link["target_name"], link["target_column"]) == ("taxes.csv", "parcel_id")
    assert link["kind"] == "guessed" and link["status"] == "guessed"
    assert link["source_connection_id"] == three_sources["a"] and link["target_connection_id"] == three_sources["b"]
    # the middle connection sees both of its cross links
    assert len(cross_links(client, three_sources["b"])) == 2


def test_the_other_connection_is_described_as_an_external_node(client, three_sources):
    cross_scan(client)
    payload = client.get(f"/api/connections/{three_sources['a']}/flowchart").json()
    external = payload["external_nodes"]
    assert [(n["connection_name"], n["name"]) for n in external] == [("Source B", "taxes.csv")]
    assert all(n["name"] != "taxes.csv" for n in payload["nodes"])


@pytest.mark.parametrize(
    "right,reason",
    [
        (pd.DataFrame({"parcel_id": ids(4)}), "fewer than 5 distinct values on one side"),
        (pd.DataFrame({"parcel_id": ids(10, 100)}), "no value overlap"),
        (pd.DataFrame({"parcel_id": ids(2) + ids(8, 100)}), "only 20% of values shared (needs 80%)"),
        (pd.DataFrame({"id": ids(10), "oid": ids(10)}), "different column names"),
    ],
)
def test_rule_thresholds_are_the_locked_tad_ones(client, tmp_path, right, reason):
    connect(client, write(tmp_path / "l", "left.csv", pd.DataFrame({"parcel_id": ids(10), "id": ids(10), "oid": ids(10)})), "L")
    connect(client, write(tmp_path / "r", "right.csv", right), "R")
    assert cross_scan(client)["guesses"] == 0, reason


def test_eighty_percent_overlap_exactly_qualifies(client, tmp_path):
    connect(client, write(tmp_path / "l", "left.csv", pd.DataFrame({"parcel_id": ids(10)})), "L")
    connect(client, write(tmp_path / "r", "right.csv", pd.DataFrame({"parcel_id": ids(8) + ids(2, 500)})), "R")
    assert cross_scan(client)["guesses"] == 1  # 8 of the 10 shared = 80% of the smaller set


def test_excluded_internal_columns_never_guess_across_connections(client, tmp_path):
    for column in ("id", "objectid", "fid", "gid", "oid", "pagenumber"):
        frame = pd.DataFrame({column: ids(10)})
        connect(client, write(tmp_path / f"l_{column}", "l.csv", frame), f"L-{column}")
        connect(client, write(tmp_path / f"r_{column}", "r.csv", frame), f"R-{column}")
    assert cross_scan(client)["guesses"] == 0


def test_approved_prefixes_are_stripped_like_within_one_connection(client, tmp_path):
    connect(client, write(tmp_path / "l", "left.csv", pd.DataFrame({"from_parcel_id": ids(10)})), "L")
    connect(client, write(tmp_path / "r", "right.csv", pd.DataFrame({"Parcel ID": ids(10)})), "R")
    assert cross_scan(client)["guesses"] == 1


def test_location_alone_never_creates_a_cross_connection_guess(client, tmp_path):
    """Two layers on exactly the same coordinates, with no shared column: no guess (no geometry matching)."""
    import geopandas as gpd
    from shapely.geometry import Point

    for name in ("p", "q"):
        folder = tmp_path / name
        folder.mkdir()
        gpd.GeoDataFrame({f"{name}_label": list("abcdefghij")}, geometry=[Point(i, i) for i in range(10)], crs=4326).to_file(
            folder / "pts.gpkg", layer="pts", driver="GPKG"
        )
        connect(client, folder, name.upper())
    assert cross_scan(client)["guesses"] == 0


def test_confirm_and_reject_work_from_either_side_and_survive_a_rescan(client, three_sources):
    cross_scan(client)
    [ab] = cross_links(client, three_sources["a"])
    # the target side (B) can confirm the very same link
    assert client.post(f"/api/connections/{three_sources['b']}/flowchart/links/{ab['id']}/confirm").status_code == 200
    [again] = cross_links(client, three_sources["a"])
    assert again["status"] == "confirmed"

    bc = next(l for l in cross_links(client, three_sources["c"]) if l["source_name"] == "taxes.csv")
    assert client.post(f"/api/connections/{three_sources['c']}/flowchart/links/{bc['id']}/reject").status_code == 200

    cross_scan(client)  # a rescan must respect both decisions
    assert [l["status"] for l in cross_links(client, three_sources["a"])] == ["confirmed"]
    assert cross_links(client, three_sources["c"]) == []


def test_unreadable_connection_is_skipped_not_fatal(client, three_sources, tmp_path):
    import shutil

    doomed = write(tmp_path / "doomed", "x.csv", pd.DataFrame({"a": ids()}))
    connect(client, doomed, "Broken")
    shutil.rmtree(doomed)  # the source disappears after it was connected
    result = cross_scan(client)
    assert result["skipped_connections"] == ["Broken"] and result["guesses"] == 2


def test_single_connection_scan_leaves_cross_guesses_alone(client, three_sources):
    cross_scan(client)
    assert client.post(f"/api/connections/{three_sources['a']}/flowchart/scan").status_code == 200
    assert len(cross_links(client, three_sources["a"])) == 1
    assert len(cross_links(client, three_sources["b"])) == 2


def test_deleting_a_connection_removes_its_cross_links_from_the_others(client, three_sources):
    cross_scan(client)
    from tarsier.storage import connections as connection_storage

    connection_storage.delete_connection(three_sources["c"])
    assert len(cross_links(client, three_sources["b"])) == 1


# --- TRS-117: knowledge graph ----------------------------------------------------


def neighbors(client, connection_id, name, **params):
    return client.get("/api/graph/neighbors", params={"connection_id": connection_id, "name": name, **params}).json()


@needs_kuzu
def test_graph_projects_sources_items_and_relations(client, three_sources):
    for connection_id in three_sources.values():
        client.post(f"/api/connections/{connection_id}/scan")
    cross_scan(client)
    status = client.post("/api/graph/rebuild").json()
    assert (status["sources"], status["items"], status["relations"]) == (3, 3, 2)
    assert client.get("/api/graph/status").json()["built"] is True


@needs_kuzu
def test_neighbors_reach_items_through_other_items(client, three_sources):
    cross_scan(client)
    one_hop = neighbors(client, three_sources["a"], "parcels.csv", hops=1)["items"]
    assert [i["name"] for i in one_hop] == ["taxes.csv"] and one_hop[0]["distance"] == 1
    assert one_hop[0]["other_connection"] is True

    two_hops = neighbors(client, three_sources["a"], "parcels.csv", hops=2)["items"]
    assert [(i["name"], i["distance"]) for i in two_hops] == [("taxes.csv", 1), ("accounts.csv", 2)]
    assert two_hops[1]["connection_id"] == three_sources["c"]


@needs_kuzu
def test_shortest_path_names_each_link_in_the_chain(client, three_sources):
    cross_scan(client)
    response = client.get("/api/graph/path", params={
        "from_connection_id": three_sources["a"], "from_name": "parcels.csv",
        "to_connection_id": three_sources["c"], "to_name": "accounts.csv",
    }).json()
    assert response["connected"] is True
    path = response["path"]
    assert [i["name"] for i in path["items"]] == ["parcels.csv", "taxes.csv", "accounts.csv"]
    assert path["length"] == 2
    assert {(l["source_column"], l["target_column"]) for l in path["links"]} == {("parcel_id", "parcel_id"), ("account_no", "account_no")}
    assert all(l["cross_connection"] for l in path["links"])


@needs_kuzu
def test_confirmed_only_ignores_unconfirmed_guesses(client, three_sources):
    cross_scan(client)
    [ab] = cross_links(client, three_sources["a"])
    assert neighbors(client, three_sources["a"], "parcels.csv", confirmed_only="true")["items"] == []
    client.post(f"/api/connections/{three_sources['a']}/flowchart/links/{ab['id']}/confirm")  # also refreshes the graph
    only = neighbors(client, three_sources["a"], "parcels.csv", hops=3, confirmed_only="true")["items"]
    assert [i["name"] for i in only] == ["taxes.csv"]  # B-C is still a guess


@needs_kuzu
def test_unconnected_items_have_no_path_or_neighbours(client, three_sources, tmp_path):
    lonely = connect(client, write(tmp_path / "d", "lonely.csv", pd.DataFrame({"unrelated": list("abcdefghij")})), "D")
    cross_scan(client)
    assert neighbors(client, lonely, "lonely.csv")["items"] == []
    response = client.get("/api/graph/path", params={
        "from_connection_id": lonely, "from_name": "lonely.csv",
        "to_connection_id": three_sources["a"], "to_name": "parcels.csv",
    }).json()
    assert response == {"connected": False, "path": None}


@needs_kuzu
def test_overview_groups_connected_items_across_connections(client, three_sources, tmp_path):
    lonely = connect(client, write(tmp_path / "d", "lonely.csv", pd.DataFrame({"unrelated": list("abcdefghij")})), "D")
    client.post(f"/api/connections/{lonely}/scan")  # items join the graph once their connection has been scanned
    cross_scan(client)
    overview = client.get("/api/graph/overview").json()
    assert overview["sources"] == 4 and overview["relations"] == 2 and overview["cross_connection_relations"] == 2
    [group] = overview["groups"]
    assert group["size"] == 3 and group["spans_connections"] is True
    assert {i["name"] for i in group["items"]} == {"parcels.csv", "taxes.csv", "accounts.csv"}
    assert overview["unconnected_items"] == 1
    assert overview["most_connected"][0]["name"] == "taxes.csv" and overview["most_connected"][0]["links"] == 2


@needs_kuzu
def test_rejecting_a_guess_updates_the_graph(client, three_sources):
    cross_scan(client)
    client.get("/api/graph/overview")  # builds it
    bc = next(l for l in cross_links(client, three_sources["c"]) if l["source_name"] == "taxes.csv")
    client.post(f"/api/connections/{three_sources['c']}/flowchart/links/{bc['id']}/reject")
    assert client.get("/api/graph/overview").json()["relations"] == 1


@needs_kuzu
def test_the_graph_is_rebuilt_from_sqlite_so_it_can_be_thrown_away(client, three_sources):
    import shutil

    cross_scan(client)
    client.post("/api/graph/rebuild")
    for path in engine.graph_path().parent.glob("graph.kuzu*"):
        shutil.rmtree(path) if path.is_dir() else path.unlink()
    assert client.get("/api/graph/status").json()["built"] is False
    assert client.get("/api/graph/overview").json()["relations"] == 2  # rebuilt on demand, nothing lost


@needs_kuzu
def test_within_one_connection_links_appear_in_the_graph_too(client, tmp_path):
    folder = tmp_path / "one"
    write(folder, "parcels.csv", pd.DataFrame({"parcel_id": ids()}))
    write(folder, "taxes.csv", pd.DataFrame({"parcel_id": ids()}))
    connection_id = connect(client, folder, "One")
    client.post(f"/api/connections/{connection_id}/flowchart/scan")
    overview = client.get("/api/graph/overview").json()
    assert overview["relations"] == 1 and overview["cross_connection_relations"] == 0


def test_graph_reports_unavailable_instead_of_breaking_the_app(client, three_sources, monkeypatch):
    monkeypatch.setattr(engine, "kuzu", None)
    status = client.get("/api/graph/status").json()
    assert status["available"] is False and "Kuzu" in status["message"]
    assert client.get("/api/graph/overview").status_code == 503
    # everything else carries on, including cross-connection guessing and confirm/reject
    assert cross_scan(client)["guesses"] == 2
    assert client.get(f"/api/connections/{three_sources['a']}/flowchart").status_code == 200


# --- Relationship Graph screen support (FSD 12.1) ---------------------------------


def neighborhood(client, connection_id, name, **params):
    return client.get("/api/graph/neighborhood", params={"connection_id": connection_id, "name": name, **params}).json()


@needs_kuzu
def test_neighborhood_returns_nodes_edges_and_degrees(client, three_sources):
    cross_scan(client)
    one = neighborhood(client, three_sources["a"], "parcels.csv", hops=1)
    assert one["found"] is True
    assert [(n["name"], n["distance"]) for n in one["nodes"]] == [("parcels.csv", 0), ("taxes.csv", 1)]
    assert [(e["source_column"], e["status"]) for e in one["edges"]] == [("parcel_id", "guessed")]
    assert {n["name"]: n["degree"] for n in one["nodes"]} == {"parcels.csv": 1, "taxes.csv": 2}  # degree counts the whole graph
    assert one["nodes"][1]["connection_name"] == "Source B"

    two = neighborhood(client, three_sources["a"], "parcels.csv", hops=2)
    assert [n["name"] for n in two["nodes"]] == ["parcels.csv", "taxes.csv", "accounts.csv"]
    assert len(two["edges"]) == 2


@needs_kuzu
def test_unknown_start_item_is_reported_not_an_error(client, three_sources):
    cross_scan(client)
    assert neighborhood(client, three_sources["a"], "nope.csv") == {"found": False, "nodes": [], "edges": []}


@needs_kuzu
def test_confirmed_only_changes_the_results_everywhere_not_just_the_drawing(client, three_sources):
    cross_scan(client)
    [ab] = cross_links(client, three_sources["a"])
    client.post(f"/api/connections/{three_sources['a']}/flowchart/links/{ab['id']}/confirm")

    everything = neighborhood(client, three_sources["a"], "parcels.csv", hops=3)
    confirmed = neighborhood(client, three_sources["a"], "parcels.csv", hops=3, confirmed_only="true")
    assert len(everything["nodes"]) == 3 and len(everything["edges"]) == 2
    assert [n["name"] for n in confirmed["nodes"]] == ["parcels.csv", "taxes.csv"]
    assert len(confirmed["edges"]) == 1
    assert {n["name"]: n["degree"] for n in confirmed["nodes"]} == {"parcels.csv": 1, "taxes.csv": 1}

    full = client.get("/api/graph/overview").json()
    strict = client.get("/api/graph/overview", params={"confirmed_only": "true"}).json()
    assert full["relations"] == 2 and strict["relations"] == 1
    assert [g["size"] for g in full["groups"]] == [3] and [g["size"] for g in strict["groups"]] == [2]
    assert strict["unconnected_items"] == 1  # accounts.csv drops out of the group


@needs_kuzu
def test_overview_lists_every_item_for_the_picker(client, three_sources):
    for connection_id in three_sources.values():
        client.post(f"/api/connections/{connection_id}/scan")
    cross_scan(client)
    items = client.get("/api/graph/overview").json()["all_items"]
    assert [(i["connection_name"], i["name"]) for i in items] == [
        ("Source A", "parcels.csv"), ("Source B", "taxes.csv"), ("Source C", "accounts.csv"),
    ]
