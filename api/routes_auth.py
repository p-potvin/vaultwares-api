import re
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request
from passlib.context import CryptContext
from app.security.ml_kem import VaultMLKEM
from db import UserAccount, ApiKey
from api.models import (
    PqcHandshakeRequest, PqcHandshakeResponse, LoginRequest, LoginResponse,
    RegisterRequest, RegisterResponse, MeResponse, ApiKeyCreateRequest,
    ApiKeyCreateResponse
)
from api.config import (
    AUTH_ENABLED, JWT_TTL_SECONDS, BOOTSTRAP_ADMIN_USERNAME,
    BOOTSTRAP_ADMIN_PASSWORD, BOOTSTRAP_ADMIN_IS_DISABLED,
    GATEWAY_REQUIRED_PUBLIC
)
from api.auth import (
    require_auth, pwd_context, _create_access_token, _get_client_ip,
    _is_trusted_client_ip, _hash_api_key, _verify_api_key
)
from api.database import db_available
from collections import defaultdict, deque
import time

router = APIRouter()

USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
MIN_PASSWORD_LENGTH = 8
REGISTER_WINDOW_SECONDS = 60
REGISTER_MAX_PER_WINDOW = 3
_register_buckets = defaultdict(lambda: deque())

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

def _origin_allowed(origin: str) -> bool:
    if not origin: return False
    from api.app import _cors_allow_origins
    if origin in _cors_allow_origins: return True
    return False

def _gateway_secret_valid(request: Request) -> bool:
    from api.config import GATEWAY_SHARED_SECRET, GATEWAY_HEADER_NAME
    if not GATEWAY_SHARED_SECRET: return False
    provided = request.headers.get(GATEWAY_HEADER_NAME, "")
    if not provided: return False
    return secrets.compare_digest(provided, GATEWAY_SHARED_SECRET)

@router.post("/security/pqc/handshake", response_model=PqcHandshakeResponse)
async def pqc_handshake(payload: PqcHandshakeRequest):
    try:
        result = VaultMLKEM.encapsulate(payload.client_public_key)
        return PqcHandshakeResponse(server_cipher_text=result["cipher_text"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request):
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

    user = await UserAccount.get_or_none(username=payload.username)
    if not user or user.is_disabled:
        pwd_context.dummy_verify()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not pwd_context.verify(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = _create_access_token(user.id, user.username, bool(user.is_admin))
    return LoginResponse(access_token=token, expires_in=max(60, JWT_TTL_SECONDS))

@router.post("/auth/register", response_model=RegisterResponse)
async def register(payload: RegisterRequest, request: Request):
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
    token = _create_access_token(new_user.id, new_user.username, False)
    return RegisterResponse(
        username=new_user.username,
        access_token=token,
        expires_in=max(60, JWT_TTL_SECONDS),
    )

@router.get("/auth/me", response_model=MeResponse)
async def me(principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user = principal["user"]
    return MeResponse(username=user.username, is_admin=bool(user.is_admin))

@router.post("/auth/api-keys", response_model=ApiKeyCreateResponse)
async def create_api_key(request: Request, payload: ApiKeyCreateRequest, principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user = principal["user"]
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")

    client_ip = _get_client_ip(request)
    if not _is_trusted_client_ip(client_ip):
        raise HTTPException(status_code=403, detail="Trusted network required")

    temp_hash = "tmp_" + secrets.token_urlsafe(16)
    obj = await ApiKey.create(name=payload.name, key_hash=temp_hash, scopes=payload.scopes or [])

    raw_key = f"vwk_{obj.id}_{secrets.token_urlsafe(32)}"
    key_hash = _hash_api_key(raw_key)

    obj.key_hash = key_hash
    await obj.save()
    return ApiKeyCreateResponse(api_key=raw_key, name=payload.name)
