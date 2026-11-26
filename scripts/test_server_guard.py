"""Require an explicit, safe port for any test PostgreSQL connection."""

import os


# PostgreSQL's default port and the usual second one: where real servers live.
FORBIDDEN_TEST_PORTS = {5432, 5433}


def validate_test_server_port(port: int | None) -> int:
    if port is None:
        raise ValueError("An explicit disposable test-server port is required.")
    if not 1 <= port <= 65535:
        raise ValueError("The test-server port must be between 1 and 65535.")
    if port in FORBIDDEN_TEST_PORTS:
        raise ValueError(f"Refusing to connect to a test server on port {port}.")
    return port


def require_test_server_port(environment_variable: str) -> int:
    value = os.environ.get(environment_variable)
    if value is None or not value.strip():
        raise RuntimeError(f"Set {environment_variable} to an explicit disposable test-server port.")
    try:
        port = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{environment_variable} must be an integer port.") from exc
    return validate_test_server_port(port)
