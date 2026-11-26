"""Alert CRUD and evaluation (PRD §7.5, FSD §11.1)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tarsier.alerts.engine import ALERT_KINDS, KIND_LABELS
from tarsier.alerts.evaluate import evaluate_connection, preview_rule
from tarsier.storage import alerts as alert_store
from tarsier.storage import connections as storage
from tarsier.connectors.base import ConnectorError
from tarsier.quality.engine import RULE_OPERATORS

router = APIRouter(prefix="/api/connections/{connection_id}")


def _require(connection_id: str):
    saved = storage.get_connection(connection_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="No such connection.")
    return saved


class AlertBody(BaseModel):
    kind: str
    title: str | None = None
    target_schema: str = ""
    target_name: str = ""
    config: dict = {}
    paused: bool = False


def _validate(body: AlertBody):
    if body.kind not in ALERT_KINDS:
        raise HTTPException(400, "Unknown alert type.")
    cfg = body.config
    if cfg.get("notify", "log") not in ("log", "email", "webhook", "slack", "teams"):
        raise HTTPException(400, "Choose a supported notification channel.")
    fields = {"row_count_drop": ("threshold_share", 0.0001, 1), "size_spike": ("threshold_share", 0.0001, 1000), "freshness": ("threshold_days", 1, 36500), "quality_score_drop": ("threshold_points", 1, 100)}
    if body.kind in fields:
        field, low, high = fields[body.kind]
        if field in cfg:
            try:
                if not low <= float(cfg[field]) <= high:
                    raise ValueError()
            except (ValueError, TypeError, OverflowError) as exc:
                raise HTTPException(400, f"{field} must be between {low} and {high}.") from exc
    if body.kind == "specific_user" and not str(cfg.get("user") or "").strip():
        raise HTTPException(400, "Enter the database user to monitor.")
    if body.kind == "layer_presence" and cfg.get("presence", "either") not in ("either", "added", "dropped"):
        raise HTTPException(400, "Choose added, dropped, or either.")
    if body.kind == "banned_value":
        if cfg.get("operator") == "is_unique":
            raise HTTPException(400, "IS UNIQUE is available only for quality rules, not alerts.")
        if not cfg.get("field"):
            raise HTTPException(400, "Enter a field for a banned-value alert.")
        if cfg.get("operator", "eq") not in RULE_OPERATORS:
            raise HTTPException(400, "Choose a supported value comparison.")


def _owned(connection_id: str, rule_id: str):
    rule = alert_store.get_rule(rule_id)
    if rule is None or rule["connection_id"] != connection_id:
        raise HTTPException(404, "No such alert.")


@router.post("/alerts/preview")
def post_preview(connection_id: str, body: AlertBody):
    _require(connection_id)
    _validate(body)
    return preview_rule(connection_id, body.model_dump())


@router.get("/alerts/kinds")
def get_kinds(connection_id: str):
    _require(connection_id)
    return [{"id": k, "label": KIND_LABELS[k]} for k in ALERT_KINDS]


@router.get("/alerts")
def get_alerts(connection_id: str):
    _require(connection_id)
    return {
        "rules": alert_store.list_rules(connection_id),
        "fires": alert_store.list_fires(connection_id),
        "kinds": [{"id": k, "label": KIND_LABELS[k]} for k in ALERT_KINDS],
    }


@router.post("/alerts")
def post_alert(connection_id: str, body: AlertBody):
    _require(connection_id)
    _validate(body)
    _validate_shared_operator(connection_id, body)
    return alert_store.create_rule(connection_id, body.model_dump())


@router.put("/alerts/{rule_id}")
def put_alert(connection_id: str, rule_id: str, body: AlertBody):
    _require(connection_id)
    _owned(connection_id, rule_id)
    _validate(body)
    _validate_shared_operator(connection_id, body)
    updated = alert_store.update_rule(rule_id, body.model_dump())
    if updated is None:
        raise HTTPException(status_code=404, detail="No such alert.")
    return updated


def _validate_shared_operator(connection_id: str, body: AlertBody):
    from tarsier.quality.engine import NEW_RULE_OPERATORS
    from tarsier.quality.rule_validation import columns_for, validate
    if body.kind != "banned_value" or body.config.get("operator") not in NEW_RULE_OPERATORS:return
    if not body.target_name:
        raise HTTPException(status_code=400, detail="Pick a target table for this operator.")
    try:
        validate({**body.config,"kind":"attribute"},columns_for(connection_id,body.target_schema,body.target_name))
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/alerts/{rule_id}")
def delete_alert(connection_id: str, rule_id: str):
    _require(connection_id)
    _owned(connection_id, rule_id)
    if not alert_store.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="No such alert.")
    return {"status": "ok"}


@router.post("/alerts/evaluate", status_code=202)
def post_evaluate(connection_id: str):
    _require(connection_id)
    try:
        fired = evaluate_connection(connection_id)
    except ConnectorError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"status": "ok", "fired": len(fired), "fires": fired}
