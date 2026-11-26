"""Covers PRD §7.1 (Feature A — Overview): scanning a connection and
reading back the cached result. Uses the Files connector — real data,
no Docker needed — since the scan/cache logic itself is connector-agnostic.
"""

import pytest

from tarsier import overview
from tarsier.storage import connections as storage


@pytest.fixture
def files_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    saved = storage.create_connection(
        name="Sample files", type="files", config={"folder": "tests/datasets/files_sample"}
    )
    return saved.id


def test_scan_then_overview_reports_every_item(files_connection):
    overview.scan_connection(files_connection)
    summary = overview.get_overview(files_connection)

    assert summary.connection_name == "Sample files"
    assert summary.ever_scanned is True
    assert summary.total_layers == 6  # shp, 2 gpkg layers, tif, csv, sample_inventory.csv
    assert summary.total_size_bytes is not None and summary.total_size_bytes > 0
    assert summary.health_coverage_count == sum(row.health_score is not None for row in summary.layers)

    by_name = {row.name: row for row in summary.layers}
    assert by_name["water_mains"].row_count == 2
    assert by_name["hydrants"].row_count == 2
    assert by_name["inspection_log.csv"].row_count == 1
    assert by_name["sample_points"].kind == "vector"
    assert by_name["sample_elevation.tif"].kind == "raster"


def test_scan_populates_bbox_for_vector_and_raster(files_connection):
    overview.scan_connection(files_connection)
    cached_vector = [c for c in _cached(files_connection) if c.name == "water_mains"][0]
    cached_raster = [c for c in _cached(files_connection) if c.name == "sample_elevation.tif"][0]

    assert cached_vector.bbox is not None
    assert cached_raster.bbox is not None
    assert cached_raster.raster_width == 4
    assert cached_raster.raster_height == 4
    assert cached_raster.raster_band_count == 1


def test_projection_overview_groups_by_srid(files_connection):
    overview.scan_connection(files_connection)
    summary = overview.get_overview(files_connection)

    # Every fixture file uses EPSG:4326, so there's exactly one group,
    # and it must be flagged as the majority.
    assert len(summary.projections) == 1
    assert summary.projections[0].srid == 4326
    assert summary.projections[0].is_majority is True


def test_nothing_is_flagged_stale_or_heavy_for_a_fresh_small_dataset(files_connection):
    overview.scan_connection(files_connection)
    summary = overview.get_overview(files_connection)

    assert all(not row.is_stale for row in summary.layers)
    assert all(not row.is_heavy for row in summary.layers)  # all well under the 1MB floor


def test_a_genuinely_old_file_is_flagged_stale(tmp_path, monkeypatch):
    import os
    import time

    monkeypatch.setenv("TARSIER_HOME", str(tmp_path / "home"))
    folder = tmp_path / "stale_folder"
    folder.mkdir()
    old_file = folder / "old.csv"
    old_file.write_text("a,b\n1,2\n")
    ninety_five_days_ago = time.time() - 95 * 86400
    os.utime(old_file, (ninety_five_days_ago, ninety_five_days_ago))

    connection_id = storage.create_connection(name="Stale test", type="files", config={"folder": str(folder)}).id
    overview.scan_connection(connection_id)
    summary = overview.get_overview(connection_id)

    assert summary.layers[0].is_stale is True


def test_a_large_file_among_small_ones_is_flagged_heavy(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path / "home"))
    folder = tmp_path / "heavy_folder"
    folder.mkdir()
    (folder / "small.csv").write_text("a,b\n1,2\n")
    with open(folder / "big.csv", "w") as f:
        f.write("a,b\n")
        f.write("1,2\n" * 300_000)  # well over the 1MB heavy floor

    connection_id = storage.create_connection(name="Heavy test", type="files", config={"folder": str(folder)}).id
    overview.scan_connection(connection_id)
    summary = overview.get_overview(connection_id)

    by_name = {row.name: row for row in summary.layers}
    assert by_name["big.csv"].is_heavy is True
    assert by_name["small.csv"].is_heavy is False


def test_rescanning_drops_items_removed_from_the_source(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    folder = tmp_path / "shrinking_folder"
    folder.mkdir()
    (folder / "a.csv").write_text("x,y\n1,2\n")

    connection_id = storage.create_connection(name="Shrinking", type="files", config={"folder": str(folder)}).id
    overview.scan_connection(connection_id)
    assert {row.name for row in overview.get_overview(connection_id).layers} == {"a.csv"}

    (folder / "b.csv").write_text("x,y\n3,4\n")
    overview.scan_connection(connection_id)
    assert {row.name for row in overview.get_overview(connection_id).layers} == {"a.csv", "b.csv"}

    (folder / "a.csv").unlink()
    overview.scan_connection(connection_id)
    assert {row.name for row in overview.get_overview(connection_id).layers} == {"b.csv"}


def _cached(connection_id):
    from tarsier.storage import item_cache

    return item_cache.list_items(connection_id)


def test_stale_badge_uses_latest_change_event_when_last_modified_is_missing(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    now = datetime.now(timezone.utc)
    old_event = now - timedelta(days=91)
    _mock_overview_item(monkeypatch, last_scanned_at=now, event=old_event)

    summary = overview.get_overview("postgis-test")

    assert summary.layers[0].is_stale is True


def test_stale_badge_uses_recent_change_event_when_last_modified_is_missing(monkeypatch):
    from datetime import datetime, timedelta, timezone

    old_scan = datetime.now(timezone.utc) - timedelta(days=120)
    recent_event = datetime.now(timezone.utc) - timedelta(days=2)
    _mock_overview_item(monkeypatch, last_scanned_at=old_scan, event=recent_event)

    summary = overview.get_overview("postgis-test")

    assert summary.layers[0].is_stale is False


def test_stale_badge_falls_back_to_last_scan_when_no_event_or_last_modified(monkeypatch):
    from datetime import datetime, timedelta, timezone

    old_scan = datetime.now(timezone.utc) - timedelta(days=91)
    _mock_overview_item(monkeypatch, last_scanned_at=old_scan, event=None)

    summary = overview.get_overview("postgis-test")

    assert summary.layers[0].is_stale is True


def _mock_overview_item(monkeypatch, *, last_scanned_at, event):
    from types import SimpleNamespace

    item = SimpleNamespace(
        schema="public", name="roads", kind="vector", geometry_type="LINESTRING",
        srid=4326, row_count=1, row_count_is_estimate=False, row_count_is_capped=False, size_bytes=100,
        has_index=False, last_modified=None,
    )
    saved = SimpleNamespace(id="postgis-test", name="PostGIS test", type="postgis", last_scanned_at=last_scanned_at)
    monkeypatch.setattr(overview.connection_storage, "get_connection", lambda _cid: saved)
    monkeypatch.setattr(overview.item_cache, "list_items", lambda _cid: [item])
    monkeypatch.setattr(overview.quality_cache, "get_all_checks", lambda _cid: {})
    monkeypatch.setattr(overview.change_log, "latest_event_times", lambda _cid: {("public", "roads"): event} if event else {})
    monkeypatch.setattr(overview.settings, "_get_value", lambda _key: None)
    monkeypatch.setattr(overview.flowchart_storage, "count_links", lambda _cid: 0)
