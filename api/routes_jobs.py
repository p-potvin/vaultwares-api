import os
import json
import time
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
from dataclasses import dataclass
from collections import defaultdict, deque
import logging
import asyncio
import httpx
from api.models import JobSummary, JobDetail, FaceswapSubmitRequest, FaceswapCompleteRequest
from api.config import (
    JOBS_DIR, JOB_QUEUE_MAX_PENDING, JOB_WORKER_CONCURRENCY,
    JOB_DEFAULT_TTL_SECONDS, JOBS_PUBLIC_SUBMIT_ENABLED,
    JOB_SUBMIT_RATE_LIMIT_MAX_PUBLIC, JOB_SUBMIT_RATE_LIMIT_WINDOW_SECONDS
)
from api.auth import require_auth, _get_client_ip, _is_trusted_client_ip
from api.database import db_available
from threading import Lock

router = APIRouter()
logger = logging.getLogger("vaultwares.api")
_jobs_fs_lock = Lock()
_job_submit_buckets = defaultdict(lambda: deque())

def _ensure_jobs_dir() -> None:
    try: os.makedirs(JOBS_DIR, exist_ok=True)
    except: pass

def _job_path(job_id: str) -> str:
    safe = "".join(ch for ch in job_id if ch.isalnum() or ch in ("-", "_"))
    return os.path.join(JOBS_DIR, f"{safe}.json")

def _read_job(job_id: str) -> Optional[dict]:
    path = _job_path(job_id)
    if not os.path.exists(path): return None
    with _jobs_fs_lock:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

def _write_job(job: dict) -> None:
    path = _job_path(job["id"])
    tmp_path = path + ".tmp"
    with _jobs_fs_lock:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)

def _list_jobs(limit: int = 50) -> List[dict]:
    _ensure_jobs_dir()
    try: candidates = [os.path.join(JOBS_DIR, name) for name in os.listdir(JOBS_DIR) if name.endswith(".json")]
    except: return []
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    jobs = []
    for path in candidates[: max(0, limit)]:
        try:
            with _jobs_fs_lock:
                with open(path, "r", encoding="utf-8") as f:
                    jobs.append(json.load(f))
        except: continue
    return jobs

def _job_now() -> float:
    return time.time()

def _new_job(kind: str, payload: dict, requested_by: dict) -> dict:
    now = _job_now()
    job_id = "job_" + uuid4().hex
    return {
        "id": job_id, "kind": kind, "status": "queued",
        "created_at": now, "updated_at": now, "requested_by": requested_by,
        "payload": payload, "result": None, "error": None,
        "ttl_seconds": JOB_DEFAULT_TTL_SECONDS
    }

def _job_redact_for_list(job: dict) -> dict:
    return {
        "id": job.get("id"), "kind": job.get("kind"), "status": job.get("status"),
        "created_at": job.get("created_at"), "updated_at": job.get("updated_at"),
        "requested_by": job.get("requested_by"), "result": job.get("result"),
        "error": job.get("error"), "progress": job.get("progress")
    }

@dataclass
class _JobQueueItem:
    job_id: str

def _enforce_job_submit_rate_limit(client_ip: str) -> None:
    now = _job_now()
    bucket = _job_submit_buckets[client_ip]
    while bucket and (now - bucket[0]) > JOB_SUBMIT_RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= JOB_SUBMIT_RATE_LIMIT_MAX_PUBLIC:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    bucket.append(now)

def _queue_job(app, job: dict) -> None:
    if not hasattr(app.state, "job_queue"):
        raise HTTPException(status_code=503, detail="Job queue unavailable")
    try: app.state.job_queue.put_nowait(_JobQueueItem(job_id=job["id"]))
    except asyncio.QueueFull: raise HTTPException(status_code=503, detail="Server busy; try again later")

def _job_belongs_to_principal(job: dict, principal: dict) -> bool:
    rb = job.get("requested_by") or {}
    if principal.get("kind") == "user":
        user = principal.get("user")
        return rb.get("username") == getattr(user, "username", None) or rb.get("user") == "vault-flows"
    if principal.get("kind") == "api_key":
        key = principal.get("api_key")
        return rb.get("name") == getattr(key, "name", None)
    return False

@router.get("/jobs", response_model=List[JobSummary])
async def list_jobs(limit: int = 50, principal=Depends(require_auth)):
    if principal.get("kind") not in ("user", "api_key"):
        raise HTTPException(status_code=401, detail="Auth required")
    items = _list_jobs(limit=min(200, max(1, int(limit))))
    return [JobSummary(**_job_redact_for_list(item)) for item in items]

