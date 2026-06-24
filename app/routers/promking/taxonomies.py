"""Pornstars / studios / categories catalog operations."""
from __future__ import annotations

from dataclasses import dataclass
import re

from fastapi import APIRouter, HTTPException, Path, Query

from .db import get_pool
from ._models import (
    BatchTaxonomyDeleteRequest,
    BatchTaxonomyDeleteResponse,
    BatchTaxonomyGenderUpdateRequest,
    BatchTaxonomyGenderUpdateResponse,
    BatchTaxonomyMergeRequest,
    BatchTaxonomyMergeResponse,
    BatchTaxonomyRenameRequest,
    BatchTaxonomySlugUpdateRequest,
    BatchTaxonomyUpdateResponse,
    Site,
    TaxonomyConflict,
    TaxonomyKind,
    TermRef,
    WriteTaxonomyKind,
)

router = APIRouter(prefix="/taxonomies", tags=["promking:taxonomies"])


@dataclass(frozen=True)
class TaxonomyTableConfig:
    public_kind: str
    table: str
    join_table: str
    term_column: str
    has_gender: bool = False


_TABLES: dict[str, TaxonomyTableConfig] = {
    "pornstars": TaxonomyTableConfig("pornstars", "pornstars", "video_pornstars", "pornstar_id", True),
    "studios": TaxonomyTableConfig("studios", "studios", "video_studios", "studio_id"),
    "categories": TaxonomyTableConfig("categories", "categories", "video_categories", "category_id"),
}


def get_table_config(kind: TaxonomyKind | WriteTaxonomyKind) -> TaxonomyTableConfig:
    table_config = _TABLES.get(kind)
    if not table_config:
        raise HTTPException(status_code=404, detail="unknown taxonomy")
    return table_config


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "term"


@router.get("/{kind}", response_model=list[TermRef])
async def list_terms(
    kind: TaxonomyKind = Path(...),
    site: Site | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="Fuzzy name search (ILIKE)."),
    gender: str | None = Query(
        None,
        description=(
            "Filter pornstars by gender. Accepts a single value (e.g. 'female') "
            "or a comma-separated list (e.g. 'female,trans'). Special tokens: "
            "'null' (NULL only), 'has' (any non-null), 'all' (no filter, default)."
        ),
    ),
) -> list[TermRef]:
    table_config = get_table_config(kind)
    table, join_table, term_column = (
        table_config.table,
        table_config.join_table,
        table_config.term_column,
    )
    select_cols = f"{table}.id, {table}.name, {table}.slug"
    group_cols = f"{table}.id, {table}.name, {table}.slug"
    if table_config.has_gender:
        select_cols += f", {table}.gender"
        group_cols += f", {table}.gender"

    extra_where: list[str] = []
    extra_params: list = []

    def add_param(value) -> str:
        extra_params.append(value)
        # placeholders are filled later relative to the base param count
        return f"__p{len(extra_params)}__"

    if q:
        extra_where.append(f"{table}.name ILIKE {add_param(f'%{q}%')}")

    if gender and table_config.has_gender and gender.lower() != "all":
        token = gender.lower()
        if token == "null":
            extra_where.append(f"({table}.gender IS NULL OR {table}.gender::text = 'unknown')")
        elif token == "has":
            extra_where.append(f"({table}.gender IS NOT NULL AND {table}.gender::text <> 'unknown')")
        else:
            values = [v.strip() for v in token.split(",") if v.strip()]
            include_null = "null" in values
            concrete = [v for v in values if v != "null"]
            clauses: list[str] = []
            if concrete:
                clauses.append(f"{table}.gender::text = ANY({add_param(concrete)}::text[])")
            if include_null:
                clauses.append(f"({table}.gender IS NULL OR {table}.gender::text = 'unknown')")
            if clauses:
                extra_where.append("(" + " OR ".join(clauses) + ")")

    pool = await get_pool()
    async with pool.acquire() as conn:
        if site:
            sql = f"""
                SELECT {select_cols}
                FROM {table}
                JOIN {join_table} ON {join_table}.{term_column} = {table}.id
                JOIN videos ON videos.id = {join_table}.video_id
                WHERE videos.site = $1 AND {table}.deleted_at IS NULL
                {''.join(f' AND {clause}' for clause in extra_where)}
                GROUP BY {group_cols}
                ORDER BY COUNT(videos.id) DESC, {table}.name ASC
                LIMIT $2 OFFSET $3
            """
            base_params = [site, limit, offset]
        else:
            sql = f"""
                SELECT {select_cols}
                FROM {table}
                WHERE {table}.deleted_at IS NULL
                {''.join(f' AND {clause}' for clause in extra_where)}
                ORDER BY {table}.name ASC
                LIMIT $1 OFFSET $2
            """
            base_params = [limit, offset]

        # Renumber extra placeholders sequentially after the base ones.
        for index, _ in enumerate(extra_params, start=len(base_params) + 1):
            sql = sql.replace(f"__p{index - len(base_params)}__", f"${index}", 1)

        rows = await conn.fetch(sql, *base_params, *extra_params)
    return [TermRef(**dict(r)) for r in rows]


