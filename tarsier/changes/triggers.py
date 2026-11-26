"""Optional PostGIS history-log install (TAD §6.2  -  the one allowed write)."""

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from tarsier.connectors.base import ConnectorError
from tarsier.connectors.postgis import PostgisConnectionConfig, _clean_connection_error

POSTGIS_OWNED = """EXISTS (
    SELECT 1 FROM pg_catalog.pg_depend d
    JOIN pg_catalog.pg_extension e ON e.oid=d.refobjid
    WHERE d.classid='pg_catalog.pg_class'::pg_catalog.regclass AND d.objid=c.oid
      AND d.refclassid='pg_catalog.pg_extension'::pg_catalog.regclass AND d.deptype='e'
      AND e.extname IN ('postgis','postgis_raster','postgis_topology')
)"""

TRACKABLE = """c.relkind IN ('r','p') AND n.nspname NOT IN
    ('pg_catalog','information_schema','pg_toast','topology','tiger','tiger_data','tarsier_changes')
    AND n.nspname NOT LIKE 'pg_temp_%' AND n.nspname NOT LIKE 'pg_toast_temp_%'
    AND NOT """ + POSTGIS_OWNED

# Catch only the private logging block, never the user's DML/DDL.
# Categories 22/23/53/54 and explicit infrastructure/log-schema errors; not 40 or 57.
LOGGING_FAILURE_HANDLER = """
    EXCEPTION WHEN data_exception OR integrity_constraint_violation OR insufficient_resources OR program_limit_exceeded OR SQLSTATE '3F000' OR SQLSTATE '42501' OR SQLSTATE '42P01' OR SQLSTATE '42703' OR SQLSTATE '42704' OR SQLSTATE '42804' OR SQLSTATE '42809' OR SQLSTATE '55000' OR SQLSTATE '55P03' OR SQLSTATE '58030' OR SQLSTATE 'P0001' THEN
        RAISE WARNING 'Tarsier history log could not save a change (SQLSTATE %). Tracking may have gaps.', SQLSTATE;
        BEGIN
            PERFORM pg_catalog.nextval('tarsier_changes.tracking_failures'::pg_catalog.regclass);
        EXCEPTION WHEN data_exception OR integrity_constraint_violation OR insufficient_resources OR program_limit_exceeded OR SQLSTATE '3F000' OR SQLSTATE '42501' OR SQLSTATE '42P01' OR SQLSTATE '42703' OR SQLSTATE '42704' OR SQLSTATE '42804' OR SQLSTATE '42809' OR SQLSTATE '55000' OR SQLSTATE '55P03' OR SQLSTATE '58030' OR SQLSTATE 'P0001' THEN
            RAISE WARNING 'Tarsier tracking-gap marker is unavailable (SQLSTATE %). Tracking completeness is unknown.', SQLSTATE;
        END;
"""

ROW_LOGGER = """
CREATE OR REPLACE FUNCTION tarsier_changes.row_logger()
RETURNS pg_catalog.trigger
SECURITY DEFINER
SET search_path = pg_catalog, tarsier_changes
AS $$
DECLARE
    rec pg_catalog.jsonb;
    fid pg_catalog.text;
    pk pg_catalog.text;
BEGIN
    BEGIN
    IF TG_OP = 'DELETE' THEN
        rec := pg_catalog.to_jsonb(OLD);
    ELSE
        rec := pg_catalog.to_jsonb(NEW);
    END IF;
    SELECT a.attname INTO pk
      FROM pg_catalog.pg_constraint k
      JOIN pg_catalog.pg_attribute a ON a.attrelid=k.conrelid AND a.attnum=k.conkey[1]
     WHERE k.conrelid=TG_RELID AND k.contype='p' AND pg_catalog.cardinality(k.conkey)=1;
    fid := COALESCE(rec->>pk, rec->>'id', rec->>'objectid', rec->>'gid', rec->>'fid', rec->>'ogc_fid');
    INSERT INTO tarsier_changes.change_log (
        occurred_at, db_user, action, schema_name, table_name, feature_id, before_json, after_json, txid
    ) VALUES (
        pg_catalog.clock_timestamp(),
        session_user,
        pg_catalog.lower(TG_OP),
        TG_TABLE_SCHEMA,
        TG_TABLE_NAME,
        fid,
        CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN pg_catalog.to_jsonb(OLD) END,
        CASE WHEN TG_OP IN ('UPDATE', 'INSERT') THEN pg_catalog.to_jsonb(NEW) END,
        pg_catalog.txid_current()
    );
""" + LOGGING_FAILURE_HANDLER + """
    END;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

DDL_LOGGER = """
CREATE OR REPLACE FUNCTION tarsier_changes.ddl_logger()
RETURNS pg_catalog.event_trigger
SECURITY DEFINER
SET search_path = pg_catalog, tarsier_changes
AS $$
DECLARE
    r pg_catalog.record;
