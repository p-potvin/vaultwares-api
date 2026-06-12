import time
import secrets
import ipaddress
from typing import Optional
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from db import UserAccount, ApiKey
from api.config import (
    AUTH_ENABLED, JWT_SECRET, JWT_ISSUER, JWT_AUDIENCE, JWT_TTL_SECONDS,
    API_KEY_PEPPER, TRUSTED_CLIENT_IPS, _trusted_client_ips,
    _tailscale_networks, _trusted_proxy_networks
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
    peer_ip = request.client.host if request.client else None
    if _is_trusted_proxy_peer(peer_ip):
        forwarded = request.headers.get("x-forwarded-proto")
        if forwarded:
            return forwarded.split(",")[0].strip().lower()
    return request.url.scheme.lower()

def _get_client_ip(request: Request) -> Optional[str]:
    peer_ip = request.client.host if request.client else None
    if not peer_ip:
        return None
    try:
        peer_obj = ipaddress.ip_address(peer_ip)
    except ValueError:
        return peer_ip

    is_trusted_proxy = _is_trusted_proxy_peer(peer_ip)
    if not is_trusted_proxy:
        return peer_ip

    xff = request.headers.get("x-forwarded-for", "")
    if not xff:
        return peer_ip

    ips = [ip.strip() for ip in xff.split(",") if ip.strip()]
    for ip_str in reversed(ips):
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
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

    return ips[-1] if ips else peer_ip

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
