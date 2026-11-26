"""Quality-check routes (PRD §7.3, FSD §9). One POST per check so bars update independently."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from tarsier.connectors.base import ConnectorError
from tarsier.quality import scan as quality_scan
from tarsier.quality.engine import applicable_checks, never_run_result
from tarsier.storage import connections as storage
from tarsier.storage import item_cache, quality_cache
from tarsier.storage import preview_cache, stats_cache
from tarsier.quality.rule_validation import columns_for, validate
from tarsier.quality.engine import NEW_RULE_OPERATORS, RULE_OPERATORS

router = APIRouter(prefix="/api/connections/{connection_id}")


def _require_connection(connection_id: str):
    saved = storage.get_connection(connection_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="No such connection.")
    return saved


class QualitySettingsBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    item_schema: str = Field(default="", alias="schema")
    name: str = ""
    boundary_schema: str | None = None
    boundary_name: str | None = None


class QualityRuleBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    item_schema: str = Field(default="", alias="schema")
    name: str = ""
    kind: str = "attribute"
    field: str
    operator: str = "eq"
    value: str | None = None
    geometry_type: str | None = None
    ai_authored: bool = False
    review_approved: bool = False


def _validate_rule(body):
    if body.ai_authored and not body.review_approved:
        raise HTTPException(409, "Review and approve the AI draft before saving.")
    if body.kind not in ("attribute", "geometry_type") or body.operator not in RULE_OPERATORS:
        raise HTTPException(400, "Choose a supported rule kind and operator.")


@router.get("/item/quality")
def get_item_quality(connection_id: str, schema: str = "", name: str = "", kind: str = "vector"):
    _require_connection(connection_id)
    cached = quality_cache.get_checks(connection_id, schema, name)
    checks = {}
    for check_id in applicable_checks(kind):
        checks[check_id] = asdict(cached.get(check_id) or never_run_result(check_id))
    settings = quality_cache.get_settings(connection_id, schema, name)
    # The boundary picker lists layers from Tarsier's own cache, so reopening
    # the Quality tab never queries the source (TAD §8, TRS-101).
    layers = [
        {"schema": i.schema, "name": i.name, "geometry_type": i.geometry_type}
        for i in item_cache.list_items(connection_id)
        if i.kind == "vector" and not (i.schema == schema and i.name == name)
    ]
    columns = (preview_cache.get_preview(connection_id, schema, name) or {}).get("columns", [])
    if not columns:
        stats = stats_cache.get_stats(connection_id, schema, name)
        if stats:
            columns = [{"name":c.name,"type":"numeric" if c.is_numeric else "text"} for c in stats.columns]
    return {
        "columns": columns,
        "checks": checks,
        "rules": quality_cache.list_rules(connection_id, schema, name),
        "boundary_schema": settings.boundary_schema if settings else None,
        "boundary_name": settings.boundary_name if settings else None,
        "vector_layers": layers,
    }


@router.post("/item/quality/scan", status_code=202)
def scan_item_quality(
    connection_id: str, schema: str = "", name: str = "", check: str = "", full: bool = False
):
    _require_connection(connection_id)
    if not check:
        raise HTTPException(status_code=400, detail="Which check should run?")
    try:
        result = quality_scan.scan_check(connection_id, schema, name, check, full=full)
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "check": asdict(result)}


@router.put("/item/quality/settings")
def put_quality_settings(connection_id: str, body: QualitySettingsBody):
    _require_connection(connection_id)
    quality_cache.set_boundary(connection_id, body.item_schema, body.name, body.boundary_schema, body.boundary_name)
    return {"status": "ok"}


@router.post("/item/quality/rules")
def post_quality_rule(connection_id: str, body: QualityRuleBody):
    _require_connection(connection_id)
    _validate_rule(body)
    if not body.field.strip():
        raise HTTPException(status_code=400, detail="Pick a field for this rule.")
    _validate_extended_rule(connection_id, body)
    return quality_cache.create_rule(
        connection_id,
        body.item_schema,
        body.name,
        {
            "kind": body.kind,
            "field": body.field,
            "operator": body.operator,
            "value": body.value,
            "geometry_type": body.geometry_type,
        },
    )


@router.put("/item/quality/rules/{rule_id}")
def put_quality_rule(connection_id: str, rule_id: str, body: QualityRuleBody):
    _require_connection(connection_id)
    _validate_rule(body)
    existing = quality_cache.get_rule(rule_id)
    if existing is None or existing.connection_id != connection_id:
        raise HTTPException(404, "No such rule.")
    body.item_schema, body.name = existing.schema, existing.name
    _validate_extended_rule(connection_id, body)
    updated = quality_cache.update_rule(
        rule_id,
        {
            "kind": body.kind,
            "field": body.field,
            "operator": body.operator,
            "value": body.value,
            "geometry_type": body.geometry_type,
        },
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="No such rule.")
    return updated


def _validate_extended_rule(connection_id: str, body: QualityRuleBody):
    if body.operator not in NEW_RULE_OPERATORS:
        return
    try:
        validate(body.model_dump(), columns_for(connection_id, body.item_schema, body.name))
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/item/quality/rules/{rule_id}")
def delete_quality_rule(connection_id: str, rule_id: str):
    _require_connection(connection_id)
    existing = quality_cache.get_rule(rule_id)
    if existing is None or existing.connection_id != connection_id:
        raise HTTPException(404, "No such rule.")
    if not quality_cache.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="No such rule.")
    return {"status": "ok"}
