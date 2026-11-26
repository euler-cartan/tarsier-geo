"""Covers TRS-019 through TRS-024 (PRD §7.2): the statistics engine itself,
tested against planted data directly — no connector/Docker needed, since
tarsier.stats.engine works on a plain DataFrame.
"""

import pandas as pd
import pytest

from tarsier.stats.engine import HISTOGRAM_BINS, compute_table_stats


def test_binary_and_array_columns_are_counted_without_utf8_decoding():
    df = pd.DataFrame({"binary": [b"\x81\xff", b"\x81\xff", b"\x00"], "ids": [[1, 2], [1, 2], [3]]})
    result = compute_table_stats(df, is_sample=False)
    columns = {c.name: c for c in result.columns}
    assert columns["binary"].unique_count == 2
    assert columns["binary"].top_values[0] == ("0x81ff", 2)
    assert result.duplicate_row_count == 1


def test_decimal_attributes_have_numeric_stats_and_serializable_flag_rows():
    import json
    from dataclasses import asdict
    from decimal import Decimal
    from datetime import date
    df = pd.DataFrame({"value":[Decimal("1.5"),Decimal("1.5"),Decimal("2.5")],"date":[date(2026,1,1)]*3})
    result=compute_table_stats(df,is_sample=False)
    assert result.columns[0].is_numeric
    assert result.columns[0].minimum == 1.5
    assert result.duplicate_row_count == 1
    assert "2026-01-01" in json.dumps(asdict(result))


def test_per_column_stats_match_hand_calculated_values():
    df = pd.DataFrame({"diameter": [10, 20, 30, None], "material": ["PVC", "PVC", "Steel", "Steel"]})
    stats = compute_table_stats(df, is_sample=False)
    by_name = {c.name: c for c in stats.columns}

    diameter = by_name["diameter"]
    assert diameter.is_numeric is True
    assert diameter.minimum == 10
    assert diameter.maximum == 30
    assert diameter.average == 20
    assert diameter.empty_count == 1
    assert diameter.unique_count == 3

    material = by_name["material"]
    assert material.is_numeric is False
    assert material.unique_count == 2
    assert ("PVC", 2) in material.top_values


def test_messy_category_detection_groups_case_and_whitespace_variants():
    df = pd.DataFrame({"road_type": ["Road", "road", "ROAD", " road ", "Avenue"]})
    stats = compute_table_stats(df, is_sample=False)
    road_type = next(c for c in stats.columns if c.name == "road_type")

    flat = {v for group in road_type.messy_groups for v in group}
    assert {"Road", "road", "ROAD"}.issubset(flat)
    assert "Avenue" not in flat


def test_messy_category_detection_catches_an_abbreviation():
    df = pd.DataFrame({"road_type": ["Road"] * 8 + ["rd"] * 2})
    stats = compute_table_stats(df, is_sample=False)
    road_type = next(c for c in stats.columns if c.name == "road_type")

    flat = {v for group in road_type.messy_groups for v in group}
    assert "Road" in flat and "rd" in flat


def test_out_of_range_numeric_values_are_flagged_as_iqr_outliers():
    df = pd.DataFrame({"year": [2001, 2003, 2005, 2002, 2004, 9999]})
    stats = compute_table_stats(df, is_sample=False)
    year = next(c for c in stats.columns if c.name == "year")

    assert year.out_of_range_count == 1


def test_duplicate_rows_are_detected():
    df = pd.DataFrame({"a": [1, 2, 1], "b": ["x", "y", "x"]})
    stats = compute_table_stats(df, is_sample=False)
    assert stats.duplicate_row_count == 1


def test_null_geometry_is_counted_when_flagged():
    df = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "__geom_null": [False, True, False],
            "__cx": [1.0, None, 3.0],
            "__cy": [1.0, None, 3.0],
        }
    )
    stats = compute_table_stats(
        df, is_sample=False, geometry_columns=("__cx", "__cy"), null_geometry_column="__geom_null"
    )
    assert stats.null_geometry_count == 1


