"""Portable backups omit the credential vault and derived Kuzu database."""
import json
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path

from tarsier.storage.paths import database_path, run_state_path, tarsier_home


def backup(destination: str) -> Path:
    output = Path(destination).resolve()
    if output.exists():
        raise ValueError("Backup destination already exists; choose a new filename.")
    if run_state_path().exists():
        raise ValueError("Stop Tarsier before backing up so snapshots and settings stay consistent.")
    if not database_path().exists():
        raise ValueError("There is no Tarsier database to back up.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        copy = Path(work) / "tarsier.sqlite3"
        with closing(sqlite3.connect(database_path())) as source, closing(sqlite3.connect(copy)) as target:
            source.backup(target)
        # These settings can contain credential-bearing URLs entered by users.
        # Require reconfiguration instead of copying endpoint credentials.
        with closing(sqlite3.connect(copy)) as db:
            db.execute("DELETE FROM app_settings WHERE key LIKE 'ai_%' OR key LIKE 'notification_%'")
            for row_id, config in db.execute("SELECT id, config_json FROM connections").fetchall():
                db.execute("UPDATE connections SET config_json=? WHERE id=?", (json.dumps(_scrub(json.loads(config))), row_id))
            for table, column in (("alert_rules", "config_json"), ("automations", "graph_json")):
                for row_id, config in db.execute(f"SELECT id, {column} FROM {table}").fetchall():
                    db.execute(f"UPDATE {table} SET {column}=?, paused=1 WHERE id=?", (json.dumps(_scrub(json.loads(config))), row_id))
            db.commit()
            db.execute("VACUUM")
        created = False
        try:
            with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
                created = True
                archive.writestr("manifest.json", json.dumps({"format": 1, "credentials": "excluded"}))
                archive.write(copy, "tarsier.sqlite3")
                for path in (tarsier_home() / "snapshots").glob("*"):
                    if path.suffix in (".json", ".parquet") and path.is_file():
                        archive.write(path, "snapshots/" + path.name)
        except Exception:
            if created:
                output.unlink(missing_ok=True)
            raise
    return output


def _scrub(value):
    from urllib.parse import urlsplit, urlunsplit
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items() if not any(word in k.lower() for word in ("password", "secret", "token", "api_key", "webhook_url"))}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, str) and "://" in value:
        url = urlsplit(value)
        return urlunsplit((url.scheme, url.netloc.rsplit("@", 1)[-1], url.path, "", ""))
    return value


def restore(source: str) -> Path:
    """Restore into an empty data directory; never overwrite an installation."""
    target = tarsier_home()
    if run_state_path().exists() or any(target.iterdir()):
        raise ValueError("Restore needs an empty TARSIER_HOME directory. Existing data will not be overwritten.")
    with tempfile.TemporaryDirectory() as work, zipfile.ZipFile(source) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        if manifest != {"format": 1, "credentials": "excluded"}:
            raise ValueError("Unsupported backup format.")
        for member in archive.infolist():
            parts = Path(member.filename).parts
            allowed = member.filename in ("manifest.json", "tarsier.sqlite3") or (len(parts) == 2 and parts[0] == "snapshots" and Path(parts[1]).suffix in (".json", ".parquet"))
            if not allowed or ".." in parts or Path(member.filename).is_absolute():
                raise ValueError("Backup contains an unexpected path.")
        archive.extractall(work)
        copy = Path(work) / "tarsier.sqlite3"
        with closing(sqlite3.connect(copy)) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup database failed its integrity check.")
            # New IDs ensure an OS keyring entry from the old installation is
            # never silently reused after a credentials-excluded restore.
            import uuid
            mapping = {row[0]: str(uuid.uuid4()) for row in db.execute("SELECT id FROM connections")}
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for table in tables:
                quoted = '"' + table.replace('"', '""') + '"'
                columns = {r[1] for r in db.execute(f"PRAGMA table_info({quoted})")}
                for column in ("connection_id", "peer_connection_id"):
                    if column in columns:
                        for old, new in mapping.items():
                            db.execute(f'UPDATE {quoted} SET "{column}"=? WHERE "{column}"=?', (new, old))
            for old, new in mapping.items():
                db.execute("UPDATE connections SET id=? WHERE id=?", (new, old))
            db.execute("DELETE FROM app_settings WHERE key LIKE 'ai_%' OR key LIKE 'notification_%'")
            db.commit()
        for metadata in (Path(work) / "snapshots").glob("*.json"):
            data = json.loads(metadata.read_text(encoding="utf-8"))
            data["connection_id"] = mapping.get(data["connection_id"], data["connection_id"])
            metadata.write_text(json.dumps(data), encoding="utf-8")
        shutil.copy2(copy, target / "tarsier.sqlite3")
        (target / "vault-namespace").write_text(uuid.uuid4().hex)
        if (Path(work) / "snapshots").exists():
            shutil.copytree(Path(work) / "snapshots", target / "snapshots")
    return target
