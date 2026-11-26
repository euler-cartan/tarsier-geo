"""Oracle Spatial connector (PRD §5, TAD §6.1, §3). Read-only.

Lists vector layers (via Oracle Spatial's `ALL_SDO_GEOM_METADATA`), rasters
(via `ALL_TAB_COLUMNS` for SDO_GEORASTER columns), and plain tables.

Oracle Spatial (the MDSYS component) isn't installed on every Oracle
database  -  it's an Enterprise Edition option, absent from Oracle Database
Free/XE and plenty of real installations that never licensed it. When its
catalog views don't exist, everything is correctly listed as plain tables
instead of failing  -  there's nothing spatial a database without Oracle
Spatial could contain.

Read-only note (TAD §9): unlike Postgres, Oracle has no session-wide
"reject every write" flag. `SET TRANSACTION READ ONLY` is issued as the
first statement of every transaction here  -  it genuinely blocks writes for
that transaction, but must be re-issued per transaction, since Oracle
doesn't carry it forward automatically the way Postgres's
default_transaction_read_only does. Tarsier's own code only ever issues
SELECT statements regardless.
"""

from tarsier.timing import timed_phase
from dataclasses import dataclass

import pandas as pd
import sqlalchemy
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError, OperationalError

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
from tarsier.limits import ID_SCAN_MAX_ROWS


@dataclass(frozen=True)
class OracleConnectionConfig:
    host: str
    port: int = 1521
    service_name: str = "XEPDB1"
    username: str = ""
    password: str | None = None
    owners: tuple[str, ...] | None = None  # None = the connected user's own schema

    def url(self) -> sqlalchemy.engine.URL:
        # Built by SQLAlchemy so any character in a password or service name is escaped correctly.
        return sqlalchemy.engine.URL.create(
            "oracle+oracledb",
            username=self.username,
            password=self.password or None,
            host=self.host,
            port=self.port,
            query={"service_name": self.service_name},
        )

    def effective_owners(self) -> tuple[str, ...]:
        return self.owners if self.owners else (self.username.upper(),)


def build_config(config: dict, password: str | None = None) -> OracleConnectionConfig:
    return OracleConnectionConfig(
        host=config.get("host", ""),
        port=int(config.get("port", 1521)),
        service_name=config.get("service_name", "XEPDB1"),
        username=config.get("username", ""),
        password=password,
    )


def _build_engine(config: OracleConnectionConfig):
    return sqlalchemy.create_engine(
        config.url(),
        connect_args={"tcp_connect_timeout": 5},
        pool_pre_ping=True,
    )


def _set_read_only(conn) -> None:
    conn.execute(text("SET TRANSACTION READ ONLY"))


def _clean_connection_error(config: OracleConnectionConfig, exc: Exception) -> ConnectorError:
    detail = str(getattr(exc, "orig", exc))
    if "ORA-01017" in detail:
        message = f"Could not connect: the username or password for {config.username!r} was rejected."
    elif "ORA-12514" in detail or "ORA-12505" in detail:
        message = f"Could not connect: service name {config.service_name!r} was not recognized by {config.host}:{config.port}."
    else:
        message = f"Could not connect to {config.host}:{config.port}  -  check the host, port, and that the server is reachable."
    return ConnectorError(message)


def test_connection(config: OracleConnectionConfig) -> None:
    try:
        engine = _build_engine(config)
        with engine.connect() as conn:
            _set_read_only(conn)
            conn.execute(text("SELECT 1 FROM dual"))
    except (OperationalError, DatabaseError) as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()


@timed_phase("fetch")
def list_items(config: OracleConnectionConfig) -> list[DataItem]:
    engine = _build_engine(config)
    try:
        with engine.connect() as conn:
            _set_read_only(conn)
            vector_items, vector_keys = _list_vector_layers(conn, config.effective_owners())
            raster_items, raster_keys = _list_raster_layers(conn, config.effective_owners())
            tabular_items = _list_tables(conn, config.effective_owners(), vector_keys | raster_keys)
    except (OperationalError, DatabaseError) as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()

    return sorted(
        [*vector_items, *raster_items, *tabular_items],
        key=lambda item: (item.schema, item.name),
    )


