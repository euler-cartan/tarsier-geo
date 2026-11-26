"""Covers TRS-004 (PRD §5): connect to files in a folder, list contents.

Fixtures are real files under tests/datasets/files_sample/ (a shapefile, a
two-layer GeoPackage, a GeoTIFF, and a CSV) — no Docker needed, since this
connector never touches a database (PRD §5: files have no change tracking).
"""

import pytest

from tarsier.connectors.base import ConnectorError
from tarsier.connectors.files import FilesConnectionConfig, list_items
from tarsier.connectors.files import test_connection as check_connection

FIXTURE_DIR = "tests/datasets/files_sample"


def test_connection_succeeds_for_existing_folder():
    check_connection(FilesConnectionConfig(folder=FIXTURE_DIR))


def test_connection_fails_for_missing_folder():
    with pytest.raises(ConnectorError):
        check_connection(FilesConnectionConfig(folder="tests/datasets/does_not_exist"))


def test_connection_fails_for_a_file_not_a_folder():
    with pytest.raises(ConnectorError):
        check_connection(FilesConnectionConfig(folder=f"{FIXTURE_DIR}/inspection_log.csv"))


@pytest.fixture
def items():
    return list_items(FilesConnectionConfig(folder=FIXTURE_DIR))


def test_shapefile_is_listed_as_vector(items):
    by_name = {item.name: item for item in items}
    layer = by_name["sample_points"]
    assert layer.kind == "vector"
    assert layer.geometry_type == "Point"
    assert layer.srid == 4326
    assert layer.path == "sample_points.shp"


def test_geopackage_layers_are_both_listed(items):
    by_name = {item.name: item for item in items}
    assert by_name["water_mains"].kind == "vector"
    assert by_name["water_mains"].geometry_type == "LineString"
    assert by_name["hydrants"].kind == "vector"
    assert by_name["hydrants"].geometry_type == "Point"
    # Both layers live in the same physical file.
    assert by_name["water_mains"].path == "sample.gpkg"
    assert by_name["hydrants"].path == "sample.gpkg"


def test_geotiff_is_listed_as_raster(items):
    by_name = {item.name: item for item in items}
    raster = by_name["sample_elevation.tif"]
    assert raster.kind == "raster"
    assert raster.srid == 4326


def test_csv_is_listed_as_tabular(items):
    by_name = {item.name: item for item in items}
    table = by_name["inspection_log.csv"]
    assert table.kind == "tabular"
    assert table.geometry_type is None
