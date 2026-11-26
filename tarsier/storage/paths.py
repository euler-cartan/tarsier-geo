"""Resolves where Tarsier keeps its own state (SQLite file, run info), separate from user data (TAD §5)."""

import os
from pathlib import Path


def tarsier_home() -> Path:
    """Platform-appropriate directory for Tarsier's own data, created if missing."""
    override = os.environ.get("TARSIER_HOME")
    if override:
        home = Path(override)
    elif os.name == "nt":
        home = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "tarsier-geo"
    else:
        home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "tarsier-geo"
    home.mkdir(parents=True, exist_ok=True)
    return home


def run_state_path() -> Path:
    """Where the running server's PID and port are recorded, so `tarsier-geo stop` can find it."""
    return tarsier_home() / "run.json"


def database_path() -> Path:
    """Tarsier's own SQLite file (TAD §5)  -  not the user's connected databases."""
    return tarsier_home() / "tarsier.sqlite3"
