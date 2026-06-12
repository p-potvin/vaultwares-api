import json
import os
from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import uuid4
from api.config import WORKFLOWS_FILE
from threading import Lock

_storage_lock = Lock()

class Workflow(BaseModel):
    id: str
    name: str
    category: Optional[str] = None
    description: Optional[str] = None
    steps: list = Field(default_factory=list)
    pinned: bool = False
    pin: Optional[bool] = None
    favorite: bool = False
    lastRun: Optional[str] = None

class WorkflowCreateRequest(BaseModel):
    id: Optional[str] = None
    name: str
    category: Optional[str] = None
    description: Optional[str] = None
    steps: list = Field(default_factory=list)
    pinned: bool = False
    pin: Optional[bool] = None
    favorite: bool = False
    lastRun: Optional[str] = None

class WorkflowUpdateRequest(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[list] = None
    pinned: Optional[bool] = None
    pin: Optional[bool] = None
    favorite: Optional[bool] = None
    lastRun: Optional[str] = None

class WorkflowsExportRequest(BaseModel):
    ids: List[str]

class WorkflowsBackupRequest(BaseModel):
    pass

class WorkflowsRestoreRequest(BaseModel):
    data: list | dict

class WorkflowPinRequest(BaseModel):
    id: str
    pin: bool

class WorkflowFavoriteRequest(BaseModel):
    id: str
    favorite: bool

class WorkflowRunRequest(BaseModel):
    id: str
    mode: str = Field(default="local")
    callbackUrl: Optional[str] = None

class JobSubmitRequest(BaseModel):
    kind: str = Field(default="workflow_run")
    id: str
    mode: str = Field(default="local")
    callbackUrl: Optional[str] = None

class JobSummary(BaseModel):
    id: str
    kind: str
    status: str
    created_at: float
    updated_at: float
    requested_by: Optional[dict] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    progress: Optional[dict] = None

class JobDetail(JobSummary):
    payload: Optional[dict] = None
    ttl_seconds: Optional[int] = None

class ConfigUpdateRequest(BaseModel):
    modelsDir: Optional[str] = None
    preferredStorageProvider: Optional[str] = None
    apiMode: Optional[str] = None
    apiBase: Optional[str] = None
    themeIndex: Optional[int] = None
    runtimeProvider: Optional[str] = None
    localBridgeUrl: Optional[str] = None
    localComfyUrl: Optional[str] = None
    saveDirectory: Optional[str] = None
    facefusionCommand: Optional[str] = None
    scannedModels: Optional[dict] = None
    flowModelSelections: Optional[dict] = None
    updatedAt: Optional[str] = None

class ModelsDirRequest(BaseModel):
    dir_path: Optional[str] = None
    models_dir: Optional[str] = None
    modelsDir: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None

class RegisterResponse(BaseModel):
    username: str
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class FlowNodeIn(BaseModel):
    id: str
    type: str
    label: str = ""
    position: dict = Field(default_factory=dict)
    params: dict = Field(default_factory=dict)
    preset: Optional[str] = None

class FlowEdgeIn(BaseModel):
    id: str
    source: str
    sourceHandle: Optional[str] = None
    target: str
    targetHandle: Optional[str] = None

class FlowIn(BaseModel):
    id: str
    name: str
    nodes: List[FlowNodeIn]
    edges: List[FlowEdgeIn] = Field(default_factory=list)
    phase: int = 0
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None

class FlowRunRequest(BaseModel):
    flow: FlowIn

class ExecutionResultOut(BaseModel):
    nodeId: str
    output: str
    error: Optional[str] = None
    kind: Optional[str] = None
    imageUrl: Optional[str] = None
    imageUrls: Optional[List[str]] = None
    fileRef: Optional[str] = None
    data: Optional[dict] = None

class FlowRunResponse(BaseModel):
    results: List[ExecutionResultOut]

class PqcHandshakeRequest(BaseModel):
    client_public_key: str

class PqcHandshakeResponse(BaseModel):
    server_cipher_text: str
    algorithm: str = "ML-KEM-768"

class MeResponse(BaseModel):
    username: str
    is_admin: bool = False

class ApiKeyCreateRequest(BaseModel):
    name: Optional[str] = None
    scopes: Optional[list[str]] = None

class ApiKeyCreateResponse(BaseModel):
    api_key: str
    name: Optional[str] = None

class NetworkDiagnosticsResponse(BaseModel):
    served_by: str
    peer_ip: str
    client_ip: str
    effective_scheme: str
    via_trusted_proxy: bool
    trusted_client_ip: bool
    trusted_client_allowlist_active: bool
    gateway_required_public: bool
    gateway_header_present: bool
    forwarded_for: Optional[str] = None
    forwarded_proto: Optional[str] = None
    correlation_id: Optional[str] = None

class OllamaModelInfo(BaseModel):
    name: str
    size: int = 0
    modified_at: Optional[str] = None

class FlowsModelsResponse(BaseModel):
    models: List[OllamaModelInfo]
    default: str
    ollama_reachable: bool

class WorkflowValidationEntry(BaseModel):
    workflow_id: str
    verdict: str
    summary: str
    node_count: int
    error_count: int

class WorkflowValidationResponse(BaseModel):
    comfyui_reachable: bool
    cached_at: float
    results: List[WorkflowValidationEntry]

class UploadImageResponse(BaseModel):
    token: str
    filename: str
    size_bytes: int
    mime: str
    expires_in: int

class FaceswapSubmitRequest(BaseModel):
    source_face: str
    target_image: str

class FaceswapCompleteRequest(BaseModel):
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None

class OpenPayload(BaseModel):
    filename: Optional[str] = None
    folder: Optional[bool] = False

class ScrapePayload(BaseModel):
    url: str
    selector: Optional[str] = ""
    playwright: Optional[bool] = False
    batch_size: Optional[int] = 100

class DownloadPayload(BaseModel):
    url: str
    links: List[str]
    batch_size: Optional[int] = 5
    upscale_enabled: Optional[bool] = False
    upscale_model: Optional[str] = "4xNomos8k_atd"

def _next_workflow_id() -> str:
    return f"wf-{uuid4().hex[:12]}"

def _workflow_pin_value(pin: Optional[bool], pinned: Optional[bool]) -> bool:
    if pin is not None:
        return bool(pin)
    if pinned is not None:
        return bool(pinned)
    return False

def _workflow_to_dict(workflow: Workflow) -> dict:
    pin_value = _workflow_pin_value(workflow.pin, workflow.pinned)
    return {
        "id": workflow.id,
        "name": workflow.name,
        "category": workflow.category,
        "description": workflow.description,
        "steps": workflow.steps or [],
        "pinned": pin_value,
        "favorite": bool(workflow.favorite),
        "lastRun": workflow.lastRun,
    }

def _dict_to_workflow(data: dict) -> Workflow:
    pin_value = _workflow_pin_value(data.get("pin"), data.get("pinned"))
    return Workflow(
        id=data.get("id", _next_workflow_id()),
        name=data.get("name", "Untitled workflow"),
        category=data.get("category"),
        description=data.get("description"),
        steps=data.get("steps") or [],
        pinned=pin_value,
        pin=pin_value,
        favorite=bool(data.get("favorite", False)),
        lastRun=data.get("lastRun"),
    )

def _load_workflows_from_file() -> List[Workflow]:
    with _storage_lock:
        if not os.path.exists(WORKFLOWS_FILE):
            return []
        with open(WORKFLOWS_FILE, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    if not isinstance(raw, list):
        return []
    return [_dict_to_workflow(item) for item in raw if isinstance(item, dict)]

def _save_workflows_to_file(workflows: List[Workflow]) -> None:
    serialized = [_workflow_to_dict(workflow) for workflow in workflows]
    with _storage_lock:
        with open(WORKFLOWS_FILE, "w", encoding="utf-8") as handle:
            json.dump(serialized, handle, indent=2)
