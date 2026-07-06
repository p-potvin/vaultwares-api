"""GET/PATCH/DELETE videos. Insertion happens via the fetcher persistence path."""
from __future__ import annotations

from fastapi import APIRouter, Query

import json
from .db import get_pool
from ._models import (
    BatchAddTaxonomyRequest,
    BatchChangeSourceRequest,
    BatchCountResponse,
    BatchError,
    BatchMetadataResponse,
    BatchMetadataUpdateRequest,
    BatchVideoIdsRequest,
    Site,
    TermRef,
    VideoDetail,
    VideoListItem,
)
from .taxonomies import get_table_config

router = APIRouter(prefix="/videos", tags=["promking:videos"])

_METADATA_COLUMNS = {
    "title": "title",
    "source_url": "source_url",
    "embed_url": "embed_url",
    "embed_type": "embed_type",
    "thumbnail_url": "thumbnail_url",
    "preview_url": "preview_url",
    "duration_seconds": "duration_seconds",
    "views": "views",
    "qualities": "qualities",
}


def build_metadata_update_clause(updates: dict[str, object], first_param: int) -> tuple[str, list[object]]:
    assignments: list[str] = []
    values: list[object] = []
    for key, value in updates.items():
        column = _METADATA_COLUMNS.get(key)
        if not column:
            raise ValueError(f"Unsupported metadata field: {key}")
        values.append(value)
        assignments.append(f"{column} = ${first_param + len(values) - 1}")
    if not assignments:
        raise ValueError("No metadata updates supplied")
    assignments.append("updated_at = now()")
    return ", ".join(assignments), values


def build_gender_clause(
    gender: str | None,
    column: str,
    next_param_index: int,
) -> tuple[str, list[list[str]]]:
    """Build a WHERE-fragment for filtering a `gender` enum column.

    Returns (sql_fragment, extra_params). `sql_fragment` is empty when no
    filter applies; otherwise it's a balanced expression you can join with
    `AND`. The column is cast to text before comparing against the array so
    Postgres can match the enum against `text[]` without a `DataError`.
    """
    if not gender or gender.lower() == "all":
        return "", []
    token = gender.lower()
    if token == "null":
        return f"({column} IS NULL OR {column}::text = 'unknown')", []
    if token == "has":
        return f"({column} IS NOT NULL AND {column}::text <> 'unknown')", []
    values = [v.strip() for v in token.split(",") if v.strip()]
    include_null = "null" in values
    concrete = [v for v in values if v != "null"]
    clauses: list[str] = []
    extra_params: list[list[str]] = []
    if concrete:
        extra_params.append(concrete)
        clauses.append(f"{column}::text = ANY(${next_param_index}::text[])")
    if include_null:
        clauses.append(f"({column} IS NULL OR {column}::text = 'unknown')")
    if not clauses:
        return "", []
    return "(" + " OR ".join(clauses) + ")", extra_params


def build_video_filters(
    *,
    site: Site | None = None,
    q: str | None = None,
    actor: str | None = None,
    studio: str | None = None,
    category: str | None = None,
    related_to: str | None = None,
    exclude_slug: str | None = None,
    disabled: bool | None = None,
    source: str | None = None,
) -> tuple[str, str, list]:
    """Build taxonomy/related filters for list_videos.

    The helper is intentionally pure so frontend-facing filter contracts can be
    unit-tested without requiring Postgres.
    """
    joins: list[str] = []
    where = ["1=1"]
    params: list = []

    def add_param(value: str) -> str:
        params.append(value)
        return f"${len(params)}"

    if q:
        where.append(
            "to_tsvector('english', videos.title) @@ plainto_tsquery('english', "
            f"{add_param(q)})"
        )
    if actor:
        joins.extend(
            [
                "JOIN video_pornstars actor_filter ON actor_filter.video_id = videos.id",
                "JOIN pornstars actor_terms ON actor_terms.id = actor_filter.pornstar_id",
            ]
        )
        where.append(f"actor_terms.slug = {add_param(actor)}")
    if studio:
        joins.extend(
            [
                "JOIN video_studios studio_filter ON studio_filter.video_id = videos.id",
                "JOIN studios studio_terms ON studio_terms.id = studio_filter.studio_id",
            ]
        )
        where.append(f"studio_terms.slug = {add_param(studio)}")
    if category:
        joins.extend(
            [
                "JOIN video_categories category_filter ON category_filter.video_id = videos.id",
                "JOIN categories category_terms ON category_terms.id = category_filter.category_id",
            ]
        )
        where.append(f"category_terms.slug = {add_param(category)}")
    if related_to:
        joins.extend(
            [
                "JOIN videos related_video ON 1=1",
                "LEFT JOIN video_pornstars related_actors ON related_actors.video_id = related_video.id",
                "LEFT JOIN video_pornstars current_actors ON current_actors.video_id = videos.id AND current_actors.pornstar_id = related_actors.pornstar_id",
                "LEFT JOIN video_studios related_studios ON related_studios.video_id = related_video.id",
                "LEFT JOIN video_studios current_studios ON current_studios.video_id = videos.id AND current_studios.studio_id = related_studios.studio_id",
                "LEFT JOIN video_categories related_categories ON related_categories.video_id = related_video.id",
                "LEFT JOIN video_categories current_categories ON current_categories.video_id = videos.id AND current_categories.category_id = related_categories.category_id",
            ]
        )
        where.append(f"related_video.slug = {add_param(related_to)}")
        where.append("videos.id <> related_video.id")
        where.append(
            "("
            "current_actors.pornstar_id IS NOT NULL OR "
            "current_studios.studio_id IS NOT NULL OR "
            "current_categories.category_id IS NOT NULL"
            ")"
        )
    if exclude_slug:
        where.append(f"videos.slug <> {add_param(exclude_slug)}")
    if disabled is not None:
        if disabled:
            where.append("videos.disabled_at IS NOT NULL")
        else:
            where.append("videos.disabled_at IS NULL")
    if source:
        where.append(f"videos.source = {add_param(source)}")

    return " AND ".join(where), "\n        ".join(joins), params


