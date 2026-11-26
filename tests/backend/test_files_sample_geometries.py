from tarsier.connectors.files import FilesConnectionConfig, list_items, sample_geometries, sample_id_values

FIXTURE_DIR = "tests/datasets/quality_planted"


def test_sample_geometries_keeps_raw_geometry():
    items = list_items(FilesConnectionConfig(folder=FIXTURE_DIR))
    parcels = next(i for i in items if i.name == "parcels")
    sample = sample_geometries(FilesConnectionConfig(folder=FIXTURE_DIR), parcels)
    assert sample.is_sample is False
    assert sample.geodataframe.geometry.notna().all()
    assert (~sample.geodataframe.geometry.is_valid).sum() == 1


def test_sample_id_values_reads_full_objectid_column():
    items = list_items(FilesConnectionConfig(folder=FIXTURE_DIR))
    parcels = next(i for i in items if i.name == "parcels")
    sample = sample_id_values(FilesConnectionConfig(folder=FIXTURE_DIR), parcels)
    assert sample is not None
    assert sample.column.lower() == "objectid"
    assert 3 not in set(sample.values.astype(int))
