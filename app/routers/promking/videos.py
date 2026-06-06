"""GET/PATCH/DELETE videos. Insertion happens via the fetcher persistence path."""
from __future__ import annotations

from fastapi import APIRouter, Query

from .db import get_pool
from ._models import Site, VideoListItem

router = APIRouter(prefix="/videos", tags=["promking:videos"])


@router.get("", response_model=list[VideoListItem])
async def list_videos(
    site: Site = Query(..., description="fxv or pkt — required."),
    limit: int = Query(24, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="Postgres FTS query over title."),
) -> list[VideoListItem]:
    pool = await get_pool()
    sql_base = """
        SELECT id, site, title, slug, thumbnail_url, preview_url,
               duration_seconds, views, created_at
        FROM videos
        WHERE site = $1
    """
    params: list = [site]
    if q:
        sql_base += " AND to_tsvector('english', title) @@ plainto_tsquery('english', $2)"
        params.append(q)
        sql_base += " ORDER BY created_at DESC LIMIT $3 OFFSET $4"
        params.extend([limit, offset])
    else:
        sql_base += " ORDER BY created_at DESC LIMIT $2 OFFSET $3"
        params.extend([limit, offset])
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql_base, *params)
    return [VideoListItem(**dict(r)) for r in rows]


@router.get("/{slug}")
async def get_video(slug: str, site: Site = Query(...)) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, site, title, slug, thumbnail_url, preview_url,
                   duration_seconds, views, created_at, updated_at,
                   source, source_url, embed_url, embed_type
            FROM videos
            WHERE site = $1 AND slug = $2
            """,
            site,
            slug,
        )
    if row is None:
        return None
    # TODO: join taxonomy terms (actors/studios/categories) via the join tables.
    return dict(row)
