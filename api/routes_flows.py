import re
import httpx
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Optional
from api.models import (
    FlowIn, FlowNodeIn, FlowEdgeIn, FlowRunRequest, FlowRunResponse,
    ExecutionResultOut, FlowsModelsResponse, OllamaModelInfo,
    WorkflowValidationResponse, WorkflowValidationEntry
)
from api.auth import require_auth
from api.config import (
    OLLAMA_DEFAULT_MODEL, OLLAMA_CALL_TIMEOUT_SECONDS, OLLAMA_URL,
    COMFYUI_OBJECT_INFO_CACHE_TTL
)
from api.database import db_available, WorkflowDB, workflowdb_to_pydantic
from api.models import _load_workflows_from_file
import logging

router = APIRouter()
logger = logging.getLogger("vaultwares.api")

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_VALIDATION_UI_ONLY = {
    "Note", "MarkdownNote", "Reroute", "RerouteNode", "PrimitiveNode",
    "PrimitiveBoolean", "PrimitiveInt", "PrimitiveFloat", "PrimitiveString",
    "PrimitiveStringMultiline", "Anchor",
    "Fast Groups Muter (rgthree)", "Fast Groups Bypasser (rgthree)",
    "Bookmark (rgthree)", "Label (rgthree)",
}
_object_info_cache = [0.0, {}]

def _flow_topo_sort(nodes: List[FlowNodeIn], edges: List[FlowEdgeIn]) -> List[FlowNodeIn]:
    by_id = {n.id: n for n in nodes}
    incoming = {n.id: set() for n in nodes}
    for e in edges:
        if e.target in incoming and e.source in by_id:
            incoming[e.target].add(e.source)
    order = []
    visited = set()

    def visit(node_id: str):
        if node_id in visited or node_id not in by_id:
            return
        visited.add(node_id)
        for dep in incoming[node_id]:
            visit(dep)
        order.append(by_id[node_id])

    for n in nodes:
        visit(n.id)
    return order

def _render_template(text: str, upstream_text: str) -> str:
    if not text: return upstream_text
    out = text
    for placeholder in ("{{input}}", "{{value}}", "{{context}}"):
        out = out.replace(placeholder, upstream_text)
    return out

def _strip_reasoning_tokens(text: str) -> str:
    if "<think>" not in text and "<THINK>" not in text: return text
    return _THINK_BLOCK_RE.sub("", text).lstrip()

async def _ollama_generate(model: str, prompt: str, system: str, temperature: float) -> str:
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if system: body["system"] = system

    async with httpx.AsyncClient(timeout=OLLAMA_CALL_TIMEOUT_SECONDS) as client:
        try:
            r = await client.post(f"{OLLAMA_URL}/api/generate", json=body)
        except httpx.ConnectError as e:
            raise RuntimeError(f"Cannot reach Ollama at {OLLAMA_URL}: {e}") from e
        except httpx.TimeoutException as e:
            raise RuntimeError(f"Ollama call timed out after {OLLAMA_CALL_TIMEOUT_SECONDS}s") from e

        if r.status_code == 404:
            raise RuntimeError(f"Model '{model}' not available in Ollama. Pull it with: ollama pull {model}")
        if r.status_code != 200:
            raise RuntimeError(f"Ollama returned {r.status_code}: {r.text[:200]}")
        data = r.json()
        return _strip_reasoning_tokens(str(data.get("response", "")).strip())

async def _get_comfyui_object_info() -> tuple[dict, bool]:
    from api.config import COMFYUI_URL
    cached_at, payload = _object_info_cache
    if payload and (time.time() - cached_at) < COMFYUI_OBJECT_INFO_CACHE_TTL:
        return payload, True
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{COMFYUI_URL}/object_info")
            r.raise_for_status()
            data = r.json()
        _object_info_cache[0] = time.time()
        _object_info_cache[1] = data
        return data, True
    except Exception as exc:
        logger.warning(f"validate: ComfyUI /object_info unreachable: {exc}")
        return payload, False

def _classify_validation(node_count: int, kinds: dict, node_errors: dict) -> str:
    if kinds.get("unknown_pack"): return "blocked_unknown_pack"
    if kinds.get("subgraph_uuid"): return "blocked_subgraph"
    if node_errors:
        for info in node_errors.values():
            for err in info.get("errors") or []:
                msg = (err.get("message") or "").lower()
                details = (err.get("details") or "").lower()
                if "value_not_in_list" in msg or "not in allowed list" in details:
                    return "blocked_missing_model"
        return "broken_wiring"
    if node_count == 0: return "empty"
    return "pass"

