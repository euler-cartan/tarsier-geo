"""Covers TRS-007's data (PRD §5): the tier rules behind the notice text."""

import pytest

from tarsier.connectors.tiers import get_connection_type_info, list_connection_types


def test_lists_all_six_types_in_prd_order():
    ids = [t.id for t in list_connection_types()]
    assert ids == ["postgis", "oracle", "sqlserver", "files", "arcgis", "geoserver"]


def test_postgis_is_fully_available_with_no_notice():
    info = get_connection_type_info("postgis")
    assert info.change_tracking == "full"
    assert info.quality_checks == "full"
    assert info.statistics == "full"
    assert info.notice is None


@pytest.mark.parametrize(
    "type_id,change_tracking,quality_checks",
    [
        ("oracle", "partial", "full"),
        ("sqlserver", "partial", "full"),
        ("files", "none", "full"),
        ("arcgis", "partial", "partial"),
        ("geoserver", "partial", "partial"),
    ],
)
def test_other_types_match_prd_table(type_id, change_tracking, quality_checks):
    info = get_connection_type_info(type_id)
    assert info.change_tracking == change_tracking
    assert info.quality_checks == quality_checks
    assert info.statistics == "full"
    assert info.notice is not None
    assert len(info.notice) > 0


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        get_connection_type_info("made-up-type")
