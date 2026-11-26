"""Pull trigger log or poll fingerprints into Tarsier's SQLite store."""

from tarsier.timing import timed_run, timed_phase
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError

from tarsier.changes.engine import diff_fingerprints
from tarsier.changes.triggers import install_triggers, triggers_installed, upgrade_triggers
from tarsier.connectors.base import ConnectorError
from tarsier.connectors.registry import get_connector
from tarsier.limits import CHANGE_SYNC_BATCH, CHANGE_SYNC_MAX_PER_RUN, POLLING_MAX_ROWS
from tarsier.storage import change_log, item_cache
from tarsier.storage import connections as connection_storage
from tarsier.storage import settings as settings_store

_POLL_SKIPPED_KEY = "polling_skipped:"


def _postgis_config(connection_id: str):
    saved = connection_storage.get_connection(connection_id)
    if saved is None:
        raise ValueError(f"No such connection: {connection_id!r}")
    if saved.type != "postgis":
        raise ConnectorError("Change capture is only built for PostGIS in this phase.")
    password = connection_storage.get_connection_password(connection_id)
    connector = get_connector(saved.type)
    return saved, connector, connector.build_config(saved.config, password)


def enable_triggers(connection_id: str) -> None:
    _, _, config = _postgis_config(connection_id)
    if triggers_installed(config):
        upgrade_triggers(config)
    else:
        install_triggers(config)
    change_log.set_mode(connection_id, "triggers")
    # Re-read saved images after an explicitly allowed logger upgrade, including
    # older events whose feature ID was omitted by the conventional-name logger.
    change_log.record_sync(connection_id, 0)


def enable_polling(connection_id: str) -> None:
    _postgis_config(connection_id)
    change_log.set_mode(connection_id, "polling")


def tracking_health(connection_id: str) -> dict:
    state = change_log.get_state(connection_id)
    if not state or state.mode == "none":
        return {"status": "not_enabled", "possible_gaps": None}
    if state.mode == "polling":
        message = "Polling compares snapshots; changes between polls can be missed."
        skipped = polling_skipped(connection_id)
        if skipped:
            message += (
                f" {len(skipped)} table(s) are too large or unreadable for polling and are not tracked; "
                "install the history log to track them."
            )
        return {"status": "polling", "possible_gaps": None, "message": message, "skipped_tables": skipped}
    from tarsier.changes.triggers import tracking_health as inspect
    try:
        _, _, config = _postgis_config(connection_id)
        health = inspect(config)
        health["acknowledged_failures"] = state.acknowledged_failures or 0
        health["acknowledged_at"] = _aware(state.acknowledged_at).isoformat() if state.acknowledged_at else None
        total = health.get("logging_failures")
        health["unacknowledged_failures"] = max(0, total - health["acknowledged_failures"]) if total is not None else None
        return health
    except ConnectorError:
        return {"status": "unavailable", "possible_gaps": True,
                "message": "Tracking completeness could not be verified."}


@timed_run("change_sync")
def sync_connection(connection_id: str) -> int:
    saved, connector, config = _postgis_config(connection_id)
    state = change_log.get_state(connection_id)
    mode = state.mode if state else "none"
    if mode == "none":
        if triggers_installed(config):
            change_log.set_mode(connection_id, "triggers")
            mode = "triggers"
        else:
            raise ConnectorError("Change tracking isn't enabled. Install the history log, or use polling.")
    if mode == "triggers":
        # Old SQLite rows lost the source offset. Recover their true instants
        # from the source log once, not by guessing an offset for naive dates.
        cursor = state.last_source_log_id if state and state.utc_cache_version == 1 else 0
        count = _sync_triggers(connection_id, connector, config, cursor)
    else:
        count = _sync_polling(connection_id, connector, config)
    try:
        from tarsier.alerts.evaluate import evaluate_connection

        evaluate_connection(connection_id)
    except Exception:
        pass
    try:
        from tarsier.automation.evaluate import evaluate_connection as evaluate_autos

        evaluate_autos(connection_id)
    except Exception:
        pass
    return count


