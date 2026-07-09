"""VaultWares Identity Manager — Vault, Device, and Sync API routes.

These endpoints implement the zero-knowledge vault sync protocol.
The server stores ciphertext + metadata only. It never decrypts vault items.
"""
import uuid
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List
from api.auth import require_auth, _create_access_token
from api.database import db_available
from db import UserAccount, VaultItem, DeviceRegistration, SyncCursor
from api.config import JWT_SECRET, JWT_ISSUER, JWT_AUDIENCE, JWT_TTL_SECONDS
from jose import jwt

router = APIRouter(prefix="/v1")


# ─── Models ───────────────────────────────────────────────────────────────────

class VaultEnvelopeModel(BaseModel):
    version: int = 1
    itemType: str
    ciphertext: str
    nonce: str
    encapsulatedKey: str
    metadata: dict
    signature: str
    createdAt: str
    updatedAt: str
    authorDeviceId: str


class VaultItemCreate(BaseModel):
    envelope: VaultEnvelopeModel


class VaultItemUpdate(BaseModel):
    envelope: VaultEnvelopeModel


class VaultItemResponse(BaseModel):
    id: str
    envelope: VaultEnvelopeModel
    deletedAt: Optional[str] = None


class VaultItemListResponse(BaseModel):
    items: List[VaultItemResponse]


class AuthRegisterRequest(BaseModel):
    email: str
    kemPublicKey: str
    sigPublicKey: str
    deviceName: str
    deviceClass: str = "browser"
    platform: str = ""


class AuthRegisterResponse(BaseModel):
    userId: int
    deviceId: str
    deviceRole: str = "master"
    accessToken: str
    refreshToken: str


class DeviceRegisterRequest(BaseModel):
    kemPublicKey: str
    sigPublicKey: str
    deviceName: str
    deviceClass: str = "browser"
    platform: str = ""


class DeviceRegisterResponse(BaseModel):
    deviceId: str
    deviceRole: str
    approvalState: str


class DeviceApproveRequest(BaseModel):
    approvalSignature: str


class DeviceListResponse(BaseModel):
    devices: List[dict]


class SyncPushRequest(BaseModel):
    items: List[dict]
    cursor: Optional[str] = None


class SyncPushResponse(BaseModel):
    cursor: str
    conflicts: List[dict]


class SyncPullResponse(BaseModel):
    items: List[dict]
    cursor: str
    hasMore: bool


# ─── Auth ─────────────────────────────────────────────────────────────────────

@router.post("/auth/register", response_model=AuthRegisterResponse)
async def identity_register(payload: AuthRegisterRequest, request: Request):
    """Register a new identity manager account with PQC keys. First device becomes master."""
    if not db_available():
        raise HTTPException(status_code=503, detail="Database unavailable")

    existing = await UserAccount.get_or_none(username=payload.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = await UserAccount.create(
        username=payload.email,
        password_hash="",  # No password — auth is via PQC keys + JWT
        is_admin=False,
        is_disabled=False,
    )

    device_id = str(uuid.uuid4())
    await DeviceRegistration.create(
        id=device_id,
        user=user,
        device_name=payload.deviceName,
        device_class=payload.deviceClass,
        platform=payload.platform,
        device_role="master",
        pqc_public_key=payload.kemPublicKey,
        pqc_sig_public_key=payload.sigPublicKey,
        approval_state="approved",
    )

    access_token = _create_access_token(user.id, user.username, False)
    refresh_token = _create_access_token(user.id, user.username, False, ttl_override=86400)

    return AuthRegisterResponse(
        userId=user.id,
        deviceId=device_id,
        deviceRole="master",
        accessToken=access_token,
        refreshToken=refresh_token,
    )


@router.post("/auth/refresh")
async def identity_refresh(request: Request):
    """Refresh access token using refresh token."""
    body = await request.json()
    refresh_token = body.get("refreshToken")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="refreshToken required")

    try:
        payload = jwt.decode(refresh_token, JWT_SECRET, audience=JWT_AUDIENCE, issuer=JWT_ISSUER, algorithms=["HS256"])
        user_id = payload.get("uid")
        username = payload.get("usr")
        if not user_id or not username:
            raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = await UserAccount.get_or_none(id=user_id)
    if not user or user.is_disabled:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    new_access = _create_access_token(user.id, user.username, False)
    new_refresh = _create_access_token(user.id, user.username, False, ttl_override=86400)

    return {"accessToken": new_access, "refreshToken": new_refresh}


# ─── Vault Items ──────────────────────────────────────────────────────────────

