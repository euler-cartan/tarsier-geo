"""Row caps that keep Tarsier safe on very large sources (TAD §8 "read gently").

Every read of user data is bounded. A "full" run reads up to these caps and
labels its result as a sample when the source is larger, instead of pulling
an unbounded table into memory. Each cap can be raised per deployment with
an environment variable, for machines with the memory to spare.
"""

import os


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


# Rows read by an explicit "full" statistics or quality run.
FULL_SCAN_MAX_ROWS = _env_int("TARSIER_FULL_SCAN_MAX_ROWS", 100_000)
# ID values read (in ID order) by the completeness check.
ID_SCAN_MAX_ROWS = _env_int("TARSIER_ID_SCAN_MAX_ROWS", 1_000_000)
# Largest table a GeoParquet snapshot will capture; bigger ones are skipped and reported.
SNAPSHOT_MAX_ROWS = _env_int("TARSIER_SNAPSHOT_MAX_ROWS", 250_000)
# Largest table the polling change tracker fingerprints; bigger ones need the history log.
POLLING_MAX_ROWS = _env_int("TARSIER_POLLING_MAX_ROWS", 250_000)
# Minimum minutes between scheduled polling passes (each pass reads every tracked table).
POLLING_INTERVAL_MINUTES = _env_int("TARSIER_POLLING_INTERVAL_MINUTES", 15)
# History-log rows pulled per round trip, and per scheduled sync.
CHANGE_SYNC_BATCH = _env_int("TARSIER_CHANGE_SYNC_BATCH", 5_000)
CHANGE_SYNC_MAX_PER_RUN = _env_int("TARSIER_CHANGE_SYNC_MAX_PER_RUN", 50_000)
# Change events returned to the Changes screen in one response.
CHANGE_EVENTS_PAGE = _env_int("TARSIER_CHANGE_EVENTS_PAGE", 1_000)
# Newest change events an alert or automation pass looks at. Events it has
# already handled are skipped by their receipts; this only bounds the read.
EVENT_EVALUATION_WINDOW = _env_int("TARSIER_EVENT_EVALUATION_WINDOW", 20_000)