@timed_phase("fetch")
def _sync_triggers(connection_id, connector, config, last_id: int) -> int:
    from tarsier.connectors.postgis import _build_engine, _clean_connection_error

    # Row counts for the mass-change rule come from Tarsier's own cache. Re-reading
    # every table's metadata from the source on each sync (once a minute) would
    # hammer a large database for a number that barely moves.
    table_counts = {(i.schema, i.name): i.row_count for i in item_cache.list_items(connection_id)}
    cursor = last_id
    total = 0
    engine = _build_engine(config)
    try:
        with engine.connect() as conn:
            primary_keys = dict(((r.schema_name, r.table_name), r.column_name) for r in conn.execute(text("""
                SELECT n.nspname AS schema_name,c.relname AS table_name,a.attname AS column_name
                FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid=k.conrelid
                JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                JOIN pg_catalog.pg_attribute a ON a.attrelid=k.conrelid AND a.attnum=k.conkey[1]
                WHERE k.contype='p' AND pg_catalog.cardinality(k.conkey)=1
            """)).mappings())
            # Pull the log in bounded pages. A bulk load can write millions of
            # rows between two syncs; they are caught up over several runs
            # rather than loaded into memory at once.
            while total < CHANGE_SYNC_MAX_PER_RUN:
                rows = conn.execute(
                    text(
                        "SELECT id, occurred_at, db_user, action, schema_name, table_name, "
                        "feature_id, before_json, after_json, txid "
                        "FROM tarsier_changes.change_log WHERE id > :last ORDER BY id LIMIT :lim"
                    ),
                    {"last": cursor, "lim": CHANGE_SYNC_BATCH},
                ).mappings().all()
                if not rows:
                    break
                payload = []
                for row in rows:
                    feature_id = row["feature_id"]
                    if feature_id is None and row["action"] != "schema":
                        image = row["before_json"] if row["action"] == "delete" else row["after_json"]
                        key = primary_keys.get((row["schema_name"], row["table_name"]))
                        value = (image or {}).get(key)
                        if value is not None:
                            feature_id = str(value)
                    payload.append(
                        {
                            "occurred_at": row["occurred_at"],
                            "db_user": row["db_user"],
                            "action": row["action"],
                            "schema": row["schema_name"],
                            "name": row["table_name"],
                            "feature_id": feature_id,
                            "before": row["before_json"],
                            "after": row["after_json"],
                            "txid": row["txid"],
                            "source": "trigger",
                            "source_log_id": int(row["id"]),
                        }
                    )
                change_log.insert_events(connection_id, payload, table_counts)
                cursor = int(rows[-1]["id"])
                change_log.record_sync(connection_id, cursor)
                total += len(rows)
                if len(rows) < CHANGE_SYNC_BATCH:
                    break
    except ProgrammingError as exc:
        raise ConnectorError("The history log isn't installed on this database, or this user can't read it.") from exc
    except OperationalError as exc:
        raise ConnectorError("The history log isn't installed on this database.") from exc
    except DBAPIError as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()

    change_log.record_sync(connection_id, cursor)
    return total