@router.post("/batch/disable", response_model=BatchCountResponse)
async def batch_disable_videos(payload: BatchVideoIdsRequest) -> BatchCountResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            UPDATE videos
            SET disabled_at = now(), updated_at = now()
            WHERE id = ANY($1::int[]) AND disabled_at IS NULL
            RETURNING id
            """,
            payload.video_ids,
        )
    changed = {row["id"] for row in rows}
    skipped = [video_id for video_id in payload.video_ids if video_id not in changed]
    return BatchCountResponse(count=len(changed), skipped=skipped)


@router.post("/batch/enable", response_model=BatchCountResponse)
async def batch_enable_videos(payload: BatchVideoIdsRequest) -> BatchCountResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            UPDATE videos
            SET disabled_at = NULL, updated_at = now()
            WHERE id = ANY($1::int[]) AND disabled_at IS NOT NULL
            RETURNING id
            """,
            payload.video_ids,
        )
    changed = {row["id"] for row in rows}
    skipped = [video_id for video_id in payload.video_ids if video_id not in changed]
    return BatchCountResponse(count=len(changed), skipped=skipped)


@router.post("/batch/change-source", response_model=BatchMetadataResponse)
async def batch_change_source(payload: BatchChangeSourceRequest) -> BatchMetadataResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            UPDATE videos
            SET source = $2, updated_at = now()
            WHERE id = ANY($1::int[])
            RETURNING id
            """,
            payload.video_ids,
            payload.new_source,
        )
    changed = {row["id"] for row in rows}
    errors = [
        BatchError(video_id=video_id, reason="video not found")
        for video_id in payload.video_ids
        if video_id not in changed
    ]
    return BatchMetadataResponse(count=len(changed), errors=errors)


@router.post("/batch/metadata-update", response_model=BatchMetadataResponse)
async def batch_update_metadata(payload: BatchMetadataUpdateRequest) -> BatchMetadataResponse:
    try:
        set_sql, values = build_metadata_update_clause(payload.updates, first_param=2)
    except ValueError as exc:
        return BatchMetadataResponse(
            count=0,
            errors=[BatchError(video_id=video_id, reason=str(exc)) for video_id in payload.video_ids],
        )
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            UPDATE videos
            SET {set_sql}
            WHERE id = ANY($1::int[])
            RETURNING id
            """,
            payload.video_ids,
            *values,
        )
    changed = {row["id"] for row in rows}
    errors = [
        BatchError(video_id=video_id, reason="video not found")
        for video_id in payload.video_ids
        if video_id not in changed
    ]
    return BatchMetadataResponse(count=len(changed), errors=errors)


