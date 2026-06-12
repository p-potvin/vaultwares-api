from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List
import socket
from tortoise.exceptions import DoesNotExist
from api.models import (
    Workflow, WorkflowCreateRequest, WorkflowUpdateRequest, WorkflowsExportRequest,
    WorkflowsBackupRequest, WorkflowsRestoreRequest, WorkflowPinRequest,
    WorkflowFavoriteRequest, WorkflowRunRequest, NetworkDiagnosticsResponse,
    _next_workflow_id, _workflow_pin_value, _dict_to_workflow,
    _load_workflows_from_file, _save_workflows_to_file
)
from api.database import db_available, WorkflowDB, workflowdb_to_pydantic
from api.auth import (
    require_auth, _get_client_ip, _is_trusted_client_ip,
    _is_trusted_proxy_peer, _effective_scheme
)
from api.config import (
    JOBS_PUBLIC_SUBMIT_ENABLED, GATEWAY_REQUIRED_PUBLIC,
    GATEWAY_HEADER_NAME, _trusted_client_ips
)
import time

router = APIRouter()

def _job_requested_by(principal: dict) -> dict:
    if principal.get("kind") == "user":
        user = principal.get("user")
        return {"kind": "user", "username": getattr(user, "username", None)}
    if principal.get("kind") == "api_key":
        key = principal.get("api_key")
        return {"kind": "api_key", "name": getattr(key, "name", None)}
    return {"kind": "unknown"}

def _job_submit_allowed(request: Request, principal: dict) -> bool:
    client_ip = _get_client_ip(request) or ""
    if _is_trusted_client_ip(client_ip):
        return True
    if principal.get("kind") == "user":
        return True
    return JOBS_PUBLIC_SUBMIT_ENABLED

@router.get("/workflows", response_model=List[Workflow])
async def list_workflows(_principal=Depends(require_auth)):
    if db_available():
        workflows = await WorkflowDB.all()
        return [workflowdb_to_pydantic(wf) for wf in workflows]
    return _load_workflows_from_file()

@router.get("/workflows/{workflow_id}", response_model=Workflow)
async def get_workflow(workflow_id: str, _principal=Depends(require_auth)):
    if db_available():
        try:
            obj = await WorkflowDB.get(id=workflow_id)
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return workflowdb_to_pydantic(obj)
    workflows = _load_workflows_from_file()
    match = next((w for w in workflows if w.id == workflow_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return match

@router.post("/workflows", response_model=Workflow)
async def create_workflow(wf: WorkflowCreateRequest, _principal=Depends(require_auth)):
    workflow_id = wf.id or _next_workflow_id()
    pin_value = _workflow_pin_value(wf.pin, wf.pinned)
    created = Workflow(
        id=workflow_id,
        name=wf.name,
        category=wf.category,
        description=wf.description,
        steps=wf.steps or [],
        pinned=pin_value,
        pin=pin_value,
        favorite=wf.favorite,
        lastRun=wf.lastRun,
    )

    if db_available():
        obj = await WorkflowDB.create(
            id=created.id,
            name=created.name,
            category=created.category,
            steps=created.steps,
            pinned=created.pinned,
            favorite=created.favorite,
        )
        return workflowdb_to_pydantic(obj)

    workflows = _load_workflows_from_file()
    workflows.append(created)
    _save_workflows_to_file(workflows)
    return created

@router.put("/workflows/{id}", response_model=Workflow)
async def update_workflow(id: str, wf: WorkflowUpdateRequest, _principal=Depends(require_auth)):
    if db_available():
        try:
            obj = await WorkflowDB.get(id=id)
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="Workflow not found")
        if wf.name is not None: obj.name = wf.name
        if wf.category is not None: obj.category = wf.category
        if wf.steps is not None: obj.steps = wf.steps
        if wf.favorite is not None: obj.favorite = wf.favorite
        pin_value = _workflow_pin_value(wf.pin, wf.pinned)
        if wf.pin is not None or wf.pinned is not None:
            obj.pinned = pin_value
        await obj.save()
        return workflowdb_to_pydantic(obj)

    workflows = _load_workflows_from_file()
    for index, item in enumerate(workflows):
        if item.id != id:
            continue
        updated = Workflow(
            id=id,
            name=wf.name if wf.name is not None else item.name,
            category=wf.category if wf.category is not None else item.category,
            description=wf.description if wf.description is not None else item.description,
            steps=wf.steps if wf.steps is not None else item.steps,
            pinned=_workflow_pin_value(wf.pin, wf.pinned) if (wf.pin is not None or wf.pinned is not None) else item.pinned,
            pin=_workflow_pin_value(wf.pin, wf.pinned) if (wf.pin is not None or wf.pinned is not None) else item.pinned,
            favorite=wf.favorite if wf.favorite is not None else item.favorite,
            lastRun=wf.lastRun if wf.lastRun is not None else item.lastRun,
        )
        workflows[index] = updated
        _save_workflows_to_file(workflows)
        return updated
    raise HTTPException(status_code=404, detail="Workflow not found")

@router.delete("/workflows/{id}")
async def delete_workflow(id: str, _principal=Depends(require_auth)):
    if db_available():
        deleted = await WorkflowDB.filter(id=id).delete()
        if not deleted:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return {"ok": True}

    workflows = _load_workflows_from_file()
    filtered = [item for item in workflows if item.id != id]
    if len(filtered) == len(workflows):
        raise HTTPException(status_code=404, detail="Workflow not found")
    _save_workflows_to_file(filtered)
    return {"ok": True}

@router.post("/workflows/export")
async def export_workflows(req: WorkflowsExportRequest, _principal=Depends(require_auth)):
    if db_available():
        workflows = await WorkflowDB.filter(id__in=req.ids)
        return [workflowdb_to_pydantic(wf) for wf in workflows]
    workflows = _load_workflows_from_file()
    if not req.ids:
        return workflows
    target_ids = set(req.ids)
    return [workflow for workflow in workflows if workflow.id in target_ids]

@router.post("/workflows/backup")
async def backup_workflows(_: WorkflowsBackupRequest, _principal=Depends(require_auth)):
    if db_available():
        workflows = await WorkflowDB.all()
        return [workflowdb_to_pydantic(wf) for wf in workflows]
    return _load_workflows_from_file()

@router.post("/workflows/restore")
async def restore_workflows(req: WorkflowsRestoreRequest, _principal=Depends(require_auth)):
    items = req.data
    if isinstance(items, dict):
        candidate = items.get("workflows", [])
        items = candidate if isinstance(candidate, list) else []
    workflows_in = [_dict_to_workflow(item) for item in items if isinstance(item, dict)]

    if db_available():
        for wf in workflows_in:
            await WorkflowDB.update_or_create(
                defaults={
                    "name": wf.name,
                    "category": wf.category,
                    "steps": wf.steps,
                    "pinned": wf.pinned,
                    "favorite": wf.favorite,
                },
                id=wf.id,
            )
        return {"ok": True}

    existing = {workflow.id: workflow for workflow in _load_workflows_from_file()}
    for workflow in workflows_in:
        existing[workflow.id] = workflow
    _save_workflows_to_file(list(existing.values()))
    return {"ok": True}

@router.post("/workflows/pin")
async def pin_workflow(req: WorkflowPinRequest, _principal=Depends(require_auth)):
    if db_available():
        try:
            obj = await WorkflowDB.get(id=req.id)
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="Workflow not found")
        obj.pinned = req.pin
        await obj.save()
        return workflowdb_to_pydantic(obj)

    workflows = _load_workflows_from_file()
    for index, item in enumerate(workflows):
        if item.id != req.id:
            continue
        updated = item.model_copy(update={"pinned": req.pin, "pin": req.pin})
        workflows[index] = updated
        _save_workflows_to_file(workflows)
        return updated
    raise HTTPException(status_code=404, detail="Workflow not found")

