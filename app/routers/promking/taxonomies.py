"""Actors / studios / categories CRUD (read-only stubs for v0.1)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path

from .db import get_pool
from ._models import TaxonomyKind, TermRef

router = APIRouter(prefix="/taxonomies", tags=["promking:taxonomies"])

_TABLES: dict[str, str] = {
    "actors": "actors",
    "studios": "studios",
    "categories": "categories",
}


@router.get("/{kind}", response_model=list[TermRef])
async def list_terms(kind: TaxonomyKind = Path(...)) -> list[TermRef]:
    table = _TABLES.get(kind)
    if not table:
        raise HTTPException(status_code=404, detail="unknown taxonomy")
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT id, name, slug FROM {table} ORDER BY name ASC"
        )
    return [TermRef(**dict(r)) for r in rows]


# TODO: POST/PATCH/DELETE + bulk-move endpoints land with the admin panels (ADR §10).
