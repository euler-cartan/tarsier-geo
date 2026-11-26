from types import SimpleNamespace
from fastapi.testclient import TestClient
from tarsier.api.app import create_app
from tarsier import overview
from tarsier.connectors import postgis
from tarsier.connectors.base import DataItem, ItemMetadata
from tarsier.storage import connections


def test_no_postgis_still_lists_plain_tables(monkeypatch):
    calls = []
    class Result:
        def scalar(self): return False
        def fetchall(self):
            return [SimpleNamespace(table_schema='public', table_name='ordinary', readable=True)]
    class Conn:
        def execute(self, statement, params=None):
            calls.append(str(statement))
            return Result()
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class Engine:
        def connect(self): return Conn()
        def dispose(self): pass
    monkeypatch.setattr(postgis, '_build_engine', lambda config: Engine())
    items = postgis.list_items(postgis.PostgisConnectionConfig(host='localhost'))
    assert [(item.name, item.kind) for item in items] == [('ordinary', 'tabular')]
    assert any('pg_extension' in statement for statement in calls)
    assert not any('geometry_columns' in statement for statement in calls)


def test_scan_returns_readable_notice_and_keeps_tabular_item(tmp_path, monkeypatch):
    monkeypatch.setenv('TARSIER_HOME', str(tmp_path))
    saved = connections.create_connection('plain database', 'postgis', {'host': 'localhost'})
    connector = SimpleNamespace(
        build_config=lambda config, password: None,
        list_items=lambda config: [DataItem('public', 'ordinary', 'tabular')],
        describe_item=lambda config, item: ItemMetadata(row_count=3),
    )
    monkeypatch.setattr(overview, 'get_connector', lambda kind: connector)
    monkeypatch.setattr(postgis, 'spatial_features_available', lambda config: False)
    monkeypatch.setattr(overview, '_evaluate_alerts', lambda cid: None)
    monkeypatch.setattr('tarsier.graph.engine.refresh_quietly', lambda: None)
    client = TestClient(create_app())
    result = client.post(f'/api/connections/{saved.id}/scan')
    assert result.status_code == 202
    body = client.get(f'/api/connections/{saved.id}/overview').json()
    assert body['source_notice'] == 'PostGIS is not installed in this database. Spatial features are unavailable; non-spatial tables are still available.'
    assert body['layers'][0]['name'] == 'ordinary'
    assert body['layers'][0]['row_count'] == 3
