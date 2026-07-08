from __future__ import annotations
import re
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from jose import jwt, JWTError

from api.auth import pwd_context, _create_access_token
from api.config import JWT_SECRET, JWT_AUDIENCE, JWT_ISSUER
from .db import get_pool

router = APIRouter(prefix="/auth", tags=["promking:auth"])

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$")
MIN_PASSWORD_LENGTH = 8

class PromKingLoginRequest(BaseModel):
    email: str
    password: str

class PromKingLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600

class PromKingRegisterRequest(BaseModel):
    email: str
    password: str

class PromKingRegisterResponse(BaseModel):
    email: str
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600

class PromKingMeResponse(BaseModel):
    id: int
    email: str
    role: str

class PromKingFavoriteRequest(BaseModel):
    wallpaper_id: str

class PromKingFavoritesResponse(BaseModel):
    favorites: List[str]

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
bearer_scheme = HTTPBearer(auto_error=False)

async def get_current_promking_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    user_id = payload.get("uid")
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, email, role FROM users WHERE id = $1", user_id)
    if not row:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return dict(row)

@router.post("/register", response_model=PromKingRegisterResponse)
async def register(payload: PromKingRegisterRequest):
    email = payload.email.strip().lower()
    password = payload.password
    
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email format")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
        
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM users WHERE email = $1", email)
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")
            
        hashed = pwd_context.hash(password)
        user_id = await conn.fetchval(
            "INSERT INTO users (email, password_hash, role) VALUES ($1, $2, 'viewer') RETURNING id",
            email, hashed
        )
        
    # Standard vaultwares JWT creation
    token = _create_access_token(user_id, email, False, ttl_override=3600)
    return PromKingRegisterResponse(email=email, access_token=token)

@router.post("/login", response_model=PromKingLoginResponse)
async def login(payload: PromKingLoginRequest):
    email = payload.email.strip().lower()
    password = payload.password
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id, email, password_hash, role FROM users WHERE email = $1", email)
        if not user:
            pwd_context.dummy_verify()
            raise HTTPException(status_code=401, detail="Invalid email or password")
            
        if not pwd_context.verify(password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
            
    is_admin = user["role"] == "admin"
    token = _create_access_token(user["id"], user["email"], is_admin, ttl_override=3600)
    return PromKingLoginResponse(access_token=token)

@router.get("/me", response_model=PromKingMeResponse)
async def me(current_user: dict = Depends(get_current_promking_user)):
    return PromKingMeResponse(
        id=current_user["id"],
        email=current_user["email"],
        role=current_user["role"]
    )

@router.get("/favorites", response_model=PromKingFavoritesResponse)
async def list_favorites(current_user: dict = Depends(get_current_promking_user)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT wallpaper_id FROM wallpaper_favorites WHERE user_id = $1",
            current_user["id"]
        )
    return PromKingFavoritesResponse(favorites=[r["wallpaper_id"] for r in rows])

@router.post("/favorites", response_model=PromKingFavoritesResponse)
async def toggle_favorite(
    payload: PromKingFavoriteRequest,
    current_user: dict = Depends(get_current_promking_user)
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM wallpaper_favorites WHERE user_id = $1 AND wallpaper_id = $2",
            current_user["id"], payload.wallpaper_id
        )
        if existing:
            await conn.execute(
                "DELETE FROM wallpaper_favorites WHERE user_id = $1 AND wallpaper_id = $2",
                current_user["id"], payload.wallpaper_id
            )
        else:
            await conn.execute(
                "INSERT INTO wallpaper_favorites (user_id, wallpaper_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                current_user["id"], payload.wallpaper_id
            )
            
        # Return updated list of favorites
        rows = await conn.fetch(
            "SELECT wallpaper_id FROM wallpaper_favorites WHERE user_id = $1",
            current_user["id"]
        )
    return PromKingFavoritesResponse(favorites=[r["wallpaper_id"] for r in rows])
