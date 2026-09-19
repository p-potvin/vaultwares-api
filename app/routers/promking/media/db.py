"""
Prom-King OnlyFans Media Database Operations.
Manages CRUD queries for the `onlyfans_media` association table and updates
video thumbnail/preview references.
"""
from __future__ import annotations

import logging
from typing import Any
import asyncpg

logger = logging.getLogger("promking.media.db")


async def upsert_onlyfans_media(
    conn: asyncpg.Connection,
    video_id: int,
    thumbnail_url: str | None,
    preview_video_url: str | None,
    sprite_url: str | None,
    sprite_vtt_url: str | None,
    tile_width: int = 160,
    tile_height: int = 90,
    tile_count: int = 15,
    tiles_per_row: int = 5,
    interval_seconds: float = 0.0,
) -> dict[str, Any]:
    """
    Inserts or updates the association record in `onlyfans_media`.
    """
    row = await conn.fetchrow(
        """
        INSERT INTO onlyfans_media (
            video_id, thumbnail_url, preview_video_url, sprite_url, sprite_vtt_url,
            tile_width, tile_height, tile_count, tiles_per_row, interval_seconds,
            updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now())
        ON CONFLICT (video_id) DO UPDATE SET
            thumbnail_url = COALESCE(EXCLUDED.thumbnail_url, onlyfans_media.thumbnail_url),
            preview_video_url = COALESCE(EXCLUDED.preview_video_url, onlyfans_media.preview_video_url),
            sprite_url = COALESCE(EXCLUDED.sprite_url, onlyfans_media.sprite_url),
            sprite_vtt_url = COALESCE(EXCLUDED.sprite_vtt_url, onlyfans_media.sprite_vtt_url),
            tile_width = EXCLUDED.tile_width,
            tile_height = EXCLUDED.tile_height,
            tile_count = EXCLUDED.tile_count,
            tiles_per_row = EXCLUDED.tiles_per_row,
            interval_seconds = EXCLUDED.interval_seconds,
            updated_at = now()
        RETURNING *
        """,
        video_id,
        thumbnail_url,
        preview_video_url,
        sprite_url,
        sprite_vtt_url,
        tile_width,
        tile_height,
        tile_count,
        tiles_per_row,
        interval_seconds,
    )
    return dict(row) if row else {}


async def get_onlyfans_media(
    conn: asyncpg.Connection,
    video_id: int,
) -> dict[str, Any] | None:
    """Fetches the onlyfans_media row for a given video_id."""
    row = await conn.fetchrow(
        "SELECT * FROM onlyfans_media WHERE video_id = $1",
        video_id,
    )
    return dict(row) if row else None


async def get_onlyfans_media_batch(
    conn: asyncpg.Connection,
    video_ids: list[int],
) -> dict[int, dict[str, Any]]:
    """Fetches onlyfans_media rows for a collection of video IDs."""
    if not video_ids:
        return {}
    rows = await conn.fetch(
        "SELECT * FROM onlyfans_media WHERE video_id = ANY($1::int[])",
        video_ids,
    )
    return {r["video_id"]: dict(r) for r in rows}


async def sync_video_media_urls(
    conn: asyncpg.Connection,
    video_id: int,
    thumbnail_url: str | None,
    preview_url: str | None,
    duration_seconds: int | None = None,
) -> None:
    """
    Updates the parent videos row to point to the local media assets.
    """
    updates = []
    params: list[Any] = []
    idx = 1

    if thumbnail_url:
        updates.append(f"thumbnail_url = ${idx}")
        params.append(thumbnail_url)
        idx += 1

    if preview_url:
        updates.append(f"preview_url = ${idx}")
        params.append(preview_url)
        idx += 1

    if duration_seconds and duration_seconds > 0:
        updates.append(f"duration_seconds = COALESCE(duration_seconds, ${idx})")
        params.append(duration_seconds)
        idx += 1

    if updates:
        params.append(video_id)
        query = f"UPDATE videos SET {', '.join(updates)}, updated_at = now() WHERE id = ${idx}"
        await conn.execute(query, *params)
