"""Planted geometries against TAD Phase 4 quality formulas (TRS-029–038)."""

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Polygon

from tarsier.quality.engine import (
    check_boundary,
    check_completeness,
    check_custom_rules,
    check_dangles,
    check_gaps,
    check_overlaps,
    check_projection,
    check_slivers,
    check_validity,
    majority_srid,
)


def test_dangle_spatial_lookup_preserves_connections_across_cell_boundaries():
    frame = gpd.GeoDataFrame(geometry=[LineString([(0,0),(1,0)]),LineString([(1,0),(2,0)]),LineString([(2,0),(3,0)])],crs=3857)
    result = check_dangles(frame)
    assert result.fail_count == 2


def test_validity_flags_self_crossing_polygon():
    gdf = gpd.GeoDataFrame(
        {"id": [1, 2], "geometry": [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), Polygon([(0, 0), (1, 1), (0, 1), (1, 0)])]}
    )
    result = check_validity(gdf)
    assert result.fail_count == 1
    assert result.failing_rows[0]["id"] == 2


def test_overlaps_need_positive_area_not_just_touching():
    touching = gpd.GeoDataFrame(
        {
            "id": [1, 2],
            "geometry": [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), Polygon([(1, 0), (2, 0), (2, 1), (1, 1)])],
        }
    )
    overlapping = gpd.GeoDataFrame(
        {
            "id": [1, 2],
            "geometry": [Polygon([(0, 0), (2, 0), (2, 2), (0, 2)]), Polygon([(1, 1), (3, 1), (3, 3), (1, 3)])],
        }
    )
    assert check_overlaps(touching).fail_count == 0
    assert check_overlaps(overlapping).fail_count == 2


def test_sliver_requires_thin_and_small():
    gdf = gpd.GeoDataFrame(
        {
            "id": [1, 2, 3],
            "geometry": [
                Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]),
                Polygon([(20, 0), (30, 0), (30, 10), (20, 10)]),
                Polygon([(0, 20), (10, 20), (10, 20.01), (0, 20.01)]),
            ],
        }
    )
    result = check_slivers(gdf)
    assert result.fail_count == 1
    assert result.failing_rows[0]["id"] == 3


def test_small_compact_polygon_is_not_a_sliver():
    gdf = gpd.GeoDataFrame(
        {
            "id": [1, 2],
            "geometry": [
                Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]),
                Polygon([(0, 0), (0.2, 0), (0.2, 0.2), (0, 0.2)]),
            ],
        }
    )
    assert check_slivers(gdf).fail_count == 0


def test_gaps_flag_small_interior_hole():
    donut = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)], [[(4, 4), (4.2, 4), (4.2, 4.2), (4, 4.2)]])
    other = Polygon([(20, 0), (30, 0), (30, 10), (20, 10)])
    result = check_gaps(gpd.GeoDataFrame({"geometry": [donut, other]}))
    assert result.fail_count == 1
    assert result.failing_rows[0]["area"] > 0


def test_dangles_flag_unconnected_line_end():
    gdf = gpd.GeoDataFrame(
        {
            "id": [1, 2, 3, 4],
            "geometry": [
                LineString([(0, 0), (1, 0)]),
                LineString([(1, 0), (0, 1)]),
                LineString([(0, 1), (0, 0)]),
                LineString([(5, 5), (5, 6)]),
            ],
        }
    )
    result = check_dangles(gdf)
    assert result.fail_count == 1
    assert result.failing_rows[0]["id"] == 4


def test_completeness_flags_id_sequence_gap():
    result = check_completeness(pd.Series([1, 2, 4]), "objectid")
    assert result.fail_count == 1
    assert result.failing_rows[0]["objectid"] == 3


def test_completeness_not_applicable_without_id_column():
    result = check_completeness(None, None)
    assert result.status == "not_applicable"


def test_projection_uses_majority_crs():
    assert majority_srid([4326, 4326, 3857]) == 4326
    assert check_projection(3857, 4326).fail_count == 1
    assert check_projection(4326, 4326).fail_count == 0


def test_boundary_flags_feature_outside_cover():
    layer = gpd.GeoDataFrame(
        {
            "id": [1, 2],
            "geometry": [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), Polygon([(100, 100), (101, 100), (101, 101), (100, 101)])],
        }
    )
    boundary = gpd.GeoDataFrame({"geometry": [Polygon([(-1, -1), (10, -1), (10, 10), (-1, 10)])]})
    result = check_boundary(layer, boundary)
    assert result.fail_count == 1
    assert result.failing_rows[0]["id"] == 2


def test_custom_attribute_rule_flags_negative_diameter():
    df = pd.DataFrame({"diameter": [10, -1, 3]})
    result = check_custom_rules(df, [{"kind": "attribute", "field": "diameter", "operator": "gt", "value": "0"}])
    assert result.fail_count == 1
    assert result.failing_rows[0]["diameter"] == -1


def test_geometry_type_rule_flags_mismatch():
    gdf = gpd.GeoDataFrame(
        {
            "category": ["Road", "Park"],
            "geometry": [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), Polygon([(2, 2), (3, 2), (3, 3), (2, 3)])],
        }
    )
    result = check_custom_rules(
        gdf,
        [{"kind": "geometry_type", "field": "category", "operator": "eq", "value": "Road", "geometry_type": "LineString"}],
    )
    assert result.fail_count == 1
    assert result.failing_rows[0]["category"] == "Road"
