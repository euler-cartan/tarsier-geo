"""Bounded map geometries cached separately from tabular previews."""
import json
from tarsier.storage.db import get_session
from tarsier.storage.models import MapPreviewCache


def save(connection_id, schema, name, payload):
    with get_session() as session:
        row = session.get(MapPreviewCache, (connection_id, schema, name))
        if row is None:
            row = MapPreviewCache(connection_id=connection_id, schema=schema, name=name)
            session.add(row)
        row.preview_json = json.dumps(payload)
        session.commit()


def get(connection_id, schema, name):
    with get_session() as session:
        row = session.get(MapPreviewCache, (connection_id, schema, name))
        return json.loads(row.preview_json) if row else None


def delete_all_for_connection(connection_id):
    with get_session() as session:
        session.query(MapPreviewCache).filter(MapPreviewCache.connection_id == connection_id).delete()
        session.commit()
