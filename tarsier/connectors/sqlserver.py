"""SQL Server connector (PRD §5, TAD §6.1, §3). Read-only.

Lists vector layers (any column typed `geometry`/`geography`  -  SQL Server's
own built-in spatial types, found via INFORMATION_SCHEMA.COLUMNS) and plain
tables. No raster listing: SQL Server has no native raster/image spatial
type comparable to PostGIS raster or Oracle GeoRaster.

Read-only note (TAD §9): SQL Server has no T-SQL equivalent of Postgres's
`default_transaction_read_only` or Oracle's `SET TRANSACTION READ ONLY`  -
there is no server-enforced read-only session mode for an ordinary
database connection. Read-only here is application discipline only:
Tarsier's code issues nothing but SELECT. For a stronger guarantee, the
user should provision a SQL Server login with only SELECT/VIEW permission
 -  outside what Tarsier's own code can enforce.
"""

from tarsier.timing import timed_phase
from dataclasses import dataclass

import pandas as pd
import sqlalchemy
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tarsier.connectors.base import (
    ConnectorError,
    DataItem,
    GeometrySample,
    IdColumnSample,
    ItemMetadata,
    SampleResult,
    sample_frame,
    find_id_column,
)
from tarsier.connectors.geoms import geodataframe_from_wkb_rows
from tarsier.limits import ID_SCAN_MAX_ROWS

_EXCLUDED_SCHEMAS = ("sys", "INFORMATION_SCHEMA", "guest", "db_owner", "db_accessadmin",
                     "db_securityadmin", "db_ddladmin", "db_backupoperator", "db_datareader",
                     "db_datawriter", "db_denydatareader", "db_denydatawriter")


@dataclass(frozen=True)
class SqlServerConnectionConfig:
    host: str
    port: int = 1433
    database: str = "master"
    username: str = "sa"
    password: str | None = None
    schemas: tuple[str, ...] | None = None  # None = all non-system schemas

    def url(self) -> sqlalchemy.engine.URL:
        # Built by SQLAlchemy so any character in a password or database name is escaped correctly.
        return sqlalchemy.engine.URL.create(
            "mssql+pymssql",
            username=self.username,
            password=self.password or None,
            host=self.host,
            port=self.port,
            database=self.database,
        )


def build_config(config: dict, password: str | None = None) -> SqlServerConnectionConfig:
    return SqlServerConnectionConfig(
        host=config.get("host", ""),
        port=int(config.get("port", 1433)),
        database=config.get("database", "master"),
        username=config.get("username", "sa"),
        password=password,
    )


def _b(identifier: str) -> str:
    """Bracket-quote a schema/table/column name, escaping a closing bracket."""
    return "[" + str(identifier).replace("]", "]]") + "]"


def _qualified(item: DataItem) -> str:
    return f"{_b(item.schema)}.{_b(item.name)}"


def _build_engine(config: SqlServerConnectionConfig):
    return sqlalchemy.create_engine(
        config.url(),
        connect_args={"login_timeout": 5},
        pool_pre_ping=True,
    )


def _clean_connection_error(config: SqlServerConnectionConfig, exc: Exception) -> ConnectorError:
    detail = str(getattr(exc, "orig", exc))
    if "Login failed" in detail:
        message = f"Could not connect: the username or password for {config.username!r} was rejected."
    elif "Cannot open database" in detail:
        message = f"Could not connect: database {config.database!r} does not exist on {config.host}:{config.port}."
    else:
        message = f"Could not connect to {config.host}:{config.port}/{config.database}  -  check the host, port, and that the server is reachable."
    return ConnectorError(message)


def test_connection(config: SqlServerConnectionConfig) -> None:
    try:
        engine = _build_engine(config)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except DBAPIError as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()


def _schema_filter_sql(column: str) -> str:
    excluded = ", ".join(f"'{s}'" for s in _EXCLUDED_SCHEMAS)
    return f"{column} NOT IN ({excluded})"


def _schema_scope_sql(column: str, schemas: tuple[str, ...] | None) -> tuple[str, dict]:
    if schemas:
        placeholders = ", ".join(f":schema_{i}" for i in range(len(schemas)))
        return f"{column} IN ({placeholders})", {f"schema_{i}": s for i, s in enumerate(schemas)}
    return _schema_filter_sql(column), {}


@timed_phase("fetch")
def list_items(config: SqlServerConnectionConfig) -> list[DataItem]:
    engine = _build_engine(config)
    try:
        with engine.connect() as conn:
            vector_items, vector_keys = _list_vector_layers(conn, config.schemas)
            tabular_items = _list_tables(conn, config.schemas, vector_keys)
    except DBAPIError as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()

    return sorted([*vector_items, *tabular_items], key=lambda item: (item.schema, item.name))


