"""GET/PATCH/DELETE videos. Insertion happens via the fetcher persistence path."""
from __future__ import annotations

from fastapi import APIRouter, Query

import json
from .db import get_pool
from ._models import Site, TermRef, VideoDetail, VideoListItem

router = APIRouter(prefix="/videos", tags=["promking:videos"])


def build_video_filters(
    *,
    site: Site,
    q: str | None = None,
    actor: str | None = None,
    studio: str | None = None,
    category: str | None = None,
    related_to: str | None = None,
    exclude_slug: str | None = None,
) -> tuple[str, str, list]:
    """Build taxonomy/related filters for list_videos.

    The helper is intentionally pure so frontend-facing filter contracts can be
    unit-tested without requiring Postgres.
    """
    joins: list[str] = []
    where = ["videos.site = $1", "videos.embed_type <> 'iframe'"]
    params: list = [site]

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
                "JOIN video_actors actor_filter ON actor_filter.video_id = videos.id",
                "JOIN actors actor_terms ON actor_terms.id = actor_filter.actor_id",
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
                "JOIN videos related_video ON related_video.site = videos.site",
                "LEFT JOIN video_actors related_actors ON related_actors.video_id = related_video.id",
                "LEFT JOIN video_actors current_actors ON current_actors.video_id = videos.id AND current_actors.actor_id = related_actors.actor_id",
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
            "current_actors.actor_id IS NOT NULL OR "
            "current_studios.studio_id IS NOT NULL OR "
            "current_categories.category_id IS NOT NULL"
            ")"
        )
    if exclude_slug:
        where.append(f"videos.slug <> {add_param(exclude_slug)}")

    return " AND ".join(where), "\n        ".join(joins), params


@router.get("", response_model=list[VideoListItem])
async def list_videos(
    site: Site = Query(..., description="fxv or pkt — required."),
    limit: int = Query(24, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="Postgres FTS query over title."),
    actor: str | None = Query(None, description="Filter by actor slug."),
    studio: str | None = Query(None, description="Filter by studio slug."),
    category: str | None = Query(None, description="Filter by category slug."),
    related_to: str | None = Query(None, description="Related-video seed slug."),
    exclude_slug: str | None = Query(None, description="Slug to omit from results."),
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
    )
    limit_param = f"${len(params) + 1}"
    offset_param = f"${len(params) + 2}"
    params.extend([limit, offset])
    sql_base = f"""
        SELECT videos.id, videos.site, videos.title, videos.slug,
               videos.thumbnail_url, videos.preview_url, videos.duration_seconds,
               videos.views, videos.created_at, videos.qualities,
               (
                 SELECT coalesce(jsonb_agg(jsonb_build_object('id', a.id, 'name', a.name, 'slug', a.slug)), '[]'::jsonb)
                 FROM video_actors va
                 JOIN actors a ON a.id = va.actor_id
                 WHERE va.video_id = videos.id
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


@router.get("/{slug}", response_model=VideoDetail | None)
async def get_video(slug: str, site: Site = Query(...)) -> VideoDetail | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, site, title, slug, thumbnail_url, preview_url,
                   duration_seconds, views, created_at, updated_at,
                   source, source_url, embed_url, embed_type, qualities
            FROM videos
            WHERE site = $1 AND slug = $2 AND embed_type <> 'iframe'
            """,
            site,
            slug,
        )
        if row is None:
            return None

        video_id = row["id"]
        actors = await conn.fetch(
            """
            SELECT actors.id, actors.name, actors.slug
            FROM actors
            JOIN video_actors ON video_actors.actor_id = actors.id
            WHERE video_actors.video_id = $1
            ORDER BY actors.name ASC
            """,
            video_id,
        )
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
