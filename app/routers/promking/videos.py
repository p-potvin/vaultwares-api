"""GET/PATCH/DELETE videos. Insertion happens via the fetcher persistence path."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import asyncio
import json
import re
import secrets
import time
from typing import Any
from .db import get_pool


async def is_admin_request(request: Request) -> bool:
    try:
        from api.config import GATEWAY_SHARED_SECRET, GATEWAY_HEADER_NAME
        if GATEWAY_SHARED_SECRET:
            gw_hdr = request.headers.get(GATEWAY_HEADER_NAME)
            if gw_hdr and secrets.compare_digest(gw_hdr, GATEWAY_SHARED_SECRET):
                return True
    except Exception:
        pass

    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        try:
            from api.auth import JWT_SECRET, JWT_AUDIENCE, JWT_ISSUER
            from jose import jwt
            payload = jwt.decode(
                token,
                JWT_SECRET,
                algorithms=["HS256"],
                audience=JWT_AUDIENCE,
                issuer=JWT_ISSUER,
            )
            if payload.get("adm") is True:
                return True
            user_id = payload.get("uid")
            if user_id:
                pool = await get_pool()
                async with pool.acquire() as conn:
                    user_role = await conn.fetchval(
                        "SELECT role FROM users WHERE id = $1 AND disabled_at IS NULL",
                        user_id,
                    )
                    if user_role == "admin":
                        return True
        except Exception:
            pass

    return False
from ._models import (
    BatchAddTaxonomyRequest,
    BatchRemoveTaxonomyRequest,
    BatchChangeSourceRequest,
    BatchCountResponse,
    BatchError,
    BatchMergeQueueRequest,
    BatchMergeQueueResponse,
    BatchMetadataResponse,
    BatchMetadataUpdateRequest,
    BatchRemotePreviewsRequest,
    BatchRevertPreviewsRequest,
    BatchVideoIdsRequest,
    BatchVideoMergeRequest,
    BatchVideoMergeResponse,
    DuplicateCandidateItem,
    DuplicateClusterItem,
    DuplicateQueueResponse,
    MergeAllDuplicatesRequest,
    MergeAllDuplicatesResponse,
    Site,
    TermRef,
    VideoDetail,
    VideoListItem,
)
from .taxonomies import get_table_config
from .media import remote as remote_media
from .viewers import require_admin

router = APIRouter(prefix="/videos", tags=["promking:videos"])

_METADATA_COLUMNS = {
    "title": "title",
    "slug": "slug",
    "source_url": "source_url",
    "embed_url": "embed_url",
    "embed_type": "embed_type",
    "thumbnail_url": "thumbnail_url",
    "preview_url": "preview_url",
    "duration_seconds": "duration_seconds",
    "views": "views",
    "description": "description",
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


STOP_WORDS = {
    "the", "a", "an", "of", "in", "and", "on", "at", "for", "to",
    "with", "by", "from", "is", "or", "it", "as", "be", "this", "that",
}


def build_video_filters(
    *,
    site: Site | None = None,
    q: str | None = None,
    pornstar: str | None = None,
    studio: str | None = None,
    category: str | None = None,
    related_to: str | None = None,
    exclude_slug: str | None = None,
    disabled: str | bool | None = None,
    source: str | None = None,
    health: str | None = None,
    onlyfans: str | bool | None = "false",
    admin: bool = False,
) -> tuple[str, str, list]:
    """Build taxonomy/related filters for list_videos.

    The helper is intentionally pure so frontend-facing filter contracts can be
    unit-tested without requiring Postgres.
    """
    # Normalise disabled flag:
    #   "all" / None -> do not filter by disabled status at all
    #   True / "true" / "disabled" -> disabled only
    #   False / "false" / "enabled" -> enabled only
    is_disabled_filter: str | bool | None = disabled
    if isinstance(disabled, str):
        d_lower = disabled.strip().lower()
        if d_lower in ("all", "none", ""):
            is_disabled_filter = "all"
        elif d_lower in ("true", "1", "disabled"):
            is_disabled_filter = True
        elif d_lower in ("false", "0", "enabled"):
            is_disabled_filter = False
        else:
            is_disabled_filter = None
    elif disabled is False:
        is_disabled_filter = False
    elif disabled is True:
        is_disabled_filter = True

    # Normalise onlyfans flag:
    #   "all" -> do not filter by onlyfans at all
    #   True / "true" / "1" -> onlyfans videos only
    #   False / "false" / "0" / None -> regular videos only (default)
    is_onlyfans_filter: str | bool | None = onlyfans
    if isinstance(onlyfans, str):
        of_lower = onlyfans.strip().lower()
        if of_lower in ("all", "both"):
            is_onlyfans_filter = "all"
        elif of_lower in ("true", "1"):
            is_onlyfans_filter = True
        elif of_lower in ("false", "0", "none"):
            is_onlyfans_filter = False
        else:
            is_onlyfans_filter = False
    elif onlyfans is True:
        is_onlyfans_filter = True
    elif onlyfans is False or onlyfans is None:
        is_onlyfans_filter = False

    joins: list[str] = []
    where = ["1=1"]
    params: list = []

    if is_onlyfans_filter is True:
        where.append("videos.is_onlyfans = true")
    elif is_onlyfans_filter is False:
        where.append("videos.is_onlyfans = false")

    def add_param(value: Any) -> str:
        params.append(value)
        return f"${len(params)}"

    # Video catalog is unified across all sites; `site` argument is preserved for backwards compatibility but ignored.
    if q:
        clean_q = q.strip()
        num_id = clean_q[1:] if clean_q.startswith("#") else clean_q
        is_num = num_id.isdigit()
        is_admin_mode = admin or (is_disabled_filter == "all") or (health is not None)

        if is_admin_mode:
            search_clauses = []
            if is_num:
                search_clauses.append(f"videos.id = {add_param(int(num_id))}")
            q_like = add_param(f"%{clean_q}%")
            search_clauses.append(f"videos.title ILIKE {q_like}")
            q_ts = add_param(clean_q)
            search_clauses.append(f"to_tsvector('english', videos.title) @@ plainto_tsquery('english', {q_ts})")

            # Meaningful word matching across title (AND logic)
            words = [re.sub(r'[^a-zA-Z0-9]', '', w) for w in clean_q.split()]
            meaningful = [w for w in words if w.lower() not in STOP_WORDS and len(w) >= 2]
            if len(meaningful) >= 2:
                and_title = [f"videos.title ILIKE {add_param(f'%{w}%')}" for w in meaningful]
                search_clauses.append("(" + " AND ".join(and_title) + ")")

            where.append("(" + " OR ".join(search_clauses) + ")")
        else:
            search_clauses = []
            if is_num:
                search_clauses.append(f"videos.id = {add_param(int(num_id))}")
            q_ts = add_param(clean_q)
            q_like = add_param(f"%{clean_q}%")
            search_clauses.extend([
                f"to_tsvector('english', videos.title) @@ plainto_tsquery('english', {q_ts})",
                f"videos.title ILIKE {q_like}",
                "videos.id IN (SELECT q_vp.video_id FROM video_pornstars q_vp"
                "                    JOIN pornstars q_p ON q_p.id = q_vp.pornstar_id"
                f"                  WHERE q_p.name ILIKE {q_like} AND q_p.deleted_at IS NULL)",
                "videos.id IN (SELECT q_vs.video_id FROM video_studios q_vs"
                "                    JOIN studios q_s ON q_s.id = q_vs.studio_id"
                f"                  WHERE q_s.name ILIKE {q_like} AND q_s.deleted_at IS NULL)",
                "videos.id IN (SELECT q_vc.video_id FROM video_categories q_vc"
                "                    JOIN categories q_c ON q_c.id = q_vc.category_id"
                f"                  WHERE q_c.name ILIKE {q_like} AND q_c.deleted_at IS NULL)",
            ])

            # Multi-word fuzzy / cross-entity search for public client: filter out stop words
            words = [re.sub(r'[^a-zA-Z0-9]', '', w) for w in clean_q.split()]
            words = [w for w in words if w.lower() not in STOP_WORDS and len(w) >= 3]
            if len(words) >= 2:
                or_terms = " | ".join(words)
                p_or_ts = add_param(or_terms)
                search_clauses.append(f"to_tsvector('english', videos.title) @@ to_tsquery('english', {p_or_ts})")
                word_patterns = [f"%{w}%" for w in words]
                p_patterns = add_param(word_patterns)
                search_clauses.append(
                    "videos.id IN (SELECT q_vp.video_id FROM video_pornstars q_vp"
                    "                    JOIN pornstars q_p ON q_p.id = q_vp.pornstar_id"
                    f"                  WHERE q_p.name ILIKE ANY({p_patterns}::text[]) AND q_p.deleted_at IS NULL)"
                )
                search_clauses.append(
                    "videos.id IN (SELECT q_vs.video_id FROM video_studios q_vs"
                    "                    JOIN studios q_s ON q_s.id = q_vs.studio_id"
                    f"                  WHERE q_s.name ILIKE ANY({p_patterns}::text[]) AND q_s.deleted_at IS NULL)"
                )
                search_clauses.append(
                    "videos.id IN (SELECT q_vc.video_id FROM video_categories q_vc"
                    "                    JOIN categories q_c ON q_c.id = q_vc.category_id"
                    f"                  WHERE q_c.name ILIKE ANY({p_patterns}::text[]) AND q_c.deleted_at IS NULL)"
                )

            where.append("(" + " OR ".join(search_clauses) + ")")
    if pornstar:
        joins.extend(
            [
                "JOIN video_pornstars pornstar_filter ON pornstar_filter.video_id = videos.id",
                "JOIN pornstars pornstar_terms ON pornstar_terms.id = pornstar_filter.pornstar_id",
            ]
        )
        where.append(f"pornstar_terms.slug = {add_param(pornstar)}")
        where.append("pornstar_terms.deleted_at IS NULL")
        if is_disabled_filter is False:
            where.append("pornstar_terms.disabled = false")
    if studio:
        joins.extend(
            [
                "JOIN video_studios studio_filter ON studio_filter.video_id = videos.id",
                "JOIN studios studio_terms ON studio_terms.id = studio_filter.studio_id",
            ]
        )
        where.append(f"studio_terms.slug = {add_param(studio)}")
        where.append("studio_terms.deleted_at IS NULL")
        if is_disabled_filter is False:
            where.append("studio_terms.disabled = false")
    if category:
        joins.extend(
            [
                "JOIN video_categories category_filter ON category_filter.video_id = videos.id",
                "JOIN categories category_terms ON category_terms.id = category_filter.category_id",
            ]
        )
        where.append(f"category_terms.slug = {add_param(category)}")
        where.append("category_terms.deleted_at IS NULL")
        if is_disabled_filter is False:
            where.append("category_terms.disabled = false")
    if related_to:
        joins.extend(
            [
                "JOIN videos related_video ON 1=1",
                "LEFT JOIN video_pornstars related_pornstars ON related_pornstars.video_id = related_video.id",
                "LEFT JOIN video_pornstars current_pornstars ON current_pornstars.video_id = videos.id AND current_pornstars.pornstar_id = related_pornstars.pornstar_id",
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
            "current_pornstars.pornstar_id IS NOT NULL OR "
            "current_studios.studio_id IS NOT NULL OR "
            "current_categories.category_id IS NOT NULL"
            ")"
        )
    if exclude_slug:
        where.append(f"videos.slug <> {add_param(exclude_slug)}")
    if is_disabled_filter is not None and is_disabled_filter != "all":
        if is_disabled_filter is True:
            where.append(
                "("
                "videos.disabled_at IS NOT NULL OR "
                "EXISTS (SELECT 1 FROM video_studios vs JOIN studios s ON s.id = vs.studio_id WHERE vs.video_id = videos.id AND s.disabled = true) OR "
                "EXISTS (SELECT 1 FROM video_pornstars vp JOIN pornstars p ON p.id = vp.pornstar_id WHERE vp.video_id = videos.id AND p.disabled = true) OR "
                "EXISTS (SELECT 1 FROM video_categories vc JOIN categories c ON c.id = vc.category_id WHERE vc.video_id = videos.id AND c.disabled = true)"
                ")"
            )
        else:
            where.append("videos.disabled_at IS NULL")
            where.append("NOT EXISTS (SELECT 1 FROM video_pornstars vp JOIN pornstars p ON p.id = vp.pornstar_id WHERE vp.video_id = videos.id AND p.disabled = true)")
            where.append("NOT EXISTS (SELECT 1 FROM video_studios vs JOIN studios s ON s.id = vs.studio_id WHERE vs.video_id = videos.id AND s.disabled = true)")
            where.append("NOT EXISTS (SELECT 1 FROM video_categories vc JOIN categories c ON c.id = vc.category_id WHERE vc.video_id = videos.id AND c.disabled = true)")
    if source:
        where.append(f"videos.source = {add_param(source)}")
    if health:
        if health == "missing_thumbnail":
            where.append("(videos.thumbnail_url IS NULL OR videos.thumbnail_url = '')")
        elif health == "missing_duration":
            where.append("(videos.duration_seconds IS NULL OR videos.duration_seconds = 0)")
        elif health == "missing_description":
            where.append("(videos.description IS NULL OR videos.description = '')")
        elif health == "tpdb_matched":
            where.append("EXISTS (SELECT 1 FROM tpdb_scenes ts WHERE ts.video_id = videos.id)")
        elif health == "tpdb_unmatched":
            where.append("NOT EXISTS (SELECT 1 FROM tpdb_scenes ts WHERE ts.video_id = videos.id)")
        elif health == "untagged_categories":
            where.append("NOT EXISTS (SELECT 1 FROM video_categories vc JOIN categories c ON c.id = vc.category_id WHERE vc.video_id = videos.id AND c.disabled = false)")
        elif health == "untagged_pornstars":
            where.append("NOT EXISTS (SELECT 1 FROM video_pornstars vp JOIN pornstars p ON p.id = vp.pornstar_id WHERE vp.video_id = videos.id AND p.disabled = false)")
        elif health == "untagged_studios":
            where.append("NOT EXISTS (SELECT 1 FROM video_studios vs JOIN studios s ON s.id = vs.studio_id WHERE vs.video_id = videos.id AND s.disabled = false)")

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


def generated_preview_url(media_hash: str) -> str:
    return f"/api/promking/media/cache/{media_hash}.mp4"


@router.post("/batch/remote-previews", response_model=BatchMetadataResponse)
async def batch_set_remote_previews(
    payload: BatchRemotePreviewsRequest, _admin: dict = Depends(require_admin)
) -> BatchMetadataResponse:
    """Points videos at their generated preview (`/api/promking/media/cache/<hash>.mp4`).

    The clip may live on the workstation rather than OVH (see `media/remote.py`). The video's
    current external preview_url is remembered as the fallback, served when the clip can't be.
    It is recorded before the Postgres update commits; revert checks Postgres, so a record left
    by a failed batch is never acted on.
    """
    items = {item.video_id: item for item in payload.items}
    ids = list(items)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            current = {
                row["id"]: row["preview_url"]
                for row in await conn.fetch(
                    "SELECT id, preview_url FROM videos WHERE id = ANY($1::int[]) FOR UPDATE",
                    ids,
                )
            }
            found = [video_id for video_id in ids if video_id in current]
            fallbacks = []
            for video_id in found:
                item = items[video_id]
                old = current[video_id] or ""
                fallback = item.fallback_url or (old if re.match(r"^https?://", old) else None)
                fallbacks.append((item.media_hash, video_id, fallback))
            await asyncio.to_thread(remote_media.save_fallbacks, fallbacks)
            await conn.execute(
                """
                UPDATE videos AS v
                SET preview_url = x.url, updated_at = now()
                FROM unnest($1::int[], $2::text[]) AS x(id, url)
                WHERE v.id = x.id AND v.preview_url IS DISTINCT FROM x.url
                """,
                found,
                [generated_preview_url(items[video_id].media_hash) for video_id in found],
            )
    errors = [BatchError(video_id=video_id, reason="video not found") for video_id in ids if video_id not in current]
    return BatchMetadataResponse(count=len(found), errors=errors)


@router.post("/batch/remote-previews/revert", response_model=BatchMetadataResponse)
async def batch_revert_remote_previews(
    payload: BatchRevertPreviewsRequest, _admin: dict = Depends(require_admin)
) -> BatchMetadataResponse:
    """Puts the site's original preview back for videos switched by `/batch/remote-previews`.

    Only videos still pointing at the clip they were switched to are touched: a preview edited
    since (or a switch whose batch failed) is left alone.
    """
    records = await asyncio.to_thread(remote_media.records_for_videos, payload.video_ids)
    revertible = {v: r for v, r in records.items() if r[1]}
    ids = list(revertible)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            UPDATE videos AS v
            SET preview_url = x.url, updated_at = now()
            FROM unnest($1::int[], $2::text[], $3::text[]) AS x(id, url, expected)
            WHERE v.id = x.id AND v.preview_url = x.expected
            RETURNING v.id
            """,
            ids,
            [revertible[video_id][1] for video_id in ids],
            [generated_preview_url(revertible[video_id][0]) for video_id in ids],
        )
    changed = {row["id"] for row in rows}

    def reason(video_id: int) -> str:
        if video_id not in records:
            return "never switched to a generated preview"
        if video_id not in revertible:
            return "no original preview recorded"
        return "video not found or preview_url changed since the switch"

    errors = [BatchError(video_id=v, reason=reason(v)) for v in payload.video_ids if v not in changed]
    return BatchMetadataResponse(count=len(changed), errors=errors)


