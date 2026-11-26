from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.dialects import postgresql

from tarsier.connectors import postgis
from tarsier.connectors.base import DataItem


class _Result:
    def __init__(self, row=None, scalar=None):
        self.row, self.scalar = row, scalar

    def fetchone(self):
        return self.row

    def scalar_one(self):
        return self.scalar


class _Connection:
    dialect = postgresql.dialect()

    def __init__(self, count=None, count_error=None):
        self.count, self.count_error, self.calls, self.rollbacks = count, count_error, [], 0

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append(sql)
        if "reltuples" in sql:
            return _Result(SimpleNamespace(estimate=-1, size_bytes=64))
        if "SELECT count(*)" in sql:
            if self.count_error:
                raise self.count_error
            return _Result(scalar=self.count)
        if "statement_timeout" in sql:
            return _Result()
        if "pg_indexes" in sql:
            return _Result(SimpleNamespace(c=0))
        raise AssertionError(sql)

    def rollback(self):
        self.rollbacks += 1


class _Engine:
    def __init__(self, conn):
        self.conn = conn

    def connect(self):
        return self

    def __enter__(self):
        return self.conn

    def __exit__(self, *_):
        return False

    def dispose(self):
        pass


@pytest.mark.parametrize("count", [0, 1, 20_000])
def test_missing_reltuples_uses_bounded_exact_count(monkeypatch, count):
    conn = _Connection(count=count)
    monkeypatch.setattr(postgis, "_build_engine", lambda _config: _Engine(conn))

    metadata = postgis.describe_item(
        postgis.PostgisConnectionConfig("localhost"), DataItem("odd schema", "table name", "tabular")
    )

    assert metadata.row_count == count
    assert metadata.row_count_is_estimate is False
    assert metadata.row_count_is_capped is False
    count_sql = next(sql for sql in conn.calls if "SELECT count(*)" in sql)
    assert 'FROM (SELECT 1 FROM "odd schema"."table name" LIMIT 20001) s' in count_sql
    assert any("statement_timeout = 2000" in sql for sql in conn.calls)


def test_missing_reltuples_caps_large_count_at_20001(monkeypatch):
    conn = _Connection(count=20_001)
    monkeypatch.setattr(postgis, "_build_engine", lambda _config: _Engine(conn))

    metadata = postgis.describe_item(postgis.PostgisConnectionConfig("localhost"), DataItem("s", "t", "tabular"))

    assert metadata.row_count == 20_001
    assert metadata.row_count_is_estimate is False
    assert metadata.row_count_is_capped is True


def test_bounded_count_timeout_leaves_size_unknown(monkeypatch):
    timeout = OperationalError("count", {}, Exception("timeout"))
    conn = _Connection(count_error=timeout)
    monkeypatch.setattr(postgis, "_build_engine", lambda _config: _Engine(conn))

    metadata = postgis.describe_item(postgis.PostgisConnectionConfig("localhost"), DataItem("s", "t", "tabular"))

    assert metadata.row_count is None
    assert metadata.row_count_is_estimate is False
    assert conn.rollbacks == 1
    assert any("pg_indexes" in sql for sql in conn.calls)


def test_existing_item_cache_schema_gets_capped_count_marker(tmp_path):
    from sqlalchemy import create_engine, inspect, text
    from tarsier.storage.db import _apply_simple_migrations

    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE item_metadata_cache (connection_id VARCHAR, "schema" VARCHAR, name VARCHAR)'))

    _apply_simple_migrations(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("item_metadata_cache")}
    assert "row_count_is_capped" in columns
    engine.dispose()
