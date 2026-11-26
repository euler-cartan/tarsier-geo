from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from tarsier.api.app import create_app
from tarsier.storage import connections
from tarsier import checks


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path / "home"))
    return TestClient(create_app())


def test_job_reports_progress_errors_and_avoids_duplicate_runs(client, monkeypatch):
    connection = connections.create_connection("Test", "files", {})
    submitted = []
    monkeypatch.setattr(checks._pool, "submit", lambda *args: submitted.append(args))
    monkeypatch.setattr("tarsier.overview.scan_connection", lambda _: None)
    monkeypatch.setattr("tarsier.storage.item_cache.list_items", lambda _: [SimpleNamespace(schema="public",name="example",kind="tabular",row_count=1)])
    monkeypatch.setattr("tarsier.stats.scan.scan_item_stats", lambda *args,**kwargs: None)
    calls=[]
    def run(*args, **kwargs):
        calls.append(args[-1])
        if args[-1] == "completeness": raise RuntimeError("private driver text")
    monkeypatch.setattr("tarsier.quality.scan.scan_check", run)
    url=f"/api/connections/{connection.id}/checks"
    try:
        assert client.post(url).json()["state"] == "running"
        assert client.post(url).status_code == 202
        assert len(submitted) == 1
        checks._run(connection.id,submitted[0][2])
        result=client.get(url).json()
        assert result["state"] == "completed_with_errors"
        assert result["completed"] == result["total"]
        assert calls and result["errors"][0]["check"] == "completeness"
        assert "private driver text" not in str(result)
        from tarsier.storage.run_timings import read_runs
        assert read_runs(connection_id=connection.id)[0]["outcome"] == "completed_with_errors"
    finally:
        checks._active.discard(connection.id)


def test_interrupted_job_is_visible(client):
    connection=connections.create_connection("Test","files",{})
    checks._save(connection.id,{"state":"running","message":"Working","completed":1,"total":5,"errors":[]})
    result=client.get(f"/api/connections/{connection.id}/checks").json()
    assert result["state"] == "interrupted"
    assert "restarted" in result["message"]


def test_map_returns_wgs84_geometry_without_attributes(client, monkeypatch):
    import geopandas as gpd
    from shapely.geometry import Point
    frame=gpd.GeoDataFrame({"private_value":["not for the preview"]},geometry=[Point(111319.49,111325.14)],crs=3857)
    connector=SimpleNamespace(sample_geometries=lambda *a,**kw: SimpleNamespace(geodataframe=frame,is_sample=False))
    connection=connections.create_connection("Map","files",{})
    monkeypatch.setattr("tarsier.quality.scan._load_context",lambda *a:(None,connector,None,None,SimpleNamespace(kind="vector")))
    response=client.post(f"/api/connections/{connection.id}/item/map/scan",params={"schema":"public","name":"points"})
    assert response.status_code == 200
    body=response.json()
    assert body["feature_count"] == 1
    assert body["bbox"][0] == pytest.approx(1,abs=.001)
    assert body["bbox"][1] == pytest.approx(1,abs=.001)
    assert "private_value" not in response.text
    assert client.get(f"/api/connections/{connection.id}/item/map",params={"schema":"public","name":"points"}).json() == body