@router.post("/batch/merge", response_model=BatchVideoMergeResponse)
async def batch_merge_videos(payload: BatchVideoMergeRequest) -> BatchVideoMergeResponse:
    """Merge one or more secondary videos into a primary video.
    
    Transfers views, taxonomy links (pornstars, studios, categories), short links,
    and video_sites. Preserves audio previews (especially from /media/cache/) and
    backfills any missing duration, thumbnail, description, or qualities.
    Soft-disables merged secondary videos.
    """
    primary_id = payload.primary_id
    merge_from = [vid for vid in payload.merge_from if vid != primary_id]
    if not merge_from:
        raise HTTPException(status_code=400, detail="No secondary videos provided to merge")

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            primary = await conn.fetchrow(
                """
                SELECT id, title, slug, thumbnail_url, preview_url, duration_seconds,
                       views, qualities, description, source, source_url
                  FROM videos
                 WHERE id = $1
                """,
                primary_id,
            )
            if not primary:
                raise HTTPException(status_code=404, detail=f"Primary video #{primary_id} not found")

            secondaries = await conn.fetch(
                """
                SELECT id, title, slug, thumbnail_url, preview_url, duration_seconds,
                       views, qualities, description, source, source_url
                  FROM videos
                 WHERE id = ANY($1::int[])
                """,
                merge_from,
            )
            if not secondaries:
                raise HTTPException(status_code=404, detail="No valid secondary videos found")

            found_ids = [s["id"] for s in secondaries]

            # 1. Total Views
            total_views = (primary["views"] or 0) + sum(s["views"] or 0 for s in secondaries)

            # 2. Preview URL / Audio preview preservation
            preview_url = primary["preview_url"]
            if payload.preserve_audio_preview:
                def is_audio_preview(url: str | None) -> bool:
                    if not url:
                        return False
                    u = url.lower()
                    return "/media/cache/" in u or "/generator/" in u

                has_audio = is_audio_preview(preview_url)
                if not has_audio:
                    for s in secondaries:
                        s_prev = s["preview_url"]
                        if is_audio_preview(s_prev):
                            preview_url = s_prev
                            break
                    if not preview_url:
                        for s in secondaries:
                            if s["preview_url"]:
                                preview_url = s["preview_url"]
                                break
            elif not preview_url:
                for s in secondaries:
                    if s["preview_url"]:
                        preview_url = s["preview_url"]
                        break

            # 3. Thumbnail URL
            thumbnail_url = primary["thumbnail_url"]
            if payload.prefer_secondary_thumbnail or not thumbnail_url:
                for s in secondaries:
                    if s["thumbnail_url"]:
                        thumbnail_url = s["thumbnail_url"]
                        break

            # 4. Duration
            duration = primary["duration_seconds"]
            if not duration:
                for s in secondaries:
                    if s["duration_seconds"]:
                        duration = s["duration_seconds"]
                        break

            # 5. Description
            description = primary["description"]
            if not description:
                for s in secondaries:
                    if s["description"]:
                        description = s["description"]
                        break

            # 6. Qualities
            qualities = primary["qualities"]
            if not qualities:
                for s in secondaries:
                    if s["qualities"]:
                        qualities = s["qualities"]
                        break

            # 7. Title & Slug overrides if supplied
            title = payload.custom_title.strip() if payload.custom_title and payload.custom_title.strip() else primary["title"]
            slug = payload.custom_slug.strip() if payload.custom_slug and payload.custom_slug.strip() else primary["slug"]

            # 8. Transfer Taxonomy
            await conn.execute(
                """
                INSERT INTO video_pornstars (video_id, pornstar_id)
                SELECT $1, pornstar_id
                  FROM video_pornstars
                 WHERE video_id = ANY($2::int[])
                ON CONFLICT (video_id, pornstar_id) DO NOTHING
                """,
                primary_id,
                found_ids,
            )
            await conn.execute(
                """
                INSERT INTO video_studios (video_id, studio_id)
                SELECT $1, studio_id
                  FROM video_studios
                 WHERE video_id = ANY($2::int[])
                ON CONFLICT (video_id, studio_id) DO NOTHING
                """,
                primary_id,
                found_ids,
            )
            await conn.execute(
                """
                INSERT INTO video_categories (video_id, category_id)
                SELECT $1, category_id
                  FROM video_categories
                 WHERE video_id = ANY($2::int[])
                ON CONFLICT (video_id, category_id) DO NOTHING
                """,
                primary_id,
                found_ids,
            )

            # Clean up taxonomy on secondaries so they are cleanly detached
            await conn.execute("DELETE FROM video_pornstars WHERE video_id = ANY($1::int[])", found_ids)
            await conn.execute("DELETE FROM video_studios WHERE video_id = ANY($1::int[])", found_ids)
            await conn.execute("DELETE FROM video_categories WHERE video_id = ANY($1::int[])", found_ids)

            # Transfer short links to primary
            await conn.execute(
                "UPDATE short_links SET video_id = $1 WHERE video_id = ANY($2::int[])",
                primary_id,
                found_ids,
            )

            # Transfer video sites
            await conn.execute(
                """
                INSERT INTO video_sites (video_id, site)
                SELECT $1, site
                  FROM video_sites
                 WHERE video_id = ANY($2::int[])
                ON CONFLICT (video_id, site) DO NOTHING
                """,
                primary_id,
                found_ids,
            )

            # Update primary video
            await conn.execute(
                """
                UPDATE videos
                   SET title = $2,
                       slug = $3,
                       views = $4,
                       preview_url = $5,
                       thumbnail_url = $6,
                       duration_seconds = $7,
                       description = $8,
                       qualities = $9,
                       updated_at = now()
                 WHERE id = $1
                """,
                primary_id,
                title,
                slug,
                total_views,
                preview_url,
                thumbnail_url,
                duration,
                description,
                qualities if isinstance(qualities, str) or qualities is None else json.dumps(qualities),
            )

            # Soft-disable secondaries
            await conn.execute(
                """
                UPDATE videos
                   SET disabled_at = now(),
                       updated_at = now()
                 WHERE id = ANY($1::int[])
                """,
                found_ids,
            )

    return BatchVideoMergeResponse(
        primary_id=primary_id,
        merged_ids=found_ids,
        primary_slug=slug,
        views=total_views,
        transferred_pornstars=0,
        transferred_studios=0,
        transferred_categories=0,
        preview_url=preview_url,
        thumbnail_url=thumbnail_url,
        message=f"Merged {len(found_ids)} video(s) into #{primary_id} ({slug}).",
    )