BEGIN
    FOR r IN SELECT * FROM pg_catalog.pg_event_trigger_ddl_commands() LOOP
        BEGIN
        INSERT INTO tarsier_changes.change_log (
            occurred_at, db_user, action, schema_name, table_name, feature_id, before_json, after_json, txid
        ) VALUES (
            pg_catalog.clock_timestamp(),
            session_user,
            'schema',
            COALESCE(r.schema_name, ''),
            COALESCE(r.object_identity, ''),
            NULL,
            NULL,
            pg_catalog.jsonb_build_object('command_tag', r.command_tag, 'object_identity', r.object_identity),
            pg_catalog.txid_current()
        );
""" + LOGGING_FAILURE_HANDLER + """
        END;
    END LOOP;
END;
$$ LANGUAGE plpgsql
"""


def _write_engine(config: PostgisConnectionConfig):
    import sqlalchemy

    return sqlalchemy.create_engine(
        config.url(),
        # Installing triggers acquires locks on every table. Bound both the
        # lock wait and each DDL statement so Test & Save cannot wait forever.
        connect_args={
            "connect_timeout": 5,
            "options": "-c lock_timeout=5000 -c statement_timeout=15000",
        },
        pool_pre_ping=True,
    )


def _secure_loggers(conn) -> None:
    # Static SQL only. No caller SQL, role names or table identifiers are interpolated.
    conn.execute(text("REVOKE ALL ON SCHEMA tarsier_changes FROM PUBLIC"))
    conn.execute(text("CREATE SEQUENCE IF NOT EXISTS tarsier_changes.tracking_failures"))
    conn.execute(text("ALTER SEQUENCE tarsier_changes.tracking_failures OWNER TO CURRENT_USER"))
    conn.execute(text("REVOKE ALL ON SEQUENCE tarsier_changes.tracking_failures FROM PUBLIC"))
    conn.execute(text(ROW_LOGGER))
    conn.execute(text(DDL_LOGGER))
    conn.execute(text("ALTER FUNCTION tarsier_changes.row_logger() OWNER TO CURRENT_USER"))
    conn.execute(text("ALTER FUNCTION tarsier_changes.ddl_logger() OWNER TO CURRENT_USER"))
    conn.execute(text("REVOKE ALL ON TABLE tarsier_changes.change_log FROM PUBLIC"))
    conn.execute(text("REVOKE ALL ON SEQUENCE tarsier_changes.change_log_id_seq FROM PUBLIC"))


def upgrade_triggers(config: PostgisConnectionConfig) -> None:
    """Upgrade an existing history installation without touching source tables."""
    engine = _write_engine(config)
    try:
        with engine.begin() as conn:
            _secure_loggers(conn)
            _remove_excluded_triggers(conn)
    except OperationalError as exc:
        raise _clean_connection_error(config, exc) from exc
    except Exception as exc:
        raise ConnectorError(
            "Could not upgrade the history log. Allow the upgrade using its owner "
            "or an administrator; source tables and triggers were not reinstalled."
        ) from exc
    finally:
        engine.dispose()


def _remove_excluded_triggers(conn) -> None:
    # Remove only the exact trigger installed by Tarsier on extension members.
    rows = conn.execute(text("""
        SELECT n.nspname,c.relname FROM pg_catalog.pg_trigger t
        JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE t.tgname='tarsier_row_logger'
          AND t.tgfoid='tarsier_changes.row_logger()'::pg_catalog.regprocedure
          AND """ + POSTGIS_OWNED)).all()
    quote = conn.dialect.identifier_preparer.quote_identifier
    for schema, name in rows:
        conn.execute(text(f'DROP TRIGGER tarsier_row_logger ON {quote(schema)}.{quote(name)}'))


def install_triggers(config: PostgisConnectionConfig) -> None:
    engine = _write_engine(config)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS tarsier_changes"))
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS tarsier_changes.change_log (
                        id BIGSERIAL PRIMARY KEY,
                        occurred_at TIMESTAMPTZ NOT NULL,
                        db_user TEXT,
                        action TEXT NOT NULL,
                        schema_name TEXT NOT NULL,
                        table_name TEXT NOT NULL,
                        feature_id TEXT,
                        before_json JSONB,
                        after_json JSONB,
                        txid BIGINT
                    )
                    """
                )
            )
            _secure_loggers(conn)
            conn.execute(text("DROP EVENT TRIGGER IF EXISTS tarsier_ddl_logger"))
            conn.execute(
                text(
                    """
                    CREATE EVENT TRIGGER tarsier_ddl_logger ON ddl_command_end
                    WHEN TAG IN ('ALTER TABLE', 'CREATE TABLE', 'DROP TABLE')
                    EXECUTE PROCEDURE tarsier_changes.ddl_logger()
                    """
                )
            )
            tables = conn.execute(
                text(
                    """
                    SELECT n.nspname,c.relname FROM pg_catalog.pg_class c
                    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE
                    """ + TRACKABLE
                )
            ).fetchall()
            for schema, name in tables:
                quote = conn.dialect.identifier_preparer.quote_identifier
                qualified = f'{quote(schema)}.{quote(name)}'
                conn.execute(text(f"DROP TRIGGER IF EXISTS tarsier_row_logger ON {qualified}"))
                conn.execute(
                    text(
                        f"CREATE TRIGGER tarsier_row_logger "
                        f"AFTER INSERT OR UPDATE OR DELETE ON {qualified} "
                        f"FOR EACH ROW EXECUTE PROCEDURE tarsier_changes.row_logger()"
                    )
                )
    except OperationalError as exc:
        raise _clean_connection_error(config, exc) from exc
    except ConnectorError:
        raise
    except Exception as exc:
        raise ConnectorError(
            "Could not install the history log. Tarsier needs permission to create a schema "
            "and triggers in this database  -  you can skip this and use polling instead."
        ) from exc
    finally:
        engine.dispose()


