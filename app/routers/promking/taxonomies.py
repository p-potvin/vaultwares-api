"""Actors / studios / categories CRUD (read-only stubs for v0.1)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query

from .db import get_pool
from ._models import Site, TaxonomyKind, TermRef

router = APIRouter(prefix="/taxonomies", tags=["promking:taxonomies"])

_TABLES: dict[str, tuple[str, str, str]] = {
    "actors": ("actors", "video_actors", "actor_id"),
    "studios": ("studios", "video_studios", "studio_id"),
    "categories": ("categories", "video_categories", "category_id"),
}


@router.get("/{kind}", response_model=list[TermRef])
async def list_terms(
    kind: TaxonomyKind = Path(...),
    site: Site | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> list[TermRef]:
    table_config = _TABLES.get(kind)
    if not table_config:
        raise HTTPException(status_code=404, detail="unknown taxonomy")
    table, join_table, term_column = table_config
    pool = await get_pool()
    async with pool.acquire() as conn:
        if site:
            rows = await conn.fetch(
                f"""
                SELECT {table}.id, {table}.name, {table}.slug
                FROM {table}
                JOIN {join_table} ON {join_table}.{term_column} = {table}.id
                JOIN videos ON videos.id = {join_table}.video_id
                WHERE videos.site = $1
                GROUP BY {table}.id, {table}.name, {table}.slug
                ORDER BY COUNT(videos.id) DESC, {table}.name ASC
                LIMIT $2
                """,
                site,
                limit,
            )
        else:
            rows = await conn.fetch(
                f"SELECT id, name, slug FROM {table} ORDER BY name ASC LIMIT $1",
                limit,
            )
    return [TermRef(**dict(r)) for r in rows]


# TODO: POST/PATCH/DELETE + bulk-move endpoints land with the admin panels (ADR §10).