def score_video_candidate(v: dict | Any) -> float:
    """Deterministic score for choosing primary video in duplicate title cluster."""
    score = 0.0
    prev = (v.get("preview_url") or "").lower() if isinstance(v, dict) else (getattr(v, "preview_url", None) or "").lower()
    if "/media/cache/" in prev or "/generator/" in prev:
        score += 100000.0
    elif prev.startswith("http://") or prev.startswith("https://") or prev.startswith("/"):
        score += 10000.0

    thumb = (v.get("thumbnail_url") or "").lower() if isinstance(v, dict) else (getattr(v, "thumbnail_url", None) or "").lower()
    if thumb.startswith("http://") or thumb.startswith("https://") or thumb.startswith("/"):
        score += 5000.0

    qualities = v.get("qualities") if isinstance(v, dict) else getattr(v, "qualities", None)
    if qualities:
        score += 2000.0

    dur = (v.get("duration_seconds") if isinstance(v, dict) else getattr(v, "duration_seconds", None)) or 0
    if dur > 0:
        score += 1000.0 + min(dur, 3600)

    desc = v.get("description") if isinstance(v, dict) else getattr(v, "description", None)
    if desc:
        score += 500.0

    views = (v.get("views") if isinstance(v, dict) else getattr(v, "views", None)) or 0
    score += views

    vid = (v.get("id") if isinstance(v, dict) else getattr(v, "id", None)) or 0
    score += max(0, 1000000 - vid) / 10000.0
    return score


