import time
import os
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers import bytes_to_base64url, base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
    PublicKeyCredentialDescriptor,
    AttestationConveyancePreference,
)
from db import UserAccount, WebAuthnCredential
from api.auth import require_auth, _create_access_token
from api.config import JWT_TTL_SECONDS

router = APIRouter()
WEBAUTHN_CHALLENGES = {}

def _cleanup_webauthn_challenges():
    now = time.time()
    stale = [k for k, v in WEBAUTHN_CHALLENGES.items() if now - v["timestamp"] > 300]
    for k in stale:
        WEBAUTHN_CHALLENGES.pop(k, None)

def _get_rp_id(request: Request) -> str:
    host = request.headers.get("x-forwarded-host")
    if not host:
        host = request.headers.get("host")
    if not host:
        host = request.url.hostname
    if host and ":" in host:
        host = host.split(":")[0]
    return host or os.environ.get("WEBAUTHN_RP_ID", "prom-king.xyz")

@router.post("/auth/passkey/register")
@router.post("/auth/register/options")
async def webauthn_register_options(request: Request, principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user = principal["user"]
    _cleanup_webauthn_challenges()

    rp_id = _get_rp_id(request)
    rp_name = "FullXXX" if "fullxxx" in rp_id.lower() else "Prom-King"
    user_id_bytes = str(user.id).encode("utf-8")
    
    user_credentials = await WebAuthnCredential.filter(user=user)
    exclude_credentials = []
    for cred in user_credentials:
        try:
            exclude_credentials.append(PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(cred.credential_id)
            ))
        except Exception:
            pass

    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=rp_name,
        user_id=user_id_bytes,
        user_name=user.username,
        user_display_name=user.username,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=None,
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=exclude_credentials,
    )

    challenge_str = bytes_to_base64url(options.challenge)
    WEBAUTHN_CHALLENGES[challenge_str] = {
        "challenge": options.challenge,
        "username": user.username,
        "timestamp": time.time(),
    }
    return Response(content=options_to_json(options), media_type="application/json")

@router.post("/auth/passkey/register/verify")
@router.post("/auth/register/verify")
async def webauthn_register_verify(request: Request, payload: dict, principal=Depends(require_auth)):
    if principal.get("kind") != "user":
        raise HTTPException(status_code=401, detail="User token required")
    user = principal["user"]
    _cleanup_webauthn_challenges()

    credential_payload = payload.get("credential")
    if credential_payload is None:
        credential_payload = payload

    challenge_str = payload.get("challenge")
    if not challenge_str:
        try:
            client_data_b64 = credential_payload.get("response", {}).get("clientDataJSON", "")
            if client_data_b64:
                pad = len(client_data_b64) % 4
                if pad:
                    client_data_b64 += "=" * (4 - pad)
                import base64
                client_data_decoded = base64.urlsafe_b64decode(client_data_b64.encode("utf-8")).decode("utf-8")
                import json
                client_data = json.loads(client_data_decoded)
                challenge_str = client_data.get("challenge")
        except Exception:
            pass

    if not challenge_str or challenge_str not in WEBAUTHN_CHALLENGES:
        raise HTTPException(status_code=400, detail="Challenge missing or expired")

    challenge_info = WEBAUTHN_CHALLENGES.pop(challenge_str)
    if challenge_info["username"] != user.username:
        raise HTTPException(status_code=403, detail="Challenge owner mismatch")

    rp_id = _get_rp_id(request)
    expected_origin = payload.get("origin") or f"https://{rp_id}"

    try:
        verification = verify_registration_response(
            credential=credential_payload,
            expected_challenge=challenge_info["challenge"],
            expected_origin=expected_origin,
            expected_rp_id=rp_id,
            require_user_verification=False,
        )
    except Exception as e:
        try:
            verification = verify_registration_response(
                credential=credential_payload,
                expected_challenge=challenge_info["challenge"],
                expected_origin="http://localhost:4321",
                expected_rp_id="localhost",
                require_user_verification=False,
            )
        except Exception as e2:
            raise HTTPException(status_code=400, detail=f"WebAuthn verification failed: {e2}")

    credential_id_str = bytes_to_base64url(verification.credential_id)
    public_key_str = bytes_to_base64url(verification.credential_public_key)

    existing = await WebAuthnCredential.get_or_none(credential_id=credential_id_str)
    if existing:
        raise HTTPException(status_code=409, detail="Credential already registered")

    await WebAuthnCredential.create(
        user=user,
        credential_id=credential_id_str,
        public_key=public_key_str,
        sign_count=verification.sign_count,
    )
    return {"ok": True}

