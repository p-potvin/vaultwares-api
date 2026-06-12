import os
import time
import secrets
import asyncio
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Response
from pydantic import BaseModel
from jose import jwt, JWTError
from api.models import UploadImageResponse
from api.config import (
    UPLOADS_DIR, UPLOADS_MAX_BYTES, UPLOADS_TOKEN_TTL_SECONDS, JWT_SECRET, JWT_ISSUER
)
from api.auth import require_auth
from api.comfyui import _verify_comfyui_image_token, _sign_comfyui_image_token
import httpx
from api.config import COMFYUI_URL

router = APIRouter()
_ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif", "image/bmp"}
_ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

def _sign_upload_token(rel_path: str, mime: str, original_name: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": JWT_ISSUER,
            "aud": "uploads",
            "iat": now, "nbf": now,
            "exp": now + UPLOADS_TOKEN_TTL_SECONDS,
            "p": rel_path,
            "m": mime,
            "n": original_name,
        },
        JWT_SECRET, algorithm="HS256",
    )

def _verify_upload_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"], audience="uploads", issuer=JWT_ISSUER)
    except JWTError as e:
        raise HTTPException(status_code=403, detail=f"Invalid upload token: {e}")

def _resolve_image_ref_to_path(image_ref: str) -> str:
    claims = _verify_upload_token(image_ref)
    rel = str(claims.get("p") or "")
    if not rel or os.path.isabs(rel) or ".." in rel.split(os.sep):
        raise RuntimeError("Invalid image_ref token")
    abs_path = os.path.abspath(os.path.join(UPLOADS_DIR, rel))
    if not os.path.isfile(abs_path):
        raise RuntimeError(f"Upload referenced by token no longer exists ({rel})")
    return abs_path

async def _upload_to_comfyui(local_path: str, mime: str = "image/png") -> str:
    fname = os.path.basename(local_path)
    with open(local_path, "rb") as f:
        files = {"image": (fname, f.read(), mime)}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{COMFYUI_URL}/upload/image", files=files, data={"overwrite": "true"})
    if r.status_code != 200: raise RuntimeError(f"ComfyUI /upload/image -> {r.status_code}: {r.text[:200]}")
    return str(r.json().get("name") or fname)

async def _resolve_image_inputs(inputs: dict, input_paths: dict, image_keys: list) -> dict:
    if not inputs: return inputs or {}
    out = dict(inputs)
    for key in image_keys:
        val = out.get(key)
        if not isinstance(val, str) or not val: continue
        if val.count(".") != 2: continue
        try: local_path = _resolve_image_ref_to_path(val)
        except Exception as e: raise RuntimeError(f"Cannot resolve image_ref for input '{key}': {e}")
        ext = os.path.splitext(local_path)[1].lower().lstrip(".")
        mime = f"image/{ 'jpeg' if ext == 'jpg' else (ext or 'png') }"
        comfy_name = await _upload_to_comfyui(local_path, mime=mime)
        out[key] = comfy_name
    return out

async def _execute_workflow_run(
    workflow_id: str,
    mode: str,
    inputs: dict,
    progress_cb=None,
    cancel_event: asyncio.Event | None = None,
) -> dict:
    from api.database import db_available, WorkflowDB, workflowdb_to_pydantic
    from api.models import _load_workflows_from_file
    import json
    
    if db_available():
        try: wf = await WorkflowDB.get(id=workflow_id)
        except: raise RuntimeError(f"Workflow '{workflow_id}' not found in DB")
        steps = wf.steps or []
    else:
        wfs = _load_workflows_from_file()
        match = next((w for w in wfs if w.id == workflow_id), None)
        if not match: raise RuntimeError(f"Workflow '{workflow_id}' not found in workflows.json")
        steps = match.steps or []

    if not isinstance(steps, list) or not steps: raise RuntimeError(f"Workflow '{workflow_id}' has no steps")
    step = next((s for s in steps if isinstance(s, dict) and s.get("kind") == "comfyui_graph"), None)
    if not step: raise RuntimeError(f"Workflow '{workflow_id}' has no comfyui_graph step")

    graph = step.get("graph")
    if not isinstance(graph, dict): raise RuntimeError("comfyui_graph step is missing a valid 'graph' object")
    input_paths = step.get("input_paths") or {}
    image_input_keys = step.get("image_inputs") or []

    if progress_cb:
        try: progress_cb({"kind": "resolving_inputs"})
        except: pass

    resolved_inputs = await _resolve_image_inputs(inputs or {}, input_paths, image_input_keys)
    
    # Render substitutions
    out_graph = json.loads(json.dumps(graph))
    for input_key, dotted in (input_paths or {}).items():
        if input_key not in resolved_inputs: continue
        parts = dotted.split(".")
        cursor = out_graph
        for p in parts[:-1]:
            if isinstance(cursor, dict) and p in cursor: cursor = cursor[p]
            else:
                cursor = None
                break
        if isinstance(cursor, dict): cursor[parts[-1]] = resolved_inputs[input_key]

    from api.comfyui import _execute_comfyui_graph
    return await _execute_comfyui_graph(out_graph, progress_cb=progress_cb, cancel_event=cancel_event)