def _validate_comfyui_graph(graph: dict, object_info: dict, step: dict | None) -> dict:
    overridden = set()
    if step and isinstance(step, dict):
        ip = step.get("input_paths") or {}
        ii = step.get("image_inputs") or []
        if isinstance(ip, dict) and isinstance(ii, list):
            for key in ii:
                dotted = ip.get(key)
                if isinstance(dotted, str) and "." in dotted:
                    nid = dotted.split(".")[0]
                    field = dotted.split(".")[-1]
                    overridden.add((nid, field))

    kinds = {"ok": 0, "ui_only": 0, "subgraph_uuid": 0, "unknown_pack": 0}
    errors = []

    for nid, node in graph.items():
        if not isinstance(node, dict): continue
        ct = node.get("class_type")
        if not ct:
            errors.append({"node_id": nid, "class_type": "?", "message": "node has no class_type", "details": ""})
            continue
        if ct in _VALIDATION_UI_ONLY:
            kinds["ui_only"] += 1
            continue
        if _UUID_RE.match(ct):
            kinds["subgraph_uuid"] += 1
            continue
        schema = object_info.get(ct) if isinstance(object_info, dict) else None
        if not schema:
            kinds["unknown_pack"] += 1
            errors.append({
                "node_id": nid, "class_type": ct,
                "message": "missing_node_type",
                "details": f"Node class '{ct}' not registered with ComfyUI",
            })
            continue
        kinds["ok"] += 1

        required = schema.get("input", {}).get("required", {}) if isinstance(schema, dict) else {}
        if not isinstance(required, dict): continue
        inputs = node.get("inputs") or {}
        for name, spec in required.items():
            if (nid, name) in overridden: continue
            value = inputs.get(name)
            if isinstance(value, list) and len(value) == 2:
                src_id = str(value[0])
                if src_id not in graph:
                    errors.append({
                        "node_id": nid, "class_type": ct,
                        "message": "broken_link",
                        "details": f"Required input '{name}' linked to missing node '{src_id}'",
                    })
                continue
            if value is None:
                errors.append({
                    "node_id": nid, "class_type": ct,
                    "message": "missing_required",
                    "details": f"Required input '{name}' has no value",
                })
                continue
            spec_type = spec[0] if isinstance(spec, list) and spec else spec
            if isinstance(spec_type, list):
                if value not in spec_type:
                    errors.append({
                        "node_id": nid, "class_type": ct,
                        "message": "value_not_in_list",
                        "details": f"Input '{name}' value {value!r} not in allowed list",
                    })
                continue
            if isinstance(spec_type, str) and spec_type.upper() in (
                "MODEL", "CLIP", "VAE", "CONDITIONING", "LATENT", "IMAGE",
                "MASK", "CONTROL_NET", "UPSCALE_MODEL", "STYLE_MODEL",
                "INSIGHTFACE", "IPADAPTER",
            ):
                if value == "" or value is None:
                    errors.append({
                        "node_id": nid, "class_type": ct,
                        "message": "missing_required",
                        "details": f"Required wire '{name}' ({spec_type}) is empty",
                    })

    node_errors = {}
    for e in errors:
        node_errors.setdefault(e["node_id"], {"class_type": e["class_type"], "errors": []})
        node_errors[e["node_id"]]["errors"].append({"message": e["message"], "details": e["details"]})

    verdict = _classify_validation(len(graph), kinds, node_errors)
    if verdict == "pass": summary = f"{kinds['ok']} nodes, no validation errors"
    elif verdict == "blocked_unknown_pack": summary = f"{kinds['unknown_pack']} unknown node class(es) — custom pack not installed"
    elif verdict == "blocked_subgraph": summary = f"{kinds['subgraph_uuid']} subgraph reference(s) — needs expansion"
    elif verdict == "blocked_missing_model": summary = f"references model(s) not on disk"
    elif verdict == "broken_wiring": summary = f"{len(errors)} wiring issue(s)"
    else: summary = "empty graph"

    return {"verdict": verdict, "summary": summary, "node_count": len(graph), "kinds": kinds, "errors": errors[:20]}

@router.get("/flows/validation", response_model=WorkflowValidationResponse)
async def flows_validation(_principal=Depends(require_auth)):
    object_info, reachable = await _get_comfyui_object_info()
    if db_available():
        wfs = await WorkflowDB.all()
        workflows = [workflowdb_to_pydantic(w) for w in wfs]
    else:
        workflows = _load_workflows_from_file()

    results = []
    for wf in workflows:
        steps = wf.steps or []
        step = next((s for s in steps if isinstance(s, dict) and s.get("kind") == "comfyui_graph"), None)
        if not step:
            results.append(WorkflowValidationEntry(workflow_id=wf.id, verdict="empty", summary="no comfyui_graph step", node_count=0, error_count=0))
            continue
        graph = step.get("graph") or {}
        validation = _validate_comfyui_graph(graph, object_info, step)
        results.append(WorkflowValidationEntry(
            workflow_id=wf.id, verdict=validation["verdict"], summary=validation["summary"],
            node_count=validation["node_count"], error_count=len(validation["errors"])
        ))
    return WorkflowValidationResponse(comfyui_reachable=reachable, cached_at=_object_info_cache[0], results=results)

