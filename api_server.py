
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import HTMLResponse
import os
import json
from threading import Lock
from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import uuid4
import hashlib
import time
from collections import defaultdict, deque
import ipaddress
import secrets
import string

import asyncio
from dotenv import load_dotenv
from db import init_db, close_db, UserAccount, ApiKey
from tortoise import Tortoise
import logging
from jose import jwt, JWTError
from passlib.context import CryptContext

# Load .env before reading environment-backed settings.
load_dotenv()

from app.security.ml_kem import VaultMLKEM

# --- Configurable Settings ---
AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "1") == "1"
DEFAULT_MODELS_DIR = os.environ.get("DEFAULT_MODELS_DIR") or os.environ.get("MODELS_DIR")

JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ISSUER = os.environ.get("JWT_ISSUER", "vault-server")
JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE", "vaultwares")
JWT_TTL_SECONDS = int(os.environ.get("JWT_TTL_SECONDS", "900"))
API_KEY_PEPPER = os.environ.get("API_KEY_PEPPER") or JWT_SECRET

BOOTSTRAP_ADMIN_USERNAME = os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "")
BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
BOOTSTRAP_ADMIN_IS_DISABLED = os.environ.get("BOOTSTRAP_ADMIN_IS_DISABLED", "0") == "1"

REQUIRE_HTTPS = os.environ.get("REQUIRE_HTTPS", "1") == "1"
ALLOW_HTTP_TRUSTED = os.environ.get("ALLOW_HTTP_TRUSTED", "1") == "1"

# Exact origins only by default (no wildcards). Use stable Vercel alias domains.
ALLOWED_ORIGINS = set(
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
)

TAILSCALE_CIDRS = [
    cidr.strip()
    for cidr in os.environ.get("TAILSCALE_CIDRS", "100.64.0.0/10,fd7a:115c:a1e0::/48").split(",")
    if cidr.strip()
]
_tailscale_networks = []
for _cidr in TAILSCALE_CIDRS:
    try:
        _tailscale_networks.append(ipaddress.ip_network(_cidr, strict=False))
    except ValueError:
        # Ignore invalid CIDRs to avoid startup hard-fail; the API will treat the network as untrusted.
        pass

TRUSTED_PROXY_CIDRS = [
    cidr.strip()
    for cidr in os.environ.get("TRUSTED_PROXY_CIDRS", "127.0.0.1/32,::1/128").split(",")
    if cidr.strip()
]
_trusted_proxy_networks = []
for _cidr in TRUSTED_PROXY_CIDRS:
    try:
        _trusted_proxy_networks.append(ipaddress.ip_network(_cidr, strict=False))
    except ValueError:
        pass

RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "1") == "1"
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_MAX_PUBLIC = int(os.environ.get("RATE_LIMIT_MAX_PUBLIC", "120"))
RATE_LIMIT_MAX_TRUSTED = int(os.environ.get("RATE_LIMIT_MAX_TRUSTED", "1200"))
MAINTENANCE_MODE = os.environ.get("MAINTENANCE_MODE", "0") == "1"

GATEWAY_REQUIRED_PUBLIC = os.environ.get("GATEWAY_REQUIRED_PUBLIC", "1") == "1"
GATEWAY_SHARED_SECRET = os.environ.get("GATEWAY_SHARED_SECRET", "")
GATEWAY_HEADER_NAME = os.environ.get("GATEWAY_HEADER_NAME", "x-vw-gateway-secret").lower()


# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vaultwares.api")

app = FastAPI(title="Vaultwares Workflow API", description="API for managing workflows, favorites, backup, NIM integration, and storage.", version="0.2.0")

# --- CORS ---
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:4173").split(",")
    if origin.strip()
]
_cors_allow_origins = sorted(set(CORS_ORIGINS) | ALLOWED_ORIGINS) if (CORS_ORIGINS or ALLOWED_ORIGINS) else []

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bearer_scheme = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def _is_trusted_client_ip(ip: Optional[str]) -> bool:
    if not ip:
        return False
    if ip == "::1" or ip.startswith("127."):
        return True
    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for net in _tailscale_networks:
        if ip_obj in net:
            return True
    return False