@router.get("/jobs/recent", response_model=Optional[JobSummary])
async def get_recent_job(kind: Optional[str] = None, status: Optional[str] = None, principal=Depends(require_auth)):
    if principal.get("kind") not in ("user", "api_key"):
        raise HTTPException(status_code=401, detail="Auth required")
    statuses = set(s.strip() for s in (status or "").split(",") if s.strip()) or None
    items = _list_jobs(limit=200)
    for item in items:
        if kind and item.get("kind") != kind: continue
        if statuses and item.get("status") not in statuses: continue
        if not _job_belongs_to_principal(item, principal) and principal.get("kind") == "user":
            user = principal.get("user")
            if not getattr(user, "is_admin", False): continue
        return JobSummary(**_job_redact_for_list(item))
    return None

@router.get("/jobs/{job_id}", response_model=JobDetail)
async def get_job(job_id: str, principal=Depends(require_auth)):
    if principal.get("kind") not in ("user", "api_key"):
        raise HTTPException(status_code=401, detail="Auth required")
    job = _read_job(job_id)
    if not job: raise HTTPException(status_code=404, detail="Job not found")
    return JobDetail(**dict(job))

@router.post("/jobs/{job_id}/cancel", response_model=JobDetail)
async def cancel_job(job_id: str, principal=Depends(require_auth)):
    if principal.get("kind") not in ("user", "api_key"):
        raise HTTPException(status_code=401, detail="Auth required")
    job = _read_job(job_id)
    if not job: raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") in ("succeeded", "failed"): return JobDetail(**job)
    job["status"] = "canceled"
    job["updated_at"] = _job_now()
    _write_job(job)
    return JobDetail(**job)

@router.post("/api/jobs/faceswap")
async def submit_faceswap(req: FaceswapSubmitRequest, request: Request):
    client_ip = _get_client_ip(request) or ""
    if not _is_trusted_client_ip(client_ip):
        _enforce_job_submit_rate_limit(client_ip)
    job = _new_job(
        kind="faceswap",
        payload={"source_face": req.source_face, "target_image": req.target_image},
        requested_by={"kind": "public", "ip": client_ip}
    )
    _write_job(job)
    return {"status": "queued", "jobId": job["id"]}

@router.post("/api/jobs/claim", response_model=Optional[JobDetail])
async def claim_faceswap_job(request: Request):
    client_ip = _get_client_ip(request) or ""
    if not _is_trusted_client_ip(client_ip):
        raise HTTPException(status_code=403, detail="Forbidden source")
    jobs = _list_jobs(limit=200)
    queued_jobs = [j for j in jobs if j.get("status") == "queued" and j.get("kind") == "faceswap"]
    if not queued_jobs: return None
    queued_jobs.sort(key=lambda j: float(j.get("created_at") or 0))
    target_job = queued_jobs[0]
    target_job["status"] = "running"
    target_job["updated_at"] = _job_now()
    _write_job(target_job)
    return JobDetail(**target_job)

@router.get("/api/jobs/{job_id}", response_model=JobDetail)
async def get_public_job_status(job_id: str):
    job = _read_job(job_id)
    if not job: raise HTTPException(status_code=404, detail="Job not found")
    return JobDetail(**job)

@router.post("/api/jobs/{job_id}/complete", response_model=JobDetail)
async def complete_faceswap_job(job_id: str, req: FaceswapCompleteRequest, request: Request):
    client_ip = _get_client_ip(request) or ""
    if not _is_trusted_client_ip(client_ip):
        raise HTTPException(status_code=403, detail="Forbidden source")
    job = _read_job(job_id)
    if not job: raise HTTPException(status_code=404, detail="Job not found")
    job["status"] = req.status
    job["updated_at"] = _job_now()
    if req.result is not None: job["result"] = req.result
    if req.error is not None: job["error"] = req.error
    _write_job(job)
    return JobDetail(**job)