@router.post("/auth/passkey/login")
@router.post("/auth/login/options")
async def webauthn_login_options(request: Request):
    _cleanup_webauthn_challenges()
    rp_id = _get_rp_id(request)
    options = generate_authentication_options(
        rp_id=rp_id,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    challenge_str = bytes_to_base64url(options.challenge)
    WEBAUTHN_CHALLENGES[challenge_str] = {
        "challenge": options.challenge,
        "timestamp": time.time(),
    }
    return Response(content=options_to_json(options), media_type="application/json")

@router.post("/auth/passkey/login/verify")
@router.post("/auth/login/verify")
async def webauthn_login_verify(request: Request, payload: dict):
    _cleanup_webauthn_challenges()

    credential_payload = payload.get("credential")
    if credential_payload is None:
        credential_payload = payload

    challenge_str = payload.get("challenge")
    if not challenge_str:
        try:
            client_data_b64 = credential_payload.get("response", {}).get("clientDataJSON", "")
            if client_data_b64:
                pad = len(client_data_b64) % 4
                if pad:
                    client_data_b64 += "=" * (4 - pad)
                import base64
                client_data_decoded = base64.urlsafe_b64decode(client_data_b64.encode("utf-8")).decode("utf-8")
                import json
                client_data = json.loads(client_data_decoded)
                challenge_str = client_data.get("challenge")
        except Exception:
            pass

    if not challenge_str or challenge_str not in WEBAUTHN_CHALLENGES:
        raise HTTPException(status_code=400, detail="Challenge missing or expired")

    challenge_info = WEBAUTHN_CHALLENGES.pop(challenge_str)
    raw_id = credential_payload.get("rawId") or credential_payload.get("id")
    credential_id_str = bytes_to_base64url(base64url_to_bytes(raw_id))

    db_cred = await WebAuthnCredential.get_or_none(credential_id=credential_id_str).prefetch_related("user")
    if not db_cred or db_cred.user.is_disabled:
        raise HTTPException(status_code=401, detail="Invalid credential")

    rp_id = _get_rp_id(request)
    expected_origin = payload.get("origin") or f"https://{rp_id}"

    try:
        verification = verify_authentication_response(
            credential=credential_payload,
            expected_challenge=challenge_info["challenge"],
            expected_origin=expected_origin,
            expected_rp_id=rp_id,
            credential_public_key=base64url_to_bytes(db_cred.public_key),
            credential_current_sign_count=db_cred.sign_count,
            require_user_verification=False,
        )
    except Exception as e:
        try:
            verification = verify_authentication_response(
                credential=credential_payload,
                expected_challenge=challenge_info["challenge"],
                expected_origin="http://localhost:4321",
                expected_rp_id="localhost",
                credential_public_key=base64url_to_bytes(db_cred.public_key),
                credential_current_sign_count=db_cred.sign_count,
                require_user_verification=False,
            )
        except Exception as e2:
            raise HTTPException(status_code=401, detail=f"WebAuthn verification failed: {e2}")

    db_cred.sign_count = verification.new_sign_count
    await db_cred.save()

    token = _create_access_token(db_cred.user.id, db_cred.user.username, bool(db_cred.user.is_admin))
    return {"access_token": token, "token_type": "bearer", "expires_in": max(60, JWT_TTL_SECONDS)}
