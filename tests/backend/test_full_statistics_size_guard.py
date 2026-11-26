from types import SimpleNamespace

import pytest

from tarsier.connectors.base import ConnectorError, DataItem
from tarsier.stats import scan


@pytest.mark.parametrize(("row_count", "message"), [
    (0, scan.EMPTY_TABLE),
    (20_001, scan.FULL_STATS_UNAVAILABLE_NO_SAMPLE),
    (None, scan.UNKNOWN_TABLE_SIZE),
])
def test_full_statistics_size_guard_messages(monkeypatch, row_count, message):
    saved = SimpleNamespace(type="postgis", config={})
    connector = SimpleNamespace(build_config=lambda *_: {}, list_items=lambda *_: [DataItem("s", "t", "tabular")], sample_rows=lambda *_args, **_kwargs: None)
    monkeypatch.setattr(scan.connection_storage, "get_connection", lambda _cid: saved)
    monkeypatch.setattr(scan.connection_storage, "get_connection_password", lambda _cid: None)
    monkeypatch.setattr(scan, "get_connector", lambda _type: connector)
    monkeypatch.setattr(scan.item_cache, "get_item", lambda *_: SimpleNamespace(row_count=row_count))
    monkeypatch.setattr(scan.stats_cache, "get_stats", lambda *_: None)

    with pytest.raises(ConnectorError) as exc:
        scan.load_item_sample_limited("c", "s", "t", scan.FULL_RUN_LIMIT)
    assert str(exc.value) == message

    assert "Sample statistics are shown" not in message or row_count == 20_001


def test_large_table_uses_sample_message_only_when_sample_stats_exist(monkeypatch):
    saved = SimpleNamespace(type="postgis", config={})
    connector = SimpleNamespace(build_config=lambda *_: {}, list_items=lambda *_: [DataItem("s", "t", "tabular")], sample_rows=lambda *_args, **_kwargs: None)
    monkeypatch.setattr(scan.connection_storage, "get_connection", lambda _cid: saved)
    monkeypatch.setattr(scan.connection_storage, "get_connection_password", lambda _cid: None)
    monkeypatch.setattr(scan, "get_connector", lambda _type: connector)
    monkeypatch.setattr(scan.item_cache, "get_item", lambda *_: SimpleNamespace(row_count=20_001))
    monkeypatch.setattr(scan.stats_cache, "get_stats", lambda *_: SimpleNamespace(is_sample=True))

    with pytest.raises(ConnectorError) as exc:
        scan.load_item_sample_limited("c", "s", "t", scan.FULL_RUN_LIMIT)
    assert str(exc.value) == scan.FULL_STATS_UNAVAILABLE