@timed_phase("fetch")
def list_foreign_keys(config: SqlServerConnectionConfig) -> list[dict[str, str]]:
    """Read declared foreign-key columns from SQL Server catalog views."""
    engine = _build_engine(config)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT source_schema.name AS source_schema, source_table.name AS source_name,
                       source_column.name AS source_column,
                       target_schema.name AS target_schema, target_table.name AS target_name,
                       target_column.name AS target_column
                FROM sys.foreign_key_columns AS fk
                JOIN sys.tables AS source_table ON source_table.object_id = fk.parent_object_id
                JOIN sys.schemas AS source_schema ON source_schema.schema_id = source_table.schema_id
                JOIN sys.columns AS source_column
                  ON source_column.object_id = fk.parent_object_id AND source_column.column_id = fk.parent_column_id
                JOIN sys.tables AS target_table ON target_table.object_id = fk.referenced_object_id
                JOIN sys.schemas AS target_schema ON target_schema.schema_id = target_table.schema_id
                JOIN sys.columns AS target_column
                  ON target_column.object_id = fk.referenced_object_id AND target_column.column_id = fk.referenced_column_id
            """)).mappings().all()
    except DBAPIError as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()
    return [dict(row) for row in rows]


def _list_vector_layers(conn, schemas):
    clause, params = _schema_scope_sql("table_schema", schemas)
    rows = conn.execute(
        text(
            f"""
            SELECT table_schema, table_name, column_name, data_type
            FROM information_schema.columns
            WHERE data_type IN ('geometry', 'geography') AND {clause}
            """
        ),
        params,
    ).fetchall()
    items = [
        DataItem(
            schema=row.table_schema, name=row.table_name, kind="vector",
            geometry_type=row.data_type, geometry_column=row.column_name,
        )
        for row in rows
    ]
    keys = {(item.schema, item.name) for item in items}
    return items, keys


def _list_tables(conn, schemas, already_classified: set[tuple[str, str]]):
    clause, params = _schema_scope_sql("table_schema", schemas)
    rows = conn.execute(
        text(
            f"""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE' AND {clause}
            """
        ),
        params,
    ).fetchall()
    return [
        DataItem(schema=row.table_schema, name=row.table_name, kind="tabular")
        for row in rows
        if (row.table_schema, row.table_name) not in already_classified
    ]


@timed_phase("fetch")
def describe_item(config: SqlServerConnectionConfig, item: DataItem) -> ItemMetadata:
    engine = _build_engine(config)
    qualified = _qualified(item)
    try:
        with engine.connect() as conn:
            # sys.dm_db_partition_stats is catalog metadata  -  no table scan,
            # per TAD §8's "read gently."
            row = conn.execute(
                text(
                    "SELECT SUM(row_count) AS rows_, "
                    "SUM(reserved_page_count) * 8 * 1024 AS size_bytes "
                    "FROM sys.dm_db_partition_stats "
                    "WHERE object_id = OBJECT_ID(:qualified) AND index_id IN (0, 1)"
                ),
                {"qualified": qualified},
            ).fetchone()
            row_count = int(row.rows_) if row and row.rows_ is not None else None
            size_bytes = int(row.size_bytes) if row and row.size_bytes is not None else None

            index_row = conn.execute(
                text("SELECT COUNT(*) AS c FROM sys.indexes WHERE object_id = OBJECT_ID(:qualified) AND type > 0"),
                {"qualified": qualified},
            ).fetchone()
            has_index = bool(index_row.c) if index_row else None
    except DBAPIError as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()

    # No bounding box: T-SQL has no built-in envelope aggregate across rows
    # without a CLR extension  -  honest "not available" over a guess.
    return ItemMetadata(row_count=row_count, size_bytes=size_bytes, has_index=has_index)


@timed_phase("fetch", observe_rows=True)
def sample_rows(config: SqlServerConnectionConfig, item: DataItem, limit: int = 1000, *, distinct_column: str | None = None) -> SampleResult:
    """PRD §7.2's statistics engine needs actual data, not just metadata.
    Unlike Oracle, SQL Server's geometry type supports spatial methods in
    T-SQL directly, so spatial-outlier detection works here  -  but found
    via a direct pymssql check that `.STCentroid()` itself returns NULL
    for anything that isn't a polygon (a real SQL Server limitation, not
    a driver bug: it returns the centroid of the *area*, undefined for a
    LineString/Point). Centroid of the bounding box (`.STEnvelope()
    .STCentroid()`) works for every geometry type instead  -  confirmed
    directly against the seeded LineString fixture.
    """
    engine = _build_engine(config)
    qualified = _qualified(item)
    try:
        with engine.connect() as conn:
            columns = conn.execute(
                text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = :s AND table_name = :n AND (:geom IS NULL OR column_name != :geom)"
                ),
                {"s": item.schema, "n": item.name, "geom": item.geometry_column},
            ).fetchall()
            column_names = [row.column_name for row in columns]
            integer_columns = [row.column_name for row in columns if getattr(row, "data_type", "").upper() in {"SMALLINT", "INTEGER", "BIGINT", "TINYINT"}]
            if distinct_column is not None:
                if distinct_column not in column_names:
                    raise ConnectorError("Pick a column from this table.")
                column = "[" + distinct_column.replace("]", "]]") + "]"
                qualified = f"[{item.schema.replace(chr(93), chr(93)*2)}].[{item.name.replace(chr(93), chr(93)*2)}]"
                rows = conn.execute(text(f"SELECT DISTINCT TOP (:lim) {column} FROM {qualified} WHERE {column} IS NOT NULL"), {"lim": limit + 1}).mappings().all()
                return SampleResult(sample_frame(rows[:limit], columns=[distinct_column], integer_columns=integer_columns), len(rows) > limit)

            select_parts = [_b(c) for c in column_names]
            geometry_columns = null_geometry_column = None
            if item.kind == "vector" and item.geometry_column:
                geom_col = _b(item.geometry_column)
                select_parts += [
                    f"{geom_col}.STEnvelope().STCentroid().STX AS __cx",
                    f"{geom_col}.STEnvelope().STCentroid().STY AS __cy",
                    f"CASE WHEN {geom_col} IS NULL THEN 1 ELSE 0 END AS __geom_null",
                ]
                geometry_columns = ("__cx", "__cy")
                null_geometry_column = "__geom_null"

            rows = conn.execute(
                text(f"SELECT TOP (:lim) {', '.join(select_parts)} FROM {qualified}"),
                {"lim": limit + 1},
            ).mappings().all()
    except DBAPIError as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()

    is_sample = len(rows) > limit
    df = sample_frame(rows[:limit], integer_columns=integer_columns)
    if null_geometry_column and null_geometry_column in df.columns:
        df[null_geometry_column] = df[null_geometry_column].astype(bool)
    return SampleResult(
        dataframe=df, is_sample=is_sample,
        geometry_columns=geometry_columns, null_geometry_column=null_geometry_column,
    )


@timed_phase("fetch", observe_rows=True)
def sample_geometries(config: SqlServerConnectionConfig, item: DataItem, limit: int = 1000) -> GeometrySample:
    if item.kind != "vector" or not item.geometry_column:
        raise ConnectorError("Geometry quality checks need a vector layer.")
    engine = _build_engine(config)
    qualified = _qualified(item)
    try:
        with engine.connect() as conn:
            columns = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = :s AND table_name = :n AND (:geom IS NULL OR column_name != :geom)"
                ),
                {"s": item.schema, "n": item.name, "geom": item.geometry_column},
            ).fetchall()
            column_names = [row.column_name for row in columns]
            select_parts = [_b(c) for c in column_names]
            geom_col = _b(item.geometry_column)
            select_parts.append(f"{geom_col}.STAsBinary() AS __wkb")
            rows = conn.execute(
                text(f"SELECT TOP (:lim) {', '.join(select_parts)} FROM {qualified}"),
                {"lim": limit + 1},
            ).mappings().all()
    except DBAPIError as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()
    is_sample = len(rows) > limit
    gdf = geodataframe_from_wkb_rows(rows[:limit], item.srid)
    return GeometrySample(geodataframe=gdf, is_sample=is_sample)


@timed_phase("fetch", observe_rows=True)
def sample_id_values(config: SqlServerConnectionConfig, item: DataItem) -> IdColumnSample | None:
    engine = _build_engine(config)
    qualified = _qualified(item)
    try:
        with engine.connect() as conn:
            columns = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = :s AND table_name = :n AND (:geom IS NULL OR column_name != :geom)"
                ),
                {"s": item.schema, "n": item.name, "geom": item.geometry_column},
            ).fetchall()
            column = find_id_column([row.column_name for row in columns])
            if column is None:
                return None
            # Lowest IDs first, bounded: never pull a very large table's whole ID column.
            rows = conn.execute(
                text(f"SELECT TOP (:lim) {_b(column)} FROM {qualified} WHERE {_b(column)} IS NOT NULL "
                     f"ORDER BY {_b(column)}"),
                {"lim": ID_SCAN_MAX_ROWS + 1},
            ).fetchall()
    except DBAPIError as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()
    is_sample = len(rows) > ID_SCAN_MAX_ROWS
    values = pd.Series([row[0] for row in rows[:ID_SCAN_MAX_ROWS]], name=column)
    return IdColumnSample(column=column, values=values, is_sample=is_sample)