@timed_phase("fetch")
def list_foreign_keys(config: OracleConnectionConfig) -> list[dict[str, str]]:
    """Read declared foreign keys visible to the configured Oracle user."""
    engine = _build_engine(config)
    owners = config.effective_owners()
    try:
        with engine.connect() as conn:
            _set_read_only(conn)
            rows = conn.execute(
                text("""
                    SELECT child.owner AS source_schema, child.table_name AS source_name,
                           child_col.column_name AS source_column,
                           parent.owner AS target_schema, parent.table_name AS target_name,
                           parent_col.column_name AS target_column
                    FROM all_constraints child
                    JOIN all_cons_columns child_col
                      ON child_col.owner = child.owner AND child_col.constraint_name = child.constraint_name
                    JOIN all_constraints parent
                      ON parent.owner = child.r_owner AND parent.constraint_name = child.r_constraint_name
                    JOIN all_cons_columns parent_col
                      ON parent_col.owner = parent.owner AND parent_col.constraint_name = parent.constraint_name
                     AND parent_col.position = child_col.position
                    WHERE child.constraint_type = 'R' AND child.owner IN :owners
                """).bindparams(sqlalchemy.bindparam("owners", expanding=True)),
                {"owners": list(owners)},
            ).mappings().all()
    except (OperationalError, DatabaseError) as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()
    return [dict(row) for row in rows]


def _list_vector_layers(conn, owners: tuple[str, ...]):
    try:
        rows = conn.execute(
            text(
                """
                SELECT owner, table_name, column_name, srid
                FROM all_sdo_geom_metadata
                WHERE owner IN :owners
                """
            ).bindparams(sqlalchemy.bindparam("owners", expanding=True)),
            {"owners": list(owners)},
        ).fetchall()
    except DatabaseError as exc:
        if "ORA-00942" not in str(getattr(exc, "orig", exc)):
            raise
        # Oracle Spatial (the MDSYS component) isn't installed on this
        # database  -  common outside Enterprise Edition. No catalog means
        # no spatial columns can exist, so there are no vector layers to
        # find; not an error.
        conn.rollback()
        return [], set()
    # Oracle's SDO_GEOMETRY is one generic type per column  -  unlike
    # PostGIS, there's no cheap metadata-only way to report a specific
    # geometry type (point/line/polygon) without sampling actual rows.
    items = [
        DataItem(
            schema=row.owner, name=row.table_name, kind="vector", geometry_type=None,
            srid=row.srid, geometry_column=row.column_name,
        )
        for row in rows
    ]
    keys = {(item.schema, item.name) for item in items}
    return items, keys


def _list_raster_layers(conn, owners: tuple[str, ...]):
    rows = conn.execute(
        text(
            """
            SELECT owner, table_name
            FROM all_tab_columns
            WHERE data_type = 'SDO_GEORASTER' AND owner IN :owners
            """
        ).bindparams(sqlalchemy.bindparam("owners", expanding=True)),
        {"owners": list(owners)},
    ).fetchall()
    items = [DataItem(schema=row.owner, name=row.table_name, kind="raster") for row in rows]
    keys = {(item.schema, item.name) for item in items}
    return items, keys


def _list_tables(conn, owners: tuple[str, ...], already_classified: set[tuple[str, str]]):
    rows = conn.execute(
        text(
            """
            SELECT owner, table_name
            FROM all_tables
            WHERE owner IN :owners
            """
        ).bindparams(sqlalchemy.bindparam("owners", expanding=True)),
        {"owners": list(owners)},
    ).fetchall()
    return [
        DataItem(schema=row.owner, name=row.table_name, kind="tabular")
        for row in rows
        if (row.owner, row.table_name) not in already_classified
    ]


@timed_phase("fetch")
def describe_item(config: OracleConnectionConfig, item: DataItem) -> ItemMetadata:
    engine = _build_engine(config)
    try:
        with engine.connect() as conn:
            _set_read_only(conn)

            stats_row = conn.execute(
                text("SELECT num_rows FROM all_tables WHERE owner = :o AND table_name = :t"),
                {"o": item.schema, "t": item.name},
            ).fetchone()
            row_count = int(stats_row.num_rows) if stats_row and stats_row.num_rows is not None else None

            size_bytes = None
            try:
                size_row = conn.execute(
                    text(
                        "SELECT bytes FROM user_segments WHERE segment_name = :t AND segment_type = 'TABLE'"
                    ),
                    {"t": item.name},
                ).fetchone()
                size_bytes = int(size_row.bytes) if size_row else None
            except DatabaseError:
                conn.rollback()  # USER_SEGMENTS only covers the connected user's own objects

            index_row = conn.execute(
                text("SELECT COUNT(*) AS c FROM all_indexes WHERE table_owner = :o AND table_name = :t"),
                {"o": item.schema, "t": item.name},
            ).fetchone()
            has_index = bool(index_row.c) if index_row else None
    except (OperationalError, DatabaseError) as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()

    # No bounding box: Oracle Spatial isn't available to test SDO_AGGR_MBR
    # against (see TAD §3's known gap)  -  honest "not available" over a
    # guess.
    return ItemMetadata(row_count=row_count, row_count_is_estimate=True, size_bytes=size_bytes, has_index=has_index)