async def merge_single_cluster(
    conn,
    primary_row: dict | Any,
    secondaries_rows: list[dict | Any],
    preserve_audio_preview: bool = True,
    prefer_secondary_thumbnail: bool = False,
) -> tuple[int, list[int], int]:
    primary_id = primary_row["id"]
    found_ids = [s["id"] for s in secondaries_rows]
    if not found_ids:
        return primary_id, [], primary_row.get("views") or 0

    total_views = (primary_row["views"] or 0) + sum(s["views"] or 0 for s in secondaries_rows)

    def is_audio_preview(url: str | None) -> bool:
        if not url:
            return False
        u = url.lower()
        return "/media/cache/" in u or "/generator/" in u

    preview_url = primary_row["preview_url"]
    if preserve_audio_preview:
        has_audio = is_audio_preview(preview_url)
        if not has_audio:
            for s in secondaries_rows:
                if is_audio_preview(s["preview_url"]):
                    preview_url = s["preview_url"]
                    break
            if not preview_url:
                for s in secondaries_rows:
                    if s["preview_url"]:
                        preview_url = s["preview_url"]
                        break
    elif not preview_url:
        for s in secondaries_rows:
            if s["preview_url"]:
                preview_url = s["preview_url"]
                break

    thumbnail_url = primary_row["thumbnail_url"]
    if prefer_secondary_thumbnail or not thumbnail_url:
        for s in secondaries_rows:
            if s["thumbnail_url"]:
                thumbnail_url = s["thumbnail_url"]
                break

    duration = primary_row["duration_seconds"]
    if not duration:
        for s in secondaries_rows:
            if s["duration_seconds"]:
                duration = s["duration_seconds"]
                break

    description = primary_row["description"]
    if not description:
        for s in secondaries_rows:
            if s["description"]:
                description = s["description"]
                break

    qualities = primary_row["qualities"]
    if not qualities:
        for s in secondaries_rows:
            if s["qualities"]:
                qualities = s["qualities"]
                break

    # Transfer Taxonomies
    await conn.execute(
        """
        INSERT INTO video_pornstars (video_id, pornstar_id)
        SELECT $1, pornstar_id FROM video_pornstars WHERE video_id = ANY($2::int[])
        ON CONFLICT (video_id, pornstar_id) DO NOTHING
        """,
        primary_id, found_ids,
    )
    await conn.execute("DELETE FROM video_pornstars WHERE video_id = ANY($1::int[])", found_ids)

    await conn.execute(
        """
        INSERT INTO video_studios (video_id, studio_id)
        SELECT $1, studio_id FROM video_studios WHERE video_id = ANY($2::int[])
        ON CONFLICT (video_id, studio_id) DO NOTHING
        """,
        primary_id, found_ids,
    )
    await conn.execute("DELETE FROM video_studios WHERE video_id = ANY($1::int[])", found_ids)

    await conn.execute(
        """
        INSERT INTO video_categories (video_id, category_id)
        SELECT $1, category_id FROM video_categories WHERE video_id = ANY($2::int[])
        ON CONFLICT (video_id, category_id) DO NOTHING
        """,
        primary_id, found_ids,
    )
    await conn.execute("DELETE FROM video_categories WHERE video_id = ANY($1::int[])", found_ids)

    # Transfer Sites
    await conn.execute(
        """
        INSERT INTO video_sites (video_id, site)
        SELECT $1, site FROM video_sites WHERE video_id = ANY($2::int[])
        ON CONFLICT (video_id, site) DO NOTHING
        """,
        primary_id, found_ids,
    )
    await conn.execute("DELETE FROM video_sites WHERE video_id = ANY($1::int[])", found_ids)

    # Transfer Short links (preventing unique constraint collision on (site, provider, video_id))
    await conn.execute(
        """
        DELETE FROM short_links WHERE video_id = ANY($1::int[])
          AND (site, provider) IN (SELECT site, provider FROM short_links WHERE video_id = $2)
        """,
        found_ids, primary_id,
    )
    await conn.execute("UPDATE short_links SET video_id = $1 WHERE video_id = ANY($2::int[])", primary_id, found_ids)

    # Transfer Favourites (preventing collision on user_id/anon_id)
    await conn.execute(
        """
        DELETE FROM favourites WHERE video_id = ANY($1::int[])
          AND user_id IS NOT NULL AND user_id IN (SELECT user_id FROM favourites WHERE video_id = $2 AND user_id IS NOT NULL)
        """,
        found_ids, primary_id,
    )
    await conn.execute(
        """
        DELETE FROM favourites WHERE video_id = ANY($1::int[])
          AND anon_id IS NOT NULL AND anon_id IN (SELECT anon_id FROM favourites WHERE video_id = $2 AND anon_id IS NOT NULL)
        """,
        found_ids, primary_id,
    )
    await conn.execute("UPDATE favourites SET video_id = $1 WHERE video_id = ANY($2::int[])", primary_id, found_ids)

    # Update primary video
    await conn.execute(
        """
        UPDATE videos
           SET views = $2,
               preview_url = $3,
               thumbnail_url = $4,
               duration_seconds = $5,
               description = $6,
               qualities = $7,
               updated_at = now()
         WHERE id = $1
        """,
        primary_id,
        total_views,
        preview_url,
        thumbnail_url,
        duration,
        description,
        qualities if isinstance(qualities, str) or qualities is None else json.dumps(qualities),
    )

    # Soft-disable secondaries
    await conn.execute(
        """
        UPDATE videos
           SET disabled_at = now(),
               updated_at = now()
         WHERE id = ANY($1::int[])
        """,
        found_ids,
    )

    return primary_id, found_ids, total_views