@timed_phase("fetch")
def _sync_polling(connection_id, connector, config) -> int:
    from tarsier.connectors.postgis import _build_engine, _clean_connection_error, _qualified

    items = [i for i in connector.list_items(config) if i.kind in ("vector", "tabular")]
    engine = _build_engine(config)
    inserted = 0
    now = datetime.now(timezone.utc)
    table_counts = {}
    skipped: list[str] = []
    try:
        with engine.connect() as conn:
            for item in items:
                qualified = _qualified(item)
                # Polling re-reads and fingerprints every row. That is only
                # reasonable for small tables; large ones are skipped and
                # reported, and need the history log instead.
                estimate = conn.execute(
                    text("SELECT reltuples::bigint FROM pg_class WHERE oid = to_regclass(:q)"), {"q": qualified}
                ).scalar()
                if estimate is not None and estimate > POLLING_MAX_ROWS:
                    skipped.append(item.qualified_name)
                    continue
                id_columns = _id_columns(conn, item.schema, item.name, item.geometry_column)
                if not id_columns:
                    continue
                quoted = ['t."'+column.replace('"','""')+'"' for column in id_columns]
                key = f'CAST({quoted[0]} AS TEXT)' if len(quoted)==1 else 'CAST(jsonb_build_array('+','.join(quoted)+') AS TEXT)'
                try:
                    rows = conn.execute(
                        text(f'SELECT {key} AS fid, md5(t::text) AS fp FROM {qualified} AS t LIMIT :lim'),
                        {"lim": POLLING_MAX_ROWS + 1},
                    ).mappings().all()
                except DBAPIError as exc:
                    if exc.connection_invalidated:
                        raise
                    # One unreadable table (no SELECT permission, a lock) must
                    # not stop every other table from being tracked.
                    conn.rollback()
                    skipped.append(item.qualified_name)
                    continue
                if len(rows) > POLLING_MAX_ROWS:
                    skipped.append(item.qualified_name)
                    continue
                current = {str(r["fid"]): r["fp"] for r in rows}
                table_counts[(item.schema, item.name)] = len(current)
                had_baseline = change_log.has_fingerprint_snapshot(connection_id, item.schema, item.name)
                previous = change_log.get_fingerprints(connection_id, item.schema, item.name) if had_baseline else {}
                diffs = diff_fingerprints(previous, current) if had_baseline else []
                payload = [
                    {
                        "occurred_at": now,
                        "db_user": None,
                        "action": d["action"],
                        "schema": item.schema,
                        "name": item.name,
                        "feature_id": d["feature_id"],
                        "before": None,
                        "after": None,
                        "txid": f"poll-{now.isoformat()}",
                        "source": "poll",
                    }
                    for d in diffs
                ]
                if payload:
                    change_log.insert_events(connection_id, payload, table_counts)
                    inserted += len(payload)
                # Nothing changed -> the stored baseline is already correct.
                if payload or not had_baseline:
                    change_log.replace_fingerprints(connection_id, item.schema, item.name, current)
    except DBAPIError as exc:
        raise _clean_connection_error(config, exc) from exc
    finally:
        engine.dispose()
    settings_store._set_value(_POLL_SKIPPED_KEY + connection_id, json.dumps(sorted(skipped)))
    change_log.record_sync(connection_id, 0)
    return inserted


def polling_skipped(connection_id: str) -> list[str]:
    raw = settings_store._get_value(_POLL_SKIPPED_KEY + connection_id)
    return json.loads(raw) if raw else []


def _id_columns(conn, schema, table, geom_col):
    from tarsier.connectors.base import find_id_column

    primary = conn.execute(text("""
        SELECT a.attname FROM pg_constraint k
        JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN LATERAL unnest(k.conkey) WITH ORDINALITY u(att,ord) ON true
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=u.att
        WHERE k.contype='p' AND n.nspname=:s AND c.relname=:n ORDER BY u.ord
    """), {"s":schema,"n":table}).fetchall()
    if primary:
        return [r.attname for r in primary]
    rows = conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = :n AND (CAST(:geom AS text) IS NULL OR column_name != CAST(:geom AS text))"
        ),
        {"s": schema, "n": table, "geom": geom_col},
    ).fetchall()
    conventional = find_id_column([r.column_name for r in rows])
    return [conventional] if conventional else []


def generate_due_report(connection_id: str, *, now: datetime | None = None) -> dict | None:
    state = change_log.get_state(connection_id)
    if state is None or not state.report_interval:
        return None
    now = now or datetime.now(timezone.utc)
    delta = timedelta(days=1) if state.report_interval == "daily" else timedelta(days=7)
    if state.last_report_at and (now - _aware(state.last_report_at)) < delta:
        return change_log.latest_report(connection_id)
    start = now - delta
    events = change_log.list_events(connection_id, start=start, end=now)
    return change_log.save_report(connection_id, state.report_interval, start, now, events)


def generate_report(connection_id: str, interval: str) -> dict:
    now = datetime.now(timezone.utc)
    delta = timedelta(days=1) if interval == "daily" else timedelta(days=7)
    start = now - delta
    events = change_log.list_events(connection_id, start=start, end=now)
    return change_log.save_report(connection_id, interval, start, now, events)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
