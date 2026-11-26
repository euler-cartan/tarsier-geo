"""Read API for the exam harness; aggregate timings in Tarsier SQLite only."""
import json
from tarsier.storage.db import get_session
from tarsier.storage.models import RunTiming


def save_run(payload):
    with get_session() as session:
        session.add(RunTiming(run_id=payload["run_id"], connection_id=payload["connection_id"],
                              started_utc=payload["started_utc"], payload_json=json.dumps(payload)))
        session.commit()


def read_runs(*, connection_id=None, run_id=None, limit=1000):
    if not 1 <= limit <= 10000:
        raise ValueError("Timing limit must be between 1 and 10000")
    with get_session() as session:
        query = session.query(RunTiming)
        if connection_id is not None:
            query = query.filter_by(connection_id=connection_id)
        if run_id is not None:
            query = query.filter_by(run_id=run_id)
        rows = query.order_by(RunTiming.started_utc.desc()).limit(limit).all()
        return [json.loads(row.payload_json) for row in rows]


def save_checkpoint(run_id, connection_id, schema, name, payload):
    from tarsier.storage.models import RunCheckpoint
    with get_session() as session:
        session.merge(RunCheckpoint(run_id=run_id,connection_id=connection_id,item_schema=schema,item_name=name,payload_json=json.dumps(payload)))
        session.commit()


def read_checkpoints(*, run_id=None, connection_id=None):
    from tarsier.storage.models import RunCheckpoint
    with get_session() as session:
        query=session.query(RunCheckpoint)
        if run_id is not None:query=query.filter_by(run_id=run_id)
        if connection_id is not None:query=query.filter_by(connection_id=connection_id)
        return [{"run_id":r.run_id,"schema":r.item_schema,"name":r.item_name,**json.loads(r.payload_json)} for r in query.order_by(RunCheckpoint.item_schema,RunCheckpoint.item_name)]