@router.get("/duplicates/queue", response_model=DuplicateQueueResponse)
async def get_duplicates_queue(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None),
    min_count: int = Query(2, ge=2),
) -> DuplicateQueueResponse:
    """Queue of active videos grouped by normalized identical titles for review and merging."""
    pool = await get_pool()
    search_term = f"%{search.strip().lower()}%" if search and search.strip() else None

    async with pool.acquire() as conn:
        if search_term:
            count_row = await conn.fetchrow(
                """
                SELECT count(*) as total_clusters,
                       COALESCE(sum(cnt), 0) as total_duplicate_videos
                  FROM (
                    SELECT lower(trim(title)) as norm_title, count(*) as cnt
                      FROM videos
                     WHERE disabled_at IS NULL
                       AND (lower(title) LIKE $1 OR lower(slug) LIKE $1)
                     GROUP BY lower(trim(title))
                    HAVING count(*) >= $2
                  ) t
                """,
                search_term,
                min_count,
            )
            cluster_rows = await conn.fetch(
                """
                SELECT lower(trim(title)) as norm_title,
                       count(*) as cnt,
                       array_agg(id ORDER BY id ASC) as ids
                  FROM videos
                 WHERE disabled_at IS NULL
                   AND (lower(title) LIKE $1 OR lower(slug) LIKE $1)
                 GROUP BY lower(trim(title))
                HAVING count(*) >= $2
                 ORDER BY count(*) DESC, lower(trim(title)) ASC
                 LIMIT $3 OFFSET $4
                """,
                search_term,
                min_count,
                limit,
                offset,
            )
        else:
            count_row = await conn.fetchrow(
                """
                SELECT count(*) as total_clusters,
                       COALESCE(sum(cnt), 0) as total_duplicate_videos
                  FROM (
                    SELECT lower(trim(title)) as norm_title, count(*) as cnt
                      FROM videos
                     WHERE disabled_at IS NULL
                     GROUP BY lower(trim(title))
                    HAVING count(*) >= $1
                  ) t
                """,
                min_count,
            )
            cluster_rows = await conn.fetch(
                """
                SELECT lower(trim(title)) as norm_title,
                       count(*) as cnt,
                       array_agg(id ORDER BY id ASC) as ids
                  FROM videos
                 WHERE disabled_at IS NULL
                 GROUP BY lower(trim(title))
                HAVING count(*) >= $1
                 ORDER BY count(*) DESC, lower(trim(title)) ASC
                 LIMIT $2 OFFSET $3
                """,
                min_count,
                limit,
                offset,
            )

        total_clusters = int(count_row["total_clusters"] if count_row else 0)
        total_duplicate_videos = int(count_row["total_duplicate_videos"] if count_row else 0)
        redundant_count = max(0, total_duplicate_videos - total_clusters)

        all_ids = [vid for c in cluster_rows for vid in c["ids"]]
        videos_by_id = {}
        if all_ids:
            v_rows = await conn.fetch(
                """
                SELECT id, title, slug, thumbnail_url, preview_url, duration_seconds,
                       views, qualities, description, source, source_url
                  FROM videos
                 WHERE id = ANY($1::int[])
                """,
                all_ids,
            )
            videos_by_id = {row["id"]: row for row in v_rows}

        clusters_result: list[DuplicateClusterItem] = []
        for c in cluster_rows:
            v_list = [videos_by_id[vid] for vid in c["ids"] if vid in videos_by_id]
            if len(v_list) < 2:
                continue

            scored_candidates = sorted(v_list, key=score_video_candidate, reverse=True)
            primary_v = scored_candidates[0]
            secondaries_v = scored_candidates[1:]

            primary_item = DuplicateCandidateItem(
                id=primary_v["id"],
                title=primary_v["title"],
                slug=primary_v["slug"],
                source=primary_v["source"],
                views=primary_v["views"] or 0,
                duration_seconds=primary_v["duration_seconds"],
                preview_url=primary_v["preview_url"],
                thumbnail_url=primary_v["thumbnail_url"],
                qualities=primary_v["qualities"],
                score=score_video_candidate(primary_v),
            )

            secondaries_items = [
                DuplicateCandidateItem(
                    id=s["id"],
                    title=s["title"],
                    slug=s["slug"],
                    source=s["source"],
                    views=s["views"] or 0,
                    duration_seconds=s["duration_seconds"],
                    preview_url=s["preview_url"],
                    thumbnail_url=s["thumbnail_url"],
                    qualities=s["qualities"],
                    score=score_video_candidate(s),
                )
                for s in secondaries_v
            ]

            total_views = (primary_v["views"] or 0) + sum(s["views"] or 0 for s in secondaries_v)
            clusters_result.append(
                DuplicateClusterItem(
                    title=primary_v["title"],
                    norm_title=c["norm_title"],
                    count=len(v_list),
                    primary=primary_item,
                    secondaries=secondaries_items,
                    total_views=total_views,
                )
            )

        return DuplicateQueueResponse(
            total_clusters=total_clusters,
            total_duplicate_videos=total_duplicate_videos,
            redundant_count=redundant_count,
            clusters=clusters_result,
        )


