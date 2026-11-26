"""Keep tests and QA scripts away from a real Tarsier data folder."""

import os
import tempfile
from pathlib import Path


def _app_defaults() -> list[Path]:
    """Where a real installation keeps its data (see tarsier/storage/paths.py)."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return [(base / "tarsier-geo").resolve(strict=False)]


def require_test_home(value: str | None = None, *, temp_root: str | None = None) -> Path:
    """Return a data folder inside the temporary directory, or refuse.

    With TARSIER_HOME unset, a new temporary folder is created and TARSIER_HOME
    is set to it. A TARSIER_HOME that points anywhere else is refused, never used.
    """
    root = Path(temp_root or os.environ.get("TARSIER_QA_TEMP_ROOT") or tempfile.gettempdir()).resolve()
    raw = os.environ.get("TARSIER_HOME") if value is None else value
    if value is None and not (raw or "").strip():
        raw = tempfile.mkdtemp(prefix="tarsier-test-", dir=root)
        os.environ["TARSIER_HOME"] = raw
    if not (raw or "").strip():
        raise RuntimeError("The test data folder is empty.")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise RuntimeError("TARSIER_HOME must be an absolute test folder.")
    resolved = candidate.resolve(strict=False)
    if any(resolved == default or resolved.is_relative_to(default) for default in _app_defaults()):
        raise RuntimeError("TARSIER_HOME cannot be the app's real data folder.")
    if resolved == root or not resolved.is_relative_to(root):
        raise RuntimeError(
            "TARSIER_HOME must be a folder inside the temporary directory. "
            "Unset it to let the tests create one, or set TARSIER_QA_TEMP_ROOT."
        )
    return resolved