@router.post("/batch/add-taxonomy", response_model=BatchCountResponse)
async def batch_add_taxonomy(payload: BatchAddTaxonomyRequest) -> BatchCountResponse:
    config = get_table_config(payload.kind)
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing_rows = await conn.fetch(
            f"""
            SELECT video_id, {config.term_column} AS term_id
            FROM {config.join_table}
            WHERE video_id = ANY($1::int[]) AND {config.term_column} = ANY($2::int[])
            """,
            payload.video_ids,
            payload.term_ids,
        )
        existing_pairs = {(row["video_id"], row["term_id"]) for row in existing_rows}
        rows = await conn.fetch(
            f"""
            INSERT INTO {config.join_table} (video_id, {config.term_column})
            SELECT selected_video.video_id, selected_term.term_id
            FROM unnest($1::int[]) AS selected_video(video_id)
            CROSS JOIN unnest($2::int[]) AS selected_term(term_id)
            ON CONFLICT DO NOTHING
            RETURNING video_id, {config.term_column} AS term_id
            """,
            payload.video_ids,
            payload.term_ids,
        )
    inserted_pairs = {(row["video_id"], row["term_id"]) for row in rows}
    skipped = [
        video_id
        for video_id in payload.video_ids
        if all((video_id, term_id) in existing_pairs for term_id in payload.term_ids)
        and not any((video_id, term_id) in inserted_pairs for term_id in payload.term_ids)
    ]
    return BatchCountResponse(count=len(inserted_pairs), skipped=skipped)


