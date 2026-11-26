"""Tarsier's own SQLite store (TAD §5)  -  never the connections it monitors."""

from functools import lru_cache
from threading import Lock

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from tarsier.storage.paths import database_path


def _apply_simple_migrations(engine) -> None:
    """`Base.metadata.create_all()` only creates missing *tables*  -  it never
    alters an existing one, so a column added to a model in a later version
    (like last_scanned_at) silently doesn't appear in an already-created
    database. SQLite supports `ALTER TABLE ... ADD COLUMN`, which covers
    every migration this project needs for now (adding nullable columns);
    nothing here handles renames or drops. Found by actually hitting this
    with real local data from an earlier phase, not in a test.
    """
    from tarsier.storage.models import Base

    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.tables.values():
            if table.name not in inspector.get_table_names():
                continue
            existing = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in existing:
                    ddl = column.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl}'))
            # create_all() also never adds an index to a table that already exists.
            existing_indexes = {index["name"] for index in inspector.get_indexes(table.name)}
            for index in table.indexes:
                if index.name not in existing_indexes:
                    index.create(conn)


_engine_initialization_lock = Lock()


@lru_cache(maxsize=8)
def _cached_engine_for(db_path: str):
    # The scheduler, background checks and web requests all write to this one
    # file. Wait for a competing writer instead of failing with "database is
    # locked", and use WAL so readers are never blocked by a writer.
    engine = create_engine(f"sqlite:///{db_path}", future=True, connect_args={"timeout": 30})

    @event.listens_for(engine, "connect")
    def _configure(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    from tarsier.storage.models import Base

    Base.metadata.create_all(engine)
    _apply_simple_migrations(engine)
    from tarsier.storage.event_receipts import initialize_upgrade
    initialize_upgrade(engine)
    return engine


def _engine_for(db_path: str):
    # lru_cache keeps its data structures thread-safe, but it may still call
    # the wrapped function more than once for the same uncached key when
    # requests arrive together. SQLite's create_all(checkfirst=True) is not
    # safe under that race: two initializers can both observe a missing table.
    with _engine_initialization_lock:
        return _cached_engine_for(db_path)


def get_engine():
    # Cache key is the resolved path, so tests pointing TARSIER_HOME at a
    # temp directory get their own isolated engine rather than reusing one
    # opened against a different location earlier in the process.
    return _engine_for(str(database_path()))


def get_session() -> Session:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)()
