"""Early quality applicability must avoid source data work."""
import pytest
from tarsier.quality import scan
from tarsier.storage import connections, quality_cache


@pytest.mark.parametrize("full", [False, True])
def test_no_custom_rules_uses_only_local_state(tmp_path, monkeypatch, full):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    saved = connections.create_connection("offline", "files", {"folder": "not-present"})
    def unexpected(*args, **kwargs):
        raise AssertionError("Source access is forbidden for a ruleless check")
    monkeypatch.setattr(scan, "_load_context", unexpected)
    monkeypatch.setattr(scan, "get_connector", unexpected)
    monkeypatch.setattr(connections, "get_connection_password", unexpected)
    calls = []
    monkeypatch.setattr("tarsier.alerts.evaluate.evaluate_connection", lambda *a: calls.append("alert"))
    monkeypatch.setattr("tarsier.automation.evaluate.evaluate_connection", lambda *a: calls.append("automation"))
    result = scan.scan_check(saved.id, "", "item", "custom_rules", full=full)
    assert result.status == "not_applicable"
    assert result.message == "No custom rules defined for this layer."
    assert quality_cache.get_checks(saved.id, "", "item")["custom_rules"].status == "not_applicable"
    assert calls == []


@pytest.mark.parametrize("check,kind", [
    ("overlaps", "LineString"), ("slivers", "MultiLineString"), ("gaps", "Point"),
    ("dangles", "Polygon"), ("dangles", "MultiPolygon"),
    ("overlaps", "MultiPoint"), ("gaps", "GeometryCollection"),
    ("slivers", "LINESTRING ZM"), ("dangles", "3D Polygon"),
])
def test_catalog_incompatible_geometry_never_reads_rows(tmp_path, monkeypatch, check, kind):
    from types import SimpleNamespace
    from tarsier.connectors.base import DataItem
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    saved = connections.create_connection("synthetic", "files", {"folder": "unused"})
    item = DataItem("", "item", "vector", geometry_type=kind)
    def unexpected(*args, **kwargs):
        raise AssertionError("Row reads are forbidden for an incompatible catalog type")
    connector = SimpleNamespace(sample_rows=unexpected, sample_geometries=unexpected)
    monkeypatch.setattr(scan, "_load_context", lambda *a: (saved, connector, None, [item], item))
    calls = []
    monkeypatch.setattr("tarsier.alerts.evaluate.evaluate_connection", lambda *a: calls.append("alert"))
    monkeypatch.setattr("tarsier.automation.evaluate.evaluate_connection", lambda *a: calls.append("automation"))
    result = scan.scan_check(saved.id, "", "item", check, full=True)
    assert result.status == "not_applicable"
    assert quality_cache.get_checks(saved.id, "", "item")[check].status == "not_applicable"
    assert calls == []


@pytest.mark.parametrize("kind", [None, "Unknown", "GEOMETRY", "Mixed", "SDO_GEOMETRY"])
@pytest.mark.parametrize("check", ["overlaps", "slivers", "gaps", "dangles"])
def test_unknown_catalog_type_never_suppresses_a_check(kind, check, monkeypatch):
    from types import SimpleNamespace
    from tarsier.connectors.base import DataItem
    item = DataItem("", "item", "vector", geometry_type=kind)
    def reached(*args, **kwargs):
        raise RuntimeError("row path reached")
    connector = SimpleNamespace(sample_geometries=reached)
    monkeypatch.setattr(scan, "_load_context", lambda *a: (SimpleNamespace(type="files"), connector, None, [item], item))
    with pytest.raises(RuntimeError, match="row path reached"):
        scan.scan_check("synthetic", "", "item", check)


@pytest.mark.parametrize("check,kind", [
    ("overlaps", "Polygon"), ("slivers", "MULTIPOLYGON Z"), ("gaps", "PolygonM"),
    ("dangles", "MultiLineString"), ("validity", "Point"), ("boundary", "Point"),
    ("custom_rules", "LineString"), ("projection", "Polygon"),
])
def test_supported_geometry_and_type_independent_checks_are_retained(check, kind):
    assert scan.geometry_check_applicability(check, kind) is None