@router.get("/flows/models", response_model=FlowsModelsResponse)
async def flows_models(_principal=Depends(require_auth)):
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            r.raise_for_status()
            data = r.json()
        models = [
            OllamaModelInfo(name=m.get("name", ""), size=int(m.get("size", 0)), modified_at=m.get("modified_at"))
            for m in data.get("models", []) if m.get("name")
        ]
        return FlowsModelsResponse(models=models, default=OLLAMA_DEFAULT_MODEL, ollama_reachable=True)
    except Exception as exc:
        logger.warning(f"flows_models: Ollama unreachable: {exc}")
        return FlowsModelsResponse(models=[], default=OLLAMA_DEFAULT_MODEL, ollama_reachable=False)

async def _handle_model_call_ollama(node: FlowNodeIn, upstream_text: str) -> dict:
    model = str(node.params.get("model") or "") or OLLAMA_DEFAULT_MODEL
    temperature = float(node.params.get("temperature") or 0.7)
    system_prompt = _render_template(str(node.params.get("system") or ""), upstream_text)
    user_prompt = _render_template(str(node.params.get("prompt") or ""), upstream_text) or upstream_text
    if not user_prompt:
        raise RuntimeError("Ollama call has no prompt and no upstream input")
    output = await _ollama_generate(model, user_prompt, system_prompt, temperature)
    return {"output": output, "kind": "text"}

