"""PostGIS / PostgreSQL connector (PRD §5, TAD §6.1, §3). Read-only.

Lists vector layers (via PostGIS's `geometry_columns`), rasters stored in
the database (via `raster_columns`, when the postgis_raster extension is
installed), and plain tables (PRD §6.2 tabular data)  -  everything else in
the target schemas.
"""

from tarsier.timing import timed_phase
from dataclasses import dataclass

import pandas as pd
import sqlalchemy
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError, DBAPIError

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

_EXCLUDED_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast", "topology", "tiger", "tiger_data", "tarsier_changes")

# PostGIS's own catalog tables, found living in `public` by default (not a
# separate schema we could exclude the normal way)  -  not user data, so
# never listed as a layer/table. geometry_columns/raster_columns are views
# in modern PostGIS and already excluded by the BASE TABLE filter below.
_POSTGIS_INTERNAL_TABLES = ("spatial_ref_sys",)


@dataclass(frozen=True)
class PostgisConnectionConfig:
    host: str
    port: int = 5432
    database: str = "postgres"
    username: str = "postgres"
    password: str | None = None
    schemas: tuple[str, ...] | None = None  # None = all non-system schemas

    def url(self) -> sqlalchemy.engine.URL:
        # Built by SQLAlchemy rather than string formatting so any character
        # in a password, database name or IPv6 host is escaped correctly.
        return sqlalchemy.engine.URL.create(
            "postgresql+psycopg",
            username=self.username,
            password=self.password or None,
            host=self.host,
            port=self.port,
            database=self.database,
        )


def build_config(config: dict, password: str | None = None) -> PostgisConnectionConfig:
    return PostgisConnectionConfig(
        host=config.get("host", ""),
        port=int(config.get("port", 5432)),
        database=config.get("database", "postgres"),
        username=config.get("username", "postgres"),
        password=password,
    )


APPLICATION_NAME = "tarsier-geo"
_READ_LOCK_TIMEOUT_MS = 5_000
_READ_STATEMENT_TIMEOUT_MS = 300_000  # ceiling for a full-run read; normal samples finish in milliseconds
_ROW_COUNT_FALLBACK_TIMEOUT_MS = 2_000
_ROW_COUNT_FALLBACK_LIMIT = 20_001


def _build_engine(config: PostgisConnectionConfig, *, statement_timeout_ms: int | None = None):
    # TAD §9: Tarsier is read-only on user data. `default_transaction_read_only`
    # is enforced by Postgres itself, not just application discipline  -  any
    # write attempted over this connection is rejected server-side.
    options = ["-c default_transaction_read_only=on"]
    # TAD §8 "read gently" / TRS-103: monitoring only ever takes share-level
    # locks, never waits long behind someone else's DDL (lock_timeout), and no
    # single read may run unbounded (statement_timeout ceiling). A DBA can
    # recognise these sessions by their application_name.
    options.append(f"-c lock_timeout={_READ_LOCK_TIMEOUT_MS}")
    options.append(f"-c statement_timeout={statement_timeout_ms if statement_timeout_ms is not None else _READ_STATEMENT_TIMEOUT_MS}")
    return sqlalchemy.create_engine(
        config.url(),
        # TAD §8: "read gently"  -  never let an unreachable host hang a
        # request indefinitely; fail fast and clearly instead.
        connect_args={
            "options": " ".join(options),
            "connect_timeout": 5,
            "application_name": APPLICATION_NAME,
        },
        pool_pre_ping=True,
    )


def _q(identifier: str) -> str:
    """Quote a schema/table/column name. Real databases have mixed-case names,
    spaces and quotes in identifiers; unquoted they fail or mean something else."""
    return '"' + str(identifier).replace('"', '""') + '"'


def _qualified(item: DataItem) -> str:
    return f"{_q(item.schema)}.{_q(item.name)}"


# A table at or under this size may have its exact extent computed when the
# planner has no statistics for it yet. Larger tables are never fully scanned
# just to draw a bounding box.
_EXACT_EXTENT_MAX_BYTES = 256 * 1024 * 1024