def triggers_installed(config: PostgisConnectionConfig) -> bool:
    from tarsier.connectors.postgis import _build_engine

    engine = _build_engine(config)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT 1 FROM information_schema.schemata WHERE schema_name = 'tarsier_changes'")
            ).fetchone()
            return row is not None
    except OperationalError:
        return False
    finally:
        engine.dispose()


def tracking_health(config: PostgisConnectionConfig) -> dict:
    """Read-only, conservative health; failure counts can outlive rolled-back edits."""
    from sqlalchemy.exc import SQLAlchemyError
    from tarsier.connectors.postgis import _build_engine

    health = {"status": "unavailable", "possible_gaps": True,
              "logging_failures": None, "logger_version": "unknown",
              "missing_trigger_count": None,
              "message": "Tracking completeness could not be verified."}
    engine = _build_engine(config)
    try:
        with engine.connect() as conn:
            functions = conn.execute(text(
                "SELECT p.proname,p.prosrc,p.prosecdef,p.proconfig FROM pg_proc p "
                "JOIN pg_namespace n ON n.oid=p.pronamespace "
                "WHERE n.nspname='tarsier_changes' AND p.proname IN ('row_logger','ddl_logger')"
            )).mappings().all()
            expected = {"row_logger": ROW_LOGGER, "ddl_logger": DDL_LOGGER}
            current = len(functions) == 2 and all(
                r["prosecdef"] and r["proconfig"] == ["search_path=pg_catalog, tarsier_changes"]
                and r["prosrc"].strip() == expected[r["proname"]].split("AS $$",1)[1].split("$$ LANGUAGE",1)[0].strip()
                for r in functions)
            health["logger_version"] = "fail_open_v1" if current else "legacy_or_modified"
            conn.execute(text("SELECT 1 FROM tarsier_changes.change_log LIMIT 0"))
            failures = conn.execute(text("SELECT last_value,is_called FROM tarsier_changes.tracking_failures")).mappings().one()
            health["logging_failures"] = int(failures["last_value"]) if failures["is_called"] else 0
            missing = conn.execute(text("""
                SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE """ + TRACKABLE + """
                  AND NOT EXISTS (SELECT 1 FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid
                    JOIN pg_namespace pn ON pn.oid=p.pronamespace
                    WHERE t.tgrelid=c.oid AND t.tgname='tarsier_row_logger'
                      AND t.tgenabled IN ('O','A') AND pn.nspname='tarsier_changes' AND p.proname='row_logger')
            """)).scalar_one()
            health["missing_trigger_count"] = int(missing)
            health["possible_gaps"] = bool(not current or missing or health["logging_failures"])
            health["status"] = "degraded" if health["possible_gaps"] else "healthy"
            health["message"] = "Tracking may have gaps; review the history log." if health["possible_gaps"] else "History log and triggers are reachable."
    except SQLAlchemyError:
        # Never claim completeness from an unreadable log/marker; no SQL or secret in API errors.
        pass
    finally:
        engine.dispose()
    return health