def _envelope_to_dict(env: VaultEnvelopeModel) -> dict:
    return {
        "version": env.version,
        "itemType": env.itemType,
        "ciphertext": env.ciphertext,
        "nonce": env.nonce,
        "encapsulatedKey": env.encapsulatedKey,
        "metadata": env.metadata,
        "signature": env.signature,
        "createdAt": env.createdAt,
        "updatedAt": env.updatedAt,
        "authorDeviceId": env.authorDeviceId,
    }


def _item_to_response(item: VaultItem) -> VaultItemResponse:
    return VaultItemResponse(
        id=item.id,
        envelope=VaultEnvelopeModel(
            version=item.envelope_version,
            itemType=item.item_type,
            ciphertext=item.ciphertext,
            nonce=item.nonce,
            encapsulatedKey=item.encapsulated_key,
            metadata=item.metadata if isinstance(item.metadata, dict) else {},
            signature=item.signature,
            createdAt=item.created_at.isoformat() if item.created_at else "",
            updatedAt=item.updated_at.isoformat() if item.updated_at else "",
            authorDeviceId=item.author_device_id or "",
        ),
        deletedAt=item.deleted_at.isoformat() if item.deleted_at else None,
    )


@router.post("/vault/items", response_model=VaultItemResponse)
async def create_vault_item(payload: VaultItemCreate, principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user = principal["user"]

    item_id = str(uuid.uuid4())
    env = payload.envelope
    item = await VaultItem.create(
        id=item_id,
        user=user,
        item_type=env.itemType,
        envelope_version=env.version,
        ciphertext=env.ciphertext,
        nonce=env.nonce,
        encapsulated_key=env.encapsulatedKey,
        metadata=env.metadata,
        signature=env.signature,
        author_device_id=env.authorDeviceId,
    )
    return _item_to_response(item)


@router.get("/vault/items", response_model=VaultItemListResponse)
async def list_vault_items(principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user = principal["user"]

    items = await VaultItem.filter(user=user, deleted_at__isnull=True)
    return VaultItemListResponse(items=[_item_to_response(i) for i in items])


@router.get("/vault/items/{item_id}", response_model=VaultItemResponse)
async def get_vault_item(item_id: str, principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user = principal["user"]

    item = await VaultItem.get_or_none(id=item_id, user=user)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return _item_to_response(item)


@router.put("/vault/items/{item_id}", response_model=VaultItemResponse)
async def update_vault_item(item_id: str, payload: VaultItemUpdate, principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user = principal["user"]

    item = await VaultItem.get_or_none(id=item_id, user=user)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    env = payload.envelope
    item.item_type = env.itemType
    item.envelope_version = env.version
    item.ciphertext = env.ciphertext
    item.nonce = env.nonce
    item.encapsulated_key = env.encapsulatedKey
    item.metadata = env.metadata
    item.signature = env.signature
    item.author_device_id = env.authorDeviceId
    await item.save()
    return _item_to_response(item)


@router.delete("/vault/items/{item_id}")
async def delete_vault_item(item_id: str, principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user = principal["user"]

    item = await VaultItem.get_or_none(id=item_id, user=user)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    from datetime import datetime, timezone
    item.deleted_at = datetime.now(timezone.utc)
    await item.save()
    return {"status": "deleted"}


# ─── Sync ─────────────────────────────────────────────────────────────────────

@router.post("/vault/sync", response_model=SyncPushResponse)
async def sync_push(payload: SyncPushRequest, principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user = principal["user"]

    for item_data in payload.items:
        item_id = item_data.get("id")
        env = item_data.get("envelope", {})
        if not item_id or not env:
            continue

        existing = await VaultItem.get_or_none(id=item_id, user=user)
        if existing:
            existing.item_type = env.get("itemType", existing.item_type)
            existing.envelope_version = env.get("version", 1)
            existing.ciphertext = env.get("ciphertext", existing.ciphertext)
            existing.nonce = env.get("nonce", existing.nonce)
            existing.encapsulated_key = env.get("encapsulatedKey", existing.encapsulated_key)
            existing.metadata = env.get("metadata", existing.metadata)
            existing.signature = env.get("signature", existing.signature)
            existing.author_device_id = env.get("authorDeviceId", existing.author_device_id)
            existing.deleted_at = None
            await existing.save()
        else:
            await VaultItem.create(
                id=item_id,
                user=user,
                item_type=env.get("itemType", "login"),
                envelope_version=env.get("version", 1),
                ciphertext=env.get("ciphertext", ""),
                nonce=env.get("nonce", ""),
                encapsulated_key=env.get("encapsulatedKey", ""),
                metadata=env.get("metadata", {}),
                signature=env.get("signature", ""),
                author_device_id=env.get("authorDeviceId", ""),
            )

    cursor = str(int(time.time()))
    return SyncPushResponse(cursor=cursor, conflicts=[])


@router.get("/vault/sync/changes", response_model=SyncPullResponse)
async def sync_pull(cursor: Optional[str] = None, principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user = principal["user"]

    items = await VaultItem.filter(user=user)
    items_list = []
    for item in items:
        items_list.append({
            "id": item.id,
            "envelope": {
                "version": item.envelope_version,
                "itemType": item.item_type,
                "ciphertext": item.ciphertext,
                "nonce": item.nonce,
                "encapsulatedKey": item.encapsulated_key,
                "metadata": item.metadata if isinstance(item.metadata, dict) else {},
                "signature": item.signature,
                "createdAt": item.created_at.isoformat() if item.created_at else "",
                "updatedAt": item.updated_at.isoformat() if item.updated_at else "",
                "authorDeviceId": item.author_device_id or "",
            },
            "deletedAt": item.deleted_at.isoformat() if item.deleted_at else None,
        })

    new_cursor = str(int(time.time()))
    return SyncPullResponse(items=items_list, cursor=new_cursor, hasMore=False)


# ─── Devices ──────────────────────────────────────────────────────────────────

@router.post("/devices", response_model=DeviceRegisterResponse)
async def register_device(payload: DeviceRegisterRequest, principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user = principal["user"]

    existing_devices = await DeviceRegistration.filter(user=user).count()
    role = "master" if existing_devices == 0 else "trusted"

    device_id = str(uuid.uuid4())
    await DeviceRegistration.create(
        id=device_id,
        user=user,
        device_name=payload.deviceName,
        device_class=payload.deviceClass,
        platform=payload.platform,
        device_role=role,
        pqc_public_key=payload.kemPublicKey,
        pqc_sig_public_key=payload.sigPublicKey,
        approval_state="approved" if role == "master" else "pending",
    )

    return DeviceRegisterResponse(
        deviceId=device_id,
        deviceRole=role,
        approvalState="approved" if role == "master" else "pending",
    )


@router.get("/devices", response_model=DeviceListResponse)
async def list_devices(principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user = principal["user"]

    devices = await DeviceRegistration.filter(user=user)
    return DeviceListResponse(devices=[
        {
            "id": d.id,
            "deviceName": d.device_name,
            "deviceClass": d.device_class,
            "platform": d.platform,
            "deviceRole": d.device_role,
            "approvalState": d.approval_state,
            "approvedBy": d.approved_by,
            "lastSeenAt": d.last_seen_at.isoformat() if d.last_seen_at else None,
            "createdAt": d.created_at.isoformat() if d.created_at else None,
        }
        for d in devices
    ])


@router.post("/devices/{device_id}/approve")
async def approve_device(device_id: str, payload: DeviceApproveRequest, principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user = principal["user"]

    master = await DeviceRegistration.get_or_none(user=user, device_role="master")
    if not master:
        raise HTTPException(status_code=403, detail="No master device found")

    target = await DeviceRegistration.get_or_none(id=device_id, user=user)
    if not target:
        raise HTTPException(status_code=404, detail="Device not found")

    target.approval_state = "approved"
    target.approved_by = master.id
    target.approval_sig = payload.approvalSignature
    await target.save()

    return {"status": "approved", "deviceId": device_id}


@router.delete("/devices/{device_id}")
async def revoke_device(device_id: str, principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user = principal["user"]

    device = await DeviceRegistration.get_or_none(id=device_id, user=user)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if device.device_role == "master":
        raise HTTPException(status_code=400, detail="Cannot revoke master device. Promote another device first.")

    device.approval_state = "revoked"
    await device.save()
    return {"status": "revoked"}


@router.post("/devices/{device_id}/promote")
async def promote_device(device_id: str, principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user = principal["user"]

    target = await DeviceRegistration.get_or_none(id=device_id, user=user)
    if not target:
        raise HTTPException(status_code=404, detail="Device not found")
    if target.approval_state != "approved":
        raise HTTPException(status_code=400, detail="Device must be approved first")

    old_masters = await DeviceRegistration.filter(user=user, device_role="master")
    for m in old_masters:
        m.device_role = "trusted"
        await m.save()

    target.device_role = "master"
    await target.save()
    return {"status": "promoted", "deviceId": device_id}