def test_spatial_outlier_detected_far_from_the_cluster():
    xs = [0.0, 0.1, -0.1, 0.05, -0.05, 50.0]  # last point is far away
    ys = [0.0, 0.1, -0.1, -0.05, 0.05, 50.0]
    df = pd.DataFrame({"__cx": xs, "__cy": ys})
    stats = compute_table_stats(df, is_sample=False, geometry_columns=("__cx", "__cy"))
    assert stats.spatial_outlier_count == 1


def test_is_sample_flag_passes_through():
    df = pd.DataFrame({"a": [1, 2, 3]})
    stats = compute_table_stats(df, is_sample=True)
    assert stats.is_sample is True
    assert stats.sampled_row_count == 3


def test_histogram_has_fifteen_bins_and_counts_sum_to_values():
    df = pd.DataFrame({"n": list(range(30))})
    stats = compute_table_stats(df, is_sample=False)
    hist = stats.columns[0].histogram
    assert hist is not None
    assert len(hist) == HISTOGRAM_BINS
    assert sum(b["count"] for b in hist) == 30
    assert hist[0]["start"] == pytest.approx(0)
    assert hist[-1]["end"] == pytest.approx(29)


def test_flag_rows_are_stored_not_just_counts():
    df = pd.DataFrame(
        {
            "a": [1, 1, 2, 3],
            "b": ["x", "x", "y", "z"],
            "__cx": [0.0, 0.1, 0.05, 80.0],
            "__cy": [0.0, 0.1, -0.05, 80.0],
            "__geom_null": [False, True, False, False],
        }
    )
    stats = compute_table_stats(
        df, is_sample=False, geometry_columns=("__cx", "__cy"), null_geometry_column="__geom_null"
    )
    assert stats.duplicate_row_count == 1
    assert { (row["a"], row["b"]) for row in stats.duplicate_rows } == {(1, "x")}
    assert len(stats.duplicate_rows) == 2
    assert stats.null_geometry_rows[0]["a"] == 1 and stats.null_geometry_rows[0]["b"] == "x"
    assert stats.map_outlier_rows[0]["a"] == 3
    assert "centroid_x" in stats.map_outlier_rows[0]


def test_empty_dataframe_does_not_crash():
    df = pd.DataFrame({"a": pd.Series(dtype="float64"), "b": pd.Series(dtype="object")})
    stats = compute_table_stats(df, is_sample=False)
    assert stats.duplicate_row_count == 0
    assert all(c.unique_count == 0 for c in stats.columns)




@pytest.mark.parametrize("values, expected", [
    ([None] * 80 + [0] * 18 + [-2, -3], 2),
    ([0] * 18 + [-2, 3], 2),
    ([7] * 20, 0),
])
def test_zero_iqr_still_flags_values_outside_the_quartiles(values, expected):
    stats = compute_table_stats(pd.DataFrame({"height": values}), is_sample=False)
    assert stats.columns[0].out_of_range_count == expected
    assert len(stats.out_of_range_rows) == expected




@pytest.mark.parametrize("dtype", [object, "string"])
def test_empty_text_includes_whitespace_and_null_but_preserves_text_values(dtype):
    values = pd.Series([None, pd.NA, "", " \t\r\n", "\u2003", "Known", "0", "NULL"], dtype=dtype)
    stats = compute_table_stats(pd.DataFrame({"owner": values}), is_sample=False).columns[0]
    assert stats.empty_count == 5
    assert stats.unique_count == 3
    assert {v for v, count in stats.top_values} == {"Known", "0", "NULL"}




def test_numeric_zero_and_false_are_not_empty_text():
    stats = compute_table_stats(pd.DataFrame({"number": [0, 0, None], "flag": [False, True, None]}), is_sample=False)
    assert [c.empty_count for c in stats.columns] == [1, 1]