@router.post("/duplicates/merge-batch", response_model=BatchMergeQueueResponse)
async def batch_merge_duplicates_queue(payload: BatchMergeQueueRequest) -> BatchMergeQueueResponse:
    """Merges a batch of duplicate title clusters automatically."""
    pool = await get_pool()
    search_term = f"%{payload.search.strip().lower()}%" if payload.search and payload.search.strip() else None

    async with pool.acquire() as conn:
        if search_term:
            cluster_rows = await conn.fetch(
                """
                SELECT lower(trim(title)) as norm_title,
                       count(*) as cnt,
                       array_agg(id ORDER BY id ASC) as ids
                  FROM videos
                 WHERE disabled_at IS NULL
                   AND (lower(title) LIKE $1 OR lower(slug) LIKE $1)
                 GROUP BY lower(trim(title))
                HAVING count(*) >= 2
                 ORDER BY count(*) DESC, lower(trim(title)) ASC
                 LIMIT $2
                """,
                search_term,
                payload.batch_size,
            )
        else:
            cluster_rows = await conn.fetch(
                """
                SELECT lower(trim(title)) as norm_title,
                       count(*) as cnt,
                       array_agg(id ORDER BY id ASC) as ids
                  FROM videos
                 WHERE disabled_at IS NULL
                 GROUP BY lower(trim(title))
                HAVING count(*) >= 2
                 ORDER BY count(*) DESC, lower(trim(title)) ASC
                 LIMIT $1
                """,
                payload.batch_size,
            )

        if not cluster_rows:
            return BatchMergeQueueResponse(
                processed_clusters=0,
                merged_secondaries_count=0,
                remaining_clusters=0,
                remaining_duplicate_videos=0,
                message="No duplicate clusters found.",
            )

        processed_clusters = 0
        merged_secondaries_count = 0

        async with conn.transaction():
            for c in cluster_rows:
                ids = c["ids"]
                v_rows = await conn.fetch(
                    """
                    SELECT id, title, slug, thumbnail_url, preview_url, duration_seconds,
                           views, qualities, description, source, source_url
                      FROM videos
                     WHERE id = ANY($1::int[]) AND disabled_at IS NULL
                    """,
                    ids,
                )
                if len(v_rows) < 2:
                    continue

                scored = sorted(v_rows, key=score_video_candidate, reverse=True)
                primary = scored[0]
                secondaries = scored[1:]

                await merge_single_cluster(
                    conn,
                    primary,
                    secondaries,
                    preserve_audio_preview=payload.preserve_audio_preview,
                    prefer_secondary_thumbnail=payload.prefer_secondary_thumbnail,
                )
                processed_clusters += 1
                merged_secondaries_count += len(secondaries)

            if payload.dry_run:
                raise HTTPException(
                    status_code=200,
                    detail=f"Dry run simulated {processed_clusters} clusters ({merged_secondaries_count} secondaries). No changes committed.",
                )

        rem_row = await conn.fetchrow(
            """
            SELECT count(*) as rem_clusters, COALESCE(sum(cnt), 0) as rem_videos
              FROM (
                SELECT lower(trim(title)), count(*) as cnt
                  FROM videos
                 WHERE disabled_at IS NULL
                 GROUP BY lower(trim(title))
                HAVING count(*) >= 2
              ) t
            """
        )
        rem_clusters = int(rem_row["rem_clusters"] if rem_row else 0)
        rem_videos = int(rem_row["rem_videos"] if rem_row else 0)

        return BatchMergeQueueResponse(
            processed_clusters=processed_clusters,
            merged_secondaries_count=merged_secondaries_count,
            remaining_clusters=rem_clusters,
            remaining_duplicate_videos=rem_videos,
            message=f"Successfully merged {processed_clusters} duplicate clusters ({merged_secondaries_count} duplicate videos disabled).",
        )


@router.post("/duplicates/merge-all", response_model=MergeAllDuplicatesResponse)
async def merge_all_duplicates(payload: MergeAllDuplicatesRequest) -> MergeAllDuplicatesResponse:
    """Iteratively merges all duplicate clusters across the entire database until resolved."""
    pool = await get_pool()
    start_time = time.time()
    total_processed = 0
    total_secondaries = 0

    batch_size = payload.batch_size
    max_clusters = payload.max_clusters

    while total_processed < max_clusters:
        async with pool.acquire() as conn:
            cluster_rows = await conn.fetch(
                """
                SELECT lower(trim(title)) as norm_title,
                       count(*) as cnt,
                       array_agg(id ORDER BY id ASC) as ids
                  FROM videos
                 WHERE disabled_at IS NULL
                 GROUP BY lower(trim(title))
                HAVING count(*) >= 2
                 ORDER BY count(*) DESC, lower(trim(title)) ASC
                 LIMIT $1
                """,
                batch_size,
            )

            if not cluster_rows:
                break

            batch_processed = 0
            batch_secondaries = 0

            async with conn.transaction():
                for c in cluster_rows:
                    ids = c["ids"]
                    v_rows = await conn.fetch(
                        """
                        SELECT id, title, slug, thumbnail_url, preview_url, duration_seconds,
                               views, qualities, description, source, source_url
                          FROM videos
                         WHERE id = ANY($1::int[]) AND disabled_at IS NULL
                        """,
                        ids,
                    )
                    if len(v_rows) < 2:
                        continue

                    scored = sorted(v_rows, key=score_video_candidate, reverse=True)
                    primary = scored[0]
                    secondaries = scored[1:]

                    await merge_single_cluster(
                        conn,
                        primary,
                        secondaries,
                        preserve_audio_preview=payload.preserve_audio_preview,
                        prefer_secondary_thumbnail=payload.prefer_secondary_thumbnail,
                    )
                    batch_processed += 1
                    batch_secondaries += len(secondaries)

                if payload.dry_run:
                    duration = round(time.time() - start_time, 2)
                    return MergeAllDuplicatesResponse(
                        total_processed_clusters=batch_processed,
                        total_merged_secondaries=batch_secondaries,
                        remaining_clusters=0,
                        duration_seconds=duration,
                        message=f"Dry run complete: {batch_processed} clusters would be merged ({batch_secondaries} duplicate videos disabled).",
                    )

            total_processed += batch_processed
            total_secondaries += batch_secondaries

            if batch_processed == 0:
                break

    duration = round(time.time() - start_time, 2)
    async with pool.acquire() as conn:
        rem_clusters = await conn.fetchval(
            """
            SELECT count(*) FROM (
                SELECT lower(trim(title)) FROM videos
                WHERE disabled_at IS NULL
                GROUP BY lower(trim(title))
                HAVING count(*) >= 2
            ) t
            """
        ) or 0

    return MergeAllDuplicatesResponse(
        total_processed_clusters=total_processed,
        total_merged_secondaries=total_secondaries,
        remaining_clusters=int(rem_clusters),
        duration_seconds=duration,
        message=f"Merge complete in {duration}s: merged {total_processed} clusters, {total_secondaries} duplicate videos safely disabled.",
    )


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
            SELECT selected_video.video_id, t.id
            FROM unnest($1::int[]) AS selected_video(video_id)
            CROSS JOIN {config.table} t
            WHERE t.id = ANY($2::int[])
              AND t.deleted_at IS NULL
              AND t.undesirable = false
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


