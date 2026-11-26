"""Covers TAD §9: secrets are never stored in plain text, and are retrievable
by the same code path regardless of which backend (OS keyring or the
encrypt-at-rest fallback) actually stored them.
"""

from tarsier.storage import secrets


def test_set_get_delete_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    stored = {}
    monkeypatch.setattr(
        secrets.keyring,
        "set_password",
        lambda service, user, password: stored.__setitem__((service, user), password),
    )
    monkeypatch.setattr(
        secrets.keyring,
        "get_password",
        lambda service, user: stored.get((service, user)),
    )
    monkeypatch.setattr(
        secrets.keyring,
        "delete_password",
        lambda service, user: stored.pop((service, user), None),
    )
    secrets.set_secret("conn-1", "s3cret-password")

    assert secrets.get_secret("conn-1") == "s3cret-password"

    secrets.delete_secret("conn-1")
    assert secrets.get_secret("conn-1") is None


def test_fallback_encryption_path_does_not_write_plaintext(tmp_path, monkeypatch):
    monkeypatch.setenv("TARSIER_HOME", str(tmp_path))
    monkeypatch.setattr(secrets, "keyring", _WindowsCredentialFailureModule())

    secrets.set_secret("conn-2", "another-secret")
    assert secrets.get_secret("conn-2") == "another-secret"

    enc_file = tmp_path / "secret-conn-2.enc"
    assert enc_file.exists()
    assert b"another-secret" not in enc_file.read_bytes()


class _WindowsCredentialFailureModule:
    """Models the native Windows backend error that escapes KeyringError."""

    class CredentialManagerError(Exception):
        pass

    def set_password(self, *a, **k):
        raise self.CredentialManagerError(
            "(1312, 'CredWrite', 'A specified logon session does not exist')"
        )

    def get_password(self, *a, **k):
        raise self.CredentialManagerError("(1312, 'CredRead', 'No logon session')")

    def delete_password(self, *a, **k):
        raise self.CredentialManagerError("(1312, 'CredDelete', 'No logon session')")


def test_masked_never_reveals_the_secret():
    assert secrets.masked("super-secret") == "••••••"
    assert "super-secret" not in secrets.masked("super-secret")
    assert secrets.masked(None) == "(not set)"
