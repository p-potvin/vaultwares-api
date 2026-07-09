"""Pornstars / studios / categories catalog operations."""
from __future__ import annotations

from dataclasses import dataclass
import re
import time

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

# --- "Hot" ranking tunables -------------------------------------------------
# sort=hot (alias: trending) ranks terms by the recency-weighted popularity of
# their videos, then applies a deterministic per-(term, time-bucket) jitter so a
# low-traffic, mostly-static catalog still rotates instead of parking the same
# handful of terms in the sidebar forever. It is intentionally NOT the default
# sort — admin lists and A→Z directories still want name ASC.
HOT_DECAY_SECONDS = 21 * 86400   # a video's weight decays ~1/e once it is 21 days old
HOT_ROTATE_SECONDS = 6 * 3600    # the jitter reshuffles membership every 6 hours
HOT_JITTER = 0.5                 # ±25% multiplicative wobble (0.75‥1.25) on the score


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
    site: Site | None = Query(None, description="Deprecated, ignored. Taxonomies are global."),
    limit: int = Query(100, ge=1, le=100000),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="Fuzzy name search (ILIKE)."),
    gender: str | None = Query(
        "female",
        description=(
            "Filter pornstars by gender. Accepts a single value (e.g. 'female') "
            "or a comma-separated list (e.g. 'female,male'). Special tokens: "
            "'null' (NULL only), 'has' (any non-null), 'all' (no filter, default)."
        ),
    ),
    sort: str = Query("default", description="Sort order: 'default', 'name_asc', 'name_desc', 'videos_asc', 'videos_desc', 'id_asc', 'id_desc', 'hot' (alias 'trending')"),
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
    pool = await get_pool()
    # Determine sorting order
    if sort == "default":
        sort_order = f"{table}.name ASC"
    elif sort == "name_asc":
        sort_order = f"{table}.name ASC"
    elif sort == "name_desc":
        sort_order = f"{table}.name DESC"
    elif sort == "videos_desc":
        sort_order = f"COUNT({join_table}.video_id) DESC, {table}.name ASC"
    elif sort == "videos_asc":
        sort_order = f"COUNT({join_table}.video_id) ASC, {table}.name ASC"
    elif sort == "id_asc":
        sort_order = f"{table}.id ASC"
    elif sort == "id_desc":
        sort_order = f"{table}.id DESC"
    elif sort in ("hot", "trending"):
        # Recency-weighted popularity: SUM over the term's live videos of
        # (views+1) * exp(-age / decay). Multiplied by a stable per-(term, bucket)
        # jitter so near-tied terms rotate every HOT_ROTATE_SECONDS instead of
        # freezing. The md5→bit(32)→bigint idiom yields a deterministic
        # 0‥4294967295 hash we normalise to [0,1].
        bucket = int(time.time() // HOT_ROTATE_SECONDS)
        # Bind as str: the seed is used as `$N::text` inside md5(), so Postgres
        # infers the param type as text and asyncpg rejects a bare int (500).
        bucket_ph = add_param(str(bucket))
        jitter_lo = 1.0 - HOT_JITTER / 2.0
        sort_order = (
            "COALESCE(SUM("
            "(videos.views + 1) * exp("
            f"-GREATEST(EXTRACT(EPOCH FROM (now() - videos.created_at)), 0) / {HOT_DECAY_SECONDS}.0"
            ")), 0) * ("
            f"{jitter_lo} + {HOT_JITTER} * ("
            f"('x' || substr(md5({table}.id::text || '-' || {bucket_ph}::text), 1, 8))::bit(32)::bigint::double precision"
            " / 4294967295.0)"
            f") DESC, {table}.name ASC"
        )
    else:
        sort_order = f"{table}.name ASC"

    pool = await get_pool()
    async with pool.acquire() as conn:
        if sort in ("hot", "trending"):
            # Join through to the videos so the score can read views + created_at.
            # disabled videos are dropped in the JOIN so they don't inflate a term.
            sql = f"""
                SELECT {select_cols}
                FROM {table}
                LEFT JOIN {join_table} ON {join_table}.{term_column} = {table}.id
                LEFT JOIN videos ON videos.id = {join_table}.video_id AND videos.disabled_at IS NULL
                WHERE {table}.deleted_at IS NULL
                {''.join(f' AND {clause}' for clause in extra_where)}
                GROUP BY {group_cols}
                ORDER BY {sort_order}
                LIMIT $1 OFFSET $2
            """
        elif sort in ("videos_desc", "videos_asc"):
            sql = f"""
                SELECT {select_cols}
                FROM {table}
                LEFT JOIN {join_table} ON {join_table}.{term_column} = {table}.id
                WHERE {table}.deleted_at IS NULL
                {''.join(f' AND {clause}' for clause in extra_where)}
                GROUP BY {group_cols}
                ORDER BY {sort_order}
                LIMIT $1 OFFSET $2
            """
        else:
            sql = f"""
                SELECT {select_cols}
                FROM {table}
                WHERE {table}.deleted_at IS NULL
                {''.join(f' AND {clause}' for clause in extra_where)}
                ORDER BY {sort_order}
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
                JOIN video_sites ON video_sites.video_id = {join_table}.video_id
                WHERE video_sites.site = $1 AND {table}.deleted_at IS NULL
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


@router.post("/{kind}", response_model=TermRef, status_code=201)
async def create_term(
    kind: WriteTaxonomyKind = Path(...),
    payload: dict = None,  # noqa: RUF013 — dict allows the tiny shape below without a new pydantic model
) -> TermRef:
    """
    Create-or-return a single term. Idempotent on (kind, slug) — repeated
    calls with the same name yield the existing row. Powers the "create on
    demand" affordance in the admin video-detail overlay: when the operator
    types a pornstar name that isn't in the DB yet, the panel offers to
    create it and attach in one shot instead of bouncing them to the batch
    UI.

    Payload shape: `{"name": "Juniper Ren", "gender": "female"?}` (gender
    only respected on pornstars). Fields beyond name/gender are ignored.
    """
    config = get_table_config(kind)
    payload = payload or {}
    name = str(payload.get("name") or "").strip()
    if not name or len(name) > 200:
        raise HTTPException(status_code=422, detail="name is required (≤200 chars)")
    slug = slugify(name)
    gender_col = ""
    gender_val = None
    if config.has_gender:
        raw = payload.get("gender")
        if raw in ("female", "male", "unknown", None):
            gender_val = raw
            gender_col = ", gender"

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Idempotent upsert on slug. If someone typed a slightly different
        # capitalisation of an existing term, return the existing row rather
        # than duplicating.
        existing = await conn.fetchrow(
            f"SELECT id, name, slug{', gender' if config.has_gender else ''} "
            f"FROM {config.table} WHERE slug = $1 AND deleted_at IS NULL",
            slug,
        )
        if existing:
            return TermRef(
                id=existing["id"],
                name=existing["name"],
                slug=existing["slug"],
                gender=existing["gender"] if config.has_gender else None,
            )
        if config.has_gender:
            row = await conn.fetchrow(
                f"INSERT INTO {config.table} (name, slug{gender_col}) "
                f"VALUES ($1, $2, $3) RETURNING id, name, slug, gender",
                name, slug, gender_val,
            )
        else:
            row = await conn.fetchrow(
                f"INSERT INTO {config.table} (name, slug) VALUES ($1, $2) RETURNING id, name, slug",
                name, slug,
            )
    return TermRef(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        gender=row["gender"] if config.has_gender else None,
    )


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