@timed_phase("fetch", observe_rows=True)
def sample_rows(config: OracleConnectionConfig, item: DataItem, limit: int = 1000, *, distinct_column: str | None = None) -> SampleResult:
    """PRD §7.2's statistics engine needs actual data, not just metadata.
    No centroid/spatial-outlier support here: Oracle Spatial isn't
    available to test SDO_GEOMETRY extraction against (see module
    docstring)  -  an honest gap, not a guess.
    """
    engine = _build_engine(config)
    try:
        with engine.connect() as conn:
            _set_read_only(conn)
            columns = conn.execute(
                text(
                    "SELECT column_name, data_type, data_scale FROM all_tab_columns "
                    "WHERE owner = :o AND table_name = :t AND (:geom IS NULL OR column_name != :geom)"
                ),
                {"o": item.schema, "t": item.name, "geom": item.geometry_column},
            ).fetchall()
            column_names = [row.column_name for row in columns]
            integer_columns = [row.column_name for row in columns if getattr(row, "data_type", "").upper() in {"INTEGER", "INT", "SMALLINT"} or (getattr(row, "data_type", "").upper() == "NUMBER" and getattr(row, "data_scale", None) == 0)]
            if distinct_column is not None:
                if distinct_column not in column_names:
                    raise ConnectorError("Pick a column from this table.")
                column = '"' + distinct_column.replace('"', '""') + '"'
                qualified = '"' + item.schema.replace('"', '""') + '"."' + item.name.replace('"', '""') + '"'
                rows = conn.execute(text(f"SELECT {column} FROM (SELECT DISTINCT {column} FROM {qualified} WHERE {column} IS NOT NULL) WHERE ROWNUM <= :lim"), {"lim": limit + 1}).mappings().all()
                return SampleResult(sample_frame(rows[:limit], columns=[distinct_column], integer_columns=integer_columns), len(rows) > limit)
            select_cols = ", ".join(f'"{c}"' for c in column_names)
            qualified = f'"{item.schema}"."{item.name}"'
            rows = conn.execute(
                text(f"SELECT {select_cols} FROM {qualified} WHERE ROWNUM <= :lim"),
                {"lim": limit + 1},
            ).mappings().all()
    except (OperationalError, DatabaseError) as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()

    is_sample = len(rows) > limit
    return SampleResult(dataframe=sample_frame(rows[:limit], integer_columns=integer_columns), is_sample=is_sample)


@timed_phase("fetch", observe_rows=True)
def sample_geometries(config: OracleConnectionConfig, item: DataItem, limit: int = 1000) -> GeometrySample:  # noqa: ARG001
    raise ConnectorError(
        "Geometry quality checks aren't available for Oracle yet  -  Oracle Spatial isn't "
        "installed on the instances Tarsier can test against."
    )


@timed_phase("fetch", observe_rows=True)
def sample_id_values(config: OracleConnectionConfig, item: DataItem) -> IdColumnSample | None:
    engine = _build_engine(config)
    try:
        with engine.connect() as conn:
            _set_read_only(conn)
            columns = conn.execute(
                text(
                    "SELECT column_name FROM all_tab_columns "
                    "WHERE owner = :o AND table_name = :t AND (:geom IS NULL OR column_name != :geom)"
                ),
                {"o": item.schema, "t": item.name, "geom": item.geometry_column},
            ).fetchall()
            column = find_id_column([row.column_name for row in columns])
            if column is None:
                return None
            qualified = f'"{item.schema}"."{item.name}"'
            # Lowest IDs first, bounded: never pull a very large table's whole ID column.
            rows = conn.execute(
                text(f'SELECT "{column}" FROM {qualified} WHERE "{column}" IS NOT NULL '
                     f'ORDER BY "{column}" FETCH FIRST :lim ROWS ONLY'),
                {"lim": ID_SCAN_MAX_ROWS + 1},
            ).fetchall()
    except (OperationalError, DatabaseError) as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()
    is_sample = len(rows) > ID_SCAN_MAX_ROWS
    values = pd.Series([row[0] for row in rows[:ID_SCAN_MAX_ROWS]], name=column)
    return IdColumnSample(column=column, values=values, is_sample=is_sample)