@router.get("/{kind}/count")
async def count_terms(
    kind: TaxonomyKind = Path(...),
    site: Site | None = Query(None),
    q: str | None = Query(None),
    gender: str | None = Query(None),
) -> dict:
    """Count rows matching the same filters as list_terms. Cheap path the
    admin uses to render proper pagination + a 'matching X of Y' counter."""
    table_config = get_table_config(kind)
    table, join_table, term_column = (
        table_config.table,
        table_config.join_table,
        table_config.term_column,
    )

    extra_where: list[str] = []
    extra_params: list = []

    def add_param(value) -> str:
        extra_params.append(value)
        return f"__p{len(extra_params)}__"

    if q:
        extra_where.append(f"{table}.name ILIKE {add_param(f'%{q}%')}")
    if gender and table_config.has_gender and gender.lower() != "all":
        token = gender.lower()
        if token == "null":
            extra_where.append(f"({table}.gender IS NULL OR {table}.gender::text = 'unknown')")
        elif token == "has":
            extra_where.append(f"({table}.gender IS NOT NULL AND {table}.gender::text <> 'unknown')")
        else:
            values = [v.strip() for v in token.split(",") if v.strip()]
            include_null = "null" in values
            concrete = [v for v in values if v != "null"]
            clauses: list[str] = []
            if concrete:
                clauses.append(f"{table}.gender::text = ANY({add_param(concrete)}::text[])")
            if include_null:
                clauses.append(f"({table}.gender IS NULL OR {table}.gender::text = 'unknown')")
            if clauses:
                extra_where.append("(" + " OR ".join(clauses) + ")")

    pool = await get_pool()
    async with pool.acquire() as conn:
        if site:
            sql = f"""
                SELECT COUNT(DISTINCT {table}.id) AS total
                FROM {table}
                JOIN {join_table} ON {join_table}.{term_column} = {table}.id
                JOIN videos ON videos.id = {join_table}.video_id
                WHERE videos.site = $1 AND {table}.deleted_at IS NULL
                {''.join(f' AND {clause}' for clause in extra_where)}
            """
            base_params = [site]
        else:
            sql = f"""
                SELECT COUNT(*) AS total
                FROM {table}
                WHERE {table}.deleted_at IS NULL
                {''.join(f' AND {clause}' for clause in extra_where)}
            """
            base_params = []
        for index, _ in enumerate(extra_params, start=len(base_params) + 1):
            sql = sql.replace(f"__p{index - len(base_params)}__", f"${index}", 1)
        total = await conn.fetchval(sql, *base_params, *extra_params)
    return {"total": int(total or 0)}


@router.post("/{kind}/batch/rename", response_model=BatchTaxonomyUpdateResponse)
async def batch_rename_terms(
    payload: BatchTaxonomyRenameRequest,
    kind: WriteTaxonomyKind = Path(...),
) -> BatchTaxonomyUpdateResponse:
    config = get_table_config(kind)
    count = 0
    conflicts: list[TaxonomyConflict] = []
    pool = await get_pool()
    async with pool.acquire() as conn:
        for item in payload.renames:
            next_slug = slugify(item.new_name)
            existing = await conn.fetchrow(
                f"SELECT id FROM {config.table} WHERE (lower(name) = lower($1) OR slug = $2) AND id <> $3 AND deleted_at IS NULL",
                item.new_name,
                next_slug,
                item.term_id,
            )
            if existing:
                conflicts.append(TaxonomyConflict(term_id=item.term_id, reason="name or slug already exists"))
                continue
            row = await conn.fetchrow(
                f"UPDATE {config.table} SET name = $1, slug = $2 WHERE id = $3 AND deleted_at IS NULL RETURNING id",
                item.new_name,
                next_slug,
                item.term_id,
            )
            if row:
                count += 1
            else:
                conflicts.append(TaxonomyConflict(term_id=item.term_id, reason="term not found"))
    return BatchTaxonomyUpdateResponse(count=count, conflicts=conflicts)


