from types import SimpleNamespace

import sqlalchemy

from tarsier.changes.triggers import _write_engine
from tarsier.connectors import postgis
from tarsier.connectors.postgis import PostgisConnectionConfig


def test_connection_check_uses_a_statement_timeout(monkeypatch):
    captured = {}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _statement):
            return None

    class Engine:
        def connect(self):
            return Connection()

        def dispose(self):
            pass

    def create_engine(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Engine()

    monkeypatch.setattr(postgis.sqlalchemy, "create_engine", create_engine)
    postgis.test_connection(PostgisConnectionConfig(host="localhost"))

    assert captured["connect_args"]["connect_timeout"] == 5
    assert "default_transaction_read_only=on" in captured["connect_args"]["options"]
    assert "statement_timeout=5000" in captured["connect_args"]["options"]


def test_trigger_install_bounds_lock_and_statement_waits(monkeypatch):
    captured = {}

    class Engine:
        pass

    def create_engine(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Engine()

    monkeypatch.setattr(sqlalchemy, "create_engine", create_engine)
    _write_engine(PostgisConnectionConfig(host="localhost"))

    assert captured["connect_args"]["connect_timeout"] == 5
    assert "lock_timeout=5000" in captured["connect_args"]["options"]
    assert "statement_timeout=15000" in captured["connect_args"]["options"]


def test_postgis_timeout_errors_are_clear_and_lock_specific():
    config = PostgisConnectionConfig(host="localhost", database="test")
    timeout = SimpleNamespace(orig=SimpleNamespace(sqlstate="57014"), __str__=lambda _self: "statement timeout")
    lock = SimpleNamespace(orig=SimpleNamespace(sqlstate="55P03"), __str__=lambda _self: "lock not available")

    timeout_message = str(postgis._clean_connection_error(config, timeout))
    lock_message = str(postgis._clean_connection_error(config, lock))

    assert "time limit" in timeout_message
    assert "table is busy" in lock_message
