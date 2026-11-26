"""Give every test run a throw-away data folder before any test can create app state."""

import os
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.test_home_guard import require_test_home

# The test HTTP client calls the app as "testserver"; the app refuses that
# host name unless the test suite opts in.
os.environ.setdefault("TARSIER_ALLOW_TEST_HOST", "1")


def pytest_sessionstart(session):
    # Tests must never write to the operating system's credential store. With no
    # OS store available, Tarsier uses its encrypted file inside TARSIER_HOME.
    import keyring
    from keyring.backends.fail import Keyring as NoOsCredentialStore

    keyring.set_keyring(NoOsCredentialStore())
    try:
        home = require_test_home()
    except RuntimeError as exc:
        raise pytest.UsageError(str(exc)) from exc
    home.mkdir(parents=True, exist_ok=True)
    base = session.config.option.basetemp
    if base is None:
        session.config.option.basetemp = str(home / f"pytest-{os.getpid()}-{uuid4().hex}")
    else:
        try:
            require_test_home(str(Path(base).resolve(strict=False)))
        except RuntimeError as exc:
            raise pytest.UsageError(str(exc)) from exc
    process_temp = home / f"temp-{os.getpid()}-{uuid4().hex}"
    process_temp.mkdir(parents=True, exist_ok=True)
    for key in ("TEMP", "TMP", "TMPDIR"):
        os.environ[key] = str(process_temp)
    tempfile.tempdir = str(process_temp)