@router.post("/workflows/favorite")
async def favorite_workflow(req: WorkflowFavoriteRequest, _principal=Depends(require_auth)):
    if db_available():
        try:
            obj = await WorkflowDB.get(id=req.id)
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="Workflow not found")
        obj.favorite = req.favorite
        await obj.save()
        return workflowdb_to_pydantic(obj)

    workflows = _load_workflows_from_file()
    for index, item in enumerate(workflows):
        if item.id != req.id:
            continue
        updated = item.model_copy(update={"favorite": req.favorite})
        workflows[index] = updated
        _save_workflows_to_file(workflows)
        return updated
    raise HTTPException(status_code=404, detail="Workflow not found")

@router.post("/workflows/run")
async def run_workflow(req: WorkflowRunRequest, request: Request, principal=Depends(require_auth)):
    if db_available():
        try:
            await WorkflowDB.get(id=req.id)
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="Workflow not found")
    else:
        workflows = _load_workflows_from_file()
        if not any(item.id == req.id for item in workflows):
            raise HTTPException(status_code=404, detail="Workflow not found")

    if not _job_submit_allowed(request, principal):
        raise HTTPException(status_code=403, detail="Job submission not allowed")

    client_ip = _get_client_ip(request) or ""
    if not _is_trusted_client_ip(client_ip):
        from api.routes_jobs import _enforce_job_submit_rate_limit
        _enforce_job_submit_rate_limit(client_ip)

    job_payload = {"id": req.id, "mode": req.mode, "correlationId": getattr(request.state, "correlation_id", None)}
    if req.callbackUrl:
        job_payload["callbackUrl"] = req.callbackUrl

    from api.routes_jobs import _new_job, _write_job, _queue_job
    from api.app import app
    job = _new_job(
        kind="workflow_run",
        payload=job_payload,
        requested_by=_job_requested_by(principal),
    )
    _write_job(job)
    _queue_job(app, job)
    return {"id": req.id, "mode": req.mode, "status": "queued", "jobId": job["id"]}

@router.get("/diagnostics/network", response_model=NetworkDiagnosticsResponse)
async def network_diagnostics(request: Request, principal=Depends(require_auth)):
    if principal.get("kind") == "user" and not principal["user"].is_admin:
        raise HTTPException(status_code=403, detail="Admin required")

    peer_ip = request.client.host if request.client else ""
    client_ip = _get_client_ip(request) or ""
    return NetworkDiagnosticsResponse(
        served_by=socket.gethostname(),
        peer_ip=peer_ip,
        client_ip=client_ip,
        effective_scheme=_effective_scheme(request),
        via_trusted_proxy=_is_trusted_proxy_peer(peer_ip),
        trusted_client_ip=_is_trusted_client_ip(client_ip),
        trusted_client_allowlist_active=bool(_trusted_client_ips),
        gateway_required_public=GATEWAY_REQUIRED_PUBLIC,
        gateway_header_present=bool(request.headers.get(GATEWAY_HEADER_NAME)),
        forwarded_for=request.headers.get("x-forwarded-for") or None,
        forwarded_proto=request.headers.get("x-forwarded-proto") or None,
        correlation_id=getattr(request.state, "correlation_id", None),
    )
