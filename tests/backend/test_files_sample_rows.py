"""Covers the sample-data path behind PRD §7.2's statistics engine for
the Files connector — real fixtures, no Docker needed.
"""

import pytest

from tarsier.connectors.base import ConnectorError
from tarsier.connectors.files import FilesConnectionConfig, list_items, sample_rows
from tarsier.stats.engine import compute_table_stats

FIXTURE_DIR = "tests/datasets/files_sample"


@pytest.fixture
def items():
    return list_items(FilesConnectionConfig(folder=FIXTURE_DIR))


def test_sample_rows_for_shapefile_excludes_geometry_keeps_centroid(items):
    layer = next(i for i in items if i.name == "sample_points")
    result = sample_rows(FilesConnectionConfig(folder=FIXTURE_DIR), layer)

    assert "geometry" not in result.dataframe.columns
    assert result.geometry_columns == ("__cx", "__cy")
    assert len(result.dataframe) == 2
    assert "name" in result.dataframe.columns


def test_sample_rows_for_geopackage_layer(items):
    layer = next(i for i in items if i.name == "water_mains")
    result = sample_rows(FilesConnectionConfig(folder=FIXTURE_DIR), layer)

    assert len(result.dataframe) == 2
    assert "id" in result.dataframe.columns


def test_sample_rows_for_csv(items):
    table = next(i for i in items if i.name == "inspection_log.csv")
    result = sample_rows(FilesConnectionConfig(folder=FIXTURE_DIR), table)

    assert result.geometry_columns is None
    assert "inspector" in result.dataframe.columns
    assert len(result.dataframe) == 1


def test_sample_rows_rejects_raster(items):
    raster = next(i for i in items if i.kind == "raster")
    with pytest.raises(ConnectorError):
        sample_rows(FilesConnectionConfig(folder=FIXTURE_DIR), raster)


def test_sample_rows_feeds_the_stats_engine_end_to_end(items):
    layer = next(i for i in items if i.name == "water_mains")
    result = sample_rows(FilesConnectionConfig(folder=FIXTURE_DIR), layer)
    stats = compute_table_stats(
        result.dataframe, result.is_sample,
        geometry_columns=result.geometry_columns, null_geometry_column=result.null_geometry_column,
    )
    id_col = next(c for c in stats.columns if c.name == "id")
    assert id_col.unique_count == 2