def _clean_connection_error(config: PostgisConnectionConfig, exc: DBAPIError) -> ConnectorError:
    # psycopg's raw message includes IPv6/IPv4 retry noise and other driver
    # internals  -  not the plain-language error FSD §15 requires. Classify by
    # the well-known Postgres FATAL text instead of surfacing it verbatim.
    detail = str(exc.orig)
    sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
    if sqlstate == "42501":
        # Very common on locked-down production databases: the monitoring
        # role can see a table in the catalog but may not read it.
        message = (
            f"The database user {config.username!r} doesn't have permission to read this data. "
            "Ask a database administrator for SELECT access."
        )
    elif getattr(exc, "connection_invalidated", False) or sqlstate in {"57P01", "57P02", "57P03"} or (sqlstate or "").startswith("08"):
        message = "The database connection was interrupted. Run the check again."
    elif sqlstate == "55P03":
        message = (
            "The database table is busy, so Tarsier stopped waiting rather than hold anything up. "
            "Wait for active database work to finish, then try again."
        )
    elif sqlstate == "57014" or "timeout" in detail.casefold():
        message = (
            "Could not connect: the database did not respond within the time limit. "
            "Check the server and any active database work, then try again."
        )
    elif "password authentication failed" in detail or "role" in detail and "does not exist" in detail:
        message = f"Could not connect: the username or password for {config.username!r} was rejected."
    elif f'database "{config.database}" does not exist' in detail:
        message = f"Could not connect: database {config.database!r} does not exist on {config.host}:{config.port}."
    elif isinstance(exc, DBAPIError) and not isinstance(exc, OperationalError):
        # A query the server rejected (missing table, unsupported projection,
        # bad data). The first line of the server message names the object and
        # never contains credentials.
        first_line = detail.splitlines()[0] if detail else "unknown error"
        message = f"The database could not complete this read: {first_line}"
    else:
        message = f"Could not connect to {config.host}:{config.port}/{config.database}  -  check the host, port, and that the server is reachable."
    return ConnectorError(message)


def test_connection(config: PostgisConnectionConfig) -> None:
    if not str(config.host or "").strip():
        raise ConnectorError("Enter the database host.")
    # The connection check is only SELECT 1, so a slow response indicates
    # an unhealthy or blocked connection and should fail promptly.
    engine = _build_engine(config, statement_timeout_ms=5_000)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except DBAPIError as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()


def _schema_filter_sql(column: str) -> str:
    excluded = ", ".join(f"'{s}'" for s in _EXCLUDED_SCHEMAS)
    clause = f"{column} NOT IN ({excluded})"
    return clause


@timed_phase("fetch")
def list_items(config: PostgisConnectionConfig) -> list[DataItem]:
    engine = _build_engine(config)
    try:
        with engine.connect() as conn:
            if _has_postgis(conn):
                vector_items, vector_keys = _list_vector_layers(conn, config.schemas)
                raster_items, raster_keys = _list_raster_layers(conn, config.schemas)
            else:
                vector_items, vector_keys = [], set()
                raster_items, raster_keys = [], set()
            tabular_items = _list_tables(conn, config.schemas, vector_keys | raster_keys)
    except DBAPIError as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()

    return sorted(
        [*vector_items, *raster_items, *tabular_items],
        key=lambda item: (item.schema, item.name),
    )