@router.get("", response_model=list[VideoListItem])
async def list_videos(
    site: Site | None = Query(None, description="Deprecated, ignored. Video catalog is now global."),
    limit: int = Query(24, ge=1, le=100000),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="Postgres FTS query over title."),
    actor: str | None = Query(None, description="Filter by actor slug."),
    studio: str | None = Query(None, description="Filter by studio slug."),
    category: str | None = Query(None, description="Filter by category slug."),
    related_to: str | None = Query(None, description="Related-video seed slug."),
    exclude_slug: str | None = Query(None, description="Slug to omit from results."),
    actor_gender: str | None = Query(
        None,
        description=(
            "Filter the embedded actors_json by gender. Accepts 'female', 'male', "
            "'unknown', a comma-separated list, or 'all' (no filter — default "
            "for backward compat). Videos themselves are not hidden; only the "
            "embedded pornstar pills are filtered."
        ),
    ),
    disabled: bool | None = Query(None, description="Filter by disabled status. True = disabled, False = enabled, None = all."),
    source: str | None = Query(None, description="Filter by video source."),
) -> list[VideoListItem]:
    pool = await get_pool()
    where_sql, joins, params = build_video_filters(
        site=site,
        q=q,
        actor=actor,
        studio=studio,
        category=category,
        related_to=related_to,
        exclude_slug=exclude_slug,
        disabled=disabled,
        source=source,
    )
    # Optional gender filter on the embedded actors_json subquery.
    gender_fragment, gender_params = build_gender_clause(
        actor_gender, "a.gender", len(params) + 1
    )
    params.extend(gender_params)
    actor_gender_clause = f" AND {gender_fragment}" if gender_fragment else ""
    limit_param = f"${len(params) + 1}"
    offset_param = f"${len(params) + 2}"
    params.extend([limit, offset])
    sql_base = f"""
        SELECT videos.id, videos.site, videos.source, videos.title, videos.slug,
               videos.thumbnail_url, videos.preview_url, videos.duration_seconds,
               videos.views, videos.created_at, videos.disabled_at, videos.qualities,
               (
                 SELECT coalesce(jsonb_agg(jsonb_build_object('id', a.id, 'name', a.name, 'slug', a.slug)), '[]'::jsonb)
                 FROM video_pornstars va
                 JOIN pornstars a ON a.id = va.pornstar_id
                 WHERE va.video_id = videos.id{actor_gender_clause}
               ) as actors_json,
               (
                 SELECT coalesce(jsonb_agg(jsonb_build_object('id', s.id, 'name', s.name, 'slug', s.slug)), '[]'::jsonb)
                 FROM video_studios vs
                 JOIN studios s ON s.id = vs.studio_id
                 WHERE vs.video_id = videos.id
               ) as studios_json
        FROM videos
        {joins}
        WHERE {where_sql}
        GROUP BY videos.id
        ORDER BY videos.created_at DESC
        LIMIT {limit_param} OFFSET {offset_param}
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql_base, *params)
    
    results = []
    for r in rows:
        d = dict(r)
        
        # Deserialise qualities JSONB/string
        if isinstance(d.get("qualities"), str):
            try:
                d["qualities"] = json.loads(d["qualities"])
            except Exception:
                d["qualities"] = None
                
        # Deserialise aggregated actors json/string
        actors_val = d.pop("actors_json", None)
        if isinstance(actors_val, str):
            try:
                d["actors"] = json.loads(actors_val)
            except Exception:
                d["actors"] = []
        elif isinstance(actors_val, list):
            d["actors"] = actors_val
        else:
            d["actors"] = []
            
        # Deserialise aggregated studios json/string
        studios_val = d.pop("studios_json", None)
        if isinstance(studios_val, str):
            try:
                d["studios"] = json.loads(studios_val)
            except Exception:
                d["studios"] = []
        elif isinstance(studios_val, list):
            d["studios"] = studios_val
        else:
            d["studios"] = []
 
        results.append(VideoListItem(**d))
    return results
 
 
@router.get("/count")
async def count_videos(
    site: Site | None = Query(None, description="Deprecated, ignored. Video catalog is now global."),
    q: str | None = Query(None),
    actor: str | None = Query(None),
    studio: str | None = Query(None),
    category: str | None = Query(None),
    disabled: bool | None = Query(None, description="Filter by disabled status. True = disabled, False = enabled, None = all."),
    source: str | None = Query(None, description="Filter by video source."),
) -> dict:
    """Count videos for the given site + filters. Cheap path for admin pagination."""
    where_sql, joins, params = build_video_filters(
        site=site,
        q=q,
        actor=actor,
        studio=studio,
        category=category,
        disabled=disabled,
        source=source,
    )
    pool = await get_pool()
    sql = f"""
        SELECT COUNT(DISTINCT videos.id) AS total
        FROM videos
        {joins}
        WHERE {where_sql}
    """
    async with pool.acquire() as conn:
        total = await conn.fetchval(sql, *params)
    return {"total": int(total or 0)}


@router.get("/{slug}", response_model=VideoDetail | None)
async def get_video(
    slug: str,
    site: Site | None = Query(None, description="Deprecated, ignored. Video catalog is now global."),
    actor_gender: str | None = Query(
        None,
        description=(
            "Filter returned pornstars by gender (default 'all'). "
            "Same syntax as the list endpoint."
        ),
    ),
) -> VideoDetail | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, title, slug, thumbnail_url, preview_url,
                   duration_seconds, views, created_at, updated_at,
                   source, source_url, embed_url, embed_type, qualities,
                   description
            FROM videos
            WHERE slug = $1
            """,
            slug,
        )
        if row is None:
            return None

        video_id = row["id"]
        actor_sql = """
            SELECT pornstars.id, pornstars.name, pornstars.slug
            FROM pornstars
            JOIN video_pornstars ON video_pornstars.pornstar_id = pornstars.id
            WHERE video_pornstars.video_id = $1
        """
        actor_params: list = [video_id]
        gender_fragment, gender_params = build_gender_clause(
            actor_gender, "pornstars.gender", len(actor_params) + 1
        )
        actor_params.extend(gender_params)
        if gender_fragment:
            actor_sql += f" AND {gender_fragment}"
        actor_sql += " ORDER BY pornstars.name ASC"
        actors = await conn.fetch(actor_sql, *actor_params)
        studios = await conn.fetch(
            """
            SELECT studios.id, studios.name, studios.slug
            FROM studios
            JOIN video_studios ON video_studios.studio_id = studios.id
            WHERE video_studios.video_id = $1
            ORDER BY studios.name ASC
            """,
            video_id,
        )
        categories = await conn.fetch(
            """
            SELECT categories.id, categories.name, categories.slug
            FROM categories
            JOIN video_categories ON video_categories.category_id = categories.id
            WHERE video_categories.video_id = $1
            ORDER BY categories.name ASC
            """,
            video_id,
        )
    payload = dict(row)
    
    # Deserialise qualities
    if isinstance(payload.get("qualities"), str):
        try:
            payload["qualities"] = json.loads(payload["qualities"])
        except Exception:
            payload["qualities"] = None

    payload["actors"] = [TermRef(**dict(r)) for r in actors]
    payload["studios"] = [TermRef(**dict(r)) for r in studios]
    payload["categories"] = [TermRef(**dict(r)) for r in categories]
    return VideoDetail(**payload)


@router.post("/{slug}/view")
async def increment_video_view(slug: str, site: Site = Query(...)) -> dict[str, int]:
    """Bump the view counter by 1.

    Called from the tube apps' video detail SSR (one bump per page load).
    Bot inflation is acceptable for a v1 — viewers see a monotonically
    increasing number, which is the only thing the UI cares about.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE videos
               SET views = views + 1,
                   updated_at = now()
             WHERE site = $1 AND slug = $2
         RETURNING views
            """,
            site,
            slug,
        )
    if row is None:
        return {"views": 0}
    return {"views": int(row["views"])}
