"""Routes behind the Add Connection flow (PRD §5, FSD §5).

Every connection type (PRD Phase 1.1–1.3) can be tested and saved. Each
connector's own `build_config` adapts the generic request body below to
its specific config shape (tarsier.connectors.registry).
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import json

from tarsier.connectors.base import ConnectorError
from tarsier.connectors.registry import get_connector
from tarsier.connectors.tiers import get_connection_type_info, list_connection_types
from tarsier.storage import connections as storage
from tarsier.storage.db import get_session
from tarsier.storage.models import ConnectionRecord

router = APIRouter(prefix="/api/connections")


@router.get("/types")
def get_connection_types():
    return [vars(info) for info in list_connection_types()]


@router.get("")
def get_connections():
    return [
        {
            "id": c.id,
            "name": c.name,
            "type": c.type,
            "config": c.config,
            "last_checked_at": c.last_checked_at,
            "last_status": c.last_status,
        }
        for c in storage.list_connections()
    ]


class CreateConnectionRequest(BaseModel):
    name: str
    type: str
    config: dict
    password: str | None = None
    enable_triggers: bool = False


@router.post("", status_code=201)
def create_connection(body: CreateConnectionRequest):
    try:
        get_connection_type_info(body.type)
        connector = get_connector(body.type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown connection type: {body.type!r}")

    name = _clean_name(body.name)
    password = _secret_from(body)
    try:
        config = connector.build_config(body.config, password)
        connector.test_connection(config)
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Check the connection details: the port must be a number.") from exc

    if body.enable_triggers:
        raise HTTPException(status_code=400, detail="Save the connection first, then choose Install/Upgrade history log.")
    saved = storage.create_connection(
        name=name, type=body.type, config=_stored_config(body.config), password=password
    )
    storage.record_check_result(saved.id, "ok")
    return {"id": saved.id, "name": saved.name, "type": saved.type}


_SECRET_KEYS = ("password", "token", "api_key", "secret")


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Give the connection a name.")
    return name[:120]


def _secret_from(body: "CreateConnectionRequest") -> str | None:
    # TAD §9: a credential never lives in the config JSON. If a client sends
    # one there (an ArcGIS token, say) it is moved to the secret store.
    return body.password or next((str(body.config[k]) for k in _SECRET_KEYS if body.config.get(k)), None)


def _stored_config(config: dict) -> dict:
    return {k: v for k, v in config.items() if k not in _SECRET_KEYS}


@router.put("/{connection_id}")
def update_connection(connection_id: str, body: CreateConnectionRequest):
    saved = storage.get_connection(connection_id)
    if saved is None:
        raise HTTPException(404, "No such connection.")
    if body.type != saved.type:
        raise HTTPException(400, "Create a new connection to use a different source type.")
    connector = get_connector(saved.type)
    name = _clean_name(body.name)
    new_secret = _secret_from(body)
    password = new_secret or storage.get_connection_password(saved.id)
    try:
        connector.test_connection(connector.build_config(body.config, password))
    except ConnectorError as exc:
        raise HTTPException(400, str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "Check the connection details: the port must be a number.") from exc
    with get_session() as session:
        record = session.get(ConnectionRecord, connection_id)
        record.name = name
        record.config_json = json.dumps(_stored_config(body.config))
        session.commit()
    if new_secret:
        from tarsier.storage.secrets import set_secret
        set_secret(connection_id, new_secret)
    storage.record_check_result(connection_id, "ok")
    return {"id": connection_id}


@router.delete("/{connection_id}")
def delete_connection(connection_id: str):
    if storage.get_connection(connection_id) is None:
        raise HTTPException(404, "No such connection.")
    storage.delete_connection(connection_id)
    return {"ok": True}
