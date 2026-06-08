
from fastapi import FastAPI, HTTPException, Depends, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
import os
import json
from threading import Lock
from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import uuid4
import hashlib
import re
import time
from collections import defaultdict, deque
import ipaddress
import secrets
import socket

import asyncio
import httpx
from dataclasses import dataclass
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


def _env_int_with_floor(name: str, default: int, minimum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return max(value, minimum)

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

TRUSTED_CLIENT_IPS = [
    ip.strip()
    for ip in os.environ.get("TRUSTED_CLIENT_IPS", "").split(",")
    if ip.strip()
]
_trusted_client_ips = []
for _ip in TRUSTED_CLIENT_IPS:
    try:
        _trusted_client_ips.append(ipaddress.ip_address(_ip))
    except ValueError:
        pass

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
RATE_LIMIT_MAX_PUBLIC = _env_int_with_floor("RATE_LIMIT_MAX_PUBLIC", 3000, 3000)
RATE_LIMIT_MAX_TRUSTED = _env_int_with_floor("RATE_LIMIT_MAX_TRUSTED", 30000, 30000)
MAINTENANCE_MODE = os.environ.get("MAINTENANCE_MODE", "0") == "1"

GATEWAY_REQUIRED_PUBLIC = os.environ.get("GATEWAY_REQUIRED_PUBLIC", "1") == "1"
GATEWAY_SHARED_SECRET = os.environ.get("GATEWAY_SHARED_SECRET", "")
GATEWAY_HEADER_NAME = os.environ.get("GATEWAY_HEADER_NAME", "x-vw-gateway-secret").lower()

# ---------------------------------------------------------------------------
# Job queue (in-process, durable state on disk)
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_DIR = os.environ.get("JOBS_DIR") or os.path.join(BASE_DIR, "data", "jobs")
JOB_QUEUE_MAX_PENDING = int(os.environ.get("JOB_QUEUE_MAX_PENDING", "200"))
JOB_WORKER_CONCURRENCY = max(1, int(os.environ.get("JOB_WORKER_CONCURRENCY", "1")))
JOB_DEFAULT_TTL_SECONDS = int(os.environ.get("JOB_DEFAULT_TTL_SECONDS", "86400"))

JOBS_PUBLIC_SUBMIT_ENABLED = os.environ.get("JOBS_PUBLIC_SUBMIT_ENABLED", "0") == "1"
JOB_SUBMIT_RATE_LIMIT_MAX_PUBLIC = _env_int_with_floor("JOB_SUBMIT_RATE_LIMIT_MAX_PUBLIC", 120, 120)
JOB_SUBMIT_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("JOB_SUBMIT_RATE_LIMIT_WINDOW_SECONDS", "60"))

_jobs_fs_lock = Lock()

def _ensure_jobs_dir() -> None:
    try:
        os.makedirs(JOBS_DIR, exist_ok=True)
    except Exception:
        # Don't hard-fail startup for filesystem issues; job endpoints will error.
        pass

def _job_path(job_id: str) -> str:
    safe = "".join(ch for ch in job_id if ch.isalnum() or ch in ("-", "_"))
    return os.path.join(JOBS_DIR, f"{safe}.json")

def _read_job(job_id: str) -> Optional[dict]:
    path = _job_path(job_id)
    if not os.path.exists(path):
        return None
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
    try:
        candidates = [
            os.path.join(JOBS_DIR, name)
            for name in os.listdir(JOBS_DIR)
            if name.endswith(".json")
        ]
    except Exception:
        return []
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    jobs: List[dict] = []
    for path in candidates[: max(0, limit)]:
        try:
            with _jobs_fs_lock:
                with open(path, "r", encoding="utf-8") as f:
                    jobs.append(json.load(f))
        except Exception:
            continue
    return jobs

def _job_now() -> float:
    return time.time()

def _new_job(kind: str, payload: dict, requested_by: dict) -> dict:
    now = _job_now()
    job_id = "job_" + uuid4().hex
    return {
        "id": job_id,
        "kind": kind,
        "status": "queued",
        "created_at": now,
        "updated_at": now,
        "requested_by": requested_by,
        "payload": payload,
        "result": None,
        "error": None,
        "ttl_seconds": JOB_DEFAULT_TTL_SECONDS,
    }

def _job_redact_for_list(job: dict) -> dict:
    # Never list full payloads by default; status pages can show details.
    return {
        "id": job.get("id"),
        "kind": job.get("kind"),
        "status": job.get("status"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "requested_by": job.get("requested_by"),
        "result": job.get("result"),
        "error": job.get("error"),
        "progress": job.get("progress"),
    }

@dataclass
class _JobQueueItem:
    job_id: str

_job_submit_buckets = defaultdict(lambda: deque())

def _enforce_job_submit_rate_limit(client_ip: str) -> None:
    now = _job_now()
    bucket = _job_submit_buckets[client_ip]
    while bucket and (now - bucket[0]) > JOB_SUBMIT_RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= JOB_SUBMIT_RATE_LIMIT_MAX_PUBLIC:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    bucket.append(now)


# --- Self-signup rate limit (separate bucket from job submission) ---
# Strict: 3 attempts / minute per IP. Trusted (tailnet) clients bypass.
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
MIN_PASSWORD_LENGTH = 8
REGISTER_WINDOW_SECONDS = 60
REGISTER_MAX_PER_WINDOW = 3
_register_buckets: "defaultdict[str, deque]" = defaultdict(lambda: deque())

def _enforce_register_rate_limit(client_ip: str) -> None:
    if _is_trusted_client_ip(client_ip):
        return
    now = time.time()
    bucket = _register_buckets[client_ip or "_unknown"]
    while bucket and (now - bucket[0]) > REGISTER_WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= REGISTER_MAX_PER_WINDOW:
        raise HTTPException(status_code=429, detail="Too many signup attempts. Try again in a minute.")
    bucket.append(now)


# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vaultwares.api")

import requests
import queue
import threading
import sys
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin

class KiwiLogHandler(logging.Handler):
    def __init__(
        self,
        target_url=None,
        max_batch_size=None,
        flush_interval=None,
        syslog_host=None,
        syslog_port=None,
        transport=None,
        start_worker=True,
    ):
        super().__init__()
        self.target_url = target_url or os.environ.get("VW_KIWI_LOG_URL")
        self.transport = (transport or os.environ.get("VW_KIWI_LOG_TRANSPORT") or ("http_json" if self.target_url else "syslog_udp")).lower()
        self.syslog_host = syslog_host or os.environ.get("VW_KIWI_SYSLOG_HOST", "127.0.0.1")
        self.syslog_port = int(syslog_port or os.environ.get("VW_KIWI_SYSLOG_PORT", "514"))
        self.max_batch_size = int(max_batch_size or os.environ.get("VW_KIWI_LOG_BATCH_SIZE", "25"))
        self.flush_interval = float(flush_interval or os.environ.get("VW_KIWI_LOG_FLUSH_SECONDS", "2.0"))
        self.lock = threading.RLock()
        self.batch = []
        self.first_log_time = None
        self.thread = None

        if start_worker:
            self.thread = threading.Thread(target=self._flush_loop, daemon=True)
            self.thread.start()

    def emit(self, record):
        if record.name.startswith(("urllib3", "requests", "httpx")):
            return
        try:
            msg = self.format(record)
            timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
            
            with self.lock:
                if not self.batch:
                    self.first_log_time = time.time()
                self.batch.append({
                    "timestamp": timestamp,
                    "level": record.levelname,
                    "logger": record.name,
                    "message": msg,
                    "correlationId": getattr(record, "correlation_id", None),
                    "method": getattr(record, "method", None),
                    "path": getattr(record, "path", None),
                    "status_code": getattr(record, "status_code", None),
                    "duration_ms": getattr(record, "duration_ms", None),
                })
                
                if len(self.batch) >= self.max_batch_size:
                    self._flush_now()
        except Exception:
            self.handleError(record)

    def _flush_now(self):
        if not self.batch:
            return
        
        payload = self.batch
        self.batch = []
        self.first_log_time = None
        
        def send_http_json():
            try:
                requests.post(self.target_url, json=payload, timeout=3)
            except Exception:
                pass

        def send_syslog_udp():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    for item in payload:
                        corr = item.get("correlationId") or "-"
                        method = item.get("method") or "-"
                        path = item.get("path") or "-"
                        status = item.get("status_code") or "-"
                        duration = item.get("duration_ms") or "-"
                        message = item.get("message") or ""
                        line = (
                            f"<14>1 {item['timestamp']} vaultwares-api vaultwares-api - - "
                            f"[vaultwares correlationId=\"{corr}\" method=\"{method}\" path=\"{path}\" status=\"{status}\" durationMs=\"{duration}\"] "
                            f"{message}"
                        )
                        sock.sendto(line.encode("utf-8", errors="replace"), (self.syslog_host, self.syslog_port))
            except Exception:
                pass

        if self.transport == "http_json" and self.target_url:
            target = send_http_json
        else:
            target = send_syslog_udp

        threading.Thread(target=target, daemon=True).start()

    def _flush_loop(self):
        while True:
            time.sleep(1.0)
            with self.lock:
                if self.batch and (time.time() - self.first_log_time >= self.flush_interval):
                    self._flush_now()

# Instantiate and register handler
kiwi_handler = KiwiLogHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
kiwi_handler.setFormatter(formatter)
root_logger = logging.getLogger()
root_logger.addHandler(kiwi_handler)

app = FastAPI(
    title="VaultWares API",
    description="Central API for VaultWares auth, DB-backed telemetry, monitor reads, logging, workflows, and media services.",
    version="0.2.0",
)

# --- Correlation ID Middleware ---
def _resolve_correlation_id(request: Request) -> str:
    corr_id = request.headers.get("x-correlation-id")
    if not corr_id:
        corr_id = request.headers.get("x-request-id")
    if not corr_id:
        corr_id = request.query_params.get("correlationId")
    if not corr_id:
        corr_id = getattr(request.state, "correlation_id", None)
    if not corr_id:
        corr_id = f"vw_{uuid.uuid4().hex[:12]}"
    request.state.correlation_id = corr_id
    return corr_id


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    corr_id = _resolve_correlation_id(request)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = corr_id
    return response

# ─── Prom-King router ──────────────────────────────────────────────────────
# Mounts /api/promking/* (videos, taxonomies, fetcher, settings, stats).
# See ADR-001 + Prom-King/shared-tube/docs/router-integration.md
try:
    from app.routers.promking import router as promking_router
    app.include_router(promking_router)
    _PROMKING_LOADED = True
except Exception as _promking_err:  # pragma: no cover — keeps startup resilient
    _PROMKING_LOADED = False
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "Prom-King router not loaded: %s", _promking_err
    )

# ─── V.A.U.L.T Monitor router ─────────────────────────────────────────────
# Mounts /monitor/* normalized read-only telemetry endpoints.
try:
    from app.routers.monitor import router as monitor_router
    app.include_router(monitor_router)
    _MONITOR_LOADED = True
except Exception as _monitor_err:  # pragma: no cover — keeps startup resilient
    _MONITOR_LOADED = False
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "Monitor router not loaded: %s", _monitor_err
    )

# ─── Telemetry router ─────────────────────────────────────────────────────
# Mounts /api/telemetry/* DB-backed ingest/read endpoints.
try:
    from app.routers.telemetry import router as telemetry_router
    app.include_router(telemetry_router)
    _TELEMETRY_LOADED = True
except Exception as _telemetry_err:  # pragma: no cover — keeps startup resilient
    _TELEMETRY_LOADED = False
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "Telemetry router not loaded: %s", _telemetry_err
    )

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