async def _handle_model_call_http(node: FlowNodeIn, upstream_text: str) -> dict:
    from api.config import HTTP_NODE_TIMEOUT_SECONDS
    url = str(node.params.get("url") or "")
    if not url: raise RuntimeError("http node requires params.url")
    method = str(node.params.get("method") or "GET").upper()
    headers = node.params.get("headers") or {}
    if not isinstance(headers, dict): raise RuntimeError("http node params.headers must be an object")
    body = node.params.get("body")
    if isinstance(body, str): body = _render_template(body, upstream_text)

    async with httpx.AsyncClient(timeout=HTTP_NODE_TIMEOUT_SECONDS) as client:
        try:
            if isinstance(body, (dict, list)): r = await client.request(method, url, headers=headers, json=body)
            elif body is None: r = await client.request(method, url, headers=headers)
            else: r = await client.request(method, url, headers=headers, content=str(body))
        except httpx.TimeoutException as e: raise RuntimeError(f"HTTP {method} {url} timed out") from e
        except httpx.RequestError as e: raise RuntimeError(f"HTTP {method} {url} failed: {e}") from e

    if r.status_code >= 400: raise RuntimeError(f"HTTP {method} {url} -> {r.status_code}: {r.text[:200]}")
    ctype = (r.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        try: parsed = r.json()
        except: return {"output": r.text, "kind": "text"}
        return {"output": r.text, "kind": "json", "data": parsed if isinstance(parsed, dict) else {"value": parsed}}
    return {"output": r.text, "kind": "text"}

async def _handle_comfyui_workflow(node: FlowNodeIn, upstream_text: str) -> dict:
    from api.config import COMFYUI_JOB_MAX_WAIT_SECONDS, COMFYUI_JOB_POLL_INTERVAL_SECONDS
    from api.routes_jobs import _new_job, _write_job, _queue_job, _read_job
    from api.app import app
    workflow_id = str(node.params.get("workflow_id") or "")
    if not workflow_id: raise RuntimeError("comfyui_workflow node requires params.workflow_id")
    mode = str(node.params.get("mode") or "local")

    if db_available():
        try: await WorkflowDB.get(id=workflow_id)
        except DoesNotExist: raise RuntimeError(f"ComfyUI workflow '{workflow_id}' not found in pipelines DB")
    else:
        wfs = _load_workflows_from_file()
        if not any(w.id == workflow_id for w in wfs): raise RuntimeError(f"ComfyUI workflow '{workflow_id}' not found in workflows.json")

    raw_inputs = node.params.get("inputs") if isinstance(node.params.get("inputs"), dict) else {}
    flow_inputs = {}
    for k, v in (raw_inputs or {}).items():
        if isinstance(v, str): flow_inputs[k] = _render_template(v, upstream_text)
        else: flow_inputs[k] = v

    job_payload = {
        "id": workflow_id, "mode": mode, "inputs": flow_inputs,
        "callbackUrl": node.params.get("callbackUrl") or node.params.get("callback_url"),
        "correlationId": node.params.get("correlationId") or node.params.get("cID"),
    }
    job_payload = {k: v for k, v in job_payload.items() if v}
    job = _new_job(kind="workflow_run", payload=job_payload, requested_by={"user": "vault-flows", "via": "/flows/run"})
    _write_job(job)
    _queue_job(app, job)

    job_id = job["id"]
    deadline = time.time() + COMFYUI_JOB_MAX_WAIT_SECONDS
    while time.time() < deadline:
        await asyncio.sleep(COMFYUI_JOB_POLL_INTERVAL_SECONDS)
        current = _read_job(job_id)
        if not current: raise RuntimeError(f"Job {job_id} disappeared from job store")
        status = current.get("status")
        if status == "succeeded":
            result = current.get("result") or {}
            image_url = result.get("image_url") or result.get("imageUrl")
            image_urls = result.get("image_urls") or result.get("imageUrls")
            if not isinstance(image_urls, list): image_urls = [image_url] if image_url else []
            payload = {"output": result.get("summary") or (f"[ComfyUI workflow {workflow_id} complete]" if not image_url else ""), "data": result if isinstance(result, dict) else {"value": result}}
            if image_url:
                payload["kind"] = "image"
                payload["imageUrl"] = image_url
                if image_urls: payload["imageUrls"] = image_urls
            else:
                payload["kind"] = "job_result"
            return payload
        if status == "failed": raise RuntimeError(current.get("error") or "ComfyUI workflow failed")
        if status == "canceled": raise RuntimeError("ComfyUI workflow was canceled")
    raise RuntimeError(f"ComfyUI workflow '{workflow_id}' timed out after {COMFYUI_JOB_MAX_WAIT_SECONDS}s")

async def _handle_model_call(node: FlowNodeIn, upstream_text: str) -> dict:
    provider = str(node.params.get("provider") or "ollama").lower()
    if provider == "ollama": return await _handle_model_call_ollama(node, upstream_text)
    if provider == "comfyui": return await _handle_comfyui_workflow(node, upstream_text)
    if provider == "http": return await _handle_model_call_http(node, upstream_text)
    raise RuntimeError(f"Unknown model_call provider '{provider}'. Supported: ollama, comfyui, http")

def _forward_upstream_payload(node_id: str, edges: List[FlowEdgeIn], results: List[ExecutionResultOut]) -> dict:
    upstream_ids = [e.source for e in edges if e.target == node_id]
    by_id = {r.nodeId: r for r in results}
    for src in upstream_ids:
        upstream = by_id.get(src)
        if upstream and not upstream.error:
            return {
                "output": upstream.output, "kind": upstream.kind or "text",
                "imageUrl": upstream.imageUrl, "imageUrls": upstream.imageUrls,
                "fileRef": upstream.fileRef, "data": upstream.data
            }
    return {"output": "", "kind": "text"}

@router.post("/flows/run", response_model=FlowRunResponse)
async def flows_run(req: FlowRunRequest, _principal=Depends(require_auth)):
    import asyncio
    nodes = list(req.flow.nodes)
    edges = list(req.flow.edges)
    sorted_nodes = _flow_topo_sort(nodes, edges)

    context = {}
    results = []

    for node in sorted_nodes:
        upstream_outputs = [context[e.source] for e in edges if e.target == node.id and e.source in context]
        upstream_text = "\n\n".join(s for s in upstream_outputs if s)

        try:
            if node.type == "input":
                raw = (node.params.get("value") or node.params.get("prompt") or node.params.get("topic") or node.params.get("text") or "")
                payload = {"output": str(raw), "kind": "text"}
            elif node.type == "image_input":
                ref = str(node.params.get("image_ref") or "")
                preview = str(node.params.get("preview_url") or "")
                fname = str(node.params.get("filename") or "")
                if not ref: raise RuntimeError("image_input node has no uploaded file")
                payload = {"output": ref, "kind": "image", "imageUrl": preview or None, "data": {"image_ref": ref, "filename": fname}}
            elif node.type == "llm":
                payload = await _handle_model_call_ollama(node, upstream_text)
            elif node.type == "model_call":
                payload = await _handle_model_call(node, upstream_text)
            elif node.type == "comfyui_workflow":
                payload = await _handle_comfyui_workflow(node, upstream_text)
            elif node.type == "transform":
                template = str(node.params.get("template") or "{{input}}")
                payload = {"output": _render_template(template, upstream_text), "kind": "text"}
            elif node.type in ("display", "output"):
                payload = _forward_upstream_payload(node.id, edges, results)
            else:
                payload = {"output": upstream_text, "kind": "text"}

            context[node.id] = payload.get("output", "") or ""
            results.append(ExecutionResultOut(nodeId=node.id, **payload))
        except Exception as exc:
            err = str(exc)
            logger.warning(f"flows_run: node {node.id} ({node.type}) failed: {err}")
            context[node.id] = ""
            results.append(ExecutionResultOut(nodeId=node.id, output="", error=err))

    return FlowRunResponse(results=results)