def _has_postgis(conn) -> bool:
    return bool(conn.execute(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis')")).scalar())


def spatial_features_available(config: PostgisConnectionConfig) -> bool:
    """Check extension availability using only PostgreSQL catalog reads."""
    engine = _build_engine(config)
    try:
        with engine.connect() as conn:
            return _has_postgis(conn)
    except DBAPIError as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()


@timed_phase("fetch")
def list_foreign_keys(config: PostgisConnectionConfig) -> list[dict[str, str]]:
    """Read declared foreign-key columns from PostgreSQL's information schema."""
    engine = _build_engine(config)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT kcu.table_schema AS source_schema, kcu.table_name AS source_name,
                       kcu.column_name AS source_column,
                       rku.table_schema AS target_schema, rku.table_name AS target_name,
                       rku.column_name AS target_column
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_catalog = kcu.constraint_catalog
                 AND tc.constraint_schema = kcu.constraint_schema
                 AND tc.constraint_name = kcu.constraint_name
                JOIN information_schema.referential_constraints AS rc
                  ON rc.constraint_catalog = tc.constraint_catalog
                 AND rc.constraint_schema = tc.constraint_schema
                 AND rc.constraint_name = tc.constraint_name
                JOIN information_schema.key_column_usage AS rku
                  ON rku.constraint_catalog = rc.unique_constraint_catalog
                 AND rku.constraint_schema = rc.unique_constraint_schema
                 AND rku.constraint_name = rc.unique_constraint_name
                 AND rku.ordinal_position = kcu.position_in_unique_constraint
                WHERE tc.constraint_type = 'FOREIGN KEY'
            """)).mappings().all()
    except (OperationalError, ProgrammingError) as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()
    return [dict(row) for row in rows]


def _schema_scope_sql(column: str, schemas: tuple[str, ...] | None) -> tuple[str, dict]:
    if schemas:
        return f"{column} = ANY(:schemas)", {"schemas": list(schemas)}
    return _schema_filter_sql(column), {}


def _list_vector_layers(conn, schemas):
    clause, params = _schema_scope_sql("f_table_schema", schemas)
    rows = conn.execute(
        text(
            f"""
            SELECT f_table_schema, f_table_name, f_geometry_column, type, srid
            FROM geometry_columns
            WHERE {clause}
            """
        ),
        params,
    ).fetchall()
    items = [
        DataItem(
            schema=row.f_table_schema, name=row.f_table_name, kind="vector",
            geometry_type=row.type, srid=row.srid, geometry_column=row.f_geometry_column,
        )
        for row in rows
    ]
    keys = {(item.schema, item.name) for item in items}
    return items, keys


def _list_raster_layers(conn, schemas):
    clause, params = _schema_scope_sql("r_table_schema", schemas)
    try:
        rows = conn.execute(
            text(
                f"""
                SELECT r_table_schema, r_table_name, srid
                FROM raster_columns
                WHERE {clause}
                """
            ),
            params,
        ).fetchall()
    except ProgrammingError:
        # postgis_raster extension isn't installed on this database  -  no
        # raster layers possible, not an error.
        conn.rollback()
        return [], set()
    items = [
        DataItem(schema=row.r_table_schema, name=row.r_table_name, kind="raster", srid=row.srid)
        for row in rows
    ]
    keys = {(item.schema, item.name) for item in items}
    return items, keys


def _list_tables(conn, schemas, already_classified: set[tuple[str, str]]):
    # information_schema.tables hides tables the role cannot read. Catalog
    # metadata keeps those visible so the UI can say "no permission".
    clause, params = _schema_scope_sql("n.nspname", schemas)
    rows = conn.execute(
        text(
            f"""
            SELECT n.nspname AS table_schema, c.relname AS table_name,
                   has_schema_privilege(n.oid, 'USAGE')
                   AND has_table_privilege(c.oid, 'SELECT') AS readable
            FROM pg_catalog.pg_class AS c
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r', 'p', 'f') AND {clause}
            """
        ),
        params,
    ).fetchall()
    return [
        DataItem(schema=row.table_schema, name=row.table_name, kind="tabular", readable=bool(row.readable))
        for row in rows
        if (row.table_schema, row.table_name) not in already_classified
        and row.table_name not in _POSTGIS_INTERNAL_TABLES
    ]


@timed_phase("fetch")
def describe_item(config: PostgisConnectionConfig, item: DataItem) -> ItemMetadata:
    engine = _build_engine(config)
    try:
        with engine.connect() as conn:
            qualified = _qualified(item)
            row = conn.execute(
                text(
                    "SELECT reltuples::bigint AS estimate, "
                    "pg_total_relation_size(to_regclass(:q)) AS size_bytes "
                    "FROM pg_class WHERE oid = to_regclass(:q)"
                ),
                {"q": qualified},
            ).fetchone()
            row_count = int(row.estimate) if row and row.estimate is not None and row.estimate >= 0 else None
            row_count_is_estimate = row_count is not None
            row_count_is_capped = False
            size_bytes = int(row.size_bytes) if row and row.size_bytes is not None else None

            if row_count is None:
                preparer = conn.dialect.identifier_preparer
                qualified_identifier = f"{preparer.quote_schema(item.schema)}.{preparer.quote(item.name)}"
                try:
                    conn.execute(text(f"SET LOCAL statement_timeout = {_ROW_COUNT_FALLBACK_TIMEOUT_MS}"))
                    bounded_count = conn.execute(text(
                        f"SELECT count(*) FROM (SELECT 1 FROM {qualified_identifier} "
                        f"LIMIT {_ROW_COUNT_FALLBACK_LIMIT}) s"
                    )).scalar_one()
                    row_count = int(bounded_count)
                    row_count_is_estimate = False
                    row_count_is_capped = row_count == _ROW_COUNT_FALLBACK_LIMIT
                    conn.execute(text(f"SET LOCAL statement_timeout = {_READ_STATEMENT_TIMEOUT_MS}"))
                except DBAPIError as exc:
                    if exc.connection_invalidated:
                        raise
                    conn.rollback()
                    row_count = None

            index_row = conn.execute(
                text("SELECT COUNT(*) AS c FROM pg_indexes WHERE schemaname = :s AND tablename = :n"),
                {"s": item.schema, "n": item.name},
            ).fetchone()
            has_index = bool(index_row.c) if index_row else None

            bbox = None
            if item.kind == "vector" and item.geometry_column:
                bbox = _layer_bbox(conn, item, size_bytes)
    except DBAPIError as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()

    return ItemMetadata(
        row_count=row_count, row_count_is_estimate=row_count_is_estimate,
        row_count_is_capped=row_count_is_capped, size_bytes=size_bytes,
        has_index=has_index, bbox=bbox,
    )


def _layer_bbox(conn, item: DataItem, size_bytes: int | None):
    """Layer extent in EPSG:4326, or None when it can't be had cheaply.

    Uses the planner's statistics (ST_EstimatedExtent)  -  instant on a table of
    any size. Only a small table with no statistics yet falls back to an exact
    ST_Extent; a large one is never scanned just for a bounding box.
    """

    def _read(extent_sql: str, params: dict):
        if item.srid and item.srid > 0:
            extent_sql = f"ST_Transform(ST_SetSRID({extent_sql}, {int(item.srid)}), 4326)"
        try:
            found = conn.execute(
                text(
                    "SELECT ST_XMin(ext) AS xmin, ST_YMin(ext) AS ymin, "
                    f"ST_XMax(ext) AS xmax, ST_YMax(ext) AS ymax FROM (SELECT {extent_sql} AS ext) AS e"
                ),
                params,
            ).fetchone()
        except DBAPIError as exc:
            if exc.connection_invalidated:
                raise
            conn.rollback()
            return None
        if found and found.xmin is not None:
            return (found.xmin, found.ymin, found.xmax, found.ymax)
        return None

    bbox = _read(
        "ST_EstimatedExtent(:s, :t, :g)::geometry",
        {"s": item.schema, "t": item.name, "g": item.geometry_column},
    )
    if bbox is None and size_bytes is not None and size_bytes <= _EXACT_EXTENT_MAX_BYTES:
        bbox = _read(f"(SELECT ST_Extent({_q(item.geometry_column)})::geometry FROM {_qualified(item)})", {})
    return bbox


_SAMPLE_SEEDS = tuple(range(719, 729))
FULL_ID_DEFAULT_ROW_GATE = 1_000_000


def sampling_plan(reltuples, n_live_tup):
    import math
    for basis, value in (("reltuples", reltuples), ("n_live_tup", n_live_tup)):
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0:
            return {"method": "complete" if value <= 3000 else "multi_seed_system", "basis": basis,
                    "estimated_rows": value, "percent": None if value <= 3000 else min(50.0, 100.0*1500/value)}
    return {"method": "bounded_tid", "basis": "no usable row estimate", "estimated_rows": None,
            "percent": None, "page_budget": 40, "address_budget": 10000, "row_budget": 2000}


def _row_estimate(conn, item):
    return conn.execute(text("""
        SELECT c.reltuples, st.n_live_tup, pg_relation_size(c.oid) AS bytes,
               current_setting('block_size')::int AS block_size, c.relkind, am.amname
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        LEFT JOIN pg_stat_user_tables st ON st.relid=c.oid
        LEFT JOIN pg_am am ON am.oid=c.relam
        WHERE n.nspname=:s AND c.relname=:n
    """), {"s": item.schema, "n": item.name}).mappings().one()


def _tid_plan_safe(plan):
    nodes = []
    def visit(node):
        nodes.append(node.get("Node Type", ""))
        for child in node.get("Plans", []): visit(child)
    visit(plan)
    return "Tid Scan" in nodes and all(n in {"Limit", "Tid Scan", "Result"} for n in nodes)


def _guarded_rows(conn, item, select_parts, *, read_rows=None):
    import math
    qualified = '"' + item.schema.replace('"', '""') + '"."' + item.name.replace('"', '""') + '"'
    fields = ', '.join(select_parts)
    read_rows = read_rows or (lambda statement, params=None: conn.execute(statement, params or {}).mappings().all())
    meta = _row_estimate(conn, item)
    if meta["relkind"] != "r" or meta["amname"] != "heap":
        raise ConnectorError("Guarded sampling requires a heap table; no full-scan fallback was attempted.")
    plan = sampling_plan(meta["reltuples"], meta["n_live_tup"])
    details = {**plan, "seed_vector": [], "budget_limited": False}
    if plan["method"] == "complete":
        rows = read_rows(text(f"SELECT {fields} FROM {qualified} LIMIT 4001"))
        complete = len(rows) <= 4000
        details["budget_limited"] = not complete
        rows = rows[:4000]
        if not complete: details["method"] = "small_estimate_budget_limited"
    elif plan["method"] == "multi_seed_system":
        params = {"percent": plan["percent"]/10}
        draws = []
        for i, seed in enumerate(_SAMPLE_SEEDS):
            params[f"seed{i}"] = seed
            draws.append(f"(SELECT {i} AS __tarsier_sample_draw, {fields}, ctid::text AS __tarsier_sample_tid, tableoid AS __tarsier_sample_oid FROM {qualified} TABLESAMPLE SYSTEM (:percent) REPEATABLE (:seed{i}) LIMIT 401)")
        drawn = read_rows(text(' UNION ALL '.join(draws)), params)
        # Each draw is bounded before client acquisition. Deduplicate identities,
        # not row values: identical source rows remain distinct observations.
        identities = {}
        for row in drawn:
            identities.setdefault((row["__tarsier_sample_oid"], row["__tarsier_sample_tid"]), row)
        details["seed_vector"] = list(_SAMPLE_SEEDS)
        details["drawn_rows"] = len(drawn)
        from collections import Counter
        draw_counts = Counter(row["__tarsier_sample_draw"] for row in drawn)
        details["budget_limited"] = len(identities) > 4000 or any(n >= 401 for n in draw_counts.values())
        rows = [{k:v for k,v in row.items() if k not in {"__tarsier_sample_tid", "__tarsier_sample_oid", "__tarsier_sample_draw"}} for row in list(identities.values())[:4000]]
        complete = False
    else:
        pages = math.ceil(meta["bytes"]/meta["block_size"])
        if pages == 0:
            rows = []
        else:
            blocks = sorted({min(pages-1, int((i+.5)*pages/min(40,pages))) for i in range(min(40,pages))})
            addresses = [f"({block},{offset})" for block in blocks for offset in range(1,251)][:10000]
            statement = text(f"SELECT {fields} FROM {qualified} WHERE ctid=ANY(CAST(:addresses AS tid[])) LIMIT 2000")
            params = {"addresses": addresses}
            conn.execute(text("SET LOCAL enable_seqscan=off"))
            actual_plan = conn.execute(text("EXPLAIN (FORMAT JSON) " + statement.text), params).scalar_one()[0]["Plan"]
            if not _tid_plan_safe(actual_plan):
                raise ConnectorError("Bounded sample requires a direct TID access plan; no sequential-scan fallback was attempted.")
            rows = read_rows(statement, params)
            details["pages_addressed"] = len(blocks)
            details["tuple_addresses"] = len(addresses)
        details["budget_limited"] = len(rows) == 2000
        complete = False
    details.update(row_count=len(rows), complete=complete)
    return rows, not complete, details


@timed_phase("fetch", observe_rows=True)
def sample_rows(config: PostgisConnectionConfig, item: DataItem, limit: int = 1000, *, distinct_column: str | None = None) -> SampleResult:
    """PRD §7.2's statistics engine needs actual data, not just metadata.
    Fetches `limit` rows (plus one, to detect whether this is a sample
    without a separate COUNT)  -  TAD §8: never a full table scan just to
    show statistics. The geometry column itself is never selected; only
    its centroid (for spatial-outlier detection) and a null flag.
    """
    engine = _build_engine(config, statement_timeout_ms=5000) if limit == 1000 and distinct_column is None else _build_engine(config)
    try:
        with engine.connect() as conn:
            columns = conn.execute(
                text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = :s AND table_name = :n AND column_name != COALESCE(:geom, '')"
                ),
                {"s": item.schema, "n": item.name, "geom": item.geometry_column},
            ).fetchall()
            column_names = [row.column_name for row in columns]
            integer_columns = [row.column_name for row in columns if getattr(row, "data_type", "").upper() in {"SMALLINT", "INTEGER", "BIGINT", "TINYINT"}]
            if distinct_column is not None:
                if distinct_column not in column_names:
                    raise ConnectorError("Pick a column from this table.")
                column = '"' + distinct_column.replace('"', '""') + '"'
                qualified = '"' + item.schema.replace('"', '""') + '"."' + item.name.replace('"', '""') + '"'
                expression = f"{column}::jsonb" if any(row.column_name == distinct_column and getattr(row, "data_type", None) == "json" for row in columns) else column
                rows = conn.execute(text(f"SELECT DISTINCT {expression} AS {column} FROM {qualified} WHERE {column} IS NOT NULL LIMIT :lim"), {"lim": limit + 1}).mappings().all()
                return SampleResult(sample_frame(rows[:limit], columns=[distinct_column], integer_columns=integer_columns), len(rows) > limit)

            select_parts = ['"' + c.replace('"', '""') + '"' for c in column_names]
            geometry_columns = null_geometry_column = None
            if item.kind == "vector" and item.geometry_column:
                geom_col = '"' + item.geometry_column.replace('"', '""') + '"'
                centroid = f"ST_Centroid(ST_Transform({geom_col}, 4326))" if item.srid and item.srid > 0 else None
                select_parts += [
                    f"ST_X({centroid}) AS __cx" if centroid else "NULL::double precision AS __cx",
                    f"ST_Y({centroid}) AS __cy" if centroid else "NULL::double precision AS __cy",
                    f"({geom_col} IS NULL) AS __geom_null",
                ]
                geometry_columns = ("__cx", "__cy")
                null_geometry_column = "__geom_null"

            qualified = _qualified(item)
            details = {}
            if limit == 1000:
                rows, guarded_is_sample, details = _guarded_rows(conn, item, select_parts)
            else:
                rows = conn.execute(
                    text(f"SELECT {', '.join(select_parts)} FROM {qualified} LIMIT :lim"),
                    {"lim": limit + 1},
                ).mappings().all()
    except DBAPIError as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()

    is_sample = guarded_is_sample if limit == 1000 else len(rows) > limit
    df = sample_frame(rows if limit == 1000 else rows[:limit], integer_columns=integer_columns)
    if not details:
        details = {"method": "first_rows" if is_sample else "complete", "seed_vector": [], "row_count": len(df), "complete": not is_sample}
    return SampleResult(
        dataframe=df, is_sample=is_sample,
        geometry_columns=geometry_columns, null_geometry_column=null_geometry_column, details=details,
    )


@timed_phase("fetch", observe_rows=True)
def sample_geometries(config: PostgisConnectionConfig, item: DataItem, limit: int = 1000) -> GeometrySample:
    if item.kind != "vector" or not item.geometry_column:
        raise ConnectorError("Geometry quality checks need a vector layer.")
    engine = _build_engine(config, statement_timeout_ms=5000) if limit == 1000 else _build_engine(config)
    try:
        with engine.connect() as conn:
            columns = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = :s AND table_name = :n AND column_name != COALESCE(:geom, '')"
                ),
                {"s": item.schema, "n": item.name, "geom": item.geometry_column},
            ).fetchall()
            column_names = [row.column_name for row in columns]
            select_parts = ['"' + c.replace('"', '""') + '"' for c in column_names]
            geom_col = '"' + item.geometry_column.replace('"', '""') + '"'
            select_parts.append(f"ST_AsBinary({geom_col}) AS __wkb")
            reference = conn.execute(text("SELECT srtext FROM spatial_ref_sys WHERE srid = :srid"), {"srid": item.srid}).first() if item.srid else None
            qualified = _qualified(item)
            details = {}
            if limit == 1000:
                rows, guarded_is_sample, details = _guarded_rows(conn, item, select_parts)
            else:
                rows = conn.execute(
                    text(f"SELECT {', '.join(select_parts)} FROM {qualified} LIMIT :lim"),
                    {"lim": limit + 1},
                ).mappings().all()
    except DBAPIError as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()
    is_sample = guarded_is_sample if limit == 1000 else len(rows) > limit
    gdf = geodataframe_from_wkb_rows(rows if limit == 1000 else rows[:limit], item.srid, crs=reference.srtext if reference else None)
    if not details:
        details = {"method": "first_rows" if is_sample else "complete", "seed_vector": [], "row_count": len(gdf), "complete": not is_sample}
    return GeometrySample(geodataframe=gdf, is_sample=is_sample, details=details)


@timed_phase("fetch", observe_rows=True)
def sample_id_values(config: PostgisConnectionConfig, item: DataItem, *, full: bool = False) -> IdColumnSample | None:
    engine = _build_engine(config, statement_timeout_ms=5000)
    try:
        with engine.connect() as conn:
            columns = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = :s AND table_name = :n AND column_name != COALESCE(:geom, '')"
                ),
                {"s": item.schema, "n": item.name, "geom": item.geometry_column},
            ).fetchall()
            column = find_id_column([row.column_name for row in columns])
            if column is None:
                return None
            if not full:
                meta = _row_estimate(conn, item)
                plan = sampling_plan(meta["reltuples"], meta["n_live_tup"])
                if plan["estimated_rows"] is None or plan["estimated_rows"] > FULL_ID_DEFAULT_ROW_GATE:
                    raise ConnectorError(f"Full-ID completeness requires an explicit full check above {FULL_ID_DEFAULT_ROW_GATE:,} estimated rows or when size is unknown.")
            qualified = _qualified(item)
            rows = conn.execute(text(f"SELECT {_q(column)} FROM {qualified}")).fetchall()
    except DBAPIError as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()
    return IdColumnSample(column=column, values=pd.Series([row[0] for row in rows], name=column))


_RASTER_SAMPLE_PERCENT = 10  # of tiles, via TABLESAMPLE, only when a raster has many tiles
_RASTER_SAMPLE_MIN_TILES = 100
_RASTER_HISTOGRAM_BINS = 32
_RASTER_STATEMENT_TIMEOUT_MS = 30_000


@timed_phase("fetch")
def raster_detail(config: PostgisConnectionConfig, item: DataItem, *, full: bool = False):
    """PRD §8 fields for a raster stored in PostGIS (postgis_raster).

    Read-only catalog + statistics queries. A tiled raster with many tiles
    is summarised from a fixed sample of its tiles (TABLESAMPLE ... REPEATABLE,
    so every query in one run sees the same tiles) unless `full=True`
    (TAD §8). Metadata the database doesn't hold (acquisition date, sensor,
    cloud cover) stays None -> "Not available". The histogram re-bins each
    tile's own 64-bin histogram into global bins, so it is approximate for
    multi-tile rasters (exact for single-tile ones).
    """
    from tarsier.raster.analyze import BandStats, HistogramBin, RasterDetail

    engine = _build_engine(config, statement_timeout_ms=_RASTER_STATEMENT_TIMEOUT_MS)
    try:
        with engine.connect() as conn:
            meta = conn.execute(
                text(
                    "SELECT r_raster_column, srid, scale_x, scale_y, num_bands, pixel_types, "
                    "nodata_values, ST_XMin(extent) AS xmin, ST_YMin(extent) AS ymin, "
                    "ST_XMax(extent) AS xmax, ST_YMax(extent) AS ymax "
                    "FROM raster_columns WHERE r_table_schema = :s AND r_table_name = :n"
                ),
                {"s": item.schema, "n": item.name},
            ).first()
            if meta is None:
                raise ConnectorError(f"{item.name!r} is not listed in raster_columns.")

            qualified = '"{}"."{}"'.format(item.schema.replace('"', '""'), item.name.replace('"', '""'))
            column = '"{}"'.format(meta.r_raster_column.replace('"', '""'))
            band_count = meta.num_bands or 0
            width = height = None
            if meta.xmin is not None and meta.scale_x and meta.scale_y:
                width = round((meta.xmax - meta.xmin) / abs(meta.scale_x))
                height = round((meta.ymax - meta.ymin) / abs(meta.scale_y))

            tile_estimate = conn.execute(
                text("SELECT reltuples::bigint FROM pg_class WHERE oid = to_regclass(:q)"), {"q": qualified}
            ).scalar()
            sampled = (not full) and (tile_estimate or 0) > _RASTER_SAMPLE_MIN_TILES
            source = f"{qualified} TABLESAMPLE SYSTEM ({_RASTER_SAMPLE_PERCENT}) REPEATABLE (42)" if sampled else qualified

            pixel_types = list(meta.pixel_types or [])
            nodata_values = list(meta.nodata_values or [])
            bands = []
            for index in range(1, band_count + 1):
                stats = conn.execute(
                    text(
                        f"SELECT (s).count AS cnt, (s).mean AS mean, (s).stddev AS stddev, "
                        f"(s).min AS min, (s).max AS max, tot FROM ("
                        f"SELECT ST_SummaryStatsAgg({column}, {index}, true, 1) AS s, "
                        f"SUM(ST_Width({column})::bigint * ST_Height({column})) AS tot FROM {source}) t"
                    )
                ).first()
                valid = int(stats.cnt) if stats is not None and stats.cnt else 0
                total = int(stats.tot) if stats is not None and stats.tot else 0
                histogram = []
                if valid and stats.min is not None and stats.max is not None:
                    low, high = float(stats.min), float(stats.max)
                    if low == high:
                        histogram = [HistogramBin(low, high, valid)]
                    else:
                        rows = conn.execute(
                            text(
                                f"WITH h AS (SELECT (ST_Histogram({column}, {index}, true, 64)).* FROM {source}) "
                                f"SELECT LEAST(width_bucket((min + max) / 2, :lo, :hi, {_RASTER_HISTOGRAM_BINS}), "
                                f"{_RASTER_HISTOGRAM_BINS}) AS bucket, SUM(count)::bigint AS cnt FROM h GROUP BY 1"
                            ),
                            {"lo": low, "hi": high},
                        ).fetchall()
                        step = (high - low) / _RASTER_HISTOGRAM_BINS
                        counts = {int(r.bucket): int(r.cnt) for r in rows}
                        histogram = [
                            HistogramBin(low + step * i, low + step * (i + 1), counts.get(i + 1, 0))
                            for i in range(_RASTER_HISTOGRAM_BINS)
                        ]
                bands.append(
                    BandStats(
                        index=index,
                        name=f"Band {index}",
                        dtype=pixel_types[index - 1] if index <= len(pixel_types) else None,
                        nodata=nodata_values[index - 1] if index <= len(nodata_values) else None,
                        minimum=float(stats.min) if valid else None,
                        maximum=float(stats.max) if valid else None,
                        average=float(stats.mean) if valid else None,
                        spread=float(stats.stddev) if valid and stats.stddev is not None else None,
                        nodata_percent=round(100.0 * (total - valid) / total, 4) if total else None,
                        valid_pixel_count=valid,
                        histogram=histogram,
                    )
                )
    except (OperationalError, ProgrammingError) as exc:
        raise ConnectorError(
            f"Could not read raster statistics for {item.name!r}: {str(exc.orig).splitlines()[0]}"
        ) from exc
    finally:
        engine.dispose()

    return RasterDetail(
        width=width,
        height=height,
        band_count=band_count,
        pixel_size_x=float(meta.scale_x) if meta.scale_x is not None else None,
        pixel_size_y=abs(float(meta.scale_y)) if meta.scale_y is not None else None,
        crs=f"EPSG:{meta.srid}" if meta.srid else None,
        srid=meta.srid or None,
        footprint=(meta.xmin, meta.ymin, meta.xmax, meta.ymax) if meta.xmin is not None else None,
        dtype=pixel_types[0] if pixel_types else None,
        nodata=nodata_values[0] if nodata_values else None,
        has_overviews=None,
        is_sample=sampled,
        sample_note=f"Based on a sample (about {_RASTER_SAMPLE_PERCENT}% of tiles)" if sampled else None,
        bands=bands,
    )


_INTEGER_TYPES = {"smallint": 32767, "integer": 2147483647, "bigint": 9223372036854775807}
_TEXT_TYPES = {"text", "character varying", "character"}


@timed_phase("fetch")
def column_guess_metadata(config, item):
    """Catalog cardinality estimates, never an unbounded COUNT DISTINCT."""
    import math
    engine = _build_engine(config, statement_timeout_ms=5000)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT a.attname AS name, format_type(a.atttypid,NULL) AS type,
                       s.n_distinct, c.reltuples, st.n_live_tup
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
                LEFT JOIN pg_stats s ON s.schemaname=n.nspname AND s.tablename=c.relname AND s.attname=a.attname
                LEFT JOIN pg_stat_user_tables st ON st.relid=c.oid
                WHERE n.nspname=:s AND c.relname=:n
            """), {"s": item.schema, "n": item.name}).mappings().all()
        result = {}
        for row in rows:
            nd, count = row["n_distinct"], row["reltuples"]
            if count is None or count <= 0:
                count = row["n_live_tup"]
            estimate = None
            if nd is not None and math.isfinite(nd) and nd != 0:
                estimate = nd if nd > 0 else -nd * count if count and count > 0 else None
            result[row["name"]] = {"type": row["type"], "estimate": estimate, "row_estimate": count}
        return result
    except DBAPIError as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()


