"""Secret storage for connection credentials (TAD §9  -  mandatory).

Tries the operating system's own secure storage first (Windows Credential
Manager / macOS Keychain / Linux Secret Service, via `keyring`). Many of
Tarsier's on-premise deployment targets are headless Linux servers with no
Secret Service daemon, so when the OS store isn't usable, falls back to
encrypting the secret at rest with a locally-held key, per TAD §9's
"otherwise encrypt at rest" rule.

Secrets are never logged and never returned in full by anything outside
this module (the storage layer only ever exposes a masked form).
"""

import keyring
from cryptography.fernet import Fernet, InvalidToken

from tarsier.storage.paths import tarsier_home

_SERVICE_NAME = "tarsier-geo"


def _service_name():
    # A restored installation must not inherit credentials from OS keyring
    # entries belonging to the installation from which its backup was taken.
    namespace = tarsier_home() / "vault-namespace"
    return _SERVICE_NAME + (":" + namespace.read_text().strip() if namespace.exists() else "")


def _fallback_key_path():
    return tarsier_home() / "secret.key"


def _fallback_fernet() -> Fernet:
    key_path = _fallback_key_path()
    if key_path.exists():
        key = key_path.read_bytes()
    else:
        key = Fernet.generate_key()
        key_path.write_bytes(key)
        try:
            key_path.chmod(0o600)
        except OSError:
            pass  # best-effort on platforms without POSIX permissions (e.g. Windows)
    return Fernet(key)


def set_secret(connection_id: str, secret: str) -> None:
    try:
        keyring.set_password(_service_name(), connection_id, secret)
        return
    # Some OS backends raise their native exception instead of wrapping it in
    # KeyringError (Windows Credential Manager does this for WinError 1312).
    # A backend that cannot be reached is the documented signal to use the
    # encrypted local fallback.
    except Exception:
        pass
    token = _fallback_fernet().encrypt(secret.encode("utf-8"))
    (_fallback_key_path().parent / f"secret-{connection_id}.enc").write_bytes(token)


def get_secret(connection_id: str) -> str | None:
    try:
        value = keyring.get_password(_service_name(), connection_id)
        if value is not None:
            return value
    except Exception:
        pass
    enc_path = _fallback_key_path().parent / f"secret-{connection_id}.enc"
    if not enc_path.exists():
        return None
    token = enc_path.read_bytes()
    try:
        return _fallback_fernet().decrypt(token).decode("utf-8")
    except (InvalidToken, ValueError):
        # The key file was replaced or damaged, so this secret can no longer be
        # read. Treat it as not set (the user re-enters it) instead of failing
        # every request that touches the connection.
        return None


def delete_secret(connection_id: str) -> None:
    try:
        keyring.delete_password(_service_name(), connection_id)
    except Exception:
        pass
    enc_path = _fallback_key_path().parent / f"secret-{connection_id}.enc"
    enc_path.unlink(missing_ok=True)


def masked(secret: str | None) -> str:
    """Never display a secret back in full (TAD §9)."""
    return "••••••" if secret else "(not set)"