from fastapi.staticfiles import StaticFiles
_faceswap_static_dir = os.environ.get("FACESWAP_STATIC_DIR")
if _faceswap_static_dir and os.path.isdir(_faceswap_static_dir):
    app.mount("/faceswap", StaticFiles(directory=_faceswap_static_dir, html=True), name="faceswap")

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
    if _trusted_client_ips:
        return any(ip_obj == trusted_ip for trusted_ip in _trusted_client_ips)
    for net in _tailscale_networks:
        if ip_obj.version != net.version:
            continue
        if ip_obj in net:
            return True
    return False

def _is_trusted_proxy_peer(peer_ip: Optional[str]) -> bool:
    if not peer_ip:
        return False
    try:
        peer_obj = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    for net in _trusted_proxy_networks:
        if peer_obj.version != net.version:
            continue
        if peer_obj in net:
            return True
    return False

def _effective_scheme(request: Request) -> str:
    # Only trust proxy-provided scheme headers when the immediate peer is a trusted proxy.
    # Otherwise, a direct caller could spoof x-forwarded-proto to bypass HTTPS enforcement.
    peer_ip = request.client.host if request.client else None
    if _is_trusted_proxy_peer(peer_ip):
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

    is_trusted_proxy = _is_trusted_proxy_peer(peer_ip)
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
        except ValueError:
            # If it's an invalid IP format, treat it as the untrusted client
            return ip_str

        is_from_trusted_proxy = False
        for net in _trusted_proxy_networks:
            if ip_obj.version != net.version:
                continue
            if ip_obj in net:
                is_from_trusted_proxy = True
                break

        if not is_from_trusted_proxy:
            return ip_str

    # Fallback to rightmost (the one immediately connected to the proxy) if all are trusted
    return ips[-1] if ips else peer_ip

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
    import hashlib
    return hashlib.sha256((API_KEY_PEPPER + raw_key).encode("utf-8")).hexdigest()

def _verify_api_key(raw_key: str, hashed_key: str) -> bool:
    if not raw_key or not hashed_key:
        return False
    if not API_KEY_PEPPER:
        raise HTTPException(status_code=500, detail="API key pepper is not configured")
    if hashed_key.startswith("$2"):
        # Legacy bcrypt support
        return pwd_context.verify(API_KEY_PEPPER + raw_key, hashed_key)
    return secrets.compare_digest(_hash_api_key(raw_key), hashed_key)

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
        parts = api_key.split("_")
        if len(parts) == 3 and parts[0] == "vwk":
            try:
                candidate = await ApiKey.get_or_none(id=int(parts[1]))
                if candidate:
                    import hmac
                    expected_hash = _hash_api_key(api_key)
                    if hmac.compare_digest(candidate.key_hash, expected_hash):
                        key_row = candidate
                    elif _verify_api_key(api_key, candidate.key_hash):
                        key_row = candidate
            except ValueError:
                pass

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
    correlation_id = _resolve_correlation_id(request)
    method = request.method
    path = request.url.path
    started = time.perf_counter()
    try:
        if len(_rate_state) > RATE_LIMIT_MAX_STATE_SIZE:
            # Prevent clearing the whole dictionary to avoid rate limit bypass
            # Remove oldest element
            oldest_key = next(iter(_rate_state))
            _rate_state.pop(oldest_key, None)

        client_ip = _get_client_ip(request) or ""
        is_trusted_ip = _is_trusted_client_ip(client_ip)
        logger.info(
            "request.start",
            extra={
                "correlation_id": correlation_id,
                "method": method,
                "path": path,
                "client_ip": client_ip,
                "trusted_client": is_trusted_ip,
            },
        )

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
            else:
                # No gateway required: fall back to browser origin allowlist.
                if not origin or not _origin_allowed(origin):
                    raise HTTPException(status_code=403, detail="Forbidden source")

        if RATE_LIMIT_ENABLED:
            is_media_pipeline = path in ["/health", "/scrape", "/download", "/abort", "/api/abort", "/api/jobs"]
            if not is_media_pipeline:
                now = time.time()
                key = f"{client_ip}:{origin}" if origin else client_ip
                bucket = _rate_state[key]
                while bucket and (now - bucket[0]) > RATE_LIMIT_WINDOW_SECONDS:
                    bucket.popleft()
                limit = RATE_LIMIT_MAX_TRUSTED if is_trusted_ip else RATE_LIMIT_MAX_PUBLIC
                if len(bucket) >= limit:
                    raise HTTPException(status_code=429, detail="Rate limit exceeded")
                bucket.append(now)

        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Correlation-Id"] = correlation_id
        logger.info(
            "request.complete",
            extra={
                "correlation_id": correlation_id,
                "method": method,
                "path": path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
                "trusted_client": is_trusted_ip,
            },
        )

        return response
    except HTTPException as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.warning(
            "request.blocked",
            extra={
                "correlation_id": correlation_id,
                "method": method,
                "path": path,
                "status_code": exc.status_code,
                "duration_ms": duration_ms,
                "reason": exc.detail,
            },
        )
        response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        response.headers["X-Correlation-Id"] = correlation_id
        return response
    except Exception:
        peer_ip = request.client.host if request.client else None
        try:
            client_ip = _get_client_ip(request)
        except Exception:
            client_ip = None
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception(
            "request.crashed",
            extra={
                "correlation_id": correlation_id,
                "method": method,
                "path": path,
                "status_code": 500,
                "duration_ms": duration_ms,
                "peer_ip": peer_ip,
                "client_ip": client_ip,
            },
        )
        response = JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
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

class JobSubmitRequest(BaseModel):
    kind: str = Field(default="workflow_run")
    id: str
    mode: str = Field(default="local")

class JobSummary(BaseModel):
    id: str
    kind: str
    status: str
    created_at: float
    updated_at: float
    requested_by: Optional[dict] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    progress: Optional[dict] = None  # live ComfyUI progress (current_node, step/total, message)

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

# Self-signup. Email is optional and currently not persisted (UserAccount has
# no email column yet); accepting it lets the frontend collect it without
# breaking the API if/when the column is added.
class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None

class RegisterResponse(BaseModel):
    username: str
    access_token: str
    token_type: str = "bearer"
    expires_in: int

# --- vault-flows graph execution ----------------------------------------------
# These mirror the FlowNode/FlowEdge/Flow types in vault-flows/src/nodes/types.ts.
# When this endpoint is called from the SPA, the entire React Flow graph is sent
# as JSON; we walk it topologically and execute each node.
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
    # New fields so we can carry diverse outputs (image refs, file paths,
    # structured job results) alongside the text. The SPA's DisplayNode
    # branches on `kind` to render previews instead of just strings.
    kind: Optional[str] = None         # 'text' | 'image' | 'json' | 'file' | 'job_result'
    imageUrl: Optional[str] = None     # primary image (== imageUrls[0])
    imageUrls: Optional[List[str]] = None  # all output images for multi-image workflows
    fileRef: Optional[str] = None      # set when kind == 'file'
    data: Optional[dict] = None        # set when kind in ('json', 'job_result')

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

# vault-flows graph execution: where to send LLM node calls. Defaults to local
# Ollama on the operator box. Override via OLLAMA_URL.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_DEFAULT_MODEL = os.environ.get("OLLAMA_DEFAULT_MODEL", "llama3")
OLLAMA_CALL_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_CALL_TIMEOUT_SECONDS", "120"))

# comfyui_workflow / model_call+comfyui: how aggressively to poll the job
# status, and how long to wait before giving up.
COMFYUI_JOB_POLL_INTERVAL_SECONDS = float(os.environ.get("COMFYUI_JOB_POLL_INTERVAL_SECONDS", "2"))
COMFYUI_JOB_MAX_WAIT_SECONDS = float(os.environ.get("COMFYUI_JOB_MAX_WAIT_SECONDS", "600"))

# Where to reach the local ComfyUI REST API (the actual image-gen backend).
# The job worker posts graphs to /prompt, polls /history, fetches /view.
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
COMFYUI_PROMPT_TIMEOUT_SECONDS = float(os.environ.get("COMFYUI_PROMPT_TIMEOUT_SECONDS", "300"))

# Signed-URL config. URL tokens use the existing JWT_SECRET so we don't add
# a new secret to rotate.
COMFYUI_URL_TOKEN_TTL_SECONDS = int(os.environ.get("COMFYUI_URL_TOKEN_TTL_SECONDS", "3600"))

# Where client-uploaded image inputs land on disk.
UPLOADS_DIR = os.environ.get("UPLOADS_DIR", "./_uploads")
UPLOADS_MAX_BYTES = int(os.environ.get("UPLOADS_MAX_BYTES", str(20 * 1024 * 1024)))  # 20 MB
UPLOADS_TOKEN_TTL_SECONDS = int(os.environ.get("UPLOADS_TOKEN_TTL_SECONDS", "86400"))  # 24h

# How long to cache ComfyUI /object_info inside the pipelines process.
# Workflow validation uses it; refreshing too often would hammer ComfyUI on
# every catalog open, but stale cache means newly-installed custom packs
# won't be visible until expiry.
COMFYUI_OBJECT_INFO_CACHE_TTL = int(os.environ.get("COMFYUI_OBJECT_INFO_CACHE_TTL", "300"))

# model_call+provider:http: timeout for the generic HTTP node.
HTTP_NODE_TIMEOUT_SECONDS = float(os.environ.get("HTTP_NODE_TIMEOUT_SECONDS", "60"))

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
DB_URL = os.getenv("DB_URL", "postgres://localhost:5432/vaultwares")

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

def _apply_input_paths(graph: dict, input_paths: dict, inputs: dict) -> dict:
    """
    Mutate a copy of `graph` by writing each `inputs[key]` into the dotted
    path `input_paths[key]`. Missing input keys leave the graph's existing
    default value untouched.

    Example:
        graph = {"5": {"inputs": {"seed": 0, "text": "default"}}}
        input_paths = {"prompt": "5.inputs.text", "seed": "5.inputs.seed"}
        inputs = {"prompt": "a cat", "seed": 42}
        -> graph["5"]["inputs"] = {"seed": 42, "text": "a cat"}
    """
    if not isinstance(graph, dict):
        return graph
    out = json.loads(json.dumps(graph))  # deep copy
    for input_key, dotted in (input_paths or {}).items():
        if input_key not in inputs:
            continue
        if not isinstance(dotted, str):
            continue
        parts = dotted.split(".")
        cursor = out
        for p in parts[:-1]:
            if isinstance(cursor, dict) and p in cursor:
                cursor = cursor[p]
            else:
                cursor = None
                break
        if isinstance(cursor, dict):
            cursor[parts[-1]] = inputs[input_key]
    return out


async def _comfyui_ws_listener(
    client_id: str,
    prompt_id: str,
    progress_cb,
    cancel_event: asyncio.Event,
    done_event: asyncio.Event,
) -> None:
    """
    Subscribe to ComfyUI's WebSocket and forward progress events for our
    prompt_id to the provided callback. Runs until done_event is set (by the
    history-poller noticing completion) or until the WS errors out.

    Events we surface to progress_cb (one dict per call):
      {kind: 'execution_start',  prompt_id}
      {kind: 'execution_cached', prompt_id, nodes: [...]}
      {kind: 'executing',        prompt_id, node: <id or None>}
      {kind: 'progress',         prompt_id, node, value, max}
      {kind: 'executed',         prompt_id, node, output}
      {kind: 'execution_error',  prompt_id, node_id, exception_message}
      {kind: 'execution_success',prompt_id}
    """
    if progress_cb is None:
        return
    ws_url = COMFYUI_URL.replace("http://", "ws://").replace("https://", "wss://")
    url = f"{ws_url}/ws?clientId={client_id}"
    try:
        import websockets
        async with websockets.connect(url, max_size=None, ping_interval=20) as ws:
            while not done_event.is_set() and not cancel_event.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    return
                if not isinstance(raw, (str, bytes)):
                    continue
                if isinstance(raw, bytes):
                    # ComfyUI sends binary frames for preview images; skip
                    continue
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                kind = msg.get("type")
                data = msg.get("data") or {}
                if not isinstance(data, dict):
                    continue
                if data.get("prompt_id") and data["prompt_id"] != prompt_id:
                    continue
                if kind in (
                    "execution_start", "execution_cached", "executing",
                    "progress", "executed", "execution_error", "execution_success",
                ):
                    try:
                        progress_cb({"kind": kind, **data})
                    except Exception:
                        pass
    except Exception as exc:
        # WS failures shouldn't block the run — we still have history polling
        logger.debug(f"ComfyUI ws listener for {prompt_id} ended: {exc}")