@timed_phase("fetch")
def probe_column_values(config, item, column, values, source_type=None):
    """Option A: return True/False, or None for a five-second lookup timeout."""
    from numbers import Integral
    metadata = column_guess_metadata(config, item)
    if column not in metadata:
        raise ConnectorError("Pick a column from this table.")
    target_type = metadata[column]["type"]
    field = '"' + column.replace('"', '""') + '"'
    qualified = '"' + item.schema.replace('"', '""') + '"."' + item.name.replace('"', '""') + '"'
    source_integer = source_type in _INTEGER_TYPES or (bool(values) and all(isinstance(v, Integral) and not isinstance(v, bool) for v in values))
    source_text = source_type in _TEXT_TYPES or (bool(values) and all(isinstance(v, str) for v in values))
    mixed = (source_text and target_type in _INTEGER_TYPES) or (source_integer and target_type in _TEXT_TYPES)
    if source_text and target_type not in _TEXT_TYPES and target_type not in _INTEGER_TYPES:
        return False
    if target_type in _TEXT_TYPES and not source_text and not source_integer:
        return False
    params = {}
    if mixed:
        normalized = {str(v).strip() for v in values if str(v).strip() and all('0' <= c <= '9' for c in str(v).strip())}
        denominator = len(normalized)
        if target_type in _INTEGER_TYPES:
            bound = _INTEGER_TYPES[target_type]
            selected = [int(v) for v in normalized if len(v) <= 19 and str(int(v)) == v and int(v) <= bound]
        else:
            selected = list(normalized)
            # Match Python str.strip, including non-ASCII whitespace; never strip zeros.
            params["whitespace"] = ''.join(chr(i) for i in range(0x110000) if chr(i).isspace())
            field = f"btrim({field}::text, :whitespace)"
    else:
        selected = list(values)
        denominator = len(values)
    if denominator < 5:
        return False
    if not selected:
        return False
    from sqlalchemy import bindparam
    statement = text(f"SELECT count(DISTINCT {field}) FROM {qualified} WHERE {field} IN :values").bindparams(bindparam("values", expanding=True))
    params["values"] = selected
    engine = _build_engine(config, statement_timeout_ms=5000)
    try:
        with engine.connect() as conn:
            matched = conn.execute(statement, params).scalar_one()
        return matched / denominator >= .8
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) == "57014" or getattr(exc.orig, "pgcode", None) == "57014":
            from tarsier.timing import record_timeout
            record_timeout()
            return None
        if isinstance(exc, OperationalError):
            raise _clean_connection_error(config, exc) from exc
        raise ConnectorError("Could not verify the candidate column types.") from exc
    finally:
        engine.dispose()