@router.post("/batch/remove-taxonomy", response_model=BatchCountResponse)
async def batch_remove_taxonomy(payload: BatchRemoveTaxonomyRequest) -> BatchCountResponse:
    config = get_table_config(payload.kind)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            DELETE FROM {config.join_table}
            WHERE video_id = ANY($1::int[]) AND {config.term_column} = ANY($2::int[])
            RETURNING video_id, {config.term_column} AS term_id
            """,
            payload.video_ids,
            payload.term_ids,
        )
    deleted_pairs = {(row["video_id"], row["term_id"]) for row in rows}
    skipped = [
        video_id
        for video_id in payload.video_ids
        if not any((video_id, term_id) in deleted_pairs for term_id in payload.term_ids)
    ]
    return BatchCountResponse(count=len(deleted_pairs), skipped=skipped)


@router.get("", response_model=list[VideoListItem])
async def list_videos(
    request: Request,
    site: Site | None = Query(None, description="Deprecated, ignored. Video catalog is now global."),
    limit: int = Query(50, ge=1, le=100000),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="Postgres FTS query over title."),
    pornstar: str | None = Query(None, description="Filter by pornstar slug."),
    studio: str | None = Query(None, description="Filter by studio slug."),
    category: str | None = Query(None, description="Filter by category slug."),
    related_to: str | None = Query(None, description="Related-video seed slug."),
    exclude_slug: str | None = Query(None, description="Slug to omit from results."),
    pornstar_gender: str | None = Query(
        "female",
        description=(
            "Filter the embedded pornstars_json by gender. Accepts 'female', 'male', "
            "'unknown', a comma-separated list, or 'all' (no filter — default "
            "for backward compat). Videos themselves are not hidden; only the "
            "embedded pornstar pills are filtered."
        ),
    ),
    disabled: str | None = Query("false", description="Filter by disabled status. 'false'/'enabled' = enabled, 'true'/'disabled' = disabled, 'all'/'none' = all."),
    source: str | None = Query(None, description="Filter by video source."),
    health: str | None = Query(None, description="Filter by catalog health issue."),
    onlyfans: str | None = Query("false", description="Filter by OnlyFans status: 'false' (default, excludes OnlyFans), 'true' (OnlyFans only), 'all' (both)."),
    sort: str = Query("default", description="Sort order: 'default', 'title_asc', 'title_desc', 'views_desc', 'views_asc', 'duration_desc', 'duration_asc', 'date_desc', 'date_asc'"),
    admin: bool = Query(False, description="Admin search mode: strictly matches video title and ID, skips multi-entity OR matching."),
) -> list[VideoListItem]:
    wants_admin = bool(admin)
    wants_disabled = disabled is not None and str(disabled).strip().lower() not in ("false", "0", "enabled")
    if wants_admin or wants_disabled:
        if not await is_admin_request(request):
            if wants_admin:
                admin = False
            if wants_disabled:
                disabled = "false"

    pool = await get_pool()
    where_sql, joins, params = build_video_filters(
        site=site,
        q=q,
        pornstar=pornstar,
        studio=studio,
        category=category,
        related_to=related_to,
        exclude_slug=exclude_slug,
        disabled=disabled,
        source=source,
        health=health,
        onlyfans=onlyfans,
        admin=admin,
    )
    # Optional gender filter on the embedded pornstars_json subquery.
    gender_fragment, gender_params = build_gender_clause(
        pornstar_gender, "a.gender", len(params) + 1
    )
    params.extend(gender_params)
    pornstar_gender_clause = f" AND {gender_fragment}" if gender_fragment else ""
    
    # Determine sorting order
    if sort == "title_asc":
        sort_order = "videos.title ASC"
    elif sort == "title_desc":
        sort_order = "videos.title DESC"
    elif sort == "views_desc":
        sort_order = "videos.views DESC NULLS LAST"
    elif sort == "views_asc":
        sort_order = "videos.views ASC NULLS FIRST"
    elif sort == "duration_desc":
        sort_order = "videos.duration_seconds DESC NULLS LAST"
    elif sort == "duration_asc":
        sort_order = "videos.duration_seconds ASC NULLS FIRST"
    elif sort == "date_desc":
        sort_order = "videos.created_at DESC"
    elif sort == "date_asc":
        sort_order = "videos.created_at ASC"
    else:  # default
        sort_order = "videos.created_at DESC"
        
    # When viewing all or disabled videos (admin mode), include disabled linked terms in chips
    allow_disabled_tax = (disabled in ("all", "none", "true", "1", "disabled"))
    tax_pornstar_disabled = "" if allow_disabled_tax else " AND a.disabled = false"
    tax_studio_disabled = "" if allow_disabled_tax else " AND s.disabled = false"

    limit_param = f"${len(params) + 1}"
    offset_param = f"${len(params) + 2}"
    params.extend([limit, offset])
    sql_base = f"""
        SELECT videos.id, videos.source, videos.title, videos.slug,
               videos.thumbnail_url, videos.preview_url, videos.duration_seconds,
               videos.views, videos.created_at, videos.disabled_at, videos.qualities,
               videos.is_onlyfans,
               (
                 videos.disabled_at IS NOT NULL OR
                 EXISTS (SELECT 1 FROM video_studios vs JOIN studios s ON s.id = vs.studio_id WHERE vs.video_id = videos.id AND s.disabled = true) OR
                 EXISTS (SELECT 1 FROM video_pornstars vp JOIN pornstars p ON p.id = vp.pornstar_id WHERE vp.video_id = videos.id AND p.disabled = true) OR
                 EXISTS (SELECT 1 FROM video_categories vc JOIN categories c ON c.id = vc.category_id WHERE vc.video_id = videos.id AND c.disabled = true)
               ) as is_disabled,
               onlyfans_media.thumbnail_url as of_thumb,
               onlyfans_media.preview_video_url as of_preview,
               onlyfans_media.sprite_url as of_sprite,
               onlyfans_media.sprite_vtt_url as of_sprite_vtt,
               onlyfans_media.tile_width as of_tile_width,
               onlyfans_media.tile_height as of_tile_height,
               onlyfans_media.tile_count as of_tile_count,
               onlyfans_media.tiles_per_row as of_tiles_per_row,
               onlyfans_media.interval_seconds as of_interval_seconds,
               (
                 SELECT coalesce(jsonb_agg(jsonb_build_object('id', a.id, 'name', a.name, 'slug', a.slug, 'disabled', a.disabled)), '[]'::jsonb)
                 FROM video_pornstars va
                 JOIN pornstars a ON a.id = va.pornstar_id
                 WHERE va.video_id = videos.id AND a.deleted_at IS NULL{tax_pornstar_disabled}{pornstar_gender_clause}
               ) as pornstars_json,
               (
                 SELECT coalesce(jsonb_agg(jsonb_build_object('id', s.id, 'name', s.name, 'slug', s.slug, 'disabled', s.disabled)), '[]'::jsonb)
                 FROM video_studios vs
                 JOIN studios s ON s.id = vs.studio_id
                 WHERE vs.video_id = videos.id AND s.deleted_at IS NULL{tax_studio_disabled}
               ) as studios_json
        FROM videos
        LEFT JOIN onlyfans_media ON onlyfans_media.video_id = videos.id
        {joins}
        WHERE {where_sql}
        ORDER BY {sort_order}
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
                
        # Deserialise aggregated pornstars json/string
        pornstars_val = d.pop("pornstars_json", None)
        if isinstance(pornstars_val, str):
            try:
                d["pornstars"] = json.loads(pornstars_val)
            except Exception:
                d["pornstars"] = []
        elif isinstance(pornstars_val, list):
            d["pornstars"] = pornstars_val
        else:
            d["pornstars"] = []
            
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

        if d.get("is_onlyfans") and (d.get("of_sprite") or d.get("of_thumb")):
            d["onlyfans_media"] = {
                "thumbnail_url": d.get("of_thumb") or d.get("thumbnail_url"),
                "preview_video_url": d.get("of_preview") or d.get("preview_url"),
                "sprite_url": d.get("of_sprite"),
                "sprite_vtt_url": d.get("of_sprite_vtt"),
                "tile_width": d.get("of_tile_width") or 160,
                "tile_height": d.get("of_tile_height") or 90,
                "tile_count": d.get("of_tile_count") or 30,
                "tiles_per_row": d.get("of_tiles_per_row") or 6,
                "interval_seconds": float(d.get("of_interval_seconds") or 0.0),
            }
            d["sprite_url"] = d.get("of_sprite")
            if d.get("of_thumb"):
                d["thumbnail_url"] = d.get("of_thumb")
            if d.get("of_preview"):
                d["preview_url"] = d.get("of_preview")
        else:
            d["onlyfans_media"] = None
            d["sprite_url"] = None

        for k in list(d.keys()):
            if k.startswith("of_"):
                del d[k]

        results.append(VideoListItem(**d))
    return results
 
 