async def _execute_comfyui_graph(graph: dict, progress_cb=None, cancel_event: asyncio.Event | None = None) -> dict:
    """
    Submit a ComfyUI API-format graph, poll /history until completion, mint a
    signed /comfyui-image/{token} URL for each output image.

    If `progress_cb` is provided, it's called with dicts containing live event
    data from ComfyUI's WebSocket (`executing`, `progress`, etc.) so the
    caller can surface per-step status (KSampler 12/30, etc.).

    If `cancel_event` is provided and gets set during execution, we POST to
    ComfyUI's /interrupt and raise a RuntimeError("canceled").

    Returns:
        {
            "image_url":  "/api/comfyui-image/<token>",  # first output
            "image_urls": [...],                          # all outputs
            "prompt_id":  "...",
            "images":     [{filename, subfolder, type}, ...],
            "summary":    "Generated N image(s)",
        }
    """
    client_id = secrets.token_hex(8)
    deadline = time.time() + COMFYUI_PROMPT_TIMEOUT_SECONDS
    cancel_event = cancel_event or asyncio.Event()
    done_event = asyncio.Event()

    async with httpx.AsyncClient(timeout=COMFYUI_PROMPT_TIMEOUT_SECONDS) as client:
        # 1. Submit
        try:
            r = await client.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": graph, "client_id": client_id},
            )
        except httpx.RequestError as e:
            raise RuntimeError(f"ComfyUI POST /prompt failed: {e}") from e
        if r.status_code >= 400:
            raise RuntimeError(f"ComfyUI /prompt -> {r.status_code}: {r.text[:300]}")
        submit = r.json()
        prompt_id = submit.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI didn't return prompt_id: {submit}")

        if progress_cb:
            try:
                progress_cb({"kind": "submitted", "prompt_id": prompt_id})
            except Exception:
                pass

        # 2. Spawn the WS listener in parallel with history polling
        listener_task = asyncio.create_task(
            _comfyui_ws_listener(client_id, prompt_id, progress_cb, cancel_event, done_event)
        )

        try:
            while time.time() < deadline:
                # Honor cancel: POST /interrupt and bail
                if cancel_event.is_set():
                    try:
                        await client.post(f"{COMFYUI_URL}/interrupt", timeout=5.0)
                    except Exception:
                        pass
                    raise RuntimeError("canceled")

                await asyncio.sleep(1.5)
                try:
                    h = await client.get(f"{COMFYUI_URL}/history/{prompt_id}")
                except httpx.RequestError:
                    continue
                if h.status_code != 200:
                    continue
                history = h.json()
                entry = history.get(prompt_id)
                if not entry:
                    continue
                status = entry.get("status", {})
                status_str = status.get("status_str")
                if status_str == "error":
                    msgs = status.get("messages", [])
                    raise RuntimeError(f"ComfyUI workflow errored: {msgs}")
                if status.get("completed") or status_str == "success":
                    outputs = entry.get("outputs", {})
                    image_refs: List[dict] = []
                    for node_out in outputs.values():
                        if not isinstance(node_out, dict):
                            continue
                        for img in node_out.get("images") or []:
                            image_refs.append(
                                {
                                    "filename": img.get("filename"),
                                    "subfolder": img.get("subfolder", ""),
                                    "type": img.get("type", "output"),
                                }
                            )
                    if not image_refs:
                        raise RuntimeError("ComfyUI workflow completed but produced no images")

                    # 3. Mint signed URLs (much lighter than base64 data URIs)
                    image_urls = []
                    for img in image_refs:
                        token = _sign_comfyui_image_token(
                            img["filename"], img.get("subfolder", ""), img.get("type", "output")
                        )
                        image_urls.append(f"/api/comfyui-image/{token}")
                    return {
                        "image_url": image_urls[0],
                        "image_urls": image_urls,
                        "prompt_id": prompt_id,
                        "images": image_refs,
                        "summary": f"Generated {len(image_refs)} image(s) via ComfyUI",
                    }
        finally:
            done_event.set()
            try:
                await asyncio.wait_for(listener_task, timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                listener_task.cancel()

    raise RuntimeError(
        f"ComfyUI prompt {prompt_id} did not complete within {COMFYUI_PROMPT_TIMEOUT_SECONDS}s"
    )


async def _resolve_image_inputs(inputs: dict, input_paths: dict, image_keys: list) -> dict:
    """
    For any input key in `image_keys` whose value is an upload-token string,
    decode it to a local file, push it into ComfyUI's input folder via
    /upload/image, and replace the value with the ComfyUI-side filename so
    LoadImage nodes can reference it directly.

    Returns a new inputs dict (doesn't mutate the original).
    """
    if not inputs:
        return inputs or {}
    out = dict(inputs)
    for key in image_keys:
        val = out.get(key)
        if not isinstance(val, str) or not val:
            continue
        # An image_ref looks like a JWT (three base64url-ish segments split by ".").
        if val.count(".") != 2:
            continue
        try:
            local_path = _resolve_image_ref_to_path(val)
        except Exception as e:
            raise RuntimeError(f"Cannot resolve image_ref for input '{key}': {e}")
        # Best-effort MIME from extension
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
    """
    Job-worker entry point for kind=workflow_run jobs. Loads the saved
    workflow's steps, finds the first comfyui_graph step, applies input_paths
    substitutions from `inputs`, and dispatches to ComfyUI.

    `progress_cb(event_dict)` is invoked with ComfyUI's live WebSocket events
    (executing/progress/executed/...) plus a synthetic 'submitted' event when
    the prompt is accepted. The worker uses this to write per-step progress
    to the job record.

    `cancel_event` — if set, _execute_comfyui_graph POSTs /interrupt to
    ComfyUI and raises RuntimeError("canceled").

    Inputs whose key is in step.image_inputs are upload-token references
    that get decoded + pushed to ComfyUI's input folder before submission.
    """
    if db_available():
        try:
            wf = await WorkflowDB.get(id=workflow_id)
        except DoesNotExist:
            raise RuntimeError(f"Workflow '{workflow_id}' not found in DB")
        steps = wf.steps or []
    else:
        wfs = _load_workflows_from_file()
        match = next((w for w in wfs if w.id == workflow_id), None)
        if not match:
            raise RuntimeError(f"Workflow '{workflow_id}' not found in workflows.json")
        steps = match.steps or []

    if not isinstance(steps, list) or not steps:
        raise RuntimeError(f"Workflow '{workflow_id}' has no steps")

    step = next(
        (s for s in steps if isinstance(s, dict) and s.get("kind") == "comfyui_graph"),
        None,
    )
    if not step:
        raise RuntimeError(
            f"Workflow '{workflow_id}' has no comfyui_graph step (got: "
            f"{[s.get('kind') if isinstance(s, dict) else type(s).__name__ for s in steps]})"
        )

    graph = step.get("graph")
    if not isinstance(graph, dict):
        raise RuntimeError("comfyui_graph step is missing a valid 'graph' object")
    input_paths = step.get("input_paths") or {}
    if not isinstance(input_paths, dict):
        input_paths = {}
    image_input_keys = step.get("image_inputs") or []
    if not isinstance(image_input_keys, list):
        image_input_keys = []

    if progress_cb:
        try:
            progress_cb({"kind": "resolving_inputs"})
        except Exception:
            pass
    resolved_inputs = await _resolve_image_inputs(inputs or {}, input_paths, image_input_keys)
    rendered = _apply_input_paths(graph, input_paths, resolved_inputs)
    return await _execute_comfyui_graph(rendered, progress_cb=progress_cb, cancel_event=cancel_event)


async def _job_worker(app: FastAPI, worker_id: int) -> None:
    queue: asyncio.Queue = app.state.job_queue
    while True:
        item: _JobQueueItem = await queue.get()
        try:
            job = _read_job(item.job_id)
            if not job:
                continue
            if job.get("status") != "queued":
                continue

            job["status"] = "running"
            job["updated_at"] = _job_now()
            _write_job(job)

            result: Optional[dict] = None
            error: Optional[str] = None

            try:
                if job.get("kind") == "workflow_run":
                    payload = job.get("payload") or {}
                    workflow_id = str(payload.get("id") or "")
                    mode = str(payload.get("mode") or "local")
                    inputs = payload.get("inputs") or {}
                    if not isinstance(inputs, dict):
                        inputs = {}
                    logger.info(
                        f"worker {worker_id}: running workflow {workflow_id} "
                        f"mode={mode} inputs_keys={list(inputs.keys())}"
                    )

                    # --- Live progress wiring --------------------------------
                    # progress_cb persists each ComfyUI event into the job
                    # record's `progress` field so the SPA can poll for it.
                    progress_state: dict = {
                        "prompt_id": None,
                        "current_node_id": None,
                        "current_node_class": None,
                        "step": 0,
                        "total": 0,
                        "message": "starting",
                        "cached_nodes": [],
                        "events_seen": 0,
                    }
                    last_write = [0.0]  # mutable to capture in closure

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
                            cached = event.get("nodes") or []
                            progress_state["cached_nodes"] = cached
                            progress_state["message"] = f"reused {len(cached)} cached node(s)"
                        elif kind == "executing":
                            node = event.get("node")
                            progress_state["current_node_id"] = node
                            # Look up class_type from the running graph if we can
                            cls = None
                            try:
                                if node is not None:
                                    g = rendered if False else None  # not in scope here
                            except Exception:
                                cls = None
                            progress_state["current_node_class"] = cls
                            progress_state["step"] = 0
                            progress_state["total"] = 0
                            progress_state["message"] = (
                                f"running node {node}" if node else "finalizing"
                            )
                        elif kind == "progress":
                            progress_state["step"] = int(event.get("value") or 0)
                            progress_state["total"] = int(event.get("max") or 0)
                            n = progress_state.get("current_node_id")
                            progress_state["message"] = (
                                f"step {progress_state['step']}/{progress_state['total']}"
                                + (f" (node {n})" if n else "")
                            )
                        elif kind == "executed":
                            progress_state["message"] = f"node {event.get('node')} done"
                        elif kind == "execution_error":
                            progress_state["message"] = "ComfyUI error"
                        elif kind == "execution_success":
                            progress_state["message"] = "done"
                        # Throttle disk writes to ~5/sec to avoid hammering the job store
                        now = time.time()
                        if now - last_write[0] < 0.2 and kind not in (
                            "execution_success", "execution_error", "submitted"
                        ):
                            return
                        last_write[0] = now
                        cur = _read_job(item.job_id) or job
                        cur["progress"] = dict(progress_state)
                        cur["updated_at"] = _job_now()
                        _write_job(cur)

                    cancel_event = asyncio.Event()

                    async def watch_cancel() -> None:
                        # Polls the job record so the SPA can /jobs/{id}/cancel
                        # and have the worker trip ComfyUI's /interrupt.
                        while not cancel_event.is_set():
                            await asyncio.sleep(1.0)
                            cur = _read_job(item.job_id)
                            if cur and cur.get("status") == "canceled":
                                cancel_event.set()
                                return

                    watch_task = asyncio.create_task(watch_cancel())
                    try:
                        result = await _execute_workflow_run(
                            workflow_id, mode, inputs,
                            progress_cb=progress_cb,
                            cancel_event=cancel_event,
                        )
                    finally:
                        cancel_event.set()
                        try:
                            await asyncio.wait_for(watch_task, timeout=1.5)
                        except (asyncio.TimeoutError, Exception):
                            watch_task.cancel()
                else:
                    raise ValueError(f"Unknown job kind: {job.get('kind')}")
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                logger.warning(f"worker {worker_id}: job {item.job_id} failed: {error}")

            job = _read_job(item.job_id) or job
            if job.get("status") == "canceled":
                job["updated_at"] = _job_now()
                _write_job(job)
                continue

            job["status"] = "failed" if error else "succeeded"
            job["updated_at"] = _job_now()
            job["result"] = result
            job["error"] = error
            _write_job(job)
        finally:
            queue.task_done()

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

    # Start Prom-King APScheduler (best-effort; PROMKING_DATABASE_URL may be
    # unset on workstations that don't run the tube routes).
    if _PROMKING_LOADED:
        try:
            from app.routers.promking.cron import start_scheduler as _pk_start
            await _pk_start()
        except Exception as _pk_err:
            logger.warning("Prom-King APScheduler not started: %s", _pk_err)

    _ensure_jobs_dir()
    if not hasattr(app.state, "job_queue"):
        app.state.job_queue = asyncio.Queue(maxsize=JOB_QUEUE_MAX_PENDING)
        app.state.job_workers = [
            asyncio.create_task(_job_worker(app, index + 1))
            for index in range(JOB_WORKER_CONCURRENCY)
        ]

        # Re-queue any durable queued jobs from a previous run (best-effort).
        try:
            durable = _list_jobs(limit=JOB_QUEUE_MAX_PENDING)
            queued = [j for j in durable if j.get("status") == "queued"]
            queued.sort(key=lambda j: float(j.get("created_at") or 0))
            for job in queued:
                try:
                    app.state.job_queue.put_nowait(_JobQueueItem(job_id=str(job.get("id"))))
                except asyncio.QueueFull:
                    break
        except Exception:
            pass

@app.on_event("shutdown")
async def shutdown_event():
    try:
        if hasattr(app.state, "job_workers"):
            for task in list(app.state.job_workers):
                task.cancel()
        await close_db()
        logger.info("Tortoise ORM connections closed.")
    except Exception as e:
        logger.error(f"Error closing Tortoise ORM connections: {e}")

    # Stop Prom-King APScheduler + close its asyncpg pool.
    if _PROMKING_LOADED:
        try:
            from app.routers.promking.cron import stop_scheduler as _pk_stop
            from app.routers.promking.db import close_pool as _pk_close
            await _pk_stop()
            await _pk_close()
        except Exception as _pk_err:
            logger.warning("Prom-King shutdown warning: %s", _pk_err)

    if _TELEMETRY_LOADED:
        try:
            from app.routers.telemetry.db import close_pool as _telemetry_close
            await _telemetry_close()
        except Exception as _telemetry_err:
            logger.warning("Telemetry shutdown warning: %s", _telemetry_err)


# --- Endpoints ---

def db_available() -> bool:
    return bool(_tortoise_initialized and Tortoise._inited)

def _queue_job(app: FastAPI, job: dict) -> None:
    if not hasattr(app.state, "job_queue"):
        raise HTTPException(status_code=503, detail="Job queue unavailable")
    try:
        app.state.job_queue.put_nowait(_JobQueueItem(job_id=job["id"]))
    except asyncio.QueueFull:
        raise HTTPException(status_code=503, detail="Server busy; try again later")

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
        # Login is expected to be initiated by your own frontends (browser requests).
        # Even in gateway mode, require an allowlisted Origin to reduce drive-by abuse.
        origin = request.headers.get("origin", "")
        if not _origin_allowed(origin):
            raise HTTPException(status_code=403, detail="Forbidden origin")
        if GATEWAY_REQUIRED_PUBLIC and not _gateway_secret_valid(request):
            raise HTTPException(status_code=403, detail="Forbidden source")

    user = await UserAccount.get_or_none(username=payload.username)
    if not user or user.is_disabled:
        # Prevent timing-based username enumeration
        pwd_context.dummy_verify()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not pwd_context.verify(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = _create_access_token(user.id, user.username, bool(user.is_admin))
    return LoginResponse(access_token=token, expires_in=max(60, JWT_TTL_SECONDS))

@app.post("/auth/register", response_model=RegisterResponse)
async def register(payload: RegisterRequest, request: Request):
    """
    Self-signup for non-admin user accounts. Same origin/source enforcement as
    /auth/login, plus a stricter per-IP rate limit (3/min). Returns a JWT so
    the client can skip a follow-up /auth/login round-trip.
    """
    if not AUTH_ENABLED:
        raise HTTPException(status_code=400, detail="Auth is disabled")
    if not db_available():
        raise HTTPException(status_code=503, detail="Database unavailable")

    client_ip = _get_client_ip(request)
    if not _is_trusted_client_ip(client_ip):
        origin = request.headers.get("origin", "")
        if not _origin_allowed(origin):
            raise HTTPException(status_code=403, detail="Forbidden origin")
        if GATEWAY_REQUIRED_PUBLIC and not _gateway_secret_valid(request):
            raise HTTPException(status_code=403, detail="Forbidden source")

    _enforce_register_rate_limit(client_ip or "")

    username = payload.username.strip()
    password = payload.password
    if not USERNAME_RE.match(username):
        raise HTTPException(
            status_code=400,
            detail="Username must be 3-32 chars: letters, digits, underscore, or dash",
        )
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        )

    existing = await UserAccount.get_or_none(username=username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")

    new_user = await UserAccount.create(
        username=username,
        password_hash=pwd_context.hash(password),
        is_admin=False,
        is_disabled=False,
    )
    logger.info(f"Registered new user: {new_user.username} (id={new_user.id})")

    token = _create_access_token(new_user.id, new_user.username, False)
    return RegisterResponse(
        username=new_user.username,
        access_token=token,
        expires_in=max(60, JWT_TTL_SECONDS),
    )

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

@app.get("/diagnostics/network", response_model=NetworkDiagnosticsResponse)
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

@app.get("/workflows", response_model=List[Workflow])
async def list_workflows(_principal=Depends(require_auth)):
    if db_available():
        workflows = await WorkflowDB.all()
        return [workflowdb_to_pydantic(wf) for wf in workflows]
    return _load_workflows_from_file()


@app.get("/workflows/{workflow_id}", response_model=Workflow)
async def get_workflow(workflow_id: str, _principal=Depends(require_auth)):
    """Fetch a single workflow by id (used by the SPA's per-node schema lookup)."""
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
        _enforce_job_submit_rate_limit(client_ip)

    job = _new_job(
        kind="workflow_run",
        payload={"id": req.id, "mode": req.mode},
        requested_by=_job_requested_by(principal),
    )
    _write_job(job)
    _queue_job(app, job)

    # Compatibility response shape: keep existing keys + add jobId.
    return {"id": req.id, "mode": req.mode, "status": "queued", "jobId": job["id"]}

# --- vault-flows graph runner -------------------------------------------------
def _flow_topo_sort(nodes: List[FlowNodeIn], edges: List[FlowEdgeIn]) -> List[FlowNodeIn]:
    """
    Return nodes in topological order (sources first). Stable: respects the
    input order of `nodes` for any nodes with the same depth. Cycles are
    broken arbitrarily (visited-set semantics).
    """
    by_id = {n.id: n for n in nodes}
    incoming: dict[str, set[str]] = {n.id: set() for n in nodes}
    for e in edges:
        if e.target in incoming and e.source in by_id:
            incoming[e.target].add(e.source)

    order: List[FlowNodeIn] = []
    visited: set[str] = set()

    def visit(node_id: str) -> None:
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
    """Replace {{input}} / {{value}} / {{context}} placeholders with upstream content."""
    if not text:
        return upstream_text
    out = text
    for placeholder in ("{{input}}", "{{value}}", "{{context}}"):
        out = out.replace(placeholder, upstream_text)
    return out


_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)

def _strip_reasoning_tokens(text: str) -> str:
    """
    Remove <think>...</think> chain-of-thought blocks that some reasoning models
    (Qwen 3, DeepSeek-R1 distillations, etc.) emit in the response stream. We
    surface only the final answer to the SPA; preserve raw text if the model
    doesn't use these markers.
    """
    if "<think>" not in text and "<THINK>" not in text:
        return text
    return _THINK_BLOCK_RE.sub("", text).lstrip()


async def _ollama_generate(model: str, prompt: str, system: str, temperature: float) -> str:
    """Call Ollama /api/generate (non-streaming) and return the response text."""
    body: dict = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if system:
        body["system"] = system

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


class OllamaModelInfo(BaseModel):
    name: str
    size: int = 0  # bytes
    modified_at: Optional[str] = None

class FlowsModelsResponse(BaseModel):
    models: List[OllamaModelInfo]
    default: str
    ollama_reachable: bool


# ---------------------------------------------------------------------------
# Workflow validation — replicates ComfyUI's validate_prompt without queuing
# ---------------------------------------------------------------------------

# UI-only nodes that are NOT registered server-side in ComfyUI but appear in
# editor workflows. The converter skips them; the validator does too.
_VALIDATION_UI_ONLY = {
    "Note", "MarkdownNote", "Reroute", "RerouteNode", "PrimitiveNode",
    "PrimitiveBoolean", "PrimitiveInt", "PrimitiveFloat", "PrimitiveString",
    "PrimitiveStringMultiline", "Anchor",
    "Fast Groups Muter (rgthree)", "Fast Groups Bypasser (rgthree)",
    "Bookmark (rgthree)", "Label (rgthree)",
}

# UUID-named subgraph references (ComfyUI editor's newer subgraph feature)
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# In-process cache for /object_info to avoid hammering ComfyUI on every
# catalog refresh. (cached_at_epoch, payload)
_object_info_cache: tuple[float, dict] = (0.0, {})


async def _get_comfyui_object_info() -> tuple[dict, bool]:
    """
    Return (object_info, comfyui_reachable). Uses in-process cache up to
    COMFYUI_OBJECT_INFO_CACHE_TTL seconds; falls back to the stale cache
    when ComfyUI is unreachable.
    """
    global _object_info_cache
    cached_at, payload = _object_info_cache
    if payload and (time.time() - cached_at) < COMFYUI_OBJECT_INFO_CACHE_TTL:
        return payload, True
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{COMFYUI_URL}/object_info")
            r.raise_for_status()
            data = r.json()
        _object_info_cache = (time.time(), data)
        return data, True
    except Exception as exc:
        logger.warning(f"validate: ComfyUI /object_info unreachable: {exc}")
        # Fall back to whatever stale cache we have (better than nothing)
        return payload, False


def _classify_validation(node_count: int, kinds: dict, node_errors: dict) -> str:
    """
    Reduce the validator output to a single verdict string the SPA can map
    to a badge color. Priority: blocker kinds → wiring errors → pass.
    """
    if kinds.get("unknown_pack"):
        return "blocked_unknown_pack"
    if kinds.get("subgraph_uuid"):
        return "blocked_subgraph"
    if node_errors:
        # Distinguish "value not in list" (typically missing model file) from
        # generic wiring issues — actionable difference for the user.
        for info in node_errors.values():
            for err in info.get("errors") or []:
                msg = (err.get("message") or "").lower()
                details = (err.get("details") or "").lower()
                if "value_not_in_list" in msg or "not in allowed list" in details:
                    return "blocked_missing_model"
        return "broken_wiring"
    if node_count == 0:
        return "empty"
    return "pass"


def _validate_comfyui_graph(graph: dict, object_info: dict, step: dict | None) -> dict:
    """
    Lightweight server-side replica of ComfyUI's validate_prompt(). Returns:
        { verdict, summary, node_count, kinds: {ok, ui_only, subgraph_uuid,
          unknown_pack}, errors: [{node_id, class_type, message, details}] }
    """
    overridden: set[tuple[str, str]] = set()
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
    errors: list[dict] = []

    for nid, node in graph.items():
        if not isinstance(node, dict):
            continue
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
        if not isinstance(required, dict):
            continue
        inputs = node.get("inputs") or {}
        for name, spec in required.items():
            if (nid, name) in overridden:
                continue  # worker overrides at runtime
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
            # Enum literal check
            spec_type = spec[0] if isinstance(spec, list) and spec else spec
            if isinstance(spec_type, list):
                if value not in spec_type:
                    errors.append({
                        "node_id": nid, "class_type": ct,
                        "message": "value_not_in_list",
                        "details": f"Input '{name}' value {value!r} not in allowed list",
                    })
                continue
            # Required wire types that arrived as literals
            if isinstance(spec_type, str) and spec_type.upper() in (
                "MODEL", "CLIP", "VAE", "CONDITIONING", "LATENT", "IMAGE",
                "MASK", "CONTROL_NET", "UPSCALE_MODEL", "STYLE_MODEL",
                "INSIGHTFACE", "IPADAPTER",
            ):
                # Empty strings/None should have hit the `value is None` branch;
                # if it's an empty string we still want to flag it
                if value == "" or value is None:
                    errors.append({
                        "node_id": nid, "class_type": ct,
                        "message": "missing_required",
                        "details": f"Required wire '{name}' ({spec_type}) is empty",
                    })

    node_errors: dict = {}
    for e in errors:
        node_errors.setdefault(e["node_id"], {"class_type": e["class_type"], "errors": []})
        node_errors[e["node_id"]]["errors"].append({
            "message": e["message"], "details": e["details"]
        })

    verdict = _classify_validation(len(graph), kinds, node_errors)

    # Summary string
    if verdict == "pass":
        summary = f"{kinds['ok']} nodes, no validation errors"
    elif verdict == "blocked_unknown_pack":
        summary = f"{kinds['unknown_pack']} unknown node class(es) — custom pack not installed"
    elif verdict == "blocked_subgraph":
        summary = f"{kinds['subgraph_uuid']} subgraph reference(s) — needs expansion"
    elif verdict == "blocked_missing_model":
        summary = f"references model(s) not on disk"
    elif verdict == "broken_wiring":
        summary = f"{len(errors)} wiring issue(s)"
    else:
        summary = "empty graph"

    return {
        "verdict": verdict,
        "summary": summary,
        "node_count": len(graph),
        "kinds": kinds,
        "errors": errors[:20],  # cap so the response stays reasonable
    }


class WorkflowValidationEntry(BaseModel):
    workflow_id: str
    verdict: str  # 'pass' | 'broken_wiring' | 'blocked_unknown_pack' | 'blocked_subgraph' | 'blocked_missing_model' | 'empty'
    summary: str
    node_count: int
    error_count: int


class WorkflowValidationResponse(BaseModel):
    comfyui_reachable: bool
    cached_at: float
    results: List[WorkflowValidationEntry]


@app.get("/flows/validation", response_model=WorkflowValidationResponse)
async def flows_validation(_principal=Depends(require_auth)):
    """
    Validate every seeded comfyui_graph workflow against ComfyUI's current
    /object_info. Used by the SPA's WorkflowLibrary to render a verdict badge
    per card. No GPU work; pure schema check.
    """
    object_info, reachable = await _get_comfyui_object_info()

    # Load all workflows
    if db_available():
        wfs = await WorkflowDB.all()
        workflows = [workflowdb_to_pydantic(w) for w in wfs]
    else:
        workflows = _load_workflows_from_file()

    results: list[WorkflowValidationEntry] = []
    for wf in workflows:
        steps = wf.steps or []
        step = next((s for s in steps if isinstance(s, dict) and s.get("kind") == "comfyui_graph"), None)
        if not step:
            results.append(WorkflowValidationEntry(
                workflow_id=wf.id, verdict="empty",
                summary="no comfyui_graph step",
                node_count=0, error_count=0,
            ))
            continue
        graph = step.get("graph") or {}
        validation = _validate_comfyui_graph(graph, object_info, step)
        results.append(WorkflowValidationEntry(
            workflow_id=wf.id,
            verdict=validation["verdict"],
            summary=validation["summary"],
            node_count=validation["node_count"],
            error_count=len(validation["errors"]),
        ))

    cached_at = _object_info_cache[0]
    return WorkflowValidationResponse(
        comfyui_reachable=reachable, cached_at=cached_at, results=results
    )


@app.get("/flows/models", response_model=FlowsModelsResponse)
async def flows_models(_principal=Depends(require_auth)):
    """
    List models currently loaded in Ollama, so the SPA can offer a dropdown
    in the LLM node param panel instead of free-text model names.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            r.raise_for_status()
            data = r.json()
        models = [
            OllamaModelInfo(
                name=m.get("name", ""),
                size=int(m.get("size", 0)),
                modified_at=m.get("modified_at"),
            )
            for m in data.get("models", [])
            if m.get("name")
        ]
        return FlowsModelsResponse(
            models=models, default=OLLAMA_DEFAULT_MODEL, ollama_reachable=True
        )
    except Exception as exc:
        logger.warning(f"flows_models: Ollama unreachable: {exc}")
        return FlowsModelsResponse(
            models=[], default=OLLAMA_DEFAULT_MODEL, ollama_reachable=False
        )


# --- Signed image URLs --------------------------------------------------------
# Instead of base64-inflating generated images into JSON responses, the runner
# returns a /comfyui-image/{token} URL. The token is a JWT signed with the
# existing JWT_SECRET; payload identifies the ComfyUI file by filename/subfolder
# /type plus an exp timestamp. The endpoint is unauthenticated (so <img src>
# from the browser just works) but tokens are short-lived and unguessable.

def _sign_comfyui_image_token(filename: str, subfolder: str, type_: str) -> str:
    now = int(time.time())
    claims = {
        "iss": JWT_ISSUER,
        "aud": "comfyui-image",
        "iat": now,
        "nbf": now,
        "exp": now + COMFYUI_URL_TOKEN_TTL_SECONDS,
        "fn": filename,
        "sub_": subfolder,
        "tp": type_,
    }
    return jwt.encode(claims, JWT_SECRET, algorithm="HS256")


def _verify_comfyui_image_token(token: str) -> dict:
    try:
        claims = jwt.decode(
            token, JWT_SECRET, algorithms=["HS256"],
            audience="comfyui-image", issuer=JWT_ISSUER,
        )
    except JWTError as e:
        raise HTTPException(status_code=403, detail=f"Invalid image token: {e}")
    return claims


@app.get("/comfyui-image/{token}")
async def comfyui_image(token: str):
    """
    Serve a generated ComfyUI image by validating the signed URL token and
    proxying the bytes from ComfyUI's /view. Unauthenticated by design — the
    token IS the access credential, and tokens are short-lived.
    """
    claims = _verify_comfyui_image_token(token)
    filename = str(claims.get("fn") or "")
    subfolder = str(claims.get("sub_") or "")
    type_ = str(claims.get("tp") or "output")
    if not filename:
        raise HTTPException(status_code=400, detail="Token missing filename")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            v = await client.get(
                f"{COMFYUI_URL}/view",
                params={"filename": filename, "subfolder": subfolder, "type": type_},
            )
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"ComfyUI unreachable: {e}")
    if v.status_code != 200:
        raise HTTPException(status_code=v.status_code, detail="ComfyUI /view error")
    return Response(
        content=v.content,
        media_type=v.headers.get("content-type", "image/png"),
        headers={"Cache-Control": "private, max-age=600"},
    )


# --- Image uploads -----------------------------------------------------------
# Clients POST multipart to /uploads/image, server writes the bytes to
# UPLOADS_DIR with a random filename, and returns a signed token the client
# can pass as a node `params.image_ref`. The token decodes back to the path.
# This lets a vault-flows image_input node carry an image reference end-to-end
# without persisting client data without consent: the file lives only while
# the token is valid (TTL), then a cleanup pass can remove orphans.

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
        return jwt.decode(
            token, JWT_SECRET, algorithms=["HS256"],
            audience="uploads", issuer=JWT_ISSUER,
        )
    except JWTError as e:
        raise HTTPException(status_code=403, detail=f"Invalid upload token: {e}")


class UploadImageResponse(BaseModel):
    token: str          # opaque ref the client passes back as a node param
    filename: str       # original filename (for display)
    size_bytes: int
    mime: str
    expires_in: int


@app.post("/uploads/image", response_model=UploadImageResponse)
async def upload_image(
    file: UploadFile = File(...),
    _principal=Depends(require_auth),
):
    """
    Accept a client-uploaded image. Stores it under UPLOADS_DIR with a random
    name, returns a signed token referencing it. The token is what the SPA
    embeds in an image_input node as `params.image_ref`.
    """
    mime = (file.content_type or "").lower()
    if mime not in _ALLOWED_IMAGE_MIMES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type: {mime}. Allowed: {sorted(_ALLOWED_IMAGE_MIMES)}",
        )
    original = file.filename or "upload"
    ext = os.path.splitext(original)[1].lower()
    if ext not in _ALLOWED_IMAGE_EXTS:
        ext = ".png"

    # Stream-read with size cap so a malicious upload can't OOM us.
    data = bytearray()
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > UPLOADS_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Upload exceeds {UPLOADS_MAX_BYTES} bytes",
            )
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")

    os.makedirs(UPLOADS_DIR, exist_ok=True)
    rel_name = f"{secrets.token_urlsafe(16)}{ext}"
    abs_path = os.path.join(UPLOADS_DIR, rel_name)
    with open(abs_path, "wb") as f:
        f.write(bytes(data))

    token = _sign_upload_token(rel_name, mime, original)
    return UploadImageResponse(
        token=token, filename=original, size_bytes=len(data),
        mime=mime, expires_in=UPLOADS_TOKEN_TTL_SECONDS,
    )


@app.get("/uploads/image/{token}")
async def serve_upload(token: str):
    """
    Serve a previously-uploaded image. Like /comfyui-image, the token IS the
    credential; unauthenticated so <img src> works from the browser.
    """
    claims = _verify_upload_token(token)
    rel = str(claims.get("p") or "")
    mime = str(claims.get("m") or "application/octet-stream")
    if not rel or os.path.isabs(rel) or ".." in rel.split(os.sep):
        raise HTTPException(status_code=400, detail="Invalid upload reference")
    abs_path = os.path.join(UPLOADS_DIR, rel)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Upload not found (may have been cleaned up)")
    with open(abs_path, "rb") as f:
        body = f.read()
    return Response(content=body, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})


def _resolve_image_ref_to_path(image_ref: str) -> str:
    """
    Convert an upload-token reference into an absolute path on disk so the
    worker can hand it to ComfyUI as a LoadImage input. Raises if the token
    is invalid or the file is missing.
    """
    claims = _verify_upload_token(image_ref)
    rel = str(claims.get("p") or "")
    if not rel or os.path.isabs(rel) or ".." in rel.split(os.sep):
        raise RuntimeError("Invalid image_ref token")
    abs_path = os.path.abspath(os.path.join(UPLOADS_DIR, rel))
    if not os.path.isfile(abs_path):
        raise RuntimeError(f"Upload referenced by token no longer exists ({rel})")
    return abs_path


async def _upload_to_comfyui(local_path: str, mime: str = "image/png") -> str:
    """
    Push a client upload into ComfyUI's input folder via its /upload/image API
    so LoadImage nodes in the graph can reference it by name. Returns the
    filename ComfyUI saved it under.
    """
    fname = os.path.basename(local_path)
    with open(local_path, "rb") as f:
        files = {"image": (fname, f.read(), mime)}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{COMFYUI_URL}/upload/image", files=files, data={"overwrite": "true"})
    if r.status_code != 200:
        raise RuntimeError(f"ComfyUI /upload/image -> {r.status_code}: {r.text[:200]}")
    body = r.json()
    return str(body.get("name") or fname)


# --- Per-node-type handlers (dispatcher pattern) ------------------------------
# Each handler takes the node + the joined upstream text and returns a dict of
# kwargs for ExecutionResultOut (without `nodeId`). The top-level loop adds
# nodeId and wraps it. Raising RuntimeError surfaces a clean per-node `error`
# without aborting the rest of the graph.

async def _handle_model_call_ollama(node: FlowNodeIn, upstream_text: str) -> dict:
    model = str(node.params.get("model") or "") or OLLAMA_DEFAULT_MODEL
    temperature = float(node.params.get("temperature") or 0.7)
    system_prompt = _render_template(
        str(node.params.get("system") or ""), upstream_text
    )
    user_prompt = _render_template(
        str(node.params.get("prompt") or ""), upstream_text
    ) or upstream_text
    if not user_prompt:
        raise RuntimeError("Ollama call has no prompt and no upstream input")
    output = await _ollama_generate(model, user_prompt, system_prompt, temperature)
    return {"output": output, "kind": "text"}


async def _handle_model_call_http(node: FlowNodeIn, upstream_text: str) -> dict:
    """
    Generic HTTP node. params:
      url:     str (required)
      method:  str (default GET)
      headers: dict[str, str]
      body:    str | dict | list — strings get template-substituted with upstream
    """
    url = str(node.params.get("url") or "")
    if not url:
        raise RuntimeError("http node requires params.url")
    method = str(node.params.get("method") or "GET").upper()
    headers = node.params.get("headers") or {}
    if not isinstance(headers, dict):
        raise RuntimeError("http node params.headers must be an object")
    body = node.params.get("body")
    if isinstance(body, str):
        body = _render_template(body, upstream_text)

    async with httpx.AsyncClient(timeout=HTTP_NODE_TIMEOUT_SECONDS) as client:
        try:
            if isinstance(body, (dict, list)):
                r = await client.request(method, url, headers=headers, json=body)
            elif body is None:
                r = await client.request(method, url, headers=headers)
            else:
                r = await client.request(method, url, headers=headers, content=str(body))
        except httpx.TimeoutException as e:
            raise RuntimeError(f"HTTP {method} {url} timed out") from e
        except httpx.RequestError as e:
            raise RuntimeError(f"HTTP {method} {url} failed: {e}") from e

    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {method} {url} -> {r.status_code}: {r.text[:200]}")

    ctype = (r.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        try:
            parsed = r.json()
        except Exception:
            return {"output": r.text, "kind": "text"}
        return {
            "output": r.text,
            "kind": "json",
            "data": parsed if isinstance(parsed, dict) else {"value": parsed},
        }
    return {"output": r.text, "kind": "text"}


async def _handle_comfyui_workflow(node: FlowNodeIn, upstream_text: str) -> dict:
    """
    Enqueue a saved ComfyUI workflow (from pipelines' own DB) as one step in
    the flow. Polls /jobs/{id} via in-process helpers until completion, then
    surfaces image_url / structured result back to the SPA.
    """
    workflow_id = str(node.params.get("workflow_id") or "")
    if not workflow_id:
        raise RuntimeError("comfyui_workflow node requires params.workflow_id")
    mode = str(node.params.get("mode") or "local")

    # Validate workflow exists before enqueueing (saves a roundtrip)
    if db_available():
        try:
            await WorkflowDB.get(id=workflow_id)
        except DoesNotExist:
            raise RuntimeError(f"ComfyUI workflow '{workflow_id}' not found in pipelines DB")
    else:
        wfs = _load_workflows_from_file()
        if not any(w.id == workflow_id for w in wfs):
            raise RuntimeError(f"ComfyUI workflow '{workflow_id}' not found in workflows.json")

    # Pass through any per-node `inputs` overrides (prompt, seed, etc.) so the
    # worker can template-substitute them into the saved graph at run time.
    # Any string value containing {{input}}/{{value}}/{{context}} is rendered
    # against upstream output — that's how an upstream image_input node's
    # token reaches the comfyui_workflow node's image_ref input.
    raw_inputs = node.params.get("inputs") if isinstance(node.params.get("inputs"), dict) else {}
    flow_inputs: dict = {}
    for k, v in (raw_inputs or {}).items():
        if isinstance(v, str):
            flow_inputs[k] = _render_template(v, upstream_text)
        else:
            flow_inputs[k] = v
    job = _new_job(
        kind="workflow_run",
        payload={"id": workflow_id, "mode": mode, "inputs": flow_inputs},
        requested_by={"user": "vault-flows", "via": "/flows/run"},
    )
    _write_job(job)
    _queue_job(app, job)
    job_id = job["id"]

    deadline = time.time() + COMFYUI_JOB_MAX_WAIT_SECONDS
    while time.time() < deadline:
        await asyncio.sleep(COMFYUI_JOB_POLL_INTERVAL_SECONDS)
        current = _read_job(job_id)
        if not current:
            raise RuntimeError(f"Job {job_id} disappeared from job store")
        status = current.get("status")
        if status == "succeeded":
            result = current.get("result") or {}
            image_url = result.get("image_url") or result.get("imageUrl")
            image_urls = result.get("image_urls") or result.get("imageUrls")
            if not isinstance(image_urls, list):
                image_urls = [image_url] if image_url else []
            payload = {
                "output": result.get("summary")
                or (f"[ComfyUI workflow {workflow_id} complete]" if not image_url else ""),
                "data": result if isinstance(result, dict) else {"value": result},
            }
            if image_url:
                payload["kind"] = "image"
                payload["imageUrl"] = image_url
                if image_urls:
                    payload["imageUrls"] = image_urls
            else:
                payload["kind"] = "job_result"
            return payload
        if status == "failed":
            raise RuntimeError(current.get("error") or "ComfyUI workflow failed")
        if status == "canceled":
            raise RuntimeError("ComfyUI workflow was canceled")

    raise RuntimeError(
        f"ComfyUI workflow '{workflow_id}' timed out after {COMFYUI_JOB_MAX_WAIT_SECONDS}s"
    )


async def _handle_model_call(node: FlowNodeIn, upstream_text: str) -> dict:
    """
    Provider-discriminated generation node. params.provider selects the backend.
    """
    provider = str(node.params.get("provider") or "ollama").lower()
    if provider == "ollama":
        return await _handle_model_call_ollama(node, upstream_text)
    if provider == "comfyui":
        return await _handle_comfyui_workflow(node, upstream_text)
    if provider == "http":
        return await _handle_model_call_http(node, upstream_text)
    raise RuntimeError(
        f"Unknown model_call provider '{provider}'. Supported: ollama, comfyui, http"
    )


def _forward_upstream_payload(
    node_id: str, edges: List[FlowEdgeIn], results: List[ExecutionResultOut]
) -> dict:
    """
    For display/output nodes: preserve the upstream node's kind/imageUrl/data
    instead of stringifying everything. If multiple upstreams, take the first
    non-empty one — graphs with N-to-1 fan-in are uncommon at display nodes.
    """
    upstream_ids = [e.source for e in edges if e.target == node_id]
    by_id = {r.nodeId: r for r in results}
    for src in upstream_ids:
        upstream = by_id.get(src)
        if upstream and not upstream.error:
            return {
                "output": upstream.output,
                "kind": upstream.kind or "text",
                "imageUrl": upstream.imageUrl,
                "imageUrls": upstream.imageUrls,
                "fileRef": upstream.fileRef,
                "data": upstream.data,
            }
    return {"output": "", "kind": "text"}


@app.post("/flows/run", response_model=FlowRunResponse)
async def flows_run(req: FlowRunRequest, _principal=Depends(require_auth)):
    """
    Walk a vault-flows graph topologically and dispatch each node to its
    handler. Supported node types:
      - input             — emits params.value (or prompt/topic/text fallback)
      - llm               — backward-compatible alias for model_call+ollama
      - model_call        — params.provider: 'ollama' | 'comfyui' | 'http'
      - comfyui_workflow  — runs a saved ComfyUI workflow as one step
      - transform         — template substitution
      - display/output    — forwards the upstream node's full payload
                            (text, image, JSON, etc.)

    Returns one ExecutionResult per node, in execution order. Errors on one
    node don't abort the run — that node gets an `error` field and downstream
    nodes still receive whatever upstream produced.
    """
    nodes = list(req.flow.nodes)
    edges = list(req.flow.edges)
    sorted_nodes = _flow_topo_sort(nodes, edges)

    context: dict[str, str] = {}
    results: List[ExecutionResultOut] = []

    for node in sorted_nodes:
        upstream_outputs = [
            context[e.source]
            for e in edges
            if e.target == node.id and e.source in context
        ]
        upstream_text = "\n\n".join(s for s in upstream_outputs if s)

        try:
            if node.type == "input":
                raw = (
                    node.params.get("value")
                    or node.params.get("prompt")
                    or node.params.get("topic")
                    or node.params.get("text")
                    or ""
                )
                payload: dict = {"output": str(raw), "kind": "text"}

            elif node.type == "image_input":
                # Emit the upload-token ref as the node's output, plus a
                # preview URL so display nodes can render the thumbnail.
                ref = str(node.params.get("image_ref") or "")
                preview = str(node.params.get("preview_url") or "")
                fname = str(node.params.get("filename") or "")
                if not ref:
                    raise RuntimeError("image_input node has no uploaded file")
                payload = {
                    "output": ref,
                    "kind": "image",
                    "imageUrl": preview or None,
                    "data": {"image_ref": ref, "filename": fname},
                }

            elif node.type == "llm":
                payload = await _handle_model_call_ollama(node, upstream_text)

            elif node.type == "model_call":
                payload = await _handle_model_call(node, upstream_text)

            elif node.type == "comfyui_workflow":
                payload = await _handle_comfyui_workflow(node, upstream_text)

            elif node.type == "transform":
                template = str(node.params.get("template") or "{{input}}")
                payload = {
                    "output": _render_template(template, upstream_text),
                    "kind": "text",
                }

            elif node.type in ("display", "output"):
                payload = _forward_upstream_payload(node.id, edges, results)

            else:
                # Unknown node type — pass upstream through so the graph still flows
                payload = {"output": upstream_text, "kind": "text"}

            context[node.id] = payload.get("output", "") or ""
            results.append(ExecutionResultOut(nodeId=node.id, **payload))

        except Exception as exc:
            err = str(exc)
            logger.warning(f"flows_run: node {node.id} ({node.type}) failed: {err}")
            context[node.id] = ""
            results.append(ExecutionResultOut(nodeId=node.id, output="", error=err))

    return FlowRunResponse(results=results)


@app.get("/jobs", response_model=List[JobSummary])
async def list_jobs(limit: int = 50, principal=Depends(require_auth)):
    if principal.get("kind") not in ("user", "api_key"):
        raise HTTPException(status_code=401, detail="Auth required")
    items = _list_jobs(limit=min(200, max(1, int(limit))))
    return [JobSummary(**_job_redact_for_list(item)) for item in items]


def _job_belongs_to_principal(job: dict, principal: dict) -> bool:
    """Match a job's requested_by against the calling principal."""
    rb = job.get("requested_by") or {}
    if principal.get("kind") == "user":
        user = principal.get("user")
        return rb.get("username") == getattr(user, "username", None) or rb.get("user") == "vault-flows"
    if principal.get("kind") == "api_key":
        key = principal.get("api_key")
        return rb.get("name") == getattr(key, "name", None)
    return False


@app.get("/jobs/recent", response_model=Optional[JobSummary])
async def get_recent_job(
    kind: Optional[str] = None,
    status: Optional[str] = None,
    principal=Depends(require_auth),
):
    """
    Return the caller's most recently-updated job (optionally filtered by
    kind and status). Used by the SPA's progress overlay to find the
    in-flight job for the current /flows/run.

    `status` accepts a CSV like 'queued,running' to match either.
    """
    if principal.get("kind") not in ("user", "api_key"):
        raise HTTPException(status_code=401, detail="Auth required")
    statuses = set(s.strip() for s in (status or "").split(",") if s.strip()) or None
    items = _list_jobs(limit=200)
    for item in items:  # already sorted by updated_at desc
        if kind and item.get("kind") != kind:
            continue
        if statuses and item.get("status") not in statuses:
            continue
        if not _job_belongs_to_principal(item, principal) and principal.get("kind") == "user":
            # Admin sees all; non-admin only their own
            user = principal.get("user")
            if not getattr(user, "is_admin", False):
                continue
        return JobSummary(**_job_redact_for_list(item))
    return None


@app.get("/jobs/{job_id}", response_model=JobDetail)
async def get_job(job_id: str, principal=Depends(require_auth)):
    if principal.get("kind") not in ("user", "api_key"):
        raise HTTPException(status_code=401, detail="Auth required")
    job = _read_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    payload = dict(job)
    return JobDetail(**payload)

@app.post("/jobs/{job_id}/cancel", response_model=JobDetail)
async def cancel_job(job_id: str, principal=Depends(require_auth)):
    if principal.get("kind") not in ("user", "api_key"):
        raise HTTPException(status_code=401, detail="Auth required")
    job = _read_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") in ("succeeded", "failed"):
        return JobDetail(**job)
    job["status"] = "canceled"
    job["updated_at"] = _job_now()
    _write_job(job)
    return JobDetail(**job)


class FaceswapSubmitRequest(BaseModel):
    source_face: str
    target_image: str


class FaceswapCompleteRequest(BaseModel):
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None


@app.post("/api/jobs/faceswap")
async def submit_faceswap(req: FaceswapSubmitRequest, request: Request):
    """
    Public endpoint to submit a faceswap job.
    """
    client_ip = _get_client_ip(request) or ""
    if not _is_trusted_client_ip(client_ip):
        _enforce_job_submit_rate_limit(client_ip)

    job = _new_job(
        kind="faceswap",
        payload={
            "source_face": req.source_face,
            "target_image": req.target_image
        },
        requested_by={"kind": "public", "ip": client_ip}
    )
    _write_job(job)
    return {"status": "queued", "jobId": job["id"]}


@app.post("/api/jobs/claim", response_model=Optional[JobDetail])
async def claim_faceswap_job(request: Request):
    """
    Tailscale secure endpoint for clopeux-desktop to claim the oldest pending faceswap job.
    """
    client_ip = _get_client_ip(request) or ""
    if not _is_trusted_client_ip(client_ip):
        raise HTTPException(status_code=403, detail="Forbidden source")

    jobs = _list_jobs(limit=200)
    queued_jobs = [j for j in jobs if j.get("status") == "queued" and j.get("kind") == "faceswap"]
    if not queued_jobs:
        return None

    # Sort to fetch the oldest queued job first
    queued_jobs.sort(key=lambda j: float(j.get("created_at") or 0))
    target_job = queued_jobs[0]

    target_job["status"] = "running"
    target_job["updated_at"] = _job_now()
    _write_job(target_job)

    return JobDetail(**target_job)


@app.get("/api/jobs/{job_id}", response_model=JobDetail)
async def get_public_job_status(job_id: str):
    """
    Public unauthenticated endpoint to query the status of a specific job.
    """
    job = _read_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobDetail(**job)


@app.post("/api/jobs/{job_id}/complete", response_model=JobDetail)

async def complete_faceswap_job(job_id: str, req: FaceswapCompleteRequest, request: Request):
    """
    Tailscale secure endpoint for clopeux-desktop to commit finished job states.
    """
    client_ip = _get_client_ip(request) or ""
    if not _is_trusted_client_ip(client_ip):
        raise HTTPException(status_code=403, detail="Forbidden source")

    job = _read_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job["status"] = req.status
    job["updated_at"] = _job_now()
    if req.result is not None:
        job["result"] = req.result
    if req.error is not None:
        job["error"] = req.error

    _write_job(job)
    return JobDetail(**job)


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
def update_config(req: ConfigUpdateRequest, principal=Depends(require_auth)):
    if principal.get("kind") != "user" or not principal["user"].is_admin:
        raise HTTPException(status_code=403, detail="Admin required")
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
def set_models_dir(req: ModelsDirRequest, principal=Depends(require_auth)):
    if principal.get("kind") != "user" or not principal["user"].is_admin:
        raise HTTPException(status_code=403, detail="Admin required")
    global DEFAULT_MODELS_DIR
    resolved = req.dir_path or req.models_dir or req.modelsDir
    if resolved is None:
        raise HTTPException(status_code=422, detail="Expected one of dir_path, models_dir, or modelsDir")
    DEFAULT_MODELS_DIR = resolved
    APP_CONFIG["modelsDir"] = resolved
    return {"models_dir": DEFAULT_MODELS_DIR, "dir_path": DEFAULT_MODELS_DIR, "modelsDir": DEFAULT_MODELS_DIR}




# --- Media Pipeline Configuration ---
ZIPPER_DEST_DIR = r"C:\Users\Administrator\Desktop\Github Repos\python-zipper\.downloaded"
RD_TOKEN_PATH = r"C:\Users\Administrator\Desktop\Github Repos\.access\realdebrid_api.txt"

# Add python-zipper scraper module path dynamically
sys.path.append(r"C:\Users\Administrator\Desktop\Github Repos\python-zipper\dataset_builder")
try:
    import scraper
except ImportError:
    scraper = None
    logger.warning("Media Pipeline: Failed to import 'scraper' module. Check path.")

zipper_cancel_event = threading.Event()
THROTTLE_SPEED_BPS = 5 * 1024 * 1024  # 5 MiB/s default

active_zipper_jobs = {}
zipper_jobs_lock = threading.Lock()

def update_job_progress(corr_id: str, status: Optional[str] = None, increment_processed: bool = False, increment_images: bool = False, increment_other: bool = False, total_links: Optional[int] = None):
    parent_id = corr_id.split("-")[0] if "-" in corr_id else corr_id
    with zipper_jobs_lock:
        if parent_id not in active_zipper_jobs:
            return
        job = active_zipper_jobs[parent_id]
        if status:
            job["status"] = status
        if increment_processed:
            job["processed_links"] += 1
        if increment_images:
            job["images_count"] += 1
        if increment_other:
            job["other_files_count"] += 1
        if total_links is not None:
            job["total_links"] = total_links
        job["updated_at"] = time.time()
        
        # Auto-complete status
        if job["processed_links"] >= job["total_links"] and job["status"] == "running":
            job["status"] = "completed"
            
        # Limit memory to 50 jobs
        if len(active_zipper_jobs) > 50:
            sorted_jobs = sorted(active_zipper_jobs.items(), key=lambda x: x[1]["created_at"])
            for old_id, _ in sorted_jobs[:len(active_zipper_jobs) - 50]:
                active_zipper_jobs.pop(old_id, None)

def throttle_chunk(chunk_size, start_time):
    if THROTTLE_SPEED_BPS:
        min_time = chunk_size / THROTTLE_SPEED_BPS
        elapsed = time.time() - start_time
        if elapsed < min_time:
            time.sleep(min_time - elapsed)

def get_rd_token():
    try:
        if os.path.exists(RD_TOKEN_PATH):
            with open(RD_TOKEN_PATH, 'r') as f:
                return f.read().strip()
    except Exception as e:
        logger.error(f"[Media Pipeline] Failed to read Real-Debrid token: {e}")
    return None

def unrestrict_link_rd(url, rd_token, corr_id):
    if not rd_token:
        logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Real-Debrid token not available. Skipping unrestriction.")
        return url
    try:
        headers = {
            'Authorization': f'Bearer {rd_token}',
            'User-Agent': 'Mozilla/5.0'
        }
        resp = requests.post(
            "https://api.real-debrid.com/rest/1.0/unrestrict/link",
            headers=headers,
            data={'link': url},
            timeout=12
        )
        if resp.status_code == 200:
            data = resp.json()
            dl_url = data.get('download')
            if dl_url:
                logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Real-Debrid successfully unrestricted: {url} -> {dl_url}")
                return dl_url
        else:
            logger.warning(f"[correlationId: {corr_id}] [Media Pipeline] Real-Debrid error {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"[correlationId: {corr_id}] [Media Pipeline] Real-Debrid unrestriction exception: {e}")
    return url

def bypass_linkvertise(url, corr_id):
    bypass_services = [
        "https://trw.lat/api/bypass",
        "https://api.bypass.vip/bypass",
        "https://free.bypass-api.com/bypass"
    ]
    for service in bypass_services:
        try:
            logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Attempting bypass via {service} for: {url}")
            resp = requests.get(service, params={'url': url}, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                res_link = None
                if data.get('success'):
                    res_link = data.get('result') or data.get('destination')
                elif 'destination' in data:
                    res_link = data['destination']
                elif 'result' in data:
                    res_link = data['result']
                
                if res_link and res_link.lower().startswith("http"):
                    return res_link
        except Exception as e:
            logger.warning(f"[correlationId: {corr_id}] [Media Pipeline] Bypass service {service} error: {e}")
    return url

def download_image_throttled(url, headers, corr_id):
    try:
        resp = requests.get(url, headers=headers, stream=True, timeout=10)
        if resp.status_code != 200:
            return None
        
        content = bytearray()
        for chunk in resp.iter_content(chunk_size=8192):
            if zipper_cancel_event.is_set():
                return None
            if chunk:
                start_chunk = time.time()
                content.extend(chunk)
                throttle_chunk(len(chunk), start_chunk)
        return bytes(content)
    except Exception as e:
        logger.error(f"[correlationId: {corr_id}] [Media Pipeline] Failed to download image from {url}: {e}")
        return None

def _run_scraper_thread(url, selector, playwright, batch_size, corr_id):
    logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Background scraper task started for URL: {url}")
    if not scraper:
        logger.error(f"[correlationId: {corr_id}] [Media Pipeline] Scraper module not loaded. Aborting scraper.")
        update_job_progress(corr_id, status="failed")
        return
        
    os.makedirs(ZIPPER_DEST_DIR, exist_ok=True)
    try:
        if playwright:
            urls = scraper.scrape_with_playwright(url, selector)
        else:
            urls = scraper.scrape_with_requests(url, selector)
    except Exception as e:
        logger.error(f"[correlationId: {corr_id}] [Media Pipeline] Scraping exception: {e}")
        update_job_progress(corr_id, status="failed")
        return
        
    if not urls:
        logger.info(f"[correlationId: {corr_id}] [Media Pipeline] No media URLs found for: {url}")
        update_job_progress(corr_id, status="completed")
        return
        
    update_job_progress(corr_id, total_links=len(urls))
    _download_and_process_links(url, urls, batch_size, corr_id)

def _run_downloader_thread(url, links, batch_size, corr_id):
    logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Background downloader task started for URL: {url} ({len(links)} links)")
    os.makedirs(ZIPPER_DEST_DIR, exist_ok=True)
    _download_and_process_links(url, links, batch_size, corr_id)

def _download_and_process_links(page_url, raw_links, batch_size, corr_id):
    if not scraper:
        logger.error(f"[correlationId: {corr_id}] [Media Pipeline] Scraper module not loaded. Aborting process.")
        update_job_progress(corr_id, status="failed")
        return
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    url_slug = scraper.get_url_slug(page_url)
    rd_token = get_rd_token()
    
    # De-duplicate links
    unique_urls = []
    seen = set()
    for u in raw_links:
        full_url = urljoin(page_url, u)
        if (full_url.startswith("http://") or full_url.startswith("https://")) and full_url not in seen:
            seen.add(full_url)
            unique_urls.append(full_url)

    update_job_progress(corr_id, total_links=len(unique_urls))
    logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Processing {len(unique_urls)} link(s)...")

    image_urls = []
    
    for idx, url in enumerate(unique_urls):
        if zipper_cancel_event.is_set():
            logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Task aborted by user before processing links.")
            update_job_progress(corr_id, status="aborted")
            return
            
        file_corr_id = f"{corr_id}-{idx:03d}"
        
        # 1. Bypass shorteners
        resolved_url = url
        if any(domain in url.lower() for domain in ["linkvertise.com", "direct-link.net", "link-center.net", "link-hub.net", "link-target.net"]):
            resolved_url = bypass_linkvertise(url, file_corr_id)
            logger.info(f"[correlationId: {file_corr_id}] [Media Pipeline] Bypassed {url} -> {resolved_url}")

        # 2. Unrestrict premium hosts
        final_url = resolved_url
        is_premium = any(domain in resolved_url.lower() for domain in [
            "mega.nz", "keep2share.cc", "k2s.cc", "fileboom.me", "fboom.me",
            "rapidgator.net", "rg.to", "katfile.com", "tezfiles.com", "pixeldrain.com"
        ])
        if is_premium:
            final_url = unrestrict_link_rd(resolved_url, rd_token, file_corr_id)
            logger.info(f"[correlationId: {file_corr_id}] [Media Pipeline] Unrestricted {resolved_url} -> {final_url}")

        # 3. Determine if it's an image or other file
        parsed = urlparse(final_url)
        ext = os.path.splitext(parsed.path)[1].lower().strip(".")
        
        is_image = ext in ["jpg", "jpeg", "png", "gif", "webp", "svg"]
        
        if is_image:
            image_urls.append((final_url, file_corr_id))
        else:
            # Save non-image file directly in background
            threading.Thread(target=_download_direct_file_worker, args=(final_url, headers, file_corr_id), daemon=True).start()

    # Download and zip remaining image files in batches
    if image_urls:
        _download_and_zip_images_worker(url_slug, page_url, image_urls, batch_size, headers, corr_id)

def _download_direct_file_worker(url, headers, file_corr_id):
    file_path = None
    try:
        logger.info(f"[correlationId: {file_corr_id}] [Media Pipeline] Starting direct download for: {url}")
        resp = requests.get(url, headers=headers, stream=True, timeout=120)
        if resp.status_code != 200:
            logger.warning(f"[correlationId: {file_corr_id}] [Media Pipeline] Direct download failed for {url}: status {resp.status_code}")
            update_job_progress(file_corr_id, increment_processed=True)
            return
            
        content_disp = resp.headers.get('content-disposition', '')
        filename = ""
        if 'filename=' in content_disp:
            filename = content_disp.split('filename=')[1].strip('"\'')
        
        if not filename:
            parsed = urlparse(url)
            filename = os.path.basename(parsed.path)
            
        if not filename:
            filename = f"download_{hashlib.md5(url.encode()).hexdigest()[:8]}.bin"

        # Clean filename
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        file_path = os.path.join(ZIPPER_DEST_DIR, filename)
        
        logger.info(f"[correlationId: {file_corr_id}] [Media Pipeline] Saving to: {file_path}")
        
        with open(file_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if zipper_cancel_event.is_set():
                    logger.info(f"[correlationId: {file_corr_id}] [Media Pipeline] Direct download aborted by user.")
                    f.close()
                    if os.path.exists(file_path):
                        try: os.remove(file_path)
                        except: pass
                    update_job_progress(file_corr_id, status="aborted", increment_processed=True)
                    return
                if chunk:
                    start_chunk = time.time()
                    f.write(chunk)
                    throttle_chunk(len(chunk), start_chunk)
                    
        logger.info(f"[correlationId: {file_corr_id}] [Media Pipeline] Completed download: {filename}")
        update_job_progress(file_corr_id, increment_processed=True, increment_other=True)
    except Exception as e:
        logger.error(f"[correlationId: {file_corr_id}] [Media Pipeline] Error downloading {url}: {e}")
        update_job_progress(file_corr_id, increment_processed=True)

def _download_and_zip_images_worker(url_slug, page_url, img_info_list, batch_size, headers, corr_id):
    import zipfile
    import random
    
    zip_writer = None
    zip_path = None
    count = 0
    zip_file_count = 0
    
    logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Downloading {len(img_info_list)} images for slug '{url_slug}'...")

    for img_url, file_corr_id in img_info_list:
        if zipper_cancel_event.is_set():
            if zip_writer is not None:
                zip_writer.close()
                logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Closed active ZIP during cancellation: {zip_path}")
            logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Zipping task aborted by user.")
            update_job_progress(corr_id, status="aborted")
            return

        parsed_img = urlparse(img_url)
        ext = os.path.splitext(parsed_img.path)[1].lower().strip(".")
        if ext not in ["jpg", "jpeg", "png", "gif", "webp", "svg"]:
            ext = "jpg"

        logger.info(f"[correlationId: {file_corr_id}] [Media Pipeline] Downloading image: {img_url}")
        content = download_image_throttled(img_url, headers, file_corr_id)
        if not content:
            update_job_progress(file_corr_id, increment_processed=True)
            continue

        if len(content) < 40 * 1024:
            logger.info(f"[correlationId: {file_corr_id}] [Media Pipeline] Skipping image under 40KB ({len(content)} bytes): {img_url}")
            update_job_progress(file_corr_id, increment_processed=True)
            continue

        if zip_writer is None:
            random_suffix = random.randint(0, 9000)
            zip_filename = f"{url_slug}_{random_suffix}.zip"
            zip_path = os.path.join(ZIPPER_DEST_DIR, zip_filename)
            zip_writer = zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED)
            zip_file_count += 1
            logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Created new ZIP archive: {zip_path}")

        filename_in_zip = f"{url_slug}_{str(count + 1).zfill(3)}.{ext}"
        try:
            zip_writer.writestr(filename_in_zip, content)
            count += 1
            logger.info(f"[correlationId: {file_corr_id}] [Media Pipeline] Added to archive {filename_in_zip}")
            update_job_progress(file_corr_id, increment_processed=True, increment_images=True)
        except Exception as e:
            logger.error(f"[correlationId: {file_corr_id}] [Media Pipeline] Failed to write to zip: {e}")
            update_job_progress(file_corr_id, increment_processed=True)

        if count > 0 and count % batch_size == 0:
            zip_writer.close()
            zip_writer = None
            logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Closed ZIP archive {zip_path}")
            count = 0

    if zip_writer is not None:
        zip_writer.close()
        logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Closed final ZIP archive {zip_path}")

    logger.info(f"[correlationId: {corr_id}] [Media Pipeline] Finished downloading and zipping task for: {page_url}")


# --- Media Pipeline FastAPI Endpoints ---
class ScrapePayload(BaseModel):
    url: str
    selector: Optional[str] = ""
    playwright: Optional[bool] = False
    batch_size: Optional[int] = 100

class DownloadPayload(BaseModel):
    url: str
    links: List[str]
    batch_size: Optional[int] = 100

@app.get("/health")
def api_health():
    return {"status": "online"}

@app.get("/api/jobs")
def api_get_jobs():
    with zipper_jobs_lock:
        return {"jobs": active_zipper_jobs}

@app.post("/scrape")
def api_scrape(payload: ScrapePayload, request: Request):
    corr_id = request.state.correlation_id
    with zipper_jobs_lock:
        active_zipper_jobs[corr_id] = {
            "status": "running",
            "url": payload.url,
            "total_links": 0,
            "processed_links": 0,
            "images_count": 0,
            "other_files_count": 0,
            "created_at": time.time(),
            "updated_at": time.time()
        }
    zipper_cancel_event.clear()
    threading.Thread(
        target=_run_scraper_thread,
        args=(payload.url, payload.selector, payload.playwright, payload.batch_size, corr_id),
        daemon=True
    ).start()
    return {"status": "Scraping task started", "correlationId": corr_id}

@app.post("/download")
def api_download(payload: DownloadPayload, request: Request):
    corr_id = request.state.correlation_id
    with zipper_jobs_lock:
        active_zipper_jobs[corr_id] = {
            "status": "running",
            "url": payload.url,
            "total_links": len(payload.links),
            "processed_links": 0,
            "images_count": 0,
            "other_files_count": 0,
            "created_at": time.time(),
            "updated_at": time.time()
        }
    zipper_cancel_event.clear()
    threading.Thread(
        target=_run_downloader_thread,
        args=(payload.url, payload.links, payload.batch_size, corr_id),
        daemon=True
    ).start()
    return {"status": "Download task started", "count": len(payload.links), "correlationId": corr_id}

@app.post("/abort")
@app.post("/api/abort")
def api_abort():
    zipper_cancel_event.set()
    logger.info("[Media Pipeline] Cancellation event triggered by user.")
    with zipper_jobs_lock:
        for job in active_zipper_jobs.values():
            if job["status"] == "running":
                job["status"] = "aborted"
                job["updated_at"] = time.time()
    return {"status": "Aborted"}


# --- Wildcard Proxy Endpoints ---
async def _async_proxy(target_url: str, request: Request):
    params = dict(request.query_params)
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length"]}
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.request(
                method=request.method,
                url=target_url,
                params=params,
                headers=headers,
                content=body,
                follow_redirects=False
            )
            
            resp_headers = {}
            for k, v in resp.headers.items():
                if k.lower() not in ["content-encoding", "transfer-encoding", "content-length", "access-control-allow-origin"]:
                    resp_headers[k] = v
                    
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=resp_headers
            )
        except Exception as e:
            return Response(
                content=f"Proxy error: {e}".encode("utf-8"),
                status_code=502
            )

@app.api_route("/api/huggingface/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_huggingface(path: str, request: Request):
    return await _async_proxy(f"https://huggingface.co/api/{path}", request)

@app.api_route("/api/civitai/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_civitai(path: str, request: Request):
    return await _async_proxy(f"https://civitai.red/api/{path}", request)

@app.api_route("/api/comfyui/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_comfyui(path: str, request: Request):
    return await _async_proxy(f"{COMFYUI_URL}/{path}", request)

@app.api_route("/api/ollama/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_ollama(path: str, request: Request):
    return await _async_proxy(f"{OLLAMA_URL}/{path}", request)




# --- Script Entrypoint ---
if __name__ == "__main__":
    import uvicorn
    # Default to binding on all interfaces so the API can be reached over LAN/Tailscale
    # when intentionally exposed (for example via a VPS reverse proxy).
    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", "9001"))
    reload = os.environ.get("UVICORN_RELOAD", "1") == "1"
    uvicorn.run("api_server:app", host=host, port=port, reload=reload)
