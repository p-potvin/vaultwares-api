"""
Viewer (public tube-site user) endpoints — scaffold.

Registration + login already live in `auth.py` (`/auth/register`, `/auth/login`,
`/auth/me`). This module adds the tube-site-specific pieces that were missing:

  - Video favourites (bound to `favourites` table, not the wallpaper-only
    `wallpaper_favorites` already served by /auth/favorites).
  - Admin-side user management (list, disable, enable). Requires an admin
    role; viewer role gets 403.

Kept intentionally thin — schema, endpoints, one auth helper. UIs on top of
this are in shared-tube (admin Users tab + per-app /account page).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel

from .auth import get_current_promking_user
from .db import get_pool
from ._models import Site

router = APIRouter(prefix="/viewers", tags=["promking:viewers"])


# ── shapes ─────────────────────────────────────────────────────────────────

class FavouriteVideo(BaseModel):
    id: int
    site: Site
    slug: str
    title: str
    thumbnail_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    added_at: datetime


class FavouriteListResponse(BaseModel):
    videos: list[FavouriteVideo]
    total: int


class ToggleFavouriteResponse(BaseModel):
    favourited: bool
    count: int


class UserRow(BaseModel):
    id: int
    email: str
    role: str
    created_at: datetime
    disabled_at: Optional[datetime] = None
    favourite_count: int = 0


class UserListResponse(BaseModel):
    users: list[UserRow]
    total: int


# ── auth helpers ──────────────────────────────────────────────────────────

async def require_admin(user: dict = Depends(get_current_promking_user)) -> dict:
    if str(user.get("role")) != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


# ── viewer-facing endpoints ────────────────────────────────────────────────

@router.get("/me/favourites", response_model=FavouriteListResponse)
async def list_my_favourites(
    site: Site = Query(...),
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_promking_user),
) -> FavouriteListResponse:
    """Video favourites for the current viewer, newest-first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT v.id, v.site::text AS site, v.slug, v.title, v.thumbnail_url,
                   v.duration_seconds, f.created_at AS added_at
              FROM favourites f
              JOIN videos v ON v.id = f.video_id
             WHERE f.user_id = $1 AND v.site = $2 AND v.disabled_at IS NULL
             ORDER BY f.created_at DESC
             LIMIT $3 OFFSET $4
            """,
            user["id"],
            site,
            limit,
            offset,
        )
        total = await conn.fetchval(
            """
            SELECT COUNT(*)::bigint
              FROM favourites f JOIN videos v ON v.id = f.video_id
             WHERE f.user_id = $1 AND v.site = $2 AND v.disabled_at IS NULL
            """,
            user["id"],
            site,
        )
    return FavouriteListResponse(videos=[FavouriteVideo(**dict(r)) for r in rows], total=int(total or 0))


@router.post("/videos/{slug}/favourite", response_model=ToggleFavouriteResponse)
async def toggle_video_favourite(
    slug: str = Path(...),
    site: Site = Query(...),
    user: dict = Depends(get_current_promking_user),
) -> ToggleFavouriteResponse:
    """
    Toggle a favourite for the current viewer. Returns whether the video is
    now favourited, plus the total favourites for the video (useful for a
    heart-count in the UI).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        video = await conn.fetchrow(
            "SELECT id FROM videos WHERE site = $1 AND slug = $2 AND disabled_at IS NULL",
            site,
            slug,
        )
        if not video:
            raise HTTPException(status_code=404, detail="video not found")
        existing = await conn.fetchrow(
            "SELECT id FROM favourites WHERE user_id = $1 AND video_id = $2",
            user["id"],
            video["id"],
        )
        if existing:
            await conn.execute("DELETE FROM favourites WHERE id = $1", existing["id"])
            favourited = False
        else:
            await conn.execute(
                "INSERT INTO favourites (user_id, video_id) VALUES ($1, $2)",
                user["id"],
                video["id"],
            )
            favourited = True
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM favourites WHERE video_id = $1",
            video["id"],
        )
    return ToggleFavouriteResponse(favourited=favourited, count=int(total or 0))


# ── admin-facing endpoints ─────────────────────────────────────────────────

@router.get("/admin/users", response_model=UserListResponse)
async def admin_list_users(
    q: Optional[str] = Query(None, description="email ILIKE match"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_disabled: bool = Query(True),
    _admin: dict = Depends(require_admin),
) -> UserListResponse:
    """Paginated list of every viewer account, with a per-user favourite count."""
    pool = await get_pool()
    params: list = []
    where: list[str] = ["1=1"]
    if q:
        params.append(f"%{q}%")
        where.append(f"email ILIKE ${len(params)}")
    if not include_disabled:
        where.append("disabled_at IS NULL")
    where_sql = " AND ".join(where)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT u.id, u.email, u.role::text AS role, u.created_at, u.disabled_at,
                   (SELECT COUNT(*) FROM favourites f WHERE f.user_id = u.id) AS favourite_count
              FROM users u
             WHERE {where_sql}
             ORDER BY u.created_at DESC
             LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """,
            *params, limit, offset,
        )
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM users WHERE {where_sql}",
            *params,
        )
    return UserListResponse(users=[UserRow(**dict(r)) for r in rows], total=int(total or 0))


@router.post("/admin/users/{user_id}/disable", response_model=UserRow)
async def admin_disable_user(user_id: int = Path(..., ge=1), _admin: dict = Depends(require_admin)) -> UserRow:
    return await _set_user_disabled(user_id, disable=True)


@router.post("/admin/users/{user_id}/enable", response_model=UserRow)
async def admin_enable_user(user_id: int = Path(..., ge=1), _admin: dict = Depends(require_admin)) -> UserRow:
    return await _set_user_disabled(user_id, disable=False)


async def _set_user_disabled(user_id: int, *, disable: bool) -> UserRow:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE users
               SET disabled_at = CASE WHEN $2 THEN NOW() ELSE NULL END
             WHERE id = $1
             RETURNING id, email, role::text AS role, created_at, disabled_at,
                       (SELECT COUNT(*) FROM favourites f WHERE f.user_id = users.id) AS favourite_count
            """,
            user_id,
            disable,
        )
    if not row:
        raise HTTPException(status_code=404, detail="user not found")
    return UserRow(**dict(row))
