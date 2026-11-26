"""Automation builder API (PRD §7.6, FSD §11.2)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tarsier.automation.engine import catalog, template_graph, validate_automation_graph, walk_graph
from tarsier.automation.evaluate import run_one, _context, _handle
from tarsier.storage import automations as auto_store
from tarsier.storage import connections as storage

router = APIRouter(prefix="/api/connections/{connection_id}")


def _require(connection_id: str):
    if storage.get_connection(connection_id) is None:
        raise HTTPException(status_code=404, detail="No such connection.")


@router.get("/automations/catalog")
def get_catalog(connection_id: str):
    _require(connection_id)
    return catalog()


@router.get("/automations")
def list_automations(connection_id: str):
    _require(connection_id)
    return {"automations": auto_store.list_automations(connection_id), "runs": auto_store.list_runs(connection_id)}


class AutomationBody(BaseModel):
    title: str = ""
    graph: dict = {}
    paused: bool = False
    template_id: str | None = None
    ai_authored: bool = False
    review_approved: bool = False


def _validate(body: AutomationBody, *, saving=True):
    if saving and body.ai_authored and not body.review_approved:
        raise HTTPException(409, "Review and approve the AI draft before saving.")
    try:
        return validate_automation_graph(body.graph)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/automations/templates/{template_id}")
def get_template(connection_id: str, template_id: str):
    _require(connection_id)
    result = template_graph(template_id)
    if result is None:
        raise HTTPException(404, "Unknown template.")
    return result


@router.post("/automations/preview")
def preview(connection_id: str, body: AutomationBody):
    _require(connection_id)
    graph = _validate(body, saving=False)
    ctx = _context(connection_id, {"graph": graph}, include_all_events=True)
    ctx.dry_run = True
    ok, message, trace = walk_graph(graph, ctx, _handle)
    return {"ok": ok, "message": message, "trace": trace, "dry_run": True}


@router.post("/automations", status_code=201)
def create_automation(connection_id: str, body: AutomationBody):
    _require(connection_id)
    if body.ai_authored and not body.review_approved:
        raise HTTPException(409, "Review and approve the AI draft before saving.")
    payload = body.model_dump()
    if body.template_id:
        spec = template_graph(body.template_id)
        if spec is None:
            raise HTTPException(status_code=400, detail="Unknown template.")
        payload["title"] = body.title or spec["title"]
        payload["graph"] = spec["graph"]
    else:
        payload["graph"] = _validate(body)
    return auto_store.create_automation(connection_id, payload)


@router.put("/automations/{automation_id}")
def update_automation(connection_id: str, automation_id: str, body: AutomationBody):
    _require(connection_id)
    existing = auto_store.get_automation(automation_id)
    if existing is None or existing["connection_id"] != connection_id:
        raise HTTPException(404, "No such automation.")
    payload = body.model_dump()
    payload["graph"] = _validate(body)
    updated = auto_store.update_automation(automation_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="No such automation.")
    return updated


@router.delete("/automations/{automation_id}")
def delete_automation(connection_id: str, automation_id: str):
    _require(connection_id)
    existing = auto_store.get_automation(automation_id)
    if existing is None or existing["connection_id"] != connection_id:
        raise HTTPException(404, "No such automation.")
    if not auto_store.delete_automation(automation_id):
        raise HTTPException(status_code=404, detail="No such automation.")
    return {"ok": True}


@router.post("/automations/{automation_id}/test-run")
def test_run(connection_id: str, automation_id: str):
    _require(connection_id)
    return run_one(connection_id, automation_id, dry_run=True)


@router.post("/automations/{automation_id}/run")
def run_now(connection_id: str, automation_id: str):
    _require(connection_id)
    return run_one(connection_id, automation_id, dry_run=False)