def _effective_scheme(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-proto")
    if forwarded:
        return forwarded.split(",")[0].strip().lower()
    return request.url.scheme.lower()

def _get_client_ip(request: Request) -> Optional[str]:
    """
    Uses X-Forwarded-For only when the immediate peer is a trusted proxy.
    This prevents public callers from spoofing their source IP.
    """
    peer_ip = request.client.host if request.client else None
    if not peer_ip:
        return None
    try:
        peer_obj = ipaddress.ip_address(peer_ip)
    except ValueError:
        return peer_ip

    is_trusted_proxy = any(peer_obj in net for net in _trusted_proxy_networks)
    if not is_trusted_proxy:
        # Client connected directly to server; ignore X-Forwarded-For completely
        return peer_ip

    xff = request.headers.get("x-forwarded-for", "")
    if not xff:
        return peer_ip

    # Iterate right-to-left to find the first untrusted IP
    ips = [ip.strip() for ip in xff.split(",") if ip.strip()]
    for ip_str in reversed(ips):
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            if not any(ip_obj in net for net in _trusted_proxy_networks):
                return ip_str
        except ValueError:
            # If it's an invalid IP format, treat it as the untrusted client
            return ip_str

    # Fallback to leftmost if all are trusted
    return ips[0] if ips else peer_ip

def _origin_allowed(origin: str) -> bool:
    if not origin:
        return False
    if origin in ALLOWED_ORIGINS:
        return True
    if origin in _cors_allow_origins:
        return True
    return False

def _gateway_secret_valid(request: Request) -> bool:
    if not GATEWAY_SHARED_SECRET:
        return False
    provided = request.headers.get(GATEWAY_HEADER_NAME, "")
    if not provided:
        return False
    return secrets.compare_digest(provided, GATEWAY_SHARED_SECRET)

def _hash_api_key(raw_key: str) -> str:
    if not raw_key:
        return ""
    if not API_KEY_PEPPER:
        raise HTTPException(status_code=500, detail="API key pepper is not configured")
    hasher = hashlib.sha256()
    hasher.update((API_KEY_PEPPER + raw_key).encode("utf-8"))
    return hasher.hexdigest()

def _verify_api_key(raw_key: str, hashed_key: str) -> bool:
    if not raw_key or not hashed_key:
        return False
    if not API_KEY_PEPPER:
        raise HTTPException(status_code=500, detail="API key pepper is not configured")
    if hashed_key.startswith("$2"):
        # Legacy bcrypt hash
        return pwd_context.verify(API_KEY_PEPPER + raw_key, hashed_key)
    expected = _hash_api_key(raw_key)
    return secrets.compare_digest(expected, hashed_key)

def _create_access_token(user_id: int, username: str, is_admin: bool) -> str:
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT secret is not configured")
    now = int(time.time())
    payload = {
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": now + max(60, JWT_TTL_SECONDS),
        "sub": f"user:{user_id}",
        "uid": user_id,
        "usr": username,
        "adm": bool(is_admin),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def _get_localized_unauthorized_msg(request: Request) -> str:
    accept_language = request.headers.get("accept-language", "")
    if not accept_language:
        return "Unauthorized"

    # Parse the Accept-Language header
    languages = [lang.split(';')[0].strip().lower() for lang in accept_language.split(',')]

    for lang in languages:
        if lang.startswith("fr"):
            return "Non autorisé"
        elif lang.startswith("es"):
            return "No autorizado"

    return "Unauthorized"

async def _get_user_from_token(token: str, request: Request) -> UserAccount:
    detail_msg = _get_localized_unauthorized_msg(request)

    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT secret is not configured")
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
        )
    except JWTError:
        raise HTTPException(status_code=403, detail=detail_msg)

    user_id = payload.get("uid")
    if not isinstance(user_id, int):
        raise HTTPException(status_code=403, detail=detail_msg)

    user = await UserAccount.get_or_none(id=user_id)
    if not user or user.is_disabled:
        raise HTTPException(status_code=403, detail=detail_msg)
    return user

async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    if not AUTH_ENABLED:
        return {"kind": "anonymous"}

    client_ip = _get_client_ip(request)
    is_trusted_ip = _is_trusted_client_ip(client_ip)

    token = credentials.credentials if credentials else None
    if token:
        user = await _get_user_from_token(token, request)
        return {"kind": "user", "user": user}

    api_key = request.headers.get("x-api-key", "")
    if api_key and is_trusted_ip:
        key_row = None
        if api_key.startswith("vwk_"):
            parts = api_key.split("_")
            if len(parts) >= 3:
                try:
                    key_id = int(parts[1])
                    key_row = await ApiKey.get_or_none(id=key_id)
                except ValueError:
                    pass

        if key_row:
            if not _verify_api_key(api_key, key_row.key_hash):
                key_row = None

        if not key_row and not api_key.startswith("vwk_"):
            key_hash = _hash_api_key(api_key)
            key_row = await ApiKey.get_or_none(key_hash=key_hash)

        if not key_row or key_row.is_revoked:
            detail_msg = _get_localized_unauthorized_msg(request)
            raise HTTPException(status_code=403, detail=detail_msg)
        return {"kind": "api_key", "api_key": key_row}

    detail_msg = _get_localized_unauthorized_msg(request)
    raise HTTPException(status_code=403, detail=detail_msg)

_rate_state = defaultdict(lambda: deque())
RATE_LIMIT_MAX_STATE_SIZE = 10000

@app.middleware("http")
async def gate_requests(request: Request, call_next):
    if len(_rate_state) > RATE_LIMIT_MAX_STATE_SIZE:
        # Prevent clearing the whole dictionary to avoid rate limit bypass
        # Remove oldest element
        oldest_key = next(iter(_rate_state))
        _rate_state.pop(oldest_key, None)

    client_ip = _get_client_ip(request) or ""
    is_trusted_ip = _is_trusted_client_ip(client_ip)

    if MAINTENANCE_MODE and not is_trusted_ip:
        raise HTTPException(status_code=503, detail="Temporarily unavailable")

    scheme = _effective_scheme(request)
    if REQUIRE_HTTPS and scheme != "https" and not (ALLOW_HTTP_TRUSTED and is_trusted_ip):
        raise HTTPException(status_code=426, detail="HTTPS required")

    origin = request.headers.get("origin", "")
    if not is_trusted_ip:
        if GATEWAY_REQUIRED_PUBLIC:
            if not GATEWAY_SHARED_SECRET:
                raise HTTPException(status_code=500, detail="Gateway secret is not configured")
            if not _gateway_secret_valid(request):
                raise HTTPException(status_code=403, detail="Forbidden source")

        if origin:
            if not _origin_allowed(origin):
                raise HTTPException(status_code=403, detail="Forbidden origin")
        else:
            raise HTTPException(status_code=403, detail="Forbidden source")

    if RATE_LIMIT_ENABLED:
        now = time.time()
        key = f"{client_ip}:{origin}" if origin else client_ip
        bucket = _rate_state[key]
        while bucket and (now - bucket[0]) > RATE_LIMIT_WINDOW_SECONDS:
            bucket.popleft()
        limit = RATE_LIMIT_MAX_TRUSTED if is_trusted_ip else RATE_LIMIT_MAX_PUBLIC
        if len(bucket) >= limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        bucket.append(now)

    correlation_id = "c" + "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    request.state.correlation_id = correlation_id

    response = await call_next(request)

    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Correlation-Id"] = correlation_id

    return response

# --- Models ---
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
    mode: str  # 'local' or 'nim'

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

# --- Persistent JSON Storage ---
VAULTWARES_HOME_CSS = """
body { background: #181c24; color: #f3f6fa; font-family: 'Segoe UI', Arial, sans-serif; text-align: center; margin: 0; padding: 0; }
.logo { margin-top: 48px; }
.vault {
    display: inline-block;
    margin: 0 auto 24px auto;
    width: 120px;
    height: 120px;
    background: linear-gradient(135deg, #2e3a4e 60%, #4e7ad2 100%);
    border-radius: 50%;
    box-shadow: 0 4px 32px #0008;
    position: relative;
}
.vault:before {
    content: '';
    display: block;
    position: absolute;
    left: 50%; top: 50%;
    width: 60px; height: 60px;
    background: #232b3a;
    border-radius: 50%;
    transform: translate(-50%, -50%);
    box-shadow: 0 0 0 8px #4e7ad2;
}
h1 { font-size: 2.5rem; margin: 24px 0 8px 0; letter-spacing: 2px; }
.subtitle { color: #b0c4e7; font-size: 1.2rem; margin-bottom: 32px; }
.links a {
    display: inline-block;
    margin: 12px 16px;
    padding: 12px 28px;
    background: #4e7ad2;
    color: #fff;
    border-radius: 6px;
    text-decoration: none;
    font-weight: 600;
    font-size: 1.1rem;
    transition: background 0.2s;
}
.links a:hover { background: #355a8a; }
.apidoc-link {
    margin-top: 40px;
    color: #b0c4e7;
    font-size: 0.95rem;
}
.apidoc-link a {
    color: #fff;
    text-decoration: underline;
}
"""

WORKFLOWS_FILE = os.environ.get("WORKFLOWS_FILE", "workflows.json")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
API_KEY_REG_URL = os.environ.get("API_KEY_REG_URL", f"{FRONTEND_URL.rstrip('/')}/register")

_storage_lock = Lock()
APP_CONFIG = {
    "modelsDir": DEFAULT_MODELS_DIR or "",
    "preferredStorageProvider": "other",
    "apiMode": "remote-with-local-fallback",
    "apiBase": "",
    "themeIndex": 0,
    "runtimeProvider": "local-bridge" if DEFAULT_MODELS_DIR else "browser-local",
    "localBridgeUrl": "http://127.0.0.1:8484",
    "localComfyUrl": "http://127.0.0.1:8188",
    "saveDirectory": "",
    "facefusionCommand": "facefusion",
    "scannedModels": {
        "scannedAt": "",
        "source": "none",
        "modelsDir": DEFAULT_MODELS_DIR or "",
        "warnings": [],
        "categories": {
            "checkpoints": [],
            "loras": [],
            "insightface": [],
            "hyperswap": [],
            "reactorFaces": [],
            "facerestoreModels": [],
            "ultralytics": [],
            "sams": [],
        },
    },
    "flowModelSelections": {
        "imageCaptioning": {"captionModel": "", "captionAdapter": ""},
        "loraTraining": {"baseModel": ""},
        "videoFaceSwap": {
            "swapModel": "",
            "alternateSwapModel": "",
            "faceModel": "",
            "restoreModel": "",
            "detectorModel": "",
        },
    },
}

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


@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <html>
    <head>
        <title>Vaultwares Pipelines</title>
        <style>{css}</style>
    </head>
    <body>
        <div class="logo">
            <div class="vault"></div>
        </div>
        <h1>Vaultwares Pipelines</h1>
        <div class="subtitle">Multi-Agent AI Workflow Platform</div>
        <p>Welcome to <b>Vaultwares</b>!<br>
        Access the full dashboard, explore workflows, and manage your AI pipelines.</p>
        <div class="links">
            <a href="{frontend_url}" target="_blank">Go to Frontend Dashboard</a>
            <a href="{api_key_url}" target="_blank">Register for an API Key</a>
        </div>
        <p class="apidoc-link">API documentation: <a href='/docs'>/docs</a></p>
    </body>
    </html>
    """.format(css=VAULTWARES_HOME_CSS, frontend_url=FRONTEND_URL, api_key_url=API_KEY_REG_URL)


# --- DB Setup ---
from tortoise import fields, models
from tortoise.exceptions import DoesNotExist
DB_URL = os.getenv("DB_URL", "postgres://postgres:postgres@localhost:5432/vaultwares")

class WorkflowDB(models.Model):
    id = fields.CharField(pk=True, max_length=64)
    name = fields.CharField(max_length=255)
    category = fields.CharField(max_length=255, null=True)
    steps = fields.JSONField(null=True)
    pinned = fields.BooleanField(default=False)
    favorite = fields.BooleanField(default=False)

    class Meta:
        table = "workflows"

def workflowdb_to_pydantic(wf: WorkflowDB) -> Workflow:
    pin_value = bool(wf.pinned)
    return Workflow(
        id=wf.id,
        name=wf.name,
        category=wf.category,
        description=None,
        steps=wf.steps or [],
        pinned=pin_value,
        pin=pin_value,
        favorite=wf.favorite,
        lastRun=None,
    )


# --- Tortoise ORM Initialization State ---
_tortoise_initialized = False

@app.on_event("startup")
async def startup_event():
    global _tortoise_initialized
    try:
        await init_db(DB_URL)
        _tortoise_initialized = True
        logger.info("Tortoise ORM initialized successfully.")

        # Optional bootstrap for initial setup. Use only on trusted networks.
        if BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD:
            existing = await UserAccount.get_or_none(username=BOOTSTRAP_ADMIN_USERNAME)
            if not existing:
                await UserAccount.create(
                    username=BOOTSTRAP_ADMIN_USERNAME,
                    password_hash=pwd_context.hash(BOOTSTRAP_ADMIN_PASSWORD),
                    is_admin=True,
                    is_disabled=BOOTSTRAP_ADMIN_IS_DISABLED,
                )
                logger.info("Bootstrapped initial admin user.")
    except Exception as e:
        logger.error(f"Failed to initialize Tortoise ORM: {e}")
        _tortoise_initialized = False

@app.on_event("shutdown")
async def shutdown_event():
    try:
        await close_db()
        logger.info("Tortoise ORM connections closed.")
    except Exception as e:
        logger.error(f"Error closing Tortoise ORM connections: {e}")


# --- Endpoints ---

def db_available() -> bool:
    return bool(_tortoise_initialized and Tortoise._inited)

@app.post("/security/pqc/handshake", response_model=PqcHandshakeResponse)
async def pqc_handshake(payload: PqcHandshakeRequest):
    """
    Experimental PQC Handshake (ML-KEM).
    """
    try:
        result = VaultMLKEM.encapsulate(payload.client_public_key)
        return PqcHandshakeResponse(
            server_cipher_text=result["cipher_text"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request):
    if not AUTH_ENABLED:
        raise HTTPException(status_code=400, detail="Auth is disabled")
    if not db_available():
        raise HTTPException(status_code=503, detail="Database unavailable")

    client_ip = _get_client_ip(request)
    if not _is_trusted_client_ip(client_ip):
        # Public internet is browser-origin gated by middleware; this is a last defense-in-depth check.
        origin = request.headers.get("origin", "")
        if not origin or not _origin_allowed(origin):
            raise HTTPException(status_code=403, detail="Forbidden source")

    user = await UserAccount.get_or_none(username=payload.username)
    if not user or user.is_disabled:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not pwd_context.verify(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = _create_access_token(user.id, user.username, bool(user.is_admin))
    return LoginResponse(access_token=token, expires_in=max(60, JWT_TTL_SECONDS))

@app.get("/auth/me", response_model=MeResponse)
async def me(principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user: UserAccount = principal["user"]
    return MeResponse(username=user.username, is_admin=bool(user.is_admin))

@app.post("/auth/api-keys", response_model=ApiKeyCreateResponse)
async def create_api_key(request: Request, payload: ApiKeyCreateRequest, principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user: UserAccount = principal["user"]
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")

    client_ip = _get_client_ip(request)
    if not _is_trusted_client_ip(client_ip):
        raise HTTPException(status_code=403, detail="Trusted network required")

    # Create the API key record first to get the auto-incremented ID
    # Use a temporary placeholder hash, since the unique constraint requires it
    temp_hash = "tmp_" + secrets.token_urlsafe(16)
    obj = await ApiKey.create(name=payload.name, key_hash=temp_hash, scopes=payload.scopes or [])

    # Generate the actual raw key with the ID embedded
    raw_key = f"vwk_{obj.id}_{secrets.token_urlsafe(32)}"
    key_hash = _hash_api_key(raw_key)

    # Update the record with the real hash
    obj.key_hash = key_hash
    await obj.save()

    return ApiKeyCreateResponse(api_key=raw_key, name=payload.name)

@app.get("/workflows", response_model=List[Workflow])
async def list_workflows(_principal=Depends(require_auth)):
    if db_available():
        workflows = await WorkflowDB.all()
        return [workflowdb_to_pydantic(wf) for wf in workflows]
    return _load_workflows_from_file()


@app.post("/workflows", response_model=Workflow)
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


@app.put("/workflows/{id}", response_model=Workflow)
async def update_workflow(id: str, wf: WorkflowUpdateRequest, _principal=Depends(require_auth)):
    if db_available():
        try:
            obj = await WorkflowDB.get(id=id)
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="Workflow not found")
        if wf.name is not None:
            obj.name = wf.name
        if wf.category is not None:
            obj.category = wf.category
        if wf.steps is not None:
            obj.steps = wf.steps
        if wf.favorite is not None:
            obj.favorite = wf.favorite
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


@app.delete("/workflows/{id}")
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


@app.post("/workflows/export")
async def export_workflows(req: WorkflowsExportRequest, _principal=Depends(require_auth)):
    if db_available():
        workflows = await WorkflowDB.filter(id__in=req.ids)
        return [workflowdb_to_pydantic(wf) for wf in workflows]
    workflows = _load_workflows_from_file()
    if not req.ids:
        return workflows
    target_ids = set(req.ids)
    return [workflow for workflow in workflows if workflow.id in target_ids]


@app.post("/workflows/backup")
async def backup_workflows(_: WorkflowsBackupRequest, _principal=Depends(require_auth)):
    if db_available():
        workflows = await WorkflowDB.all()
        return [workflowdb_to_pydantic(wf) for wf in workflows]
    return _load_workflows_from_file()


@app.post("/workflows/restore")
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


@app.post("/workflows/pin")
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


@app.post("/workflows/favorite")
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


@app.post("/workflows/run")
async def run_workflow(req: WorkflowRunRequest, _principal=Depends(require_auth)):
    if db_available():
        try:
            await WorkflowDB.get(id=req.id)
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="Workflow not found")
    else:
        workflows = _load_workflows_from_file()
        if not any(item.id == req.id for item in workflows):
            raise HTTPException(status_code=404, detail="Workflow not found")
    # NIM VM integration placeholder
    if req.mode == "nim":
        return {"id": req.id, "mode": req.mode, "status": "nim_vm_placeholder", "message": "NIM VM integration not yet implemented."}
    return {"id": req.id, "mode": req.mode, "status": "started"}

# --- Persistent Storage Placeholders ---
@app.post("/storage/google-drive/upload")
def upload_google_drive(_principal=Depends(require_auth)):
    # Placeholder for Google Drive upload
    return {"status": "placeholder", "message": "Google Drive upload not implemented."}

@app.post("/storage/dropbox/upload")
def upload_dropbox(_principal=Depends(require_auth)):
    # Placeholder for Dropbox upload
    return {"status": "placeholder", "message": "Dropbox upload not implemented."}

@app.post("/storage/icloud/upload")
def upload_icloud(_principal=Depends(require_auth)):
    # Placeholder for iCloud upload
    return {"status": "placeholder", "message": "iCloud upload not implemented."}

@app.post("/storage/other/upload")
def upload_other(_principal=Depends(require_auth)):
    # Placeholder for other storage providers
    return {"status": "placeholder", "message": "Other storage provider upload not implemented."}

# --- App Config ---
@app.get("/config")
def get_config(_principal=Depends(require_auth)):
    return APP_CONFIG

@app.post("/config")
def update_config(req: ConfigUpdateRequest, _principal=Depends(require_auth)):
    payload = req.model_dump(exclude_none=True)
    APP_CONFIG.update(payload)
    if "modelsDir" in payload:
        global DEFAULT_MODELS_DIR
        DEFAULT_MODELS_DIR = payload["modelsDir"]
    return APP_CONFIG

# --- Models Directory Config ---
@app.get("/config/models-dir")
def get_models_dir(_principal=Depends(require_auth)):
    value = APP_CONFIG.get("modelsDir") or DEFAULT_MODELS_DIR or ""
    return {"models_dir": value, "dir_path": value, "modelsDir": value}

@app.post("/config/models-dir")
def set_models_dir(req: ModelsDirRequest, _principal=Depends(require_auth)):
    global DEFAULT_MODELS_DIR
    resolved = req.dir_path or req.models_dir or req.modelsDir
    if resolved is None:
        raise HTTPException(status_code=422, detail="Expected one of dir_path, models_dir, or modelsDir")
    DEFAULT_MODELS_DIR = resolved
    APP_CONFIG["modelsDir"] = resolved
    return {"models_dir": DEFAULT_MODELS_DIR, "dir_path": DEFAULT_MODELS_DIR, "modelsDir": DEFAULT_MODELS_DIR}




# --- Script Entrypoint ---
if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("API_HOST", "127.0.0.1")
    port = int(os.environ.get("API_PORT", "9001"))
    reload = os.environ.get("UVICORN_RELOAD", "1") == "1"
    uvicorn.run("api_server:app", host=host, port=port, reload=reload)