@router.post("/{kind}/batch/slug-update", response_model=BatchTaxonomyUpdateResponse)
async def batch_update_slugs(
    payload: BatchTaxonomySlugUpdateRequest,
    kind: WriteTaxonomyKind = Path(...),
) -> BatchTaxonomyUpdateResponse:
    config = get_table_config(kind)
    count = 0
    errors: list[TaxonomyConflict] = []
    pool = await get_pool()
    async with pool.acquire() as conn:
        for item in payload.updates:
            next_slug = slugify(item.new_slug)
            existing = await conn.fetchrow(
                f"SELECT id FROM {config.table} WHERE slug = $1 AND id <> $2 AND deleted_at IS NULL",
                next_slug,
                item.term_id,
            )
            if existing:
                errors.append(TaxonomyConflict(term_id=item.term_id, reason="slug already exists"))
                continue
            row = await conn.fetchrow(
                f"UPDATE {config.table} SET slug = $1 WHERE id = $2 AND deleted_at IS NULL RETURNING id",
                next_slug,
                item.term_id,
            )
            if row:
                count += 1
            else:
                errors.append(TaxonomyConflict(term_id=item.term_id, reason="term not found"))
    return BatchTaxonomyUpdateResponse(count=count, errors=errors)


@router.post("/{kind}/batch/merge", response_model=BatchTaxonomyMergeResponse)
async def batch_merge_terms(
    payload: BatchTaxonomyMergeRequest,
    kind: WriteTaxonomyKind = Path(...),
) -> BatchTaxonomyMergeResponse:
    config = get_table_config(kind)
    merge_from = [term_id for term_id in payload.merge_from if term_id != payload.primary_id]
    if not merge_from:
        return BatchTaxonomyMergeResponse(merged_count=0, video_recount=0)
    pool = await get_pool()
    async with pool.acquire() as conn:
        primary = await conn.fetchrow(
            f"SELECT id FROM {config.table} WHERE id = $1 AND deleted_at IS NULL",
            payload.primary_id,
        )
        if not primary:
            raise HTTPException(status_code=404, detail="primary term not found")
        video_recount = await conn.fetchval(
            f"SELECT COUNT(DISTINCT video_id) FROM {config.join_table} WHERE {config.term_column} = ANY($1::int[])",
            merge_from,
        )
        await conn.execute(
            f"""
            INSERT INTO {config.join_table} (video_id, {config.term_column})
            SELECT video_id, $1
            FROM {config.join_table}
            WHERE {config.term_column} = ANY($2::int[])
            ON CONFLICT DO NOTHING
            """,
            payload.primary_id,
            merge_from,
        )
        deleted_rows = await conn.fetch(
            f"UPDATE {config.table} SET deleted_at = now() WHERE id = ANY($1::int[]) AND deleted_at IS NULL RETURNING id",
            merge_from,
        )
    return BatchTaxonomyMergeResponse(
        merged_count=len(deleted_rows),
        video_recount=int(video_recount or 0),
    )


@router.post("/{kind}/batch/delete", response_model=BatchTaxonomyDeleteResponse)
async def batch_delete_terms(
    payload: BatchTaxonomyDeleteRequest,
    kind: WriteTaxonomyKind = Path(...),
) -> BatchTaxonomyDeleteResponse:
    config = get_table_config(kind)
    pool = await get_pool()
    async with pool.acquire() as conn:
        videos_orphaned = await conn.fetchval(
            f"SELECT COUNT(DISTINCT video_id) FROM {config.join_table} WHERE {config.term_column} = ANY($1::int[])",
            payload.term_ids,
        )
        rows = await conn.fetch(
            f"UPDATE {config.table} SET deleted_at = now() WHERE id = ANY($1::int[]) AND deleted_at IS NULL RETURNING id",
            payload.term_ids,
        )
    return BatchTaxonomyDeleteResponse(deleted_count=len(rows), videos_orphaned=int(videos_orphaned or 0))


@router.post("/pornstars/batch/gender-update", response_model=BatchTaxonomyGenderUpdateResponse)
async def batch_update_pornstar_gender(
    payload: BatchTaxonomyGenderUpdateRequest,
) -> BatchTaxonomyGenderUpdateResponse:
    config = get_table_config("pornstars")
    count = 0
    errors: list[TaxonomyConflict] = []
    pool = await get_pool()
    async with pool.acquire() as conn:
        for item in payload.updates:
            row = await conn.fetchrow(
                f"UPDATE {config.table} SET gender = $1 WHERE id = $2 AND deleted_at IS NULL RETURNING id",
                item.gender,
                item.pornstar_id,
            )
            if row:
                count += 1
            else:
                errors.append(TaxonomyConflict(term_id=item.pornstar_id, reason="pornstar not found"))
    return BatchTaxonomyGenderUpdateResponse(count=count, errors=errors)
