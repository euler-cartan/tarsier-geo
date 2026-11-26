from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
import time

import tarsier.storage.db as db


def test_concurrent_first_use_initializes_sqlite_engine_once(tmp_path, monkeypatch):
    create_engine = db.create_engine
    call_count = 0
    count_lock = Lock()

    def counted_create_engine(*args, **kwargs):
        nonlocal call_count
        with count_lock:
            call_count += 1
        # Make it likely all workers would miss the cache together without
        # the initialization lock.
        time.sleep(0.05)
        return create_engine(*args, **kwargs)

    monkeypatch.setattr(db, "create_engine", counted_create_engine)
    ready = Barrier(8)
    db_path = str(tmp_path / "concurrent.sqlite3")

    def initialize():
        ready.wait()
        return db._engine_for(db_path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        engines = list(pool.map(lambda _index: initialize(), range(8)))

    try:
        assert call_count == 1
        assert all(engine is engines[0] for engine in engines)
    finally:
        engines[0].dispose()
        db._cached_engine_for.cache_clear()
