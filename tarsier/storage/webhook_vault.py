"""Webhook URLs are credentials: anyone holding one can post to that channel.

Alert and automation settings used to keep the URL in plain text inside the
settings database, and the API handed it back to the browser. Now the URL goes
to the credential store (the same place as connection passwords) and the saved
settings keep only an opaque reference, `webhook_ref`. The API never returns
the URL; in the forms a blank field means "keep the saved one".
"""

import json
import logging
import re
import uuid

from tarsier.storage import secrets

_log = logging.getLogger("tarsier.webhooks")
_REF = re.compile(r"[0-9a-f]{32}")


def _key(ref: str) -> str:
    return f"webhook-{ref}"


def _valid(ref) -> bool:
    return isinstance(ref, str) and bool(_REF.fullmatch(ref))


def protect_config(config: dict | None, previous: dict | None = None) -> dict:
    """Move a typed webhook URL into the credential store; return the config without it."""
    config = dict(config or {})
    url = str(config.pop("webhook_url", "") or "").strip()
    config.pop("webhook_ref", None)  # a client never chooses which secret a rule points at
    old_ref = (previous or {}).get("webhook_ref")
    if url:
        ref = old_ref if _valid(old_ref) else uuid.uuid4().hex
        secrets.set_secret(_key(ref), url)
        config["webhook_ref"] = ref
    elif _valid(old_ref):
        config["webhook_ref"] = old_ref  # blank means: keep the saved URL
    return config


def protect_graph(graph: dict | None, previous: dict | None = None) -> dict:
    """The same for every node of an automation, matched to the old node by id."""
    graph = dict(graph or {"nodes": [], "edges": []})
    old = {n.get("id"): (n.get("config") or {}) for n in (previous or {}).get("nodes") or []}
    nodes = []
    for node in graph.get("nodes") or []:
        node = dict(node)
        if isinstance(node.get("config"), dict):
            node["config"] = protect_config(node["config"], old.get(node.get("id")))
        nodes.append(node)
    graph["nodes"] = nodes
    return graph


def resolve(config: dict | None) -> str:
    """The URL to post to. Settings saved before this change still carry it inline."""
    config = config or {}
    ref = config.get("webhook_ref")
    if _valid(ref):
        return secrets.get_secret(_key(ref)) or ""
    return str(config.get("webhook_url") or "")


def purge_config(config: dict | None) -> None:
    ref = (config or {}).get("webhook_ref")
    if _valid(ref):
        secrets.delete_secret(_key(ref))


def purge_graph(graph: dict | None) -> None:
    for node in (graph or {}).get("nodes") or []:
        purge_config(node.get("config"))


def migrate_legacy() -> int:
    """Move webhook URLs saved in plain text by earlier versions into the credential store."""
    from tarsier.storage.db import get_session
    from tarsier.storage.models import AlertRule, Automation

    moved = 0
    with get_session() as session:
        for row in session.query(AlertRule).all():
            config = json.loads(row.config_json or "{}")
            if str(config.get("webhook_url") or "").strip():
                row.config_json = json.dumps(protect_config(config))
                moved += 1
        for row in session.query(Automation).all():
            graph = json.loads(row.graph_json or "{}")
            if any(str((n.get("config") or {}).get("webhook_url") or "").strip() for n in graph.get("nodes") or []):
                row.graph_json = json.dumps(protect_graph(graph))
                moved += 1
        session.commit()
    if moved:
        _log.info("Moved %d saved webhook setting(s) into the credential store.", moved)
    return moved