def _workflow_job_lock(app) -> asyncio.Lock:
    lock = getattr(app.state, "workflow_job_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        app.state.workflow_job_lock = lock
    return lock

async def _execute_workflow_run_serialized(
    app, workflow_id: str, mode: str, inputs: dict,
    progress_cb=None, cancel_event: asyncio.Event | None = None
) -> dict:
    async with _workflow_job_lock(app):
        return await _execute_workflow_run(workflow_id, mode, inputs, progress_cb=progress_cb, cancel_event=cancel_event)

@router.post("/uploads/image", response_model=UploadImageResponse)
async def upload_image(file: UploadFile = File(...), _principal=Depends(require_auth)):
    mime = (file.content_type or "").lower()
    if mime not in _ALLOWED_IMAGE_MIMES:
        raise HTTPException(status_code=415, detail=f"Unsupported image type: {mime}. Allowed: {sorted(_ALLOWED_IMAGE_MIMES)}")
    original = file.filename or "upload"
    ext = os.path.splitext(original)[1].lower()
    if ext not in _ALLOWED_IMAGE_EXTS: ext = ".png"

    data = bytearray()
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk: break
        data.extend(chunk)
        if len(data) > UPLOADS_MAX_BYTES:
            raise HTTPException(status_code=413, detail=f"Upload exceeds {UPLOADS_MAX_BYTES} bytes")
    if not data: raise HTTPException(status_code=400, detail="Empty upload")

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    rel_name = f"{secrets.token_urlsafe(16)}{ext}"
    abs_path = os.path.join(UPLOADS_DIR, rel_name)
    with open(abs_path, "wb") as f: f.write(bytes(data))

    token = _sign_upload_token(rel_name, mime, original)
    return UploadImageResponse(token=token, filename=original, size_bytes=len(data), mime=mime, expires_in=UPLOADS_TOKEN_TTL_SECONDS)

@router.get("/uploads/image/{token}")
async def serve_upload(token: str):
    claims = _verify_upload_token(token)
    rel = str(claims.get("p") or "")
    mime = str(claims.get("m") or "application/octet-stream")
    if not rel or os.path.isabs(rel) or ".." in rel.split(os.sep):
        raise HTTPException(status_code=400, detail="Invalid upload reference")
    abs_path = os.path.join(UPLOADS_DIR, rel)
    if not os.path.isfile(abs_path): raise HTTPException(status_code=404, detail="Upload not found")
    with open(abs_path, "rb") as f: body = f.read()
    return Response(content=body, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})

@router.get("/comfyui-image/{token}")
async def comfyui_image(token: str):
    claims = _verify_comfyui_image_token(token)
    filename = str(claims.get("fn") or "")
    subfolder = str(claims.get("sub_") or "")
    type_ = str(claims.get("tp") or "output")
    if not filename: raise HTTPException(status_code=400, detail="Token missing filename")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            v = await client.get(f"{COMFYUI_URL}/view", params={"filename": filename, "subfolder": subfolder, "type": type_})
        except httpx.RequestError as e: raise HTTPException(status_code=502, detail=f"ComfyUI unreachable: {e}")
    if v.status_code != 200: raise HTTPException(status_code=v.status_code, detail="ComfyUI /view error")
    return Response(content=v.content, media_type=v.headers.get("content-type", "image/png"), headers={"Cache-Control": "private, max-age=600"})