@router.get("/count")
async def count_videos(
    request: Request,
    site: Site | None = Query(None, description="Filter to videos belonging to the site."),
    q: str | None = Query(None),
    pornstar: str | None = Query(None),
    studio: str | None = Query(None),
    category: str | None = Query(None),
    disabled: str | None = Query("false", description="Filter by disabled status. 'false'/'enabled' = enabled, 'true'/'disabled' = disabled, 'all'/'none' = all."),
    source: str | None = Query(None, description="Filter by video source."),
    health: str | None = Query(None, description="Filter by catalog health issue."),
    onlyfans: str | None = Query("false", description="Filter by OnlyFans status: 'false' (default, excludes OnlyFans), 'true' (OnlyFans only), 'all' (both)."),
    admin: bool = Query(False, description="Admin search mode: strictly matches video title and ID."),
) -> dict:
    wants_admin = bool(admin)
    wants_disabled = disabled is not None and str(disabled).strip().lower() not in ("false", "0", "enabled")
    if wants_admin or wants_disabled:
        if not await is_admin_request(request):
            if wants_admin:
                admin = False
            if wants_disabled:
                disabled = "false"

    pool = await get_pool()
    where_sql, joins, params = build_video_filters(
        site=site,
        q=q,
        pornstar=pornstar,
        studio=studio,
        category=category,
        disabled=disabled,
        source=source,
        health=health,
        onlyfans=onlyfans,
        admin=admin,
    )
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
    request: Request,
    slug: str,
    site: Site | None = Query(None, description="Filter to ensure the video belongs to the site."),
    pornstar_gender: str | None = Query(
        None,
        description=(
            "Filter returned pornstars by gender (default 'all'). "
            "Same syntax as the list endpoint."
        ),
    ),
    include_disabled: bool = Query(False, description="If true, allows viewing disabled videos (for admin)."),
) -> VideoDetail | None:
    if include_disabled and not await is_admin_request(request):
        include_disabled = False

    pool = await get_pool()
    async with pool.acquire() as conn:
        if not include_disabled:
            where_clause = """
                WHERE slug = $1 AND disabled_at IS NULL
                  AND NOT EXISTS (SELECT 1 FROM video_pornstars vp JOIN pornstars p ON p.id = vp.pornstar_id WHERE vp.video_id = videos.id AND (p.disabled = true OR p.undesirable = true))
                  AND NOT EXISTS (SELECT 1 FROM video_studios vs JOIN studios s ON s.id = vs.studio_id WHERE vs.video_id = videos.id AND (s.disabled = true OR s.undesirable = true))
                  AND NOT EXISTS (SELECT 1 FROM video_categories vc JOIN categories c ON c.id = vc.category_id WHERE vc.video_id = videos.id AND (c.disabled = true OR c.undesirable = true))
            """
        else:
            where_clause = "WHERE slug = $1"
        params = [slug]
        # Video catalog is unified across all sites; any video slug resolves on any site.

        row = await conn.fetchrow(
            f"""
            SELECT id, title, slug, thumbnail_url, preview_url,
                   duration_seconds, views, created_at, updated_at,
                   source, source_url, embed_url, embed_type, qualities,
                   is_onlyfans, description, disabled_at,
                   (
                     videos.disabled_at IS NOT NULL OR
                     EXISTS (SELECT 1 FROM video_studios vs JOIN studios s ON s.id = vs.studio_id WHERE vs.video_id = videos.id AND s.disabled = true) OR
                     EXISTS (SELECT 1 FROM video_pornstars vp JOIN pornstars p ON p.id = vp.pornstar_id WHERE vp.video_id = videos.id AND p.disabled = true) OR
                     EXISTS (SELECT 1 FROM video_categories vc JOIN categories c ON c.id = vc.category_id WHERE vc.video_id = videos.id AND c.disabled = true)
                   ) as is_disabled
            FROM videos
            {where_clause}
            """,
            *params,
        )
        if row is None:
            return None

        video_id = row["id"]
        tax_pornstar_filter = "" if include_disabled else " AND pornstars.disabled = false"
        pornstar_sql = f"""
            SELECT pornstars.id, pornstars.name, pornstars.slug, pornstars.disabled
            FROM pornstars
            JOIN video_pornstars ON video_pornstars.pornstar_id = pornstars.id
            WHERE video_pornstars.video_id = $1 AND pornstars.deleted_at IS NULL{tax_pornstar_filter}
        """
        pornstar_params: list = [video_id]
        gender_fragment, gender_params = build_gender_clause(
            pornstar_gender, "pornstars.gender", len(pornstar_params) + 1
        )
        pornstar_params.extend(gender_params)
        if gender_fragment:
            pornstar_sql += f" AND {gender_fragment}"
        pornstar_sql += " ORDER BY pornstars.name ASC"
        pornstars = await conn.fetch(pornstar_sql, *pornstar_params)

        tax_studio_filter = "" if include_disabled else " AND studios.disabled = false"
        studios = await conn.fetch(
            f"""
            SELECT studios.id, studios.name, studios.slug, studios.disabled
            FROM studios
            JOIN video_studios ON video_studios.studio_id = studios.id
            WHERE video_studios.video_id = $1 AND studios.deleted_at IS NULL{tax_studio_filter}
            ORDER BY studios.name ASC
            """,
            video_id,
        )

        tax_cat_filter = "" if include_disabled else " AND categories.disabled = false"
        categories = await conn.fetch(
            f"""
            SELECT categories.id, categories.name, categories.slug, categories.disabled
            FROM categories
            JOIN video_categories ON video_categories.category_id = categories.id
            WHERE video_categories.video_id = $1 AND categories.deleted_at IS NULL{tax_cat_filter}
            ORDER BY categories.name ASC
            """,
            video_id,
        )
        of_media_row = None
        if row["is_onlyfans"]:
            of_media_row = await conn.fetchrow(
                "SELECT * FROM onlyfans_media WHERE video_id = $1",
                video_id,
            )
    payload = dict(row)
    payload["is_disabled"] = bool(row["is_disabled"])
    
    # Deserialise qualities
    if isinstance(payload.get("qualities"), str):
        try:
            payload["qualities"] = json.loads(payload["qualities"])
        except Exception:
            payload["qualities"] = None

    if of_media_row:
        of_d = dict(of_media_row)
        payload["onlyfans_media"] = {
            "thumbnail_url": of_d.get("thumbnail_url") or payload.get("thumbnail_url"),
            "preview_video_url": of_d.get("preview_video_url") or payload.get("preview_url"),
            "sprite_url": of_d.get("sprite_url"),
            "sprite_vtt_url": of_d.get("sprite_vtt_url"),
            "tile_width": of_d.get("tile_width") or 160,
            "tile_height": of_d.get("tile_height") or 90,
            "tile_count": of_d.get("tile_count") or 30,
            "tiles_per_row": of_d.get("tiles_per_row") or 6,
            "interval_seconds": float(of_d.get("interval_seconds") or 0.0),
        }
        payload["sprite_url"] = of_d.get("sprite_url")
        if of_d.get("thumbnail_url"):
            payload["thumbnail_url"] = of_d.get("thumbnail_url")
        if of_d.get("preview_video_url"):
            payload["preview_url"] = of_d.get("preview_video_url")
    else:
        payload["onlyfans_media"] = None
        payload["sprite_url"] = None

    payload["pornstars"] = [TermRef(**dict(r)) for r in pornstars]
    payload["studios"] = [TermRef(**dict(r)) for r in studios]
    payload["categories"] = [TermRef(**dict(r)) for r in categories]
    return VideoDetail(**payload)


@router.post("/{slug}/view")
async def increment_video_view(slug: str, site: Site | None = Query(None)) -> dict[str, int]:
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
             WHERE slug = $1
         RETURNING views
            """,
            slug,
        )
    if row is None:
        return {"views": 0}
    return {"views": int(row["views"])}


@router.delete("/{video_id}")
async def delete_video(
    video_id: int,
    _admin: None = Depends(require_admin),
) -> dict:
    """Permanently delete a single video and cascade-remove its join references."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            res = await conn.execute("DELETE FROM videos WHERE id = $1", video_id)
            if res == "DELETE 0":
                raise HTTPException(status_code=404, detail=f"Video #{video_id} not found")
    return {"status": "ok", "deleted_id": video_id}