async def _notify_job_callback(job: dict) -> None:
    from urllib.parse import urlparse
    from api.config import _tailscale_networks
    import ipaddress
    payload = job.get("payload") or {}
    callback_url = payload.get("callbackUrl") or payload.get("callback_url")
    if not callback_url: return
    callback_url = str(callback_url)
    
    # Check if callback URL is allowed
    parsed = urlparse(callback_url)
    allowed = False
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        if os.environ.get("JOB_CALLBACK_ALLOW_EXTERNAL", "0") == "1":
            allowed = True
        else:
            host = parsed.hostname.lower()
            if host in {"localhost", "127.0.0.1", "::1"}:
                allowed = True
            else:
                try:
                    ip = ipaddress.ip_address(host)
                    allowed = ip.is_loopback or ip.is_private or any(ip in net for net in _tailscale_networks)
                except ValueError: pass

    if not allowed:
        logger.warning(f"job.callback_blocked: {callback_url}")
        return

    body = {
        "jobId": job.get("id"), "kind": job.get("kind"), "status": job.get("status"),
        "result": job.get("result"), "error": job.get("error"), "correlationId": payload.get("correlationId")
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(callback_url, json=body)
    except Exception as exc:
        logger.warning(f"job.callback_failed for {callback_url}: {exc}")

async def _job_worker(app, worker_id: int) -> None:
    queue = app.state.job_queue
    while True:
        item = await queue.get()
        try:
            job = _read_job(item.job_id)
            if not job or job.get("status") != "queued": continue
            job["status"] = "running"
            job["updated_at"] = _job_now()
            _write_job(job)

            result = None
            error = None
            try:
                if job.get("kind") == "workflow_run":
                    payload = job.get("payload") or {}
                    workflow_id = str(payload.get("id") or "")
                    mode = str(payload.get("mode") or "local")
                    inputs = payload.get("inputs") or {}
                    
                    progress_state = {
                        "prompt_id": None, "current_node_id": None, "current_node_class": None,
                        "step": 0, "total": 0, "message": "starting", "cached_nodes": [], "events_seen": 0
                    }
                    last_write = [0.0]

                    def progress_cb(event: dict) -> None:
                        kind = event.get("kind")
                        progress_state["events_seen"] += 1
                        if kind == "submitted":
                            progress_state["prompt_id"] = event.get("prompt_id")
                            progress_state["message"] = "submitted to ComfyUI"
                        elif kind == "resolving_inputs":
                            progress_state["message"] = "preparing inputs"
                        elif kind == "execution_start":
                            progress_state["message"] = "execution started"
                        elif kind == "execution_cached":
                            progress_state["cached_nodes"] = event.get("nodes") or []
                            progress_state["message"] = f"reused {len(progress_state['cached_nodes'])} cached node(s)"
                        elif kind == "executing":
                            node = event.get("node")
                            progress_state["current_node_id"] = node
                            progress_state["step"] = 0
                            progress_state["total"] = 0
                            progress_state["message"] = f"running node {node}" if node else "finalizing"
                        elif kind == "progress":
                            progress_state["step"] = int(event.get("value") or 0)
                            progress_state["total"] = int(event.get("max") or 0)
                            n = progress_state["current_node_id"]
                            progress_state["message"] = f"step {progress_state['step']}/{progress_state['total']}" + (f" (node {n})" if n else "")
                        elif kind == "executed":
                            progress_state["message"] = f"node {event.get('node')} done"
                        elif kind == "execution_error":
                            progress_state["message"] = "ComfyUI error"
                        elif kind == "execution_success":
                            progress_state["message"] = "done"

                        now = time.time()
                        if now - last_write[0] < 0.2 and kind not in ("execution_success", "execution_error", "submitted"):
                            return
                        last_write[0] = now
                        cur = _read_job(item.job_id) or job
                        cur["progress"] = dict(progress_state)
                        cur["updated_at"] = _job_now()
                        _write_job(cur)

                    cancel_event = asyncio.Event()
                    async def watch_cancel():
                        while not cancel_event.is_set():
                            await asyncio.sleep(1.0)
                            cur = _read_job(item.job_id)
                            if cur and cur.get("status") == "canceled":
                                cancel_event.set()
                                return

                    watch_task = asyncio.create_task(watch_cancel())
                    try:
                        from api.routes_uploads import _execute_workflow_run_serialized
                        result = await _execute_workflow_run_serialized(app, workflow_id, mode, inputs, progress_cb=progress_cb, cancel_event=cancel_event)
                    finally:
                        cancel_event.set()
                        try: await asyncio.wait_for(watch_task, timeout=1.5)
                        except: watch_task.cancel()
                else:
                    raise ValueError(f"Unknown job kind: {job.get('kind')}")
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                logger.warning(f"worker {worker_id}: job {item.job_id} failed: {error}")

            job = _read_job(item.job_id) or job
            if job.get("status") == "canceled":
                job["updated_at"] = _job_now()
                _write_job(job)
                await _notify_job_callback(job)
                continue

            job["status"] = "failed" if error else "succeeded"
            job["updated_at"] = _job_now()
            job["result"] = result
            job["error"] = error
            _write_job(job)
            await _notify_job_callback(job)
        finally:
            queue.task_done()
